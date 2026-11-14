// ESP-NOW pairing (IF-01 Notes): fixed MAC addresses; the platform ignores packets from any other address.
// Owner: B. Fill in the real addresses of the two boards (print them with WiFi.macAddress()).
#pragma once
#include <stdint.h>

namespace ondos {

// TODO(B): replace with the glove ESP32-C3 MAC address.
constexpr uint8_t GLOVE_MAC[6] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
// TODO(A/B): replace with the platform ESP32-S3 MAC address.
constexpr uint8_t PLATFORM_MAC[6] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

}  // namespace ondos
