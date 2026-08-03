# FCS saturation & focal-volume expansion

High excitation power changes the effective observation volume in FCS. This
calculator solves an arbitrary N-state photochemical scheme at steady state
across the focus, integrates the resulting emission profile, and tells you how
far your measurement has drifted from the Gaussian model an ordinary FCS fit
assumes.

---

## Why saturation distorts an FCS curve

An FCS fit assumes the detection volume is a fixed 3D Gaussian. That holds only
while the molecule's response to the excitation is linear. It stops holding
when:

1. **The excited state saturates.** Near the focal centre the molecule is
   already excited when the next photon arrives, so emission stops tracking
   excitation. The profile grows a flat top.
2. **A dark state traps population.** A triplet, a photo-isomer or any other
   long-lived non-emitting state removes molecules from the bright cycle for as
   long as it lives — preferentially at the centre, where the excitation is
   strongest. The profile can go from flat-topped to hollow.

### What that costs you

* **Concentration overestimated.** `V_eff` grows, so `G(0) = 1/(c V_eff)` falls
  and an unsaturated fit reports `N` too high — by exactly the `V_eff/V₀`
  factor this tool reports.
* **Diffusion time inflated.** A wider emission profile takes longer to cross,
  so apparent `τ_D` rises with power while `D` has not changed.
* **Extra relaxation terms.** Dark-state cycling adds bunching at the lags of
  those states' lifetimes — microseconds for a triplet, milliseconds for a
  cyanine isomer, which lands right on top of diffusion.

---

## The scheme is yours

Nothing here is specific to triplets. A scheme is three arrays:

* **K_dark[to, from]** — every power-independent rate: fluorescence decay,
  intersystem crossing, isomerisation, thermal recovery, energy transfer.
* **K_exc[to, from]** — relative excitation cross-sections, multiplied by the
  local excitation rate.
* **Q** — the relative brightness of each state.

Two states (ground + excited) is the minimum and six the maximum; a new scheme
starts as the three-state singlet/triplet case because that is what most dyes
do — a default, not an assumption. Diagonals are derived from the column sums and
stay read-only, so what you type is always a valid master-equation generator.

**A state that cannot absorb a photon must have Q = 0.** A ground state with
`Q > 0` would emit outside the focus, and the effective volume would then be set
by the size of the integration grid rather than by the photophysics. The
calculator warns when a scheme does this.

---

## Getting the optics right

| Field | Meaning |
| --- | --- |
| **Excitation λ** | Laser wavelength (nm). Sets the photon energy — the same power delivers 33 % more photons at 650 nm than at 488 nm. |
| **Dye (MMFDB)** | Type-to-search over ~700 entries, matching any part of the name. Reads ε **at the excitation wavelength** off the stored absorption spectrum. |
| **Laser Power** | Total average power at the objective back aperture (mW). The slider is **logarithmic** — drag it to watch the curve respond; results are cached, so revisiting a power is instant. |
| **w_r, w_z** | 1/e² beam waists (nm) — calibration, from a dye standard at low power. |
| **D** | Diffusion coefficient (µm²/s). |

> The catalogued ε is the **peak** value. Exciting a dye off its absorption
> maximum can deliver a small fraction of it, so picking the dye rather than
> typing the peak ε is often the difference between a right and a wrong
> excitation rate.

At **P = 0** the saturated curve equals the unsaturated Gaussian exactly. That
is not an approximation — with no excitation there is no populated scheme.

---

## Reading the panels

* **FCS curve** — unperturbed Gaussian against the saturated curve, plus the
  summary: peak focal excitation rate and `V_eff/V₀`. Tick *Normalize G(τ)* to
  compare shapes rather than amplitudes.
* **Profiles** — the excitation rate, one population curve per state, and the
  emission profile `F(r) = Σ Q_i P_i(r)`. The flattening of `F(r)` is the
  saturation.
* **Volume(P)** / **τ_D(P)** — both quantities swept over power with your
  current power marked. Choose an operating power where these are still flat.
* **State diagram** — drag nodes and rate badges, double-click a badge to edit;
  📂 / 💾 load and save schemes as JSON.
* **Info** — the summary above, in a dock of its own. It starts hidden; restore
  it from the dock's right-click menu when you want it beside the curve.

Every panel is a dock: drag one out, tab it with another, close it and restore
it from the tab bar's menu. The three profile plots open as tabs in one column
so each gets full width.

---

## Rules of thumb

1. **Measure the power dependence.** The defensible number comes from a power
   series extrapolated to zero, not from a correction. This tool tells you how
   far from zero you are.
2. **Calibrate at low power.** Fit `w_r` from a standard (Rhodamine 6G,
   D ≈ 400 µm²/s at 25 °C) below 0.1 mW, then fix it.
3. **Watch the dark-state timescale.** A microsecond triplet is separable from
   millisecond diffusion; a millisecond isomer is not, and will be absorbed into
   your diffusion term if you do not model it.
4. **Fitting?** The same physics is the `FCS (kinetics)` model. Use *Full* mode
   when the amplitude matters — *Fast* mode omits the volume expansion.
5. **Session persistence.** Settings, scheme and layout are saved to
   `~/.chisurf/plugins/fcs_saturation_calc/settings.json` on close.

---

## Further reading

* [Optical saturation in FCS](docs/concepts/fcs_saturation.md)
* [FCS saturation and focal-volume expansion (guide)](docs/guides/56_fcs_saturation.md)
* [Correlation and FCS basics](docs/concepts/fcs_correlation.md)
* Widengren, Mets & Rigler, J. Phys. Chem. **99** (1995) 13368.
  [10.1021/j100036a009](https://doi.org/10.1021/j100036a009)
* Widengren & Schwille, J. Phys. Chem. A **104** (2000) 6416.
  [10.1021/jp000059s](https://doi.org/10.1021/jp000059s)
* Gregor, Patra & Enderlein, ChemPhysChem **6** (2005) 164.
  [10.1002/cphc.200400319](https://doi.org/10.1002/cphc.200400319)
