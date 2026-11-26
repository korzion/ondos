#include "MotorController.h"

#include <cmath>

#ifdef ARDUINO
#include <Arduino.h>
#endif

namespace ondos {

namespace {

#ifdef ARDUINO
constexpr uint8_t LEDC_CHANNEL_X = 0;
constexpr uint8_t LEDC_CHANNEL_Y = 1;
constexpr uint32_t MAX_PWM_DUTY = (1u << MotorController::SERVO_PWM_RESOLUTION_BITS) - 1u;

uint32_t pulseUsToDuty(uint32_t pulse_us) {
  if (pulse_us == 0) {
    return 0;
  }
  const uint64_t scaled =
      static_cast<uint64_t>(pulse_us) * static_cast<uint64_t>(MAX_PWM_DUTY);
  const uint32_t duty = static_cast<uint32_t>(scaled / MotorController::SERVO_PERIOD_US);
  return (duty > MAX_PWM_DUTY) ? MAX_PWM_DUTY : duty;
}
#endif

}  // namespace

bool MotorController::begin(int servo_x_pin,
                            int servo_y_pin,
                            PwmWriter writer,
                            void* writer_context) {
  if (servo_x_pin < 0 || servo_y_pin < 0 || servo_x_pin == servo_y_pin) {
    initialized_ = false;
    stopped_ = true;
    return false;
  }

  servo_x_pin_ = servo_x_pin;
  servo_y_pin_ = servo_y_pin;
  pwm_writer_ = writer;
  pwm_writer_ctx_ = writer_context;

#ifdef ARDUINO
  if (pwm_writer_ == nullptr) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    const bool ok_x = ledcAttach(servo_x_pin_, SERVO_PWM_FREQ_HZ, SERVO_PWM_RESOLUTION_BITS);
    const bool ok_y = ledcAttach(servo_y_pin_, SERVO_PWM_FREQ_HZ, SERVO_PWM_RESOLUTION_BITS);
    if (!ok_x || !ok_y) {
      initialized_ = false;
      stopped_ = true;
      return false;
    }
#else
    ledcSetup(LEDC_CHANNEL_X, SERVO_PWM_FREQ_HZ, SERVO_PWM_RESOLUTION_BITS);
    ledcAttachPin(servo_x_pin_, LEDC_CHANNEL_X);
    ledcSetup(LEDC_CHANNEL_Y, SERVO_PWM_FREQ_HZ, SERVO_PWM_RESOLUTION_BITS);
    ledcAttachPin(servo_y_pin_, LEDC_CHANNEL_Y);
#endif
  }
#endif

  initialized_ = true;
  stopped_ = false;
  applyOutputs(0.0f, 0.0f);
  return true;
}

bool MotorController::setCalibration(const ServoCalibration& x_cal,
                                     const ServoCalibration& y_cal) {
  if (!isValidCalibration(x_cal) || !isValidCalibration(y_cal)) {
    return false;
  }
  cal_x_ = x_cal;
  cal_y_ = y_cal;
  if (initialized_ && !stopped_) {
    applyOutputs(current_tilt_x_deg_, current_tilt_y_deg_);
  }
  return true;
}

bool MotorController::setMotorOutput(float tilt_x_deg, float tilt_y_deg) {
  if (!initialized_ || stopped_) {
    return false;
  }
  if (!std::isfinite(tilt_x_deg) || !std::isfinite(tilt_y_deg)) {
    return false;
  }

  applyOutputs(tilt_x_deg, tilt_y_deg);
  return true;
}

bool MotorController::levelPlatform() {
  return setMotorOutput(0.0f, 0.0f);
}

void MotorController::stopMotors() {
  stopped_ = true;
  current_tilt_x_deg_ = 0.0f;
  current_tilt_y_deg_ = 0.0f;
  last_pulse_x_us_ = 0;
  last_pulse_y_us_ = 0;

  if (!initialized_) {
    return;
  }
  writePulseUs(servo_x_pin_, 0);
  writePulseUs(servo_y_pin_, 0);
}

bool MotorController::enableMotors() {
  if (!initialized_) {
    return false;
  }
  stopped_ = false;
  applyOutputs(0.0f, 0.0f);
  return true;
}

bool MotorController::isValidCalibration(const ServoCalibration& cal) {
  if (cal.min_pulse_us == 0 || cal.max_pulse_us >= SERVO_PERIOD_US) {
    return false;
  }
  if (cal.min_pulse_us > cal.neutral_pulse_us || cal.neutral_pulse_us > cal.max_pulse_us) {
    return false;
  }
  if (!std::isfinite(cal.us_per_deg) || cal.us_per_deg <= 0.0f) {
    return false;
  }
  if (cal.axis_sign != 1.0f && cal.axis_sign != -1.0f) {
    return false;
  }
  return true;
}

uint32_t MotorController::tiltToPulseUs(float tilt_deg, const ServoCalibration& cal) {
  const float raw_us =
      static_cast<float>(cal.neutral_pulse_us) + (cal.axis_sign * tilt_deg * cal.us_per_deg);
  if (raw_us <= static_cast<float>(cal.min_pulse_us)) {
    return cal.min_pulse_us;
  }
  if (raw_us >= static_cast<float>(cal.max_pulse_us)) {
    return cal.max_pulse_us;
  }
  return static_cast<uint32_t>(std::lround(raw_us));
}

void MotorController::writePulseUs(int pin, uint32_t pulse_us) {
  if (pwm_writer_ != nullptr) {
    pwm_writer_(pin, pulse_us, pwm_writer_ctx_);
    return;
  }
#ifdef ARDUINO
  const uint32_t duty = pulseUsToDuty(pulse_us);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin, duty);
#else
  const uint8_t channel = (pin == servo_x_pin_) ? LEDC_CHANNEL_X : LEDC_CHANNEL_Y;
  ledcWrite(channel, duty);
#endif
#else
  (void)pin;
  (void)pulse_us;
#endif
}

void MotorController::applyOutputs(float tilt_x_deg, float tilt_y_deg) {
  current_tilt_x_deg_ = tilt_x_deg;
  current_tilt_y_deg_ = tilt_y_deg;
  last_pulse_x_us_ = tiltToPulseUs(tilt_x_deg, cal_x_);
  last_pulse_y_us_ = tiltToPulseUs(tilt_y_deg, cal_y_);
  writePulseUs(servo_x_pin_, last_pulse_x_us_);
  writePulseUs(servo_y_pin_, last_pulse_y_us_);
}

}  // namespace ondos
