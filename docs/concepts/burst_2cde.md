---
type: Concept
title: FRET-2CDE and ALEX-2CDE
description: In single-molecule FRET on freely diffusing molecules, each labelled molecule crossing the confocal volume produces one short burst of a few tens to a few hundred photons.
tags: [concepts, bursts, fret]
anchor: concept-burst-2cde
---

(concept-burst-2cde)=
# FRET-2CDE and ALEX-2CDE

In single-molecule FRET on freely diffusing molecules, each labelled molecule
crossing the confocal volume produces one short **burst** of a few tens to a few
hundred photons. A burst's mean apparent FRET efficiency tells you *where* the
molecule sits on the $E$ axis, but not *whether it stayed there*. A molecule that
switches between a low- and a high-FRET state while transiting the spot yields a
single burst at some intermediate efficiency — on the $E$ histogram alone it is
indistinguishable from a genuinely static intermediate. **2CDE**
(two-channel kernel density estimator, {cite}`tomov2012`) is a
per-burst score that exposes this hidden sub-burst structure directly from the
photon arrival times, with no kinetic model and no binning.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/01_fret_2cde`.

## The two-channel kernel-density estimate

2CDE works on the raw photon stream. For each detection channel the local photon
**rate** around a given photon is estimated by a kernel density estimate (KDE):
a kernel is centred on the photon's macro time and the contributions of nearby
photons — measured in *time*, not in *photon index* — are summed. Following
Tomov's notation {cite}`tomov2012`, the KDE at the $i$-th photon of channel $X$,
evaluated over the photons of channel $Y$, is

$$
\mathrm{KDE}_{X_i}^{Y} \;=\;
\sum_{j}^{N_{CHY}}
\exp\!\left(-\frac{\lvert t_{(CHX)_i} - t_{(CHY)_j}\rvert}{\tau}\right),
$$

a symmetric-exponential (Laplace) kernel of time constant $\tau$ — the original
Tomov choice. ChiSurf also offers the Gaussian kernel of the FRETBursts
implementation {cite}`ingargiola2016`,
$\exp\!\big(-(t_i-t_j)^2/2\tau^2\big)$, which estimates the rate more accurately
and with far weaker dependence on the evaluation position (the Laplace kernel,
sampled *at* the photon positions, always sits on its own peak and systematically
over-estimates the rate). For a Gaussian kernel the rate estimate is reliable
above $\sim 1/(2\tau)$ counts per second; below that it depends strongly on where
the KDE is evaluated. For the Laplace kernel the self-channel density
$\mathrm{KDE}_{X_i}^{X}$ excludes the photon itself and carries Tomov's
small-$N$ correction, the **nbKDE** term {cite}`tomov2012`

$$
\mathrm{nbKDE}_{X_i}^{X} \;=\;
\left(1 + \frac{2}{N_{CHX}}\right)
\sum_{j,\,j\neq i}^{N_{CHX}}
\exp\!\left(-\frac{\lvert t_{(CHX)_i}-t_{(CHX)_j}\rvert}{\tau}\right),
$$

where $N_{CHX}$ is the number of channel-$X$ photons in the current burst. The
Gaussian variant uses the raw $\mathrm{KDE}_{X_i}^{X}$ (self term included, no
prefactor), as FRETBursts does.

A subtlety worth knowing: the kernel density itself is evaluated over the
**entire photon stream**, and only the resulting per-photon densities are sliced
per burst. Restricting the KDE to the burst slice would put an artificial cliff
at each burst boundary — photons near the edge would lose the neighbours that
legitimately contribute to their local rate, biasing their density downward and
inflating 2CDE for short bursts. Evaluating globally and slicing afterwards
keeps every photon's rate estimate honest; this is the FRETBursts reference
scheme {cite}`ingargiola2016`, which `tttrlib.TwoCDE` reproduces bit-exactly. The burst enters only through the
averages $(E)_D$, $(1-E)_A$ and the small-$N$ factors, which use the burst's own
photon counts.

The kernel time constant $\tau$ sets the timescale over which brightness is
averaged. It should be short enough to resolve within-burst changes yet long
enough to accumulate several photons per kernel. Tomov used
$\tau = 45\ \mu\mathrm{s}$ for FRET-2CDE and $75\ \mu\mathrm{s}$ for
ALEX-2CDE, and recommends 30–500 µs for typical data {cite}`tomov2012` — well
below the millisecond burst duration and above the microsecond inter-photon
spacing.

## FRET-2CDE: a per-burst dynamics score

FRET-2CDE compares the donor (D) and acceptor (A) brightness *time courses*
within a burst. From the KDE terms above, define a donor-weighted and an
acceptor-weighted efficiency estimate,

$$
(E)_D = \frac{1}{N_{CHD}} \sum_{i=1}^{N_{CHD}}
\frac{\mathrm{KDE}_{D_i}^{A}}{\mathrm{KDE}_{D_i}^{A} + \mathrm{nbKDE}_{D_i}^{D}},
\qquad
(1-E)_A = \frac{1}{N_{CHA}} \sum_{i=1}^{N_{CHA}}
\frac{\mathrm{KDE}_{A_i}^{D}}{\mathrm{KDE}_{A_i}^{D} + \mathrm{nbKDE}_{A_i}^{A}},
$$

and combine them into

$$
\boxed{\;\mathrm{FRET\text{-}2CDE} = 110 - 100\,\big[(E)_D + (1-E)_A\big]\;}
$$

(Tomov eqs. 6–8 {cite}`tomov2012`).

The logic is the **temporal (anti)correlation** of the two colours. In a static
burst the donor and acceptor rates rise and fall together (both track the same
molecule crossing the beam), so $(E)_D + (1-E)_A \approx 1$ and FRET-2CDE settles
near a fixed baseline of $\approx 10$, independent of the actual efficiency. If
the molecule switches FRET state mid-burst, the donor and acceptor brightness
become **anticorrelated in time** — donor bright while acceptor dim, then the
reverse — the two weighted estimates no longer sum to one, and FRET-2CDE rises,
typically into the 30–100 range for clear millisecond dynamics. Bursts near the
static baseline are treated as static and bursts above a cutoff as dynamic:
Tomov split at 15 {cite}`tomov2012`; ChiSurf's `dynamic_fraction` defaults to
12.

## ALEX-2CDE: a brightness-heterogeneity / purity score

With alternating-laser excitation (ALEX) or pulsed interleaved excitation (PIE)
the sample is probed by two excitation streams — donor-excitation ($D_{ex}$) and
acceptor-excitation ($A_{ex}$). ALEX-2CDE reuses the same two-channel KDE
machinery, but now on the two *excitation* streams, to score how uniform the
donor and acceptor brightness are across the burst. Define the cross-over-self
brightness ratios (Tomov eqs. 10–11 {cite}`tomov2012`)

$$
BR_{D_{ex}} = \frac{1}{N_{CHA_{ex}}} \sum_{i=1}^{N_{CHD_{ex}}}
\frac{\mathrm{KDE}_{D_{ex,i}}^{A}}{\mathrm{KDE}_{D_{ex,i}}^{D}},
\qquad
BR_{A_{ex}} = \frac{1}{N_{CHD_{ex}}} \sum_{i=1}^{N_{CHA_{ex}}}
\frac{\mathrm{KDE}_{A_{ex,i}}^{D}}{\mathrm{KDE}_{A_{ex,i}}^{A}},
$$

For a burst whose two excitation streams keep a fixed brightness ratio, each
$BR \to 1$. Tomov sums them (eq. 12),
$\mathrm{ALEX\text{-}2CDE} = 100 - 50\,(BR_{D_{ex}} + BR_{A_{ex}})$, so a pure
burst scores $\approx 0$ and a heterogeneous one rises above it {cite}`tomov2012`.
ChiSurf computes exactly this (`tttrlib.TwoCDE`).

:::{note}
tttrlib builds before 2026-09-24 took the *difference*
$100 - 50\,(BR_{D_{ex}} - BR_{A_{ex}})$, copied from the code cell of the
FRETBursts 2CDE notebook (whose own text quotes eq. 12). Its static baseline is
$\approx 100$, not 0 — 200 simulated constant-rate 1 ms bursts gave a median of
98.5 against 7.3 for eq. 12 — so ALEX-2CDE columns written by an older build, and
any cutoff tuned on them, must be recomputed.
:::

A well-behaved single molecule carrying one active donor and one active acceptor
gives donor- and acceptor-excitation photons that are present *throughout* the
burst; the brightness ratios are balanced and the burst sits in the static
cluster. Impure bursts break this balance: a donor-only or acceptor-only molecule, an
acceptor that **blinks** or bleaches partway through the burst, or two molecules
of different labelling coinciding in the volume all make one excitation stream's
brightness heterogeneous relative to the other, driving ALEX-2CDE (eq. 12) up. It is
therefore used as a **purity filter** — Tomov kept bursts below 4–10 on the eq. 12
scale {cite}`tomov2012` — to purge donor-only/acceptor-only contamination,
photophysical artefacts, and multi-molecule events before building $E$–$S$
histograms.

The two scores are complementary: FRET-2CDE reports **within-burst FRET
dynamics** (state switching), ALEX-2CDE reports **within-burst brightness
heterogeneity** (impurity / photophysics). Both are single numbers per burst,
computed from the same KDE primitive, and both live as columns you can gate on in
the burst browser or in ndX.

## Settings, and what 2CDE cannot tell you

ChiSurf's defaults are $\tau = 100\ \mu\mathrm{s}$ with the Laplace kernel
(Tomov's original), and `dynamic_fraction(threshold=12.0)` for the
static/dynamic split. The kernels are truncated for speed — at $5\tau$ (Laplace,
as in {cite}`tomov2012`) and $3\tau$ (Gaussian, as in FRETBursts) — where the
neglected tail is below $e^{-5}$ and $e^{-4.5}$ of the peak.

**2CDE has a timescale window, and it is set by $\tau$ and the burst duration.**
Exchange much faster than $\tau$ is averaged inside the kernel and the burst
looks static; exchange much slower than the ~1 ms transit means the molecule
simply never switches during the burst, and it *also* looks static. Only
dynamics roughly between $\tau$ and the burst duration raise the score. A
FRET-2CDE near baseline therefore means "no dynamics **in this window**", never
"no dynamics".

**The baseline is a statistical quantity, not a constant.** The $\approx 10$
static value emerges from averaging noisy per-photon ratios, so bursts with few
photons scatter around it much more widely than photon-rich bursts. A fixed
cutoff of 12 consequently flags a larger fraction of *dim* bursts as dynamic
purely by shot noise. Apply a photon-count threshold before interpreting the
dynamic fraction, and treat that fraction as comparative between similarly
filtered datasets rather than as an absolute number.

**It is a flag, not a rate.** 2CDE scores that a burst changed; it does not
estimate how fast, how many states, or in which direction. Use it to *select*
dynamic bursts, then hand them to a method that models kinetics —
{ref}`concept-h2mm` for photon-by-photon rates, {ref}`concept-pda2c` for
distributions, or the FRET-line analysis in {ref}`concept-fret`.

**Other things move the score.** Acceptor blinking or bleaching mid-burst is a
genuine brightness anticorrelation and raises FRET-2CDE exactly like a
conformational transition; so can a second molecule entering the volume. Screen
with ALEX-2CDE first where ALEX/PIE data are available {cite}`tomov2012`. Finally, donor-only and
acceptor-only bursts have no meaningful two-colour ratio at all — ChiSurf returns
`NaN` when either stream is empty in a burst, so those rows must be dropped, not
read as zeros.

## See also

- Guide: {doc}`/guides/01_fret_2cde`.
- Plugin `chisurf/plugins/burst/burst_2cde/`
  ({src}`chisurf/plugins/burst/burst_2cde/core/computation.py`); engine
  `tttrlib.TwoCDE` (base class `tttrlib.BurstFeature`). There is no NumPy
  fallback any more: without `TwoCDE` the plugin raises.
- The complementary variance-based dynamics test, Burst Variance Analysis
  (`chisurf/plugins/burst/burst_bva/`).
- Primary literature: {cite}`tomov2012` introduces the 2CDE kernel and both of
  its statistics; {cite}`ingargiola2016` is the FRETBursts implementation the
  engine is validated against.
