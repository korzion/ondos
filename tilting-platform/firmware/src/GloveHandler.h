#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>

#include "../../../shared/firmware/include/ondos_packets.h"
#include "../../../shared/firmware/include/ondos_pairing.h"

namespace ondos {

class GloveHandler {
 public:
  // Initializes Wi-Fi STA mode and ESP-NOW, and registers GLOVE_MAC as a peer.
  bool begin();

  // Periodic update: sends GameInfo heartbeat at 5 Hz and immediately on change.
  void update(uint32_t now_ms);

  // Parses inbound IF-01 ESP-NOW packets (GloveData, GloveStatus).
  void processGloveData(const uint8_t* data, size_t len, int8_t rssi_dbm);

  // Sends an IF-01 Haptic command to the glove (scales intensity by vibration_intensity_pct).
  bool sendHaptic(HapticPattern pattern, uint8_t intensity_pct, uint16_t duration_ms);

  // Convenience helper to map IF-02 WarningKind to IF-01 HapticPattern.
  bool sendWarningHaptic(WarningKind kind, uint8_t intensity_pct);

  // Updates fields broadcast in GameInfo; marks packet dirty so update() sends immediately.
  void setGameInfo(Mode mode, State state, bool is_vibration_enabled,
                   uint8_t vibration_intensity_pct, uint8_t calibrate_request);

  // True if GloveData arrived within GLOVE_DATA_LOSS_MS (300 ms).
  bool isGloveConnected(uint32_t now_ms) const;

  bool hasGloveData() const { return has_glove_data_; }
  bool hasGloveStatus() const { return has_glove_status_; }
  const espnow::GloveData& getGloveData() const { return last_glove_data_; }
  const espnow::GloveStatus& getGloveStatus() const { return last_glove_status_; }
  int8_t getRssiDbm() const { return rssi_dbm_; }

 private:
  static bool isZeroMac(const uint8_t mac[6]);
  static bool isSameMac(const uint8_t a[6], const uint8_t b[6]);
  bool ensurePeer(const uint8_t mac[6]);
  bool sendGameInfo();

#if ESP_ARDUINO_VERSION_MAJOR >= 3
  static void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len);
#else
  static void onEspNowRecv(const uint8_t* mac, const uint8_t* data, int len);
#endif

  static GloveHandler* instance_;

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
  int8_t rssi_dbm_ = -50;

  static constexpr uint32_t GAME_INFO_PERIOD_MS = 200;  // 5 Hz (IF-01)
};

}  // namespace ondos