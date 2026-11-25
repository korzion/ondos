#pragma once
#include <Arduino.h>

#include "../../../shared/firmware/include/ondos_packets.h"

namespace ondos {

struct PlatformSettings {
  float max_tilt_deg = 12.0f;
  float max_tilt_speed_deg_s = 60.0f;
  float glove_gain = 1.0f;
  float glove_deadzone_deg = 1.5f;
};

class PlatformController {
 public:
  static constexpr int MODE_BUTTON_PIN = 6;
  static constexpr int MODE_LED_PIN = 7;

  // Left-header pins: GPIO 6 = Mode Button (INPUT_PULLUP), GPIO 7 = Mode LED
  void begin(int mode_button_pin = MODE_BUTTON_PIN, int mode_led_pin = MODE_LED_PIN);

  // Sets laptop target tilt (AI or PID mode) and resets the 200 ms command watchdog.
  void setTargetTilt(float target_x_deg, float target_y_deg, uint32_t now_ms);

  // Updates active mode/state from HostState, button presses, and laptop-link timeouts.
  // Safe to call separately before update(now_ms); guards against duplicate runs in the same ms.
  void updateMode(uint32_t now_ms);

  // Main control step: enforces safety, timeouts, deadzone/gain, angle & speed limits.
  void update(uint32_t now_ms);

  // --- Inputs fed by SerialHandler / GloveHandler / SafetyManager ---
  void onHostState(State state, Mode mode, uint32_t now_ms);
  void onGloveData(float hand_tilt_x_deg, float hand_tilt_y_deg, uint32_t now_ms);
  void onSettings(const serial::Settings& settings);
  void onCommand(SerialCommand cmd);
  void setPhysicalEStop(bool pressed);
  void setFault(Fault fault);

  // --- Outputs read by MotorController, SerialHandler, and GloveHandler ---
  float getAppliedTiltX() const { return applied_tilt_x_deg_; }
  float getAppliedTiltY() const { return applied_tilt_y_deg_; }
  PlatformSource getSource() const { return active_source_; }
  Mode getMode() const { return current_mode_; }
  State getEffectiveState() const { return effective_state_; }
  uint32_t getModeButtonPresses() const { return mode_button_presses_; }
  uint8_t getCalibrateRequest() const { return calibrate_request_; }
  bool isEStopActive() const { return is_e_stop_; }
  bool isLaptopConnected(uint32_t now_ms) const;
  bool isGloveConnected(uint32_t now_ms) const;
  Fault getFault() const { return fault_; }
  const PlatformSettings& getSettings() const { return settings_; }

 private:
  void pollModeButton(uint32_t now_ms);
  void updateModeLed(uint32_t now_ms);
  float applyDeadzoneAndGain(float raw_deg) const;
  float clampTilt(float deg) const;
  float slewLimit(float current_deg, float target_deg, float max_step_deg) const;

  int button_pin_ = MODE_BUTTON_PIN;
  int led_pin_ = MODE_LED_PIN;

  PlatformSettings settings_{};

  // State & mode tracking
  Mode current_mode_ = Mode::Glove;
  State host_state_ = State::Setup;
  State effective_state_ = State::NoLaptop;
  PlatformSource active_source_ = PlatformSource::None;
  Fault fault_ = Fault::None;

  // Explicit reception flags & single-clock (ms) timestamps
  bool ever_received_host_state_ = false;
  bool ever_received_target_tilt_ = false;
  bool ever_received_glove_data_ = false;
  uint32_t last_host_state_ms_ = 0;
  uint32_t last_target_tilt_ms_ = 0;
  uint32_t last_glove_data_ms_ = 0;

  bool has_updated_ = false;
  uint32_t last_update_ms_ = 0;
  bool has_mode_updated_ = false;
  uint32_t last_mode_update_ms_ = 0;

  // Standalone (no-laptop) glove enable latch (IF-02)
  bool offline_glove_enabled_ = false;
  bool was_laptop_connected_ = false;

  // E-stop tracking
  bool physical_e_stop_ = false;
  bool software_e_stop_ = false;
  bool is_e_stop_ = false;
  bool was_e_stop_ = false;

  // Button debounce & press detection
  bool last_button_reading_ = true;
  bool stable_button_state_ = true;
  uint32_t last_debounce_ms_ = 0;
  uint32_t button_press_start_ms_ = 0;
  bool long_press_handled_ = false;
  uint32_t mode_button_presses_ = 0;
  uint8_t calibrate_request_ = 0;

  // Raw and applied tilt targets
  float raw_laptop_target_x_ = 0.0f;
  float raw_laptop_target_y_ = 0.0f;
  float raw_glove_x_ = 0.0f;
  float raw_glove_y_ = 0.0f;
  float applied_tilt_x_deg_ = 0.0f;
  float applied_tilt_y_deg_ = 0.0f;

  static constexpr uint32_t DEBOUNCE_MS = 30;
  static constexpr uint32_t LONG_PRESS_MS = 3000;
};

}  // namespace ondos