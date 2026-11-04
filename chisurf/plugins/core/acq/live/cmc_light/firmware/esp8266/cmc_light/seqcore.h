// Excitation sequence compiler: C++ port of cmc_light/seqcore.py.
//
// Portable (ESP8266 and host). Must stay behaviour-identical to the Python
// reference, including the error texts and the duty values.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace seqcore {

static const int MAX_EDGES = 1024;  // == seqcore.MAX_EDGES
static const int64_t DENSE_GAP_US = 12;        // == seqcore.DENSE_GAP_US (measured)
static const int64_t DENSE_RUN_MAX_US = 3000;   // == seqcore.DENSE_RUN_MAX_US
static const int64_t DENSE_FOREVER = 1LL << 30;  // == seqcore.DENSE_FOREVER
static const int MAX_STEPS = 512;   // == seqcore.MAX_STEPS
static const int MAX_CHANNELS = 8;
// == seqcore.CYCLE_FACTORS: sequence periods per program with cycle dithering, preferred first
static const int64_t CYCLE_FACTORS[] = {100, 50, 20, 10};

struct Step {
  int64_t dur;
  int64_t mask;
};

// Periodic edge program. Times are in us within one period; at each edge the
// player writes clrs[i] to GPIO_OUT_CLR and sets[i] to GPIO_OUT_SET.
struct Program {
  int64_t period = 0;
  uint32_t n = 0;  // number of edges actually played
  uint64_t times[MAX_EDGES];
  uint16_t sets[MAX_EDGES];
  uint16_t clrs[MAX_EDGES];
  uint32_t start_set = 0, start_clr = 0, idle_set = 0, idle_clr = 0;
  double duty[MAX_CHANNELS];
  int64_t cycle_factor = 1;  // sequence periods per program period (cycle dithering)
};

std::vector<Step> alex_steps(int n_channels, int64_t on_us, int64_t gap_us);
int64_t period_us(const std::vector<Step>& steps);

// Compile a sequence (see seqcore.compile_program). sync_gpio < 0: none.
// cycle_dither: power_mode "cycles" (else "pwm").
// Returns false and sets err to the Python ValueError text on failure.
bool compile_program(const std::vector<Step>& steps, const int* gpios, int nch,
                     const bool* enabled, const double* powers, int64_t pwm_period_us,
                     int64_t min_pulse_us, bool active_high, int sync_gpio, int64_t sync_us,
                     Program& out, std::string& err, bool cycle_dither = false);

int64_t dense_run_us(const uint64_t* times, uint32_t n, int64_t period, int64_t gap);

}  // namespace seqcore
