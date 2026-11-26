#include <Arduino.h>
#include <string.h>

#include "../../../shared/firmware/include/ondos_packets.h"
#include "serial_handler.h"

SerialHandler serialHandler(Serial);
ondos::serial::PlatformState platformState{};
ondos::serial::HostState hostState{};
ondos::serial::TargetTilt targetTilt{};
ondos::serial::Warning warning{};
ondos::serial::Settings settings{};
ondos::serial::Command command{};
bool hasHostState = false;
bool hasTargetTilt = false;
bool hasWarning = false;
bool hasSettings = false;
bool commandPending = false;
uint32_t lastHostStateMs = 0;
uint32_t lastPlatformStateMs = 0;

void handleIncomingPacket(const uint8_t* payload) {
  switch (payload[0]) {
    case ondos::serial::MSG_HOST_STATE:
      memcpy(&hostState, payload, sizeof(hostState));
      hasHostState = true;
      lastHostStateMs = millis();
      platformState.mode = hostState.mode;
      break;
    case ondos::serial::MSG_TARGET_TILT:
      memcpy(&targetTilt, payload, sizeof(targetTilt));
      hasTargetTilt = true;
      break;
    case ondos::serial::MSG_WARNING:
      memcpy(&warning, payload, sizeof(warning));
      hasWarning = true;
      break;
    case ondos::serial::MSG_SETTINGS:
      memcpy(&settings, payload, sizeof(settings));
      hasSettings = true;
      break;
    case ondos::serial::MSG_COMMAND:
      memcpy(&command, payload, sizeof(command));
      commandPending = true;
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(921600);
  platformState.source = static_cast<uint8_t>(ondos::PlatformSource::None);
  platformState.mode = static_cast<uint8_t>(ondos::Mode::Glove);
  platformState.fault = static_cast<uint8_t>(ondos::Fault::Imu);
}

void loop() {
  uint8_t payload[SerialHandler::MAX_PAYLOAD_SIZE];
  size_t payloadSize = 0;
  for (;;) {
    const SerialHandler::ReceiveResult result =
        serialHandler.receiveMessage(payload, sizeof(payload), payloadSize);
    if (result == SerialHandler::ReceiveResult::NoFrame) {
      break;
    }
    if (result == SerialHandler::ReceiveResult::FrameReady) {
      handleIncomingPacket(payload);
    }
  }

  const uint32_t now = millis();
  const bool laptopConnected = hasHostState &&
      (now - lastHostStateMs < ondos::HOST_STATE_TIMEOUT_MS);
  platformState.is_laptop_connected = laptopConnected ? 1 : 0;
  if (now - lastPlatformStateMs >= 20) {
    lastPlatformStateMs += 20;
    serialHandler.sendFrame(reinterpret_cast<const uint8_t*>(&platformState),
                            sizeof(platformState));
  }
}
