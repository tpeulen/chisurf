// Edge player on the ESP8266 FRC1 timer.
//
// The ISR plays every edge whose time has come (all outputs in one write to
// GPIO_OUT_CLR / GPIO_OUT_SET), then reprograms the one-shot timer for the
// next edge. The timer is set GUARD_US early and the last few microseconds
// are busy-waited, so edges land on the microsecond regardless of interrupt
// entry latency. Gaps longer than the 23-bit timer range are bridged by
// intermediate wake-ups. Schedule is absolute (base + times[i]), so there is
// no drift; lateness (actual - scheduled) is recorded.
#include "player.h"

#include <Arduino.h>

extern "C" {
#include <user_interface.h>
}

namespace player {
namespace {

// timer1 prescaler /16: 5 MHz, 0.2 us per tick, 23-bit range = 1.677 s
const uint32_t TICKS_PER_US = 5;
const int64_t MAX_ARM_US = 1000000;  // bridge longer gaps with extra wake-ups
#ifndef PLAYER_GUARD_US
#define PLAYER_GUARD_US 12  // wake-up error measured 2..12 us (1..6 us as NMI), WiFi AP on
#endif
const int64_t GUARD_US = PLAYER_GUARD_US;  // fire this early, busy-wait the rest
const int64_t MIN_ARM_US = 20;
const int64_t ISR_BUDGET_US = 4000;  // never hog the CPU longer than this
const int64_t START_DELAY_US = 2000;

enum Phase : uint8_t { START, EDGE, FINAL };

struct State {
  const uint64_t* times;
  const uint16_t* sets;
  const uint16_t* clrs;
  uint32_t n;
  uint64_t period;
  uint32_t idx;
  uint64_t base;
  uint64_t target;
  Phase phase;
  uint32_t cycles_max;
  bool wrapped;  // the last edge of a period was played; the cycle completes at base
  uint32_t start_set, start_clr, idle_set, idle_clr;
  // 64-bit extension of the 32-bit microsecond clock (owned by the ISR while active)
  uint32_t last32;
  uint32_t hi;
};

State st;
volatile bool active = false;
volatile uint32_t cycles = 0;
volatile uint32_t late_max = 0;
uint32_t all_outputs = 0;

#if PLAYER_DIAG
// wake-up error of the timer: actual entry time - requested entry time
int32_t diag_wake_min = 0x7fffffff, diag_wake_max = -0x7fffffff;
uint32_t diag_throttles = 0, diag_isr = 0;
uint64_t diag_wake_at = 0;
#endif

// system_get_time(): microseconds from the WDEV timer register (IRAM, register read + add)
inline IRAM_ATTR uint64_t now64() {
  uint32_t t = system_get_time();
  if (t < st.last32) st.hi++;
  st.last32 = t;
  return ((uint64_t)st.hi << 32) | t;
}

inline IRAM_ATTR void arm_us(int64_t us) {
  if (us > MAX_ARM_US) us = MAX_ARM_US;
  if (us < MIN_ARM_US) us = MIN_ARM_US;
#if PLAYER_DIAG
  diag_wake_at = ((uint64_t)st.hi << 32 | st.last32) + us;
#endif
  // only T1L here: TEIE is shared with the SDK (watchdog), a read-modify-write
  // from the NMI could race with it; the edge interrupt is enabled once in play()
  T1L = ((uint32_t)us * TICKS_PER_US) & 0x7FFFFF;
#if !PLAYER_NMI
  TEIE |= TEIE1;  // the core's level-1 handler clears it for one-shot timers
#endif
}

IRAM_ATTR void isr() {
  if (!active) return;
  uint64_t entry = now64();
#if PLAYER_DIAG
  {
    int32_t e = (int32_t)(int64_t)(entry - diag_wake_at);
    if (e < diag_wake_min) diag_wake_min = e;
    if (e > diag_wake_max) diag_wake_max = e;
    diag_isr++;
  }
#endif
  for (;;) {
    uint64_t now = now64();
    int64_t d = (int64_t)(st.target - now);
    if (d > GUARD_US) {
      // timer1 and the microsecond clock run from different dividers: allow 25 ppm
      arm_us(d - GUARD_US - d / 40000);
      return;
    }
    if ((int64_t)(now - entry) > ISR_BUDGET_US) {  // hopelessly dense program
#if PLAYER_DIAG
      diag_throttles++;
#endif
      arm_us(1000);
      return;
    }
    while (d > 0) {
      now = now64();
      d = (int64_t)(st.target - now);
    }
    uint32_t late = (uint32_t)(-d);
    if (st.wrapped) {  // passed the end of a period
      st.wrapped = false;
      cycles = cycles + 1;
    }
    if (st.phase == EDGE) {
      uint32_t i = st.idx;
      GPOC = st.clrs[i];
      GPOS = st.sets[i];
      if (late > late_max) late_max = late;
      if (++i >= st.n) {
        i = 0;
        st.base += st.period;
        st.wrapped = true;
        if (st.cycles_max && cycles + 1 >= st.cycles_max) {
          st.phase = FINAL;
          st.target = st.base;  // switch off at the end of the last period
          continue;
        }
      }
      st.idx = i;
      st.target = st.base + st.times[i];
    } else if (st.phase == START) {
      GPOC = st.start_clr;
      GPOS = st.start_set;
      st.phase = EDGE;
      st.idx = 0;
      st.target = st.base + st.times[0];
    } else {  // FINAL
      GPOC = st.idle_clr;
      GPOS = st.idle_set;
      if (late > late_max) late_max = late;
      active = false;
      T1C = 0;
      return;
    }
  }
}

void timer_off() {
  active = false;
  timer1_disable();
}

}  // namespace

void begin(uint32_t mask) {
  all_outputs = mask;
  timer1_disable();
#if PLAYER_NMI
  ETS_FRC_TIMER1_INTR_ATTACH(NULL, NULL);
  ETS_FRC_TIMER1_NMI_INTR_ATTACH(isr);
#else
  timer1_attachInterrupt(isr);
#endif
}

void write_static(uint32_t set_mask, uint32_t clr_mask) {
  timer_off();
  GPOC = clr_mask & all_outputs;
  GPOS = set_mask & all_outputs;
}

void stop() {
  bool was = active;
  timer_off();
  if (was) {
    GPOC = st.idle_clr;
    GPOS = st.idle_set;
  }
}

void play(const seqcore::Program& prog, uint32_t cycles_max) {
  timer_off();
  st.times = prog.times;
  st.sets = prog.sets;
  st.clrs = prog.clrs;
  st.n = prog.n;
  st.period = (uint64_t)prog.period;
  st.cycles_max = cycles_max;
  st.start_set = prog.start_set;
  st.start_clr = prog.start_clr;
  st.idle_set = prog.idle_set;
  st.idle_clr = prog.idle_clr;
  st.idx = 0;
  st.phase = START;
  st.wrapped = false;
  st.hi = 0;
  st.last32 = system_get_time();
  st.base = now64() + START_DELAY_US;
  st.target = st.base;
  cycles = 0;
  late_max = 0;
  if (!st.n) return;
  active = true;
  timer1_enable(TIM_DIV16, TIM_EDGE, TIM_SINGLE);
  timer1_write((uint32_t)(START_DELAY_US - GUARD_US) * TICKS_PER_US);  // also sets TEIE1
}

#if PLAYER_DIAG
void diag(char* buf, size_t n) {
  snprintf(buf, n,
           "guard %d wake_err_us min %d max %d isr %u throttles %u free_heap %u max_block %u "
           "free_stack_min %u reset %s",
           (int)GUARD_US, diag_wake_min, diag_wake_max, diag_isr, diag_throttles,
           (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getMaxFreeBlockSize(),
           (unsigned)ESP.getFreeContStack(), ESP.getResetReason().c_str());
  diag_wake_min = 0x7fffffff;
  diag_wake_max = -0x7fffffff;
  diag_isr = diag_throttles = 0;
}
#endif

bool running() { return active; }
uint32_t cycles_done() { return cycles; }
uint32_t late_max_us() { return late_max; }

}  // namespace player
