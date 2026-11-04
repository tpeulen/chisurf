#include "analysis.h"

#include <cmath>
#include <cstdlib>
#include <cstring>

namespace analysis {

unsigned long part_us[4] = {0, 0, 0, 0};
#ifdef ARDUINO
#include <esp_timer.h>
static inline unsigned long now_us() { return (unsigned long)esp_timer_get_time(); }
#else
static inline unsigned long now_us() { return 0; }
#endif

// response tables: raw 5/6-bit codes -> linear values (default: the code scaled to 0..255)
static uint16_t R8[32], G8[64], B8[32];
static uint8_t RAW_R8[32], RAW_G8[64];  // raw codes on an 8-bit scale, for saturation / ranging
static bool tables_ready = false, custom = false;

void reset_luts() {
  for (int i = 0; i < 32; i++) {
    RAW_R8[i] = uint8_t((i * 255 + 15) / 31);
    R8[i] = B8[i] = RAW_R8[i];
  }
  for (int i = 0; i < 64; i++) {
    RAW_G8[i] = uint8_t((i * 255 + 31) / 63);
    G8[i] = RAW_G8[i];
  }
  tables_ready = true;
  custom = false;
}

static void make_tables() { reset_luts(); }

void set_lut(int channel, const uint16_t *values) {
  if (!tables_ready) make_tables();
  uint16_t *t = channel == R ? R8 : channel == G ? G8 : B8;
  int n = channel == G ? 64 : 32;
  for (int i = 0; i < n; i++) t[i] = values[i] > LUT_MAX ? LUT_MAX : values[i];
  custom = true;
}

const uint16_t *get_lut(int channel, int *count) {
  if (!tables_ready) make_tables();
  *count = channel == G ? 64 : 32;
  return channel == R ? R8 : channel == G ? G8 : B8;
}

bool luts_custom() { return custom; }

bool alloc_profiles(Profiles &p, int width, int height) {
  if (p.width == width && p.height == height && p.x[0]) return true;
  for (int c = 0; c < NCH; c++) {
    free(p.x[c]);
    free(p.y[c]);
    p.x[c] = (float *)malloc(sizeof(float) * width);  // internal RAM: small and fast
    p.y[c] = (float *)malloc(sizeof(float) * height);
    if (!p.x[c] || !p.y[c]) return false;
  }
  p.width = width;
  p.height = height;
  return true;
}

// median and robust noise (1.4826 MAD) of a histogram
static void hist_stats(const uint32_t *hist, int bins, uint32_t n, float &median, float &noise) {
  if (n == 0) {
    median = 0;
    noise = 0.5f;
    return;
  }
  uint32_t half = (n + 1) / 2, acc = 0;
  int med = 0;
  for (; med < bins - 1; med++) {
    acc += hist[med];
    if (acc >= half) break;
  }
  acc = hist[med];
  int d = 0;
  while (acc < half && d < bins) {
    d++;
    if (med - d >= 0) acc += hist[med - d];
    if (med + d < bins) acc += hist[med + d];
  }
  noise = 1.4826f * float(d);
  if (noise < 0.5f) noise = 0.5f;  // quantisation floor
  // level: mean of the border within +-5 noise of the median. The median of integer codes is
  // biased by up to half a code, which over a whole frame adds up to a large false signal.
  int lo = med - int(5 * noise + 1), hi = med + int(5 * noise + 1);
  if (lo < 0) lo = 0;
  if (hi > bins - 1) hi = bins - 1;
  double sw = 0, sv = 0;
  for (int b = lo; b <= hi; b++) {
    sw += hist[b];
    sv += double(hist[b]) * b;
  }
  median = sw > 0 ? float(sv / sw) : float(med);
}

static inline void split(const uint8_t *px, int v[NCH]) {
  uint16_t w = (uint16_t(px[0]) << 8) | px[1];
  v[R] = R8[w >> 11];
  v[G] = G8[(w >> 5) & 0x3F];
  v[B] = B8[w & 0x1F];
  v[S] = v[R] + v[G] + v[B];
}

void add_dark(const uint8_t *rgb565, int width, int height, float *dark_sum) {
  if (!tables_ready) make_tables();
  const size_t n = size_t(width) * height;
  int v[NCH];
  for (size_t i = 0; i < n; i++) {
    split(rgb565 + 2 * i, v);
    for (int c = 0; c < NCH; c++) dark_sum[c * n + i] += v[c];
  }
}

// per-frame scratch (internal RAM)
static int32_t *colsum[NCH], *rowsum[NCH];
static int scratch_w = 0, scratch_h = 0;
// one frame row, copied from the camera's external memory: a burst copy is far faster
// than reading single pixels out of PSRAM (measured: the main pass more than halves)
static uint8_t *rowbuf = nullptr;
static int rowbuf_bytes = 0;

// copy a span of one row (or the whole row) into internal RAM
static const uint8_t *fetch_span(const uint8_t *rgb565, int width, int y, int x0, int count) {
  const uint8_t *src = rgb565 + 2 * (size_t(y) * width + size_t(x0));
  int need = 2 * count;
  if (x0 + count > width) need = 2 * (width - x0);
  if (rowbuf_bytes < need) {
    free(rowbuf);
    rowbuf = (uint8_t *)malloc(need);
    rowbuf_bytes = rowbuf ? need : 0;
  }
  if (!rowbuf) return src;
  memcpy(rowbuf, src, need);
  return rowbuf;
}

static inline const uint8_t *fetch_row(const uint8_t *rgb565, int width, int y) {
  return fetch_span(rgb565, width, y, 0, width);
}

static bool scratch(int w, int h) {
  if (w == scratch_w && h == scratch_h && colsum[0]) return true;
  for (int c = 0; c < NCH; c++) {
    free(colsum[c]);
    free(rowsum[c]);
    colsum[c] = (int32_t *)malloc(sizeof(int32_t) * w);
    rowsum[c] = (int32_t *)malloc(sizeof(int32_t) * h);
    if (!colsum[c] || !rowsum[c]) return false;
  }
  scratch_w = w;
  scratch_h = h;
  return true;
}

void analyse(const uint8_t *rgb565, int width, int height, BackgroundMode mode, const float *dark,
             float thr_frac, FrameStats &out, Profiles &prof, int step) {
  if (!tables_ready) make_tables();
  if (step < 1) step = 1;
  const int W = width / step, H = height / step;  // the sampled grid
  if (!scratch(W, H)) return;
  if (!alloc_profiles(prof, W, H)) return;
  const size_t n = size_t(W) * H;
  const float area = float(step) * float(step);  // sums are per frame pixel, not per sample
  out.width = width;
  out.height = height;
  out.step = step;

  // --- background: median / MAD of a 2-pixel border ring ---
  static const int BINS_C = LUT_MAX + 1, BINS_S = 3 * LUT_MAX + 1;
  static uint32_t hist_r[BINS_C], hist_g[BINS_C], hist_b[BINS_C], hist_s[BINS_S];
  uint32_t *hist[NCH] = {hist_r, hist_g, hist_b, hist_s};
  memset(hist_r, 0, sizeof(hist_r));
  memset(hist_g, 0, sizeof(hist_g));
  memset(hist_b, 0, sizeof(hist_b));
  memset(hist_s, 0, sizeof(hist_s));
  uint32_t nb = 0;
  int v[NCH];
  auto border_px = [&](int x, int y) {
    split(rgb565 + 2 * (size_t(y * step) * width + size_t(x) * step), v);
    for (int c = 0; c < NCH; c++) hist[c][v[c]]++;
    nb++;
  };
  const int ring = 2;
  unsigned long t_start = now_us();
  for (int y = 0; y < H; y++) {
    if (y < ring || y >= H - ring) {
      for (int x = 0; x < W; x++) border_px(x, y);
    } else {
      for (int x = 0; x < ring; x++) border_px(x, y);
      for (int x = W - ring; x < W; x++) border_px(x, y);
    }
  }
  part_us[0] = now_us() - t_start;
  float bgf[NCH], noise[NCH];
  int bg[NCH];
  for (int c = 0; c < NCH; c++) {
    hist_stats(hist[c], c == S ? BINS_S : BINS_C, nb, bgf[c], noise[c]);  // bgf: clipped mean level
    if (mode == BG_NONE) bgf[c] = 0;  // dark mode: the edge level still weights the spot moments
    bg[c] = int(bgf[c] + 0.5f);
  }

  // spot threshold from the previous frame's peak (the spot barely changes between frames)
  int thr[NCH];
  for (int c = 0; c < NCH; c++) {
    float prev_peak = out.ch[c].peak > 0 ? out.ch[c].peak : 0;
    float t = thr_frac * prev_peak, t3 = 3.0f * noise[c];
    thr[c] = int(t > t3 ? t : t3);
  }

  // --- one pass: raw column / row sums, peaks and spot moments ---
  // Background subtraction of the sums happens afterwards (colsum - bg * height), so
  // the per-pixel work is small; moments only run for the few pixels above threshold.
  for (int c = 0; c < NCH; c++) {
    memset(colsum[c], 0, sizeof(int32_t) * W);
    memset(rowsum[c], 0, sizeof(int32_t) * H);
  }
  double mw[NCH] = {0}, mx[NCH] = {0}, my[NCH] = {0}, mxx[NCH] = {0}, myy[NCH] = {0}, mxy[NCH] = {0};
  int peak[NCH] = {0, 0, 0, 0};
  int peak_x[NCH] = {0, 0, 0, 0}, peak_y[NCH] = {0, 0, 0, 0};
  uint32_t np[NCH] = {0}, sat = 0;
  int raw_top = 0;
  double dsum[NCH] = {0};
  const bool use_dark = mode == BG_DARK && dark;
  int thr_raw[NCH];
  for (int c = 0; c < NCH; c++) thr_raw[c] = thr[c] + bg[c];
  int32_t *cR = colsum[R], *cG = colsum[G], *cB = colsum[B];

  t_start = now_us();
  for (int y = 0; y < H; y++) {
    const uint8_t *px = fetch_row(rgb565, width, y * step);
    const int stride = 2 * step;
    int32_t rR = 0, rG = 0, rB = 0;
    for (int x = 0; x < W; x++, px += stride) {
      uint16_t w16 = (uint16_t(px[0]) << 8) | px[1];
      int r5 = w16 >> 11, g6 = (w16 >> 5) & 0x3F, b5 = w16 & 0x1F;
      int vr = R8[r5], vg = G8[g6], vb = B8[b5], vs = vr + vg + vb;
      cR[x] += vr;
      cG[x] += vg;
      cB[x] += vb;
      rR += vr;
      rG += vg;
      rB += vb;
      if (r5 == 31 || g6 == 63 || b5 == 31) sat++;
      int raw = RAW_R8[r5] > RAW_G8[g6] ? RAW_R8[r5] : RAW_G8[g6];
      if (RAW_R8[b5] > raw) raw = RAW_R8[b5];
      if (raw > raw_top) raw_top = raw;
      if (vr > peak[R]) { peak[R] = vr; peak_x[R] = x; peak_y[R] = y; }
      if (vg > peak[G]) { peak[G] = vg; peak_x[G] = x; peak_y[G] = y; }
      if (vb > peak[B]) { peak[B] = vb; peak_x[B] = x; peak_y[B] = y; }
      if (vs > peak[S]) { peak[S] = vs; peak_x[S] = x; peak_y[S] = y; }
    }
    rowsum[R][y] = rR;
    rowsum[G][y] = rG;
    rowsum[B][y] = rB;
  }

  part_us[1] = now_us() - t_start;
  t_start = now_us();
  // pass 2: the spot's moments in one box around the brightest pixel, all channels at
  // once (each pixel is read once: the frame lives in slow external memory). A whole-frame
  // pass would also drag the centroid towards stray light.
  {
    float prev = out.ch[S].sx > 0 ? out.ch[S].sx / step : 0.0f;
    int box = int(4.0f * prev) + 6;
    const int box_max = W / 4 > 12 ? W / 4 : 12;
    if (box > box_max) box = box_max;
    int cxp = peak_x[S], cyp = peak_y[S];
    int x0 = cxp - box, x1 = cxp + box + 1, y0 = cyp - box, y1 = cyp + box + 1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > W) x1 = W;
    if (y1 > H) y1 = H;
    for (int y = y0; y < y1; y++) {
      const uint8_t *px = fetch_span(rgb565, width, y * step, x0 * step, (x1 - x0) * step);
      float fw[NCH] = {0, 0, 0, 0}, fx[NCH] = {0, 0, 0, 0}, fxx[NCH] = {0, 0, 0, 0};
      for (int x = x0; x < x1; x++, px += 2 * step) {
        uint16_t w16 = (uint16_t(px[0]) << 8) | px[1];
        const int vv[NCH] = {R8[w16 >> 11], G8[(w16 >> 5) & 0x3F], B8[w16 & 0x1F], 0};
        const int vs = vv[R] + vv[G] + vv[B];
        for (int c = 0; c < NCH; c++) {
          int val = c == S ? vs : vv[c];
          if (val <= thr_raw[c]) continue;
          float sw = float(val - bg[c]), fxv = float(x);
          np[c]++;
          fw[c] += sw;
          fx[c] += sw * fxv;
          fxx[c] += sw * fxv * fxv;
        }
      }
      double yy = y;
      for (int c = 0; c < NCH; c++) {
        if (fw[c] == 0) continue;
        mw[c] += fw[c];
        mx[c] += fx[c];
        my[c] += fw[c] * yy;
        mxx[c] += fxx[c];
        myy[c] += fw[c] * yy * yy;
        mxy[c] += fx[c] * yy;
      }
    }
  }

  part_us[2] = now_us() - t_start;
  t_start = now_us();
  for (int x = 0; x < W; x++) colsum[S][x] = cR[x] + cG[x] + cB[x];
  for (int y = 0; y < H; y++) rowsum[S][y] = rowsum[R][y] + rowsum[G][y] + rowsum[B][y];
  int64_t total[NCH] = {0};
  for (int c = 0; c < NCH; c++)
    for (int x = 0; x < W; x++) total[c] += colsum[c][x];

  if (use_dark && step == 1) {  // per-pixel dark frame: a second, slower pass for the sums only
    for (int c = 0; c < NCH; c++) {
      double acc = 0;
      for (size_t i = 0; i < n; i++) acc += dark[c * n + i];
      dsum[c] = double(total[c]) - acc;
      for (int x = 0; x < width; x++) {
        double d = 0;
        for (int y = 0; y < height; y++) d += dark[c * n + size_t(y) * width + x];
        colsum[c][x] -= int32_t(d);
      }
      for (int y = 0; y < height; y++) {
        double d = 0;
        for (int x = 0; x < width; x++) d += dark[c * n + size_t(y) * width + x];
        rowsum[c][y] -= int32_t(d);
      }
    }
  }
  out.saturated = sat;
  out.raw_top = raw_top;
  for (int c = 0; c < NCH; c++) peak[c] -= bg[c];

  for (int c = 0; c < NCH; c++) {
    float sub_x = use_dark ? 0.0f : bgf[c] * H, sub_y = use_dark ? 0.0f : bgf[c] * W;
    for (int x = 0; x < W; x++) prof.x[c][x] = (float(colsum[c][x]) - sub_x) * area;
    for (int y = 0; y < H; y++) prof.y[c][y] = (float(rowsum[c][y]) - sub_y) * area;
    ChannelStats &st = out.ch[c];
    st.bg = bgf[c];
    st.noise = noise[c];
    st.peak = float(peak[c]);
    st.sum = (use_dark ? dsum[c] : double(total[c]) - double(bgf[c]) * double(n)) * area;
    st.npix = np[c];
    if (mw[c] > 0) {
      double W = mw[c];
      double cx = mx[c] / W, cy = my[c] / W;
      double vxx = mxx[c] / W - cx * cx, vyy = myy[c] / W - cy * cy, vxy = mxy[c] / W - cx * cy;
      double tr = 0.5 * (vxx + vyy), det = vxx * vyy - vxy * vxy;
      double disc = std::sqrt(std::fabs(tr * tr - det));
      double l1 = tr + disc, l2 = tr - disc;
      st.cx = float(cx * step);  // back to frame pixels
      st.cy = float(cy * step);
      st.sx = float(std::sqrt(l1 > 0 ? l1 : 0) * step);
      st.sy = float(std::sqrt(l2 > 0 ? l2 : 0) * step);
      st.angle = float(0.5 * std::atan2(2 * vxy, vxx - vyy) * 180.0 / M_PI);
    } else {
      st.cx = st.cy = -1;
      st.sx = st.sy = st.angle = 0;
    }
    st.spot_sum = 0;
    st.spot_bg = 0;
    st.spot_px = 0;
  }

  // --- spot photometry with a local background (small boxes: cheap) ---
  for (int c = 0; c < NCH; c++) {
    ChannelStats &st = out.ch[c];
    if (st.cx < 0) continue;
    float half = (3.0f * st.sx + 3.0f) / step;
    if (half > 0.25f * W) half = 0.25f * W;
    float scx = st.cx / step, scy = st.cy / step;
    int x0 = int(scx - half), x1 = int(scx + half + 1), y0 = int(scy - half), y1 = int(scy + half + 1);
    int ring = int(0.5f * half) + 3;
    int X0 = x0 - ring, X1 = x1 + ring, Y0 = y0 - ring, Y1 = y1 + ring;
    if (X0 < 0) X0 = 0;
    if (Y0 < 0) Y0 = 0;
    if (X1 > W) X1 = W;
    if (Y1 > H) Y1 = H;
    if (x0 < X0) x0 = X0;
    if (y0 < Y0) y0 = Y0;
    if (x1 > X1) x1 = X1;
    if (y1 > Y1) y1 = Y1;
    int64_t in_sum = 0, ring_sum = 0;
    uint32_t in_n = 0, ring_n = 0;
    for (int y = Y0; y < Y1; y++) {
      const uint8_t *px = fetch_span(rgb565, width, y * step, X0 * step, (X1 - X0) * step);
      bool yin = y >= y0 && y < y1;
      for (int x = X0; x < X1; x++, px += 2 * step) {
        uint16_t w16 = (uint16_t(px[0]) << 8) | px[1];
        int vr = R8[w16 >> 11], vg = G8[(w16 >> 5) & 0x3F], vb = B8[w16 & 0x1F];
        int val = c == R ? vr : c == G ? vg : c == B ? vb : vr + vg + vb;
        if (yin && x >= x0 && x < x1) {
          in_sum += val;
          in_n++;
        } else {
          ring_sum += val;
          ring_n++;
        }
      }
    }
    float ring_mean = ring_n ? float(double(ring_sum) / ring_n) : bgf[c];
    st.spot_bg = ring_mean;
    st.spot_px = uint32_t(in_n * area);
    st.spot_sum = (double(in_sum) - double(ring_mean) * in_n) * area;
  }
  part_us[3] = now_us() - t_start;
}

}  // namespace analysis
