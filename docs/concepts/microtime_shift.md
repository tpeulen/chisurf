---
type: Concept
title: 'Micro-time shift: putting detectors on one time axis'
description: Why two detectors of one TCSPC measurement need different micro-time offsets, what a cyclic shift does to the photon stream, and how the rising edge of the instrument response is used to align them.
tags: [concepts, tcspc, tttr, micro-time, detectors, pie]
anchor: concept-microtime-shift
---

(concept-microtime-shift)=
# Micro-time shift: putting detectors on one time axis

A TCSPC card stamps every photon with a **micro time**: the number of the
time bin, out of $N$, between the photon and the next excitation pulse (see
{ref}`concept-tcspc-lifetime`). The bin is only meaningful relative to the
laser: a detector behind a longer cable, a slower amplifier or a longer optical
path delivers the same photon a few hundred picoseconds later, and the whole
decay of that detector sits at a different place on the axis. Two detectors
that look at the same sample therefore show the **same decay at different
offsets**, and anything that treats the axis as common — a lifetime fit with
one IRF, a PIE or time-gating window, a combined decay of two polarisation
channels, a per-pixel phasor — is wrong by the offset.

## The cyclic shift

The micro-time axis is periodic: bin $N-1$ is followed by the next pulse's
bin $0$. The shift is therefore **cyclic**. A photon of routing channel $c$
in bin $b$ moves to

$$
b' = \bigl(b + s_{\mathrm{global}} + s_c\bigr) \bmod N,
$$

where $s_{\mathrm{global}}$ moves every channel and $s_c$ is that channel's
own shift. Nothing is lost and nothing is created: the micro time of every
photon of channel $c$ is moved, the macro times and routing channels are
untouched, and the photon count is unchanged. A decay that straddles bin 0
after the shift is still one connected decay, because the wrap is the same
wrap the laser repetition makes.

## Aligning on the rising edge

The offset of a detector is read from the **rising edge of its response**,
where the signal climbs out of the background: the edge is steep, so a small
change of the threshold moves it by a fraction of a bin, whereas the peak of
a broad decay is imprecise. ChiSurf takes, per detector, the first bin up to
the maximum whose counts reach the **trigger level** (a count threshold you
choose above the background and below the peak). If $e_c$ is that bin and
$t$ the **target bin** where all edges should land,

$$
s_c = (t - e_c) \bmod N .
$$

A level below the background makes the edge the first bin (the shift is then
meaningless); a level above the peak falls back to the peak bin. The level is
a judgement about the data, which is why it is drawn on the histogram as a
line you can drag.

Aligning by the edge assumes the detectors see **the same excitation
geometry**: the same pulse and a prompt component (scatter, a short-lived
dye) with a sharp rise. For a pure long-lived decay without prompt signal the
edge is the pulse's convolution with the detector response; it is still the
right alignment for *relative* offsets between equal detectors, but not an
absolute zero, which belongs to the IRF fit
({ref}`concept-tcspc-lifetime`).

## What is not corrected

The shift moves whole bins. A sub-bin offset (a fraction of the $12.5\,
\mathrm{ns}/4096 \approx 3\,\mathrm{ps}$ bin of a typical card is far below
any detector's timing jitter) is not resolved; the differential non-linearity
of the card ({ref}`concept-tcspc-lifetime`, nuisance terms) and the
**different IRF shapes** of the detectors remain, so a joint lifetime fit
still needs one IRF per detector.

## See also

- Workflow: {doc}`/guides/88_microtime_shifter` (queue files, align, save,
  archive).
- Where the shifted files go next: detector setup and PIE windows
  ({doc}`/guides/87_channel_definition`), decays
  ({doc}`/guides/73_tttr_decay_and_correlation`).
- Implementation: {src}`chisurf/core/fio/tttr_shift.py` (the photon-level
  shift, shared with the reading seam), {src}`chisurf/plugins/tttr/tttr_microtime_shifter/gui/app.py`
  (the window and the rising-edge search).
- Key literature: {cite}`becker2005` (TCSPC instrumentation, detector and
  cable delays); {cite}`wahl2015` (timing electronics).
