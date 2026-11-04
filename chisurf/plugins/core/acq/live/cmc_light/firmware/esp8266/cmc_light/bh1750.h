// BH1750FVI ambient light sensor on I2C (M5Stack DLight unit), used here as the
// instrument's internal power monitor: it sits in the laser head and measures what
// the lasers put out, averaged over its integration time (~120 ms at high resolution),
// which is what makes it read a pulsed laser's average power.
//
// The chip needs no library: one opcode byte starts a measurement mode, and the result
// is two bytes. lux = raw / 1.2 * (69 / MTreg), halved again in high-resolution mode 2.
#pragma once

#include <Arduino.h>
#include <Wire.h>

class BH1750 {
 public:
  enum Mode { CONT_HIGH = 0x10, CONT_HIGH2 = 0x11, CONT_LOW = 0x13 };
  static const uint8_t ADDR_LOW = 0x23;   // ADDR pin low (the usual wiring)
  static const uint8_t ADDR_HIGH = 0x5C;  // ADDR pin high

  bool begin(int sda, int scl, uint32_t hz = 100000) {
    Wire.begin(sda, scl);
    Wire.setClock(hz);
    sda_ = sda;
    scl_ = scl;
    addr_ = 0;
    for (uint8_t a : {ADDR_LOW, ADDR_HIGH}) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) {
        addr_ = a;
        break;
      }
    }
    if (!addr_) return false;
    write(0x01);  // power on
    write(0x07);  // reset the data register
    set_mtreg(mtreg_);
    write(mode_);
    last_change_ms_ = millis();
    return true;
  }

  bool present() const { return addr_ != 0; }
  uint8_t address() const { return addr_; }
  int sda() const { return sda_; }
  int scl() const { return scl_; }
  Mode mode() const { return mode_; }
  uint8_t mtreg() const { return mtreg_; }

  void set_mode(Mode m) {
    mode_ = m;
    if (addr_) {
      write(m);
      last_change_ms_ = millis();
    }
  }

  // Measurement time register 31..254 (default 69): longer integration, more sensitivity.
  bool set_mtreg(uint8_t value) {
    if (value < 31 || value > 254) return false;
    mtreg_ = value;
    if (addr_) {
      write(0x40 | (value >> 5));         // high three bits
      write(0x60 | (value & 0x1F));       // low five bits
      write(mode_);                       // the mode has to be set again
      last_change_ms_ = millis();
    }
    return true;
  }

  // Integration time of the current mode, milliseconds.
  uint32_t integration_ms() const {
    uint32_t base = mode_ == CONT_LOW ? 24 : 180;  // worst case from the data sheet
    return base * mtreg_ / 69;
  }

  // Read when a new result can be ready; returns true when *lux* was updated.
  bool poll(float& lux) {
    if (!addr_) return false;
    uint32_t now = millis();
    if (now - last_read_ms_ < integration_ms() || now - last_change_ms_ < integration_ms()) {
      return false;
    }
    last_read_ms_ = now;
    if (Wire.requestFrom(addr_, uint8_t(2)) != 2) return false;
    uint16_t raw = (uint16_t(Wire.read()) << 8) | Wire.read();
    raw_ = raw;
    lux = float(raw) / 1.2f * (69.0f / float(mtreg_)) / (mode_ == CONT_HIGH2 ? 2.0f : 1.0f);
    lux_ = lux;
    valid_ = true;
    return true;
  }

  float lux() const { return lux_; }
  uint16_t raw() const { return raw_; }
  bool valid() const { return valid_; }
  uint32_t age_ms() const { return valid_ ? millis() - last_read_ms_ : 0; }
  bool saturated() const { return raw_ >= 0xFFF0; }

 private:
  void write(uint8_t opcode) {
    Wire.beginTransmission(addr_);
    Wire.write(opcode);
    Wire.endTransmission();
  }

  uint8_t addr_ = 0, mtreg_ = 69;
  int sda_ = -1, scl_ = -1;
  Mode mode_ = CONT_HIGH;
  float lux_ = 0.0f;
  uint16_t raw_ = 0;
  bool valid_ = false;
  uint32_t last_read_ms_ = 0, last_change_ms_ = 0;
};
