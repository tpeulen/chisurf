# Burst Variance Analysis

BVA asks one question of every burst: *was the FRET efficiency constant while the
molecule crossed the focus, or did it change?*

A genuinely static molecule can only vary its apparent efficiency through **shot
noise** — the random way a finite number of photons partitions into donor and
acceptor counts. A molecule that interconverts *during* the burst adds variance
on top of that floor. BVA makes the excess visible.

Press **Guide** for the walk-through.

## What is computed

Each burst is sliced into consecutive sub-windows of *n* photons. Every slice
gets its own proximity ratio E_i = n_A/n, and the burst contributes one point:
its mean efficiency against the **standard deviation of its slices**.

The comparison is not against zero. If the molecule is static, the acceptor count
in a slice is binomial, so the per-slice efficiency has standard deviation

**σ_sn(E) = √( E(1−E) / n )**

— the **static line**, a semicircle-like curve, zero at E = 0 and E = 1 and
largest at ½, narrowing as *n* grows. ChiSurf draws it by Monte-Carlo binomial
sampling rather than from the closed form, which captures the small bias of the
discrete estimator at low *n* and at the edges.

The numbers are larger than intuition suggests. At n = 5 photons a **perfectly
static** molecule at E = 0.5 still scatters by σ = √(0.25/5) = **0.224** — more
than ±0.2 in apparent efficiency, from shot noise alone. At n = 20 it is 0.112.
That is why "how much do the sub-efficiencies vary" is a meaningless question
without the floor drawn next to it.

## Reading the plot

- **On the line** — static on the burst timescale. A folded protein, a rigid
  labelled duplex, a donor-only species.
- **Clearly above the line** — excess variance: the molecules visit at least two
  FRET states *within* one burst. The height above the line grows with the
  amplitude of the change and with the exchange rate relative to the burst
  duration.
- **An arch bridging two spots** — the signature of two-state exchange, and it
  survives even when the time-averaged *E* histogram shows a single smeared peak.

Two static species that are *not* interconverting give two separate spots **on**
the line, not an arch. That distinction is the whole point of the plot.

## The settings that decide the answer

**Photons per slice** trades stability against time resolution. Small *n* gives
many slices and sensitivity to fast exchange, but a noisier per-burst σ and a
taller static line; large *n* smooths σ and lowers the line but goes blind to the
fastest dynamics. Typical values are 5–10. The **same** *n* must be used for the
data and for the static line — the tick box in the toolbar redraws the line for
the value the run used.

**Min window length** is the alternative slicing by a fixed time rather than a
fixed photon count, which is the right choice when the count rate varies strongly
across a burst.

**Donor and acceptor detectors** come from the detector setup on the *Channel
Definitions* tab. Get them backwards and the analysis still completes.

## Before believing the result

"Above the static line" means *excess variance*. It does not mean *conformational
dynamics*, and everything below produces it too:

- **Acceptor blinking or bleaching** — a dye going dark mid-burst is exactly the
  two-level signal BVA detects, and it is the single most common false positive.
  Bleaching is irreversible, so it biases the *late* slices; an ALEX stoichiometry
  filter or a photon-by-photon check separates it from real exchange.
- **Background, and its drift.** Background photons are uncorrelated with the
  molecule, so they pull the mean toward the background ratio and inflate the
  scatter — worst in dim bursts. The static line is computed for *pure* binomial
  sampling, so uncorrected background lifts the whole population off it.
- **Crosstalk and direct excitation** compress the accessible *E* range, moving
  the population relative to the line without changing its variance.
- **Too few slices.** A σ estimated from *m* slices carries a relative
  uncertainty of order 1/√(2m), so short bursts scatter widely in *both*
  directions. Apply a minimum photon count and read the density, not individual
  points.
- **Linker dynamics, dye sticking, rotational states** — real distance or
  quantum-yield changes that are not the process you are asking about.

**A negative result rules out dynamics in one window only.** BVA sees exchange
between roughly the slice duration and the burst duration — about 10⁻⁴ to 10⁻³ s
for a 1 ms burst and a 5-photon slice at 50 kHz. Faster exchange averages inside
every slice and looks static; slower exchange catches each molecule in one state
and gives two static spots. Filtered-FCS and ns-FCS cover the faster decades;
recurrence analysis and binned-trace HMMs the slower ones.

BVA is a **screen, not a proof**: it says something varies more than shot noise.
The photophysical explanations have to be excluded before the conformational one
is accepted.

## Further reading

- [Burst variance analysis](docs/concepts/bva.md) — the derivation, in full.
- [Burst variance analysis, step by step](docs/guides/08_burst_variance_analysis.md)
- [FRET-2CDE and ALEX-2CDE](docs/concepts/burst_2cde.md) — the same question
  asked through photon kernel densities instead of variance.
- [Photon-by-photon HMM](docs/concepts/h2mm.md) — what quantifies the dynamics
  BVA only flags.
- [Single-molecule FRET bursts](docs/concepts/smfret_bursts.md)
- Torella, Holden, Santoso, Hohlbein, Kapanidis, *Identifying molecular dynamics
  in single-molecule FRET experiments with burst variance analysis*,
  Biophys. J. **100**, 1568–1577 (2011),
  [10.1016/j.bpj.2011.01.066](https://doi.org/10.1016/j.bpj.2011.01.066)
