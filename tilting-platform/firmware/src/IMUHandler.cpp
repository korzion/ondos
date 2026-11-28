#include "IMUHandler.h"
#include <cmath>

namespace ondos {

bool IMUHandler::writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(addr_);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission(true) == 0;
}

bool IMUHandler::begin(int sda_pin, int scl_pin, uint8_t addr) {
  addr_ = addr;
  initialized_ = false;
  has_valid_read_ = false;
  fault_ = true;

  Wire.begin(sda_pin, scl_pin);
  Wire.setClock(I2C_CLOCK_HZ);

  // Wake up MPU6050, enable ~44 Hz DLPF, and explicitly set +/-250 deg/s and +/-2g ranges
  if (!writeRegister(REG_PWR_MGMT_1, PWR_WAKE) ||
      !writeRegister(REG_CONFIG, DLPF_CFG_44HZ) ||
      !writeRegister(REG_GYRO_CONFIG, GYRO_FS_250DPS) ||
      !writeRegister(REG_ACCEL_CONFIG, ACCEL_FS_2G)) {
    return false;
  }

  initialized_ = true;
  fault_ = false;
  consecutive_errors_ = 0;
  last_read_us_ = micros();
  return true;
}

bool IMUHandler::readRegisters(uint8_t start_reg, uint8_t* buf, uint8_t len) {
  Wire.beginTransmission(addr_);
  Wire.write(start_reg);
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t received = Wire.requestFrom(addr_, len, static_cast<uint8_t>(1));
  if (received != len) return false;

  for (uint8_t i = 0; i < len; ++i) {
    buf[i] = Wire.read();
  }
  return true;
}

bool IMUHandler::readIMU() {
  if (!initialized_) {
    fault_ = true;
    return false;
  }

  uint8_t raw[RAW_PACKET_LEN];
  if (!readRegisters(REG_ACCEL_XOUT_H, raw, RAW_PACKET_LEN)) {
    if (++consecutive_errors_ >= MAX_ERRORS) {
      fault_ = true;
    }
    return false;
  }

  consecutive_errors_ = 0;
  fault_ = false;

  const int16_t ax_raw = static_cast<int16_t>((raw[0] << 8) | raw[1]);
  const int16_t ay_raw = static_cast<int16_t>((raw[2] << 8) | raw[3]);
  const int16_t az_raw = static_cast<int16_t>((raw[4] << 8) | raw[5]);
  const int16_t gx_raw = static_cast<int16_t>((raw[8] << 8) | raw[9]);
  const int16_t gy_raw = static_cast<int16_t>((raw[10] << 8) | raw[11]);

  if (ax_raw == 0 && ay_raw == 0 && az_raw == 0) {
    fault_ = true;
    return false;
  }

  const float ax_g = ax_raw / ACCEL_LSB_PER_G;
  const float ay_g = ay_raw / ACCEL_LSB_PER_G;
  const float az_g = az_raw / ACCEL_LSB_PER_G;

  const float gx_deg_s = (gx_raw / GYRO_LSB_PER_DEG_S) - gyro_bias_x_deg_s_;
  const float gy_deg_s = (gy_raw / GYRO_LSB_PER_DEG_S) - gyro_bias_y_deg_s_;

  const uint32_t now_us = micros();
  float dt_s = (now_us - last_read_us_) * US_TO_S;
  last_read_us_ = now_us;
  if (dt_s <= 0.0f || dt_s > MAX_DT_S) {
    dt_s = DEFAULT_DT_S;
  }

  // Board frame (D4): +x edge down gives ax_g < 0, so use atan2(-ax_g, az_g)
  const float accel_x_deg = SIGN_X * (std::atan2(-ax_g, az_g) * RAD_TO_DEG_F) - offset_x_deg_;
  const float accel_y_deg = SIGN_Y * (std::atan2(-ay_g, az_g) * RAD_TO_DEG_F) - offset_y_deg_;

  if (!has_valid_read_) {
    tilt_.tilt_x_deg = accel_x_deg;
    tilt_.tilt_y_deg = accel_y_deg;
    has_valid_read_ = true;
    return true;
  }

  const float gyro_rate_x_deg_s = SIGN_X * gy_deg_s;
  const float gyro_rate_y_deg_s = -SIGN_Y * gx_deg_s;

  tilt_.tilt_x_deg =
      ALPHA * (tilt_.tilt_x_deg + gyro_rate_x_deg_s * dt_s) + (1.0f - ALPHA) * accel_x_deg;
  tilt_.tilt_y_deg =
      ALPHA * (tilt_.tilt_y_deg + gyro_rate_y_deg_s * dt_s) + (1.0f - ALPHA) * accel_y_deg;

  return true;
}

bool IMUHandler::calibrate(uint16_t samples) {
  if (!initialized_ || samples == 0) return false;

  double sum_x_deg = 0.0;
  double sum_y_deg = 0.0;
  double sum_gx_deg_s = 0.0;
  double sum_gy_deg_s = 0.0;
  uint16_t valid = 0;

  for (uint16_t i = 0; i < samples; ++i) {
    uint8_t raw[RAW_PACKET_LEN];
    if (readRegisters(REG_ACCEL_XOUT_H, raw, RAW_PACKET_LEN)) {
      const int16_t ax_raw = static_cast<int16_t>((raw[0] << 8) | raw[1]);
      const int16_t ay_raw = static_cast<int16_t>((raw[2] << 8) | raw[3]);
      const int16_t az_raw = static_cast<int16_t>((raw[4] << 8) | raw[5]);
      const int16_t gx_raw = static_cast<int16_t>((raw[8] << 8) | raw[9]);
      const int16_t gy_raw = static_cast<int16_t>((raw[10] << 8) | raw[11]);

      if (ax_raw != 0 || ay_raw != 0 || az_raw != 0) {
        const float ax_g = ax_raw / ACCEL_LSB_PER_G;
        const float ay_g = ay_raw / ACCEL_LSB_PER_G;
        const float az_g = az_raw / ACCEL_LSB_PER_G;

        sum_x_deg += SIGN_X * (std::atan2(-ax_g, az_g) * RAD_TO_DEG_F);
        sum_y_deg += SIGN_Y * (std::atan2(-ay_g, az_g) * RAD_TO_DEG_F);
        sum_gx_deg_s += gx_raw / GYRO_LSB_PER_DEG_S;
        sum_gy_deg_s += gy_raw / GYRO_LSB_PER_DEG_S;
        ++valid;
      }
    }
    delay(CALIBRATE_SAMPLE_DELAY_MS);
  }

  if (valid == 0 || valid < (samples / 2)) {
    fault_ = true;
    return false;
  }

  offset_x_deg_ = static_cast<float>(sum_x_deg / valid);
  offset_y_deg_ = static_cast<float>(sum_y_deg / valid);
  gyro_bias_x_deg_s_ = static_cast<float>(sum_gx_deg_s / valid);
  gyro_bias_y_deg_s_ = static_cast<float>(sum_gy_deg_s / valid);
  tilt_.tilt_x_deg = 0.0f;
  tilt_.tilt_y_deg = 0.0f;
  has_valid_read_ = true;
  last_read_us_ = micros();
  return true;
}

}  // namespace ondos