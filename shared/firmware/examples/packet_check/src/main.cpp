// Sends a known PlatformState frame over USB serial so the Python side can check the decoding.
// Uses only the shared headers: no packet layout is written by hand.
#include <Arduino.h>

#include "ondos_framing.h"
#include "ondos_packets.h"

using namespace ondos;

void setup() { Serial.begin(921600); }

void loop() {
  static uint32_t presses = 0;
  serial::PlatformState s;
  s.tilt_x_deg = 1.5f;
  s.tilt_y_deg = -0.5f;
  s.applied_tilt_x_deg = 1.0f;
  s.applied_tilt_y_deg = 0.0f;
  s.source = static_cast<uint8_t>(PlatformSource::Glove);
  s.mode = static_cast<uint8_t>(Mode::Glove);
  s.mode_button_presses = presses++;
  s.is_e_stop = 0;
  s.is_laptop_connected = 0;
  s.is_glove_connected = 1;
  s.fault = static_cast<uint8_t>(Fault::None);

  uint8_t tmp[sizeof s + 2], out[sizeof s + 8];
  size_t n = frame(reinterpret_cast<const uint8_t*>(&s), sizeof s, tmp, out);
  Serial.write(out, n);
  delay(500);
}
