---
type: Concept
title: µs-ALEX — alternating excitation, and the titration it enables
description: What microsecond alternating-laser excitation measures, why folding the alternation into the micro-time turns it into ordinary PIE data, and how a concentration series of FRET histograms yields a binding constant.
tags: [concepts, fret, smfret, alex, titration]
anchor: concept-us-alex
sources:
  - text: Derived in part from the English Wikipedia article "Hill equation (biochemistry)"
    url: https://en.wikipedia.org/wiki/Hill_equation_(biochemistry)
    licence: CC-BY-SA-4.0
  - text: Derived in part from the English Wikipedia article "Dissociation constant"
    url: https://en.wikipedia.org/wiki/Dissociation_constant
    licence: CC-BY-SA-4.0
---

(concept-us-alex)=

# µs-ALEX — alternating excitation, and the titration it enables

:::{admonition} How to run it
:class: tip
[Coming from ALEX-Suite](../guides/66_alex_suite.md) walks the workflow; the
burst observables themselves are in {ref}`concept-smfret-bursts`.
:::

## What the alternation buys

A two-colour FRET burst gives the efficiency $E$, and $E$ alone cannot tell a
low-FRET molecule from one whose acceptor is missing or dark: both put nearly all
their photons in the donor channel. **Alternating-laser excitation** removes the
ambiguity by asking the acceptor directly. The acceptor laser is switched on and
off out of phase with the donor laser, so every photon carries two labels — which
detector saw it, and which laser was on — and the four combinations are

$$
I_{DD},\quad I_{DA},\quad I_{AA},\quad I_{AD}
$$

(first index the exciting colour, second the emitting one). The **stoichiometry**

$$
S = \frac{\gamma I_{DD} + I_{DA}}{\gamma I_{DD} + I_{DA} + I_{AA}/\beta}
$$

is near 1 when only a donor is present, near 0 when only an acceptor is, and
mid-range for a doubly labelled molecule. Gating on $S$ is what makes an $E$
histogram a statement about FRET rather than about labelling
(Kapanidis *et al.* 2004).

In **µs-ALEX** the switching period is tens to hundreds of microseconds — long
compared with the fluorescence lifetime, short compared with a burst — so the
laser identity is encoded in the photon's **macro** time. In **PIE / ns-ALEX**
the two lasers are pulsed within one excitation period and the identity is in the
**micro** time instead. The measured quantity is the same; only where the label
sits differs.

## Folding: why µs-ALEX and PIE are one thing

Take a µs-ALEX stream and replace each photon's micro time by its **phase within
the alternation period**,

$$
\varphi = (t_{\text{macro}} - \Delta)\ \mathrm{mod}\ T,
$$

and the measurement becomes indistinguishable from a PIE measurement: the two
excitation periods are now two micro-time windows, and every gating, correction
and burst analysis written for PIE applies unchanged. ChiSurf does exactly this
(`tttrlib`'s `alex_to_microtime`), which is why there is no separate ALEX
analysis path — only a conversion at the front.

The period $T$ and the shift $\Delta$ are hardware settings, and they are
measurable rather than remembered. Assign $+1$ to every donor-detector photon and
$-1$ to every acceptor-detector one: the alternation is then a single sharp line
in the power spectrum of that signed stream, far sharper than in either
detector's own intensity, which the sample modulates too. The laser windows
follow from the folded phase histogram — two plateaus separated by the rise/fall
gaps — and which plateau is the donor excitation follows from which detector is
brighter in it. That last comparison is what a "channel flip" setting used to
guess at.

A wrong $T$ is silent, not loud: the folded phase smears out, the windows land on
nothing in particular, and the analysis proceeds to a stoichiometry histogram
with one peak instead of three. The check is the picture, and the *contrast* of
the spectral line is its number.

## The four streams, and what they are for

| stream | excitation | emission | used for |
|---|---|---|---|
| $I_{DD}$ | donor | donor | $E$, $S$, donor lifetime |
| $I_{DA}$ | donor | acceptor | $E$, $S$ (the FRET channel) |
| $I_{AA}$ | acceptor | acceptor | $S$ — is an active acceptor present? |
| $I_{AD}$ | acceptor | donor | diagnostics only; essentially background |

The corrections that turn these counts into a transferable efficiency — leakage
$\alpha$, direct excitation $\delta$, detection $\gamma$, excitation flux $\beta$
— are in {ref}`concept-accurate-fret`.

:::{admonition} A rate is not a count
:class: warning
$E$ and $S$ are ratios of **photon counts**. A burst table's per-stream *count
rate* divides each stream's photons by that stream's own time span, so the four
rates of one burst have four different denominators and their ratios are not the
count ratios. Read the counts.
:::

## Titration: fit the series, not the histograms

A titration is the same molecule measured at several ligand concentrations. Each
measurement gives an $E$ histogram; what changes across the series is not *where*
the populations sit but *how much* of each there is. So the whole series is one
fit,

$$
h_j(E) \;=\; \sum_{k} A_{jk}\, \exp\!\left[-\tfrac{1}{2}
\left(\frac{E-\mu_k}{\sigma_k}\right)^{\!2}\right],
$$

with the centres $\mu_k$ and widths $\sigma_k$ **shared** across every
concentration $j$ and only the amplitudes $A_{jk}$ free.

Sharing the shape is the point rather than a convenience. Fitting each histogram
on its own lets a noisy condition move a peak by more than the amplitude change
being measured, and the isotherm then reports that wander as affinity.

The amplitudes enter linearly, so they need not be searched: for any trial
$(\mu,\sigma)$ they are the non-negative least-squares solution, and only the
$2K$ shape parameters go to the optimiser. That *variable projection* is what
keeps a two-component fit of six conditions out of the local minimum where one
component has collapsed onto the other.

Normalising each condition's component **areas** gives fractions
$f_{jk} = A_{jk}\sigma_k / \sum_l A_{jl}\sigma_l$, and the fraction of the
population the ligand produces, against concentration, is a binding isotherm:

$$
f(c) \;=\; f_{\min} + (f_{\max}-f_{\min})\,\frac{c^{n}}{K_d^{\,n} + c^{n}}
$$

with $n=1$ for a single site and $n \ne 1$ for cooperativity: $n>1$ means that
binding one ligand raises the affinity for the next, $n<1$ that it lowers it.

:::{admonition} n is not the number of binding sites
:class: warning
The Hill coefficient is written as if it counted sites, and in practice it
rarely does — a protein with four sites routinely fits with $n \approx 2.5$.
Read it as an **interaction coefficient** that says how steeply the occupancy
turns on, and quote the site count from structure or stoichiometry rather than
from a curve fit (Weiss 1997; Stefan & Le Novère 2013).
:::

:::{admonition} An unsaturated series does not have a K_d
:class: warning
If the highest concentration has not reached the plateau, $K_d$ and $f_{\max}$
trade off against each other: the fit converges, the reported uncertainty is
small, and both numbers are meaningless. Either extend the series or hold the
baseline.
:::

## Further reading

- Kapanidis *et al.*, *PNAS* **101**, 8936 (2004) — ALEX and the stoichiometry
  axis. [10.1073/pnas.0401690101](https://doi.org/10.1073/pnas.0401690101)
- Müller *et al.*, *Biophys. J.* **89**, 3508 (2005) — pulsed interleaved
  excitation. [10.1529/biophysj.105.064766](https://doi.org/10.1529/biophysj.105.064766)
- Hellenkamp *et al.*, *Nat. Methods* **15**, 669 (2018) — the correction factors
  and why they decide whether two laboratories agree.
  [10.1038/s41592-018-0085-0](https://doi.org/10.1038/s41592-018-0085-0)
- Weiss, *FASEB J.* **11**, 835 (1997) — "The Hill equation revisited: uses and
  misuses". [10.1096/fasebj.11.11.9285481](https://doi.org/10.1096/fasebj.11.11.9285481)
- Stefan & Le Novère, *PLoS Comput. Biol.* **9**, e1003106 (2013) — cooperative
  binding, and what the Hill coefficient does and does not say.
  [10.1371/journal.pcbi.1003106](https://doi.org/10.1371/journal.pcbi.1003106)
- {ref}`concept-smfret-bursts`, {ref}`concept-accurate-fret`.
