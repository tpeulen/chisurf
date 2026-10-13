---
type: Concept
title: 'TTTR Tools: the two clocks of a photon record'
description: The macro time and micro time of a TTTR record, what each is used for, and which TTTR Tools operation changes which clock; ALEX Creator, Micro-time Shifter, Photon Table, Count Rate Analysis and Audifier.
tags: [concepts, tttr, photons]
anchor: concept-tttr-stream-tools
---

(concept-tttr-stream-tools)=
# TTTR Tools: the two clocks of a photon record

A TTTR file holds one record per detected photon: the detector (routing channel), the **macro time** $t$ and the
**micro time** $\tau$. The TTTR Tools window (`chisurf/plugins/tttr/tttr_toolbox/`) hosts the operations that act on
this stream before any analysis interprets it.

| clock | scale | wraps | builds |
|---|---|---|---|
| macro time $t$ | free-running, ns to hours | no | bursts, correlation curves, count-rate traces |
| micro time $\tau$ | ps across one pulse period $T$ | every $T$ | lifetimes, TCSPC decays, PIE gates |

A tool that moves a photon in one clock leaves the other untouched. That is why these operations are safe, and why they are
easy to misread.

## The tools

- **ALEX Creator** folds alternation encoded in the macro time into the micro time,
  $\varphi = (t - s)\bmod T$, so PIE pipelines can gate the excitation windows. A wrong period $T$ smears the folded
  phase histogram without raising an error ({ref}`concept-us-alex`).
- **Micro-time Shifter** applies a global and a per-channel cyclic offset,
  $\tau' = (\tau + s_\mathrm{global} + s_c)\bmod N$, to put detectors with different delays on one axis
  ({ref}`concept-microtime-shift`).
- **Photon Table** lists the records (routing channel, micro time, macro time) with a channel filter.
- **Count Rate Analysis** reports per-detector count rates $N_c/T_\mathrm{meas}$ over many files, the quickest check for a
  dead detector, bleaching or a closed shutter.
- **Audifier** plays the stream; blinking, bursts and afterpulsing sound different.

**0. Setup** holds the one detector setup (routing, PIE windows, reading calibration, LUTs) that Count Rate Analysis and
Audifier share. File-level operations (split, convert, header) live in [File tools](file_tools.md) (File › Data).

## Rules of thumb

1. These tools write new files; keep the originals.
2. Check the count rates before an analysis: most problems that look like analysis problems show up there.
3. After a micro-time shift, look at the IRF again; it is the only check that the shift went the intended way.

## Workflows

[TTTR Tools window](../guides/101_tttr_toolbox.md), [ALEX Creator](../guides/100_alex_creator.md),
[Micro-time shifter](../guides/88_microtime_shifter.md), [Audifier](../guides/94_tttr_audifier.md).

Tool: Audifier (`chisurf/plugins/tttr/audifier/`).
