(concept-tcpda)=
# Three-colour PDA (tcPDA)

Two-colour FRET measures one distance per molecule. Label three sites and you
measure three — **in the same molecule, at the same moment**. That is the only
way to distinguish a protein that breathes along one coordinate from one whose
three regions move independently: three separate two-colour experiments give
three *marginal* distributions and can never say whether the distances move
together, because the joint distribution was never observed.

Three-colour photon distribution analysis extracts those distances, and their
**correlations**, from the shot-noise-broadened photon statistics of individual
bursts. It is the three-colour counterpart of {doc}`PDA <pda>`, and it shares
that page's central idea — the noise is computed, not fitted — but almost
nothing of its machinery.

For the workflow in ChiSurf, see the guide {doc}`/guides/42_tcpda`.

## Three dyes, three distances, coupled pathways

Call the dyes blue (B), green (G) and red (R) in order of increasing wavelength,
with inter-dye distances $R_{BG}$, $R_{BR}$, $R_{GR}$ and their own Förster
radii. Two things make this more than three two-colour experiments stacked.

**The pathways compete.** An excited blue dye can transfer to green *or* to red,
and both are rates out of the same excited state, so they share a denominator.
With $x_{ij} = (R_{0,ij}/R_{ij})^6$,

$$
E_{BG} = \frac{x_{BG}}{1 + x_{BG} + x_{BR}},
\qquad
E_{BR} = \frac{x_{BR}}{1 + x_{BG} + x_{BR}}.
$$

Opening a B→R pathway therefore *reduces* transfer to green even though
$R_{BG}$ has not moved. This is the standard trap: reading an ordinary
two-colour formula off the blue–green pair of a three-colour construct
overestimates that distance, and it does so in the direction that mimics the
molecule getting longer.

**The pathways cascade.** Energy delivered to green may continue to red, so the
dye that finally emits is

$$
P(B) = 1 - E_{BG} - E_{BR},
\quad
P(G) = E_{BG}(1 - E_{GR}),
\quad
P(R) = E_{BR} + E_{BG}E_{GR}.
$$

The red channel is fed by **two distinguishable routes** — direct $B \to R$
transfer and the two-step $B \to G \to R$ relay. That redundancy is exactly why
three distances are identifiable from count statistics at all: without it, the
red counts could be explained by either distance alone.

Under green (PIE/ALEX) excitation the blue dye is a spectator and the system is
ordinary two-colour, $P(G) = 1 - E_{GR}$, $P(R) = E_{GR}$. Because $R_{GR}$
appears in *both* excitation periods, the two halves of a burst constrain each
other.

## What a burst looks like

A burst under alternating excitation carries five photon counts:

| symbol | excitation → detection |
| --- | --- |
| $F_{BB}$ | blue → blue |
| $F_{BG}$ | blue → green |
| $F_{BR}$ | blue → red |
| $F_{GG}$ | green → green |
| $F_{GR}$ | green → red |

Under blue excitation a photon lands in one of three channels, so the counts
follow a **trinomial** distribution; under green excitation only two channels
are open, so a **binomial** one. Each channel additionally collects
uncorrelated Poisson background, and the burst likelihood is the product of the
two partitions, marginalised over how many of the observed counts were
background:

$$
L(F \mid p, B) = \sum_{b \le F}
   \Big[\prod_c \mathrm{Pois}(b_c; B_c)\Big]\,
   \mathrm{Multinom}(F - b;\, p).
$$

This is where tcPDA departs from two-colour PDA in kind, not degree. Two-colour
PDA builds an **S1S2 count matrix** and fits a one-dimensional projection of it;
tcPDA fits the **per-burst likelihood** directly. There is no histogram to
convolve, and correspondingly no photon-number distribution to supply — the
likelihood conditions on each burst's own size.

## Excitation, transfer, emission

ChiSurf expresses the instrument as three matrices, composed left to right:

$$
p(\text{laser }\ell) \;\propto\;
   \underbrace{X_{\ell,\cdot}}_{\text{excitation}}\;
   \underbrace{T(R)}_{\text{transfer}}\;
   \underbrace{M}_{\text{emission}}
$$

| matrix | shape | meaning |
| --- | --- | --- |
| excitation | (lasers, dyes) | how a laser pulse distributes its excitation. **Rows sum to one** |
| transfer | (dyes, dyes) | excitation on dye *i* finally emitted by dye *j*; from the distances |
| emission | (dyes, channels) | photon from dye *d* counted in channel *c* |

The row-normalisation of the excitation matrix is not cosmetic. A laser pulse
excites **exactly one** dye, so direct excitation of the redder dyes
*partitions* the excitation rather than adding to it. Treating it as extra
weight leaves the donor's share at one, and because the channel probabilities
are normalised afterwards the error is invisible at zero direct excitation and
grows with it — a silent bias in precisely the correction meant to remove one.

The excitation and emission matrices are the same two objects ChiSurf's
light-path simulator produces, so a simulated optical path can be used directly
instead of hand-entered correction factors. The familiar scalars
($\gamma$, crosstalk, direct excitation) are the same information in a
lower-triangular form.

## Correlated distance distributions

A species is a **trivariate Gaussian** over $(R_{GR}, R_{BG}, R_{BR})$ with a
full covariance matrix. The off-diagonal entries are the point of the method: a
positive $\rho(R_{GR}, R_{BG})$ says the two distances grow and shrink together,
which is what a single conformational coordinate looks like; independent widths
say they do not.

Two practical notes. The covariance is parameterised internally by a Cholesky
factor, so a fit cannot step outside the positive-definite cone — an invalid
covariance is not a distribution, and an optimiser will find one within a step
or two if allowed. And the species is integrated by **Gauss–Hermite
quadrature** on the transformed coordinates rather than a uniform grid, because
the species *is* Gaussian: a handful of nodes per axis matches what a uniform
grid needs tens for.

## Corrections that change what a species contributes

**Stochastic labelling** is a permutation, not a dropout. When the two labelling
sites are chemically equivalent, green and red land on either one, so a fraction
of molecules carries the mirror geometry: $R_{BG}$ and $R_{BR}$ exchanged, with
$R_{GR}$ untouched — it is the distance *between* the two swapped dyes. The
correlations with $R_{GR}$ trade places for the same reason.

**Brightness** follows from the optics. Energy transfer moves photons between
channels whose detection efficiencies differ, so a high-FRET species can be
genuinely dimmer and produce smaller bursts. Ignoring that over-weights it — it
is credited the same amplitude while contributing fewer photons — so each
species gets its own burst-size distribution, stretched by a brightness derived
from its distances rather than fitted.

## Dynamics

If a molecule interconverts *during* the burst, what is observed is a **time
average**. For two states the distribution of the time fraction spent in state 1
is available exactly, including the two boundary atoms — molecules that never
switched, which are finite-probability events rather than density and which
carry the entire static limit.

Beyond two states there is no closed form, and ChiSurf uses the approach of
Gopich and Szabo: keep the first two moments of the time-averaged observable —
which *are* exact for any rate matrix — and match a shape to them. The variance
carries the physics,

$$
\sigma^2_{\bar x}(T) = \frac{2}{T^2}\int_0^T (T-t)\,C(t)\,dt,
$$

whose per-mode factor $\frac{2}{(\lambda T)^2}(e^{\lambda T} - 1 - \lambda T)$
is 1 in the slow limit (states resolved, full static heterogeneity) and falls as
$2/|\lambda|T$ in the fast one (motional narrowing). The intermediate regime —
counts filling in *between* the static peaks, where neither limit puts anything
— is the dynamic signal.

The approximation agrees with exact sampling to about 1% once there is more
than a transition or two per observation window. It degrades as exchange slows,
because well-separated states give a multi-modal distribution that a
two-moment match cannot follow — but slow exchange means the states are
*resolved*, and a static multi-species fit describes that case directly.

Where the moment match is not enough, the occupation times are **sampled**
instead. That sampling runs inside the photon simulator's kinetics rather than
in ChiSurf: the simulator records a *state trajectory* — every transition, with
the time it happened — from which the fraction of each observation window spent
in each state follows exactly. An event log matters here rather than a
periodic snapshot, because a snapshot cannot see a state that is entered and
left between two samples, which is precisely the fast-exchange regime. Each
observation window is one immobile, non-emitting molecule started from the
equilibrium populations, so the windows are independent draws. The seed is
fixed, so the fit objective stays deterministic and the optimiser is not
chasing sampling scatter.

## Reading a fit

A single species with small widths and correlations near zero: three rigid,
independent distances. Large widths with a strong positive correlation: one
coordinate along which the whole construct expands and contracts. Two species
that a dynamic fit prefers over a static mixture: interconversion, with the
exchange rate readable from the fill-in between the peaks.

Because the objective is a likelihood rather than a histogram $\chi^2$, the
reported $\chi^2_r$ here is a **relative** measure. It settles near 2.4 for a
good fit rather than at one — the saturated reference has three free cells per
burst and the per-cell counts are far too small for the usual deviance
asymptotics. Use it to compare fits of the same data, not to decide in absolute
terms whether a model is adequate; for that, use the error surfaces or a
parametric bootstrap.

## References

- Gopich, I. V.; Szabo, A. *FRET efficiency distributions of multistate single
  molecules.* J. Phys. Chem. B **2010**, 114, 15221 — the multistate
  time-averaging approximation used for dynamics.
- Antonik, M.; Felekyan, S.; Gaiduk, A.; Seidel, C. A. M. *Separating structural
  heterogeneities from stochastic variations in fluorescence resonance energy
  transfer distributions via photon distribution analysis.* J. Phys. Chem. B
  **2006**, 110, 6970 — two-colour PDA, the foundation.
- Kalinin, S.; Felekyan, S.; Valeri, A.; Seidel, C. A. M. *Characterizing
  multiple molecular states in single-molecule multiparameter fluorescence
  detection by probability distribution analysis.* J. Phys. Chem. B **2008**,
  112, 8361 — dynamic PDA.
- Barth, A.; Voith von Voithenberg, L.; Lamb, D. C. *Quantitative single-molecule
  three-color Förster resonance energy transfer by photon distribution analysis.*
  J. Phys. Chem. B **2019**, 123, 6901 — three-colour PDA.

## See also

- {doc}`PDA <pda>` — the two-colour method this generalises.
- {doc}`Accurate FRET <accurate_fret>` — the correction factors.
- {doc}`Parameter uncertainty <parameter_uncertainty>` — error surfaces.
- Guide: {doc}`/guides/42_tcpda`.
