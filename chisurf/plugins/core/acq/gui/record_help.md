# Record

Measures single molecules and analyses every burst while the measurement runs: the histograms of
the measurement type build up as you measure (E–S for PIE), a quality panel says whether to go on,
and the run lands in the project with exactly the bursts you saw.

## Sources

| Source | What it is |
|---|---|
| **Simulator (smFRET)** | A simulated MultiHarp measuring tttrlib's photon simulator: molecules diffusing through a confocal focus, each carrying donor and acceptor — with **PIE** excited by a green and a red pulse per period, with **two colour** by the green laser only. Populations are set by E and S, so the answer is known; the records take the same path as a real device's. |
| **Replay a photon stream** | A photons dataset of the Datasets workspace played back at measurement speed (*Speed* 1) or faster. |
| **PicoQuant device (USB)** | A MultiHarp (or another PicoQuant device the driver supports) over USB, through CMC's pqusb: **Connect**, check the count rates, set the sync and input levels, then Start. |

**Sample & instrument realism** (simulator only, folded) sets how real the simulated measurement
looks. *Realistic* (the default) adds what a confocal smFRET measurement shows: donor-only and
acceptor-only molecules, aggregates, bleaching and blinking, γ ≠ 1, leakage α and direct excitation
δ, background, scatter, afterpulses, an instrument response with timing jitter, per-state lifetimes,
detector dead time, brightness spread and slow drift. *Ideal* switches all of it off. Runs with the
same *Seed* are identical.

## Laser

**Connect** opens the laser driver — PicoQuant Sepia II when its library is installed, else a
simulated laser (the status line's tooltip says why Sepia II is not available). Connecting switches
every output off. The **Program** (head on/off, intensity, pulsed; the oscillator *Divider*; the
*Sequencer*'s pulses, outputs and sync per output) reaches the laser only with **Apply**, and light
needs **Emission on** after that. Any edit switches the outputs off until the next Apply.
**Laser off** is always there. The end of a run and closing the window close the laser.

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

## Device session

**Device session…** opens the acquisition window of earlier versions (Becker-Hickl, PicoQuant and
BrickMic setup cards, routing, decay and correlation plots).
