# cmc-sense: the ESP32-CAM as a light sensor

An AI-Thinker ESP32-CAM (OV2640) with the firmware in `firmware/esp32cam/cmc_sense`
is a quantitative light detector and beam profiler. It never sends images: every
frame is analysed on the chip, and the computer reads numbers over the USB serial
cable (ESP32-CAM-MB programmer, CH340).

Build and flash:

```
arduino-cli compile --fqbn esp32:esp32:esp32cam --output-dir build/esp32cam firmware/esp32cam/cmc_sense
python -m esptool --chip esp32 --port /dev/cu.wchusbserial1340 --baud 460800 \
    write-flash 0x0 build/esp32cam/cmc_sense.ino.merged.bin
```

## Link

The client searches USB-serial ports for `CMC,SENSE` boards and reconnects by itself
when one appears. The board starts at 115200 baud, 8N1; `SYST:BAUD 460800` switches the link and the
client (which tries both rates when connecting; a re-plug returns the board to 115200).
230400 does not work with the CH340 on macOS and 921600 is unreliable, so 460800 is the
fast rate. DTR/RTS must stay low (they reset the board). Data lines (`MEAS?`, `MEAS:ALL?`, `MEAS:PROF?`) end with `*HH`, the sum of all
bytes before `*` modulo 256 in hex; the Python client rejects and repeats a corrupted
reading.

## Commands

| Command | Reply / effect |
|---|---|
| `*IDN?` | `CMC,SENSE-CAM-OV2640,<serial>,1.0` |
| `*RST`, `*OPC?`, `SYST:ERR?` | as SCPI |
| `MEAS?` | one reading of a fresh frame (fields: `MEAS:FIEL?`) |
| `MEAS:ALL? [bin]` | reading, then x profiles R,G,B,S, then y profiles R,G,B,S (9 lines) |
| `MEAS:PROF? <R\|G\|B\|S>,<X\|Y>[,bin]` | one profile of the last frame |
| `MEAS:LAST?`, `MEAS:ALL:LAST? [bin]` | the latest analysed frame, without waiting for a new one |
| `MEAS:STREam ON[,bin[,every]] \| OFF` | push `#M...` readings after every analysed frame (and `#XR...`/`#YR...` profiles every n-th) |
| `SYST:BAUD <115200\|460800\|921600>` | link speed (the board restarts at 115200) |
| `SYST:XCLK <6..30>` | camera clock in MHz (default 24) |
| `SENS:EXP:MAX <1..1200>` | auto-ranging never exposes longer than this |
| `SENS:RANG:AUTO ON\|OFF` | auto-ranging of exposure x gain |
| `SENS:EXP <1..1200>` | exposure in sensor lines (~0.2 ms each; effective up to ~500), turns auto off |
| `SENS:GAIN <0..30>` | gain setting, turns auto off |
| `SENS:BACK EDGE\|DARK\|NONE` | background for sums and profiles |
| `SENS:BACK:DARK:ACQ [frames]` | average a dark frame (switch the light off first) |
| `SENS:BIN <1\|2\|4\|8>` | analyse every n-th pixel in x and y (sums stay per frame pixel) |
| `SENS:THR <0..1>` | spot threshold, fraction of the peak |
| `SENS:RES QQVGA\|QVGA\|CIF\|VGA` | frame size; stored, the board restarts (~3 s), which drops the stream, the 460800 link and the binning: wait on the open port and set them again |
| `CAL:LUT <R\|G\|B>,v0,...` | response table (32 values for R and B, 64 for G, 0..1023), stored |
| `CAL:LUT? <ch>`, `CAL:LUT:RES`, `CAL:LUT:STAT?` | read, reset, IDENTITY or CUSTOM |

A frame-size change is confirmed, not assumed: the client puts the link back to 115200,
sends `SENS:RES` and waits for the ROM boot banner (`ets `, `rst:0x`, ...). A lost
`SENS:RES` otherwise looks exactly like a board that restarted and went quiet, and the
client would wait for a reboot that never happened - the size silently stayed as it was.
The restart also clears everything set at run time (stream, link speed, binning, range),
so those are set again afterwards, before the stream is restarted.

**Never close the port to ride out a restart.** The USB-serial chip stays enumerated
while the board reboots, but closing the port toggles DTR and RTS, which drive IO0 and
EN through the auto-reset circuit: the board can come back up in the ROM bootloader,
where it is silent at every baud rate and no reconnect succeeds (it looks dead until it
is reset by hand). The client keeps the port open, sets it back to 115200 and waits for
the board to answer again (`Sensor.wait_restart`). A board that has gone silent anyway
is pulsed out of it with RTS while DTR stays low (`Sensor.hard_reset`, the same lines
esptool uses), which is what the GUI tries first when no reading has arrived for 8 s.

Before anything is asked of a board, the client sends `MEAS:STRE OFF` and then waits
until the link has been *quiet* for 0.4 s. Flushing the host's buffer is not enough:
the board answers queries between its stream lines, so a client that stops at the
first `CMC,` line it sees would read the next stream line as the reply to its next
query (and everything after that is off by one). The same wait follows every
`MEAS:STRE OFF`.

## Reading fields

Per frame: `frame, t_ms, fps, exposure, gain, gain_x, saturated, range_state, width,
height`, then for each channel R, G, B and S (= R+G+B):

| field | meaning |
|---|---|
| `bg`, `noise` | border level (clipped mean) and robust noise (1.4826 MAD) |
| `peak` | brightest pixel minus background |
| `sum` | whole frame minus the border level |
| `npix`, `cx`, `cy` | pixels above the spot threshold, their weighted centroid (px) |
| `sx`, `sy`, `angle` | 1-sigma widths along the principal axes (px), orientation (deg) |
| `spot_sum`, `spot_bg`, `spot_px` | spot photometry: sum over a box of 3 sigma around the centroid minus the mean level of a ring around it |

`range_state`: 0 in range, 1 adjusting, 2 too bright at the shortest exposure, 3 too
dark at the longest exposure and highest gain.

## Dynamic range and calibration

The signal of a reading is `spot_sum / (exposure x gain)`, comparable over the whole
auto-ranging range (exposure 1..~500 lines, gain x1..x31, and the spot's many pixels).
The GUI calibrates it with the laser (Light sensor > setup / calibration):

1. **Response**: continuous laser light, exposure sweep; the brightest pixel's code
   against the exposure gives the pixel response, whose inverse is uploaded as
   `CAL:LUT` tables. Every pixel value is then proportional to the light.
2. **Gain**: the linearised signal against the gain setting.
3. **Absolute**: with a power meter reading at the sensor position, watts per unit
   of signal for that laser (per wavelength).

Background and crosstalk (GUI: Corrections):

* **background**: the signal with every laser off (stray light, dark current), per
  channel, subtracted from every reading;
* **crosstalk**: a matrix of each laser's share of the R, G, B channels, measured with
  one laser on at a time (full power, dimmed while the spot saturates) (rows = sources = lasers, columns = detectors = channels, each
  row normalised to 1 - the convention of imp.bff's `PhotophysicsCrosstalkMatrix`). A
  reading is unmixed into per-laser signals by non-negative least squares. Both can also
  be typed in by hand.

The calibration is stored per sensor in `~/Documents/cmc-light/sensor-calibration-<serial>.json`.

Measured limits (2026-09-16):

- The unattenuated lasers saturate the sensor even at the shortest exposure (1 line):
  put an ND filter (OD 2..3) or a diffuser in front of the camera for quantitative
  work.
- The laser drivers emit no light for TTL pulses shorter than ~90 us (red), ~135 us
  (blue), ~175 us (green). Pulsed light is therefore not a linear reference; the
  response calibration uses continuous light and the exposure time instead.
- With exposures shorter than a pulsed laser's period, the rolling shutter aliases
  (rows see the light or not): keep exposure >= several periods.
Speed (measured over USB with streaming at 460800 baud, GUI default in bold):

| binning | analysed | analysis | camera | readings/s in the GUI |
|---|---|---|---|---|
| 1x1 | 320x240 | 157 ms | 6 fps | 6 |
| **2x2** | **160x120** | **49 ms** | **15 fps** | **16** |
| 4x4 | 80x60 | 16 ms | 28 fps | 25 |

`SYST:TIM?` reports grab and analysis times and the analysis split (border, main pass,
spot moments, photometry and profiles). The per-pixel cost is set by reading the frame
out of PSRAM while the camera's DMA writes the next one into it, so the analysis time
scales with the pixels read rather than with the arithmetic. Frame rows are copied into
internal RAM in bursts, and the spot moments and photometry only read a box around the
brightest pixel (which also keeps stray light out of the centroid).

What made it fast: two frame buffers (the camera fills one while the chip analyses the
other), a 24 MHz camera clock, pixel binning, the faster link, and streaming (the board
pushes each reading instead of waiting to be asked; a request costs a frame period).
Binning keeps the coordinates in frame pixels and scales the sums, so readings stay
comparable. `SENS:EXP:MAX` keeps auto-ranging from choosing frame-rate-killing exposures.
