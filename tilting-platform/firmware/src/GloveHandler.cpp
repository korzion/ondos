#include "GloveHandler.h"
#include <cmath>
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

bool GloveHandler::begin() {
  initialized_ = false;
  peer_added_ = false;

  // IF-01 requires a fixed GLOVE_MAC; fail until configured in ondos_pairing.h
  if (isZeroMac(GLOVE_MAC)) {
    return false;
  }

  instance_ = this;

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    return false;
  }

  esp_now_peer_info_t peer{};
  std::memcpy(peer.peer_addr, GLOVE_MAC, 6);
  peer.channel = 0;
  peer.encrypt = false;

  if (esp_now_add_peer(&peer) != ESP_OK) {
    return false;
  }

  std::memcpy(peer_mac_, GLOVE_MAC, 6);
  peer_added_ = true;

  esp_now_register_recv_cb(&GloveHandler::onEspNowRecv);

  // Default GameInfo state at boot (IF-01)
  game_info_.msg_type = espnow::MSG_GAME_INFO;
  game_info_.mode = static_cast<uint8_t>(Mode::Glove);
  game_info_.state = static_cast<uint8_t>(State::Setup);
  game_info_.is_vibration_enabled = 1;
  game_info_.vibration_intensity_pct = MAX_PERCENT;
  game_info_.calibrate_request = 0;
  game_info_dirty_ = true;

  initialized_ = true;
  return true;
}

void GloveHandler::onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (!instance_ || !info || !data || len <= 0) return;

  // IF-01: ignore packets from any address other than configured GLOVE_MAC
  if (isZeroMac(GLOVE_MAC) || !isSameMac(info->src_addr, GLOVE_MAC)) {
    return;
  }

  int8_t rssi = DEFAULT_RSSI_DBM;
  if (info->rx_ctrl) {
    int r = info->rx_ctrl->rssi;
    if (r < MIN_RSSI_DBM) r = MIN_RSSI_DBM;
    if (r > MAX_RSSI_DBM) r = MAX_RSSI_DBM;
    rssi = static_cast<int8_t>(r);
  }

  instance_->processGloveData(data, static_cast<size_t>(len), rssi);
}

void GloveHandler::processGloveData(const uint8_t* data, size_t len, int8_t rssi_dbm) {
  if (!data || len < 1) return;

  const uint8_t msg_type = data[0];
  if (msg_type == espnow::MSG_GLOVE_DATA && len == sizeof(espnow::GloveData)) {
    espnow::GloveData pkt{};
    std::memcpy(&pkt, data, sizeof(pkt));

    // Reject non-finite tilt values or invalid calibration flag
    if (!std::isfinite(pkt.hand_tilt_x_deg) || !std::isfinite(pkt.hand_tilt_y_deg) ||
        pkt.is_calibrated > 1) {
      return;
    }

    const uint32_t rx_ms = millis();
    portENTER_CRITICAL(&mux_);
    last_glove_data_ = pkt;
    last_glove_data_ms_ = rx_ms;
    has_glove_data_ = true;
    rssi_dbm_ = rssi_dbm;
    portEXIT_CRITICAL(&mux_);
  } else if (msg_type == espnow::MSG_GLOVE_STATUS && len == sizeof(espnow::GloveStatus)) {
    espnow::GloveStatus pkt{};
    std::memcpy(&pkt, data, sizeof(pkt));

    portENTER_CRITICAL(&mux_);
    last_glove_status_ = pkt;
    has_glove_status_ = true;
    rssi_dbm_ = rssi_dbm;
    portEXIT_CRITICAL(&mux_);
  }
}

void GloveHandler::setGameInfo(Mode mode, State state, bool is_vibration_enabled,
                               uint8_t vibration_intensity_pct, uint8_t calibrate_request) {
  uint8_t m = static_cast<uint8_t>(mode);
  uint8_t s = static_cast<uint8_t>(state);
  uint8_t vib = is_vibration_enabled ? 1 : 0;
  uint8_t inten = vibration_intensity_pct > MAX_PERCENT ? MAX_PERCENT : vibration_intensity_pct;

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

bool GloveHandler::sendGameInfo(uint32_t now_ms) {
  if (!initialized_ || !peer_added_) return false;
  esp_err_t err = esp_now_send(peer_mac_, reinterpret_cast<const uint8_t*>(&game_info_),
                               sizeof(game_info_));
  if (err == ESP_OK) {
    last_game_info_ms_ = now_ms;
    game_info_dirty_ = false;
    return true;
  }
  return false;
}

void GloveHandler::update(uint32_t now_ms) {
  if (!initialized_ || !peer_added_) return;
  if (game_info_dirty_ || (now_ms - last_game_info_ms_) >= GAME_INFO_PERIOD_MS) {
    sendGameInfo(now_ms);
  }
}

bool GloveHandler::sendHaptic(HapticPattern pattern, uint8_t intensity_pct, uint16_t duration_ms) {
  if (!initialized_ || !peer_added_) return false;

  uint8_t scaled = 0;
  if (game_info_.is_vibration_enabled) {
    uint8_t clamped = intensity_pct > MAX_PERCENT ? MAX_PERCENT : intensity_pct;
    scaled = static_cast<uint8_t>(
        (static_cast<uint16_t>(clamped) * game_info_.vibration_intensity_pct) / MAX_PERCENT);
  }

  espnow::Haptic pkt{};
  pkt.msg_type = espnow::MSG_HAPTIC;
  pkt.pattern_id = static_cast<uint8_t>(pattern);
  pkt.intensity_pct = scaled;
  pkt.duration_ms = duration_ms > MAX_HAPTIC_DURATION_MS ? MAX_HAPTIC_DURATION_MS : duration_ms;

  return esp_now_send(peer_mac_, reinterpret_cast<const uint8_t*>(&pkt), sizeof(pkt)) == ESP_OK;
}

bool GloveHandler::sendWarningHaptic(WarningKind kind, uint8_t intensity_pct) {
  if (kind == WarningKind::NotMoving) {
    return sendHaptic(HapticPattern::NotMoving, intensity_pct, NOT_MOVING_HAPTIC_MS);
  }
  return sendHaptic(HapticPattern::AwayFromExit, intensity_pct, AWAY_FROM_EXIT_HAPTIC_MS);
}

bool GloveHandler::isGloveConnected(uint32_t now_ms) const {
  bool received = false;
  uint32_t last_ms = 0;

  portENTER_CRITICAL(&mux_);
  received = has_glove_data_;
  last_ms = last_glove_data_ms_;
  portEXIT_CRITICAL(&mux_);

  if (!received) return false;
  // Signed diff avoids false disconnect if a packet arrives just after caller read millis()
  const int32_t age_ms = static_cast<int32_t>(now_ms - last_ms);
  return age_ms <= static_cast<int32_t>(GLOVE_DATA_LOSS_MS);
}

bool GloveHandler::hasGloveData() const {
  portENTER_CRITICAL(&mux_);
  const bool val = has_glove_data_;
  portEXIT_CRITICAL(&mux_);
  return val;
}

bool GloveHandler::hasGloveStatus() const {
  portENTER_CRITICAL(&mux_);
  const bool val = has_glove_status_;
  portEXIT_CRITICAL(&mux_);
  return val;
}

espnow::GloveData GloveHandler::getGloveData() const {
  portENTER_CRITICAL(&mux_);
  const espnow::GloveData copy = last_glove_data_;
  portEXIT_CRITICAL(&mux_);
  return copy;
}

espnow::GloveStatus GloveHandler::getGloveStatus() const {
  portENTER_CRITICAL(&mux_);
  const espnow::GloveStatus copy = last_glove_status_;
  portEXIT_CRITICAL(&mux_);
  return copy;
}

int8_t GloveHandler::getRssiDbm() const {
  portENTER_CRITICAL(&mux_);
  const int8_t val = rssi_dbm_;
  portEXIT_CRITICAL(&mux_);
  return val;
}

}  // namespace ondos