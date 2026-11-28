#pragma once
#include <Arduino.h>
#include <Wire.h>

namespace ondos {

struct PlateTilt {
  float tilt_x_deg = 0.0f;  // > 0 rolls ball to +x (board frame D4)
  float tilt_y_deg = 0.0f;  // > 0 rolls ball to +y (board frame D4)
};

class IMUHandler {
 public:
  static constexpr int DEFAULT_SDA_PIN = 8;
  static constexpr int DEFAULT_SCL_PIN = 9;
  static constexpr uint8_t DEFAULT_I2C_ADDR = 0x68;

  // Initializes I2C and configures MPU6050 wake, DLPF, and +/-2g / +/-250 deg/s ranges.
  bool begin(int sda_pin = DEFAULT_SDA_PIN, int scl_pin = DEFAULT_SCL_PIN,
             uint8_t addr = DEFAULT_I2C_ADDR);

  // Reads MPU6050 accel + gyro and updates filtered plate tilt. Returns false on I2C failure.
  bool readIMU();

  // Returns the latest filtered plate tilt in degrees (board frame).
  PlateTilt getTilt() const { return tilt_; }

  // True if sensor initialization failed or consecutive I2C reads failed.
  bool hasFault() const { return fault_; }

  // Captures flat resting angles and gyro zero-rate bias (call when plate is level and still).
  bool calibrate(uint16_t samples = 50);

 private:
  bool writeRegister(uint8_t reg, uint8_t value);
  bool readRegisters(uint8_t start_reg, uint8_t* buf, uint8_t len);

  uint8_t addr_ = DEFAULT_I2C_ADDR;
  bool initialized_ = false;
  bool has_valid_read_ = false;
  bool fault_ = true;
  uint8_t consecutive_errors_ = 0;
  uint32_t last_read_us_ = 0;

  PlateTilt tilt_;
  float offset_x_deg_ = 0.0f;
  float offset_y_deg_ = 0.0f;
  float gyro_bias_x_deg_s_ = 0.0f;
  float gyro_bias_y_deg_s_ = 0.0f;

  // Flip to -1.0f if the GY-521 sensor is mounted rotated on the plate
  static constexpr float SIGN_X = 1.0f;
  static constexpr float SIGN_Y = 1.0f;
  static constexpr float ALPHA = 0.96f;
  static constexpr float RAD_TO_DEG_F = 57.2957795f;
  static constexpr uint8_t MAX_ERRORS = 5;

  // MPU6050 registers and configuration values
  static constexpr uint32_t I2C_CLOCK_HZ = 400000;
  static constexpr uint8_t REG_CONFIG = 0x1A;
  static constexpr uint8_t REG_GYRO_CONFIG = 0x1B;
  static constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
  static constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
  static constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;

  static constexpr uint8_t PWR_WAKE = 0x00;
  static constexpr uint8_t DLPF_CFG_44HZ = 0x03;
  static constexpr uint8_t GYRO_FS_250DPS = 0x00;
  static constexpr uint8_t ACCEL_FS_2G = 0x00;

  static constexpr uint8_t RAW_PACKET_LEN = 14;
  static constexpr float ACCEL_LSB_PER_G = 16384.0f;
  static constexpr float GYRO_LSB_PER_DEG_S = 131.0f;

  static constexpr float US_TO_S = 1e-6f;
  static constexpr float MAX_DT_S = 0.2f;
  static constexpr float DEFAULT_DT_S = 0.02f;
  static constexpr uint32_t CALIBRATE_SAMPLE_DELAY_MS = 5;
};

}  // namespace ondos