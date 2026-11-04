// C++ port of cmc_light/seqcore.py (see there for the model).
//
// The Python version builds interval lists; here every channel is a lazy
// generator of its merged on-intervals and the edge table is a k-way merge of
// those streams. This keeps RAM bounded even when a sequence would need far
// more than MAX_EDGES edges (the error text reports the exact count, like the
// reference).
#include "seqcore.h"

#include <cmath>
#include <cstdio>
#include <cstring>

void seqcore_idle_hook();  // defined by the platform (feeds the watchdog on the ESP8266)

namespace seqcore {

std::vector<Step> alex_steps(int n_channels, int64_t on_us, int64_t gap_us) {
  std::vector<Step> steps;
  for (int ch = 0; ch < n_channels; ch++) {
    steps.push_back(Step{on_us, int64_t(1) << ch});
    if (gap_us) steps.push_back(Step{gap_us, 0});
  }
  return steps;
}

int64_t period_us(const std::vector<Step>& steps) {
  int64_t p = 0;
  for (const Step& s : steps) p += s.dur;
  return p;
}

namespace {

int64_t pwm_width(double p, int64_t sub, int64_t min_pulse_us) {
  int64_t w = (int64_t)(p * (double)sub + 0.5);
  if (w <= 0) return 0;
  if (w < min_pulse_us) return (2 * p * (double)sub >= (double)min_pulse_us) ? min_pulse_us : 0;
  int64_t off = sub - w;
  if (off < min_pulse_us) return (2 * off < min_pulse_us) ? sub : sub - min_pulse_us;
  return w;
}

double clamp_power(double p) {
  p = (p > 0.0) ? p : 0.0;  // Python: min(1.0, max(0.0, p)), nan -> 0
  return (p < 1.0) ? p : 1.0;
}

// Python round() of a small non-negative double: half to even
int64_t py_round(double x) {
  double f = std::floor(x);
  double d = x - f;  // exact
  int64_t r = (int64_t)f;
  if (d > 0.5 || (d == 0.5 && (r & 1))) r++;
  return r;
}

bool dithered(bool cycle_dither, bool en, double p) {  // == seqcore.dithered
  p = clamp_power(p);
  return cycle_dither && en && p > 0.0 && p < 1.0;
}

struct Ev {
  int64_t t;
  uint32_t on, off;
};

// Lazily produces the on/off edges of one channel, in time order. The sync output
// is one more generator: ch = nch, always at full power, plus a pulse of pulse_w
// at the start of every sequence period (== seqcore.sync_intervals).
struct ChanGen {
  const std::vector<Step>* steps = nullptr;
  int ch = 0;
  bool en = false;
  double p = 0;    // power of the current cycle (dithered: 1 or 0)
  double p_set = 0;  // clamped power setting
  bool dith = false;
  int64_t ncyc = 1, cyc = 0, count = 0;  // cycle dithering: count lit cycles of ncyc
  int64_t pwm = 1, minp = 0, period = 0;
  int64_t pulse_w = 0, pulse_cyc = -1;  // sync pulse width, last cycle that got it
  uint32_t bit = 0;
  // raw interval iteration
  size_t si = 0;
  int64_t t = 0, k = 0, nsub = 0, dur = 0;
  bool in_step = false;
  // merging
  bool have_pend = false;
  int64_t ps = 0, pe = 0;
  // edge emission
  int stage = 0;
  int64_t cs = 0, ce = 0;
  // results
  int64_t lit = 0;
  bool start_on = false;

  // PWM sub-periods of the current step: start a, lengths q or q+1 (Bresenham
  // on the remainder, identical to t + k*dur//nsub), on-time w0 / w1 per length.
  int64_t a = 0, q = 0, w0 = 0, w1 = 0, r = 0, acc = 0;

  void cycle_power() {  // == seqcore.cycle_lit
    if (dith)
      p = ((cyc + 1) * count / ncyc > cyc * count / ncyc) ? 1.0 : 0.0;
    else
      p = p_set;
  }

  bool raw(int64_t& s, int64_t& e) {
    for (;;) {
      if (si >= steps->size()) {  // next sequence period of the program
        if (cyc + 1 >= ncyc) return false;
        cyc++;
        si = 0;
        cycle_power();
        continue;
      }
      if (pulse_w > 0 && si == 0 && !in_step && pulse_cyc != cyc) {
        pulse_cyc = cyc;  // starts with step 0: merged() joins them
        s = t;
        e = t + pulse_w;
        return true;
      }
      if (!in_step) {
        dur = (*steps)[si].dur;
        int64_t mask = (*steps)[si].mask;
        if (((mask >> ch) & 1) && en && p > 0) {
          if (p >= 1.0) {
            s = t;
            e = t + dur;
            lit += dur;
            t += dur;
            si++;
            return true;
          }
          nsub = (dur + pwm / 2) / pwm;
          if (nsub < 1) nsub = 1;
          q = dur / nsub;
          r = dur % nsub;
          w0 = pwm_width(p, q, minp);
          w1 = r ? pwm_width(p, q + 1, minp) : 0;
          if (w0 == 0 && w1 == 0) {  // dark step
            t += dur;
            si++;
            continue;
          }
          if (w0 == q && (r == 0 || w1 == q + 1)) {  // every sub-period solid
            s = t;
            e = t + dur;
            lit += dur;
            t += dur;
            si++;
            return true;
          }
          k = 0;
          a = t;
          acc = 0;
          in_step = true;
        } else {
          t += dur;
          si++;
          continue;
        }
      }
      while (k < nsub) {
        acc += r;
        int64_t w = w0, len = q;
        if (acc >= nsub) {
          acc -= nsub;
          w = w1;
          len = q + 1;
        }
        int64_t start = a;
        a += len;
        k++;
        if (w > 0) {
          lit += w;
          s = start;
          e = start + w;
          return true;
        }
      }
      in_step = false;
      t += dur;
      si++;
    }
  }

  bool merged(int64_t& s, int64_t& e) {
    int64_t a, b;
    if (!have_pend) {
      if (!raw(ps, pe)) return false;
      have_pend = true;
    }
    while (raw(a, b)) {
      if (a <= pe) {
        if (b > pe) pe = b;
      } else {
        s = ps;
        e = pe;
        ps = a;
        pe = b;
        return true;
      }
    }
    s = ps;
    e = pe;
    have_pend = false;
    return true;
  }

  bool next(Ev& ev) {
    for (;;) {
      if (stage == 1) {
        stage = 2;
        ev = Ev{cs, bit, 0};
        return true;
      }
      if (stage == 2) {
        stage = 0;
        ev = Ev{ce, 0, bit};
        return true;
      }
      if (!merged(cs, ce)) return false;
      if (cs == 0) start_on = true;
      if (ce - cs >= period) continue;  // solid for the whole period: level only
      stage = 1;
    }
  }
};

}  // namespace

namespace {

bool compile_once(const std::vector<Step>& steps, const int* gpios, int nch,
                  const bool* enabled, const double* powers, int64_t pwm_period_us,
                  int64_t min_pulse_us, bool active_high, int sync_gpio, int64_t sync_us,
                  bool cycle_dither, int64_t ncyc, Program& out, std::string& err) {
  static char buf[128];
  int64_t base = period_us(steps);
  int64_t period = base * ncyc;
  if (base <= 0) {
    err = "sequence is empty";
    return false;
  }
  if (pwm_period_us < 1) pwm_period_us = 1;
  for (int ch = 0; ch < nch; ch++) {
    if (gpios[ch] < 0 || gpios[ch] > 15) {
      snprintf(buf, sizeof buf, "GPIO%d cannot be driven by the player", gpios[ch]);
      err = buf;
      return false;
    }
  }

  // static: the ESP8266 loop stack is only 4 kB (compile_program is not reentrant)
  static ChanGen gens[MAX_CHANNELS + 1];  // + sync
  static Ev heads[MAX_CHANNELS + 1];
  static bool live[MAX_CHANNELS + 1];
  uint32_t all_bits = 0;
  auto init = [&](ChanGen& g, int ch) {
    double p = clamp_power(powers[ch]);
    g = ChanGen();
    g.steps = &steps;
    g.ch = ch;
    g.en = enabled[ch];
    g.p_set = p;
    g.ncyc = ncyc;
    g.dith = dithered(cycle_dither, enabled[ch], powers[ch]);
    g.count = g.dith ? py_round((double)ncyc * p) : 0;
    g.cycle_power();
    g.pwm = pwm_period_us;
    g.minp = min_pulse_us;
    g.period = period;
    g.bit = uint32_t(1) << gpios[ch];
  };
  for (int ch = 0; ch < nch; ch++) {
    init(gens[ch], ch);
    all_bits |= gens[ch].bit;
  }
  uint32_t sync_bit = 0;
  const int SYNC = nch;
  // sync output: steps with mask bit nch, ORed with the pulse at the start of every
  // sequence period (on at c*base, off at c*base + w); the same in every period
  bool has_sync = sync_gpio >= 0;
  if (has_sync) {
    sync_bit = uint32_t(1) << sync_gpio;
    ChanGen& g = gens[SYNC];
    g = ChanGen();
    g.steps = &steps;
    g.ch = nch;
    g.en = true;
    g.p_set = 1.0;
    g.ncyc = ncyc;
    g.cycle_power();
    g.pwm = pwm_period_us;
    g.minp = min_pulse_us;
    g.period = period;
    g.bit = sync_bit;
    if (sync_us > 0) g.pulse_w = sync_us < base - 1 ? sync_us : base - 1;
  }
  // Only a stream's last interval can end at or beyond the period end; that
  // off edge wraps to (end % period) and is merged in after the streams.
  static Ev wrapped[MAX_CHANNELS + 1];
  int n_wrapped = 0;
  auto advance = [&](int i) {
    if (i == SYNC && !has_sync) {
      live[i] = false;
      return;
    }
    live[i] = gens[i].next(heads[i]);
    if (live[i] && heads[i].t >= period) {
      wrapped[n_wrapped++] = Ev{heads[i].t % period, 0, heads[i].off};
      live[i] = false;
    }
  };
  for (int i = 0; i <= SYNC; i++) advance(i);

  const char* too_many =
      "sequence needs more than %d edges: lengthen the PWM period or shorten the sequence";
  uint32_t stored = 0;
  uint32_t iter = 0;
  for (;;) {
    int64_t tmin = -1;
    for (int i = 0; i <= SYNC; i++)
      if (live[i] && (tmin < 0 || heads[i].t < tmin)) tmin = heads[i].t;
    if (tmin < 0) break;
    uint32_t on = 0, off = 0;
    for (int i = 0; i <= SYNC; i++) {
      while (live[i] && heads[i].t == tmin) {
        on |= heads[i].on;
        off |= heads[i].off;
        advance(i);
      }
    }
    if (stored >= (uint32_t)MAX_EDGES) {  // stop at the limit: the rest can only add edges
      snprintf(buf, sizeof buf, too_many, MAX_EDGES);
      err = buf;
      return false;
    }
    out.times[stored] = (uint64_t)tmin;
    out.sets[stored] = (uint16_t)on;
    out.clrs[stored] = (uint16_t)off;
    stored++;
    if ((++iter & 0x3FF) == 0) seqcore_idle_hook();
  }
  // merge the wrapped off edges into the (complete, sorted) table
  for (int j = 0; j < n_wrapped; j++) {
    const Ev& w = wrapped[j];
    uint32_t lo = 0, hi = stored;
    while (lo < hi) {
      uint32_t mid = (lo + hi) / 2;
      if (out.times[mid] < (uint64_t)w.t)
        lo = mid + 1;
      else
        hi = mid;
    }
    if (lo < stored && out.times[lo] == (uint64_t)w.t) {
      out.clrs[lo] |= (uint16_t)w.off;
      continue;
    }
    if (stored >= (uint32_t)MAX_EDGES) {
      snprintf(buf, sizeof buf, too_many, MAX_EDGES);
      err = buf;
      return false;
    }
    memmove(out.times + lo + 1, out.times + lo, (stored - lo) * sizeof out.times[0]);
    memmove(out.sets + lo + 1, out.sets + lo, (stored - lo) * sizeof out.sets[0]);
    memmove(out.clrs + lo + 1, out.clrs + lo, (stored - lo) * sizeof out.clrs[0]);
    out.times[lo] = (uint64_t)w.t;
    out.sets[lo] = 0;
    out.clrs[lo] = (uint16_t)w.off;
    stored++;
  }
  uint32_t n = stored;
  uint32_t start_on = 0;
  for (int ch = 0; ch < nch; ch++)
    if (gens[ch].start_on) start_on |= gens[ch].bit;
  if (has_sync && gens[SYNC].start_on) start_on |= sync_bit;

  uint32_t kept = 0;
  for (uint32_t i = 0; i < n; i++) {
    uint32_t on = out.sets[i], off = out.clrs[i];
    uint32_t both = on & off;  // off at the period end meets on at the start
    on &= ~both;
    off &= ~both;
    uint32_t s, c;
    if (active_high) {
      s = on;
      c = off;
    } else {
      s = off & ~sync_bit;
      c = on & ~sync_bit;
      s |= on & sync_bit;
      c |= off & sync_bit;
    }
    if (s || c) {
      out.times[kept] = out.times[i];
      out.sets[kept] = (uint16_t)s;
      out.clrs[kept] = (uint16_t)c;
      kept++;
    }
  }
  out.n = kept;
  out.period = period;
  out.cycle_factor = ncyc;
  {
    int64_t run = dense_run_us(out.times, kept, period, DENSE_GAP_US);
    if (run > DENSE_RUN_MAX_US) {
      char msg[200];
      if (run >= DENSE_FOREVER)
        snprintf(msg, sizeof msg,
                 "edges closer than %d us for the whole period: the player cannot keep up; "
                 "use a longer PWM period, equal powers, or a larger min pulse",
                 (int)DENSE_GAP_US + 1);
      else
        snprintf(msg, sizeof msg,
                 "edges closer than %d us for more than %d us: the player cannot keep up; "
                 "use a longer PWM period, equal powers, or a larger min pulse",
                 (int)DENSE_GAP_US + 1, (int)DENSE_RUN_MAX_US);
      out.n = 0;
      err = msg;
      return false;
    }
  }
  if (active_high) {
    out.start_set = start_on;
    out.start_clr = (all_bits | sync_bit) & ~start_on;
    out.idle_set = 0;
    out.idle_clr = all_bits | sync_bit;
  } else {
    uint32_t lasers_on = start_on & all_bits;
    out.start_set = (all_bits & ~lasers_on) | (start_on & sync_bit);
    out.start_clr = lasers_on | (sync_bit & ~start_on);
    out.idle_set = all_bits;
    out.idle_clr = sync_bit;
  }
  for (int ch = 0; ch < nch; ch++) {
    int64_t granted = 0;
    for (const Step& st : steps)
      if ((st.mask >> ch) & 1) granted += st.dur;
    granted *= ncyc;
    out.duty[ch] = (granted && enabled[ch]) ? (double)gens[ch].lit / (double)granted : 0.0;
  }
  return true;
}

}  // namespace

bool compile_program(const std::vector<Step>& steps, const int* gpios, int nch,
                     const bool* enabled, const double* powers, int64_t pwm_period_us,
                     int64_t min_pulse_us, bool active_high, int sync_gpio, int64_t sync_us,
                     Program& out, std::string& err, bool cycle_dither) {
  // == seqcore.compile_program: the largest cycle factor whose program fits
  bool any = false;
  for (int ch = 0; ch < nch; ch++)
    if (dithered(cycle_dither, enabled[ch], powers[ch])) any = true;
  if (!any)
    return compile_once(steps, gpios, nch, enabled, powers, pwm_period_us, min_pulse_us,
                        active_high, sync_gpio, sync_us, cycle_dither, 1, out, err);
  for (int64_t m : CYCLE_FACTORS) {
    err.clear();
    if (compile_once(steps, gpios, nch, enabled, powers, pwm_period_us, min_pulse_us,
                     active_high, sync_gpio, sync_us, cycle_dither, m, out, err))
      return true;
    seqcore_idle_hook();
  }
  return false;  // err: the error of the smallest factor
}

int64_t dense_run_us(const uint64_t* times, uint32_t n, int64_t period, int64_t gap) {
  // == seqcore.dense_run_us: longest stretch of consecutive edges at most `gap` apart
  if (n == 0) return 0;
  uint32_t start = 0;
  int64_t biggest = -1;
  bool any_big = false;
  for (uint32_t i = 0; i < n; i++) {
    int64_t g = (i + 1 < n) ? (int64_t)(times[i + 1] - times[i])
                            : (int64_t)times[0] + period - (int64_t)times[n - 1];
    if (g > gap) any_big = true;
    if (g > biggest) {  // first maximum, like Python's max()
      biggest = g;
      start = i;
    }
  }
  if (!any_big) return DENSE_FOREVER;
  int64_t longest = 0, run = 0;
  for (uint32_t k = 1; k <= n; k++) {
    uint32_t i = (start + k) % n;
    int64_t g = (i + 1 < n) ? (int64_t)(times[i + 1] - times[i])
                            : (int64_t)times[0] + period - (int64_t)times[n - 1];
    if (g <= gap) {
      run += g;
      if (run > longest) longest = run;
    } else {
      run = 0;
    }
  }
  return longest;
}

}  // namespace seqcore
