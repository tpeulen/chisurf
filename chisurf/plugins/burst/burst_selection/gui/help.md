# Burst selection — deciding what a burst is

This is the step every later burst number depends on. It reads raw TTTR files,
finds the bursts, filters them, and writes a burst folder that BVA, 2CDE, MLE,
H2MM and the FRET histograms all consume. Change something here and every
downstream result changes with it.

Press **Guide** for the walk-through.

## How a burst is found

A measurement is a long timestamp stream that is mostly background. The
**sliding-window** search runs a window of *m* consecutive photons along it and
computes the instantaneous count rate — *m* divided by the time those photons
span. A burst opens where that rate rises above a threshold set **relative to
the local background**, typically a factor *F* ≈ 6 with *m* ≈ 10, and closes when
it falls back.

Tying the threshold to the *local* background is the part that matters. Laser
power and buffer conditions drift over a long acquisition; a fixed rate threshold
silently changes what it selects as they do, and a background-relative one does
not.

In ALEX you can additionally demand a coincident rate rise in **both** excitation
streams — a dual-channel search, which rejects singly-labelled species before
they ever reach the histogram.

## The setting people get wrong

**Do not put the size cut inside the search.** Search permissively (*L* = *m*)
and apply the real minimum-photon cut afterwards, on the **background-corrected**
size. A size cut applied during the search interacts with the threshold and
biases *which molecules you ever see* — dim molecules are removed preferentially,
and dim usually correlates with something you care about.

## The channel definition

The detector setup says which physical channel is donor, which is acceptor, and
which excitation period each belongs to. Nothing downstream re-checks it. A
swapped assignment produces a complete, plausible analysis with *E* reflected
about ½, and there is no fit statistic anywhere that reports it. Set it once,
against the hardware, and confirm it on a sample whose answer you know.

## Reading the diagnostic tabs

**dT** — inter-photon times. The background shows as a broad exponential; bursts
are the short-time excess. If there is no clear excess, the search has nothing to
find and no threshold will conjure it.

**Burst length** — how many photons per burst. Should fall smoothly. A spike at
the minimum means the cut is doing the selecting.

**MCS** — the intensity trace over time. This is where you see photobleaching,
a drifting focus, or an aggregate crossing.

**Decay** — the micro-time histogram of the selected photons, which is what any
lifetime fit will be run on.

**Summary** — counts and rates for the whole run.

## Before you go on

1. **Vary the threshold by a factor of two.** A real population survives it. If
   the burst count and the histogram both move a lot, you are selecting the
   threshold, not the sample.
2. **Look at MCS across the whole file** before trusting any average over it.
3. **Check the donor-only population lands where it should** once corrections are
   applied downstream — the earliest sign that the channel definition is wrong.

It also runs headless: `csc burst-selection --help`.

## Further reading

- [Single-molecule FRET: bursts, E, S and the corrections](docs/concepts/smfret_bursts.md)
- [Finding bursts, step by step](docs/guides/13_burst_identification.md)
- [Background rates](docs/guides/15_background_rates.md)
- [Timestamps and bursts](docs/guides/33_timestamps_and_bursts.md)
- [Selecting FRET populations](docs/guides/28_selecting_fret_populations.md)
- [Exporting burst data](docs/guides/34_exporting_burst_data.md)
