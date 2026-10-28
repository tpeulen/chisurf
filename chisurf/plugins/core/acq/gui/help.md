# Record

Measures single molecules and analyses every burst while the measurement runs: the histograms of
the measurement type build up as you measure (E–S for PIE), a quality panel says whether to go on,
and the run lands in the project with exactly the bursts you saw.

## Windows

The tool is a set of windows you arrange: **Acquisition** (settings files, source, simulated sample and
instrument, TCSPC device, scan, run), **Laser**, **Analysis** (setup, measurement type, burst rule,
running trace), **Quality** (traffic lights) and one window per plot -- **Histogram** (Point),
**Image** (Image), **Trace** and **Decays**. Drag a title to float or dock a window, drop it on another
to make tabs, resize from any edge, double-click a title to fold it. The bar on top always holds
**Start**, **Stop**, the run's state, **Laser off**, **Guide**, **Help** and **Reset layout**. The
arrangement is kept between sessions.

## Point and Image

**Point** measures single molecules at one spot: bursts are searched live, their histograms (E–S for
PIE) and the quality lights of the FRET checker build up, and the **running trace** shows the last
seconds -- donor up, acceptor (FRET and directly excited) down -- in bins you choose (**Analysis ›
Running trace**: span, default 1 s; bin, default 1 ms).

**Image** scans: the scanner's line and frame markers arrive in the photon stream, and the image
builds up line by line (intensity, mean arrival time as fast FLIM, each detector, each micro-time
window of a PIE setup). The **Scan** section sets pixels, area, dwell time, frames, bidirectional
scanning and z planes. Sources: the **simulated scan** (beads of two lifetimes on a cell outline,
scanned by tttrlib's simulator through a simulated MultiHarp), or **Replay an image** of the
workspace -- its scan is read from the file's header, nothing is recorded, and the image equals the
one the imaging tools build from the file. Real scanners come with CMC's device layer (rustytime).
The imaging quality lights: pile-up (the brightest pixel against the laser rate), lines per frame and
paired line markers (the markers are consistent), and the signal in the bright pixels. A recorded
scan enters **Datasets** as an image (photons) that the imaging tools take from the workspace.

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
next Apply. **Laser off** is always there. The end of a run blocks emission (the laser stays connected with its program, so the next run needs only **Emission on**); closing the window closes the laser.

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
