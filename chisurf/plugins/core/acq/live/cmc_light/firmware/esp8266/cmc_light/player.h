// Edge player: plays a seqcore::Program from the FRC1 (timer1) interrupt.
#pragma once

#include <cstddef>
#include <cstdint>

#include "seqcore.h"

namespace player {

// 0 (default): timer1 as normal level-1 interrupt.
// 1: timer1 as NMI. Slightly smaller wake-up error, but on the D1 mini it crashed
//    the WiFi SDK (Exception 9/28 in the WiFi event callback) within 1-2 minutes at
//    2-20 kHz edge rates, so it is off by default.
#ifndef PLAYER_NMI
#define PLAYER_NMI 0
#endif

void begin(uint32_t all_outputs_mask);
// Drive levels; stops playback.
void write_static(uint32_t set_mask, uint32_t clr_mask);
// Start periodic playback of prog (must stay valid until stop()); cycles 0 = forever.
void play(const seqcore::Program& prog, uint32_t cycles);
// Stop playback; outputs go to the program's idle levels if it was playing.
void stop();
bool running();
uint32_t cycles_done();
uint32_t late_max_us();

#ifndef PLAYER_DIAG
#define PLAYER_DIAG 0
#endif
#if PLAYER_DIAG
void diag(char* buf, size_t n);  // debug builds: "#DIAG" on the serial port
#endif

}  // namespace player
