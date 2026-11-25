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
  // Default ESP32-S3 I2C pins (GPIO8 = SDA, GPIO9 = SCL) and MPU6050 address 0x68
  bool begin(int sda_pin = 8, int scl_pin = 9, uint8_t addr = 0x68);

  // Reads MPU6050 accel + gyro and updates filtered plate tilt. Returns false on I2C failure.
  bool readIMU();

  // Returns the latest filtered plate tilt in degrees (board frame).
  PlateTilt getTilt() const { return tilt_; }

  // True if sensor initialization failed or consecutive I2C reads failed.
  bool hasFault() const { return fault_; }

  // Captures current flat resting angles as zero offset (call when plate is level).
  bool calibrate(uint16_t samples = 50);

 private:
  bool readRegisters(uint8_t start_reg, uint8_t* buf, uint8_t len);

  uint8_t addr_ = 0x68;
  bool initialized_ = false;
  bool fault_ = true;
  uint8_t consecutive_errors_ = 0;
  uint32_t last_read_us_ = 0;

  PlateTilt tilt_;
  float offset_x_deg_ = 0.0f;
  float offset_y_deg_ = 0.0f;

  // Flip to -1.0f if the GY-521 sensor is mounted rotated on the plate
  static constexpr float SIGN_X = 1.0f;
  static constexpr float SIGN_Y = 1.0f;
  static constexpr float ALPHA = 0.96f;
  static constexpr float RAD_TO_DEG_F = 57.2957795f;
  static constexpr uint8_t MAX_ERRORS = 5;
};

}  // namespace ondos