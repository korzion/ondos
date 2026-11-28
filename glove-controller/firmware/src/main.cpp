#include <Arduino.h>

#include "ondos_packets.h"
#include "ondos_pairing.h"

namespace {
constexpr uint32_t SERIAL_BAUD_RATE = 115200;
}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
}

void loop() {}
