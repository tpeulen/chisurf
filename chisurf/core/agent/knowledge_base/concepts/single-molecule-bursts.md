---
type: Concept
title: Single-molecule bursts
description: >-
  What a burst measurement contains, why the proximity ratio is not the FRET
  efficiency, and what a sub-ensemble decay is an average over.
tags: [smfret, bursts, tttr, proximity-ratio, setcspc]
timestamp: '2026-07-25T00:00:00Z'
---

# What is being measured

A confocal spot is smaller than a droplet of buffer by many orders of
magnitude, so in a dilute solution it holds **no molecule most of the time**.
When one diffuses through, it fluoresces for the millisecond or so it takes to
cross, and the detectors record a **burst** of photons. Between bursts there is
only scatter and dark counts.

Two things follow, and they are why single-molecule work exists:

* Each burst is **one molecule**, so a mixture shows up as separate populations
  instead of an average. This is the entire point — an ensemble measurement of
  a half-folded protein gives one number that describes neither state.
* Each burst is **short and small**: a few hundred to a few thousand photons.
  That is enough to place a molecule in a population, and not nearly enough to
  fit its decay. Hence sub-ensemble analysis, below.

The raw data is a photon stream (TTTR): for every photon, which detector saw it
(the **routing channel**), when it arrived relative to the experiment (the
**macro time**, ~ns to ms resolution) and when it arrived relative to the laser
pulse (the **micro time**, ~ps resolution). Bursts come from macro times;
lifetimes come from micro times. The same photons carry both.

# Bursts and the .bur table

A burst search marks stretches of the stream where the count rate is high
enough for long enough — a threshold, not a measurement, so its parameters are
part of the result. The output of a Seidel-style analysis is one `.bur` table
per photon file, whose rows are bursts and whose columns include the burst's
**first and last photon index** into that file's stream (end exclusive) and the
photon counts per colour (green/red/yellow).

Because the indices point back into the stream, any per-burst quantity can be
recomputed from the photons themselves — which is what makes sub-ensemble
analysis possible at all, and what makes it worth verifying the indices once
against the recorded per-colour counts.

# Proximity ratio is not efficiency

```
PR = N_red / (N_green + N_red)
```

counted over one burst. It moves with FRET, which is why it separates
populations — but it is **not** the FRET efficiency E, because it ignores:

* **background** in both channels (worst for dim bursts),
* **spectral crosstalk**: donor emission leaking into the acceptor detector,
* **direct excitation** of the acceptor by the donor's laser,
* **γ**, the ratio of detection efficiency × quantum yield between the two
  channels.

Uncorrected, PR is compressed toward the middle: true E of 0 and 1 appear as
maybe 0.05 and 0.95. So PR is a **selection coordinate** — excellent for
choosing molecules, wrong as a reported efficiency. Getting E from intensities
means measuring all four corrections.

The lifetime route avoids them entirely: the donor's decay is quenched by FRET
regardless of how the acceptor's photons were detected.

# Sub-ensemble TCSPC

Take the bursts of one population, pool the **donor-channel** photons of all of
them, and histogram their micro times. Ten thousand photons from four hundred
bursts make a decay that can be fitted, where no single burst could be.

What this buys, and what it costs:

* it is an **average over the selected molecules**, so a heterogeneous
  population returns a mixture, and the fitted components are not necessarily
  states;
* it inherits the selection — a different window gives a different decay, so
  the window is part of the result;
* it needs an **instrument response**, which burst measurements rarely include.
  One can be estimated from the non-burst photons of the same measurement, but
  that estimate is contaminated by the fluorescence of molecules too dim to
  trigger a burst. Fitting every population against the same IRF makes the
  resulting bias largely cancel in *ratios* of lifetimes, which is what an
  efficiency is made of.

# The donor-only population is the reference

The low-PR peak in almost every FRET measurement is molecules whose acceptor is
absent, bleached or dark. Their donor is unquenched, so their sub-ensemble
decay gives τ_D(0) — from the same sample, buffer, instrument and day as the
FRET population. That is a better reference than a separately prepared
donor-only sample, and it is free.

With it:

```
E = 1 - <tau>x(DA) / <tau>x(D0)          R = R0 (1/E - 1)^(1/6)
```

using the **species-weighted** lifetime (see
[FRET from lifetimes](fret-from-lifetimes.md)).

# The check worth making

E from the donor lifetime and the proximity ratio of the same population come
from independent observables. On a clean measurement they agree — a PR
0.5–0.7 selection gives E ≈ 0.53 from the lifetime. When they disagree it is
information, not noise: lifetime-E well below PR points at acceptor-channel
background or crosstalk inflating PR; well above points at donor quenching that
is not FRET (a nearby tryptophan, a bad label), in which case the distance is
not a distance.
