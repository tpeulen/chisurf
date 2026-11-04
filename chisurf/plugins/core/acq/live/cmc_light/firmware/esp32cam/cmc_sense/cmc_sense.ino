// cmc-sense: an ESP32-CAM (AI-Thinker, OV2640) as a quantitative light sensor.
//
// No images leave the board. Every frame is analysed on the chip (analysis.cpp):
// integrated signal, peak, spot centroid and widths per colour channel, and x / y
// beam profiles. The computer reads them with SCPI commands over the USB serial
// cable (see docs/SENSE.md). Exposure and gain are set by the chip's own auto-ranging
// loop (or by hand) and reported with every reading, so the signal can be normalised
// to exposure x gain: that is what gives the large dynamic range.
#include <Arduino.h>
#include <esp_camera.h>
#include <esp_log.h>
#include <esp_mac.h>
#include <esp_rom_sys.h>

#include <Preferences.h>

#include "analysis.h"

static const char *VERSION = "1.0";
static const long BAUD = 115200;  // the board always starts here; SYST:BAUD switches
static long baud_now = BAUD;

// AI-Thinker ESP32-CAM pins
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22
#define FLASH_LED_GPIO 4

using namespace analysis;

// ---------------------------------------------------------------- settings --
struct Settings {
  framesize_t size = FRAMESIZE_QVGA;
  int exposure = 300;  // OV2640 AEC lines, 1..1200
  int gain = 0;        // 0..30 (index into the sensor's gain table)
  bool auto_range = true;
  BackgroundMode bg = BG_EDGE;
  float thr_frac = 0.2f;
  int bin = 1;         // analyse every bin-th pixel in x and y: fewer pixels, faster readings
  int exposure_max = 1200;  // auto-ranging never goes past this (long exposures = few frames/s)
};
static Settings cfg;
static Preferences prefs;

// ---------------------------------------------------------------- state --
static sensor_t *sensor = nullptr;
static bool camera_ok = false;
static char serial_no[16] = "0";
static char sensor_name[16] = "none";
static FrameStats stats;
static Profiles prof;
static uint32_t frame_no = 0;       // analysed frames
static uint32_t settle_skip = 0;    // frames still to discard after a setting change
static int ae_state = 0;            // 0 in range, 1 adjusting, 2 too bright at min, 3 too dark at max
static unsigned long frame_ms = 0;  // capture time of the last analysed frame
static float fps = 0;
static int used_exposure = 0, used_gain = 0;  // settings the last analysed frame was taken with
static unsigned long grab_us = 0, analyse_us = 0;  // time of the last capture / analysis
static bool stream_on = false;  // push a reading after every analysed frame (no request)
static int stream_bin = 4;      // profile binning of the stream
static int stream_every = 0;    // profiles with every n-th streamed reading (0: never)
static void print_measurement(const char *prefix = "");
static void print_profile(const float *p, int len, int bin, const char *prefix = "");
static float *dark = nullptr;
static int dark_w = 0, dark_h = 0;

// errors, SCPI style
static const int ERRQ = 8;
static int err_code[ERRQ];
static String err_msg[ERRQ];
static int err_n = 0;
static void push_error(int code, const String &msg) {
  if (err_n < ERRQ) {
    err_code[err_n] = code;
    err_msg[err_n] = msg;
    err_n++;
  }
}

// OV2640 gain table (esp32-camera ov2640.c): multiplier from the register bits
static float gain_factor(int g) {
  static const uint8_t tbl[31] = {0x00, 0x10, 0x18, 0x30, 0x34, 0x38, 0x3C, 0x70, 0x72, 0x74, 0x76,
                                  0x78, 0x7A, 0x7C, 0x7E, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6,
                                  0xF7, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF};
  if (g < 0) g = 0;
  if (g > 30) g = 30;
  uint8_t r = tbl[g];
  float f = 1.0f + float(r & 0x0F) / 16.0f;
  for (int b = 4; b < 8; b++) f *= (r & (1 << b)) ? 2.0f : 1.0f;
  return f;
}

static void apply_exposure() {
  if (!sensor) return;
  sensor->set_aec_value(sensor, cfg.exposure);
  sensor->set_agc_gain(sensor, cfg.gain);
  settle_skip = 2;  // the sensor applies new values a frame or two later
}

static void configure_sensor() {
  sensor->set_pixformat(sensor, PIXFORMAT_RGB565);
  sensor->set_framesize(sensor, cfg.size);
  // a measurement instrument: every automatic image "improvement" off
  sensor->set_exposure_ctrl(sensor, 0);
  sensor->set_aec2(sensor, 0);
  sensor->set_gain_ctrl(sensor, 0);
  sensor->set_whitebal(sensor, 0);
  sensor->set_awb_gain(sensor, 0);
  sensor->set_raw_gma(sensor, 0);
  sensor->set_lenc(sensor, 0);
  sensor->set_bpc(sensor, 0);
  sensor->set_wpc(sensor, 0);
  sensor->set_dcw(sensor, 1);
  sensor->set_brightness(sensor, 0);
  sensor->set_contrast(sensor, 0);
  sensor->set_saturation(sensor, 0);
  sensor->set_sharpness(sensor, 0);
  sensor->set_denoise(sensor, 0);
  sensor->set_special_effect(sensor, 0);
  sensor->set_colorbar(sensor, 0);
  sensor->set_hmirror(sensor, 0);
  sensor->set_vflip(sensor, 0);
  // OV2640 clock divider: the driver's default (3) gives ~10 frames/s in RGB565; 1 is the
  // fastest the ESP32's capture keeps up with (0 overruns: short frames)
  if (sensor->id.PID == OV2640_PID) sensor->set_reg(sensor, 0x111, 0xFF, 0x01);
  apply_exposure();
}

static int xclk_hz = 24000000;  // OV2640 takes up to ~24 MHz; more frames per second
static bool fb_in_dram = false;  // PSRAM: internal-RAM frame buffers delivered empty frames (FB-SIZE 0)

static bool camera_begin() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;
  c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM;
  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;
  c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM;
  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM;
  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = xclk_hz;
  c.pixel_format = PIXFORMAT_RGB565;
  c.frame_size = cfg.size;
  c.jpeg_quality = 12;
  // two frame buffers: the camera fills one while the chip analyses the other
  c.fb_count = psramFound() ? 2 : 1;
  c.fb_location = (fb_in_dram || !psramFound()) ? CAMERA_FB_IN_DRAM : CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t e = ESP_FAIL;
  for (int attempt = 0; attempt < 4 && e != ESP_OK; attempt++) {
    if (attempt) {  // after a soft restart the sensor may not answer: power-cycle it via PWDN
      esp_camera_deinit();
      pinMode(PWDN_GPIO_NUM, OUTPUT);
      digitalWrite(PWDN_GPIO_NUM, HIGH);
      delay(200);
      digitalWrite(PWDN_GPIO_NUM, LOW);
      delay(200);
    }
    e = esp_camera_init(&c);
  }
  if (e != ESP_OK) {
    push_error(-240, String("Hardware error; camera init failed 0x") + String(e, HEX));
    return false;
  }
  sensor = esp_camera_sensor_get();
  switch (sensor->id.PID) {
    case OV2640_PID: strcpy(sensor_name, "OV2640"); break;
    case OV3660_PID: strcpy(sensor_name, "OV3660"); break;
    case OV5640_PID: strcpy(sensor_name, "OV5640"); break;
    default: snprintf(sensor_name, sizeof(sensor_name), "PID%04X", sensor->id.PID);
  }
  configure_sensor();
  return true;
}

// ---------------------------------------------------------------- auto range --
static void auto_range() {
  if (!cfg.auto_range) {
    ae_state = 0;
    return;
  }
  // brightest raw code of the colour channels (8-bit scale, independent of the response tables)
  float top = float(stats.raw_top);
  const float lo = 90, hi = 235;
  int exp = cfg.exposure, gain = cfg.gain;
  if (stats.saturated > 0 || top >= hi) {
    if (gain > 0) {
      gain = gain > 4 ? gain - 4 : 0;
    } else {
      exp = exp / 2;
    }
  } else if (top < lo) {
    float f = 160.0f / (top > 8 ? top : 8);
    if (f > 4) f = 4;
    if (exp < cfg.exposure_max) {
      int e2 = int(exp * f + 0.5f);
      exp = e2 > exp ? e2 : exp + 1;
    } else if (gain < 30) {
      gain = gain + 2 > 30 ? 30 : gain + 2;
    }
  }
  if (exp < 1) exp = 1;
  if (exp > cfg.exposure_max) exp = cfg.exposure_max;
  if (exp != cfg.exposure || gain != cfg.gain) {
    ae_state = 1;
    cfg.exposure = exp;
    cfg.gain = gain;
    apply_exposure();
  } else if (stats.saturated > 0 || top >= hi) {
    ae_state = 2;
  } else if (top < lo) {
    ae_state = 3;
  } else {
    ae_state = 0;
  }
}

// ---------------------------------------------------------------- frames --
static bool grab_and_analyse() {
  unsigned long t0 = micros();
  camera_fb_t *fb = esp_camera_fb_get();
  grab_us = micros() - t0;
  if (!fb) {
    push_error(-240, "Hardware error; no frame");
    return false;
  }
  bool used = false;
  if (settle_skip > 0) {
    settle_skip--;
  } else if (fb->format == PIXFORMAT_RGB565) {
    int w = fb->width, h = fb->height;
    {
      const float *d = (cfg.bg == BG_DARK && dark && dark_w == w && dark_h == h && cfg.bin == 1)
                           ? dark : nullptr;
      unsigned long t1 = micros();
      analyse(fb->buf, w, h, d ? BG_DARK : (cfg.bg == BG_DARK ? BG_EDGE : cfg.bg), d, cfg.thr_frac,
              stats, prof, cfg.bin);
      analyse_us = micros() - t1;
      used_exposure = cfg.exposure;
      used_gain = cfg.gain;
      unsigned long now = millis();
      if (frame_ms) {
        float inst = 1000.0f / float(now - frame_ms > 0 ? now - frame_ms : 1);
        fps = fps ? 0.8f * fps + 0.2f * inst : inst;
      }
      frame_ms = now;
      frame_no++;
      used = true;
    }
  }
  esp_camera_fb_return(fb);
  if (used) {
    auto_range();
    if (stream_on) {  // push the reading: no request, no waiting for the next frame
      print_measurement("#M");
      if (stream_every > 0 && frame_no % stream_every == 0) {
        static const char *names = "RGBS";
        char tag[4] = {'#', 'X', 'R', 0};
        for (int c = 0; c < NCH; c++) {
          tag[1] = 'X';
          tag[2] = names[c];
          print_profile(prof.x[c], prof.width, stream_bin, tag);
          tag[1] = 'Y';
          print_profile(prof.y[c], prof.height, stream_bin, tag);
        }
      }
    }
  }
  return used;
}

static bool acquire_dark(int frames) {
  if (!camera_ok) return false;
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) return false;
  int w = fb->width, h = fb->height;
  esp_camera_fb_return(fb);
  size_t n = size_t(w) * h * NCH;
  if (!dark || dark_w != w || dark_h != h) {
    free(dark);
    dark = (float *)ps_malloc(sizeof(float) * n);
    if (!dark) return false;
    dark_w = w;
    dark_h = h;
  }
  memset(dark, 0, sizeof(float) * n);
  int got = 0;
  for (int k = 0; k < frames + 2; k++) {
    fb = esp_camera_fb_get();
    if (!fb) continue;
    if (k >= 2 && fb->width == w && fb->height == h) {  // skip two frames: settings settle
      add_dark(fb->buf, w, h, dark);
      got++;
    }
    esp_camera_fb_return(fb);
  }
  if (!got) return false;
  for (size_t i = 0; i < n; i++) dark[i] /= float(got);
  return true;
}

// ---------------------------------------------------------------- SCPI --
static const char *FIELDS =
    "frame,t_ms,fps,exposure,gain,gain_x,saturated,range_state,width,height,bin,"
    "R_bg,R_noise,R_peak,R_sum,R_npix,R_cx,R_cy,R_sx,R_sy,R_angle,R_spot_sum,R_spot_bg,R_spot_px,"
    "G_bg,G_noise,G_peak,G_sum,G_npix,G_cx,G_cy,G_sx,G_sy,G_angle,G_spot_sum,G_spot_bg,G_spot_px,"
    "B_bg,B_noise,B_peak,B_sum,B_npix,B_cx,B_cy,B_sx,B_sy,B_angle,B_spot_sum,B_spot_bg,B_spot_px,"
    "S_bg,S_noise,S_peak,S_sum,S_npix,S_cx,S_cy,S_sx,S_sy,S_angle,S_spot_sum,S_spot_bg,S_spot_px";

// Data lines end with "*HH": the sum of all bytes before the '*', modulo 256, in hex. The
// CH340 link on macOS very rarely drops a byte; the checksum lets the host notice.
static void send_checked(const char *data, int len) {
  uint8_t sum = 0;
  for (int i = 0; i < len; i++) sum += uint8_t(data[i]);
  char tail[6];
  snprintf(tail, sizeof(tail), "*%02X\n", sum);
  Serial.write((const uint8_t *)data, len);
  Serial.write((const uint8_t *)tail, strlen(tail));
}

static void print_measurement(const char *prefix) {
  static char line[1024];
  int pos = snprintf(line, sizeof(line), "%s", prefix);
  char buf[256];
  snprintf(buf, sizeof(buf), "%lu,%lu,%.1f,%d,%d,%.4f,%lu,%d,%d,%d,%d", (unsigned long)frame_no,
           (unsigned long)frame_ms, fps, used_exposure, used_gain, gain_factor(used_gain),
           (unsigned long)stats.saturated, ae_state, stats.width, stats.height, stats.step);
  pos += snprintf(line + pos, sizeof(line) - pos, "%s", buf);
  for (int c = 0; c < NCH; c++) {
    const ChannelStats &s = stats.ch[c];
    snprintf(buf, sizeof(buf), ",%.2f,%.2f,%.2f,%.1f,%lu,%.3f,%.3f,%.3f,%.3f,%.2f,%.1f,%.2f,%lu", s.bg,
             s.noise, s.peak, s.sum, (unsigned long)s.npix, s.cx, s.cy, s.sx, s.sy, s.angle, s.spot_sum,
             s.spot_bg, (unsigned long)s.spot_px);
    pos += snprintf(line + pos, sizeof(line) - pos, "%s", buf);
  }
  send_checked(line, pos);
}

// profiles as integers in one write: the CH340 USB-serial link on macOS loses bytes of long
// fragmented replies at high baud rates, so the link runs at 115200 and replies are compact
static void print_profile(const float *p, int len, int bin, const char *prefix) {
  static char line[4096];
  int pos = snprintf(line, sizeof(line), "%s", prefix);
  for (int i = 0; i < len && pos < int(sizeof(line)) - 16; i += bin) {
    float acc = 0;
    for (int k = i; k < i + bin && k < len; k++) acc += p[k];
    pos += snprintf(line + pos, sizeof(line) - pos, i ? ",%ld" : "%ld", lround(acc));
  }
  send_checked(line, pos);
}

static int channel_of(String s) {
  s.trim();
  s.toUpperCase();
  if (s == "R") return R;
  if (s == "G") return G;
  if (s == "B") return B;
  if (s == "S") return S;
  return -1;
}

static bool wait_fresh_frame(uint32_t after, unsigned long timeout_ms = 3000) {
  unsigned long t0 = millis();
  while (frame_no <= after) {
    if (millis() - t0 > timeout_ms) return false;
    if (camera_ok) grab_and_analyse();
    else delay(10);
  }
  return true;
}

// Short SCPI form: the header up to the first space, upper-cased, long words cut to their
// short form (MEASure -> MEAS). Matching is on the short forms.
static String short_header(const String &h) {
  String out, word;
  auto flush = [&]() {
    String w = word;
    w.toUpperCase();
    bool query = w.endsWith("?");
    if (query) w.remove(w.length() - 1);
    if (w.length() > 4 && !w.startsWith("*")) {
      // long form: SCPI short form is the first four letters, three if the fourth is a
      // vowel (EXPOSURE -> EXP, THRESHOLD -> THR, MEASURE -> MEAS)
      w = w.substring(0, 4);
      char last = w[3];
      if (last == 'A' || last == 'E' || last == 'I' || last == 'O' || last == 'U') w.remove(3);
    }
    out += w;
    if (query) out += "?";
    word = "";
  };
  for (unsigned i = 0; i < h.length(); i++) {
    char c = h[i];
    if (c == ':') {
      flush();
      out += ':';
    } else {
      word += c;
    }
  }
  flush();
  if (out.startsWith(":")) out.remove(0, 1);
  return out;
}

static void handle(String line) {
  line.trim();
  if (!line.length()) return;
  int sp = line.indexOf(' ');
  String head = short_header(sp < 0 ? line : line.substring(0, sp));
  String arg = sp < 0 ? "" : line.substring(sp + 1);
  arg.trim();
  String uarg = arg;
  uarg.toUpperCase();

  if (head == "*IDN?") {
    Serial.printf("CMC,SENSE-CAM-%s,%s,%s\n", sensor_name, serial_no, VERSION);
  } else if (head == "*RST") {
    framesize_t size = cfg.size;  // the frame size survives *RST (changing it restarts the board)
    cfg = Settings();
    cfg.size = size;
    if (camera_ok) apply_exposure();
  } else if (head == "*OPC?") {
    Serial.println("1");
  } else if (head == "SYST:ERR?") {
    if (err_n == 0) {
      Serial.println("0,\"No error\"");
    } else {
      Serial.printf("%d,\"%s\"\n", err_code[0], err_msg[0].c_str());
      for (int i = 1; i < err_n; i++) {
        err_code[i - 1] = err_code[i];
        err_msg[i - 1] = err_msg[i];
      }
      err_n--;
    }
  } else if (head == "MEAS?" || head == "MEAS:SCAL?") {
    if (!camera_ok) {
      push_error(-240, "Hardware error; no camera");
      Serial.println("");
    } else if (!wait_fresh_frame(frame_no)) {
      push_error(-240, "Hardware error; frame timeout");
      Serial.println("");
    } else {
      print_measurement("");
    }
  } else if (head == "CAL:LUT") {
    // CAL:LUT <R|G|B>,v0,v1,... : response table (32 values for R and B, 64 for G), 0..1023
    int comma = uarg.indexOf(',');
    int ch = channel_of(comma < 0 ? uarg : uarg.substring(0, comma));
    int n = ch == G ? 64 : 32;
    uint16_t vals[64];
    int got = 0, pos = comma + 1;
    while (ch >= 0 && ch != S && comma > 0 && got < n && pos <= int(uarg.length())) {
      int next = uarg.indexOf(',', pos);
      String tok = next < 0 ? uarg.substring(pos) : uarg.substring(pos, next);
      long v = tok.toInt();
      if (v < 0 || v > LUT_MAX) break;
      vals[got++] = uint16_t(v);
      if (next < 0) break;
      pos = next + 1;
    }
    if (ch < 0 || ch == S || got != n) {
      push_error(-224, "Illegal parameter value; CAL:LUT <R|G|B>,<32|64 values 0..1023>");
    } else {
      set_lut(ch, vals);
      prefs.putBytes(ch == R ? "lutR" : ch == G ? "lutG" : "lutB", vals, sizeof(uint16_t) * n);
    }
  } else if (head == "CAL:LUT?") {
    int ch = channel_of(uarg);
    if (ch < 0 || ch == S) {
      push_error(-224, "Illegal parameter value");
      Serial.println("");
    } else {
      int n = 0;
      const uint16_t *t = get_lut(ch, &n);
      String out;
      for (int i = 0; i < n; i++) out += (i ? "," : "") + String(t[i]);
      Serial.println(out);
    }
  } else if (head == "CAL:LUT:RES") {
    reset_luts();
    prefs.remove("lutR");
    prefs.remove("lutG");
    prefs.remove("lutB");
  } else if (head == "CAL:LUT:STAT?") {
    Serial.println(luts_custom() ? "CUSTOM" : "IDENTITY");
  } else if (head == "SYST:REG?") {  // SYST:REG? <reg> (bank<<8|reg): sensor register, for development
    Serial.println(camera_ok ? sensor->get_reg(sensor, strtol(arg.c_str(), nullptr, 0), 0xFF) : -1);
  } else if (head == "SYST:REG") {  // SYST:REG <reg>,<value>
    int comma = arg.indexOf(',');
    if (camera_ok && comma > 0) {
      sensor->set_reg(sensor, strtol(arg.substring(0, comma).c_str(), nullptr, 0), 0xFF,
                      strtol(arg.substring(comma + 1).c_str(), nullptr, 0));
      settle_skip = 2;
    }
  } else if (head == "SYST:TIM?") {
    Serial.printf("%lu,%lu,%lu,%lu,%lu,%lu\n", grab_us, analyse_us, analysis::part_us[0],
                  analysis::part_us[1], analysis::part_us[2], analysis::part_us[3]);
  } else if (head == "MEAS:LAST?") {
    print_measurement("");
  } else if (head == "MEAS:FIEL?") {
    Serial.println(FIELDS);
  } else if (head == "MEAS:PROF?") {
    // MEAS:PROF? <R|G|B|S>,<X|Y>[,<bin>]  -> profile of the last frame
    int c1 = uarg.indexOf(','), c2 = uarg.indexOf(',', c1 + 1);
    int ch = channel_of(c1 < 0 ? uarg : uarg.substring(0, c1));
    String axis = c1 < 0 ? "X" : (c2 < 0 ? uarg.substring(c1 + 1) : uarg.substring(c1 + 1, c2));
    axis.trim();
    int bin = c2 < 0 ? 1 : uarg.substring(c2 + 1).toInt();
    if (bin < 1) bin = 1;
    if (ch < 0 || (axis != "X" && axis != "Y") || !prof.x[0]) {
      push_error(-224, "Illegal parameter value");
      Serial.println("");
    } else if (axis == "X") {
      print_profile(prof.x[ch], prof.width, bin);
    } else {
      print_profile(prof.y[ch], prof.height, bin);
    }
  } else if (head == "MEAS:STRE") {
    // MEAS:STREam ON[,<profile bin>[,<profiles every n frames>]] | OFF
    int c1 = uarg.indexOf(','), c2 = uarg.indexOf(',', c1 + 1);
    String on = c1 < 0 ? uarg : uarg.substring(0, c1);
    on.trim();
    if (on == "OFF" || on == "0") {
      stream_on = false;
    } else if (on == "ON" || on == "1") {
      if (c1 > 0) {
        int b = (c2 < 0 ? uarg.substring(c1 + 1) : uarg.substring(c1 + 1, c2)).toInt();
        stream_bin = b > 0 ? b : 4;
        stream_every = c2 > 0 ? uarg.substring(c2 + 1).toInt() : 0;
      }
      stream_on = true;
    } else {
      push_error(-224, "Illegal parameter value; ON[,bin[,every]] | OFF");
    }
  } else if (head == "MEAS:STRE?") {
    Serial.printf("%d,%d,%d\n", stream_on ? 1 : 0, stream_bin, stream_every);
  } else if (head == "MEAS:ALL:LAST?") {
    // the latest analysed frame, without waiting for a new one: the fastest readout
    int bin = arg.length() ? arg.toInt() : 4;
    if (bin < 1) bin = 1;
    print_measurement("");
    for (int c = 0; c < NCH; c++) print_profile(prof.x[c], prof.width, bin);
    for (int c = 0; c < NCH; c++) print_profile(prof.y[c], prof.height, bin);
  } else if (head == "MEAS:ALL?") {
    // MEAS:ALL? [<bin>]: measurement ; x profiles R,G,B,S ; y profiles R,G,B,S (fresh frame)
    int bin = arg.length() ? arg.toInt() : 4;
    if (bin < 1) bin = 1;
    if (!camera_ok || !wait_fresh_frame(frame_no)) {
      push_error(-240, "Hardware error; no frame");
      Serial.println("");
    } else {
      print_measurement("");
      for (int c = 0; c < NCH; c++) print_profile(prof.x[c], prof.width, bin);
      for (int c = 0; c < NCH; c++) print_profile(prof.y[c], prof.height, bin);
    }
  } else if (head == "SENS:EXP") {
    int v = arg.toInt();
    if (v < 1 || v > 1200) {
      push_error(-222, "Data out of range; exposure 1..1200");
    } else {
      cfg.exposure = v;
      cfg.auto_range = false;
      apply_exposure();
    }
  } else if (head == "SENS:EXP?") {
    Serial.println(cfg.exposure);
  } else if (head == "SENS:GAIN") {
    int v = arg.toInt();
    if (v < 0 || v > 30 || !arg.length()) {
      push_error(-222, "Data out of range; gain 0..30");
    } else {
      cfg.gain = v;
      cfg.auto_range = false;
      apply_exposure();
    }
  } else if (head == "SENS:GAIN?") {
    Serial.println(cfg.gain);
  } else if (head == "SENS:RANG:AUTO") {
    if (uarg == "ON" || uarg == "1") cfg.auto_range = true;
    else if (uarg == "OFF" || uarg == "0") cfg.auto_range = false;
    else push_error(-224, "Illegal parameter value");
  } else if (head == "SENS:RANG:AUTO?") {
    Serial.println(cfg.auto_range ? "1" : "0");
  } else if (head == "SENS:BACK") {
    if (uarg.startsWith("EDGE")) cfg.bg = BG_EDGE;
    else if (uarg.startsWith("DARK")) cfg.bg = BG_DARK;
    else if (uarg.startsWith("NONE")) cfg.bg = BG_NONE;
    else push_error(-224, "Illegal parameter value");
  } else if (head == "SENS:BACK?") {
    Serial.println(cfg.bg == BG_EDGE ? "EDGE" : cfg.bg == BG_DARK ? "DARK" : "NONE");
  } else if (head == "SENS:BACK:DARK:ACQ") {
    int frames = arg.length() ? arg.toInt() : 8;
    if (frames < 1 || frames > 64) {
      push_error(-222, "Data out of range; 1..64 frames");
    } else if (!acquire_dark(frames)) {
      push_error(-240, "Hardware error; dark frame");
    }
  } else if (head == "SENS:EXP:MAX") {
    int v = arg.toInt();
    if (v < 1 || v > 1200) {
      push_error(-222, "Data out of range; 1..1200 lines");
    } else {
      cfg.exposure_max = v;
      if (cfg.exposure > v) {
        cfg.exposure = v;
        apply_exposure();
      }
    }
  } else if (head == "SENS:EXP:MAX?") {
    Serial.println(cfg.exposure_max);
  } else if (head == "SYST:BAUD") {
    // switch the link speed; the board always starts at 115200, so a lost setting is
    // recovered by re-plugging. The reply goes out at the old rate, then the UART changes.
    long v = arg.toInt();
    if (v != 115200 && v != 230400 && v != 460800 && v != 921600) {
      push_error(-224, "Illegal parameter value; 115200|230400|460800|921600");
    } else {
      Serial.printf("%ld\n", v);
      Serial.flush();
      delay(20);
      Serial.updateBaudRate(v);
      baud_now = v;
    }
  } else if (head == "SYST:BAUD?") {
    Serial.println(baud_now);
  } else if (head == "SYST:XCLK") {
    int mhz = arg.toInt();
    if (mhz < 6 || mhz > 30) {
      push_error(-222, "Data out of range; 6..30 MHz");
    } else {  // a new pixel clock needs the camera restarted
      xclk_hz = mhz * 1000000;
      esp_camera_deinit();
      camera_ok = camera_begin();
    }
  } else if (head == "SYST:XCLK?") {
    Serial.println(xclk_hz / 1000000);
  } else if (head == "SENS:BIN") {
    int v = arg.toInt();
    if (v != 1 && v != 2 && v != 4 && v != 8) {
      push_error(-224, "Illegal parameter value; bin 1|2|4|8");
    } else {
      cfg.bin = v;
      settle_skip = 1;
    }
  } else if (head == "SENS:BIN?") {
    Serial.println(cfg.bin);
  } else if (head == "SENS:THR") {
    float v = arg.toFloat();
    if (v <= 0 || v >= 1) push_error(-222, "Data out of range; threshold 0..1");
    else cfg.thr_frac = v;
  } else if (head == "SENS:THR?") {
    Serial.println(cfg.thr_frac, 3);
  } else if (head == "SENS:RES") {
    framesize_t s = uarg == "QQVGA" ? FRAMESIZE_QQVGA : uarg == "QVGA" ? FRAMESIZE_QVGA
                  : uarg == "CIF" ? FRAMESIZE_CIF : uarg == "VGA" ? FRAMESIZE_VGA : FRAMESIZE_INVALID;
    if (s == FRAMESIZE_INVALID) {
      push_error(-224, "Illegal parameter value; QQVGA|QVGA|CIF|VGA");
    } else {
      // a new frame size needs new frame buffers; re-initialising the driver at run time
      // crashed, so the size is stored and the board restarts with it (~3 s)
      if (s != cfg.size) {
        prefs.putInt("size", int(s));
        Serial.flush();
        delay(50);
        ESP.restart();
      }
    }
  } else if (head == "SENS:RES?") {
    Serial.println(cfg.size == FRAMESIZE_QQVGA ? "QQVGA" : cfg.size == FRAMESIZE_QVGA ? "QVGA"
                   : cfg.size == FRAMESIZE_CIF ? "CIF" : "VGA");
  } else {
    push_error(-113, "Undefined header; " + line);
  }
}

// ---------------------------------------------------------------- main --
void setup() {
  pinMode(FLASH_LED_GPIO, OUTPUT);
  digitalWrite(FLASH_LED_GPIO, LOW);  // the flash LED would blind the sensor
  // the serial line carries SCPI replies only: silence the camera driver's log lines
  esp_log_level_set("*", ESP_LOG_NONE);
  esp_log_set_vprintf([](const char *, va_list) { return 0; });
  esp_rom_install_channel_putc(1, [](char) {});  // the camera driver also prints via the ROM
  Serial.setRxBufferSize(1024);
  // a large TX buffer: writing a reading returns at once and the UART drains while the
  // next frame is captured, instead of blocking the analysis loop
  Serial.setTxBufferSize(8192);
  Serial.begin(BAUD);
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
  snprintf(serial_no, sizeof(serial_no), "%02x%02x%02x", mac[3], mac[4], mac[5]);
  prefs.begin("cmc-sense", false);
  int size = prefs.getInt("size", int(FRAMESIZE_QVGA));
  if (size == FRAMESIZE_QQVGA || size == FRAMESIZE_QVGA || size == FRAMESIZE_CIF || size == FRAMESIZE_VGA) {
    cfg.size = framesize_t(size);
  }
  reset_luts();
  uint16_t vals[64];
  for (int ch = R; ch <= B; ch++) {
    const char *key = ch == R ? "lutR" : ch == G ? "lutG" : "lutB";
    size_t n = ch == G ? 64 : 32;
    if (prefs.getBytesLength(key) == sizeof(uint16_t) * n && prefs.getBytes(key, vals, sizeof(vals))) {
      set_lut(ch, vals);
    }
  }
  camera_ok = camera_begin();
}

static String rx;

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (rx.length()) handle(rx);
      rx = "";
    } else if (rx.length() < 512) {
      rx += c;
    }
  }
  if (camera_ok) {
    grab_and_analyse();
  } else {
    delay(20);
  }
}
