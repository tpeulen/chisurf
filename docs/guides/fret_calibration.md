# Accurate FRET: calibration

:::{admonition} Theory
:class: seealso
See {ref}`concept-fret` for the Förster mechanism and the R0 / efficiency relations calibration rests on.
:::

Turning raw single-molecule photon counts into an **accurate** FRET efficiency
requires a handful of instrument/photophysics **calibration factors**. ChiSurf
models these as ordinary [fitting parameters](../reference/user_models.md) with a Bayesian
workflow: the **light-path calculator** provides a physically-motivated *prior*,
and **optimizing against the measured data** yields the *posterior* factors used
for accurate FRET. The same calibration can be shared across many datasets
(global analysis) and pushed to ndxplorer.

The core is Qt-free (`chisurf.core.fluorescence.fret.calibration` and
`chisurf.core.fluorescence.burst.es`), so everything below runs head-less, from
the CLI, or in a notebook. A complete runnable example ships at
`chisurf/plugins/burst/burst_analysis/examples/FRET_Calibration.ipynb`.

## The correction

Following Hellenkamp *et al.* (Nat. Methods **15**, 669, 2018), a measured
channel is written $I_{ij}$ = photons emitted by chromophore $j$ under excitation
of chromophore $i$, with chromophores numbered in order (donor $1$, acceptor $2$,
second acceptor $3$, …). For the common two-colour donor/acceptor case the
friendly aliases are

* $I_{11} \equiv$ `i_dd` — donor emission under donor excitation ("green"),
* $I_{12} \equiv$ `i_da` — acceptor emission under donor excitation ("red", the
  FRET channel),
* $I_{22} \equiv$ `i_aa` — acceptor emission under acceptor excitation
  ("yellow", ALEX/PIE).

Four correction factors (Greek-letter convention):

| factor | symbol | meaning |
|---|---|---|
| leakage | $\alpha$ | donor emission bleeding into the acceptor channel |
| direct excitation | $\delta$ | acceptor directly excited by the donor laser |
| detection | $\gamma$ | detection·quantum-yield ratio $(g_R\,\Phi_A)/(g_G\,\Phi_D)$ |
| excitation flux | $\beta$ | green/red excitation-flux ratio (stoichiometry) |

These four scalars are the **two-colour special case** of the general
correction. Physically, leakage and detection live in the **emission crosstalk
matrix** and direct excitation lives in the **excitation crosstalk matrix** — the
two matrices the light-path calculator produces. ChiSurf can correct directly
from those matrices (see [The general case](#the-general-case-crosstalk-matrices)
below), which also handles three or more chromophores and channel bleed the
scalars cannot express; the scalar path is the convenient reduction when there
are exactly two colours.

The background-subtracted, corrected efficiency and stoichiometry are

$$F_{11} = I_{11}-B_{11}, \quad F_{22} = I_{22}-B_{22},$$
$$F_{12} = (I_{12}-B_{12}) - \alpha\,F_{11} - \delta\,F_{22},$$
$$E = \frac{F_{12}}{F_{12} + \gamma\,F_{11}}, \qquad
S = \frac{\gamma F_{11} + F_{12}}{\gamma F_{11} + F_{12} + F_{22}/\beta}.$$

```python
from chisurf.core.fluorescence.burst.es import apparent_es, corrected_es

app = apparent_es(i_dd, i_da, i_aa)          # raw proximity ratio + raw S
cor = corrected_es(i_dd, i_da, i_aa,         # accurate E and S
                   gamma=1.4, alpha=0.08, delta=0.05, beta=1.0)
E, S = cor["E"], cor["S"]
```

## Where the factors come from

ChiSurf offers three complementary routes; use any or all of them.

:::{admonition} Want this done for you?
:class: tip
The **Accurate FRET** tool determines all four factors automatically from a
single burst table — it finds the donor-only, acceptor-only and FRET populations
itself, combines the estimates with the light-path prior, and adds a third route
via the donor lifetime and the static FRET line. See the
{doc}`tutorial </guides/41_accurate_fret>`; this page describes the underlying
API, which remains the right choice when the reference samples were measured
separately.
:::

### 1. Light-path prior → data-optimized posterior

The [light-path calculator](../reference/plugins/index.md) computes the spectral crosstalk matrices
of the optical setup (spectra, filters, detector QE). Those give a
*physically-motivated* value for each factor, attached as a **Gaussian prior**;
the factor stays free and is refined against the data.

```python
from chisurf.core.fluorescence.fret.calibration import (
    CalibrationParameters, set_priors_from_lightpath, refine_calibration)

calib = CalibrationParameters()
# matrices = light_path.get_crosstalk_matrices()
set_priors_from_lightpath(calib, matrices, donor="Alexa488", acceptor="Alexa647",
                          green_detector="green", red_detector="red", r0=52.0)

# optimize against burst E-S data (labels = population index per burst)
post = refine_calibration(calib, i_dd, i_da, i_aa, labels)
```

`refine_calibration` returns the **posterior** `gamma` as the precision-weighted
combination of the data estimate (from the E-S population fit, with an
uncertainty bootstrapped over bursts) and the light-path prior: strong data
follows the data, scarce data falls back to the physically-motivated prior.

### 2. Reference samples (donor-only, acceptor-only)

The standard smFRET procedure derives the factors directly from reference
measurements: $\alpha$ from a **donor-only** sample (its acceptor channel is pure
leakage), $\delta$ from an **acceptor-only** sample (pure direct excitation), and
$\gamma$/$\beta$ from the $1/S$-vs-$E$ population fit (Lee *et al.* 2005;
Hellenkamp *et al.* 2018).

```python
from chisurf.core.fluorescence.fret.calibration import calibrate_from_samples

out = calibrate_from_samples(
    calib,
    fret=(i_dd, i_da, i_aa, labels),        # >= 2 FRET populations
    donor_only=(don_i_dd, don_i_da),         # alpha
    acceptor_only=(acc_i_da, acc_i_aa, acc_i_dd),  # delta
)
```

### 3. The donor lifetime and the static FRET line

The two routes above need either reference samples or at least two FRET
populations of different efficiency. A single-population sample identifies
$\gamma$ neither way — but its **donor lifetime** does. A static population must
lie on the static FRET line, so the detection factor is whatever makes the
intensity-based efficiency agree with the lifetime-based one:

```python
from chisurf.core.fluorescence.fret.accurate import gamma_from_lifetime
from chisurf.core.fluorescence.fret.lines import static_fret_line

line = static_fret_line(4.0, r0=52.0, sigma=6.0)   # tau_D(0), R0, linker width
est = gamma_from_lifetime(i_dd, i_da, tau_f, line=line, alpha=0.08, delta=0.05)
```

This works without acceptor excitation (ALEX) altogether. Running it *after*
calibration turns the same comparison into a dynamics test — see
{ref}`concept-accurate-fret`.

### All three at once

```python
from chisurf.core.fluorescence.fret.accurate import auto_calibrate

result = auto_calibrate(i_dd, i_da, i_aa, tau_f=tau_f, line=line,
                        lightpath={"matrices": matrices, "donor": "Alexa488",
                                   "acceptor": "Alexa647",
                                   "green_detector": "green",
                                   "red_detector": "red"},
                        n_bootstrap=100)
print(result.report())
```

`auto_calibrate` finds the populations itself (a Gaussian mixture over the
stoichiometry, iterated to self-consistency), takes each factor from whichever
route identifies it, and returns the precision-weighted posterior together with
bootstrap uncertainties.

## The general case: crosstalk matrices

Hellenkamp's four scalars assume two colours and no acceptor→acceptor bleed. The
general correction consumes the two crosstalk matrices the
[light-path calculator](../reference/plugins/index.md) produces and needs no scalar factors at all:

* the **excitation matrix** $X_{lk}$ — the rate at which laser $l$ directly
  excites chromophore $k$ (absorption × flux); off-diagonals are direct
  (cross-) excitation;
* the **emission matrix** $D_{km}$ — the detected brightness of chromophore $k$
  in channel $m$ (spectrum × filter × detector QE × quantum yield); off-diagonals
  are spectral leakage, and the diagonal carries the detection/quantum-yield
  weighting that reduces to $\gamma$.

The correction is un-mix → subtract direct excitation → coupled donor budget:

$$e_{lk} = \big(I_{lm}-B\big)\,D^{-1}, \quad
F_{lk} = e_{lk} - \frac{X_{lk}}{X_{kk}}\,e_{kk}, \quad
E_{lk} = \frac{F_{lk}}{e_{ll} + \sum_a F_{la}}.$$

The first step (un-mixing with $D^{-1}$) removes *all* spectral crosstalk —
including bleed between acceptors — and puts every chromophore on a common
emission scale, which is why no explicit $\gamma$ appears. For two colours with
$D=\left[\begin{smallmatrix}1&\alpha\\0&\gamma\end{smallmatrix}\right]$ and
$X=\left[\begin{smallmatrix}1&\delta\\0&1\end{smallmatrix}\right]$ this is
algebraically identical to `corrected_es` above.

```python
from chisurf.core.fluorescence.burst.es import corrected_es_general
from chisurf.core.fluorescence.fret.calibration import general_correction_from_lightpath

# straight from the two crosstalk matrices (intensity[laser, detector])
res = corrected_es_general(intensity, excitation, emission)

# or straight from a light-path get_crosstalk_matrices() payload
res = general_correction_from_lightpath(
    intensity, matrices,
    chromophores=["D", "A1", "A2"], lasers=["Lg", "Lr", "Ly"],
    detectors=["green", "red", "yellow"])
E_01 = res[(0, 1)]["E"]   # donor 0 -> acceptor 1
E_02 = res[(0, 2)]["E"]   # donor 0 -> acceptor 2
```

### Naive vs. stable un-mixing

Step 1 (un-mixing with $D^{-1}$) is the numerically delicate part. When two
emission spectra overlap strongly, $D$ becomes ill-conditioned: the plain
pseudo-inverse (`unmix="naive"`, the default) then amplifies shot noise and can
return **negative** emissions — unphysical, and it blows the efficiency outside
$[0, 1]$. Two standard remedies (both selectable):

* `unmix="stable"` — **non-negative least squares** per burst, enforcing
  emissions $\ge 0$ (the physical constraint). Robust to strong spectral overlap;
  slower because it solves per burst rather than as one matrix multiply.
* `ridge=λ` — **Tikhonov regularization** that damps the noise amplification of an
  ill-conditioned $D$ at the cost of a small bias. Combine with either method.

```python
# non-negative, ill-conditioning-robust un-mixing (+ optional Tikhonov damping)
res = corrected_es_general(intensity, excitation, emission, unmix="stable", ridge=1e-3)
```

For well-conditioned setups the two agree; reach for `"stable"` when acceptor
spectra overlap heavily or the signal is photon-starved. Both share the same core,
`chisurf.core.fluorescence.crosstalk.invert_mixing` (which also backs the
phasor-FLIM spectral unmixing).

### Preserving photon-counting statistics (integer "photon shuffling")

Both un-mixing methods above return **fractional** source signals, which discards
the integer / Poisson nature of photon-counting data — a problem for
shot-noise-limited downstream analysis (burst variance, BVA, maximum-likelihood
fits). `photon_shuffle_unmix` instead **reassigns each detected photon to a
source** by a multinomial draw, so the output is a non-negative **integer**
per-source photon stream:

```python
from chisurf.core.fluorescence.crosstalk import photon_shuffle_unmix

# counts[detector, burst] -> integer counts[source, burst]
sources = photon_shuffle_unmix(counts, emission, seed=0)
```

The assignment probability that a photon in detector $m$ came from source $k$ is
$P(k\,|\,m)\propto a_k\,B[k,m]$, where $B$ is the row-normalised emission matrix
(each source's spectral shape) and $a_k$ the source abundance (from the NNLS
fit). This **preserves the total photon count exactly**, stays non-negative and
integer, and — because a multinomial thinning of a Poisson count yields
independent Poisson counts — **preserves the shot-noise statistics**. Its expected
value equals the continuous (Richardson–Lucy / EM) unmixing, so it is unbiased on
average; the draw is its stochastic, integer realisation.

## ndxplorer: stable / shuffle un-mixing

ndxplorer's native FRET correction is a scalar linear subtraction with no matrix
inversion or positivity constraint. To give it the robust un-mixing,
`push_unmixed_columns_to_ndx` reads the measured per-channel photon-count columns
from an open ndx window, un-mixes them (stable NNLS by default, or `"shuffle"` for
integer photons) with the light-path emission matrix, and injects the leakage-free
per-source photon columns back into ndx — leaving ndx's native columns untouched,
so nothing is double-corrected:

```python
from chisurf.plugins.ndxplorer.calibration_bridge import push_unmixed_columns_to_ndx

push_unmixed_columns_to_ndx(
    ndx_window,
    emission=emission,                       # light-path emission matrix
    channel_columns=["Number of Photons (green)", "Number of Photons (red)"],
    source_labels=["donor", "acceptor"],
    unmix="shuffle", seed=0)                  # or unmix="stable"
```

Nothing about the channel naming is hard-coded — the caller passes the emission
matrix, the measured-channel column names and the source labels (all obtainable
from the light-path calculator), so the same bridge serves any N-colour setup.

## Per-pixel / FLIM imaging

The correction cores broadcast over trailing axes, so the same calibration applies
per pixel to FLIM / PIE / ALEX image stacks. `corrected_es_image` takes the
per-pixel photon-count channels as an `(n_laser, n_detector, H, W)` tensor and
returns per-pixel accurate FRET-efficiency maps, masking photon-starved pixels:

```python
from chisurf.core.fluorescence.fret.pixel import corrected_es_image, pixel_source_photons

# intensity[laser, detector, y, x] ; stable un-mixing; dim pixels -> NaN
res = corrected_es_image(intensity, excitation, emission,
                         unmix="stable", min_counts=20)
E_map = res[(0, 1)]["E"]          # H×W efficiency image (NaN where masked)

# integer, Poisson-preserving per-source photon images (H×W per source)
sources = pixel_source_photons(counts, emission, unmix="shuffle", seed=0)
```

### Scalar multi-chromophore path

When there is no acceptor→acceptor bleed, the scalar factors extend to an
$N\times N$ matrix directly. A donor is quenched by *all* its acceptors, so the
efficiency uses the same **coupled donor budget**

$$E_{ij} = \frac{F_{ij}/\gamma_{ij}}{F_{ii} + \sum_k F_{ik}/\gamma_{ik}},$$

which recovers each pairwise efficiency exactly (a naïve pairwise correction
would bias $E_{ij}\to E_{ij}/(1-E_{ik})$) and reduces to the two-colour formula
for a single acceptor.

```python
from chisurf.core.fluorescence.burst.es import corrected_es_matrix

# intensity[i, j] = excite i, detect j; gamma/alpha/delta are (N, N) matrices
res = corrected_es_matrix(intensity, gamma, alpha, delta)
```

For cross-leakage *between* acceptors use `corrected_es_general`, which un-mixes
the detection channels as part of the correction.

## Global analysis and ndxplorer

A calibration can be **shared across datasets**. `register_calibration` exposes
it as a link target so any fit's correction parameter can be linked to the one
shared factor — refining the calibration once updates every linked fit.

```python
from chisurf.core.fluorescence.fret.calibration import (
    register_calibration, link_to_calibration)

register_calibration(calib, name="Setup calibration")   # appears in the link menu
link_to_calibration(my_fit.model.parameters_all_dict["gamma"], calib, "gamma")
```

The optimized calibration can also be pushed into an open
[ndxplorer](../reference/ndxplorer_headless_cli.md) window so its per-burst/per-pixel derived
FRET uses the data-optimized factors:

```python
from chisurf.plugins.ndxplorer.calibration_bridge import push_calibration_to_ndx
push_calibration_to_ndx(ndx_window, calib)
```

## Validating with simulated data

`BurstWorkflow.simulate(..., gamma=…)` bakes a **known** detection factor into a
`tttrlib` photon simulation (recorded on `GroundTruth.gamma`), so an end-to-end
calibration can be checked against ground truth (simulate → select bursts →
correct → recover the true efficiencies). See
`test/plugins/burst/test_calibration_simulation.py` and the example notebook.

## See also

- Concepts: {ref}`concept-fret` (the Förster mechanism and $R_0$),
  {ref}`concept-smfret-bursts` (the E/S observables being corrected).
- Deriving the factors from reference dye solutions:
  [RCM detection calibration](07_rcm_calibration.md); from the FRET sample
  itself: [RCM from FRET-labelled samples](25_rcm_from_fret_samples.md).
- Where E and S come from: [multi-parameter E–S](14_multiparameter_es.md);
  the background rates the correction subtracts:
  [background rates](15_background_rates.md).
- Source: `chisurf/core/fluorescence/fret/calibration.py`,
  `chisurf/core/fluorescence/burst/es.py`,
  `chisurf/core/fluorescence/crosstalk.py`.

## References

* B. Hellenkamp *et al.*, "Precision and accuracy of single-molecule FRET
  measurements — a multi-laboratory benchmark study", *Nat. Methods* **15**, 669
  (2018).
* N. K. Lee *et al.*, "Accurate FRET measurements within single diffusing
  biomolecules using alternating-laser excitation", *Biophys. J.* **88**, 2939
  (2005).
