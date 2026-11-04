// SCPI instrument: C++ port of cmc_light/instrument.py.
//
// Portable (ESP8266 and host). Replies and SYSTem:ERRor? texts must be
// byte-identical to the Python reference for the same session.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "seqcore.h"

#define CMC_LIGHT_VENDOR "CMC"
#define CMC_LIGHT_VERSION "2.0"

// The internal power monitor: a light sensor on the instrument's I2C bus.
struct MonitorState {
  bool present = false;
  bool simulated = false;  // no real sensor: the instrument fills in a value from the duties
  float lux = 0.0f;       // what the sensor reads, averaged over its integration time
  uint32_t raw = 0;       // sensor counts
  uint32_t age_ms = 0;    // since the reading was taken
  bool saturated = false;
  std::string mode = "HIGH";  // HIGH, HIGH2 (finer) or LOW (faster)
  int gain = 69;              // BH1750 MTreg 31..254: integration time and sensitivity
  std::string pins = "";      // "sda,scl"
  std::string addresses = ""; // what an I2C scan found, e.g. "0x23"
};

// What the instrument needs from the platform.
class Hardware {
 public:
  virtual ~Hardware() {}
  virtual void static_levels(uint32_t set_mask, uint32_t clr_mask) = 0;  // stops playback
  virtual void play(const seqcore::Program& prog, uint32_t cycles) = 0;
  virtual void stop() = 0;
  virtual void status(bool& running, uint32_t& cycles_done, uint32_t& late_max_us) = 0;
  // WLAN (persistent settings live in the instrument, the platform applies them)
  virtual void wlan_store(const std::string& ssid, const std::string& password) = 0;
  virtual void wlan_apply() = 0;
  virtual std::string wlan_address() = 0;
  virtual std::string wlan_mode() = 0;
  // power monitor on I2C; monitor() returns false when there is no sensor
  virtual bool monitor(MonitorState& out) = 0;
  virtual bool monitor_set(const std::string& mode, int gain) = 0;
  virtual bool i2c_configure(int sda, int scl) = 0;
};

struct Channel {
  const char* name;
  int gpio;
  int wavelength;
  const char* color;
};

class Instrument {
 public:
  Instrument(Hardware* hw, const Channel* channels, int nch, const std::string& serial,
             bool active_high, int sync_gpio, const char* model);

  // Process one line (commands may be joined with ';'). Returns false if
  // there is no reply, else stores it in reply.
  bool handle(const std::string& line, std::string& reply);

  // restore persistent WLAN settings at boot
  void set_wlan(const std::string& ssid, const std::string& password) {
    ssid_ = ssid;
    password_ = password;
  }
  const std::string& ssid() const { return ssid_; }
  const std::string& password() const { return password_; }

  const seqcore::Program& program() const { return *prog_; }

  typedef bool (Instrument::*Handler)(bool q, const std::vector<std::string>& a,
                                      const std::vector<int64_t>& n, bool& has, std::string& r);

 private:
  Hardware* hw_;
  const Channel* channels_;
  int nch_;
  int gpios_[seqcore::MAX_CHANNELS];
  std::string serial_;
  const char* model_;
  bool active_high_;
  int sync_gpio_;
  std::vector<std::pair<int, std::string>> errors_;
  std::string rest_;
  std::string ssid_, password_;

  // state
  bool enabled_[seqcore::MAX_CHANNELS];
  // One laser at a time: for measuring a single laser's power (the monitor diode reads
  // the total), not a limit of the hardware. Off in normal operation.
  bool exclusive_ = false;
  double powers_[seqcore::MAX_CHANNELS];
  double duty_[seqcore::MAX_CHANNELS];
  std::string source_;
  int64_t pwm_period_, min_pulse_;
  std::string power_mode_;  // "PWM" or "CYCL" (cycle dithering, sequence mode only)
  std::vector<seqcore::Step> steps_;
  int64_t cycles_, sync_us_;
  bool running_;
  bool apply_failed_ = false;
  struct Snapshot {
    bool enabled[seqcore::MAX_CHANNELS];
    double powers[seqcore::MAX_CHANNELS];
    std::string source;
    int64_t pwm_period, min_pulse, cycles, sync_us;
    bool running;
    std::string power_mode;
  };
  void save(Snapshot& s) const;
  void restore(const Snapshot& s);
  int64_t edges_, period_;  // period_: sequence (base) period of the current program
  int64_t cycle_factor_ = 1;  // sequence periods per program period
  int64_t play_factor_ = 1;   // cycle_factor_ of the program last handed to the player
  seqcore::Program* prog_;

  // pending error of the command being processed
  int err_code_;
  std::string err_detail_;

  bool fail(int code, const std::string& detail = "");
  bool arg_int(const std::vector<std::string>& a, size_t i, int64_t lo, int64_t hi, int64_t& v);
  bool arg_float(const std::vector<std::string>& a, size_t i, double lo, double hi, double& v);
  bool arg_bool(const std::vector<std::string>& a, bool& v);
  bool arg_string(const std::string& s, size_t maxlen, std::string& v);
  bool monitor_state(MonitorState& m);
  bool check_exclusive(const std::vector<seqcore::Step>& steps);
  bool chan(const std::vector<int64_t>& n, int& k);
  bool parse_header(const std::string& head, std::string& key, std::vector<int64_t>& nums);
  void push(int code, const std::string& detail);
  void reset();
  bool apply();
  bool halt();
  bool one(const std::string& cmd, bool& has, std::string& r);

#define H(name)                                                                           \
  bool name(bool q, const std::vector<std::string>& a, const std::vector<int64_t>& n, bool& has, \
            std::string& r)
  H(h_idn); H(h_rst); H(h_cls); H(h_opc); H(h_tst); H(h_err); H(h_version); H(h_nchan);
  H(h_info_model); H(h_info_wavelength); H(h_info_color); H(h_am_state); H(h_am_source);
  H(h_pow_low); H(h_pow_high); H(h_pow_duty); H(h_power); H(h_pwm_period); H(h_pwm_min); H(h_pwm_mode);
  H(h_seq_clear); H(h_seq_append); H(h_seq_nsteps); H(h_seq_list); H(h_seq_alex);
  H(h_seq_period); H(h_seq_cycles); H(h_seq_sync); H(h_seq_start); H(h_abort);
  H(h_seq_state); H(h_seq_count); H(h_seq_timing);
  H(h_wlan_ssid); H(h_wlan_pass); H(h_wlan_apply); H(h_wlan_addr); H(h_wlan_mode);
  H(h_mon_power); H(h_mon_raw); H(h_mon_present); H(h_mon_age); H(h_mon_mode); H(h_mon_gain);
  H(h_i2c_scan); H(h_i2c_pins); H(h_exclusive);
#undef H

};
