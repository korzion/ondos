#include "IMUHandler.h"
#include <cmath>

namespace ondos {

bool IMUHandler::begin(int sda_pin, int scl_pin, uint8_t addr) {
  addr_ = addr;
  Wire.begin(sda_pin, scl_pin);
  Wire.setClock(400000);

  // Wake up MPU6050 (PWR_MGMT_1 = 0x6B -> 0x00)
  Wire.beginTransmission(addr_);
  Wire.write(0x6B);
  Wire.write(0x00);
  if (Wire.endTransmission(true) != 0) {
    initialized_ = false;
    fault_ = true;
    return false;
  }

  // Enable Digital Low Pass Filter (CONFIG = 0x1A -> 0x03, ~44 Hz bandwidth)
  Wire.beginTransmission(addr_);
  Wire.write(0x1A);
  Wire.write(0x03);
  Wire.endTransmission(true);

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

  uint8_t raw[14];
  if (!readRegisters(0x3B, raw, sizeof(raw))) {
    if (++consecutive_errors_ >= MAX_ERRORS) {
      fault_ = true;
    }
    return false;
  }

  consecutive_errors_ = 0;
  fault_ = false;

  int16_t ax_raw = static_cast<int16_t>((raw[0] << 8) | raw[1]);
  int16_t ay_raw = static_cast<int16_t>((raw[2] << 8) | raw[3]);
  int16_t az_raw = static_cast<int16_t>((raw[4] << 8) | raw[5]);
  int16_t gx_raw = static_cast<int16_t>((raw[8] << 8) | raw[9]);
  int16_t gy_raw = static_cast<int16_t>((raw[10] << 8) | raw[11]);

  if (ax_raw == 0 && ay_raw == 0 && az_raw == 0) {
    fault_ = true;
    return false;
  }

  float ax = ax_raw / 16384.0f;
  float ay = ay_raw / 16384.0f;
  float az = az_raw / 16384.0f;

  float gx_deg_s = gx_raw / 131.0f;
  float gy_deg_s = gy_raw / 131.0f;

  uint32_t now_us = micros();
  float dt_s = (now_us - last_read_us_) * 1e-6f;
  last_read_us_ = now_us;
  if (dt_s <= 0.0f || dt_s > 0.2f) dt_s = 0.02f;

  // Board frame (D4): tilt_x_deg > 0 rolls ball to +x, tilt_y_deg > 0 rolls ball to +y
  float accel_x_deg = SIGN_X * (std::atan2(ax, az) * RAD_TO_DEG_F) - offset_x_deg_;
  float accel_y_deg = SIGN_Y * (std::atan2(ay, az) * RAD_TO_DEG_F) - offset_y_deg_;

  float gyro_rate_x = SIGN_X * gy_deg_s;
  float gyro_rate_y = -SIGN_Y * gx_deg_s;

  tilt_.tilt_x_deg = ALPHA * (tilt_.tilt_x_deg + gyro_rate_x * dt_s) + (1.0f - ALPHA) * accel_x_deg;
  tilt_.tilt_y_deg = ALPHA * (tilt_.tilt_y_deg + gyro_rate_y * dt_s) + (1.0f - ALPHA) * accel_y_deg;

  return true;
}

bool IMUHandler::calibrate(uint16_t samples) {
  if (!initialized_ || samples == 0) return false;

  double sum_x = 0.0;
  double sum_y = 0.0;
  uint16_t valid = 0;

  for (uint16_t i = 0; i < samples; ++i) {
    uint8_t raw[6];
    if (readRegisters(0x3B, raw, sizeof(raw))) {
      int16_t ax_raw = static_cast<int16_t>((raw[0] << 8) | raw[1]);
      int16_t ay_raw = static_cast<int16_t>((raw[2] << 8) | raw[3]);
      int16_t az_raw = static_cast<int16_t>((raw[4] << 8) | raw[5]);
      if (ax_raw != 0 || ay_raw != 0 || az_raw != 0) {
        sum_x += SIGN_X * (std::atan2(ax_raw / 16384.0f, az_raw / 16384.0f) * RAD_TO_DEG_F);
        sum_y += SIGN_Y * (std::atan2(ay_raw / 16384.0f, az_raw / 16384.0f) * RAD_TO_DEG_F);
        valid++;
      }
    }
    delay(5);
  }

  if (valid < samples / 2) {
    fault_ = true;
    return false;
  }

  offset_x_deg_ = static_cast<float>(sum_x / valid);
  offset_y_deg_ = static_cast<float>(sum_y / valid);
  tilt_.tilt_x_deg = 0.0f;
  tilt_.tilt_y_deg = 0.0f;
  return true;
}

}  // namespace ondos