# cmc-light help

cmc-light drives three TTL-modulated lasers from an ESP8266. The **Sequence table** is
the sequence: the microcontroller is given it and plays it on its own with microsecond
timing (e.g. ALEX for smFRET). There is nothing to upload and nothing to start - every
edit reaches the instrument by itself, a moment after you stop changing it. Ticking a
laser **on** decides which lasers take part; the red **OFF** button stops everything,
and a table of one step with the lasers on is simply continuous light.

## Connecting

- Pick the device in the **dropdown**; its settings sit to the right of it.
  Serial ports that answer `*IDN?` are marked `[LIGHT-3 <serial>]` (115200 baud,
  **Scan** looks again). **TCP / WiFi** takes a host (`cmc-light.local` or an IP
  address) and a port (5025). **Simulator** runs the real command logic without
  hardware.
- **Disconnect** and closing the window switch every laser off first.
- `python -m cmc_light` connects the first cmc-light found on USB, or the
  simulator when none is plugged in. `--port /dev/cu.wchusbserial10`,
  `--tcp cmc-light.local` or `--sim` choose explicitly. Add `--debug` to print every SCPI command
  and reply to the terminal; errors are always printed there.

## Lasers and relative power

- **on** enables a laser: it takes part in the sequence the MCU plays (and lights
  immediately if the table is a single window).
- **Relative power** below 100 % is pulse-width modulation of the TTL line:
  every on-window is cut into PWM periods and the laser is on for that fraction
  of each period. **achieved** is the duty after timing quantisation.
- **PWM period** sets the modulation rate (20 us .. 1 s). **min pulse** is the
  shortest high or low time that will be produced; duties that would need a
  shorter pulse round to fully off or fully on.
- Laser drivers low-pass their TTL input. Check with a photodiode that the chosen
  PWM period gives the average power you expect.

### PWM or cycle dithering (programmed sequences)

PWM cuts every window, so short gapless ALEX windows (say 35 us) get dark time
inside. **Cycle dithering** (`SOURce:PWM:MODE CYCLes`, back with `PWM`) keeps every
window solid instead: a laser at relative power p is fully on in `round(M * p)` of
`M` sequence periods, spread evenly, and dark in the others (M = 100, or 50/20/10
if the program would need too many edges). The trade-off: the power is only right
averaged over M periods, and it comes in steps of 1/M (achieved shows e.g. 0.1200
for 0.123). Lasers at 100 % and live control are not affected. The sync
output still marks every sequence period, and cycles/counts stay in sequence
periods (a finite cycle count is rounded up to a multiple of M).

In the GUI: **Laser power → low power: whole windows (no gaps)** (the default, and
chosen automatically with *gapless alternation*) or **PWM inside windows**. The
timing preview shades a dithered laser's windows by its share of lit periods and
lists e.g. `blue 30/100`.

## Timing limits

Limits depend on who is in control. The fastest path is the one where the
microcontroller plays the sequence; live control from the computer is
slower over USB and slowest over WiFi.

| Control path | Limit | Where it comes from |
|---|---|---|
| Sequence (MCU plays) | edges to ~1 us; PWM period >= 20 us | timer interrupt, measured late max 0..15 us |
| Sequence, dense edges | edges less than 13 us apart only in bursts of at most 3 ms | measured: longer runs make the player pause 1 ms every 4 ms |
| Live control, USB | live updates at most every 20 ms (50 per second) | measured 8..18 ms per command incl. error check |
| Live control, WiFi | live updates at most every 100 ms (10 per second) | estimate for the ESP8266 access point, not yet measured |

What the dense-edge rule means in practice (measured with all three lasers on):

| PWM period | equal powers | unequal powers (e.g. 30 / 50 / 70 %) |
|---|---|---|
| 50 us (20 kHz) | clean | clean |
| 40 us | clean | rejected in continuous mode |
| 25 us (40 kHz) | clean | rejected in continuous mode |
| 20 us | rejected | rejected |

A setting that would break the rule is refused with a clear error and the
previous, working setting stays active. Short bursts are allowed, e.g. 2.8 ms of
40 us PWM inside an ALEX window.

## Windows

The panels are separate windows: **Connection**, **Laser power**, **Sequence
programmer**, **Sequence table** and **Timing preview**. Drag a title bar to move a
window on its own; near a screen edge or another window it snaps flush (a window
snapped to a screen edge stays on that edge when the main window is resized).
**Shift**-drag moves a window together with the windows snapped to it.
`v` or a double-click on the title folds a window, `x` closes it, the corner grip
resizes it - its edges snap to the screen and to other windows' edges too, and a
window never gets smaller than its contents need. **View** shows or hides windows and resets the layout. The layout
and the main window's size are remembered between runs in
`~/Documents/cmc-light/cmc-light.ini`.

## Sequences

The **Sequence table** is the sequence: every row is one step with a duration,
the lasers that may emit and the **sync** output. The microcontroller plays it
with microsecond timing (steps from 20 us); everything else only edits the table.

- The table is uploaded and played automatically: change anything (a duration, a
  preset, the run time, the low-power method) and it is sent about 150 ms after the
  last change, so a slider drag is sent once, not per frame. The status (cycles
  played, period, number of edges and **late max**, the largest delay of any edge
  measured by the firmware) and the **run time** (0 = endless, otherwise cycles
  computed from the period) sit at the top of the Sequence programmer.
- **Presets** write the table live: changing any of their values (slider or
  exact field) rewrites the table's rows at once, and the preview follows.
  **ALEX to table** / **gapless to table** write a preset without changing a value.
  - **ALEX**: lasers take turns, each for the on-window, followed by a dark gap
    (gap 0 = back to back);
  - **gapless**: lasers take turns back to back, each with its own window length
    (also selects *whole windows* for low power).
  Presets never set the sync column; sync ticks stay on their rows while the
  number of rows stays the same.
- **total period**: type the whole period and press **Return**; the table's
  steps are rescaled to it.
- **Sequence table**: click a cell to select it; type digits to edit a duration
  (Return commits, Esc cancels); click a laser or sync cell or press
  Space / 0 / 1 to switch it; arrows and Tab move; **+ new row** appends; Insert,
  Ctrl+D (duplicate), Ctrl+Backspace (delete). **copy** / Ctrl+C puts the table on
  the clipboard as tab-separated text, **paste** / Ctrl+V inserts rows copied from
  Excel or a CSV.
- **sync column**: D5 is high during every step marked 1, and only then - use it
  to trigger or tag a detector or camera. On the wire it is mask bit 3
  (`SEQ:STEP:APP 1000,9` = blue + sync).
- **Timing preview**: drag a laser's (or the sync's) bar to move it, its ends to
  change its length; bars may overlap, the table is rebuilt to match.
- **load CSV... / save CSV...** (Sequence table window) read and write the table,
  one row per step:

  ```
  duration_us,blue,green,red,sync
  1000,1,0,0,1
  100,0,0,0,0
  500,0,1,1,0
  ```

  The first column may also be `duration_ms` or `duration_s`; laser columns can be
  named or numbered (`1,2,3`), the `sync` column is optional and cells may be 1/0,
  on/off, yes/no or x/empty. Lines starting with `#` are comments.
- **Text form**: `1000 B+S; 100 -; 500 G+R; 2ms 1+3` - a duration (us, ms or s)
  and the lasers by initial, name or number, `S` for sync, `-` for dark.
  **apply text** replaces the table, **to text** writes it out.

## Power diode (light sensor in the laser head)

A BH1750 light sensor (M5Stack DLight) on the laser board's I2C bus measures what the
lasers emit, averaged over its integration time, so it also reads pulsed light correctly.

- **Laser power** window, row **power diode**: the reading in **a.u.** It is the **total**
  of whatever is emitting. The sensor weights light like the human eye, so a reading
  compares a laser with itself, never one colour with another (green reads far higher
  than blue at the same optical power).
- **calibrate...** turns a.u. into watts for one laser, with a power meter:
  - put the meter where the laser goes, pick the laser and press **start**;
  - the wizard switches that laser on alone (the others stay off) at 100, 75, 50 and
    25 % power, and after each one shows the diode reading and waits for the meter's
    reading - type it, pick **W / mW / uW / nW / pW** and press **record** (**skip**
    leaves a level out, **cancel** stops and puts the lasers back);
  - it fits watts per a.u. through zero and reports the worst miss of the fit.
  The diode row then reads in watts whenever exactly one laser is on, **per laser**
  lists each laser's power, and the calibration is kept in the settings file.
- **per laser**: measures each laser with the others off (that is the only way to get a
  single laser's power) and lists the values; the lasers' previous state is restored.
- **test diode**: switches all lasers on and off a few times and reports whether the
  reading follows.
- Wiring: SDA and SCL on **D6 and D7**. **Not D8**: GPIO15 must be low while the board
  boots, and the sensor's pull-up stops it booting. The firmware searches the usual pin
  pairs at start-up and remembers the one that worked (`SYSTem:I2C:PINS`).
- **SOURce:EXCLusive ON** switches one laser on at a time (and refuses sequence steps
  that light two). It is off in normal operation and is what **per laser** uses.

## Light sensor (camera)

An ESP32-CAM with the cmc-sense firmware is a light detector and beam profiler; it
sends numbers, never images (details: `docs/SENSE.md`). It is searched for and connected
by itself - at start, when it is plugged in later, and after it was unplugged. Pressing
**Disconnect** stops that until you press **Connect** again.

- **Light sensor** window: auto range (exposure x gain) or manual exposure / gain, and
  per colour channel R, G, B, S (= R+G+B) the **signal** (spot sum with a local
  background, divided by exposure x gain: comparable across range steps), the peak or
  the absolute **power** once calibrated, the centroid in px and the **D4sigma** beam
  diameters in um.
- **Beam profile** window: the spot map in the middle with 1, 2 and 3 sigma contour
  ellipses per colour, the x projection below it and the y projection beside it, the
  signal history on a log scale over a chosen window (**history**: 10 s, 30 s, 1 m, 5 m). **Profile each laser** switches the lasers on one at a
  time (their previous state is restored) and adds each laser's spot and profiles.
- **Corrections** (button **corrections...**): the signal in three stages, per colour
  channel R, G, B, S: **raw signal**, the **background** (typed in, or measured with
  every laser off) and the **bg corrected** signal; below it the **crosstalk matrix**
  (a column per laser, a row per channel: that laser's share of the channels, its column
  summing to 1). **auto: measure with each laser** measures it by switching the lasers on
  one at a time at full power, dimming a laser whose spot saturates (a saturated spot has
  no colour); the lasers' previous state and powers are restored. The values can also be
  typed in.
  The **crosstalk corrected** rows solve the mixture for the lasers (non-negative least
  squares, the convention of imp.bff's crosstalk matrix) and show the absolute power per
  laser when that laser is calibrated.
- **Sensor setup** (button **setup / calibration...**): background (frame border, dark
  frame, none), spot photometry, and the calibration steps: 1 response (continuous
  laser light, exposure sweep), 2 gain, 3 absolute (only that laser on, its power at
  the sensor from a power meter), and the laser pulse response (the drivers emit no
  light below ~90..180 us pulses).
- **Speed** (Light sensor window, row **pixels**): frame size 320x240 or 160x120 and
  pixel binning 1x1, 2x2 or 4x4, set from the computer at any time. Changing the frame
  size restarts the camera board: readings stop for about 5 s and come back with the
  binning you had chosen; the buttons ignore clicks while that happens. If readings ever
  stop coming for 8 s the program resets the camera by itself and picks it up again -
  and a camera that has gone silent (which a scan cannot see) is reset and reconnected
  the same way. The camera pushes
  readings continuously over a 460800 baud link: about 16 readings/s at 2x2 (the
  default) and 25/s at 4x4 (80x60 px), with the beam profiles every second reading. The default (320x240, 2x2) gives about 6 readings/s; the profiles are fetched on
  every second reading. Binning keeps the coordinates in frame pixels.
- The unattenuated lasers saturate the camera: use an ND filter or a diffuser.

## Settings files

- **File > Save settings** stores powers, PWM, mode, preset parameters, the
  Sequence table, run time and the TCP host as JSON (default folder
  `~/Documents/cmc-light`).
- **File > Load settings** restores them. For safety, loading never switches a
  laser on: tick **on** yourself.

## Safety and troubleshooting

- The red **OFF** button aborts any sequence and switches all lasers off. It then
  turns into a green **ON**, which switches the same lasers back on (same powers)
  and restarts the sequence if one was playing. Ticking a laser on by hand turns
  it back into OFF.
- Lasers on D1/D2 can flash while the board is flashed or reset.
- No reply on the serial port: close other programs using it. On macOS the CH340
  driver can hang - run `scripts/usb_reset_ch340.py` or re-plug the cable.
- If a reply is lost, the program realigns the link by itself and reports
  "link resynchronised" once; the command may need repeating.
