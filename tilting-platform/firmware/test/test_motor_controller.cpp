#include <cassert>
#include <cmath>
#include <iostream>
#include <limits>
#include <map>

#include "../src/MotorController.h"

using ondos::MotorController;
using ondos::ServoCalibration;

namespace {

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
  MockPwmBus bus;
  MotorController mc;

  // Rejects invalid pins (same pin or negative pin)
  assert(!mc.begin(4, 4, &recordPulse, &bus));
  assert(!mc.begin(-1, 5, &recordPulse, &bus));
  assert(!mc.isInitialized());

  // Initializes to level (1500 us on both servos)
  assert(mc.begin(4, 5, &recordPulse, &bus));
  assert(mc.isInitialized());
  assert(!mc.isStopped());
  assert(near(mc.getTiltXDeg(), 0.0f));
  assert(near(mc.getTiltYDeg(), 0.0f));
  assert(bus.pulse_by_pin[4] == 1500);
  assert(bus.pulse_by_pin[5] == 1500);
}

void testOutputMappingBoundsAndNonFinite() {
  MockPwmBus bus;
  MotorController mc;
  assert(mc.begin(4, 5, &recordPulse, &bus));

  // Direct output mapping without double-limiting angles already bounded by PlatformController
  assert(mc.setMotorOutput(10.0f, -10.0f));
  assert(near(mc.getTiltXDeg(), 10.0f));
  assert(near(mc.getTiltYDeg(), -10.0f));
  assert(mc.getPulseXUs() == 1611);  // 1500 + round(10 * 1000/90)
  assert(mc.getPulseYUs() == 1389);  // 1500 - round(10 * 1000/90)

  // Hardware pulse-width bounds [min_pulse_us, max_pulse_us] protect servos on extreme angles
  assert(mc.setMotorOutput(500.0f, -500.0f));
  assert(mc.getPulseXUs() == 2500);
  assert(mc.getPulseYUs() == 500);

  // Non-finite inputs are rejected without altering outputs
  assert(mc.setMotorOutput(6.0f, -6.0f));
  const int writes_before_bad = bus.write_count;
  assert(!mc.setMotorOutput(std::numeric_limits<float>::quiet_NaN(), 0.0f));
  assert(!mc.setMotorOutput(0.0f, std::numeric_limits<float>::infinity()));
  assert(bus.write_count == writes_before_bad);
  assert(near(mc.getTiltXDeg(), 6.0f));
  assert(near(mc.getTiltYDeg(), -6.0f));
}

void testCalibrationAndLevel() {
  MockPwmBus bus;
  MotorController mc;
  assert(mc.begin(4, 5, &recordPulse, &bus));
  assert(mc.setMotorOutput(6.0f, -6.0f));

  // Inverted Y-axis calibration maps board frame tilt_y_deg to reversed servo direction
  ServoCalibration cal_x{};
  ServoCalibration cal_y{};
  cal_y.axis_sign = -1.0f;
  cal_y.neutral_pulse_us = 1520;
  assert(mc.setCalibration(cal_x, cal_y));
  // At y = -6 deg with axis_sign = -1 -> +6 deg -> 1520 + round(66.67) = 1587 us
  assert(bus.pulse_by_pin[5] == 1587);

  // Invalid calibration is rejected
  ServoCalibration bad_cal{};
  bad_cal.axis_sign = 2.0f;
  assert(!mc.setCalibration(cal_x, bad_cal));

  // Leveling returns both axes to 0 deg (calibrated neutral pulses)
  assert(mc.levelPlatform());
  assert(near(mc.getTiltXDeg(), 0.0f));
  assert(near(mc.getTiltYDeg(), 0.0f));
  assert(bus.pulse_by_pin[4] == 1500);
  assert(bus.pulse_by_pin[5] == 1520);
}

void testStopAndEnable() {
  MockPwmBus bus;
  MotorController mc;
  ServoCalibration cal_x{};
  ServoCalibration cal_y{};
  cal_y.axis_sign = -1.0f;
  cal_y.neutral_pulse_us = 1520;
  assert(mc.begin(4, 5, &recordPulse, &bus));
  assert(mc.setCalibration(cal_x, cal_y));

  // stopMotors() cuts PWM (0 us) and locks outputs until enableMotors()
  mc.stopMotors();
  assert(mc.isStopped());
  assert(bus.pulse_by_pin[4] == 0);
  assert(bus.pulse_by_pin[5] == 0);
  assert(!mc.setMotorOutput(5.0f, 5.0f));
  assert(!mc.levelPlatform());
  assert(bus.pulse_by_pin[4] == 0);

  // enableMotors() unlocks at level
  assert(mc.enableMotors());
  assert(!mc.isStopped());
  assert(bus.pulse_by_pin[4] == 1500);
  assert(bus.pulse_by_pin[5] == 1520);
  assert(mc.setMotorOutput(2.0f, -2.0f));
  assert(near(mc.getTiltXDeg(), 2.0f));
  assert(near(mc.getTiltYDeg(), -2.0f));
}

}  // namespace

int main() {
  testInvalidPinsAndInit();
  testOutputMappingBoundsAndNonFinite();
  testCalibrationAndLevel();
  testStopAndEnable();
  std::cout << "MotorController unit tests: PASS\n";
  return 0;
}
