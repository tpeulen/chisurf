---
type: Guide
title: Detecting and checking PIE / ALEX excitation windows
description: Find the excitation pulses of a measurement, propose prompt/delayed windows, check a detector setup's windows against the data — in the Excitation Windows tool, the setup editor, during a Record run and before burst selection; headless with csc windows and the Python API.
tags: [guides, smfret, pie, alex, setup, record]
---

# Detecting and checking excitation windows

**Setup › Excitation Windows** (`chisurf/plugins/core/excitation_windows/`), the setup editor's
**Auto-detect**, Record's live check and *From a measurement…*, and burst selection's pre-flight.
Theory: {doc}`../concepts/excitation_windows`.

PIE windows are channel numbers, and channel numbers only mean something for the TCSPC, range
and binning they were typed for. ChiSurf finds the excitation pulses in the data and holds the
windows against them wherever windows are used; it warns and offers the detected windows, and
the user decides.

## 1. Check a setup against a measurement (Excitation Windows)

Open **Setup › Excitation Windows**. Pick the measurement in the workspace list (drop a TTTR file
on ChiSurf to add it) — or press **Load example** for a simulated PIE measurement whose answer is
known — and, above it, the detector setup to check.

```{figure} figures/115_excitation_windows_check.png
:width: 90%

The simulated PIE demo (32 ps channels, 3125 per 100 ns; donor pulse at 2 ns, acceptor pulse at
52 ns) checked against a setup made for an SPC-130 (50 ps channels, prompt 0–2048, delayed
2048–4095). The windows are converted to 32 ps channels (0–3200 / 3200–6398, grey lines) and
found wrong: *delayed* lies beyond the data, *prompt* holds both pulses. Orange: the detected
windows, prompt 50–1613 (donor excitation, both detectors lit) and delayed 1613–3125 (acceptor
excitation, the donor detector dark).
```

**Use detected windows** saves the setup with the detected windows (and the channel width they
are in) into the workspace; **Keep current windows** changes nothing.

```{figure} figures/115_excitation_windows_donor_only.png
:width: 90%

The same measurement without its acceptor pulse (a donor-only sample): one pulse, so windows
cannot be placed from it. The tool says so and *Use detected windows* stays off; the range
findings about the setup's windows are still listed.
```

## 2. In the setup editor: Auto-detect

In **Setup: Channel Definition** read a measurement (**Read**), open **PIE Windows** and press
**Auto-detect**. The same panel opens over the editor; *Use detected windows* writes the windows
into the table and sets *Microtime res. (ps)* to the channel width they are in.

```{figure} figures/115_excitation_windows_setup_editor.png
:width: 90%

Auto-detect in the setup editor, the setup still holding the SPC-130 windows.
```

## 3. During a Record run

Record checks the setup's windows against the live decays once 5000 photons have arrived, and
again whenever the count has doubled. A mismatch puts a warning under **Experiment setup** with
**Update windows** (the next run uses the detected windows; this run is recorded whole) and
**Keep** (asked again only if the decays show another pulse pattern). The run is never
interrupted and nothing changes silently. One pulse only gives an info line: *one excitation
pulse seen — donor-only or not PIE; windows not checked*. The **Decays** dock draws the decays
over micro-time channels with the run's window edges and, on a mismatch, the detected ones in
orange.

A setup whose windows were defined at another channel width (its *Microtime res.*) has them —
and its detectors' micro-time gates — converted to the device's channels when the run starts; the
setup summary says so. The detector gates are checked with the windows: a gate that hides a pulse
its detector sees is reported and *Update windows* opens it to the whole range.

A **µs-ALEX** run keeps its first photons' macro times; the alternation period and the laser
windows are detected from them and held against the run's (*Alternation period* and the two
halves, or windows taken earlier). *Update windows* takes the detected period and windows. Where
the source cannot provide the macro times the panel says *ALEX windows not checked live; checked
when the run is analysed*.

```{figure} figures/115_excitation_windows_record_alex.png
:width: 100%

A µs-ALEX stream alternating every 100 µs, recorded with *Alternation period* 60 µs: the
warning names both periods and offers the detected period and laser windows.
```

```{figure} figures/115_excitation_windows_record.png
:width: 100%

A simulated PIE run under windows of another instrument (prompt 2048–3000, delayed 3000–4000 of
4000 channels): the donor pulse at channel 39 is in no window. Left, the warning with Update
windows / Keep; right, the Decays dock with the run's windows (grey) and the detected ones
(orange, 4 / 2012 / 4000).
```

**From a measurement…** under *Instrument setup* opens the review on an earlier FRET measurement
of the workspace: its windows are detected, converted to this device's channels, and taken when
you press *Use detected windows*. For µs-ALEX it takes the alternation period instead.

## 4. Before burst selection

Burst selection runs the same check on the previewed measurement (**Filter settings › Channel
selection**) and on every file it searches (the run's warnings). On a mismatch it offers **Use
detected windows** for the search; the saved setup is not changed.

```{figure} figures/115_excitation_windows_burst_selection.png
:width: 100%

Burst selection on the demo with the SPC-130 setup: the warning under the micro-time window
choice, with the detected windows on offer.
```

## 5. Every other tool that uses windows or detector gates

All of them run the same pre-flight (`windows_preflight`) on the measurement they open and say
it the same way: one line in the tool's status / warnings / CLI stderr, and — where the tool holds
the setup and its result does not already depend on the ranges — **Use detected windows**, which
takes the detected windows and opens a detector gate that sees none of its pulses. A gate that
keeps one excitation on purpose (BVA's acceptor gated to the prompt pulse, PIE's `R|G`/`R|R` split
of one detector) is fine.

| Tool | What is checked | Offer |
|---|---|---|
| Burst selection | windows + gates of the previewed / every searched file | yes |
| Burst fusion, BID → Analysis | windows + gates of each measurement | yes |
| BVA, 2CDE, burst workflow, H2MM | the streams' micro-time ranges | BVA, H2MM windows |
| MFD Prepare | the gates the bursts were selected with | report only (the bursts depend on them) |
| Background estimate | its gate masks (when asked for warnings) | — |
| Count rate, image browser, trace browser | windows / detector gates of the file shown | yes |
| Pixel tools (intensity, micro time, phasor, N&B), colocalisation, FRC, ICS | detector gates of the image stream | yes |
| PDA (three colours) | the excitation periods per colour | yes |
| fret_check, ALEX Suite / Creator | their own detection is this one | — |

Not window consumers: two-colour PDA (channels only), PDA's time windows (photons/duration),
img_calibration (full micro time), ndXplorer (reads `.bur` columns, not photons).

## 6. Headless: `csc windows`

```bash
csc windows detect run.ptu                 # kind, windows in channels and ns, notes
csc windows detect run.ptu --json
csc windows check run.ptu --setup my.setup.json            # exit 1 on a mismatch
csc windows check run.ptu --setup my.setup.json --write fixed.setup.json
```

RPC: `excitation_windows.detect` (`path`, `setup`, `kind`) and `excitation_windows.check`
(`path`, `setup`).

## 7. Python

```python
from chisurf.core.fluorescence.excitation import (
    detect_windows, check_setup, detect_pie_windows, windows_preflight, windows_message,
)

det = detect_windows("run.ptu")            # pie / alex / single / unclear
det.windows, det.windows_ns(), det.donor_detectors
report = check_setup(setup, "run.ptu")     # status, issues, proposal
report.mismatch, report.summary, report.proposal

# from histograms you already have (one per detector)
det = detect_pie_windows({"G|G": h_green, "R|G": h_red}, resolution_s=32e-12)

# reading a setup is tttrlib's
import tttrlib
tttrlib.setup_windows(setup), tttrlib.setup_gates(setup), tttrlib.setup_micro_time_resolution(setup)
tttrlib.rescale_micro_time_ranges(setup["windows"], 50e-12, 32e-12)   # another TAC / binning

# what an analysis runs before it uses windows
print(windows_message(windows_preflight(tttr, setup["windows"], detectors=setup["detectors"])))
```

Regenerate the figures with `docs/guides/screenshots/excitation_windows_shot.py`.
