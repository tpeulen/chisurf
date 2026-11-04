// cmc-light firmware: 3-laser ALEX excitation source, SCPI over USB serial
// and a raw SCPI socket (TCP 5025) over WiFi.
//
// Board: Wemos D1 mini (ESP8266), FQBN esp8266:esp8266:d1_mini:xtal=160
//   ch1 blue  = GPIO5 (D1), ch2 green = GPIO4 (D2), ch3 red = GPIO0 (D3)
//   sync      = GPIO14 (D5); all TTL, active high
//
// The SCPI model (instrument.cpp) and sequence compiler (seqcore.cpp) are
// ports of cmc_light/instrument.py and seqcore.py; the edge player
// (player.cpp) runs in the timer1 interrupt. See docs/SCPI.md.
#include <EEPROM.h>
#include <Wire.h>
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>

#include "bh1750.h"
#include "instrument.h"
#include "player.h"

namespace {

const int GPIO_BLUE = 5, GPIO_GREEN = 4, GPIO_RED = 0, GPIO_SYNC = 14;
const uint32_t ALL_OUTPUTS =
    (1UL << GPIO_BLUE) | (1UL << GPIO_GREEN) | (1UL << GPIO_RED) | (1UL << GPIO_SYNC);

const Channel CHANNELS[] = {
    {"blue", GPIO_BLUE, 0, "#3a6bff"},
    {"green", GPIO_GREEN, 0, "#2fd05a"},
    {"red", GPIO_RED, 0, "#ff3b30"},
};

const char* HOSTNAME = "cmc-light";
const char* AP_SSID = "cmc-light";
const char* AP_PASSWORD = "laser1234";
const uint16_t SCPI_PORT = 5025;
const size_t MAX_LINE = 1024;
const int MAX_CLIENTS = 3;
#ifndef STA_TIMEOUT_MS
#define STA_TIMEOUT_MS 20000UL  // give up joining the stored network, open the AP
#endif
#ifndef STA_RETRY_MS
#define STA_RETRY_MS 300000UL  // retry the stored network from AP mode (no AP clients)
#endif

// ------------------------------------------------------------------ settings
const uint32_t CFG_MAGIC = 0xC1A5E202;  // bumped: the config gained the I2C pins
struct Config {
  uint32_t magic;
  char ssid[33];
  char password[64];
  int8_t i2c_sda;  // the power monitor's bus; -1 = the default pins
  int8_t i2c_scl;
};

Config cfg;

void cfg_load() {
  EEPROM.begin(sizeof(Config));
  EEPROM.get(0, cfg);
  if (cfg.magic != CFG_MAGIC) {
    memset(&cfg, 0, sizeof cfg);
    cfg.magic = CFG_MAGIC;
    cfg.i2c_sda = cfg.i2c_scl = -1;
  }
  cfg.ssid[32] = 0;
  cfg.password[63] = 0;
}

void cfg_save() {
  EEPROM.put(0, cfg);
  EEPROM.commit();
}

// ------------------------------------------------------------------ WiFi
bool ap_mode = false;
bool apply_pending = false;
uint32_t sta_started = 0, ap_started = 0;

void start_ap() {
  WiFi.disconnect();
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  ap_mode = true;
  ap_started = millis();
}

void start_sta() {
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_STA);
  WiFi.hostname(HOSTNAME);
  WiFi.begin(cfg.ssid, cfg.password);
  ap_mode = false;
  sta_started = millis();
}

void wifi_apply() {
  if (cfg.ssid[0])
    start_sta();
  else
    start_ap();
}

void wifi_service() {
  if (apply_pending) {
    apply_pending = false;
    wifi_apply();
  }
  uint32_t now = millis();
  if (!ap_mode && WiFi.status() != WL_CONNECTED && now - sta_started > STA_TIMEOUT_MS) {
    start_ap();  // stored network not reachable
  } else if (ap_mode && cfg.ssid[0] && now - ap_started > STA_RETRY_MS &&
             WiFi.softAPgetStationNum() == 0) {
    start_sta();
  }
  MDNS.update();
}

// ------------------------------------------------------------------ power monitor
// The instrument's own light sensor (M5Stack DLight, BH1750FVI) on I2C: it sits in the
// laser head and reads the emitted power, averaged over its integration time.
//   D7 = GPIO13 (SDA), D8 = GPIO15 (SCL) by default. GPIO15 must be LOW while the board
//   boots: a module with pull-ups on the bus can stop it booting, and SYSTem:I2C:PINS
//   then moves the bus to other pins (stored, so it survives a restart).
int i2c_sda = 13, i2c_scl = 15;
BH1750 light;
std::string i2c_addresses;

static std::string fmt_int(int v) {
  char buf[16];
  snprintf(buf, sizeof buf, "%d", v);
  return buf;
}

static std::string i2c_scan() {
  std::string out;
  for (uint8_t a = 8; a < 120; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      char buf[8];
      snprintf(buf, sizeof buf, "0x%02X", a);
      if (!out.empty()) out += ",";
      out += buf;
    }
  }
  return out;
}

// ------------------------------------------------------------------ platform
class EspHardware : public Hardware {
 public:
  void static_levels(uint32_t set_mask, uint32_t clr_mask) override {
    player::write_static(set_mask, clr_mask);
  }
  void play(const seqcore::Program& prog, uint32_t cycles) override { player::play(prog, cycles); }
  void stop() override { player::stop(); }
  void status(bool& running, uint32_t& done, uint32_t& late) override {
    running = player::running();
    done = player::cycles_done();
    late = player::late_max_us();
  }
  void wlan_store(const std::string& ssid, const std::string& password) override {
    strncpy(cfg.ssid, ssid.c_str(), sizeof cfg.ssid - 1);
    cfg.ssid[sizeof cfg.ssid - 1] = 0;
    strncpy(cfg.password, password.c_str(), sizeof cfg.password - 1);
    cfg.password[sizeof cfg.password - 1] = 0;
    cfg_save();
  }
  void wlan_apply() override { apply_pending = true; }  // after the replies are out
  std::string wlan_address() override {
    IPAddress ip = ap_mode ? WiFi.softAPIP() : WiFi.localIP();
    return ip.isSet() ? ip.toString().c_str() : "0.0.0.0";
  }
  std::string wlan_mode() override { return ap_mode ? "AP" : "STA"; }

  // --- power monitor: BH1750 light sensor on the instrument's I2C bus ---
  bool monitor(MonitorState& out) override {
    out.present = light.present();
    out.simulated = false;
    out.lux = light.lux();
    out.raw = light.raw();
    out.age_ms = light.age_ms();
    out.saturated = light.saturated();
    out.mode = light.mode() == BH1750::CONT_HIGH2 ? "HIGH2"
             : light.mode() == BH1750::CONT_LOW ? "LOW" : "HIGH";
    out.gain = light.mtreg();
    out.pins = std::string(fmt_int(i2c_sda)) + "," + fmt_int(i2c_scl);
    out.addresses = i2c_addresses;
    return true;
  }

  bool monitor_set(const std::string& mode, int gain) override {
    if (!light.present()) return false;
    light.set_mode(mode == "HIGH2" ? BH1750::CONT_HIGH2
                   : mode == "LOW" ? BH1750::CONT_LOW : BH1750::CONT_HIGH);
    return light.set_mtreg((uint8_t)gain);
  }

  bool i2c_configure(int sda, int scl) override {
    i2c_sda = sda;
    i2c_scl = scl;
    bool ok = light.begin(sda, scl);
    i2c_addresses = i2c_scan();
    if (ok) {  // remember pins that worked, so a restart finds the sensor again
      cfg.i2c_sda = (int8_t)sda;
      cfg.i2c_scl = (int8_t)scl;
      cfg_save();
    }
    return ok;
  }
};

EspHardware hw;
Instrument* inst = nullptr;

// ------------------------------------------------------------------ line I/O
struct LineBuffer {
  std::string buf;
  bool overflow = false;

  // feed one byte; returns true when a complete non-empty line is in `line`
  bool feed(char c, std::string& line) {
    if (c == '\n' || c == '\r') {
      bool ok = !overflow && !buf.empty();
      if (ok) line.swap(buf);
      buf.clear();
      overflow = false;
      return ok;
    }
    if (buf.size() >= MAX_LINE)
      overflow = true;  // drop the whole line
    else
      buf += c;
    return false;
  }
};

LineBuffer serial_in;
WiFiServer server(SCPI_PORT);
WiFiClient clients[MAX_CLIENTS];
LineBuffer client_in[MAX_CLIENTS];
std::string line, reply;

void service_serial() {
  int budget = 512;
  while (Serial.available() && budget--) {
    if (serial_in.feed((char)Serial.read(), line)) {
#if PLAYER_DIAG
      if (line == "#DIAG") {
        char buf[256];
        player::diag(buf, sizeof buf);
        Serial.println(buf);
        continue;
      }
#endif
      if (inst->handle(line, reply)) {
        Serial.write(reply.data(), reply.size());
        Serial.write('\n');
      }
    }
  }
}

void service_tcp() {
  if (server.hasClient()) {
    WiFiClient c = server.accept();
    int slot = -1;
    for (int i = 0; i < MAX_CLIENTS; i++)
      if (!clients[i].connected()) slot = i;
    if (slot < 0) {
      c.stop();
    } else {
      clients[slot] = c;
      clients[slot].setNoDelay(true);
      client_in[slot] = LineBuffer();
    }
  }
  for (int i = 0; i < MAX_CLIENTS; i++) {
    WiFiClient& c = clients[i];
    int budget = 512;
    while (c.available() && budget--) {
      if (client_in[i].feed((char)c.read(), line)) {
        if (inst->handle(line, reply)) {
          reply += '\n';
          c.write(reply.data(), reply.size());
        }
      }
    }
  }
}

}  // namespace

void seqcore_idle_hook() { yield(); }

// runs before setup(), as early as the core allows: lasers off
void preinit() {
  GPOC = ALL_OUTPUTS;
  GPES = ALL_OUTPUTS;
}

void setup() {
  for (int g : {GPIO_BLUE, GPIO_GREEN, GPIO_RED, GPIO_SYNC}) {
    digitalWrite(g, LOW);
    pinMode(g, OUTPUT);
    digitalWrite(g, LOW);
  }
  player::begin(ALL_OUTPUTS);
  Serial.setRxBufferSize(1024);
  Serial.begin(115200);

  char serial[16];
  snprintf(serial, sizeof serial, "%06x", ESP.getChipId());
  static Instrument instrument(&hw, CHANNELS, 3, serial, true, GPIO_SYNC, "LIGHT-3");
  inst = &instrument;

  cfg_load();
  // find the power monitor: the stored pins first, then the pairs the sensor is usually
  // wired to. D8 (GPIO15) must be low while the board boots, so D7 + D6 is the safe pair.
  int candidates[][2] = {{cfg.i2c_sda, cfg.i2c_scl}, {13, 12}, {13, 15}, {12, 13}};
  for (auto& pins : candidates) {
    if (pins[0] < 0 || pins[1] < 0 || pins[0] == pins[1]) continue;
    i2c_sda = pins[0];
    i2c_scl = pins[1];
    if (light.begin(i2c_sda, i2c_scl)) break;
  }
  i2c_addresses = i2c_scan();
  if (light.present() && (cfg.i2c_sda != i2c_sda || cfg.i2c_scl != i2c_scl)) {
    cfg.i2c_sda = (int8_t)i2c_sda;
    cfg.i2c_scl = (int8_t)i2c_scl;
    cfg_save();
  }
  inst->set_wlan(cfg.ssid, cfg.password);
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  wifi_apply();
  server.begin();
  server.setNoDelay(true);
  if (MDNS.begin(HOSTNAME)) MDNS.addService("scpi-raw", "tcp", SCPI_PORT);
}

void loop() {
  service_serial();
  service_tcp();
  wifi_service();
  float lux;
  light.poll(lux);  // a new reading every integration time; never blocks
}
