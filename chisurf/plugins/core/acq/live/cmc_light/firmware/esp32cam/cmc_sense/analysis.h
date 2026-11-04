// Frame analysis of the cmc-sense light sensor: the camera is used as a
// quantitative detector, never as an image source.
//
// Input: an RGB565 frame (big-endian, as the OV2640 delivers it). Every pixel
// is split into four channels, all scaled to 8-bit codes: R, G, B and S = R+G+B.
//
// For each channel the analysis reports
//   bg     background level per pixel (median of the frame border)
//   noise  robust noise of the border (1.4826 * MAD)
//   peak   brightest pixel minus background
//   sum    sum over all pixels of (value - bg): the integrated signal
//   npix   pixels above the spot threshold
//   cx,cy  centroid of the spot (pixels, weighted by value - bg above threshold)
//   sx,sy  1-sigma widths along the principal axes (pixels), angle in degrees
//   spot_sum, spot_bg, spot_px   local-background photometry of the spot
// and the x / y projections of (value - bg) for beam profiles.
#pragma once

#include <cstdint>
#include <cstddef>

namespace analysis {

enum Channel { R = 0, G = 1, B = 2, S = 3, NCH = 4 };

enum BackgroundMode { BG_EDGE = 0, BG_DARK = 1, BG_NONE = 2 };

struct ChannelStats {
  float bg, noise, peak;
  double sum;
  uint32_t npix;
  float cx, cy, sx, sy, angle;
  // spot photometry with a local background: sum over a box of half-size 3 sigma around
  // the centroid, minus the mean level of the ring box around it (robust to stray light
  // and vignetting, which the border background is not)
  double spot_sum;
  float spot_bg;
  uint32_t spot_px;
};

struct FrameStats {
  int width, height;  // of the frame; coordinates and widths stay in frame pixels
  int step;           // pixel binning: only every step-th pixel in x and y was read
  uint32_t saturated;  // pixels with any channel at its full-scale code
  int raw_top;         // brightest raw colour code of the frame (8-bit scale), for auto-ranging
  ChannelStats ch[NCH];
};

// Profiles: prof_x[c][i] for i < width, prof_y[c][j] for j < height.
struct Profiles {
  int width = 0, height = 0;
  float *x[NCH] = {nullptr, nullptr, nullptr, nullptr};
  float *y[NCH] = {nullptr, nullptr, nullptr, nullptr};
};

// Response tables: raw sensor code (R, B: 5 bit, G: 6 bit) -> linear value, 0..LUT_MAX.
// The default maps codes to 0..255. A calibration (host side, with the laser as a known
// light source) replaces them so that every pixel value is proportional to the light.
static const int LUT_MAX = 1023;
void set_lut(int channel, const uint16_t *values);  // 32 values for R and B, 64 for G
const uint16_t *get_lut(int channel, int *count);
void reset_luts();
bool luts_custom();

// Allocate profile buffers for a frame size (PSRAM when available). Returns false on OOM.
bool alloc_profiles(Profiles &p, int width, int height);

// timing of the last analysis, microseconds: border, main pass, spot moments, photometry
extern unsigned long part_us[4];

// dark: optional per-channel dark frame (NCH * width * height floats), used when mode == BG_DARK.
// thr_frac: spot threshold as a fraction of the peak (above the background, at least 3 noise).
// step: analyse only every step-th pixel in both directions (1, 2, 4 ...). Sums are scaled
// by step*step, so the numbers stay comparable; the profiles then have width/step entries.
void analyse(const uint8_t *rgb565, int width, int height, BackgroundMode mode, const float *dark,
             float thr_frac, FrameStats &out, Profiles &prof, int step = 1);

// Accumulate a frame into a dark sum (NCH * width * height floats).
void add_dark(const uint8_t *rgb565, int width, int height, float *dark_sum);

}  // namespace analysis
