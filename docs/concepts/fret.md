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
spectra in `chisurf/core/fluorescence/fret/forster.py` and can look up tabulated
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

## FRET as a molecular ruler

Because $E$ is a steep, calibrated function of $R/R_0$ and $R_0$ is computable
from spectra and the donor quantum yield, a measured efficiency reads out as a
nanometre distance across the 2–10 nm window. A network of such distances between
labelled sites becomes a set of restraints for integrative structural modelling,
with the flexible dye-linker cloud handled by accessible volumes
({ref}`concept-accessible-volume`).

## See also

- Guides: {doc}`/guides/14_multiparameter_es` (accurate $E$/$S$ from bursts) ·
  {doc}`/guides/10_lifetime_anisotropy_fitting` ($\tau_{DA}$ and the $\kappa^2$
  check).
- Related concepts: {ref}`concept-smfret-bursts` (per-burst $E$, $S$, and the
  correction factors) · {ref}`concept-accessible-volume` (dye clouds and the
  three distance measures).
- Implementation: `chisurf/core/fluorescence/fret/` — overlap integral and
  Förster radius (`forster.py`), intensity-based $E$ and distance conversions
  (`__init__.py`), FRET-line generation (`fret_line.py`), calibration factors
  (`calibration.py`); FRET-line GUI `chisurf/plugins/fret_line/`.
- Key literature: Förster, T. *Zwischenmolekulare Energiewanderung und
  Fluoreszenz.* Ann. Phys. **437**, 55–75 (1948); Lakowicz, J. R. *Principles of
  Fluorescence Spectroscopy*, 3rd ed. (2006), FRET chapters; Clegg, R. M. Curr.
  Opin. Biotechnol. **6**, 103–110 (1995).
</content>
