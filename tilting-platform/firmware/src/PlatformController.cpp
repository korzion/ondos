#include "PlatformController.h"
#include <cmath>

namespace ondos {

void PlatformController::begin(int mode_button_pin, int mode_led_pin) {
  button_pin_ = mode_button_pin;
  led_pin_ = mode_led_pin;

  if (button_pin_ >= 0) {
    pinMode(button_pin_, INPUT_PULLUP);
  }
  if (led_pin_ >= 0) {
    pinMode(led_pin_, OUTPUT);
    digitalWrite(led_pin_, LOW);
  }

  current_mode_ = Mode::Glove;
  host_state_ = State::Setup;
  effective_state_ = State::NoLaptop;
  active_source_ = PlatformSource::None;
  offline_glove_enabled_ = false;
  last_update_us_ = micros();
}

void PlatformController::onHostState(State state, Mode mode, uint32_t now_ms) {
  ever_received_host_state_ = true;
  last_host_state_ms_ = now_ms;
  host_state_ = state;
  current_mode_ = mode;
}

void PlatformController::setTargetTilt(float target_x_deg, float target_y_deg, uint32_t now_ms) {
  if (!std::isfinite(target_x_deg) || !std::isfinite(target_y_deg)) {
    return;
  }
  raw_laptop_target_x_ = target_x_deg;
  raw_laptop_target_y_ = target_y_deg;
  last_target_tilt_ms_ = now_ms;
}

void PlatformController::onGloveData(float hand_tilt_x_deg, float hand_tilt_y_deg, uint32_t now_ms) {
  if (!std::isfinite(hand_tilt_x_deg) || !std::isfinite(hand_tilt_y_deg)) {
    return;
  }
  raw_glove_x_ = hand_tilt_x_deg;
  raw_glove_y_ = hand_tilt_y_deg;
  last_glove_data_ms_ = now_ms;
}

void PlatformController::onSettings(const serial::Settings& settings) {
  if (std::isfinite(settings.max_tilt_deg) && settings.max_tilt_deg >= 0.0f) {
    settings_.max_tilt_deg = settings.max_tilt_deg;
  }
  if (std::isfinite(settings.max_tilt_speed_deg_s) && settings.max_tilt_speed_deg_s > 0.0f) {
    settings_.max_tilt_speed_deg_s = settings.max_tilt_speed_deg_s;
  }
  if (std::isfinite(settings.glove_gain) && settings.glove_gain >= 0.0f) {
    settings_.glove_gain = settings.glove_gain;
  }
  if (std::isfinite(settings.glove_deadzone_deg) && settings.glove_deadzone_deg >= 0.0f) {
    settings_.glove_deadzone_deg = settings.glove_deadzone_deg;
  }
}

void PlatformController::onCommand(SerialCommand cmd) {
  switch (cmd) {
    case SerialCommand::EStop:
      software_e_stop_ = true;
      break;
    case SerialCommand::ClearEStop:
      // Refused while physical E-stop button is still pressed (IF-02)
      if (!physical_e_stop_) {
        software_e_stop_ = false;
      }
      break;
    case SerialCommand::CalibrateGlove:
      if (effective_state_ != State::Playing) {
        ++calibrate_request_;
      }
      break;
  }
}

void PlatformController::setPhysicalEStop(bool pressed) {
  physical_e_stop_ = pressed;
  if (pressed) {
    // Hardware E-stop immediately cuts motor power and locks until cleared (IF-02)
    software_e_stop_ = true;
  }
}

void PlatformController::setFault(Fault fault) {
  fault_ = fault;
}

bool PlatformController::isLaptopConnected(uint32_t now_ms) const {
  if (!ever_received_host_state_) return false;
  return (now_ms - last_host_state_ms_) <= HOST_STATE_TIMEOUT_MS;
}

bool PlatformController::isGloveConnected(uint32_t now_ms) const {
  if (last_glove_data_ms_ == 0) return false;
  return (now_ms - last_glove_data_ms_) <= GLOVE_DATA_LOSS_MS;
}

void PlatformController::pollModeButton(uint32_t now_ms) {
  if (button_pin_ < 0) return;

  bool reading = (digitalRead(button_pin_) == HIGH);
  if (reading != last_button_reading_) {
    last_debounce_ms_ = now_ms;
    last_button_reading_ = reading;
  }

  if ((now_ms - last_debounce_ms_) < DEBOUNCE_MS) {
    return;
  }

  if (reading != stable_button_state_) {
    stable_button_state_ = reading;

    if (!stable_button_state_) {
      // Button pressed (active LOW)
      button_press_start_ms_ = now_ms;
      long_press_handled_ = false;
    } else {
      // Button released
      if (!long_press_handled_) {
        // Short press (IF-02): counted for GameManager, or enables glove offline
        ++mode_button_presses_;
        if (!isLaptopConnected(now_ms) && !is_e_stop_) {
          current_mode_ = Mode::Glove;
          offline_glove_enabled_ = true;
        }
      }
    }
  }

  // Check 3-second long press while held down (IF-02: ignored in playing)
  if (!stable_button_state_ && !long_press_handled_) {
    if ((now_ms - button_press_start_ms_) >= LONG_PRESS_MS) {
      long_press_handled_ = true;
      if (effective_state_ != State::Playing) {
        ++calibrate_request_;
      }
    }
  }
}

void PlatformController::updateMode(uint32_t now_ms) {
  pollModeButton(now_ms);

  const bool laptop_ok = isLaptopConnected(now_ms);

  // Detect laptop link drop transition (IF-02 ESP32 behaviour)
  if (was_laptop_connected_ && !laptop_ok) {
    if (host_state_ == State::Playing && current_mode_ == Mode::Glove) {
      // Keep following hand if laptop drops during a glove game
      offline_glove_enabled_ = true;
    } else {
      // Level and wait for one short press
      offline_glove_enabled_ = false;
      current_mode_ = Mode::Glove;
    }
  }
  was_laptop_connected_ = laptop_ok;

  // Update E-stop state
  if (laptop_ok) {
    is_e_stop_ = physical_e_stop_ || software_e_stop_ || (host_state_ == State::EStop);
  } else {
    // Without laptop, E-stop clears when the physical button is released (IF-02)
    is_e_stop_ = physical_e_stop_;
    software_e_stop_ = false;
    if (was_e_stop_ && !is_e_stop_) {
      // Stay level after release until one short press (IF-02)
      offline_glove_enabled_ = false;
    }
  }
  was_e_stop_ = is_e_stop_;

  if (is_e_stop_) {
    effective_state_ = State::EStop;
  } else if (laptop_ok) {
    effective_state_ = host_state_;
    offline_glove_enabled_ = false;
  } else {
    effective_state_ = State::NoLaptop;
    current_mode_ = Mode::Glove;
  }
}

float PlatformController::applyDeadzoneAndGain(float raw_deg) const {
  const float dz = settings_.glove_deadzone_deg;
  if (std::fabs(raw_deg) <= dz) {
    return 0.0f;
  }
  const float shifted = (raw_deg > 0.0f) ? (raw_deg - dz) : (raw_deg + dz);
  return shifted * settings_.glove_gain;
}

float PlatformController::clampTilt(float deg) const {
  const float limit = settings_.max_tilt_deg;
  if (deg > limit) return limit;
  if (deg < -limit) return -limit;
  return deg;
}

float PlatformController::slewLimit(float current_deg, float target_deg, float max_step_deg) const {
  const float diff = target_deg - current_deg;
  if (diff > max_step_deg) return current_deg + max_step_deg;
  if (diff < -max_step_deg) return current_deg - max_step_deg;
  return target_deg;
}

void PlatformController::update(uint32_t now_ms) {
  uint32_t now_us = micros();
  float dt_s = (now_us - last_update_us_) * 1e-6f;
  last_update_us_ = now_us;
  if (dt_s <= 0.0f || dt_s > 0.2f) dt_s = 0.02f;

  updateMode(now_ms);

  // Immediate zero & lock on E-stop or active fault (IF-02 / A.8)
  if (is_e_stop_ || fault_ != Fault::None) {
    active_source_ = PlatformSource::None;
    applied_tilt_x_deg_ = 0.0f;
    applied_tilt_y_deg_ = 0.0f;
    updateModeLed(now_ms);
    return;
  }

  float desired_x = 0.0f;
  float desired_y = 0.0f;
  PlatformSource next_source = PlatformSource::None;

  const bool laptop_ok = isLaptopConnected(now_ms);
  const bool glove_ok = isGloveConnected(now_ms);

  if (laptop_ok) {
    if (effective_state_ == State::Playing) {
      if (current_mode_ == Mode::Glove) {
        if (glove_ok) {
          next_source = PlatformSource::Glove;
          desired_x = applyDeadzoneAndGain(raw_glove_x_);
          desired_y = applyDeadzoneAndGain(raw_glove_y_);
        }
      } else if (current_mode_ == Mode::Ai || current_mode_ == Mode::Simple) {
        // Enforce 200 ms command timeout (A-R5, IF-02)
        const bool target_fresh =
            (last_target_tilt_ms_ != 0) && ((now_ms - last_target_tilt_ms_) <= COMMAND_TIMEOUT_MS);
        if (target_fresh) {
          next_source = (current_mode_ == Mode::Ai) ? PlatformSource::Ai : PlatformSource::Simple;
          desired_x = raw_laptop_target_x_;
          desired_y = raw_laptop_target_y_;
        }
      }
    }
  } else {
    // Offline (no laptop): follow glove only if latched by button or mid-glove-game drop
    if (offline_glove_enabled_ && glove_ok) {
      next_source = PlatformSource::Glove;
      desired_x = applyDeadzoneAndGain(raw_glove_x_);
      desired_y = applyDeadzoneAndGain(raw_glove_y_);
    }
  }

  active_source_ = next_source;
  desired_x = clampTilt(desired_x);
  desired_y = clampTilt(desired_y);

  const float max_step = settings_.max_tilt_speed_deg_s * dt_s;
  applied_tilt_x_deg_ = slewLimit(applied_tilt_x_deg_, desired_x, max_step);
  applied_tilt_y_deg_ = slewLimit(applied_tilt_y_deg_, desired_y, max_step);

  updateModeLed(now_ms);
}

void PlatformController::updateModeLed(uint32_t now_ms) {
  if (led_pin_ < 0) return;

  if (is_e_stop_ || fault_ != Fault::None) {
    digitalWrite(led_pin_, LOW);
    return;
  }

  switch (current_mode_) {
    case Mode::Glove:
      digitalWrite(led_pin_, HIGH);
      break;
    case Mode::Ai:
      // Slow blink (2 Hz)
      digitalWrite(led_pin_, ((now_ms / 250) % 2 == 0) ? HIGH : LOW);
      break;
    case Mode::Simple:
      // Fast blink (5 Hz)
      digitalWrite(led_pin_, ((now_ms / 100) % 2 == 0) ? HIGH : LOW);
      break;
  }
}

}  // namespace ondos