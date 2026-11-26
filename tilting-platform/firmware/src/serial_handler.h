#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

class SerialHandler {
 public:
  enum class ReceiveResult : uint8_t {
    NoFrame,
    FrameReady,
    InvalidFrame,
    FrameTooLarge,
    OutputTooSmall,
    UnknownMessageType,
    InvalidPacketSize,
    InvalidPacket,
  };

  explicit SerialHandler(Stream& stream);

  // Sends one payload using the shared IF-02 COBS + CRC framing.
  bool sendFrame(const uint8_t* payload, size_t payloadSize);

  // Consumes available serial bytes and returns at most one complete frame.
  ReceiveResult receiveFrame(uint8_t* payload, size_t payloadCapacity,
                            size_t& payloadSize);

  // Receives a CRC-valid frame and checks that it is a supported IF-02
  // bridge-to-ESP32 packet with the expected packed size.
  ReceiveResult receiveMessage(uint8_t* payload, size_t payloadCapacity,
                               size_t& payloadSize);

  static constexpr size_t MAX_PAYLOAD_SIZE = 48;
  // Payload + two CRC bytes needs at most one additional COBS code byte.
  // Keeping the receive bound exact also caps malformed-frame decode output
  // at MAX_PAYLOAD_SIZE + 2 bytes.
  static constexpr size_t MAX_ENCODED_SIZE = MAX_PAYLOAD_SIZE + 3;

 private:
  Stream& stream_;
  uint8_t encodedBuffer_[MAX_ENCODED_SIZE] = {};
  size_t encodedSize_ = 0;
  bool discardingFrame_ = false;
};
