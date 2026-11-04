// Host build of the firmware's SCPI instrument on simulated hardware, for
// comparing it with the Python reference (tests/test_firmware_port.py).
//
//   c++ -std=c++17 -O1 -I../cmc_light scpi_host.cpp ../cmc_light/instrument.cpp \
//       ../cmc_light/seqcore.cpp -o scpi_host
//
// Reads SCPI lines on stdin. For every line prints "R <reply>" or "-" (no
// reply). A line "#PROGRAM" dumps the compiled edge program instead:
// "P period n start_set start_clr idle_set idle_clr cycle_factor t:set:clr ...".
#include <chrono>
#include <cstdio>
#include <iostream>
#include <string>

#include "instrument.h"

void seqcore_idle_hook() {}

class SimHardware : public Hardware {
 public:
  bool playing = false;
  uint32_t cycles = 0;
  int64_t period = 0;
  std::chrono::steady_clock::time_point t0;

  void static_levels(uint32_t, uint32_t) override { playing = false; }
  void play(const seqcore::Program& prog, uint32_t c) override {
    playing = true;
    cycles = c;
    period = prog.period;
    t0 = std::chrono::steady_clock::now();
  }
  void stop() override { playing = false; }
  void status(bool& running, uint32_t& done, uint32_t& late) override {
    uint64_t d = 0;
    if (playing && period > 0) {
      auto us = std::chrono::duration_cast<std::chrono::microseconds>(
                    std::chrono::steady_clock::now() - t0)
                    .count();
      d = us / period;
    }
    running = playing && !(cycles && d >= cycles);
    if (cycles && d > cycles) d = cycles;
    done = (uint32_t)d;
    late = 0;
  }
  void wlan_store(const std::string&, const std::string&) override {}
  void wlan_apply() override {}
  std::string wlan_address() override { return "0.0.0.0"; }
  std::string wlan_mode() override { return "AP"; }

  // no I2C here: the instrument fills in the reading (see Instrument::monitor_state)
  bool monitor(MonitorState& out) override {
    out.present = true;
    out.simulated = true;
    out.mode = mon_mode;
    out.gain = mon_gain;
    out.pins = i2c_pins;
    out.addresses = "0x23";
    return true;
  }
  bool monitor_set(const std::string& mode, int gain) override {
    mon_mode = mode;
    mon_gain = gain;
    return true;
  }
  bool i2c_configure(int sda, int scl) override {
    char buf[16];
    snprintf(buf, sizeof buf, "%d,%d", sda, scl);
    i2c_pins = buf;
    return true;
  }

  std::string mon_mode = "HIGH", i2c_pins = "13,15";
  int mon_gain = 69;
};

static const Channel CHANNELS[] = {
    {"blue", 5, 0, "#3a6bff"}, {"green", 4, 0, "#2fd05a"}, {"red", 0, 0, "#ff3b30"}};

int main() {
  SimHardware hw;
  Instrument inst(&hw, CHANNELS, 3, "SIM", true, 14, "LIGHT-3-SIM");
  std::string line, reply;
  while (std::getline(std::cin, line)) {
    if (line == "#PROGRAM") {
      const seqcore::Program& p = inst.program();
      printf("P %lld %u %u %u %u %u %lld", (long long)p.period, p.n, p.start_set, p.start_clr,
             p.idle_set, p.idle_clr, (long long)p.cycle_factor);
      for (uint32_t i = 0; i < p.n; i++)
        printf(" %llu:%u:%u", (unsigned long long)p.times[i], p.sets[i], p.clrs[i]);
      printf("\n");
    } else if (inst.handle(line, reply)) {
      printf("R %s\n", reply.c_str());
    } else {
      printf("-\n");
    }
    fflush(stdout);
  }
  return 0;
}
