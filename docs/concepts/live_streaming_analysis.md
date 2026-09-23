---
type: Concept
title: 'Streaming analysis: computing on photons that have not arrived yet'
description: Why a live display must be incremental rather than a batch analysis re-run, what a streaming consumer keeps instead of the photons, and where the streaming and batch answers are identical.
tags: [concepts, acquisition, streaming, correlation, tcspc, mcs]
---

# Streaming analysis: computing on photons that have not arrived yet

An analysis of a finished measurement can read every photon as often as it
likes. A *live* display cannot: photons keep arriving, the measurement has no
end yet, and the display is redrawn while it grows. The two situations look
similar enough that the obvious implementation of the second is the first, run
again on everything so far — and that implementation has a cost that grows
without bound.

## The cost of re-running a batch analysis

Let a measurement produce photons at a constant rate, so after time $t$ there
are $N \propto t$ of them. A batch analysis reads all $N$: one refresh costs
$O(N)$. Refreshing at a fixed rate over the measurement therefore costs

$$
\sum_{k=1}^{K} O(N_k) \;=\; O(K \cdot N) \;=\; O(N^2),
$$

and — the part an operator actually notices — the *last* refresh is the slowest
one. A thirty-minute measurement updates its correlation display more slowly
than a one-minute measurement, and it keeps getting worse for as long as the
measurement runs. Memory behaves the same way if the photons are kept to be
re-read.

A **streaming consumer** instead updates its state from each new chunk and never
looks at the older photons again. One chunk costs $O(\text{chunk})$, a whole
measurement costs $O(N)$, and the cost of a refresh at minute 30 equals the cost
at minute 1. What it keeps is not the photons but a summary whose size is fixed
by the configuration: histogram bins, correlator levels, a rolling window.

## What each live consumer keeps

**Decay histogram.** One counter per micro-time channel per detector. A photon
increments one counter, so the live histogram is *identical* to
`np.bincount` over the saved micro times — not an approximation of it.

**Multi-tau correlator.** Photons are binned into a uniform macro-time trace and
each new sample feeds a cascade of levels, level $b$ running at $2^b$ coarser
resolution — the multi-tau architecture of hardware correlators
{cite}`schatzel1990`. Because the bins are aligned to macro time 0, a level-$b$ bin is
exactly the batch correlator's `t >> b` bin, and the two agree lag for lag.
Memory is the cascade, not the photons: $O(n_\text{bins} \cdot n_\text{casc})$.

The one thing that is *not* identical is the normalisation. $G(\tau)$ divides by
how much measurement a lag actually had — an overlap term $T - \tau$ — and the
streaming correlator counts that from the bins it has emitted while a batch
correlator computes it from the photon times it was handed
{cite}`wahl2003,laurence2006`. On a real stream the
two differ by ~0.1%, everywhere, without a trend across the cascades. A
*cascade-dependent* difference means something else: it is the signature of a lag
misassignment, which reads as an inflated $G$ growing with the cascade.

**Intensity trace (MCS).** Bins of fixed width on the same absolute grid, with
only the newest $m$ retained. The retained window keeps its absolute index, so
the displayed slice is exactly the tail of the batch trace over the same
photons, on the same time axis — a display that shows the last second at 1 ms
resolution costs 1000 numbers however long the measurement runs.

**Burst rate and phasor** ride along on a pass that is already happening. The
burst search keeps the last $m$ macro times in a ring buffer and reports a burst
whenever $m$ consecutive photons span less than $T$ — the sliding-window
search of {cite}`nir2006`; the phasor accumulates $\sum\cos(\omega t_i)$
and $\sum\sin(\omega t_i)$ over micro times and divides by the photon count
{cite}`digman2008`, which is two running sums and a counter for a number that
summarises the whole decay. Neither needs the
photons afterwards.

## Ordering is the assumption they all share

Every consumer above assumes photons arrive in non-decreasing macro time, which
is what a TTTR stream is. It is the assumption that makes them exact rather than
approximate — a bin can be published once nothing can still fall into it — and
it is why a chunk boundary is not an event: a chunk is a delivery, not a unit of
analysis, and the state carried across one is what makes the result independent
of how the photons were chopped up.

The same reasoning applies one level earlier, to decoding: a record stream
carries an overflow counter that makes macro times absolute, and a decoder that
starts each buffer at zero produces a plausible first chunk and nonsense from the
second one on, with nothing raising.

## Further reading

- [Live acquisition](../guides/65_live_acquisition.md) — running one, and what
  each window shows
- [The photon container](photon_container.md) — where a finished measurement goes
- [FCS correlation](fcs_correlation.md) — what $G(\tau)$ means once you have it
- {cite}`schatzel1990` — the multi-tau architecture
- {cite}`wahl2003` — multi-tau correlation computed directly on photon arrival
  times, the batch counterpart
