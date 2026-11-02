---
type: Concept
title: FRET check — is this smFRET measurement usable?
description: How the FRET check detects the experiment from the photons, finds and reduces the bursts, corrects E and S, and grades the measurement with a fixed set of quality checks.
tags: [concepts, smfret, bursts, quality-control, alex, pie]
---

# FRET check — is this smFRET measurement usable?

The FRET check (`chisurf/plugins/burst/fret_check/`) answers one question about a
confocal single-molecule FRET measurement of diffusing molecules: *is it usable, and which
bursts should not be trusted?* It reads a TTTR file (any container tttrlib reads), guesses how
the experiment was recorded, runs a default burst search and grades the result. Every guess
is a starting point the advanced mode can edit. The burst analysis proper —
selections, sub-ensembles, fits — is {doc}`smfret_bursts`; accurate corrections and their
calibration are {doc}`accurate_fret`.

## 1. Detecting the experiment

`detect.detect_experiment` reads the photons, not the header:

* **Signal channels.** Routing channels with under 0.1 % of the photons (markers, crosstalk
  lines) are dropped. A default burst search then runs on all photons; a channel whose
  in-burst count rate is not at least twice its out-of-burst rate, or that holds under 0.5 %
  of the burst photons, carries no single-molecule signal (dark counts, scatter, an unused
  detector) and is listed as *unassigned*, with a warning.
* **Alternation in the micro time (PIE / nsALEX, or µsALEX already folded).** Per channel the
  micro time is binned into 64 coarse bins and searched for excitation onsets — steep rises
  above Poisson noise. Alternation is a pair of onsets whose second window leaves some — not
  all — channels dark: a donor detector is *dark* when its mean count per bin in the
  acceptor-excitation window is below 0.15 of its mean in the donor-excitation window. The
  dark channels are the donor detectors, the others the acceptor detectors; the two windows are
  the Dex and Aex windows.
* **Alternation only in the macro time (µsALEX).** `find_alex_period` bins each channel's
  count rate in 5 µs bins and takes the strongest peak of its spectrum between 1 and 50 kHz,
  if it stands at least 30× above the band's median; the period is refined (±0.5 %) to the
  integer number of macro-time ticks whose fold has the deepest per-channel contrast. The data are then re-read with the phase
  `macro % period` as micro time (`with_phase`), so every later step treats µsALEX like PIE.
* **cw.** One excitation. Donor and acceptor are assigned from the bursts (`assign_cw`):
  channels of one colour rise and fall together from burst to burst, and the donor colour is
  the one with bursts of its own (donor-only molecules). Without a donor-only population the
  data cannot settle it; the guess is a warning.
* **Polarization.** Two channels per colour are a parallel/perpendicular pair, the brighter
  taken as parallel.

The result is an `Experiment`: its `kind` reads `1c`, `2c cw`, `2c PIE`, `2c µsALEX` or
`MFD (… + pol)`; `warnings` lists what the data could not settle.

## 2. Streams and the burst search

Photons are routed into three streams (`pipeline.photon_streams`): DD (donor excitation,
donor emission), DA (donor excitation, acceptor emission) and AA (acceptor excitation,
acceptor emission); AD is dropped. Without alternation every photon is under donor excitation
and AA is empty.

The burst search is tttrlib's all-photon sliding window
([10.1016/S0168-1656(00)00412-0](https://doi.org/10.1016/S0168-1656(00)00412-0),
[10.1021/jp063483n](https://doi.org/10.1021/jp063483n)): a burst is where *m* consecutive
photons arrive within *T*; overlapping ranges are merged and bursts with fewer than
*Min photons* dropped. Defaults (`BurstSettings`): `min_photons = 30`, `m = 10`,
`T = 500 µs`. The background of each stream is its count rate outside the bursts.

Per burst (`Bursts.columns`, ChiSurf/Seidel `.bur` names, so ndX and ChiSurf read the table):

| Quantity | Definition |
| --- | --- |
| Proximity ratio $E$ | $I_{DA} / (I_{DD} + I_{DA})$ |
| Stoichiometry $S$ (ALEX/PIE) | $(I_{DD} + I_{DA}) / (I_{DD} + I_{DA} + I_{AA})$ ([10.1073/pnas.0401787101](https://doi.org/10.1073/pnas.0401787101), [10.1529/biophysj.105.064766](https://doi.org/10.1529/biophysj.105.064766)) |
| FRET-2CDE, ALEX-2CDE | tttrlib `TwoCDE`, Laplace kernel of width `cde_tau` (default 100 µs) ([10.1016/j.bpj.2012.01.012](https://doi.org/10.1016/j.bpj.2012.01.012)) |
| `Tau (G\|G)`, `Tau (R\|R)` | mean micro time of the burst's DD (AA) photons after the half-rise of that stream's whole decay — model-free, no IRF; TCSPC micro time only, not µsALEX |
| `r Experimental (G\|G)`, `r Experimental (R\|G)` | $(I_\parallel - G I_\perp)/(I_\parallel + 2 G I_\perp)$ with $G = 1$, no $l_1/l_2$ or background correction (polarization only) |
| `TGX-TRR` | mean macro time of donor-excited minus acceptor-excited photons, ms (ALEX/PIE) |

These are the apparent values, from the raw counts; the background comes off in the corrected ones (section 3).

## 3. Corrected E and S

In advanced mode `jobs.corrections` first takes each burst's expected background off its
counts (`jobs.background_counts`): per stream $s$,

$$I_s \leftarrow I_s - B_s\,T,$$

with $B_s$ the stream's count rate outside the bursts and $T$ the burst duration. Burst
durations differ, so this is done per burst rather than with tttrlib's single `bg_*` count
(which is then zero). *Subtract background* (Corrections, on by default;
`subtract_background=False` in the API) turns it off. Left in, an equal background in both
channels pulls a low-$E$ population towards 0.5: on a cw simulation at $E = 0.2$ with about
2.2 kHz background per stream the median corrected $E$ is 0.199 with and 0.218 without the
subtraction (`tests/test_background.py`). The calibration below sees the background-free
counts too. Then `tttrlib.accurate_fret` corrects them with the factors γ (detection and
quantum-yield ratio), α (leakage), δ (direct excitation)
and β (excitation ratio) ([10.1529/biophysj.104.054114](https://doi.org/10.1529/biophysj.104.054114),
[10.1038/s41592-018-0085-0](https://doi.org/10.1038/s41592-018-0085-0)). Defaults are neutral (γ = β = 1, α = δ = 0). *Auto-calibrate* fills
the factors from the measurement:

* **ALEX/PIE** — all four from `tttrlib.auto_calibrate` (donor-only and acceptor-only
  populations, the FRET populations' $1/S$ against $E$).
* **cw** — only the leakage α, from the bursts with $E < 0.15$ (at least 20 of them,
  `tttrlib.leakage_from_donor_only`); γ, β and δ need a reference and stay as typed.

## 4. The quality checks

`qc.run_qc` grades each check `ok`, `warn` or `bad`, or `info` when it only reports a number;
the overall verdict is the worst grade (`level` of the packed report, the answer of the
`fret_check.qc` RPC). For a check graded by `_level(value, ok, warn)`:
`ok` below the first limit, `warn` below the second, `bad` above.

Every measurement (cw or ALEX/PIE, one or two colours):

| Check | Value | ok / warn / bad |
| --- | --- | --- |
| bursts | bursts after the size filter, and their rate | ≥ 500 / ≥ 100 / fewer |
| burst density | occupancy $\lambda$ = burst rate × mean burst duration | < 0.05 / < 0.2 / ≥ 0.2 |
| multi-molecule events | $\max(P_\mathrm{occ}, P_\mathrm{gaps})$, below | < 5 % / < 15 % / ≥ 15 % |
| short gaps | gaps < 2 median burst durations, observed / expected | < 2 / < 5 / ≥ 5 (info under 300 bursts) |
| concentration | $\lambda / (N_A V_\mathrm{eff})$, $V_\mathrm{eff}$ = 1 fL unless set | info |
| dilution | $\lambda / \lambda_{2\%}$, the factor to reach 2 % multi-molecule events | ≤ 1 info / < 3 warn / bad |
| time in bursts | summed burst duration / measurement duration | < 10 % / < 30 % / ≥ 30 % |
| brightness | median in-burst count rate minus total background | info |
| signal / background | brightness / total background | > 10 / > 3 / ≤ 3 (info without out-of-burst time) |
| background (kHz) | count rate outside bursts per stream | info |
| signal stability | drift and spikes of the 1 s count-rate trace (≥ 10 s of data) | \|drift\| < 15 % and no spike / \|drift\| < 40 % and < 3 spikes / else |
| bright bursts, long bursts | fraction above the Tukey fence $Q_3 + 3\,\mathrm{IQR}$ on $\log_{10}$ count rate (duration) | < 2 % / < 5 % / ≥ 5 % |

The two multi-molecule estimates:

* from the occupancy, Poisson:
  $P_\mathrm{occ} = P(\ge 2 \mid \ge 1) = (1 - e^{-\lambda} - \lambda e^{-\lambda}) / (1 - e^{-\lambda})$;
* from the gaps between bursts: molecule arrivals are Poisson, so beyond 5 median burst
  durations (where blinking does not reach) the gap histogram is exponential; the maximum-
  likelihood rate $r$ of that tail gives $P_\mathrm{gaps} = \langle 1 - e^{-r d} \rangle$ over
  the burst durations $d$. It does not depend on the burst search having separated close
  molecules. At least 20 bursts and 10 tail gaps are needed.

Signal stability fits a line to the 1 s trace (the partial last bin dropped): drift is the
slope × duration over the mean rate; a spike is a bin above median + 8 MAD (MAD × 1.4826).

Two colours (an acceptor channel is assigned):

| Check | Value | ok / warn / bad |
| --- | --- | --- |
| donor-only / acceptor-only (ALEX/PIE) | fraction with $S > 0.8$ / $S < 0.25$; graded on the larger | < 40 % / < 70 % / ≥ 70 % |
| low-E / donor-only (cw) | fraction with $E < 0.15$ — donor-only and very low FRET cannot be told apart | < 40 % / < 70 % / ≥ 70 % |
| FRET-2CDE > 30 | fraction of bursts | < 15 % / < 35 % / ≥ 35 % |
| ALEX-2CDE > 30 (ALEX/PIE) | fraction of bursts | < 15 % / < 35 % / ≥ 35 % |

Each burst also carries flag bits (`qc.burst_flags`): bright, long, FRET-2CDE > 30,
ALEX-2CDE > 30. *Drop QC-flagged bursts* leaves them out of the plots, ndX and the CSV.

## Assumptions and limits

* The comfort zones describe a healthy confocal run of diffusing molecules; `warn` means
  *look*, `bad` means *fix before publishing*. They are not a model of a specific instrument.
* The concentration scales with the assumed $V_\mathrm{eff}$ (from FCS or a dye standard).
* The background is one rate per stream over the whole measurement; a drifting background is
  subtracted at its mean. With cw only α comes from the data.
* Files above 256 MB (`limits.LARGE_BYTES`) are analysed in chunks (`chunked.analyse_chunked`):
  the experiment is detected on the first chunk and a burst near a chunk edge is carried into
  the next one, so no burst is cut; memory stays flat.

## See also

- {doc}`../guides/112_fret_check` — the workflow: open or simulate a measurement, read the verdict, check the detection, export.
- {doc}`smfret_bursts` — the burst analysis proper; {doc}`accurate_fret` — the corrections and their calibration.
