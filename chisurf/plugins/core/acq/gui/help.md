# Record

Measures single molecules and analyses every burst while the measurement runs: the histograms of
the measurement type build up as you measure (E–S for PIE), a quality panel says whether to go on,
and the run lands in the project with exactly the bursts you saw.

## Windows

The tool is a set of windows you arrange: **Acquisition** (settings files, source, simulated sample and
instrument, TCSPC device, scan, run), **Laser**, **Analysis** (setup, measurement type, burst rule,
running trace), **Quality** (traffic lights) and one window per plot -- **Histogram** (Point),
**Image** (Image), **Points** (Image), **Trace** and **Decays**. Drag a title to float or dock a window, drop it on another
to make tabs, resize from any edge, double-click a title to fold it. The bar on top always holds
**Start**, **Stop**, the run's state, **Laser off**, **Guide**, **Help** and **Reset layout**. The
arrangement is kept between sessions.
Dock accents group **acquisition** (blue), **illumination** (amber), **analysis**
(violet), and **monitoring** (teal). These are task labels, not safety verdicts.

Next to **Load**, **…** opens a file chooser for acquisition settings in **JSON**,
**PTU**, or **PTO** files. Browsing/Cancel changes nothing. **Open** validates the
document, then applies it using the normal settings-loading rules; a profile may
connect the devices it names, with laser emission kept off. Loading is blocked
during acquisition, another load, an active power adjustment, and Guided mode.
An explicit file selection replaces the workspace reload target rather than
leaving a different profile selected behind it.

Double-click a detector or mean row in **Count rates** for a **large floating
alignment display**. Its digits grow with the window and update from the same
rate source. **Mean recorded** uses full-run photon/time counters when available,
not the displayed trace ring. Closing the readout never stops acquisition.

Choose the **Guided** operating mode to open the modal measurement wizard; there
is no separate Guided measurement dock. Operator/sample entry and the sequential
physical tasks stay inside that wizard. To edit an approved setup, enter the
wizard after selecting **Advanced** first, then expand **Edit approved setup (Advanced)** on its
first page; ordinary Guided mode keeps those expert settings hidden. Power calibration is
opened from a laser's **Calibrate** control, not a second global toolbar button.
**Help** opens this reference window; **Escape** closes it.

The wizard uses emtk's shared **Wizard** control. Its background is blurred and
cannot receive clicks or keys. **Previous**, **Stop / block light**, and **Next**
stay at the bottom while the instructions scroll above them. Previous is guarded:
it cannot change a running measurement or reuse saved references after going back.

The workflow always keeps live **count rates, correlations, decays/IRF**, and a
stage-specific **detector-count or FRET/stoichiometry** plot in the wizard itself.
The wizard is built for inexperienced operators: the filter and beam-splitter
checks are **one optics confirmation**, a single *Allow light and set approved
power* gesture tunes **every laser head in turn**, and a stage whose checks all
pass **advances automatically** — no extra Next click. On the power page you may
**edit the target** for the current head; your target is bounded by that head's
calibration and applies to the whole session.

**FCS comes first.** After water and buffer you insert your FCS pre-dilution and
run about **five minutes at low power**, increasing gradually while watching the
Correlation amplitude (never start high — detectors can be damaged). The wizard
reads how many molecules are in focus and prints **exact dilution volumes** for
the single-molecule measurements (for example: *put 47 µL buffer on the slide,
add 3 µL of the pre-dilution*), reusing the FCS concentration as instructed.

During the DNA and sample stages the wizard shows the **burst/intensity trace**,
the **E–S histogram with E and S marginals**, live **burst count, measurement
time and photon counters**, and a **traffic light**: plain green when every
configured check passes; yellow/red states say exactly **what to improve**.
After the calibrations you may **measure several samples in a row** — the
calibration, references and DNA-derived corrections stay valid for every
sample; press **Measure another sample** or **Finish guided session**.
The plot frames remain present while waiting for data. Their reference diagnostics
use the recorded photons, not a simulated preview of a connected instrument.
Amplitude-derived N and raw brightness are preliminary, not fitted diffusion times
or calibrated molecular brightness. Missing scientific limits and unfitted
diffusion/lifetime quantities remain explicitly **unverified**. A saved recording
passing acquisition checks is not a claim of complete dye/timing calibration.
Simulation practice is labeled **SIMULATION ONLY** throughout the wizard. Its
reference and DNA curves still come from the photons written to its simulated
PTUs; they are not evidence about a real instrument. The count-rate trace shows
successive acquisition bins, while numerical summary rates use the full run.

Every connected laser has its own visible name, power control, **On**, **Pulsed**
and **Calibrate** block. Heads are not hidden behind a color selector. Committing a
calibrated target performs the power request; there is no second Set button.
Changes after recordings require a confirmation and warn about pulse-shape and
timing/IRF validity. Routine controls cannot alter a running measurement's power.
Without a valid diode-to-power calibration, the control displays **drive (%)**,
not an invented optical-power value. Changing drive alone does not enable light.
When the other heads are emitting and their diode contributions are verified for
this session (verified alone points over one shared dark level, re-checked against
live readback), their net contribution is subtracted and those heads, the sequencer
and the shutters stay untouched. An unknown or changed mixture is never guessed:
the request asks first, and confirming zeroes every other head.

## Point and Image

Simple mode keeps only yellow/red quality warnings; missing data is not a passing
verdict. Advanced shows the full compact quality table, stretched to fill its dock.
Plot range controls are absent in Simple mode. In Advanced they are folded away
by default: **Histogram range**, **Trace range**
and **Decay range** each occupy one header line. Click the relevant header to show
its compact three-column controls; the other plots stay folded. Zero retains automatic
scaling. Fold the header again when finished to return the space to the plot.
Idle histogram, trace and decay docks retain full-size empty axes; waiting for
photons does not collapse or replace the plotting area with fabricated curves.

In **Decays**, **Burst photons only** switches between two live accumulators:
off shows the **total decay** from all recorded photons; on shows the decay from
photons in **all accepted bursts**. Both come from tttrlib. This is a cumulative
burst-selected decay, not the last individual burst. Switching the view never
changes the recorded PTU, the burst-search settings or the accumulated data.

**Point** measures single molecules at one spot: bursts are searched live, their histograms (E–S for
PIE) and the quality lights of the FRET checker build up, and the **running trace** shows the last
seconds in bins you choose (**Analysis › Running trace**: span, default 1 s; bin, default 1 ms).
With donor and acceptor streams, donor-excitation donor counts are cyan and donor-excitation
acceptor counts are magenta. Their common counts in the same time bin are white; directly
excited acceptor (AA) is an orange line. **White indicates temporal coincidence, not proof
of a FRET molecule:** background, leakage and independent molecules can also coincide. The
vertical range follows the run's mean, not the largest burst; extreme bursts can be clipped.

**Image** scans: the scanner's line markers arrive in the photon stream, and the image builds up
line by line (intensity, mean arrival time as fast FLIM, each detector, each micro-time window of a
PIE setup). The **Scan** section sets pixels, area, the image's corner on the stage (**X start**,
**Y start**), dwell time, frames, bidirectional scanning and z planes. Sources:

- **Simulator (scan)** -- a simulated sample (beads of two lifetimes on a cell outline, or single
  molecules on a coverslip of which a few spots hold two) scanned by tttrlib's simulator through a
  simulated MultiHarp.
- **Replay an image** of the workspace -- its scan is read from the file's header, nothing is
  recorded, and the image equals the one the imaging tools build from the file.
- **TCSPC device and scanner** -- the real instrument: the TCSPC device records while the sample
  scanner rasters. On the MT200 the scanner is the PI E-725 piezo stage, driven through libphacq's
  `pi` driver as SymPhoTime drives it (learning, then the image); its line triggers mark
  each line's start and stop on HydraHarp marker inputs, which Start switches on. Which inputs and
  which edge is the instrument's cabling, so the settings file's **scanner.line_markers** declares it
  (the MT200 profiles: start 3, stop 4, falling edge, as SymPhoTime records them); without it an image
  does not start. So the image is built from the photon stream alone. The E-725 sends no frame marker: frames are counted
  in lines, each frame is one raster. A settings file's **scanner** section names it and loading
  the file connects it (`{"driver": "pi", "address": ""}`: the first E-725 -- on Windows through PI's own USB driver; `tcp:<host>` over
  the network; `sim:` libphacq's simulator); **Scan › Scanner** shows it, its stage position and, in
  Advanced, its learning time and line turnaround. Opening the scanner moves nothing, and a scan
  opens no shutter and switches no laser beyond what every run's start does.

The imaging quality lights: pile-up (the brightest pixel against the laser rate), lines per frame and
paired line markers (the markers are consistent), and the signal in the bright pixels. A recorded
scan enters **Datasets** as an image (photons) that the imaging tools take from the workspace.

## Points: pick molecules and measure them one by one

On the image (live or finished) a **click** adds a point -- a click, not a drag, which pans the
image -- at the stage position under the pointer. **Auto-pick** runs the spot finder's
**single-molecule workflow** (Gaussian smoothing, Otsu threshold, watershed, spots touching the edge
dropped; [Spot finder](docs/guides/84_spot_finder.md)) on the intensity image and adds the molecules it found,
brightest first: **Max molecules** caps the count, **Min photons** and **Max photons** bound a spot's
summed intensity (aggregates and beads are brighter). Each point is a numbered ring on the image and
a row of the **Points** table; ✕ or Delete removes one, **Clear** all.

**Measure points** parks the focus on each point in turn -- a settled move of the scanner (no wave
generator, no line markers), as SymPhoTime's point measurement -- and records it: for **Time per
point**, or less with **Until bleached**, which ends a point once its count rate has stayed down
near the background (between the background and the starting level, 30 % of the way up, for half a
second). Every point is a recording of its own (`<name>_p000.ptu`, ...; SymPhoTime's point header:
`ImgHdr_Dimensions` 1, `ImgHdr_Ident` 6, the stage position) and enters Datasets. **Stop** ends the
sequence after the current point.

While a point records, **Trace** shows its count rate per detector and in total, the bleach rule's
threshold and the moment it called the molecule bleached, and under it the FRET efficiency (proximity
ratio) and the mean arrival time per bin. After each point its recording is analysed with ChiSurf's
shared tools -- the [intensity-trace](docs/guides/74_intensity_traces_and_file_tools.md) tool's binning (20 ms) and the shared
Gaussian **HMM** with the state count the BIC prefers -- and the row fills in:

| Column | What it is |
|---|---|
| Photons | photons recorded at the point (thousands) |
| Bleach | when the path reached its final, dimmest level |
| Steps | bleaching steps: each drop to a level dimmer than every level before (one molecule, one step) |
| E | FRET efficiency of the first level, acceptor over the sum, the final level subtracted as background |
| S | stoichiometry -- needs alternating excitation, which a point of one colour does not have |
| τ | fast lifetime: the mean arrival time of the photons before the bleach, after the decay's peak |

Select a row: its trace and HMM path appear in **Trace** and its ring is highlighted on the image.
When the sequence ends the table of every molecule is stored with the image (in the image dataset's
container, beside its other imaging results).

## Survey: a larger area, automatically

**Points › Survey** runs the Points workflow by itself, tile after tile: image a tile (the Scan
panel's raster; a tile is its **Width × Height**), **Auto-pick** it (with its *Max molecules* and
*Min/Max photons*), **Measure points**, move on -- until **Stop**, a stop condition, or the whole
area is done. A tile with fewer than **Min molecules** is logged as empty and passed; a tile that
fails is logged and passed, never the end of the survey.

- **Area:** *Whole piezo range* (default: the scanner's travel as its driver states it, 0–100 µm on
  the E-725) or a *Custom area*; every tile and every move is kept inside the range.
- **Order** (Advanced): an **outward spiral** from where you focused -- the centre of the
  last image (the scanner parks at the stage centre after every image, so its position is not the
  focus; *Spiral centre*: or the area's centre), then ring after ring. A coverslip is rarely
  flat, so the tiles nearest the focused spot, the best focused, are measured first. *Serpentine*
  rows on request.
- **Tile overlap** and the **Edge guard** (Advanced, pixels): a spot nearer a tile's edge than the
  guard is left to the neighbouring tile, which sees it whole; with an overlap of at least twice
  the guard no molecule falls between tiles, and a molecule measured already is never measured
  again.
- **Stop after** tiles, molecules or minutes (0: no limit), and (Advanced) after a number of
  **empty tiles in a row** -- far out, a ring of empty tiles usually means the sample left the
  focus.
- **Re-image after measuring** (Advanced): image each tile again after its molecules were measured,
  to see what bleached.
- **Scanner learning**: the scanner learns its pattern (linearization, line triggers) before an
  image -- 5 s on the MT200 -- and every tile has the same raster. *First tile, re-check line
  triggers* (default) learns once and re-measures only the line triggers per tile (one recorded
  period, well under a second); *First tile only* reuses everything; *Every tile* learns each
  time, as a single image does. Change it if the line edges of later tiles look shifted.

The shutters open once when the survey starts and close once when it ends or is stopped; the laser
is never switched. Every tile image and every molecule's recording enters Datasets as in a single
run, and **one table of all molecules** (with their tile and stage position) is stored with the
first tile's image and rewritten after every tile, so a stopped survey keeps its results. The
**map** under *Start survey* shows the tiles in visiting order (orange now, green measured, dark
empty, red failed) and the measured molecules; the line above it the tile, the molecules, the time
so far and the time left; the log is the tooltip of the line under the map.

## Provenance: every measurement traces back

Every image, tile image and point recording is a dataset of the project, and each can be followed
both ways -- in its own file and in the project:

- **A point's file** names the image it was picked on (file name and dataset uid), the pixel and
  the image's raster (corner and pixel size, so pixel ↔ stage is reproducible), how it was picked
  (*auto*: the spot finder workflow and a hash of its settings; or *click*) and the spot's
  brightness, the stage position aimed at and the one reached, and, in a survey, the survey and
  tile (`ChiSurf_Point_*`, `ChiSurf_Survey_*` header tags; SymPhoTime's point tags are kept).
- **A tile image's file** names its survey, the tile, the number of tiles, the tile's corner and
  the scanner's learning.
- **In the project** each dataset's container records how it came to be: a point's *point*
  record (picked and measured, the image as an external reference) and its *molecule* row, an
  image's *points* list naming every point recording, a tile's membership of its survey, and the
  survey's list of tiles with their images. The molecule tables name each molecule's point
  recording and image.

From Python, `chisurf.plugins.core.acq.live.provenance.backtrace(ptu)` returns a point's image,
pixel, pick, survey and settings; `points_of(image)` an image's points; `survey_of(image)` a tile's
survey.

## Sources

| Source | What it is |
|---|---|
| **Simulator (smFRET)** | tttrlib's photon simulator: molecules diffusing through a confocal focus, each carrying donor and acceptor — with **PIE** excited by a green and a red pulse per period, with **two colour** by the green laser only. Populations are set by E and S, so the answer is known. |
| **Replay a photon stream** | A photons dataset of the Datasets workspace played back at measurement speed (*Speed* 1) or faster. |
| **TCSPC device** | A PicoQuant MultiHarp 150/160, PicoHarp 330 or HydraHarp 500 (USB) or a Becker & Hickl SPC card (PCI), driven natively by libphacq — no vendor library. **Connect**, check the count rates, set the device up, then Start. |

**TCSPC device settings.** Once connected, the panel lists **every setting the device has**, as its
driver describes it: the sync (divider, trigger level and edge or CFD, offset, dead time), each input
on its own fold (level, edge, offset, dead time, enabled), timing (binning, histogram offset,
overflow), markers and outputs — for a B&H card its CFD, sync, TAC, timers and FIFO mode. An edit
reaches the device at once (between runs); a value the device refuses is named in the status line
and the panel shows the device's values again. The values are part of the settings file.

**Sample & instrument realism** (simulator only, folded) sets how real the simulated measurement
looks. *Realistic* (the default) adds what a confocal smFRET measurement shows: donor-only and
acceptor-only molecules, aggregates, bleaching and blinking, γ ≠ 1, leakage α and direct excitation
δ, background, scatter, afterpulses, an instrument response with timing jitter, per-state lifetimes,
detector dead time, brightness spread and slow drift. *Ideal* switches all of it off. Runs with the
same *Seed* are identical.

## Laser

**Connect** opens the laser driver — a PicoQuant Sepia II through libphacq when one is connected,
else a simulated laser (the status line's tooltip says why Sepia II is not available). Connecting
switches every output off (the Sepia's **Soft lock**).

A **Sepia II** shows its own controls, which act at once: **Soft lock** (on: every output is off),
and per laser head **Pulsed** (off: continuous wave), **Repetition rate** (80 MHz / 2ⁿ from the
head's own oscillator, or an external trigger edge) and **Intensity** (per mille). An oscillator
module (SOM 828 sequencer) is not driven yet.

The **simulated laser** has a **Program** instead (head on/off, intensity, pulsed; the oscillator
*Divider*; the *Sequencer*'s pulses, outputs and sync per output) that reaches it only with
**Apply**; light needs **Emission on** after that, and any edit switches the outputs off until the
next Apply. One laser button: red **Laser off** while the laser emits (always there, never fails), green **Laser on** otherwise (once a program is applied). The end of a run closes the excitation shutter and leaves the laser alone; closing the window closes the laser.

**Windows from laser** turns the applied program into the Experiment setup's micro-time windows: one
window per enabled excitation, shifted by the sync offset (two give *prompt* and *delayed*: PIE).

## Settings files

One JSON document holds the device, the laser program, the experiment and the run. Settings files
enter ChiSurf through the drop like every input. **Load** reads a settings row of the workspace,
fills the form and sends it to the connected device and laser (emission stays off). **Use settings
of this measurement** recovers them from a photons row's file header; what the header did not
record is listed in the status line's tooltip, and **Use its windows** takes the windows its laser
program implies. **Save as…** writes what is set now. Every recording carries its settings document
in its header (the `ChiSurf_AcquisitionSettings` tag), so a measurement can be repeated from the file.

## Measurement types

The **Experiment setup** reads the Instrument setup as one measurement type (by default the one the
setup describes):

| Type | Quantities | Histograms |
|---|---|---|
| Single colour | burst size and duration | photons, duration |
| Two colour | proximity ratio | proximity ratio |
| PIE / µs-ALEX | proximity ratio, stoichiometry (with γ, β, α, δ also FRET efficiency and corrected S) | proximity ratio vs stoichiometry |
| MFD | anisotropy per colour, proximity ratio | anisotropy; proximity ratio vs donor anisotropy |
| Three-colour PIE | proximity ratios BG, BR, GR; stoichiometries BG, GR | PR(GR) vs S(GR); PR(BG) vs PR(BR) |

**Histogram** above the plots picks which one is shown; a 2-D histogram comes with both marginals.
The 2-D colour scale defaults to `log10(1 + counts)` so a bright donor-only peak does not hide
smaller populations; choose linear or logarithmic intensity and a colormap, or enter a maximum
count to cap the display (0 uses the full range). This changes only the display, not the data
or the linear marginal distributions.

## Excitation windows: checked against the data

The setup's windows are micro-time channels of the resolution the setup declares (*Microtime res.*
in the setup editor); a setup made on another TCSPC or binning has them **converted** to this
device's channels when the run starts (the setup summary says so).

During a run Record finds the excitation pulses in the live decays (after 5000 photons, and again
whenever the count has doubled) and holds the windows against them. When they do not match -- a
window outside the range, a pulse in no window, a boundary inside a pulse, two pulses in one
window -- a warning appears under **Experiment setup** with **Update windows** (the next run uses
the detected ones; this run is recorded whole and can be re-analysed) and **Keep** (asked again
only when the decays show another pulse pattern). Nothing changes silently and the run goes on.
One pulse only is an info line: a donor-only sample or not PIE, windows not checked. The detectors'
micro-time gates are converted and checked with the windows (a gate that hides a pulse is
offered opened to the whole range). A **µs-ALEX** run is checked on its first photons' macro
times: the alternation period and the laser windows; *Update windows* takes both. Where the
source cannot provide macro times the line reads *ALEX windows not checked live; checked when the
run is analysed*.

**From a measurement…** takes the windows of an earlier FRET measurement of the workspace: its
pulses are detected and shown against the current windows, and taken (converted to this device's
channels) when you press *Use detected windows*. Method:
[Excitation windows](docs/concepts/excitation_windows.md); workflow:
[Detecting and checking excitation windows](docs/guides/115_excitation_windows.md).

## What is computed, live

1. Every photon is counted in its streams: each detector, and each detector in each excitation window
   (PIE: prompt green = DD, prompt red = DA, delayed red = AA).
2. Bursts are found by the sliding-window rule — *window photons* within *window time*, at least
   *minimum photons* — exactly as [Burst Selection](docs/guides/index.md) searches offline: re-analysing
   the recording gives the same bursts.
3. The quantities of the type, as the batch analysis computes them — e.g. proximity ratio
   DA / (DD + DA) and stoichiometry (DD + DA) / (DD + DA + AA); with γ, β, α, δ in the setup also the
   accurate-FRET efficiency and stoichiometry ([Hellenkamp et al. 2018](https://doi.org/10.1038/s41592-018-0085-0)).
   Background per stream is the rate of its photons outside bursts.

## Quality lights

The Quality dock has a short overall status and one compact table:
**Metric · Value · Limit · Status**. Hover a row for its explanation and
recommended action; those instructions are not repeated as paragraphs or a
Guidance column. Missing values remain **no verdict**, never a pass. The wizard's
quality-check table uses the same hover-only guidance convention.

The Count rates dock uses aligned **Channel · Rate · Unit** columns for sync,
every detector and the recorded mean when available. Hz/kHz/MHz scale automatically.
Its default height is compact rather than half of the right-hand plot region.

Every two seconds the FRET quality checker judges the bursts so far: green continue, amber read the
note, red act now (the note says what to do). Checks that do not apply to the type are grey —
stoichiometry without alternation is *not applicable*, the 2CDE filters are *not computed live* (run
the FRET checker on the recording). The verdict at stop is stored with the run.

## Where the run goes

The photons are written to `<name>.ptu` in a `<project> recordings` folder beside the project file
while measuring, so a crash leaves them on disk. On stop the run enters the Datasets workspace as a
photons dataset with its bursts as a run below it, readable by ndXplorer and every burst tool.
**Store photons** decides how: *Embed in the project* (the default) puts the photons inside the
`.cs.pto` at the next save, which the autosave makes at once; *Link* keeps only the path. The status
line says what happened; *Saved* names the file (the full path is its tooltip) and **Show file**
opens its folder.

## Video

The **Camera** dock previews a selected camera or capture card, video file, or
supported stream URL, next to the plots and in every mode -- including the
simulator, because it watches the sample, not the photons. The dock comes
forward when a connected source delivers its first frame. Enter a camera index
such as `0`, a Matrix Vision SDK device such as `mv:0`, or the path or URL, and
choose Connect. The Matrix Vision source uses the installed mvIMPACT Acquire
driver and supports monochrome frames; other capture cards can be added the
same way (one adapter, registered by address prefix). Camera indices, files and
streams go through the optional OpenCV Python package. Discover lists
operating-system video devices without opening them; the list does not
establish the OpenCV camera index. Devices are opened only when selected and
connected.

Enter a new recording path, then choose Record. A name ending in `.tif` or
`.tiff` records a multi-page TIFF: every captured frame becomes one page,
written as it arrives, needing no OpenCV anywhere. Any other name records a
video file through OpenCV at the playback frame rate, dropping or repeating
frames as needed for constant-rate playback. Stop recording finishes the file
while leaving the preview open. Each frame's host monotonic capture time is
written to an adjacent `.timestamps.csv` file, with wall-clock and monotonic
anchors. Video runs independently of photon acquisition and is not
automatically embedded in the project. The sidecar records the active photon PTU
path and changes of photon run during video recording. Neither an existing
recording nor an existing sidecar is overwritten. If a device driver blocks
indefinitely while reading, stopping the recording still finalizes the output,
but the source cannot reconnect until that read returns. A capture gap longer
than 30 seconds stops recording with an error instead of an unbounded number of
repeated frames. Closing Record waits up to two seconds for video finalization;
if it is still pending the output may be incomplete.
