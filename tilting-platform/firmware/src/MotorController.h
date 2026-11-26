#pragma once

#include <cstdint>

namespace ondos {

struct ServoCalibration {
  uint32_t neutral_pulse_us = 1500;
  uint32_t min_pulse_us = 500;
  uint32_t max_pulse_us = 2500;
  float us_per_deg = 1000.0f / 90.0f;  // ~11.11 us/deg for 180-deg MG996R
  float axis_sign = 1.0f;              // +1.0f or -1.0f to match board frame (D4)
};

// Optional hardware output callback; pulse_us == 0 turns PWM off (0% duty).
using PwmWriter = void (*)(int pin, uint32_t pulse_us, void* context);

// Drives the two axis servos directly from PlatformController's bounded tilt.
// Per #22 / #27 decision, PlatformController owns +/-max_tilt_deg clamping and
// max_tilt_speed_deg_s slew limiting; MotorController enforces servo pulse bounds.
class MotorController {
 public:
  // Safe ESP32-S3 GPIO defaults (avoiding GPIO 6/7 mode UI and GPIO 8/9 I2C)
  static constexpr int DEFAULT_SERVO_X_PIN = 4;
  static constexpr int DEFAULT_SERVO_Y_PIN = 5;

  static constexpr uint32_t SERVO_PWM_FREQ_HZ = 50;
  static constexpr uint32_t SERVO_PERIOD_US = 20000;
  static constexpr uint8_t SERVO_PWM_RESOLUTION_BITS = 16;

  // Initializes PWM outputs for both axes and moves the platform to level.
  bool begin(int servo_x_pin = DEFAULT_SERVO_X_PIN,
             int servo_y_pin = DEFAULT_SERVO_Y_PIN,
             PwmWriter writer = nullptr,
             void* writer_context = nullptr);

  // Sets mechanical calibration (neutral trim, pulse range, axis sign) per axis.
  bool setCalibration(const ServoCalibration& x_cal, const ServoCalibration& y_cal);

  // Commands bounded board-frame tilts in degrees to both servo PWM channels.
  // Returns false if motors are stopped/uninitialized or inputs are non-finite.
  bool setMotorOutput(float tilt_x_deg, float tilt_y_deg);

  // Moves both axes to level (0, 0).
  bool levelPlatform();

  // Cuts PWM output on both servos and locks motor control until enableMotors().
  void stopMotors();

  // Unlocks motors after stopMotors() and re-engages PWM at level (0, 0).
  bool enableMotors();

  bool isInitialized() const { return initialized_; }
  bool isStopped() const { return stopped_; }
  float getTiltXDeg() const { return current_tilt_x_deg_; }
  float getTiltYDeg() const { return current_tilt_y_deg_; }
  uint32_t getPulseXUs() const { return last_pulse_x_us_; }
  uint32_t getPulseYUs() const { return last_pulse_y_us_; }

 private:
  static bool isValidCalibration(const ServoCalibration& cal);
  static uint32_t tiltToPulseUs(float tilt_deg, const ServoCalibration& cal);

  void writePulseUs(int pin, uint32_t pulse_us);
  void applyOutputs(float tilt_x_deg, float tilt_y_deg);

  int servo_x_pin_ = DEFAULT_SERVO_X_PIN;
  int servo_y_pin_ = DEFAULT_SERVO_Y_PIN;
  PwmWriter pwm_writer_ = nullptr;
  void* pwm_writer_ctx_ = nullptr;

  bool initialized_ = false;
  bool stopped_ = true;

  ServoCalibration cal_x_{};
  ServoCalibration cal_y_{};

  float current_tilt_x_deg_ = 0.0f;
  float current_tilt_y_deg_ = 0.0f;
  uint32_t last_pulse_x_us_ = 0;
  uint32_t last_pulse_y_us_ = 0;
};

}  // namespace ondos
