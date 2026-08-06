---
type: Fundamentals
title: Lifetime, quantum yield, and the rate picture
description: Symbols on this page follow ChiSurf's usage; the common alternatives are listed in.
tags: [fundamentals, tcspc, lifetime]
anchor: fundamentals-lifetime-quantum-yield
---

(fundamentals-lifetime-quantum-yield)=
# Lifetime, quantum yield, and the rate picture

Symbols on this page follow ChiSurf's usage; the common alternatives are listed
in {ref}`fundamentals-conventions`.

## Two rates, two observables

Write $\Gamma$ for the radiative rate and $k_{nr}$ for the sum of all
non-radiative routes out of $S_1$ — internal conversion, intersystem crossing,
quenching, energy transfer, photochemistry. Both are first order, so the excited
population decays exponentially and

$$
\tau = \frac{1}{\Gamma + k_{nr}}, \qquad
Q = \frac{\Gamma}{\Gamma + k_{nr}}, \qquad Q = \Gamma\tau .
$$

The lifetime $\tau$ is the mean time spent in the excited state. The quantum
yield $Q$ is the fraction of absorbed photons re-emitted as fluorescence. The
natural lifetime $\tau_n = 1/\Gamma = \tau/Q$ is what the lifetime would be if
emission were the only exit; it is set by the transition itself — computable from the
absorption spectrum and refractive index {cite}`strickler1962` — and is
comparatively insensitive to the surroundings.

The useful asymmetry is that $\Gamma$ is roughly a property of the molecule
while $k_{nr}$ is what the environment changes. A dye that dims on attachment to
a protein has gained a $k_{nr}$ term, and its lifetime has fallen by the same
factor. A dye that dims with no change in lifetime has not gained a $k_{nr}$
term — some molecules have instead been removed from the observed population
altogether ({ref}`fundamentals-quenching`).

Intensity depends on concentration, excitation power, collection efficiency and
detector gain. The lifetime depends on none of them, because it is read from the
shape of a decay and any factor multiplying the whole decay cancels. That is why
lifetime readouts are preferred wherever a calibration is hard to keep stable —
FLIM ({ref}`concept-imaging-flim-phasor`), lifetime-resolved FRET
({ref}`concept-mfd-fitting`), and the lifetime axis of a burst experiment. The
cost is timing hardware and enough photons to determine a shape rather than an
area ({ref}`fundamentals-photon-statistics`).

## Adding a process

A new de-excitation route of rate $k_X$ — a quencher diffusing in, an acceptor
attached, a triplet channel opening — enters the same denominator:

$$
\tau_X = \frac{1}{\Gamma + k_{nr} + k_X}, \qquad
\frac{\tau}{\tau_X} = \frac{Q}{Q_X} = 1 + k_X\tau .
$$

The efficiency of that process, meaning the fraction of excited molecules it
captures, is

$$
E_X = \frac{k_X}{\Gamma + k_{nr} + k_X} = 1 - \frac{\tau_X}{\tau}
    = 1 - \frac{Q_X}{Q} .
$$

Every efficiency in this documentation is this expression with a different
$k_X$. Setting $k_X = k_q[Q]$ gives Stern–Volmer quenching
({ref}`fundamentals-quenching`); setting $k_X = k_T(R)$ gives the FRET
efficiency ({ref}`fundamentals-energy-transfer`), so the familiar
$E = 1 - \tau_{DA}/\tau_{D(0)}$ is a special case rather than a separate result.

The same expression fixes the sensitivity window. A process is only measurable
while $k_X$ is comparable to $1/\tau$: much slower and it never competes, much
faster and it is already complete. This is why the usable FRET range is about
$0.5\,R_0$ to $2\,R_0$, and why choosing a longer-lived donor genuinely extends
the range over which slow quenching can be seen.

## Multi-exponential decays

One emitting species in one environment gives one exponential. A labelled
biomolecule rarely does. ChiSurf fits

$$
I(t) = \sum_i a_i\, e^{-t/\tau_i}, \qquad a_i \ge 0,
$$

with amplitude $a_i$ proportional to the ground-state population of species $i$.
The species fraction is $x_i = a_i/\sum_j a_j$, the fraction of *molecules*. The
intensity fraction is $f_i = a_i\tau_i/\sum_j a_j\tau_j$, the fraction of
*photons* — different, because a longer-lived species emits for longer.

```{figure} /guides/figures/lifetime_averages.png
:alt: a two-exponential decay and the two ways of averaging it
:width: 100%

Two species in equal numbers, $\tau_1 = 0.5$ ns and $\tau_2 = 4.0$ ns. Half the
*molecules* are short-lived, but they contribute only 11% of the *photons* — so
the two averages differ by 60%. Substituting one for the other in
$E = 1 - \tau_{DA}/\tau_{D(0)}$ biases the distance.
```

That distinction produces two averages that are not interchangeable:

$$
\langle\tau\rangle_x = \frac{\sum_i a_i\tau_i}{\sum_i a_i}, \qquad
\langle\tau\rangle_f = \frac{\sum_i a_i\tau_i^{2}}{\sum_i a_i\tau_i}
\;\ge\; \langle\tau\rangle_x .
$$

Use $\langle\tau\rangle_x$ wherever the quantity is proportional to the number of
molecules or to steady-state intensity, which includes every efficiency computed
as $1 - \tau_{DA}/\tau_{D(0)}$. Use $\langle\tau\rangle_f$ where the measurement
is photon-weighted, which is what a phasor or a mean arrival time returns
directly. They coincide only for a single exponential, and substituting one for
the other biases a FRET distance. Both are computed explicitly
({src}`chisurf/core/fluorescence/general.py#species_averaged_lifetime`,
{src}`chisurf/core/fluorescence/general.py#fluorescence_averaged_lifetime`); the
worked arithmetic is in {ref}`concept-tcspc-lifetime`.

A decay can be multi-exponential for physically distinct reasons, and the model
cannot separate them on its own:

- Genuinely discrete states, each with its own $\tau_i$. This is the reading
  everyone wants.
- A continuous distribution — a quencher at a range of distances, or a dye
  sampling a continuum of environments. Two or three exponentials will fit it
  well without any of them being real, which is what lifetime-distribution and
  maximum-entropy analyses exist to avoid.
- Averaging over an inhomogeneous population, including a distribution of
  donor–acceptor distances. This is what makes the donor decay informative about
  the width of a distance distribution and not only its mean.
- Artefacts: scattered excitation light, an impurity, a detector timing effect,
  or an inaccurate instrument response. These are absorbed into an extra
  exponential rather than showing up as a raised $\chi^2_r$
  ({ref}`fundamentals-photon-counting`).

Two lifetimes closer than roughly a factor of two are hard to resolve and often
cannot be resolved at all. That is a property of exponential analysis, not of
the fitting code ({ref}`concept-parameter-uncertainty`).

## Quantum yield in practice

$Q$ is measured comparatively against a standard of known yield, correcting for
the refractive indices of the two solvents and for absorbance at the excitation
wavelength.

Its main role here is that the donor quantum yield $Q_D$ enters the Förster
radius as $Q_D^{1/6}$. A factor-of-two error in $Q_D$ moves $R_0$ by about 12%,
so the sixth root is forgiving — but $Q_D$ is environment-dependent, so a
tabulated $R_0$ measured for free dye is not the $R_0$ of the same dye conjugated
to your protein ({ref}`fundamentals-energy-transfer`).

## See also

- Previous: {ref}`fundamentals-absorption-emission`. Next:
  {ref}`fundamentals-quenching`, on what $k_{nr}$ is made of.
- Concepts: {ref}`concept-tcspc-lifetime` · {ref}`concept-mfd-fitting` ·
  {ref}`concept-imaging-flim-phasor` · {ref}`concept-fret`.
- Implementation:
  {src}`chisurf/core/fluorescence/general.py#species_averaged_lifetime` ·
  {src}`chisurf/core/fluorescence/general.py#fluorescence_averaged_lifetime` ·
  {src}`chisurf/core/fluorescence/general.py#rate_constant_to_lifetime`.
- Literature: {cite}`lakowicz2006` for the rate picture and the averages;
  {cite}`oconnor1984` for what multi-exponential analysis can resolve.
