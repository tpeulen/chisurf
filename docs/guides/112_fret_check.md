---
type: Guide
title: Checking an smFRET measurement
description: Drop a TTTR file (or simulate an example) into the FRET check, read the quality verdict, check the detected channels, and export the report, the burst table and the QC JSON.
tags: [guides, smfret, bursts, quality-control]
---

# Checking an smFRET measurement

**Spectroscopy › Single-Molecule › FRET check** ({src}`chisurf/plugins/burst/fret_check/app/frame.py`,
package `chisurf/plugins/burst/fret_check/`). Theory: {doc}`../concepts/fret_check`.

One pass over a confocal smFRET measurement: the experiment is detected, the bursts are found,
and a quality verdict names what is wrong. The full burst analysis continues in
{doc}`66_alex_suite` and the burst-selection workflow.

## 0. Open data

Drop a TTTR file on the window — PicoQuant PTU/HT3/T3R/T2, Becker & Hickl SPC, SM, PTO, any
container tttrlib reads. No file at hand: under **Measurement › Try it without a file**,
pick an **Example** and press **Simulate** (5 s simulated by tttrlib's photon simulator: cw,
PIE or µsALEX, with or without polarization, noise channels, one colour). The analysis runs
in the background; **Cancel** stops it, the earlier result stays. Files above 256 MB are read
in chunks.

## 1. Read the verdict (simple mode)

```{figure} figures/112_fret_check_quality.png
:width: 100%

Simple mode after **Simulate** on the *PIE 2c* example. Left, Measurement: 65,671 photons in
5.0 s, detected *2c PIE*, 170 bursts, QC *WARN*. Right, Quality: the basic checks (170 bursts
graded *WARN* below 500, burst density 0.068 *WARN*, multi-molecule events 3.3 % / 4.7 % *OK*,
dilution 1.7× *WARN*) and the two-colour checks, over the 1 s count-rate trace and the
inter-burst gap histogram with the fitted Poisson arrivals.
```

*Overall* is the worst grade. Start with every `WARN`/`BAD` row: hover it for the reason; the
PDF report adds the cause and the fix for each. The gap histogram explains the
multi-molecule estimate — an excess of short gaps on the left of the Poisson curve means
fragmented bursts or revisiting molecules. *Signal stability* needs at least 10 s of data.

```{figure} figures/112_fret_check_es.png
:width: 100%

The same run, **E / S**: the proximity ratio against the stoichiometry with both marginals —
donor-only molecules at S ≈ 1, acceptor-only at S ≈ 0, the two FRET populations at
E ≈ 0.25 and 0.75 around S ≈ 0.55. With cw only E is shown.
```

**Bursts** shows burst size, duration and count rate, and E against the donor lifetime when
the micro time allows it (else FRET-2CDE against E).

## 2. Check the detection (advanced mode)

Switch **Mode** to *Advanced*: the Channels, Burst search and Corrections windows, the Time
trace and ndX appear.

```{figure} figures/112_fret_check_channels.png
:width: 100%

Advanced mode. Left, Channels: excitation *ALEX / PIE*, donor channel 0, acceptor channel 1,
Dex window 255–2301 and Aex window 2301–4091 micro-time channels, over the log-scale
micro-time histogram of both detectors with the windows marked. Right, Bursts: burst size,
duration and count rate histograms, and E against the donor lifetime `Tau (green)`.
```

1. **Channels.** A wrong window or a swapped donor/acceptor breaks everything downstream.
   Edit *Donor*, *Acceptor* (routing channels, comma separated; with polarization parallel
   first) and the *Dex*/*Aex window* (`start-stop`), then **Apply**. **Re-detect** returns to
   what the photons say. Lines starting with `!` in Measurement are guesses the data could not
   settle.
2. **Burst search.** *Min photons*, *m photons* within *T* (µs), *2CDE τ*, and *V_eff* (fL,
   only for the concentration estimate); **Apply**.
3. **Corrections.** **Subtract background** (on: each burst loses its out-of-burst rate × its
   duration, per stream), γ, α, δ, β, or **Auto-calibrate** (ALEX/PIE: all four; cw: α only);
   **Apply**. E/S plots then show the corrected values. **Drop QC-flagged bursts** leaves the
   bright, long and 2CDE-flagged bursts out of the plots, ndX and the CSV.
4. **Time trace.** Each stream in 1 ms bins, donor up, acceptor down, every burst shaded on its
   own; *From* picks the 10 s stretch. Judge the burst search here: shading on every peak and
   none on the flat stretches between them.

```{figure} figures/112_fret_check_trace.png
:width: 100%

Advanced mode on the same run. Left, Corrections: *Subtract background* on, the neutral
factors. Right, Time trace over the 5 s simulation: DD (green) and DA (yellow) up, AA (red)
down, each of the 170 bursts a blue band over its photons.
```
5. **ndX.** The full burst table (counts per stream and detector, E, S, corrected E/S,
   lifetimes, anisotropies, TGX−TRR, 2CDE, QC flags) — pick any two columns and gate.

## 3. Export

| Button | Writes |
| --- | --- |
| **Report (.pdf)** | `<stem>.report.pdf`: verdict, E/S with marginals, count-rate trace, gaps, background, every value and the issues with their fixes |
| **Bursts (.csv)** | `<stem>.bursts.csv`: the burst table under ChiSurf `.bur` column names, QC flags included |
| **QC report (.json)** | `<stem>.qc.json`: the experiment, the burst settings and every check |

On the desktop the files go to `~/Downloads/`; the status line names the path. In the
browser build they download.

## Headless

The RPC methods `fret_check.detect`, `fret_check.analyse` and `fret_check.qc` take the same
JSON as the app's job; in Python:

```python
from chisurf.plugins.burst.fret_check.entry import analyse, detect
from chisurf.plugins.burst.fret_check.jobs import bursts_from_dict, qc_from_dict

exp = detect(path="measurement.ptu")              # or detect(scenario="PIE 2c")
result = analyse(path="measurement.ptu", correct=True, auto_calibrate=True,
                 settings={"min_photons": 30, "m": 10, "T": 500e-6})
print(result["qc"]["level"])                      # the verdict: ok / warn / bad
qc = qc_from_dict(result["qc"])                   # arrays travel packed
print([(c.name, c.level, c.value) for c in qc.checks])
bursts = bursts_from_dict(result["bursts"])       # .E, .S, .columns()
```

`result` holds `detected`, `experiment`, `bursts`, `qc`, `corrected`, `factors`, `trace` and
`micro`. Pass an edited `experiment` dict to analyse with other channels or windows, and
`subtract_background=False` to correct the raw counts. `fret_check.qc` (and `entry.qc`)
returns the `qc` part alone: `level` (the verdict) and every check.
The figures are made by {src}`docs/guides/screenshots/fret_check_shot.py`.
