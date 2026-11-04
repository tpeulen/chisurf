// C++ port of cmc_light/instrument.py. Keep the two in lock-step: the
// conformance test (tests/hardware/test_conformance.py) compares them.
#include "instrument.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

using std::string;
using std::vector;

namespace {

const char* const WORDS[] = {
    "SYSTem", "ERRor", "NEXT", "VERSion", "CHANnels", "INFormation", "MODel", "WAVelength",
    "COLor", "SOURce", "AM", "STATe", "POWer", "LIMit", "LOW", "HIGH", "NOMinal", "DUTY",
    "LEVel", "IMMediate", "AMPLitude", "PWM", "PERiod", "MINimum", "SEQuence", "CLEar", "STEP",
    "APPend", "COUNt", "LIST", "ALEX", "CYCLes", "SYNC", "WIDTh", "STARt", "ABORt", "TIMing",
    "COMMunicate", "WLAN", "SSID", "PASSword", "APPLy", "ADDRess", "MODE",
    "SENSe", "RAW", "PRESent", "AGE", "GAIN", "I2C", "SCAN", "PINS", "EXCLusive"};

// short or long spelling (already upper case) -> short form, or "" if unknown
string lookup(const string& tok) {
  if (tok.empty()) return "";
  for (const char* w : WORDS) {
    string shrt, lng;
    for (const char* c = w; *c; c++) {
      if (!(*c >= 'a' && *c <= 'z')) shrt += *c;
      lng += (*c >= 'a' && *c <= 'z') ? char(*c - 32) : *c;
    }
    if (tok == shrt || tok == lng) return shrt;
  }
  return "";
}

bool is_space(char c) {  // Python str.strip() whitespace (ASCII part)
  return c == ' ' || (c >= '\t' && c <= '\r') || (c >= 0x1c && c <= 0x1f);
}

string strip(const string& s) {
  size_t a = 0, b = s.size();
  while (a < b && is_space(s[a])) a++;
  while (b > a && is_space(s[b - 1])) b--;
  return s.substr(a, b - a);
}

vector<string> split(const string& s, char sep) {
  vector<string> out;
  size_t start = 0;
  for (;;) {
    size_t p = s.find(sep, start);
    if (p == string::npos) {
      out.push_back(s.substr(start));
      return out;
    }
    out.push_back(s.substr(start, p - start));
    start = p + 1;
  }
}

string upper(const string& s) {
  string r = s;
  for (char& c : r)
    if (c >= 'a' && c <= 'z') c -= 32;
  return r;
}

bool is_digit(char c) { return c >= '0' && c <= '9'; }

// Python float(): [sign] (digits[.digits][exp] | .digits[exp] | inf | infinity | nan),
// with single underscores allowed between digits.
bool py_float(const string& s0, double& v) {
  string s = strip(s0);
  size_t i = 0, n = s.size();
  string clean;
  if (i < n && (s[i] == '+' || s[i] == '-')) clean += s[i++];
  string word = upper(s.substr(i));
  if (word == "INF" || word == "INFINITY") {
    v = clean == "-" ? -HUGE_VAL : HUGE_VAL;
    return true;
  }
  if (word == "NAN") {
    v = NAN;
    return true;
  }
  auto digits = [&](bool& any) {
    any = false;
    while (i < n && is_digit(s[i])) {
      clean += s[i++];
      any = true;
      if (i + 1 < n && s[i] == '_' && is_digit(s[i + 1])) i++;
    }
  };
  bool int_part, frac_part = false;
  digits(int_part);
  if (i < n && s[i] == '.') {
    clean += s[i++];
    digits(frac_part);
  }
  if (!int_part && !frac_part) return false;
  if (i < n && (s[i] == 'e' || s[i] == 'E')) {
    clean += s[i++];
    if (i < n && (s[i] == '+' || s[i] == '-')) clean += s[i++];
    bool exp_digits;
    digits(exp_digits);
    if (!exp_digits) return false;
  }
  if (i != n) return false;
  v = strtod(clean.c_str(), nullptr);
  return true;
}

string fmt4(double v) {  // Python "%.4f"
  if (std::isnan(v)) return "nan";
  if (std::isinf(v)) return v < 0 ? "-inf" : "inf";
  char buf[48];
  snprintf(buf, sizeof buf, "%.4f", v);
  return buf;
}

string fmt3(double v) {  // Python "%.3f"
  char buf[40];
  snprintf(buf, sizeof buf, "%.3f", v);
  return buf;
}

string fmt_int(int64_t v) {
  char buf[24];
  snprintf(buf, sizeof buf, "%lld", (long long)v);
  return buf;
}

const char* error_message(int code) {
  switch (code) {
    case -100: return "Command error";
    case -109: return "Missing parameter";
    case -113: return "Undefined header";
    case -221: return "Settings conflict";
    case -222: return "Data out of range";
    case -224: return "Illegal parameter value";
    case -241: return "Hardware missing";
    case -350: return "Queue overflow";
  }
  return "Error";
}

struct Command {
  const char* key;
  Instrument::Handler fn;
};

}  // namespace

Instrument::Instrument(Hardware* hw, const Channel* channels, int nch, const string& serial,
                       bool active_high, int sync_gpio, const char* model)
    : hw_(hw), channels_(channels), nch_(nch), serial_(serial), model_(model),
      active_high_(active_high), sync_gpio_(sync_gpio), err_code_(0) {
  for (int k = 0; k < nch; k++) gpios_[k] = channels[k].gpio;
  prog_ = new seqcore::Program();
  reset();
  apply();  // cannot fail in CW mode
}

// ------------------------------------------------------------------ state
void Instrument::reset() {
  for (int k = 0; k < nch_; k++) {
    enabled_[k] = false;
    powers_[k] = 1.0;
    duty_[k] = 0.0;
  }
  exclusive_ = false;  // one laser at a time is a measurement mode, not the normal one
  source_ = "CW";
  pwm_period_ = 1000;
  min_pulse_ = 20;
  power_mode_ = "PWM";
  steps_ = seqcore::alex_steps(nch_, 1000, 0);
  cycles_ = 0;
  sync_us_ = 0;
  running_ = false;
  edges_ = 0;
  period_ = 0;
  cycle_factor_ = 1;
  play_factor_ = 1;
}

bool Instrument::apply() {
  bool seq = source_ == "SEQ";
  vector<seqcore::Step> cw;
  if (!seq) cw.push_back(seqcore::Step{pwm_period_, (int64_t(1) << nch_) - 1});
  hw_->stop();
  if (seq && !running_ && steps_.empty()) {
    // idle sequence mode with no steps yet: valid, outputs off (same as the reference)
    uint32_t lasers = 0, sync = sync_gpio_ >= 0 ? uint32_t(1) << sync_gpio_ : 0;
    for (int k = 0; k < nch_; k++) lasers |= uint32_t(1) << gpios_[k];
    if (active_high_)
      hw_->static_levels(0, lasers | sync);
    else
      hw_->static_levels(lasers, sync);
    for (int k = 0; k < nch_; k++) duty_[k] = 0.0;
    edges_ = 0;
    period_ = 0;
    cycle_factor_ = 1;
    return true;
  }
  string err;
  if (!seqcore::compile_program(seq ? steps_ : cw, gpios_, nch_, enabled_, powers_, pwm_period_,
                                min_pulse_, active_high_, sync_gpio_, seq ? sync_us_ : 0,
                                *prog_, err, seq && power_mode_ == "CYCL")) {
    // not in the reference: make sure nothing stays lit after a failed compile
    uint32_t lasers = 0, sync = sync_gpio_ >= 0 ? uint32_t(1) << sync_gpio_ : 0;
    for (int k = 0; k < nch_; k++) lasers |= uint32_t(1) << gpios_[k];
    if (active_high_)
      hw_->static_levels(0, lasers | sync);
    else
      hw_->static_levels(lasers, sync);
    apply_failed_ = true;
    return fail(-221, err);
  }
  for (int k = 0; k < nch_; k++) duty_[k] = prog_->duty[k];
  int64_t m = prog_->cycle_factor;
  edges_ = prog_->n;
  period_ = prog_->period / m;
  cycle_factor_ = m;
  if (seq && !running_) {
    hw_->static_levels(prog_->idle_set, prog_->idle_clr);
  } else if (edges_) {
    // SEQ:CYCLes counts sequence periods: play at least that many
    play_factor_ = m;
    hw_->play(*prog_, seq ? (uint32_t)((cycles_ + m - 1) / m) : 0);
  } else {
    hw_->static_levels(prog_->start_set, prog_->start_clr);
  }
  return true;
}

bool Instrument::chan(const vector<int64_t>& n, int& k) {
  int64_t c = n.empty() ? 1 : n[0];
  if (c < 1 || c > nch_) return fail(-222, "channel " + fmt_int(c));
  k = int(c - 1);
  return true;
}

bool Instrument::fail(int code, const string& detail) {
  err_code_ = code;
  err_detail_ = detail;
  return false;
}

bool Instrument::arg_float(const vector<string>& a, size_t i, double lo, double hi, double& v) {
  if (a.size() <= i) return fail(-109);
  if (!py_float(a[i], v)) return fail(-224, a[i]);
  if (v < lo || v > hi) return fail(-222, a[i]);
  return true;
}

bool Instrument::arg_int(const vector<string>& a, size_t i, int64_t lo, int64_t hi, int64_t& v) {
  if (a.size() <= i) return fail(-109);
  double d;
  if (!py_float(a[i], d) || std::isnan(d) || std::isinf(d)) return fail(-224, a[i]);
  d = std::trunc(d);
  if (d < (double)lo || d > (double)hi) return fail(-222, a[i]);
  v = (int64_t)d;
  return true;
}

bool Instrument::arg_bool(const vector<string>& a, bool& v) {
  string s = a.empty() ? "" : upper(a[0]);
  if (s == "ON" || s == "1") {
    v = true;
    return true;
  }
  if (s == "OFF" || s == "0") {
    v = false;
    return true;
  }
  return fail(a.empty() ? -109 : -224);
}

bool Instrument::arg_string(const string& s0, size_t maxlen, string& v) {
  if (s0.empty()) return fail(-109);
  string s = s0;
  char q = s[0];
  if (q == '"' || q == '\'') {
    if (s.size() < 2 || s[s.size() - 1] != q) return fail(-224, s);
    string inner = s.substr(1, s.size() - 2), out;
    for (size_t i = 0; i < inner.size(); i++) {
      out += inner[i];
      if (inner[i] == q && i + 1 < inner.size() && inner[i + 1] == q) i++;
    }
    s = out;
  }
  if (s.size() > maxlen) return fail(-222, "longer than " + fmt_int((int64_t)maxlen) + " bytes");
  v = s;
  return true;
}

// ------------------------------------------------------------------ I/O
bool Instrument::handle(const string& line, string& reply) {
  vector<string> replies;
  for (const string& part : split(strip(line), ';')) {
    string cmd = strip(part);
    if (cmd.empty()) continue;
    bool has = false;
    string r;
    err_code_ = 0;
    err_detail_.clear();
    // == Instrument._snapshot/_restore: a setting the player cannot play is rolled back
    Snapshot snap;
    save(snap);
    apply_failed_ = false;
    if (!one(cmd, has, r)) {
      int code = err_code_;
      string detail = err_detail_;
      if (apply_failed_) restore(snap);
      push(code, detail);
      has = false;
    }
    if (has) replies.push_back(r);
  }
  if (replies.empty()) return false;
  reply.clear();
  for (size_t i = 0; i < replies.size(); i++) {
    if (i) reply += ';';
    reply += replies[i];
  }
  return true;
}

void Instrument::save(Snapshot& s) const {
  for (int k = 0; k < nch_; k++) {
    s.enabled[k] = enabled_[k];
    s.powers[k] = powers_[k];
  }
  s.source = source_;
  s.pwm_period = pwm_period_;
  s.min_pulse = min_pulse_;
  s.cycles = cycles_;
  s.sync_us = sync_us_;
  s.running = running_;
  s.power_mode = power_mode_;
}

void Instrument::restore(const Snapshot& s) {
  for (int k = 0; k < nch_; k++) {
    enabled_[k] = s.enabled[k];
    powers_[k] = s.powers[k];
  }
  source_ = s.source;
  pwm_period_ = s.pwm_period;
  min_pulse_ = s.min_pulse;
  cycles_ = s.cycles;
  sync_us_ = s.sync_us;
  running_ = s.running;
  power_mode_ = s.power_mode;
  if (!apply()) {  // last resort: everything off
    running_ = false;
    for (int k = 0; k < nch_; k++) enabled_[k] = false;
    apply();
  }
}

void Instrument::push(int code, const string& detail) {
  if (errors_.size() >= 10)
    errors_.back() = std::make_pair(-350, string());
  else
    errors_.push_back(std::make_pair(code, detail));
}

bool Instrument::parse_header(const string& head, string& key, vector<int64_t>& nums) {
  if (!head.empty() && head[0] == '*') {
    key = head;
    return true;
  }
  vector<string> keys;
  for (const string& tok : split(head, ':')) {
    size_t k = tok.size();
    while (k > 0 && is_digit(tok[k - 1])) k--;
    string shrt = lookup(tok.substr(0, k));
    if (shrt.empty()) return fail(-113, head);
    if (!keys.empty()) {
      string last = keys.back();
      while (!last.empty() && last.back() == '#') last.pop_back();
      bool optional =
          (last == "POW" && (shrt == "LEV" || shrt == "IMM" || shrt == "AMPL")) ||
          (last == "ERR" && shrt == "NEXT");
      if (optional) continue;
    }
    if ((shrt == "SYST" || shrt == "SOUR" || shrt == "SENS") && keys.empty()) {
      int64_t num = 1;
      if (k < tok.size()) {
        num = 0;
        for (size_t i = k; i < tok.size(); i++) {
          num = num * 10 + (tok[i] - '0');
          if (num > 1000000000000LL) num = 1000000000000LL;  // absurd suffix, never valid
        }
      }
      nums.push_back(num);
      shrt += "#";
    } else if (k < tok.size()) {
      return fail(-113, head);
    }
    keys.push_back(shrt);
  }
  key.clear();
  for (size_t i = 0; i < keys.size(); i++) {
    if (i) key += ':';
    key += keys[i];
  }
  return true;
}

bool Instrument::one(const string& cmd, bool& has, string& r) {
  static const Command COMMANDS[] = {
      {"*IDN", &Instrument::h_idn}, {"*RST", &Instrument::h_rst}, {"*CLS", &Instrument::h_cls},
      {"*OPC", &Instrument::h_opc}, {"*TST", &Instrument::h_tst},
      {"SYST#:ERR", &Instrument::h_err}, {"SYST#:VERS", &Instrument::h_version},
      {"SYST#:CHAN", &Instrument::h_nchan}, {"SYST#:INF:MOD", &Instrument::h_info_model},
      {"SYST#:INF:WAV", &Instrument::h_info_wavelength},
      {"SYST#:INF:COL", &Instrument::h_info_color},
      {"SOUR#:AM:STAT", &Instrument::h_am_state}, {"SOUR#:AM:SOUR", &Instrument::h_am_source},
      {"SOUR#:EXCL", &Instrument::h_exclusive},
      {"SOUR#:POW:LIM:LOW", &Instrument::h_pow_low},
      {"SOUR#:POW:LIM:HIGH", &Instrument::h_pow_high},
      {"SOUR#:POW:NOM", &Instrument::h_pow_high}, {"SOUR#:POW:DUTY", &Instrument::h_pow_duty},
      {"SOUR#:POW", &Instrument::h_power},
      {"SOUR#:PWM:PER", &Instrument::h_pwm_period}, {"SOUR#:PWM:MIN", &Instrument::h_pwm_min},
      {"SOUR#:PWM:MODE", &Instrument::h_pwm_mode},
      {"SEQ:CLE", &Instrument::h_seq_clear}, {"SEQ:STEP:APP", &Instrument::h_seq_append},
      {"SEQ:STEP:COUN", &Instrument::h_seq_nsteps}, {"SEQ:STEP:LIST", &Instrument::h_seq_list},
      {"SEQ:ALEX", &Instrument::h_seq_alex}, {"SEQ:PER", &Instrument::h_seq_period},
      {"SEQ:CYCL", &Instrument::h_seq_cycles}, {"SEQ:SYNC:WIDT", &Instrument::h_seq_sync},
      {"SEQ:STAR", &Instrument::h_seq_start}, {"SEQ:ABOR", &Instrument::h_abort},
      {"ABOR", &Instrument::h_abort}, {"SEQ:STAT", &Instrument::h_seq_state},
      {"SEQ:COUN", &Instrument::h_seq_count}, {"SEQ:TIM", &Instrument::h_seq_timing},
      {"SYST#:COMM:WLAN:SSID", &Instrument::h_wlan_ssid},
      {"SYST#:COMM:WLAN:PASS", &Instrument::h_wlan_pass},
      {"SYST#:COMM:WLAN:APPL", &Instrument::h_wlan_apply},
      {"SYST#:COMM:WLAN:ADDR", &Instrument::h_wlan_addr},
      {"SYST#:COMM:WLAN:MODE", &Instrument::h_wlan_mode},
      {"SYST#:I2C:SCAN", &Instrument::h_i2c_scan}, {"SYST#:I2C:PINS", &Instrument::h_i2c_pins},
      {"SENS#:POW:RAW", &Instrument::h_mon_raw}, {"SENS#:POW:PRES", &Instrument::h_mon_present},
      {"SENS#:POW:MODE", &Instrument::h_mon_mode}, {"SENS#:POW:GAIN", &Instrument::h_mon_gain},
      {"SENS#:POW:AGE", &Instrument::h_mon_age}, {"SENS#:POW", &Instrument::h_mon_power},
  };
  size_t sp = cmd.find(' ');
  string head = sp == string::npos ? cmd : cmd.substr(0, sp);
  rest_ = sp == string::npos ? "" : strip(cmd.substr(sp + 1));
  bool query = !head.empty() && head.back() == '?';
  while (!head.empty() && head.back() == '?') head.pop_back();
  size_t lead = 0;
  while (lead < head.size() && head[lead] == ':') lead++;
  head = upper(head.substr(lead));
  vector<string> args;
  if (!rest_.empty())
    for (const string& x : split(rest_, ',')) args.push_back(strip(x));
  string key;
  vector<int64_t> nums;
  if (!parse_header(head, key, nums)) return false;
  for (const Command& c : COMMANDS)
    if (key == c.key) return (this->*c.fn)(query, args, nums, has, r);
  return fail(-113, head);
}

#define HANDLER(name)                                                                  \
  bool Instrument::name(bool q, const vector<string>& a, const vector<int64_t>& n, bool& has, \
                        string& r)
#define REPLY(x)  \
  do {            \
    r = (x);      \
    has = true;   \
    return true;  \
  } while (0)
#define UNUSED (void)q, (void)a, (void)n, (void)has, (void)r

// ------------------------------------------------------------------ commands
HANDLER(h_idn) {
  UNUSED;
  REPLY(string(CMC_LIGHT_VENDOR) + "," + model_ + "," + serial_ + "," + CMC_LIGHT_VERSION);
}

HANDLER(h_rst) {
  UNUSED;
  reset();
  return apply();
}

HANDLER(h_cls) {
  UNUSED;
  errors_.clear();
  return true;
}

HANDLER(h_opc) { UNUSED; REPLY("1"); }
HANDLER(h_tst) { UNUSED; REPLY("0"); }

HANDLER(h_err) {
  UNUSED;
  if (errors_.empty()) REPLY("0,\"No error\"");
  std::pair<int, string> e = errors_.front();
  errors_.erase(errors_.begin());
  string msg = error_message(e.first);
  if (!e.second.empty()) msg += "; " + e.second;
  REPLY(fmt_int(e.first) + ",\"" + msg + "\"");
}

HANDLER(h_version) { UNUSED; REPLY("1999.0"); }
HANDLER(h_nchan) { UNUSED; REPLY(fmt_int(nch_)); }

HANDLER(h_info_model) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  REPLY(channels_[k].name);
}

HANDLER(h_info_wavelength) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  REPLY(fmt_int(channels_[k].wavelength));
}

HANDLER(h_info_color) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  REPLY(channels_[k].color ? channels_[k].color : "#ffffff");
}

HANDLER(h_am_state) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  if (q) REPLY(enabled_[k] ? "ON" : "OFF");
  bool v;
  if (!arg_bool(a, v)) return false;
  if (v && exclusive_)  // one laser at a time: switching one on switches the others off
    for (int i = 0; i < nch_; i++) enabled_[i] = false;
  enabled_[k] = v;
  return apply();
}

HANDLER(h_exclusive) {  // one laser at a time: for measuring a single laser's power
  UNUSED;
  if (q) REPLY(exclusive_ ? "ON" : "OFF");
  bool v;
  if (!arg_bool(a, v)) return false;
  if (v) {
    if (!check_exclusive(steps_)) return false;
    int first = -1;
    for (int i = 0; i < nch_; i++) {
      if (!enabled_[i]) continue;
      if (first < 0) first = i;
      else enabled_[i] = false;
    }
  }
  exclusive_ = v;
  return apply();
}

HANDLER(h_am_source) {
  UNUSED;
  if (q) REPLY(source_);
  string v = a.empty() ? "" : upper(a[0]);
  if (v == "CW" || v == "CWP") {
    source_ = "CW";
    running_ = false;
  } else if (v == "SEQ" || v == "SEQUENCE") {
    source_ = "SEQ";
  } else {
    return fail(a.empty() ? -109 : -224);
  }
  return apply();
}

HANDLER(h_pow_low) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  REPLY("0.0000");
}

HANDLER(h_pow_high) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  REPLY("1.0000");
}

HANDLER(h_pow_duty) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  REPLY(fmt4(duty_[k]));
}

HANDLER(h_power) {
  UNUSED;
  int k;
  if (!chan(n, k)) return false;
  if (q) REPLY(fmt4(powers_[k]));
  double v;
  if (!arg_float(a, 0, 0.0, 1.0, v)) return false;
  powers_[k] = v;
  return apply();
}

HANDLER(h_pwm_period) {
  UNUSED;
  if (q) REPLY(fmt_int(pwm_period_));
  int64_t v;
  if (!arg_int(a, 0, 20, 1000000, v)) return false;
  pwm_period_ = v;
  return apply();
}

HANDLER(h_pwm_min) {
  UNUSED;
  if (q) REPLY(fmt_int(min_pulse_));
  int64_t v;
  if (!arg_int(a, 0, 1, 100000, v)) return false;
  min_pulse_ = v;
  return apply();
}

HANDLER(h_pwm_mode) {
  UNUSED;
  if (q) REPLY(power_mode_);
  string v = a.empty() ? "" : upper(a[0]);
  if (v == "PWM") {
    power_mode_ = "PWM";
  } else if (v == "CYCL" || v == "CYCLES") {
    power_mode_ = "CYCL";
  } else {
    return fail(a.empty() ? -109 : -224);
  }
  if (source_ == "SEQ") return apply();  // CW always uses PWM
  return true;
}

bool Instrument::halt() {
  if (running_) {
    running_ = false;
    return apply();
  }
  return true;
}

HANDLER(h_seq_clear) {
  UNUSED;
  if (!halt()) return false;
  steps_.clear();
  return true;
}

HANDLER(h_seq_append) {
  UNUSED;
  if (!halt()) return false;
  int64_t dur, mask;
  if (!arg_int(a, 0, 1, 60000000, dur)) return false;
  // mask bit nch_ drives the sync output, if there is one
  int bits = nch_ + (sync_gpio_ >= 0 ? 1 : 0);
  if (!arg_int(a, 1, 0, (int64_t(1) << bits) - 1, mask)) return false;
  std::vector<seqcore::Step> one(1, seqcore::Step{dur, mask});
  if (!check_exclusive(one)) return false;
  if (steps_.size() >= (size_t)seqcore::MAX_STEPS)
    return fail(-221, "too many steps (max " + fmt_int(seqcore::MAX_STEPS) + ")");
  steps_.push_back(seqcore::Step{dur, mask});
  return true;
}

HANDLER(h_seq_nsteps) { UNUSED; REPLY(fmt_int((int64_t)steps_.size())); }

HANDLER(h_seq_list) {
  UNUSED;
  string out;
  for (size_t i = 0; i < steps_.size(); i++) {
    if (i) out += ';';
    out += fmt_int(steps_[i].dur) + "," + fmt_int(steps_[i].mask);
  }
  REPLY(out);
}

HANDLER(h_seq_alex) {
  UNUSED;
  if (!halt()) return false;
  int64_t on, gap = 0;
  if (!arg_int(a, 0, 1, 60000000, on)) return false;
  if (a.size() > 1 && !arg_int(a, 1, 0, 60000000, gap)) return false;
  steps_ = seqcore::alex_steps(nch_, on, gap);
  return true;
}

HANDLER(h_seq_period) { UNUSED; REPLY(fmt_int(seqcore::period_us(steps_))); }

HANDLER(h_seq_cycles) {
  UNUSED;
  if (q) REPLY(fmt_int(cycles_));
  int64_t v;
  if (!arg_int(a, 0, 0, int64_t(1) << 30, v)) return false;
  cycles_ = v;
  return true;
}

HANDLER(h_seq_sync) {
  UNUSED;
  if (q) REPLY(fmt_int(sync_us_));
  if (sync_gpio_ < 0) return fail(-221, "no sync output");
  int64_t v;
  if (!arg_int(a, 0, 0, 60000000, v)) return false;
  sync_us_ = v;
  if (running_) return apply();
  return true;
}

HANDLER(h_seq_start) {
  UNUSED;
  if (steps_.empty()) return fail(-221, "sequence is empty");
  source_ = "SEQ";
  running_ = true;
  return apply();
}

HANDLER(h_abort) {
  UNUSED;
  running_ = false;
  if (source_ == "SEQ") return apply();
  return true;
}

HANDLER(h_seq_state) {
  UNUSED;
  bool hw_running;
  uint32_t done, late;
  if (running_) {
    hw_->status(hw_running, done, late);
    if (!hw_running) {
      running_ = false;  // finished its cycles
      if (!apply()) return false;
    }
  }
  if (q) REPLY(running_ ? "RUN" : "IDLE");
  bool v;
  if (!arg_bool(a, v)) return false;
  bool dummy_has;
  string dummy;
  if (v) return h_seq_start(false, vector<string>(), n, dummy_has, dummy);
  return h_abort(false, vector<string>(), n, dummy_has, dummy);
}

HANDLER(h_seq_count) {
  UNUSED;
  bool running;
  uint32_t done, late;
  hw_->status(running, done, late);
  REPLY(fmt_int((int64_t)done * play_factor_));
}

HANDLER(h_seq_timing) {
  UNUSED;
  bool running;
  uint32_t done, late;
  hw_->status(running, done, late);
  REPLY(fmt_int(late) + "," + fmt_int(edges_) + "," + fmt_int(period_));
}

// WLAN: settings are persistent (the platform stores them), *RST keeps them.
HANDLER(h_wlan_ssid) {
  UNUSED;
  if (q) {
    string out = "\"";
    for (char c : ssid_) {
      out += c;
      if (c == '"') out += '"';
    }
    REPLY(out + "\"");
  }
  string v;
  if (!arg_string(rest_, 32, v)) return false;
  ssid_ = v;
  hw_->wlan_store(ssid_, password_);
  return true;
}

HANDLER(h_wlan_pass) {
  UNUSED;
  if (q) REPLY(password_.empty() ? "\"\"" : "\"***\"");
  string v;
  if (!arg_string(rest_, 63, v)) return false;
  if (!v.empty() && v.size() < 8) return fail(-222, "password needs 8 to 63 characters");
  password_ = v;
  hw_->wlan_store(ssid_, password_);
  return true;
}

HANDLER(h_wlan_apply) {
  UNUSED;
  hw_->wlan_apply();
  return true;
}

HANDLER(h_wlan_addr) { UNUSED; REPLY(hw_->wlan_address()); }
HANDLER(h_wlan_mode) { UNUSED; REPLY(hw_->wlan_mode()); }

// ---- power monitor (light sensor on I2C) ---------------------------------- //
bool Instrument::check_exclusive(const std::vector<seqcore::Step>& steps) {
  if (!exclusive_) return true;
  const int64_t laser_bits = (int64_t(1) << nch_) - 1;
  for (const seqcore::Step& st : steps) {
    int lit = 0;
    for (int i = 0; i < nch_; i++)
      if (st.mask & laser_bits & (int64_t(1) << i)) lit++;
    if (lit > 1) return fail(-221, "only one laser at a time (SOURce:EXCLusive OFF allows more)");
  }
  return true;
}

bool Instrument::monitor_state(MonitorState& m) {
  if (!hw_->monitor(m) || !m.present) return fail(-241, "no light sensor on the I2C bus");
  if (m.simulated) {  // the simulator and the host build read what the lasers are set to
    double sum = 0.0;
    for (int k = 0; k < nch_; k++) sum += duty_[k];
    m.lux = 1000.0 * sum;
    m.raw = (uint32_t)(m.lux * 1.2 + 0.5);
    m.age_ms = 0;
  }
  return true;
}

HANDLER(h_mon_power) {  // SENSe:POWer? -> what the monitor reads, in lux
  UNUSED;
  MonitorState m;
  if (!monitor_state(m)) REPLY("nan");  // the error is queued; a query still answers
  REPLY(fmt3(m.lux));
}

HANDLER(h_mon_raw) {
  UNUSED;
  MonitorState m;
  if (!monitor_state(m)) REPLY("nan");
  REPLY(fmt_int((int64_t)m.raw));
}

HANDLER(h_mon_present) {
  UNUSED;
  MonitorState m;
  REPLY(hw_->monitor(m) && m.present ? "1" : "0");
}

HANDLER(h_mon_age) {
  UNUSED;
  MonitorState m;
  if (!monitor_state(m)) REPLY("nan");
  REPLY(fmt_int((int64_t)m.age_ms));
}

HANDLER(h_mon_mode) {
  UNUSED;
  MonitorState m;
  if (!monitor_state(m)) {
    if (q) REPLY("HIGH");
    return false;
  }
  if (q) REPLY(m.mode);
  string want = a.empty() ? "" : upper(a[0]);
  if (want != "HIGH" && want != "HIGH2" && want != "LOW") return fail(a.empty() ? -109 : -224);
  if (!hw_->monitor_set(want, m.gain)) return fail(-241, "no light sensor on the I2C bus");
  return true;
}

HANDLER(h_mon_gain) {  // BH1750 MTreg: integration time and sensitivity
  UNUSED;
  MonitorState m;
  if (!monitor_state(m)) {
    if (q) REPLY("nan");
    return false;
  }
  if (q) REPLY(fmt_int(m.gain));
  int64_t v;
  if (!arg_int(a, 0, 31, 254, v)) return false;
  if (!hw_->monitor_set(m.mode, (int)v)) return fail(-241, "no light sensor on the I2C bus");
  return true;
}

HANDLER(h_i2c_scan) {
  UNUSED;
  MonitorState m;
  hw_->monitor(m);
  REPLY(m.addresses);
}

HANDLER(h_i2c_pins) {
  UNUSED;
  MonitorState m;
  hw_->monitor(m);
  if (q) REPLY(m.pins);
  int64_t sda, scl;
  if (!arg_int(a, 0, 0, 16, sda)) return false;
  if (!arg_int(a, 1, 0, 16, scl)) return false;
  if (!hw_->i2c_configure((int)sda, (int)scl)) return fail(-241, "no sensor answered on those pins");
  return true;
}
