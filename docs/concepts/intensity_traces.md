---
type: Concept
title: 'Intensity traces: counting photons in time bins'
description: What a binned photon trace can and cannot show — Poisson counting noise, the bin-width trade-off, blinking and bleaching steps, and when to leave bins for change points.
tags: [concepts, photons, kinetics, statistics]
anchor: concept-intensity-traces
---

(concept-intensity-traces)=
# Intensity traces: counting photons in time bins

An intensity trace is the photon stream cut into consecutive windows of width
$\Delta t$ and counted: $n_k$ photons in bin $k$. It is the first thing anyone
looks at in a single-molecule recording, and the input to burst searches,
binned hidden Markov models and step counting. It is also a lossy view: the
photon arrival times inside a bin are thrown away, and everything the trace
seems to show is filtered through the choice of $\Delta t$.

For the workflow, see {doc}`the intensity-trace guide
</guides/74_intensity_traces_and_file_tools>`.

## What one bin holds

A molecule emitting at a constant detected rate $I$ delivers photons as a
Poisson process, so the count in a bin is Poisson distributed
{cite}`schottky1918`:

$$
P(n_k = n) = \frac{(I\Delta t)^n}{n!}\, e^{-I\Delta t}, \qquad
\langle n_k \rangle = \operatorname{Var}(n_k) = I\Delta t .
$$

The scatter of a flat trace is therefore not detector noise to be removed. It
is shot noise, and it sets the signal-to-noise ratio of one bin,

$$
\mathrm{SNR} = \frac{\langle n_k\rangle}{\sqrt{\operatorname{Var}(n_k)}} = \sqrt{I\Delta t}.
$$

Background adds its own Poisson counts, $n_k \sim \mathrm{Pois}\big((I + B)\Delta t\big)$,
which raises the variance without raising the signal.

The variance-to-mean ratio of the counts, the Fano factor
{cite}`fano1947`,

$$
F = \frac{\operatorname{Var}(n_k)}{\langle n_k\rangle},
$$

is 1 for a steady emitter and larger for anything that switches, diffuses or
bleaches during the trace. It is the one-number check of whether a trace holds
anything beyond counting noise. On the smFRET test file used in the guide
(freely diffusing molecules, 5 ms bins), $\langle n\rangle = 14.7$ and
$\operatorname{Var}(n) = 663$, so $F \approx 45$: the bursts dominate. The
photon-counting histogram {cite}`chen1999` makes the same test for the whole
count distribution instead of its first two moments
({ref}`concept-pch-fida`).

## The bin-width trade-off

Two requirements pull $\Delta t$ in opposite directions:

* **Coarse enough to see a level.** Two levels $I_1$ and $I_2$ separate when
  their difference exceeds the shot noise, roughly
  $|I_1 - I_2|\,\Delta t \gtrsim 2\sqrt{\bar I \Delta t}$, that is
  $\Delta t \gtrsim 4\bar I/(I_1 - I_2)^2$. At 20 kHz against 10 kHz that is
  about 1 ms; at 2 kHz against 1 kHz it is 10 ms.
* **Fine enough to see a dwell.** A visit shorter than one bin is averaged into
  its neighbours and disappears; a visit a few bins long is smeared at both
  ends. Nothing faster than $\Delta t$ can be resolved, and every transition is
  located only to within a bin.

For a freely diffusing molecule the dwell is the transit through the focus
(about 1 ms), so bins of 0.5–1 ms make bursts visible; for an immobilised
molecule the dwell is set by the kinetics or by bleaching, and bins of 10–100 ms
are typical. There is no universally right $\Delta t$. For a Poisson process
whose rate varies in time, a bin width that minimises the mean integrated
squared error of the estimated rate can be computed from the counts themselves
{cite}`shimazaki2007`; it is a useful sanity check on the choice by eye.

The histogram of the counts has its own, separate, bin setting: how finely the
count axis is divided. That is a density-estimation question
({cite}`freedman1981` gives the usual rule) and does not change the trace.

## Blinking and bleaching

Two photophysical processes put steps into every trace of a single emitter.

**Blinking** — reversible switching into a dark state. Single nanocrystals
{cite}`nirmal1996` and single fluorescent proteins {cite}`dickson1997` both
blink under continuous excitation, and in many emitters the on- and off-times
follow power laws rather than exponentials {cite}`kuno2000`
{cite}`frantsuzov2008`. A power law has no characteristic time, so a longer
recording does not converge to a mean — and the *measured* distribution
depends on the analysis: thresholding a binned trace into on and off, a
tenfold change of bin width shifted the apparent power-law exponent by about
30 % {cite}`crouch2010`. Blink statistics taken from a binned trace should
always be reported with $\Delta t$ and the threshold.

**Photobleaching** — irreversible loss of the fluorophore
{cite}`demchenko2020`. One molecule bleaches in one step to background; a
complex of $N$ labelled subunits bleaches in up to $N$ steps. Counting those
steps is a standard way to read stoichiometry, with the caveat that each label
is only detected with some probability, so the observed step counts follow a
binomial distribution and the maximum observed is a lower bound on $N$
{cite}`ulbrich2007`. In an smFRET trace of an immobilised molecule the same
reasoning is the single-molecule test: donor and acceptor bleach in single
steps, and acceptor bleaching makes the donor jump up {cite}`roy2008`.

A bleaching step and a transition into a long-lived dark state look identical
in a single trace; only the absence of a return tells them apart, and only
within the length of the recording.

## Levels, states and change points

Reading discrete levels from a trace can be done three ways, in increasing
order of how much of the data they use:

1. **Thresholding** the binned trace. Simple, and biased by both $\Delta t$ and
   the threshold, as above.
2. **A hidden Markov model** of the binned counts. States, their mean counts,
   transition probabilities and dwell times come out of one likelihood, and the
   number of states is chosen by an information criterion. The model, its
   Gaussian-emission approximation (poor below a few tens of counts per bin)
   and the conversion $k_{ij} \approx A_{ij}/\Delta t$ are covered in
   {ref}`concept-hidden-markov-models`.
3. **Change-point detection on the photon arrival times**, with no bins at all.
   The change-point problem — locating a jump in a parameter at an unknown
   time — is classical {cite}`page1957`. For single-molecule data the standard
   form is a generalised likelihood-ratio test on the inter-photon times,
   applied recursively to split the trace at each detected change, followed by
   clustering of the resulting segments into states with the number chosen by
   BIC {cite}`watkins2005`; a Bayesian variant exists {cite}`ensign2010`. It
   removes the bin-width trade-off altogether: a change point is located to
   within a few photons, not to within a bin.

The intensity-trace tool in ChiSurf implements (2) on top of the binned trace.
It does not run change-point detection; for photon-level kinetics use the
photon-by-photon HMM ({ref}`concept-photon-by-photon-kinetics`).

## Ratios from a trace

With two detection channels the tool also reports, per bin, the fraction of
photons in the **first** selected channel,

$$
f_k = \frac{n_{0,k}}{\sum_c n_{c,k}} .
$$

Which physical quantity that is depends on the channel order. With the acceptor
channel first it is the proximity ratio (uncorrected FRET efficiency); with the
donor first it is $1 - E_\mathrm{PR}$. It carries no background, crosstalk or
$\gamma$ correction ({ref}`concept-smfret-bursts`), and in bins with few photons
it is dominated by binomial noise — a bin with 4 photons can only give
$f \in \{0, 0.25, 0.5, 0.75, 1\}$.

## See also

- Guide: {doc}`/guides/74_intensity_traces_and_file_tools` · binning the
  stream by hand: {doc}`/guides/22_binned_photon_traces` · burst search on the
  same stream: {ref}`concept-smfret-bursts`.
- Hidden states from the binned trace: {ref}`concept-hidden-markov-models`;
  without bins: {ref}`concept-photon-by-photon-kinetics`.
- Implementation: binning per detector
  {src}`chisurf/plugins/tttr/intensity_trace/__init__.py#process_ptu`, the HMM
  fit {src}`chisurf/plugins/core/hmm/core/analysis.py#fit_traces`, dwell times
  {src}`chisurf/plugins/core/hmm/core/analysis.py#dwell_times`.
- Tools in ChiSurf: **Intensity trace** (`chisurf/plugins/tttr/intensity_trace/`) bins a TTTR file per detector, histograms the counts and fits an HMM.

## References

- {cite}`schottky1918` — shot noise; {cite}`fano1947` — the variance-to-mean
  ratio.
- {cite}`shimazaki2007` — choosing the bin width of a time histogram of a
  Poisson process; {cite}`freedman1981` — choosing the bins of the count
  histogram.
- {cite}`nirmal1996`, {cite}`dickson1997`, {cite}`kuno2000`,
  {cite}`frantsuzov2008` — blinking and its power-law statistics;
  {cite}`crouch2010` — how binning and thresholding change those statistics.
- {cite}`demchenko2020` — photobleaching; {cite}`ulbrich2007` — counting
  bleaching steps; {cite}`roy2008` — what a single-molecule smFRET trace looks
  like.
- {cite}`page1957`, {cite}`watkins2005`, {cite}`ensign2010` — change-point
  detection, classical and photon-by-photon.
