# Optical saturation in FCS

An FCS curve is usually fitted with a model that assumes the detection volume is
a fixed three-dimensional Gaussian. That assumption is a statement about the
*excitation* profile, and it survives only while the molecule's response to that
profile is linear. Raise the power far enough and it is not: near the focal
centre the molecule spends a large fraction of its time in states that cannot
absorb another photon, so the *emission* profile stops following the excitation
profile. It flattens, then — with a long-lived dark state — dips.

The consequences are quantitative and they all bias in the same direction:

* **The effective volume grows.** `V_eff = (∫F)² / ∫F²` is larger for a
  flat-topped profile than for the Gaussian of the same waist, so `G(0) = 1/(c
  V_eff)` falls. Fitted with an unsaturated model, the concentration comes out
  **too high by exactly the expansion factor**.
* **The apparent diffusion time grows.** A wider emission profile takes longer
  to traverse, so `τ_D` rises with power even though `D` has not changed.
* **New relaxation terms appear.** Population cycling through dark states adds
  a bunching component at the lags of those states' lifetimes — microseconds for
  a triplet, milliseconds for a photo-isomer, i.e. right on top of diffusion.

## The model

ChiSurf solves an arbitrary **N-state photochemical scheme** at steady state, at
every point of the excitation profile. The scheme is three arrays and nothing
more:

| Array | Meaning |
| --- | --- |
| `K_dark[i, j]` | Rate of the power-independent transition `j → i`, in Hz |
| `K_exc[i, j]`  | Relative excitation cross-section for `j → i`; multiplied by the local `k_exc(r, z)` |
| `Q_i`          | Relative fluorescence brightness of state `i` |

Diagonals are derived, never supplied: each matrix is zeroed on the diagonal and
the diagonal set to minus the column sum, so `K(r) = K_dark + k_exc(r) K_exc` is
a proper master-equation generator.

**No state is special.** Two states — a ground state and one emitting excited
state — is the minimum; a new scheme starts as the three-state singlet/triplet
case because that is what most dyes do, but that is a *default*, not an
assumption. A cis isomer, a photobleached state, a FRET partner: each is simply
another state with its own rates and its own `Q`, and the solver treats state 3
no differently from state 6.

The one physical constraint is that a state which cannot be reached by absorbing
a photon must have `Q = 0`; a ground state that emits would glow
outside the focus, and every volume integral below would then be set by the size
of the integration grid rather than by the photophysics. ChiSurf warns when a
scheme does that.

### Excitation rate

For a Gaussian focus of waist `w_r` (1/e² radius) illuminated with total power
`P` at wavelength `λ`:

```
Φ_total    = P / (h c / λ)                      photons / s
k_exc(0,0) = σ_abs · 2 Φ_total / (π w_r²)       s⁻¹
σ_abs      = ln(10) · 1000 · ε(λ) / N_A         cm² → m²
k_exc(r,z) = k_exc(0,0) · exp(-2r²/w_r²) · exp(-2z²/w_z²)
```

Two details matter more than they look:

* **The wavelength is not a decoration.** It sets the photon energy, so the same
  power delivers 33 % more photons at 650 nm than at 488 nm.
* **`ε` must be the value at the excitation wavelength**, not the catalogued
  peak. Exciting a dye 70 nm off its maximum can mean a factor of hundreds.
  ChiSurf reads `ε(λ)` off the stored absorption spectrum when a dye is picked
  from the [MMFDB](../../okf/architecture/mmfdb.md) repository (the chooser is
  type-to-search over ~700 entries, matching any part of the name). Because that
  value is read rather than typed, it is *not* floored at a "sensible" minimum:
  off-maximum excitation legitimately gives a few hundred M⁻¹cm⁻¹ or less, and
  `ε = 0` — a wavelength the dye does not absorb at — simply returns the
  unsaturated Gaussian, since a scheme that cannot be populated cannot saturate.

### From the scheme to G(τ)

The steady-state populations `P_i(r, z)` follow from `K(r) P(r) = 0` with
`Σ_i P_i = 1`, and the emission profile is `F(r,z) = Σ_i Q_i P_i(r,z)`. Its
spatial autocorrelation, evaluated in reciprocal space, is the diffusion part of
the FCS curve:

```
G_diff(τ) = ∫ d³k |F̃(k)|² exp(-D k² τ) / (c (∫F dV)²)
```

computed with a 0-th order Hankel transform along `r` and an FFT along `z`
(the profile is axially symmetric). The amplitude is taken from the real-space
integrals, which satisfy Parseval's theorem exactly, so `G(0) = V₀/V_eff` is
exact at any grid density and only the shape carries quadrature error.

Two exact identities keep this cheap enough to drive from a slider. The
propagator **factorises**, `exp(-D(k_r²+k_z²)τ) = exp(-D k_r² τ)·exp(-D k_z² τ)`,
so the sum over the `(k_r, k_z)` grid needs `(n_r + n_z)·n_τ` exponentials rather
than `n_r·n_z·n_τ` — the rest becomes two matrix products. And the profile is
real, so only the non-negative axial frequencies are computed and the mirror
half is restored by doubling the paired bins. Neither is an approximation; both
are checked against a direct evaluation in the test suite.

Photokinetic relaxation enters as a separate factor evaluated at the peak
excitation rate:

```
X(τ) = qᵀ exp(K τ) (q ⊙ p_eq) / (q · p_eq)²
```

which tends to 1 at long lag and to `Σ Q_i² p_i / (Σ Q_i p_i)²` at τ = 0. The
full model is `G(τ) = b + (1/N) · G_diff(τ) · X(τ)`.

At zero power there is no excitation, no populated scheme and nothing to
integrate: the model returns the analytical Gaussian
`(1+4Dτ/w_r²)⁻¹ (1+4Dτ/w_z²)⁻¹ᐟ²` with amplitude 1, exactly.

### Reading the radial profile

The most counter-intuitive thing this model predicts is that **the ground state
empties in the focal centre**. At 30 mW into a 200 nm waist the peak excitation
rate is ~3.7×10⁴ µs⁻¹ against a 250 µs⁻¹ decay rate, and the steady state at
`r = 0` is

```
S0 = 0.001    S1 = 0.167    T1 = 0.832
```

— the molecule is almost never in the ground state because it is re-excited the
moment it returns, and most of the population has piled into the dark state,
which empties 500× more slowly than it fills. `S0` climbs back to 1 outside the
beam, where there is no light. `S1` is clamped near `1/(1 + k_ISC/k_T)`, which is
what makes the emission profile flat-topped, which is the saturation.

Plot the emission on the same axis as the populations, not scaled to its own
peak: with one bright state it *is* that state's curve, and rescaling it would
show 1.0 in the centre where the bright-state population is 0.17.

## The second apparent diffusion time

The volume expansion is only half the story, and it is the half that shows up as
an amplitude. The other half is a **shape** change, and it is what Widengren and
Rigler pointed out: a saturated curve is no longer *one* diffusion component.

The reason is in the transform. `G_diff(τ)` is a weighted sum of `exp(-D k² τ)`
over the emission profile's power spectrum. For a Gaussian profile that sum
collapses exactly to the familiar `(1+4Dτ/w²)⁻¹(1+4Dτ/z²)⁻¹ᐟ²`. Flatten the
profile and its spectrum broadens — it acquires the higher-`k` content that a
sharper edge implies — so the sum becomes a *wider mixture of decay rates* than
any single Gaussian component can reproduce. Fitting one component to it returns
an inflated apparent diffusion time and leaves a systematic residual.

For the shipped Rhodamine 6G scheme at 200 nm waist, `D = 400 µm²/s`
(`τ_D = 25 µs`), fitting the computed curve with one 3D-Gaussian component:

| Power | V_eff/V₀ | apparent τ_D | one-component residual | two-component fit |
| --- | --- | --- | --- | --- |
| 0 | 1.00 | 25.5 µs | 1.8e-3 | collapses to one |
| 0.2 mW | 1.94 | 42.3 µs | 1.3e-3 | still one |
| 2 mW | 3.51 | 59.9 µs | 1.6e-3 | 3 % @ 12 µs + 97 % @ 64 µs |
| 30.8 mW | 6.14 | 80.5 µs | 5.0e-3 | 8 % @ 14 µs + 92 % @ 99 µs |

Two things to take from it. The apparent `τ_D` is **3.2× too slow** at the top
of that range, so a naive fit reports a diffusion coefficient three times too
small. And above ~1 mW a second, *faster* component appears — carrying a small
amplitude, but enough that one component stops describing the curve. In a real
fit that residual is what tells you the volume is no longer Gaussian; in the
calculator it is the residual panel under the FCS curve, because at a few times
`10⁻³` of the amplitude it is invisible plotted next to a curve of order 1.

The faster component is not an artefact: it is the contribution of the profile's
sharper edge, which decorrelates over a shorter distance than the flat centre.

### Fitting it: a global triplet times two diffusion times

The established analysis is Widengren's: a **global triplet term** multiplying a
**sum of two diffusion components**. Diffusion terms add and bunching terms
multiply, so this needs a summed multi-component diffusion — the `species` mode
of the `FCS (general)` model, with the triplet as one of its bunching terms.

Fitting the simulated 30.8 mW curve (triplet included, as measured) that way
recovers:

| | amplitude | τ_D | |
| --- | --- | --- | --- |
| fast component | 4 % | 4.2 µs | |
| slow component | 96 % | 89.7 µs | true τ_D is 25 µs |
| triplet | T = 0.83 | τ_T = 0.34 µs | |

with rms 2.3e-4 against 7.1e-4 for a single diffusion component.

Two things worth noticing. The fitted triplet time is the **apparent** one,
`1/(k_T + k_ISC·f_S1) = 0.33 µs`, not the scheme's `1/k_T = 2 µs` — excitation
empties the triplet faster than it decays. And two components beat one by only
about three times, not ten, because a *free* triplet partly absorbs the
distortion: a shortened `τ_T` mimics a fast diffusion component over part of the
range. The two are somewhat degenerate, which is exactly why the triplet is
fitted **globally across a power series** rather than per curve.

## Reading the results

`V_eff/V₀` is the number to take away. It is the factor by which an unsaturated
fit overestimates `N`, and (to within a few percent) `τ_D` rises as
`(V_eff/V₀)^{2/3}` — the apparent waist expands roughly isotropically.

The honest way to use any of this is still to **measure the power dependence**:
acquire the same sample at several powers and extrapolate to zero. The
calculator's power sweep tells you where the linear regime ends for your dye and
your objective, which is the power you should have been using all along.

## Two channels, and what comes next

The core functions accept a per-channel brightness matrix and a second profile,
so `G_ab(τ)` — the cross-correlation of two detection channels through the same
saturated volume — is expressible. That is the shape a FRET-FCS treatment needs,
where donor and acceptor channels see the same states with different
brightnesses.

## Further reading

* [Correlation and FCS basics](fcs_correlation.md)
* [Photophysics simulation](photophysics_simulation.md)
* [Guide: FCS saturation and focal-volume expansion](../guides/56_fcs_saturation.md)
* Widengren, Mets & Rigler, *Fluorescence correlation spectroscopy of triplet
  states in solution*, J. Phys. Chem. **99** (1995) 13368.
  [10.1021/j100036a009](https://doi.org/10.1021/j100036a009)
* Widengren & Schwille, *Characterization of photoinduced isomerization and
  back-isomerization of the cyanine dye Cy5 by fluorescence correlation
  spectroscopy*, J. Phys. Chem. A **104** (2000) 6416.
  [10.1021/jp000059s](https://doi.org/10.1021/jp000059s)
* Nagy, Wu & Berland, *Observation volumes and γ-factors in two-photon
  fluorescence fluctuation spectroscopy*, Biophys. J. **89** (2005) 2077.
  [10.1529/biophysj.104.052779](https://doi.org/10.1529/biophysj.104.052779)
* Gregor, Patra & Enderlein, *Optical saturation in fluorescence correlation
  spectroscopy under continuous-wave and pulsed excitation*, ChemPhysChem **6**
  (2005) 164. [10.1002/cphc.200400319](https://doi.org/10.1002/cphc.200400319)
