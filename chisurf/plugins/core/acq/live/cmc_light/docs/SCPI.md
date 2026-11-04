# cmc-light SCPI reference

3-laser ALEX (alternating laser excitation) source on an ESP8266 (Wemos D1 mini).
Firmware 2.0 (C++, `firmware/esp8266/cmc_light/`); the Python model
`cmc_light/instrument.py` + `cmc_light/seqcore.py` is the reference and answers
every command identically (checked by `tests/test_firmware_port.py` on the host and
`tests/hardware/test_conformance.py` on the board).

| channel | name  | output         | colour    | wavelength |
|---------|-------|----------------|-----------|------------|
| 1       | blue  | GPIO5 (D1)     | `#3a6bff` | 0 (unknown) |
| 2       | green | GPIO4 (D2)     | `#2fd05a` | 0 |
| 3       | red   | GPIO0 (D3)     | `#ff3b30` | 0 |
| sync    | –     | GPIO14 (D5)    | –         | – |

All outputs are TTL, active high, and driven low first thing at boot.

## Connecting

**USB serial**: 115200 8N1. **WiFi**: raw SCPI socket on TCP port **5025**
(LXI/SCPI-RAW), up to 3 clients, host name `cmc-light.local`, mDNS service
`_scpi-raw._tcp`. Both links use the same parser and the same protocol:

* one line per message, terminated by `\n` (`\r\n` accepted, empty lines ignored,
  lines over 1024 bytes are dropped);
* several commands may be joined with `;` — their replies come back in one line,
  joined with `;`;
* a reply line is sent only if at least one command in the line produced a reply;
* commands never reply with errors: read them with `SYSTem:ERRor?`.

```python
from cmc_light import LaserSource, find_instruments

find_instruments()                                   # [('/dev/cu.wchusbserial10', 'CMC,LIGHT-3,e3ba6c,2.0')]
src = LaserSource.open("/dev/cu.wchusbserial10")     # USB
src = LaserSource.open_tcp("cmc-light.local")       # WiFi (port 5025)
src = LaserSource.simulated()                        # no hardware
```

`LaserSource` checks `SYSTem:ERRor?` after every command and raises `ScpiError`.

Quick test without Python: `nc cmc-light.local 5025`, then type `*IDN?`.

### WiFi setup

Without a stored network the instrument opens its own access point
**`cmc-light`**, password **`laser1234`**, address `192.168.4.1`. To join a
network instead (settings are stored in flash and survive `*RST`, power cycles and
re-flashing):

```
SYSTem:COMMunicate:WLAN:SSID "labnet"
SYSTem:COMMunicate:WLAN:PASSword "secret123"
SYSTem:COMMunicate:WLAN:APPLy
SYSTem:COMMunicate:WLAN:MODE?        -> STA
SYSTem:COMMunicate:WLAN:ADDRess?     -> 192.168.1.57   (0.0.0.0 while connecting)
```

If the network is not joined within 20 s the instrument falls back to its access
point (`MODE?` → `AP`) and retries the stored network every 5 minutes while no
client is connected to the access point. `SSID ""` + `APPLy` returns to access-point
mode. In Python: `src.set_wlan("labnet", "secret123"); src.apply_wlan()`.

## Syntax

IEEE 488.2 / SCPI: keywords are case-insensitive and accept the short form
(capital letters) or the long form: `SOUR`, `SOURCE`, `sour` and `Source` are equal;
intermediate spellings (`SOURC`) are not. A leading `:` is allowed.
`SOURce` and `SYSTem` take an optional channel suffix (`SOURce2`), default 1; only
commands that address a channel check it (-222 `channel N` if out of range).
Nodes in `[ ]` are optional. `?` makes a query. Numbers may be written as
`500`, `5e2`, `0.5`, `1_000`; integer parameters are truncated (`777.9` → 777).
Booleans: `ON|OFF|1|0`. Strings: `"text"` or `'text'` (a doubled quote inside is a
literal quote) or bare text.

## Operating modes

* **Computer-driven** (`SOURce:AM:SOURce CW`, default). `SOURce<n>:AM:STATe ON|OFF`
  switches a laser immediately. Relative power < 1 is realised by pulse-width
  modulation with period `SOURce:PWM:PERiod`, played by the timer interrupt.
* **Programmed** (`SOURce:AM:SOURce SEQ`, or simply `SEQuence:STARt`). The instrument
  plays the uploaded step sequence autonomously with microsecond timing; lasers
  follow the sequence (and their emission state and power), the sync output marks
  the start of every period and/or follows the sync bit of the steps. `ABORt` stops; after `SEQuence:CYCLes` periods it
  stops by itself.

A *sequence* is a list of steps `(duration_us, channel_mask)`; bit 0 = channel 1,
bit 3 (value 8) = sync output. One pass = one *period*. During a step, channel *k* emits if its mask bit is set,
`SOURce<k>:AM:STATe` is ON and its power > 0; power < 1 is PWM inside the window,
with sub-periods of about `PWM:PERiod` and pulses no shorter than `PWM:MINimum`
(shorter pulses are rounded up or dropped; `POWer:DUTY?` reports the result).
While a sequence is running, any change of emission state, power or PWM settings
recompiles and restarts it; editing the step list stops it.

### Relative power in sequences: PWM or cycle dithering

`SOURce:PWM:MODE PWM|CYCLes` selects how a power below 1 is made in programmed mode
(computer-driven mode always uses PWM):

* **PWM** (default): every window is cut into PWM sub-periods and the laser is on for
  the first fraction *p* of each. Short gapless windows (e.g. 3 × 35 µs ALEX with a
  1 ms PWM period) therefore contain dark time.
* **CYCLes** (cycle dithering): windows are never cut. A channel with 0 < *p* < 1 is
  fully lit in `count = round(M·p)` of `M` sequence periods and dark in the others;
  lit periods are spread evenly (period *c*, 0-based, is lit iff
  `floor((c+1)·count/M) > floor(c·count/M)`). Channels at power 1 (or off) behave as
  in PWM mode. The instrument plays a program of `M` sequence periods, `M` being the
  largest of 100, 50, 20, 10 that fits the edge limit (1024 edges) and the dense-edge
  rule; otherwise the setting is rejected with the usual -221 edge error. If no channel
  needs dithering, `M` = 1.

  Trade-off: no dark time inside a window, but the power is only right on average over
  `M` periods (e.g. 100 × 105 µs = 10.5 ms for gapless 3 × 35 µs ALEX), and its
  resolution is 1/`M` (`SOURce<n>:POWer:DUTY?` reports `count/M`, e.g. 0.123 → `0.1200`
  with `M` = 100). The sync output (pulse and sync steps) still repeats in every sequence period;
  `SEQuence:PERiod?`, `SEQuence:TIMing?` (period) and `SEQuence:COUNt?`/`CYCLes` stay
  in sequence periods (`SEQuence:CYCLes n` plays at least *n*: the next multiple of `M`).

### Sync output (GPIO14 / D5)

The sync output is a fourth, programmable line in programmed mode (in CW mode it
stays low). It is high whenever

* the period started less than `SEQuence:SYNC:WIDTh` µs ago (clipped to period − 1), or
* the current step has mask bit *N* set, *N* = number of lasers (3 → bit 3, value 8).

Both parts are ORed; overlapping or touching high intervals merge into one pulse (no
glitch between two sync steps, or between the last step of a period and the WIDTh pulse
of the next). A sync output that is high during the whole period is a constant level
without edges. Lasers ignore bit *N*. The sync output is always active high, is never
power-modulated, and with cycle dithering (`M` > 1) the same pattern repeats in every
sequence period. Its edges count toward the 1024-edge limit and the dense-edge rule.
An instrument without a sync output accepts masks 0–7 only.

```
SEQuence:CLEar
SEQuence:STEP:APPend 1000,9      blue + sync
SEQuence:STEP:APPend 500,0       dark
SEQuence:STEP:APPend 1000,14     green + red + sync
SEQuence:STEP:APPend 200,8       sync only (camera exposure, ...)
SEQuence:STEP:LIST?              -> 1000,9;500,0;1000,14;200,8
SEQuence:SYNC:WIDTh 100          pulse 0..100 merges into step 1: sync high 0..1000, 1500..2700
SEQuence:STARt
SEQuence:STEP:APPend 100,16      -> SYSTem:ERRor? -222,"Data out of range; 16"
```

## Command reference

### Common commands

| command | reply | notes |
|---|---|---|
| `*IDN?` | `CMC,LIGHT-3,<chip id hex>,2.0` | simulator: `CMC,LIGHT-3-SIM,SIM,2.0` |
| `*RST` | – | defaults below; keeps WLAN settings and the error queue |
| `*CLS` | – | clears the error queue |
| `*OPC?` | `1` | handy as a sync point |
| `*TST?` | `0` | |

Defaults after `*RST`: all emission OFF, power 1.0, source CW, PWM period 1000 µs,
minimum pulse 20 µs, power mode PWM, sequence `SEQ:ALEX 1000` (3 steps), cycles 0, sync width 0,
not running.

### SYSTem

| command | parameters / reply |
|---|---|
| `SYSTem:ERRor[:NEXT]?` | oldest error, `<code>,"<message>[; <detail>]"`, or `0,"No error"` |
| `SYSTem:VERSion?` | `1999.0` (SCPI version) |
| `SYSTem:CHANnels?` | `3` |
| `SYSTem<n>:INFormation:MODel?` | `blue`, `green`, `red` |
| `SYSTem<n>:INFormation:WAVelength?` | nm, `0` = unknown |
| `SYSTem<n>:INFormation:COLor?` | display colour `#rrggbb` |
| `SYSTem:COMMunicate:WLAN:SSID "<name>"` | network to join, 0–32 bytes; query returns `"<name>"` (quotes doubled) |
| `SYSTem:COMMunicate:WLAN:PASSword "<secret>"` | empty or 8–63 characters; write-only, query returns `"***"` if set, else `""` |
| `SYSTem:COMMunicate:WLAN:APPLy` | reconnect with the stored settings (after the reply line is sent; drops TCP clients) |
| `SYSTem:COMMunicate:WLAN:ADDRess?` | current IPv4 address (simulator: `0.0.0.0`) |
| `SYSTem:COMMunicate:WLAN:MODE?` | `STA` (joining/joined a network) or `AP` (own access point); simulator: `AP` |

### SOURce (lasers)

| command | parameters | reply |
|---|---|---|
| `SOURce<n>:AM:STATe ON\|OFF` | emission enable of channel n | query: `ON`/`OFF` |
| `SOURce:AM:SOURce CW\|CWP\|SEQ\|SEQuence` | CW (and CWP) = computer-driven, stops a running sequence; SEQ = lasers follow the sequence | query: `CW`/`SEQ` |
| `SOURce<n>:POWer[:LEVel][:IMMediate][:AMPLitude] <p>` | relative power 0.0–1.0 | query: `%.4f`, e.g. `0.4000` |
| `SOURce<n>:POWer:DUTY?` | – | achieved relative power after timing quantisation, `%.4f`, `0.0000` when emission is off (can exceed 1 when the minimum pulse is longer than a PWM sub-period) |
| `SOURce<n>:POWer:LIMit:LOW?` | – | `0.0000` |
| `SOURce<n>:POWer:LIMit:HIGH?`, `SOURce<n>:POWer:NOMinal?` | – | `1.0000` |
| `SOURce:PWM:PERiod <us>` | 20–1000000 µs, shared by all channels | query: integer |
| `SOURce:PWM:MINimum <us>` | shortest pulse or gap, 1–100000 µs | query: integer |
| `SOURce:PWM:MODE PWM\|CYCLes` | power < 1 in programmed mode: PWM inside the windows, or cycle dithering (solid windows lit in `round(M·p)` of `M` periods, see above); invalid value -224; CW mode always uses PWM | query: `PWM`/`CYCL` |

### SEQuence (programmed mode)

| command | parameters | reply / effect |
|---|---|---|
| `SEQuence:ALEX <on_us>[,<gap_us>]` | on 1–60000000, gap 0–60000000 | steps = ch1, gap, ch2, gap, ch3, gap (no gap steps if 0); stops a running sequence |
| `SEQuence:CLEar` | – | empty step list; stops |
| `SEQuence:STEP:APPend <dur_us>,<mask>` | dur 1–60000000, mask 0–15 (bits 0–2 lasers, bit 3 sync output; 0–7 without a sync output; else -222) | adds a step (max 512 steps); stops |
| `SEQuence:STEP:COUNt?` | – | number of steps |
| `SEQuence:STEP:LIST?` | – | `dur,mask;dur,mask;...` masks as stored, incl. the sync bit (empty line if none) |
| `SEQuence:PERiod?` | – | period in µs (sum of durations) |
| `SEQuence:CYCLes <n>` | 0–1073741824, 0 = forever | periods to play at the next start (cycle dithering with `M` > 1: at least *n*, rounded up to a multiple of `M`); query: integer |
| `SEQuence:SYNC:WIDTh <us>` | 0–60000000 (0 = off, clipped to period − 1) | sync output high at the start of each period, ORed with the sync steps (mask bit 3); -221 `no sync output` without one; query: integer |
| `SENSe:POWer?` | - | the power diode in the laser head: the sensor's lux number (arbitrary units for laser light - the sensor is eye-weighted), total of what is emitting; `nan` without a sensor |
| `SENSe:POWer:RAW?` | - | sensor counts |
| `SENSe:POWer:PRESent?` | - | 1 when a sensor answers on the I2C bus |
| `SENSe:POWer:AGE?` | - | age of the reading in ms |
| `SENSe:POWer:MODE <HIGH\|HIGH2\|LOW>` | - | BH1750 resolution; query: the mode |
| `SENSe:POWer:GAIN <31..254>` | MTreg | integration time and sensitivity; query: the value |
| `SYSTem:I2C:SCAN?` | - | addresses found, e.g. `0x23` |
| `SYSTem:I2C:PINS <sda>,<scl>` | GPIO 0..16 | the bus pins, stored; query: `sda,scl` |
| `SOURce:EXCLusive <ON\|OFF>` | - | one laser at a time (for measuring one laser's power); off by default |
| `SEQuence:STARt` | – | source := SEQ, start from t = 0; -221 if the step list is empty |
| `SEQuence:ABORt`, `ABORt` | – | stop; in SEQ mode all outputs off |
| `SEQuence:STATe ON\|OFF` | – | same as STARt / ABORt |
| `SEQuence:STATe?` | – | `RUN` or `IDLE` (a sequence that finished its cycles, or that has no edges at all, reads `IDLE`) |
| `SEQuence:COUNt?` | – | completed periods since the last (re)start (device; with cycle dithering in steps of `M`); simulator: from the wall clock |
| `SEQuence:TIMing?` | – | `late_max_us,edges,period_us`: largest delay of an edge behind schedule since the last start (device-measured; simulator 0), edges per period of the current program, its period (the sequence period; with cycle dithering the edges are those of the whole `M`-period program) |

Queries of set-only commands and sets of query-only commands follow the reference
model exactly (e.g. `*IDN` without `?` still replies); rely on the documented forms.

## Errors

| code | message | typical cause |
|---|---|---|
| -109 | Missing parameter | `SOUR1:POW` without value |
| -113 | Undefined header | unknown keyword, bad suffix (`SOUR1:POW5`), empty node; detail = header |
| -221 | Settings conflict | `sequence is empty`; `sequence needs more than 1024 edges: lengthen the PWM period or shorten the sequence`; `too many steps (max 512)`; `no sync output` |
| -222 | Data out of range | value outside its range (detail = parameter), `channel N`, `longer than 32 bytes`, `password needs 8 to 63 characters` |
| -224 | Illegal parameter value | not a number / not ON/OFF / unknown source / unterminated string; detail = parameter |
| -350 | Queue overflow | more than 10 errors queued: the 10th entry is replaced |

A command that fails is not applied, except that a failed recompile (-221 edge
limit) leaves the new setting in place with all outputs off, exactly like the
reference model; fix the setting (e.g. a longer `PWM:PERiod`) to recover.

Limits: 1024 edges per period (all channels + sync together; an edge = one instant
at which any output changes), 512 steps.

## Examples

Alternating excitation, 500 µs per laser with 50 µs dark gaps, blue at 60 %:

```
*RST
SOURce1:POWer 0.6
SOURce1:AM:STATe ON;SOURce2:AM:STATe ON;SOURce3:AM:STATe ON
SEQuence:ALEX 500,50
SEQuence:SYNC:WIDTh 100
SEQuence:STARt
SEQuence:STATe?;SEQuence:COUNt?;SEQuence:TIMing?     -> RUN;1234;0,7,1650
ABORt
```

```python
from cmc_light import LaserSource

with LaserSource.open_tcp("cmc-light.local") as src:   # all off on exit
    src.set_power(1, 0.6)
    for ch in (1, 2, 3):
        src.set_emission(ch, True)
    src.load_alex(on_us=500, gap_us=50)
    src.set_sync_width(100)
    src.set_cycles(10000)             # 16.5 s, then stops by itself
    src.start()
    while src.running():
        print(src.cycles_done(), src.timing())
```

Custom sequence (blue, then green + red together, then dark), finite:

```python
src.load_steps([(2000, 0b001), (2000, 0b110), (1000, 0)])
src.set_cycles(100)
src.start()
```

Computer-driven, green at 40 % via 500 µs PWM:

```python
src.set_source("CW")
src.set_pwm_period(500)
src.set_power(2, 0.4)
src.set_emission(2, True)
print(src.duty(2))                    # 0.4
src.set_emission(2, False)
```

Preview the exact on-intervals without hardware:
`LaserSource.preview(steps, enabled, powers, pwm_period_us, min_pulse_us)`.

## Timing (firmware 2.0, measured on the board)

Edges are played from the timer1 interrupt (NMI) with all outputs written in one
register access; the timer fires 12 µs early and the rest is busy-waited on the
microsecond clock; the schedule is absolute (no drift). Measured with WiFi on
(access point, with and without an associated client), 10 queries/s over serial
and 10 queries/s over TCP (see `tests/hardware/timing.py`):

* ALEX 3 × 1000 µs + 100 µs gaps with 100 µs sync (period 3300 µs, 7 edges):
  303.0 cycles/s (expected 303.03), `late_max` ≤ 3 µs.
* CW PWM, power 0.4, period 500 µs: 2000.0 cycles/s, `late_max` ≤ 3 µs.
* Edges 30 µs apart play with `late_max` ≤ 4 µs; 15–20 µs apart ≤ 12 µs; below
  ~12 µs the interrupt cannot keep up and is throttled (1 ms stalls).

`late_max` is measured by the firmware itself (µs clock at the moment of the GPIO
write), not by an external instrument.

## Firmware build and flash

```sh
make fw-build          # scripts/fw_build.sh: installs the ESP8266 core on first use,
                       # FQBN esp8266:esp8266:d1_mini:xtal=160,eesz=4M,...
make fw-flash          # scripts/fw_flash.sh, PORT=/dev/cu.xxx to override auto-detection
make fw-conformance    # board vs Python reference (lasers switch!)
make fw-timing         # timing measurements (lasers switch!)
```

Compile-time options (`EXTRA_FLAGS="-D..." scripts/fw_build.sh`): `PLAYER_NMI=0`
(normal instead of NMI timer interrupt), `PLAYER_GUARD_US=<us>`, `PLAYER_DIAG=1`
(serial-only `#DIAG` line with interrupt wake-up statistics and free heap),
`STA_TIMEOUT_MS=<ms>` / `STA_RETRY_MS=<ms>` (WiFi fallback and retry intervals, default
20000 / 300000).

While the board is in its bootloader (during flashing) the outputs float and
GPIO0 (red) is held low: lasers on D1/D2 may light up. Disable the laser drivers
before flashing, or give their TTL inputs pull-down resistors.

## Timing limits (measured on the board)

| Control path | Limit |
|---|---|
| Programmed sequence (MCU plays) | edges to ~1 µs, `late_max` 0–15 µs; PWM period ≥ 20 µs |
| Dense edges | edges < 13 µs apart only in bursts of ≤ 3 ms; otherwise `-221 "edges closer than 13 us ..."` |
| Computer-driven over USB serial | one command incl. error check 8–18 ms → GUI paces live updates to ≥ 20 ms |
| Computer-driven over WiFi (TCP 5025) | GUI paces live updates to ≥ 100 ms (estimate, not yet measured) |

Continuous PWM with all three lasers (4 s each): 50 µs period clean for any powers;
40/30/25 µs clean with equal powers, rejected with unequal powers; 20 µs rejected.
A command whose new settings cannot be played is **rolled back**: the error is
queued and the previous, working settings stay active (`Instrument._snapshot` /
`Instrument::save`).
