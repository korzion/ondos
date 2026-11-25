#include "GloveHandler.h"
#include <cstring>

namespace ondos {

GloveHandler* GloveHandler::instance_ = nullptr;

bool GloveHandler::isZeroMac(const uint8_t mac[6]) {
  for (int i = 0; i < 6; ++i) {
    if (mac[i] != 0) return false;
  }
  return true;
}

bool GloveHandler::isSameMac(const uint8_t a[6], const uint8_t b[6]) {
  return std::memcmp(a, b, 6) == 0;
}

bool GloveHandler::ensurePeer(const uint8_t mac[6]) {
  if (isZeroMac(mac)) return false;
  if (peer_added_ && isSameMac(peer_mac_, mac)) return true;

  if (peer_added_) {
    esp_now_del_peer(peer_mac_);
    peer_added_ = false;
  }

  esp_now_peer_info_t peer{};
  std::memcpy(peer.peer_addr, mac, 6);
  peer.channel = 0;
  peer.encrypt = false;

  if (esp_now_add_peer(&peer) != ESP_OK) {
    return false;
  }

  std::memcpy(peer_mac_, mac, 6);
  peer_added_ = true;
  return true;
}

bool GloveHandler::begin() {
  instance_ = this;

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    initialized_ = false;
    return false;
  }

  esp_now_register_recv_cb(&GloveHandler::onEspNowRecv);

  // Default GameInfo state at boot (IF-01)
  game_info_.msg_type = espnow::MSG_GAME_INFO;
  game_info_.mode = static_cast<uint8_t>(Mode::Glove);
  game_info_.state = static_cast<uint8_t>(State::Setup);
  game_info_.is_vibration_enabled = 1;
  game_info_.vibration_intensity_pct = 100;
  game_info_.calibrate_request = 0;
  game_info_dirty_ = true;

  // Register configured GLOVE_MAC if populated in ondos_pairing.h
  if (!isZeroMac(GLOVE_MAC)) {
    ensurePeer(GLOVE_MAC);
  }

  initialized_ = true;
  return true;
}

#if ESP_ARDUINO_VERSION_MAJOR >= 3
void GloveHandler::onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (!instance_ || !info || !data || len <= 0) return;

  // Ignore packets from other addresses once GLOVE_MAC is configured (IF-01)
  if (!isZeroMac(GLOVE_MAC) && !isSameMac(info->src_addr, GLOVE_MAC)) {
    return;
  }
  if (!instance_->peer_added_) {
    instance_->ensurePeer(info->src_addr);
  }

  int8_t rssi = -50;
  if (info->rx_ctrl) {
    int r = info->rx_ctrl->rssi;
    if (r < -100) r = -100;
    if (r > 0) r = 0;
    rssi = static_cast<int8_t>(r);
  }

  instance_->processGloveData(data, static_cast<size_t>(len), rssi);
}
#else
void GloveHandler::onEspNowRecv(const uint8_t* mac, const uint8_t* data, int len) {
  if (!instance_ || !mac || !data || len <= 0) return;

  if (!isZeroMac(GLOVE_MAC) && !isSameMac(mac, GLOVE_MAC)) {
    return;
  }
  if (!instance_->peer_added_) {
    instance_->ensurePeer(mac);
  }

  instance_->processGloveData(data, static_cast<size_t>(len), -50);
}
#endif

void GloveHandler::processGloveData(const uint8_t* data, size_t len, int8_t rssi_dbm) {
  if (!data || len < 1) return;

  const uint8_t msg_type = data[0];
  if (msg_type == espnow::MSG_GLOVE_DATA && len == sizeof(espnow::GloveData)) {
    std::memcpy(&last_glove_data_, data, sizeof(espnow::GloveData));
    last_glove_data_ms_ = millis();
    has_glove_data_ = true;
    rssi_dbm_ = rssi_dbm;
  } else if (msg_type == espnow::MSG_GLOVE_STATUS && len == sizeof(espnow::GloveStatus)) {
    std::memcpy(&last_glove_status_, data, sizeof(espnow::GloveStatus));
    has_glove_status_ = true;
    rssi_dbm_ = rssi_dbm;
  }
}

void GloveHandler::setGameInfo(Mode mode, State state, bool is_vibration_enabled,
                               uint8_t vibration_intensity_pct, uint8_t calibrate_request) {
  uint8_t m = static_cast<uint8_t>(mode);
  uint8_t s = static_cast<uint8_t>(state);
  uint8_t vib = is_vibration_enabled ? 1 : 0;
  uint8_t inten = vibration_intensity_pct > 100 ? 100 : vibration_intensity_pct;

  if (game_info_.mode != m || game_info_.state != s ||
      game_info_.is_vibration_enabled != vib ||
      game_info_.vibration_intensity_pct != inten ||
      game_info_.calibrate_request != calibrate_request) {
    game_info_.mode = m;
    game_info_.state = s;
    game_info_.is_vibration_enabled = vib;
    game_info_.vibration_intensity_pct = inten;
    game_info_.calibrate_request = calibrate_request;
    game_info_dirty_ = true;
  }
}

bool GloveHandler::sendGameInfo() {
  if (!initialized_ || !peer_added_) return false;
  esp_err_t err = esp_now_send(peer_mac_, reinterpret_cast<const uint8_t*>(&game_info_),
                               sizeof(game_info_));
  if (err == ESP_OK) {
    last_game_info_ms_ = millis();
    game_info_dirty_ = false;
    return true;
  }
  return false;
}

void GloveHandler::update(uint32_t now_ms) {
  if (!initialized_ || !peer_added_) return;
  if (game_info_dirty_ || (now_ms - last_game_info_ms_) >= GAME_INFO_PERIOD_MS) {
    sendGameInfo();
  }
}

bool GloveHandler::sendHaptic(HapticPattern pattern, uint8_t intensity_pct, uint16_t duration_ms) {
  if (!initialized_ || !peer_added_) return false;

  uint8_t scaled = 0;
  if (game_info_.is_vibration_enabled) {
    uint8_t clamped = intensity_pct > 100 ? 100 : intensity_pct;
    scaled = static_cast<uint8_t>((static_cast<uint16_t>(clamped) * game_info_.vibration_intensity_pct) / 100);
  }

  espnow::Haptic pkt{};
  pkt.msg_type = espnow::MSG_HAPTIC;
  pkt.pattern_id = static_cast<uint8_t>(pattern);
  pkt.intensity_pct = scaled;
  pkt.duration_ms = duration_ms > 2000 ? 2000 : duration_ms;

  return esp_now_send(peer_mac_, reinterpret_cast<const uint8_t*>(&pkt), sizeof(pkt)) == ESP_OK;
}

bool GloveHandler::sendWarningHaptic(WarningKind kind, uint8_t intensity_pct) {
  if (kind == WarningKind::NotMoving) {
    return sendHaptic(HapticPattern::NotMoving, intensity_pct, 200);
  }
  return sendHaptic(HapticPattern::AwayFromExit, intensity_pct, 250);
}

bool GloveHandler::isGloveConnected(uint32_t now_ms) const {
  if (!has_glove_data_) return false;
  return (now_ms - last_glove_data_ms_) <= GLOVE_DATA_LOSS_MS;
}

}  // namespace ondos