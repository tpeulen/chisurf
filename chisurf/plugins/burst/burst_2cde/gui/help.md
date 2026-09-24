# FRET-2CDE and ALEX-2CDE

A burst's mean FRET efficiency says *where* the molecule sat on the *E* axis. It
does not say whether it **stayed** there. A molecule that switches between a low-
and a high-FRET state while it crosses the focus produces one burst at some
intermediate efficiency — on the *E* histogram it is indistinguishable from a
genuinely static intermediate.

2CDE (Tomov *et al.* 2012) is a single number per burst that separates the two,
straight from the photon arrival times, with no kinetic model and no binning.

Press **Guide** for the walk-through.

## What is computed

Around every photon, the local **rate** of each colour is estimated with a
kernel centred on its macro time — a symmetric-exponential (Laplace) kernel of
time constant τ, Tomov's original choice, or a Gaussian one. The two colours'
rate time-courses are then compared *within* each burst.

**FRET-2CDE = 110 − 100·[(E)_D + (1−E)_A]** asks whether donor and acceptor
brightness rise and fall **together**. In a static burst they do — both track the
same molecule crossing the beam — the two weighted estimates sum to ≈ 1, and the
score settles near a baseline of **≈ 10 regardless of the actual efficiency**. If
the molecule switches state mid-burst the two colours become anticorrelated in
time (donor bright while acceptor dim, then the reverse) and the score rises,
typically into 30–100 for clear millisecond dynamics.

**ALEX-2CDE = 100 − 50·(BR_Dex + BR_Aex)** (Tomov eq. 12) runs the same machinery on the two
*excitation* streams instead, and scores how uniformly donor and acceptor
brightness are distributed across the burst. It needs ALEX or PIE data. A clean
single molecule with one active donor and one active acceptor is bright in both
streams throughout the burst and lands low; a donor-only or acceptor-only
species, an acceptor that blinks or bleaches mid-burst, or two molecules
coinciding in the volume all push it up.

The two are complementary and not interchangeable: FRET-2CDE reports within-burst
**dynamics**, ALEX-2CDE reports within-burst **brightness heterogeneity**. Where
you have ALEX/PIE data, screen with ALEX-2CDE first — several of the things that
raise FRET-2CDE are impurities, not conformational change.

## The settings that decide the answer

**τ** (default 100 µs) sets the timescale over which brightness is averaged. It
must be short enough to resolve a within-burst change and long enough to collect
several photons per kernel; 40–100 µs sits between the microsecond inter-photon
spacing and the millisecond burst duration.

**Kernel.** Laplace is the published choice and what a comparison with the
literature should use. Gaussian estimates the rate more accurately and depends
far less on where it is evaluated — the Laplace kernel, sampled *at* the photon
positions, always sits on its own peak and over-estimates the rate.

**Donor / acceptor channels** are the physical detector routing channels. Get
them backwards and the analysis still completes and still looks plausible.

**Variant** picks which of the two columns is computed. A run produces one, not
both; `FRET-2CDE` and `ALEX-2CDE` are written into the `2c4/` companion folder
beside the burst tables, one row per burst, so the burst browser and ndX can gate
on them.

## Before believing the result

**τ and the burst duration are a window, and it is the only window.** Exchange
much faster than τ is averaged away inside the kernel and the burst looks static.
Exchange much slower than the ~1 ms transit means the molecule never switched
while you were watching, and it *also* looks static. A FRET-2CDE at baseline
means "no dynamics **in this window**" — never "no dynamics". Re-run with a
different τ before concluding anything.

**The baseline is a statistic, not a constant.** The ≈ 10 static value emerges
from averaging noisy per-photon ratios, so a burst with few photons scatters
around it much more widely than a photon-rich one. A fixed cutoff of 12
consequently flags a larger fraction of *dim* bursts as dynamic purely by shot
noise. Apply a photon-count threshold first, and treat a dynamic fraction as
comparative between similarly filtered datasets rather than as an absolute
number.

**It is a flag, not a rate.** 2CDE says a burst changed. It does not say how
fast, how many states, or in which direction. Use it to *select* dynamic bursts,
then hand them to a method that models kinetics — H2MM for photon-by-photon
rates, PDA for distributions, or a FRET-line analysis.

**Other things raise it.** Acceptor blinking or bleaching mid-burst is a genuine
brightness anticorrelation and lifts FRET-2CDE exactly like a conformational
transition, as does a second molecule entering the volume.

**NaN rows are not zeros.** A burst with an empty donor or acceptor stream has no
two-colour ratio at all and is returned as `NaN`. The status line reports how
many of the bursts were valid; those rows must be dropped, not read as zeros.

## Further reading

- [FRET-2CDE and ALEX-2CDE](docs/concepts/burst_2cde.md) — the derivation, in full.
- [FRET-2CDE, step by step](docs/guides/01_fret_2cde.md) — the workflow.
- [Burst variance analysis](docs/concepts/bva.md) — the variance-based dynamics
  test, which answers the same question a different way.
- [Photon-by-photon HMM](docs/concepts/h2mm.md) — what to do with the bursts 2CDE
  flags.
- [Single-molecule FRET bursts](docs/concepts/smfret_bursts.md)
- {cite}`tomov2012`
