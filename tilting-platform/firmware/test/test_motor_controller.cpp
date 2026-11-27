// Host unit tests for MotorController (runs standalone with or without -DNDEBUG):
//   clang++ -std=gnu++17 -Wall -Wextra -Werror -DNDEBUG \
//     tilting-platform/firmware/src/MotorController.cpp \
//     tilting-platform/firmware/test/test_motor_controller.cpp -o /tmp/test_mc && /tmp/test_mc
#include <cmath>
#include <iostream>
#include <limits>
#include <map>

#include "../src/MotorController.h"

using ondos::MotorController;
using ondos::ServoCalibration;

namespace {

int g_passed = 0;
int g_failed = 0;

void check(const char* name, bool ok) {
  if (ok) {
    g_passed += 1;
    return;
  }
  g_failed += 1;
  std::cerr << "  FAIL  " << name << "\n";
}

struct MockPwmBus {
  std::map<int, uint32_t> pulse_by_pin;
  int write_count = 0;
};

void recordPulse(int pin, uint32_t pulse_us, void* ctx) {
  auto* bus = static_cast<MockPwmBus*>(ctx);
  bus->pulse_by_pin[pin] = pulse_us;
  bus->write_count += 1;
}

bool near(float a, float b, float tol = 1e-4f) {
  return std::fabs(a - b) <= tol;
}

void testInvalidPinsAndInit() {
  check("ESP32-S3 LEDC resolution is 14-bit", MotorController::SERVO_PWM_RESOLUTION_BITS == 14);
  MockPwmBus bus;
  MotorController mc;

  check("rejects duplicate servo pins", !mc.begin(4, 4, &recordPulse, &bus));
  check("rejects negative servo pin", !mc.begin(-1, 5, &recordPulse, &bus));
  check("stays uninitialized on invalid pins", !mc.isInitialized());

  check("initializes with valid pins", mc.begin(4, 5, &recordPulse, &bus));
  check("reports initialized and enabled", mc.isInitialized() && !mc.isStopped());
  check("starts level at 0 deg", near(mc.getTiltXDeg(), 0.0f) && near(mc.getTiltYDeg(), 0.0f));
  check("outputs neutral 1500 us pulses", bus.pulse_by_pin[4] == 1500 && bus.pulse_by_pin[5] == 1500);
}

void testOutputMappingBoundsAndNonFinite() {
  MockPwmBus bus;
  MotorController mc;
  check("begin succeeds for output test", mc.begin(4, 5, &recordPulse, &bus));

  check("applies +/-10 deg output", mc.setMotorOutput(10.0f, -10.0f));
  check("stores +/-10 deg tilt", near(mc.getTiltXDeg(), 10.0f) && near(mc.getTiltYDeg(), -10.0f));
  check("maps +10/-10 deg to 1611/1389 us", mc.getPulseXUs() == 1611 && mc.getPulseYUs() == 1389);

  // Backup mechanical limit (+/-20 deg) clamps extreme angles and stored getTilt*Deg()
  check("accepts extreme angle input and clamps mechanically", mc.setMotorOutput(500.0f, -500.0f));
  check("clamps getTilt*Deg to +/-20 deg", near(mc.getTiltXDeg(), 20.0f) && near(mc.getTiltYDeg(), -20.0f));
  check("maps clamped +/-20 deg to 1722/1278 us", mc.getPulseXUs() == 1722 && mc.getPulseYUs() == 1278);

  // Non-finite inputs are rejected without altering outputs
  check("sets baseline valid output before NaN test", mc.setMotorOutput(6.0f, -6.0f));
  const int writes_before_bad = bus.write_count;
  check("rejects NaN tilt_x", !mc.setMotorOutput(std::numeric_limits<float>::quiet_NaN(), 0.0f));
  check("rejects Inf tilt_y", !mc.setMotorOutput(0.0f, std::numeric_limits<float>::infinity()));
  check("preserves last output on non-finite inputs",
        bus.write_count == writes_before_bad && near(mc.getTiltXDeg(), 6.0f) && near(mc.getTiltYDeg(), -6.0f));
}

void testCalibrationPulseBoundsAndLevel() {
  MockPwmBus bus;
  MotorController mc;
  check("begin succeeds for calibration test", mc.begin(4, 5, &recordPulse, &bus));
  check("sets tilt before calibration update", mc.setMotorOutput(6.0f, -6.0f));

  ServoCalibration cal_x{};
  ServoCalibration cal_y{};
  cal_y.is_inverted = true;
  cal_y.neutral_pulse_us = 1520;
  check("applies inverted Y calibration", mc.setCalibration(cal_x, cal_y));
  check("inverted Y maps -6 deg to 1587 us", bus.pulse_by_pin[5] == 1587);

  // Tighter pulse range [1400, 1600] us clamps angle to +/-9.0 deg
  cal_x.min_pulse_us = 1400;
  cal_x.max_pulse_us = 1600;
  check("applies tighter pulse bounds on X", mc.setCalibration(cal_x, cal_y));
  check("accepts 15 deg input clipped by pulse bounds", mc.setMotorOutput(15.0f, 0.0f));
  check("clips getTiltXDeg to +9 deg and 1600 us", near(mc.getTiltXDeg(), 9.0f) && mc.getPulseXUs() == 1600);

  ServoCalibration bad_cal{};
  bad_cal.max_mechanical_tilt_deg = 0.0f;
  check("rejects non-positive max_mechanical_tilt_deg", !mc.setCalibration(cal_x, bad_cal));

  check("levelPlatform returns to 0 deg", mc.levelPlatform());
  check("level zeroes tilts", near(mc.getTiltXDeg(), 0.0f) && near(mc.getTiltYDeg(), 0.0f));
  check("level outputs calibrated neutrals", bus.pulse_by_pin[4] == 1500 && bus.pulse_by_pin[5] == 1520);
}

void testStopAndEnable() {
  MockPwmBus bus;
  MotorController mc;
  ServoCalibration cal_x{};
  ServoCalibration cal_y{};
  cal_y.is_inverted = true;
  cal_y.neutral_pulse_us = 1520;
  check("begin succeeds for stop/enable test", mc.begin(4, 5, &recordPulse, &bus));
  check("calibration succeeds for stop/enable test", mc.setCalibration(cal_x, cal_y));

  mc.stopMotors();
  check("stopMotors marks stopped and cuts PWM to 0 us",
        mc.isStopped() && bus.pulse_by_pin[4] == 0 && bus.pulse_by_pin[5] == 0);
  check("rejects commands while stopped", !mc.setMotorOutput(5.0f, 5.0f) && !mc.levelPlatform());
  check("keeps 0 us while stopped", bus.pulse_by_pin[4] == 0);

  check("enableMotors unlocks PWM", mc.enableMotors() && !mc.isStopped());
  check("enableMotors restores calibrated neutral", bus.pulse_by_pin[4] == 1500 && bus.pulse_by_pin[5] == 1520);
  check("accepts commands after enableMotors", mc.setMotorOutput(2.0f, -2.0f));
  check("tracks post-enable tilts", near(mc.getTiltXDeg(), 2.0f) && near(mc.getTiltYDeg(), -2.0f));
}

}  // namespace

int main() {
  testInvalidPinsAndInit();
  testOutputMappingBoundsAndNonFinite();
  testCalibrationPulseBoundsAndLevel();
  testStopAndEnable();

  const int total = g_passed + g_failed;
  if (g_failed > 0) {
    std::cerr << "MotorController unit tests: FAIL (" << g_failed << "/" << total << " failed)\n";
    return 1;
  }
  std::cout << "MotorController unit tests: PASS (" << g_passed << "/" << total << " checks)\n";
  return 0;
}
