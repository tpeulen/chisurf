---
type: Reference
title: "smFRET burst analysis — from photon counts to accurate (E, S)"
description: The physics and algebra of single-molecule FRET burst analysis — burst search, the raw proximity ratio vs the accurate FRET efficiency E, the ALEX/PIE stoichiometry S, and the four correction factors (leakage α, direct excitation δ, detection γ, excitation β) that turn per-burst photon counts into a straightened E–S histogram. Maps the standard corrections onto ChiSurf's burst/es.py and fret/calibration.py.
tags: [reference, fret, bursts, alex, corrections, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# smFRET burst analysis — from photon counts to accurate (E, S)

Single-molecule FRET on freely diffusing molecules (confocal, µs-ALEX/PIE or MFD)
records a stream of photons in which each labelled molecule that transits the
detection volume produces a short, intense **burst** of a few tens to a few
hundred photons. Burst analysis is the pipeline that (1) finds those bursts in
the timestamp stream, (2) sorts each burst's photons into detection channels,
and (3) converts the per-burst channel counts into two per-molecule observables:
the **FRET efficiency** $E$ (a proxy for donor–acceptor distance) and the
**stoichiometry** $S$ (the donor:acceptor labelling ratio, available only when
the acceptor is directly excited).

The counts as detected are not $E$ and $S$: donor emission bleeds into the
acceptor channel, the donor laser excites the acceptor a little on its own, and
the two channels have different detection efficiencies and the two fluorophores
different quantum yields. Four **correction factors** — leakage $\alpha$, direct
excitation $\delta$, the detection factor $\gamma$, and the excitation factor
$\beta$ — remove these instrument- and dye-specific biases so that $E$ becomes an
*accurate* efficiency comparable between setups and against a structural model.
This concept is the science/pedagogy layer for that conversion.

It complements — does **not** duplicate — two adjacent concepts.
[fret-calibration.md](fret-calibration.md) records *how ChiSurf obtains the
factors*: the Bayesian light-path-prior → data-optimized-posterior workflow, the
`CalibrationParameters` group, the reference-sample and E–S estimators, and the
session-shared calibration surface. [crosstalk.md](crosstalk.md) records the
*linear-mixing core* (`crosstalk.py`) that the general matrix form of the
correction is built on. This concept explains the underlying observables and the
standard scalar correction algebra those two implement.

The exposition follows the accurate-FRET/ALEX literature — Lee et al. 2005
(*Biophys. J.* **88**:2939, the µs-ALEX E–S framework and the $\gamma$/$\beta$
straightening of the FRET line), Kudryavtsev/Sisamakis/Seidel and co-workers on
multiparameter fluorescence detection (MFD), and Hellenkamp et al. 2018
(*Nat. Methods* **15**:669, the multi-laboratory benchmark whose nomenclature
ChiSurf adopts). Formulas are reimplemented independently; nothing is a verbatim
copy. FRETBursts (Ingargiola et al. 2016) is used as documented prior art for
the workflow narrative.

## Burst search — finding molecules in the photon stream

A confocal smFRET measurement is a long timestamp record that is mostly
background (dark counts, buffer Raman/scatter, out-of-focus fluorophores) with
occasional bright bursts. Two families of algorithm extract the bursts:

- **Sliding-window (Fries) search** — slide a window of $m$ consecutive photons
  along the stream; the *instantaneous count rate* is $m$ divided by the time
  those $m$ photons span. Wherever that rate exceeds a threshold, a burst is
  open; it closes when the rate drops back below threshold. The threshold is set
  **relative to the background**: a burst starts only where the local rate is
  $F$ times the current background rate (typical $F\approx 6$, $m\approx 10$).
  Because the background is estimated in adjacent time windows (see
  [background rates](#background-and-its-role)), the threshold *tracks* drift in
  laser power or buffer over a long acquisition rather than being a fixed number.
- **All-photon vs dual-channel-burst-search (DCBS)** — the search can run on
  *all* photons (best sensitivity to short/dim bursts, the µs-ALEX default) or,
  in ALEX, require a coincident rate increase in **both** the donor-excitation
  and acceptor-excitation streams (DCBS), which suppresses singly-labelled
  species at the search stage.

A found burst is then filtered by a **minimum size** $L$ (total photons). It is
good practice to search with $L=m$ (keep everything the rate criterion found)
and impose the real size cut *afterwards*, on the background-corrected size, as a
separate selection step — this makes the population selection unbiased and lets
the same search feed several size thresholds. Larger bursts give lower shot noise
per molecule but risk two-molecule coincidences; an upper size cut removes
obvious multi-mers.

In ChiSurf the low-level search is `chisurf/core/fluorescence/burst/burst.py`
(`burst_filter`, wrapping tttrlib's `burst_search(min_ph, ph_window,
time_window)` into a per-photon mask); companion detectors in the same package
(`bocpd.py`, `cusum.py`, `kalman.py`) offer change-point alternatives to the
fixed sliding window.

## Photon channels and the per-burst count vector

Once a burst is delimited, its photons are binned by **excitation period ×
detection channel**. The general index convention (shared with
`burst/es.py` and the calibration code) is $I_{ij}$ = photons emitted by
chromophore $j$ while chromophore $i$ is being excited, chromophores numbered
donor $=1$, acceptor $=2$, second acceptor $=3$, … For the ordinary two-colour
donor/acceptor experiment the three counts have friendly aliases:

| Alias | Index | Meaning | Nickname |
|---|---|---|---|
| `i_dd` | $I_{11}$ | donor emission under **donor** excitation | "green" |
| `i_da` | $I_{12}$ | acceptor emission under **donor** excitation (the FRET signal) | "red" |
| `i_aa` | $I_{22}$ | acceptor emission under **acceptor** excitation | "yellow" |

Continuous-wave single-laser FRET has only $I_{dd}$ and $I_{da}$. The third
channel $I_{aa}$ requires **alternating excitation** — µs-ALEX (the acceptor
laser is switched on/off on a microsecond schedule and photons tagged by which
laser was on) or **PIE** (pulsed interleaved excitation, the ns-pulsed analogue,
where the TCSPC micro-time window separates the two lasers). $I_{aa}$ reports
directly on whether an active acceptor is present, and is what makes $S$
computable.

## The two raw observables

Before any factor is applied, background-subtracted counts give the two **raw**
(apparent) quantities. With per-channel backgrounds already removed
($F_{dd}=I_{dd}-B_{dd}$, etc.):

$$
E_\text{raw} \;=\; \frac{F_{da}}{F_{dd}+F_{da}},
\qquad
S_\text{raw} \;=\; \frac{F_{dd}+F_{da}}{F_{dd}+F_{da}+F_{aa}} .
$$

- $E_\text{raw}$ is the **proximity ratio** — the acceptor's share of the
  donor-excited photons. It moves monotonically with FRET (hence with distance)
  but is biased by leakage, direct excitation and the detection factor, so its
  numerical value is instrument-specific and not a true efficiency.
- $S_\text{raw}$ is the **raw stoichiometry** — the fraction of all photons that
  came from donor excitation. Doubly-labelled FRET species sit near $S\approx0.5$,
  donor-only near $S\to1$ (no $F_{aa}$), acceptor-only near $S\to0$.

`apparent_es(i_dd, i_da, i_aa)` in `burst/es.py` returns exactly this pair
(vectorized over bursts; $S=$ `None` when $I_{aa}$ is absent).

## The four correction factors

Turning $E_\text{raw}$ into an accurate $E$ requires four factors, in the
Hellenkamp 2018 nomenclature that ChiSurf uses throughout.

### Leakage α (spectral crosstalk, "lk")

A fraction of **donor** photons is detected in the **acceptor** channel because
the donor emission spectrum has a tail under the acceptor filter. This spurious
acceptor signal is proportional to the true donor signal:

$$
\alpha \;=\; \frac{F_{da}}{F_{dd}}\Bigg|_{\text{donor-only}} .
$$

Measured on a **donor-only** sample (no acceptor, so any $I_{da}$ is pure
leakage). Typical values are a few percent. The leakage-corrected FRET signal
subtracts $\alpha F_{dd}$ from the red channel.

### Direct excitation δ (dir)

The **donor** laser also excites the **acceptor** directly (the acceptor has
non-zero absorption at the donor wavelength), adding acceptor photons to $I_{da}$
that have nothing to do with energy transfer. This part is proportional to the
directly-excitable acceptor signal $F_{aa}$:

$$
\delta \;=\; \frac{F_{da}}{F_{aa}}\Bigg|_{\text{acceptor-only}} ,
$$

measured on an **acceptor-only** sample. (An equivalent parameterization,
used e.g. by FRETBursts, writes the direct-excitation photons as
$n_\text{dir} = d\,(n_a + \gamma n_d)$ with $d$ the ratio of acceptor-to-donor
absorption cross-sections at the donor wavelength; ChiSurf's $\delta$ is the
$F_{aa}$-referenced form.)

The leakage- and direct-excitation-corrected **sensitized emission** — the
genuine FRET photons — is therefore

$$
F_A \;=\; F_{da} \;-\; \alpha\,F_{dd} \;-\; \delta\,F_{aa}.
$$

This is the Gordon/Nagy "three-cube" combination (`crosstalk.correct_three_cube`).

### Detection factor γ (detection + quantum yield)

Donor and acceptor photons are **not detected with equal weight**: the two
detection channels have different collection/filter/detector efficiencies
($g_D$, $g_A$) and the two dyes have different fluorescence quantum yields
($\Phi_D$, $\Phi_A$). The **gamma factor** bundles both:

$$
\gamma \;=\; \frac{g_A\,\Phi_A}{g_D\,\Phi_D}.
$$

$\gamma$ is what makes a photon lost from the donor channel worth the right
number of photons gained in the acceptor channel, so the **accurate FRET
efficiency** is the acceptor's share of the *γ-balanced* budget:

$$
\boxed{\;E \;=\; \frac{F_A}{F_A + \gamma\,F_{dd}}\;}
$$

Equivalently, in terms of the proximity ratio alone (leakage/direct-excitation
already applied),
$E = E_\text{raw}\big/\!\big(\gamma - \gamma E_\text{raw} + E_\text{raw}\big)$ —
the FRETBursts `gamma_correct_E` form. With $\gamma=1$, $\alpha=0$, $\delta=0$
this collapses to $E_\text{raw}$.

### Excitation factor β (excitation flux / cross-section)

The two lasers do not deliver the same effective excitation to their respective
dyes: they differ in power, in beam overlap, and in the dyes' absorption
cross-sections at the two wavelengths. The **beta factor**

$$
\beta \;=\; \frac{I_\text{Aex}\,\sigma_A(\lambda_\text{Aex})}
                 {I_\text{Dex}\,\sigma_D(\lambda_\text{Dex})}
$$

rescales the acceptor-excited channel $F_{aa}$ so that the two excitation arms
are on a common footing. It enters the **accurate stoichiometry**:

$$
\boxed{\;S \;=\; \frac{\gamma F_{dd}+F_A}{\gamma F_{dd}+F_A + F_{aa}/\beta}\;}
$$

$\beta$ affects only $S$ (the vertical axis), not $E$. It is a pure
instrument/dye-pair constant — MASH-FRET, for example, stores per-FRET-pair
`.bet` (β) and `.gam` (γ) factor tables alongside the traces precisely because
they are constants of the setup applied uniformly to every molecule.

These are exactly the equations implemented in `corrected_es(...)`:

```
F_dd = i_dd - Bg_dd ;  F_aa = i_aa - Bg_aa
F_A  = (i_da - Bg_da) - alpha*F_dd - delta*F_aa
E    = F_A / (F_A + gamma*F_dd)
S    = (gamma*F_dd + F_A) / (gamma*F_dd + F_A + F_aa/beta)
```

**Ordering matters, and single-factor shortcuts do not compose.** Applying the
factors one at a time (a γ-only correction, then a leakage-only correction, …)
is *not* algebraically equal to the combined correction above — the chained
result is only approximate. Always apply the full expression in one step
(`corrected_es`), which is why ChiSurf keeps the complete formula rather than a
sequence of per-factor transforms.

## The E–S histogram and straightening the FRET line

The signature plot of ALEX/PIE burst analysis is the **2-D E–S histogram**: each
burst is one point at its $(E, S)$, and the density reveals the populations.

- **Doubly-labelled FRET species** form a horizontal band near $S\approx0.5$;
  their spread *along* $E$ resolves conformational sub-populations or FRET
  states (each fit as a Gaussian in the $E$ marginal).
- **Donor-only** contamination collects at $S\to1$ (no acceptor-excited photons).
- **Acceptor-only** collects at $S\to0$.

Selecting the FRET band (a rectangular or elliptical gate on $E$–$S$, or a cut
$F_{aa}>$ threshold) removes the singly-labelled corners and leaves clean FRET
populations for the $E$ histogram.

The role of $\gamma$ and $\beta$ is geometric as well as numerical. On the *raw*
$E_\text{raw}$–$S_\text{raw}$ plot, a series of FRET species with different
distances does **not** lie on a horizontal line: $S_\text{raw}$ drifts with
$E_\text{raw}$ because the detection imbalance changes the total photon budget as
FRET shifts photons from donor to acceptor. Concretely the population centres
obey a straight line

$$
\frac{1}{S_\text{raw}} \;=\; \Omega \;+\; \Sigma\,E_\text{raw},
$$

with slope $\Sigma$ and intercept $\Omega$ set by the very factors we are after.
Fitting that line across several FRET standards recovers the factors **from the
data**:

$$
\gamma = \frac{\Omega-1}{\Omega+\Sigma-1},
\qquad
\beta = \Omega + \Sigma - 1
$$

(Lee 2005 / Hellenkamp 2018). Applying the resulting $\gamma$ and $\beta$
**straightens the FRET line**: on the corrected $E$–$S$ plot every FRET species
falls on the same horizontal $S\approx0.5$ level, and $E$ is now the accurate
efficiency. This E–S global estimator is `global_es_correction(...)` in
`fret/calibration.py` (it returns `{gamma, beta, Omega, Sigma}`); the
donor-only and acceptor-only estimators supply $\alpha$ and $\delta$.

Once $E$ is accurate it maps to distance through the Förster relation
$E = 1/\!\left[1+(R/R_0)^6\right]$, i.e. $R = R_0\,(1/E-1)^{1/6}$, with $R_0$ the
pair's Förster radius; that last step and the uncertainty budget on $R$ are the
subject of the benchmark study (Hellenkamp 2018).

## Multi-chromophore and the general matrix form

The scalar $\alpha,\beta,\gamma,\delta$ are the **two-colour reduction** of a
general linear-mixing problem. With three or more chromophores (three-colour
FRET, dyes with mutual spectral bleed) the corrections become matrices: an
**excitation** matrix $X_{lk}$ (rate at which laser $l$ excites chromophore $k$)
and an **emission** matrix $D_{km}$ (detected brightness of chromophore $k$ in
channel $m$, folding in $\gamma$ via its diagonal). `corrected_es_general(...)`
consumes those two matrices directly — un-mix the emission
($e = I\,D^{-1}$, optionally non-negative-least-squares for robustness),
subtract direct excitation, then a **coupled donor budget**
$E_{lk}=F_{lk}/(e_{ll}+\sum_a F_{la})$ so a donor quenched by several acceptors
still yields each exact pairwise $E$. It reduces algebraically to the scalar
`corrected_es` when $D=\big[\begin{smallmatrix}1&\alpha\\0&\gamma\end{smallmatrix}\big]$
and $X=\big[\begin{smallmatrix}1&\delta\\0&1\end{smallmatrix}\big]$. The
scalar-but-multi-acceptor middle ground is `corrected_es_matrix(...)`. See
[crosstalk.md](crosstalk.md) for the mixing core and
[fret-calibration.md](fret-calibration.md) for how the light-path calculator
builds $X$ and $D$.

## Background and its role

All four corrections operate on background-subtracted counts, so per-channel
background rates are a prerequisite, not an afterthought. Background is estimated
per detection channel in adjacent time windows (typically ~30 s) and multiplied
by each burst's duration to give the expected background photons subtracted from
that burst's channel counts. Because the sliding-window threshold is itself
$F\times$ background, drift in background propagates into both burst *detection*
and burst *correction* — hence the practice of monitoring background as a
function of measurement time. ChiSurf's background estimators live in
`chisurf/core/fluorescence/burst/background.py` (and `irf_bg.py`).

## Mapping to ChiSurf

- **Per-burst E/S core** — `chisurf/core/fluorescence/burst/es.py`:
  `apparent_es` (raw proximity ratio + raw $S$), `corrected_es` (the scalar
  four-factor correction above), `corrected_es_matrix` (N-cube scalar),
  `corrected_es_general` (light-path matrix form).
- **Correction algebra** — `chisurf/core/fluorescence/crosstalk.py`
  (`correct_three_cube`, `three_cube_fret_efficiency`, `invert_mixing`).
- **Calibration factors** — `chisurf/core/fluorescence/fret/calibration.py`
  (`CalibrationParameters`; `leakage_from_donor_only` → α,
  `direct_excitation_from_acceptor_only` → δ, `global_es_correction` → γ/β from
  the E–S line, `refine_calibration` for the light-path-prior Bayesian
  posterior). Detailed in [fret-calibration.md](fret-calibration.md).
- **Burst search / background** — `burst/burst.py`, `burst/background.py`,
  plus change-point detectors (`bocpd.py`, `cusum.py`, `kalman.py`).
- **Burst plugins** — `chisurf/plugins/burst/` (search & selection
  `burst_selection`, background `burst_background`, browser `burst_browser`,
  BVA `burst_bva`, 2CDE `burst_2cde`, H2MM `burst_h2mm`, MLE `burst_mle_analysis`,
  end-to-end simulate→select→correct `burst_analysis`).

## Pointers

- Adjacent concepts: [fret-calibration.md](fret-calibration.md) (obtaining the
  factors; priors/posterior), [crosstalk.md](crosstalk.md) (linear-mixing core).
- Core: `chisurf/core/fluorescence/burst/es.py`,
  `chisurf/core/fluorescence/crosstalk.py`,
  `chisurf/core/fluorescence/fret/calibration.py`.
- User-facing page: `docs/concepts/smfret_bursts.md`.
- Key literature: Lee et al. 2005 (*Biophys. J.* 88:2939); Kudryavtsev/
  Sisamakis/Seidel MFD; Hellenkamp et al. 2018 (*Nat. Methods* 15:669).
- Documented prior art for the workflow: FRETBursts
  (Ingargiola et al. 2016, *PLoS ONE* 11:e0160716).
