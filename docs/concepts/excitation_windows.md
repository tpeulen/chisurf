---
type: Concept
title: Excitation windows — finding the PIE pulses and the ALEX alternation in the data
description: How ChiSurf detects the excitation pulses of a PIE measurement in the micro time (and the µs-ALEX alternation in the macro time), proposes prompt/delayed windows, and checks a setup's windows against the data.
tags: [concepts, smfret, pie, alex, setup, windows]
---

# Excitation windows

Pulsed interleaved excitation (PIE, nsALEX) separates donor and acceptor excitation in the
**micro time**: every sync period holds a donor-laser pulse and, a few tens of nanoseconds later,
an acceptor-laser pulse. µs-ALEX alternates the lasers in the **macro time**, over tens of
microseconds. Either way an analysis needs *windows* — which photons were excited by which laser —
and the windows are numbers a user types once into a detector setup. When the instrument changes
(another TCSPC, another binning, another sync offset) the numbers stop meaning anything, and
nothing downstream fails: the stoichiometry histogram just loses its populations.

ChiSurf therefore finds the excitations **in the data** and holds every set of windows against
them. The method is `chisurf.core.fluorescence.excitation` (Qt-free); the Excitation Windows
tool, the setup editor's *Auto-detect*, the Record tool during a run and burst selection all call
the same detection and the same check. Workflow: {doc}`../guides/115_excitation_windows`.

## 1. PIE: rising edges in the micro time

A laser pulse shows in a micro-time histogram as a **rising edge** (the instrument response)
followed by a decay. A decay never rises. So the number of rising edges is the number of
excitation pulses, whatever the lifetimes, the shape of the IRF, the background or the
afterpulsing.

For each detector, and for their sum:

1. The histogram (``n`` channels per sync period) is binned to about 256 coarse bins of
   ``k = n // 256`` channels, and treated as **circular** — a pulse near the end of the range
   decays into its start, and the sync offset can put a rise anywhere.
2. A bin ``i`` is a rise when, with ``p_i`` the lowest of the three bins before it and
   ``l_i = (h_i + h_{i+1}) / 2`` the level after it,

   ```{math}
   h_i - p_i > f\,(h_{\max} - h_{10\%}), \quad
   l_i - p_i > f\,(h_{\max} - h_{10\%}), \quad
   l_i - p_i > 5\sqrt{p_i + l_i}
   ```

   with ``f = 0.15``: a sizeable fraction of the detector's dynamic range, held over two bins (a
   single noisy bin is not a pulse) and five Poisson sigmas of the difference. Rise bins within
   two of each other are one edge. Edges of all detectors closer than 1.5 ns are one pulse.
3. At full resolution the rise is where the smoothed signal first crosses 20 % of its step;
   the peak follows, and the pulse **core** ends where the signal is back below half height.
4. **Windows** tile the period: each starts 0.3 ns before its pulse's rise and ends where the
   next one starts. A window that wraps around the end of the range keeps the part holding its
   pulse, and says how much it left out.
5. **Roles.** Per window and detector the background-corrected rate (background: the 10th
   percentile of the coarse histogram). A detector below 15 % of its brightest window is *dark*
   there. Under acceptor excitation the donor detectors are dark — that labels the window
   ``delayed`` (acceptor excitation) and the dark detectors as the donor's, whatever the order of
   the pulses in the range. Two pulses are ``prompt``/``delayed``; more (a sync divider, three
   lasers) get one window each, ``pulse1``, ``pulse2``, …, with their roles.

| Outcome | Meaning | What happens |
|---|---|---|
| ``pie`` | two or more pulses | windows proposed in channels and ns |
| ``single`` | one pulse: a donor-only sample, or no PIE | reported; nothing proposed, nothing changed |
| ``unclear`` | no edge (cw excitation, background only) or too few photons (< 1000) | reported |

A donor-only sample excited by both lasers still shows **one** pulse: the acceptor laser
excites nothing that emits. The windows cannot be placed from such data — that is said, not
raised as an error.

## 2. µs-ALEX: the alternation in the macro time

When the micro time shows no PIE (flat, or one pulse) and two detectors carry photons, the
macro time is searched for an alternation — the methods of the ALEX Creator, which now live in
`chisurf.core.fluorescence.excitation.alex`: the signed donor−acceptor stream's spectrum gives
the period (searched between 2 µs and 2 ms, so slow intensity drift is not taken for an
alternation; a contrast under 50× is refused), the folded phase gives which detector is dark
under acceptor excitation (the donor; a contrast above 0.5 is no alternation), and the occupied
plateaus of the phase give the two laser windows, trimmed by a guard at each edge. The windows
are phases of the period in macro-time ticks; ``prompt`` is the donor laser.

## 3. Checking existing windows

`check_windows` / `check_setup` hold a set of windows against a detection:

| Finding | Severity |
|---|---|
| windows defined in channels of another width — converted, then checked | warning |
| a window starts beyond the data's range (it is empty) | error |
| a window ends far beyond the range | warning |
| the data clearly alternates, there are no windows | warning |
| a pulse rises in no window | warning |
| a window boundary inside a pulse (between its rise and half-height decay) | warning |
| one window holds two pulses (its photons mix the excitations) | warning |
| ``prompt`` holds the acceptor's pulse and ``delayed`` the donor's | warning |
| a window holds < 0.5 % of the photons | warning |
| µs-ALEX windows made for another alternation period (off by > 0.5 %) | warning |
| a detector's micro-time gate starts beyond the data (the detector sees nothing) | error |
| a detector's gate hides a pulse that detector sees | warning |
| a detector's gate holds < 5 % of its photons | warning |
| one pulse / unclear: nothing checked against pulses | info |

A warning or an error is a **mismatch**; the check then offers the detected windows (or, when
only the channel width was off, the converted ones) and, for a detector whose gate is broken, the
whole range as its gate. It never applies them: the user decides (`apply_check` writes windows,
gates and their channel width into a setup).

## 4. Windows carry their channel width

A setup's windows **and its detectors' micro-time gates** (``micro_time_ranges``) are raw
micro-time channels of the resolution in its ``tttr_reading.micro_time_resolution`` — in
**picoseconds**, as the setup editor writes it (tttrlib's `StreamingBurstAnalyzer.from_setup`
reads it in ps too; ``micro_time_resolution_unit: "ns"`` marks a setup written in ns). The same nanoseconds are a different number of
channels at another resolution or binning, so every consumer converts
(`tttrlib.rescale_micro_time_ranges`) instead of applying another instrument's channel numbers: a window
``[0, 2048)`` of 50 ps channels is ``[0, 3200)`` of 32 ps channels. Detected windows are stored
with the resolution they were found at.

This was the failure that motivated the feature: a Record run on an MT200 (HydraHarp 400,
32 ps channels, 3125 per 100 ns) with the windows of an SPC-130 setup (50 ps, prompt 0–2048,
delayed 2048–4095). Unconverted, the windows cut the 3125 channels in the wrong place; the live
Decays dock also drew its 1024-bin decay against bin numbers while the windows were in channels,
so window edges and pulses could not be compared by eye.

**Where it lives.** Reading a setup -- detectors, gates, windows, their channel width, the window x
detector stream map, the half-open/inclusive range dialects, rescaling, the photon mask -- is
tttrlib's (`tttrlib.setup_detectors`, `setup_gates`, `setup_micro_time_resolution`,
`setup_channel_map`, `ranges_to_inclusive`, `rescale_micro_time_ranges`, `micro_time_mask`): one
reader for tttrlib's `StreamingBurstAnalyzer.from_setup`, ChiSurf and ndXplorer. The pulse and
ALEX detection and the check are ChiSurf's (`chisurf.core.fluorescence.excitation`), used by every
tool through one pre-flight.

## 5. Assumptions and limits

* Pulses are separated by more than 1.5 ns and the IRF rises within a few coarse bins.
* The background is roughly flat (it is estimated as the 10th percentile).
* Detector roles need two detectors with one dark under some pulse. With one detector, or no
  acceptor in the sample, which pulse excites the donor is unknown: ``prompt`` is the first.
* µs-ALEX needs enough alternation cycles and two detection bands; periods outside 2 µs–2 ms are
  not searched. In the Record tool a µs-ALEX run keeps its first 2 M photons' macro times for the
  live check; a source that cannot provide them gets an info line instead.
* Very low count rates: below 1000 photons nothing is decided; the Record tool waits for 5000
  photons and looks again whenever the count has doubled.

## Further reading

* Müller, Zaychikov, Bräuchle & Lamb, *Pulsed interleaved excitation*, Biophys. J. 89 (2005) 3508,
  [10.1529/biophysj.105.064766](https://doi.org/10.1529/biophysj.105.064766)
* Kapanidis et al., *Alternating-laser excitation of single molecules*, Acc. Chem. Res. 38 (2005) 523,
  [10.1021/ar0401348](https://doi.org/10.1021/ar0401348)
* {doc}`us_alex`, {doc}`fret_check`, {doc}`detector_setup`
