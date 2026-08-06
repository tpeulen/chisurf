(concept-fret)=
# Förster resonance energy transfer (FRET)

Förster resonance energy transfer is the non-radiative transfer of excitation
energy from an excited **donor** fluorophore to a nearby **acceptor** through
resonant dipole–dipole coupling. Because the transfer rate falls off as the
*sixth power* of the donor–acceptor separation, FRET is exquisitely sensitive to
distance over the **2–10 nm** range — the size of proteins and their complexes —
which is why it is called the *spectroscopic ruler*. This page is the physics
that every distance measurement in ChiSurf rests on: the transfer rate, the
efficiency, the **Förster radius** $R_0$, and how an efficiency becomes a
distance.

## The dipole–dipole mechanism

In Förster's weak-coupling (incoherent) limit the two chromophores keep their own
spectra and transfer excitation like a driven-oscillator resonance: the
oscillating transition dipole of the excited donor induces a dipole in the
acceptor whenever their transitions are in resonance — i.e. wherever the donor
*emission* spectrum overlaps the acceptor *absorption* spectrum. No photon is
emitted and reabsorbed, and no orbital overlap is needed; the coupling energy
scales as $1/R^3$, so the transfer *rate* scales as $1/R^6$. The resonance
condition is a spectral overlap, and the strength depends on the mutual
orientation of the two dipoles.

## Transfer rate and efficiency

For a donor with donor-only excited-state lifetime $\tau_D$ and a donor–acceptor
separation $R$, the transfer rate is

$$
k_T(R) = \frac{1}{\tau_D}\left(\frac{R_0}{R}\right)^6 .
$$

FRET is one more de-excitation channel competing with the donor's intrinsic
decay $1/\tau_D$, so the fraction of excitations that transfer — the **FRET
efficiency** — is

$$
E = \frac{k_T}{k_T + 1/\tau_D}
  = \frac{1}{1 + (R/R_0)^6}
  = 1 - \frac{\tau_{DA}}{\tau_D},
$$

where $\tau_{DA}$ is the donor lifetime *in the presence* of the acceptor. The
three forms are equivalent and each corresponds to a way of measuring $E$
(below). Inverting gives distance from efficiency,

$$
\boxed{\;R = R_0\left(\frac{1}{E} - 1\right)^{1/6}\;}
$$

The response is steep and sigmoidal in $R/R_0$: $E$ is near 1 well below $R_0$,
near 0 well above it, and most informative within roughly $\pm 40\%$ of $R_0$,
which sets the useful dynamic range of any dye pair.

:::{note}
FRET averages the transfer **rate**, not the distance. When the separation is a
*distribution* $P(R)$ (flexible linkers, conformational heterogeneity), the
efficiency must be averaged first and inverted only afterward — see
{ref}`concept-accessible-volume` for the three distinct "distances" that fall out
of one distribution.
:::

## The Förster radius $R_0$

$R_0$ is the separation at which transfer is 50% efficient ($k_T = 1/\tau_D$). It
bundles all the photophysics of the pair and the medium:

$$
R_0^6 \;\propto\; \kappa^2\, n^{-4}\, Q_D\, J,
\qquad
R_0\,[\text{nm}] = 0.02108\,\bigl(\kappa^2\, n^{-4}\, Q_D\, J\bigr)^{1/6},
$$

with $Q_D$ the donor fluorescence quantum yield, $n$ the refractive index of the
intervening medium ($\approx 1.33$–$1.4$), $\kappa^2$ the orientation factor, and
$J$ the **spectral overlap integral**

$$
J = \int f_D(\lambda)\,\varepsilon_A(\lambda)\,\lambda^4\,\mathrm{d}\lambda
\qquad [\mathrm{M^{-1}\,cm^{-1}\,nm^4}],
$$

where $f_D$ is the *area-normalized* donor emission ($\int f_D\,\mathrm{d}\lambda
= 1$) and $\varepsilon_A$ the acceptor *molar* extinction coefficient. Because
$R_0$ is a **sixth root** of its inputs, it is remarkably forgiving of moderate
errors in $Q_D$ or $J$: a 40% error in $J$ shifts $R_0$ by under 6%. Typical
organic-dye pairs have $R_0 \approx 4$–$6$ nm. ChiSurf computes $J$ and $R_0$ from
spectra in {src}`chisurf/core/fluorescence/fret/forster.py` and can look up tabulated
pair values from its fluorophore database.

## The orientation factor $\kappa^2$

Dipole–dipole coupling depends on how the two transition dipoles are oriented
relative to each other and to the connecting vector:

$$
\kappa^2 = \bigl(\cos\theta_{DA} - 3\cos\theta_D\cos\theta_A\bigr)^2 \in [0, 4].
$$

$\kappa^2$ cannot be measured per photon, so the near-universal assumption is the
**dynamic isotropic average** $\langle\kappa^2\rangle = 2/3$, valid when both dyes
reorient freely and fast compared with $\tau_D$. This is the default in ChiSurf.
Its validity is judged from the fluorescence **anisotropy**: a low residual
anisotropy $r_\infty$ signals free rotation (assumption safe), while a large
$r_\infty$ — a dye stacking on DNA or sticking to a hydrophobic patch — means
averaging is incomplete and $\kappa^2$ becomes the *dominant systematic
uncertainty* in the recovered distance. This is why anisotropy is measured
alongside FRET; see {doc}`/guides/10_lifetime_anisotropy_fitting`.

## Measuring the efficiency

The three forms of $E$ map onto three experimental routes:

- **Intensity / ratiometric.** Count donor and acceptor photons and form a ratio.
  The raw **proximity ratio** $S_r/(S_g+S_r)$ tracks distance but is
  instrument-specific; turning it into an *accurate* $E$ requires correcting for
  background, spectral leakage, direct acceptor excitation, and the unequal
  detection/quantum-yield budget $\gamma$. In single-molecule burst experiments
  this correction algebra is central — see {ref}`concept-smfret-bursts` and
  {doc}`/guides/14_multiparameter_es`.
- **Lifetime.** Use $E = 1 - \tau_{DA}/\tau_D$. This is **self-calibrating** — no
  reference sample, no $\gamma$ — and time-resolved donor decays additionally
  resolve a whole *distribution* of distances rather than a single mean.
  ChiSurf's TCSPC FRET models and **FRET-lines** (which plot fluorescence-averaged
  against species-averaged donor lifetime to diagnose dynamics and dye artefacts)
  live in this route.
- **(Anti)correlation.** Donor–acceptor anti-correlation in FCS, or filtered-FCS,
  reports the microsecond-to-millisecond exchange between FRET states rather than
  a static distance.

## How precise is the distance?

Because $R$ depends on $E$ through a sixth root, the two error budgets behave
very differently — and knowing which one dominates tells you whether to spend
effort on better statistics or on better photophysics.

**Statistical error in $E$.** Differentiating $E = 1/(1+(R/R_0)^6)$ gives a
compact propagation rule,

$$
\frac{\Delta R}{R} = \frac{\Delta E}{6\,E\,(1-E)} .
$$

The factor $6E(1-E)$ peaks at $E = 0.5$, so the *same* uncertainty in efficiency
buys very different distance precision depending on where you sit:

| $E$ | $6E(1-E)$ | $\Delta R/R$ for $\Delta E = 0.02$ |
|---|---|---|
| 0.05 / 0.95 | 0.285 | 7.0 % |
| 0.1 / 0.9 | 0.54 | 3.7 % |
| 0.3 / 0.7 | 1.26 | 1.6 % |
| 0.5 | 1.50 | 1.3 % |

This is the quantitative version of "most informative near $R_0$": a 2 %
efficiency error is a 1.3 % distance error mid-range but a 7 % error out in the
tails, where $E$ is also hardest to measure accurately. In practice it sets the
usable window at roughly $0.5\,R_0 < R < 1.5\,R_0$ ($E \approx 0.98$ down to
$0.08$).

**Systematic error in $R_0$.** Here the sixth root works *for* you. $R_0$
scales as $(\kappa^2 Q_D n^{-4} J)^{1/6}$, so an error factor $f$ in any input
moves $R_0$ — and hence every distance — by only $f^{1/6}$:

| error in $J$ or $Q_D$ | effect on $R_0$ |
|---|---|
| ×1.2 (20 %) | +3.1 % |
| ×1.4 (40 %) | +5.8 % |
| ×2.0 (100 %) | +12.2 % |

A doubling of the overlap integral costs only 12 % in distance. The one input
that is *not* forgiving is $\kappa^2$, because its plausible range is far wider
than a factor of two. Relative to the isotropic $\langle\kappa^2\rangle = 2/3$:

| $\kappa^2$ | $R$ scaled by | situation |
|---|---|---|
| 0.04 | 0.63 (−37 %) | both dyes strongly immobilized, unfavourable geometry |
| 1/3 | 0.89 (−11 %) | one dye hindered |
| 2/3 | 1.00 | free isotropic rotation (assumed) |
| 4/3 | 1.12 (+12 %) | one dye hindered, favourable geometry |
| 4 | 1.35 (+35 %) | both dipoles aligned head-to-tail |

So a two-fold error in $\kappa^2$ is a tolerable ~11 % distance error, but the
pathological immobilized cases reach ±35 %, dwarfing every other term. That
asymmetry — statistics cheap, $\kappa^2$ expensive — is why anisotropy is
measured routinely and why $Q_D$ and $J$ rarely need to be known to better than
10 %.

:::{note}
ChiSurf defaults to $\kappa^2 = 2/3$ and $n = 1.33$. Note the unit convention in
{src}`chisurf/core/fluorescence/fret/forster.py`: the prefactor 0.02108 yields $R_0$ in
**nm**, but `forster_radius()` returns **Ångström** (it multiplies by 10).
:::

## FRET as a molecular ruler

Because $E$ is a steep, calibrated function of $R/R_0$ and $R_0$ is computable
from spectra and the donor quantum yield, a measured efficiency reads out as a
nanometre distance across the 2–10 nm window. A network of such distances between
labelled sites becomes a set of restraints for integrative structural modelling,
with the flexible dye-linker cloud handled by accessible volumes
({ref}`concept-accessible-volume`).

## See also

- Fundamentals: {ref}`fundamentals-energy-transfer` (mechanism, the overlap
  integral, the $\kappa^2$ averaging regimes) ·
  {ref}`fundamentals-lifetime-quantum-yield` (where $E = 1-\tau_{DA}/\tau_{D(0)}$
  comes from).
- Guides: {doc}`/guides/14_multiparameter_es` (accurate $E$/$S$ from bursts) ·
  {doc}`/guides/10_lifetime_anisotropy_fitting` ($\tau_{DA}$ and the $\kappa^2$
  check).
- Related concepts: {ref}`concept-smfret-bursts` (per-burst $E$, $S$, and the
  correction factors) · {ref}`concept-accessible-volume` (dye clouds and the
  three distance measures).
- Implementation: overlap integral and Förster radius
  {src}`chisurf/core/fluorescence/fret/forster.py#forster_radius`, intensity-based
  $E$ and distance conversions
  {src}`chisurf/core/fluorescence/fret/__init__.py`, FRET-line generation
  {src}`chisurf/core/fluorescence/fret/fret_line.py`, calibration factors
  {src}`chisurf/core/fluorescence/fret/calibration.py`; FRET-line GUI
  `chisurf/plugins/fret_line/`.
- Key literature: {cite}`foerster1948` is the mechanism itself;
  {cite}`clegg1995` a compact review of it; {cite}`lakowicz2006` the textbook
  treatment, FRET chapters.
