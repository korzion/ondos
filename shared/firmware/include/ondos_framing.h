// IF-02 serial framing for the ESP32: COBS + CRC-16/CCITT-FALSE (owner: A).
// frame = COBS(payload + crc16(payload) little endian) + 0x00
// Same algorithm as shared/protocol/framing.py; shared/tests checks both against each other.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace ondos {

inline uint16_t crc16_ccitt_false(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int b = 0; b < 8; ++b) crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
  }
  return crc;
}

// Encodes len bytes; out must hold len + len / 254 + 2 bytes. Returns the encoded size (no delimiter).
inline size_t cobs_encode(const uint8_t* in, size_t len, uint8_t* out) {
  size_t code_pos = 0, o = 1;
  uint8_t code = 1;
  for (size_t i = 0; i < len; ++i) {
    if (in[i] == 0) {
      out[code_pos] = code; code_pos = o++; code = 1;
    } else {
      out[o++] = in[i];
      if (++code == 0xFF) { out[code_pos] = code; code_pos = o++; code = 1; }
    }
  }
  out[code_pos] = code;
  return o;
}

// Decodes len bytes (no delimiter). Returns the decoded size, or 0 on bad data.
inline size_t cobs_decode(const uint8_t* in, size_t len, uint8_t* out) {
  size_t i = 0, o = 0;
  while (i < len) {
    uint8_t code = in[i];
    if (code == 0 || i + code > len + (code > 1 ? 0 : 1)) return 0;
    for (uint8_t k = 1; k < code; ++k) out[o++] = in[i + k];
    i += code;
    if (code < 0xFF && i < len) out[o++] = 0;
  }
  return o;
}

// Builds a full frame (with the trailing 0x00) from a payload; out must hold len + len / 254 + 5 bytes.
inline size_t frame(const uint8_t* payload, size_t len, uint8_t* tmp, uint8_t* out) {
  for (size_t i = 0; i < len; ++i) tmp[i] = payload[i];
  uint16_t crc = crc16_ccitt_false(payload, len);
  tmp[len] = static_cast<uint8_t>(crc & 0xFF);
  tmp[len + 1] = static_cast<uint8_t>(crc >> 8);
  size_t n = cobs_encode(tmp, len + 2, out);
  out[n] = 0;
  return n + 1;
}

// Decodes raw (bytes between delimiters) into payload; returns the payload size, or 0 on a broken frame.
inline size_t unframe(const uint8_t* raw, size_t len, uint8_t* payload) {
  size_t n = cobs_decode(raw, len, payload);
  if (n < 3) return 0;
  uint16_t crc = static_cast<uint16_t>(payload[n - 2] | (payload[n - 1] << 8));
  if (crc16_ccitt_false(payload, n - 2) != crc) return 0;
  return n - 2;
}

}  // namespace ondos
