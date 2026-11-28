#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>

#include "../../../shared/firmware/include/ondos_packets.h"
#include "../../../shared/firmware/include/ondos_pairing.h"

namespace ondos {

class GloveHandler {
 public:
  // Initializes Wi-Fi STA mode, ESP-NOW, and registers GLOVE_MAC as peer.
  // Returns false if GLOVE_MAC is all zeros or ESP-NOW setup fails (IF-01).
  bool begin();

  // Periodic update: sends GameInfo heartbeat at 5 Hz and immediately on change.
  void update(uint32_t now_ms);

  // Parses and validates inbound IF-01 ESP-NOW packets (GloveData, GloveStatus).
  void processGloveData(const uint8_t* data, size_t len, int8_t rssi_dbm);

  // Sends an IF-01 Haptic command to the glove (scales intensity by vibration_intensity_pct).
  bool sendHaptic(HapticPattern pattern, uint8_t intensity_pct, uint16_t duration_ms);

  // Convenience helper to map IF-02 WarningKind to IF-01 HapticPattern.
  bool sendWarningHaptic(WarningKind kind, uint8_t intensity_pct);

  // Updates fields broadcast in GameInfo; marks packet dirty so update() sends immediately.
  void setGameInfo(Mode mode, State state, bool is_vibration_enabled,
                   uint8_t vibration_intensity_pct, uint8_t calibrate_request);

  // True if valid GloveData arrived within GLOVE_DATA_LOSS_MS (300 ms).
  bool isGloveConnected(uint32_t now_ms) const;

  // Thread-safe copy-out getters.
  bool hasGloveData() const;
  bool hasGloveStatus() const;
  espnow::GloveData getGloveData() const;
  espnow::GloveStatus getGloveStatus() const;
  int8_t getRssiDbm() const;

 private:
  static bool isZeroMac(const uint8_t mac[6]);
  static bool isSameMac(const uint8_t a[6], const uint8_t b[6]);
  bool sendGameInfo(uint32_t now_ms);
  static void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len);

  static GloveHandler* instance_;
  mutable portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;

  bool initialized_ = false;
  bool peer_added_ = false;
  uint8_t peer_mac_[6] = {0, 0, 0, 0, 0, 0};

  espnow::GloveData last_glove_data_{};
  espnow::GloveStatus last_glove_status_{};
  espnow::GameInfo game_info_{};

  bool has_glove_data_ = false;
  bool has_glove_status_ = false;
  bool game_info_dirty_ = true;

  uint32_t last_glove_data_ms_ = 0;
  uint32_t last_game_info_ms_ = 0;
  int8_t rssi_dbm_ = DEFAULT_RSSI_DBM;

  static constexpr uint32_t GAME_INFO_PERIOD_MS = 200;       // 5 Hz (IF-01)
  static constexpr uint16_t NOT_MOVING_HAPTIC_MS = 200;
  static constexpr uint16_t AWAY_FROM_EXIT_HAPTIC_MS = 250;
  static constexpr uint16_t MAX_HAPTIC_DURATION_MS = 2000;
  static constexpr uint8_t MAX_PERCENT = 100;
  static constexpr int8_t DEFAULT_RSSI_DBM = -50;
  static constexpr int8_t MIN_RSSI_DBM = -100;
  static constexpr int8_t MAX_RSSI_DBM = 0;
};

}  // namespace ondos