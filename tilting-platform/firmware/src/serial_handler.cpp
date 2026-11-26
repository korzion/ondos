#include "serial_handler.h"

#include <string.h>

#include <math.h>

#include "../../../shared/firmware/include/ondos_framing.h"
#include "../../../shared/firmware/include/ondos_packets.h"

namespace {
constexpr size_t MAX_RAW_SIZE = SerialHandler::MAX_PAYLOAD_SIZE + 2;
constexpr size_t MAX_FRAME_SIZE = SerialHandler::MAX_PAYLOAD_SIZE +
                                  SerialHandler::MAX_PAYLOAD_SIZE / 254 + 5;
}  // namespace

SerialHandler::SerialHandler(Stream& stream) : stream_(stream) {}

bool SerialHandler::sendFrame(const uint8_t* payload, size_t payloadSize) {
  if (payload == nullptr || payloadSize == 0 || payloadSize > MAX_PAYLOAD_SIZE) {
    return false;
  }

  uint8_t crcPayload[MAX_RAW_SIZE];
  uint8_t frameBytes[MAX_FRAME_SIZE];
  const size_t frameSize = ondos::frame(payload, payloadSize, crcPayload, frameBytes);
  return stream_.write(frameBytes, frameSize) == frameSize;
}

SerialHandler::ReceiveResult SerialHandler::receiveFrame(uint8_t* payload,
                                                          size_t payloadCapacity,
                                                          size_t& payloadSize) {
  payloadSize = 0;

  while (stream_.available() > 0) {
    const int value = stream_.read();
    if (value < 0) {
      break;
    }

    const uint8_t byte = static_cast<uint8_t>(value);
    if (byte == 0) {
      if (discardingFrame_) {
        discardingFrame_ = false;
        encodedSize_ = 0;
        return ReceiveResult::FrameTooLarge;
      }
      if (encodedSize_ == 0) {
        continue;
      }

      uint8_t decoded[MAX_RAW_SIZE];
      const size_t decodedSize = ondos::unframe(encodedBuffer_, encodedSize_, decoded);
      encodedSize_ = 0;
      if (decodedSize == 0) {
        return ReceiveResult::InvalidFrame;
      }
      if (payload == nullptr || decodedSize > payloadCapacity) {
        return ReceiveResult::OutputTooSmall;
      }

      memcpy(payload, decoded, decodedSize);
      payloadSize = decodedSize;
      return ReceiveResult::FrameReady;
    }

    if (discardingFrame_) {
      continue;
    }
    if (encodedSize_ == sizeof(encodedBuffer_)) {
      encodedSize_ = 0;
      discardingFrame_ = true;
      continue;
    }

    encodedBuffer_[encodedSize_++] = byte;
  }

  return ReceiveResult::NoFrame;
}

SerialHandler::ReceiveResult SerialHandler::receiveMessage(uint8_t* payload,
                                                            size_t payloadCapacity,
                                                            size_t& payloadSize) {
  const ReceiveResult result = receiveFrame(payload, payloadCapacity, payloadSize);
  if (result != ReceiveResult::FrameReady) {
    return result;
  }

  if (payloadSize == 0) {
    return ReceiveResult::InvalidPacketSize;
  }

  size_t expectedSize = 0;
  switch (payload[0]) {
    case ondos::serial::MSG_HOST_STATE:
      expectedSize = sizeof(ondos::serial::HostState);
      break;
    case ondos::serial::MSG_TARGET_TILT:
      expectedSize = sizeof(ondos::serial::TargetTilt);
      break;
    case ondos::serial::MSG_WARNING:
      expectedSize = sizeof(ondos::serial::Warning);
      break;
    case ondos::serial::MSG_SETTINGS:
      expectedSize = sizeof(ondos::serial::Settings);
      break;
    case ondos::serial::MSG_COMMAND:
      expectedSize = sizeof(ondos::serial::Command);
      break;
#if defined(ONDOS_ENABLE_SERIAL_TEST_MESSAGES)
    case ondos::serial::MSG_INJECT_GLOVE_DATA:
      expectedSize = sizeof(ondos::serial::InjectGloveData);
      break;
#endif
    default:
      return ReceiveResult::UnknownMessageType;
  }

  if (payloadSize != expectedSize) {
    return ReceiveResult::InvalidPacketSize;
  }

  switch (payload[0]) {
    case ondos::serial::MSG_HOST_STATE: {
      ondos::serial::HostState packet;
      memcpy(&packet, payload, sizeof(packet));
      if (packet.state > static_cast<uint8_t>(ondos::State::NoLaptop) ||
          packet.mode > static_cast<uint8_t>(ondos::Mode::Simple)) {
        return ReceiveResult::InvalidPacket;
      }
      break;
    }
    case ondos::serial::MSG_TARGET_TILT: {
      ondos::serial::TargetTilt packet;
      memcpy(&packet, payload, sizeof(packet));
      if (!isfinite(packet.target_tilt_x_deg) ||
          !isfinite(packet.target_tilt_y_deg)) {
        return ReceiveResult::InvalidPacket;
      }
      break;
    }
    case ondos::serial::MSG_WARNING: {
      ondos::serial::Warning packet;
      memcpy(&packet, payload, sizeof(packet));
      if (packet.kind > static_cast<uint8_t>(ondos::WarningKind::AwayFromExit) ||
          packet.intensity_pct > 100) {
        return ReceiveResult::InvalidPacket;
      }
      break;
    }
    case ondos::serial::MSG_SETTINGS: {
      ondos::serial::Settings packet;
      memcpy(&packet, payload, sizeof(packet));
      if (!isfinite(packet.max_tilt_deg) ||
          !isfinite(packet.max_tilt_speed_deg_s) ||
          !isfinite(packet.glove_gain) ||
          !isfinite(packet.glove_deadzone_deg) ||
          !isfinite(packet.filter_strength) ||
          packet.max_tilt_deg < 0 || packet.max_tilt_speed_deg_s < 0 ||
          packet.glove_gain < 0 || packet.glove_deadzone_deg < 0 ||
          packet.is_vibration_enabled > 1 ||
          packet.vibration_intensity_pct > 100) {
        return ReceiveResult::InvalidPacket;
      }
      break;
    }
    case ondos::serial::MSG_COMMAND: {
      ondos::serial::Command packet;
      memcpy(&packet, payload, sizeof(packet));
      if (packet.cmd > static_cast<uint8_t>(ondos::SerialCommand::CalibrateGlove)) {
        return ReceiveResult::InvalidPacket;
      }
      break;
    }
#if defined(ONDOS_ENABLE_SERIAL_TEST_MESSAGES)
    case ondos::serial::MSG_INJECT_GLOVE_DATA: {
      ondos::serial::InjectGloveData packet;
      memcpy(&packet, payload, sizeof(packet));
      if (packet.is_calibrated > 1) {
        return ReceiveResult::InvalidPacket;
      }
      const float values[] = {packet.hand_tilt_x_deg, packet.hand_tilt_y_deg,
                              packet.ax_m_s2, packet.ay_m_s2, packet.az_m_s2,
                              packet.gx_deg_s, packet.gy_deg_s, packet.gz_deg_s};
      for (float value : values) {
        if (!isfinite(value)) {
          return ReceiveResult::InvalidPacket;
        }
      }
      break;
    }
#endif
    default:
      return ReceiveResult::UnknownMessageType;
  }

  return ReceiveResult::FrameReady;
}
