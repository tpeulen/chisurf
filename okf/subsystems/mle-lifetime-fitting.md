---
type: Subsystem
title: MLE Lifetime Fitting (fit2x)
description: The tttrlib Fit23/24/25/26 Poisson-MLE lifetime engine and the input contract every consumer (burst, pixel, molecule) must honour to get correct, stable fits.
resource: chisurf/core/fluorescence/mle/
tags: [core, fluorescence, tcspc, mle, fit2x, imaging, burst, anisotropy]
timestamp: '2026-07-22T00:00:00Z'
---

# Scope

`chisurf/core/fluorescence/mle/` (`fit2x.py`, `parallel.py`) is the Qt-free
facade over tttrlib's `Fit23`/`Fit24`/`Fit25`/`Fit26` Poisson maximum-likelihood
lifetime estimators (the Maus-2001 `2I*` objective). Every per-observation
lifetime fit in chisurf funnels through the same engine:

| Consumer | Path |
| --- | --- |
| Burst-MLE (interactive preview) | `burst_mle_analysis/wizard.py` → `tttrlib.Fit23` directly |
| Burst-MLE (batch run / replay) | `burst_mle_analysis` → `Fit2xSettings` → `fit_matrix` |
| Pixel-wise FLIM | `img_pixel_mle` → `Fit2xSettings` → `fit_map`/`fit_matrix` |
| Molecule-wise imaging | `sm_image_mle` → `Fit2xSettings` |

Because they share one engine, **a fitting bug found in one consumer is a bug in
all of them.** The problems below were first diagnosed in the burst-MLE wizard
(2026-07-22); each is a property of the shared engine, so the fixes are stated
here as a contract every consumer must honour.

## Shared modules (reuse, don't re-copy)

`chisurf/core/fluorescence/mle/` is the common floor. Beyond `Fit2xSettings`,
`Fit2x`, `assemble_vv_vh` and `fit_matrix_threaded`, two small helpers exist so
the consumers stop re-implementing them:

- `parse_detector_setup(payload)` → `DetectorSetup` (`setup.py`): extracts
  channels (+ even/odd ∥/⊥ split), the micro-time window **and** `g_factor`/
  `l1`/`l2` from the shared detector-setup payload. Every consumer's
  `apply_setup_settings` calls this. It exists because both imaging tools used to
  parse the payload by hand and **drop the polarisation corrections**, so the
  fit silently ran at `g=1, l1=l2=0` (see §3).
- `interpolate_shift(arr, shift)` (`irf.py`): the sub-bin IRF shift, previously
  copied verbatim into all three tools.

The plugin-scaffolding layer (`gui/tool.py`, `gui/view_model.py`, `api/`, `cli/`)
of the two imaging tools is still largely duplicated; a shared `AutoFormMleTool`
/ `MleViewModelBase` base is a pending refactor.

# Input contract (the three that actually bite)

## 1. `dt` and `period` are nanoseconds, taken from the file header

`Fit23` reports `tau`/`rho` in units of its `dt` (micro-time channel width) and
convolves over one `period` (excitation period). Both must be **nanoseconds**,
consistent with each other and with the reported lifetime. The channel-definition
GUI cannot supply this: its micro-time field is *picoseconds* (it feeds the
g-factor calculator as `..._ps`) and its macro-time field is nanoseconds, and
neither is auto-filled from the header. Derive both from the TTTR header:

```
dt_ns     = header.micro_time_resolution * 1e9 * binning
period_ns = header.number_of_micro_time_channels * header.micro_time_resolution * 1e9
```

`period` is the full TAC range and is **binning-invariant**
(`n_binned * dt_binned == n_chan * micro_res`). Getting this wrong does not make
the fit diverge — the model still fits the data *shape* — it silently
**mislabels the lifetime** (a decay that visibly falls in ~1 ns was shown as
"5 ns"). The imaging consumers already do this
(`img_pixel_mle/backend/services.py`, `gui/view_model.py`); the burst wizard was
fixed to match (`MLELifetimeAnalysisWizard._header_time_ns`).

## 2. The background must be area-normalised, so `gamma` is a true fraction

The model adds background as `bg[i] * gamma`: **gamma is the *fraction* of the
model that is background**, which only holds if the background pattern has unit
area. Extracted backgrounds are photon histograms summing to thousands of counts,
so a raw pattern makes gamma a multiplier of ~`sum(bg)`: for **any gamma > 0** the
model amplitude blows up by that factor, the Poisson objective goes negative, and
a free-gamma fit diverges to `gamma ≈ 1` ("all background"), with the plot
exploding to ~1e6. Fix: **area-normalise the background before the fit**
(`bg /= bg.sum()`). This is centralised in `Fit2xSettings.__post_init__`, so every
facade consumer is covered at once; the burst wizard's direct-`Fit23` preview
path normalises in `create_fit_instance`.

Do **not** normalise inside tttrlib's `DecayFit23::modelf` — that model is the
cross-language Python/R/Java reference contract
(`tttrlib/test/python/decayfit/test_decayfit_cross_language.py`, mirrored in the R
and Java suites), so changing it breaks parity (it moves `REF_FIT25_TI` et al.).
gamma weighting a caller-normalised background is correct and leaves the contract
untouched.

## 3. Freeing `gamma` needs soft bounds, not a hard clamp (tttrlib)

Even with a normalised background, the free-gamma optimiser used to walk gamma
onto its hard `[0, 0.999]` clamp and **stall at the bound**: a hard clamp makes
the objective flat (zero gradient) beyond the bound, so the line search sees no
reason to come back. tttrlib's header-only L-BFGS (`include/i_lbfgs.h`) gained
optional **soft bounds** — `set_bounds(i, lo, hi)` adds a smooth exterior penalty
that is identically zero inside the box (true objective and the unconstrained path
unchanged) but rises with a real gradient outside — and `DecayFit23::fit` sets
`[0, 0.999]` on gamma for the free pass. The batch kernel `fit_matrix` calls the
same scalar `fit()` per row, so **imaging inherits the soft bounds automatically**;
`fit_matrix`'s tau-only fast path already used the bounded Brent minimiser. With
this, free-gamma converges to the same interior optimum from any start instead of
pinning at 0.999 with a negative `2I*`.

# A poor fit is usually the IRF, not the fitter

When `2I*` is high and the residuals are structured after the above are correct,
the cause is almost always IRF quality: the one-click **auto-extracted IRF is
decay-shaped** (built from the non-burst / low-count photons), so scatter and
signal are hard to separate and gamma trends high. A *measured* IRF/background
gives lower gamma and better residuals. `test_mle_fit_simulation` pins that the
fit machinery itself is correct and well-conditioned, so real-data failures point
at the inputs, not the estimator. See also `okf/references/vv-vh-decay-format.md`
for the VV/VH (Jordi) layout the engine expects.

# Defence in depth

The burst wizard's `plot_fit_result` flags a non-physical result
(`_fit_diverged`: `2I* < 0`, non-finite model, or model amplitude ≫ data), clips
the displayed model, and shows a status warning, so a pathological fit can never
blow the plot up again even if a future input violates the contract. Imaging
consumers write NaN for pixels/molecules that fail (`fit_map` masks low-count
pixels), so they degrade gracefully rather than emitting garbage lifetimes.

# Related

* [Fluorescence domain](/subsystems/fluorescence-domain.md) — the wider Qt-free kernel.
* [Fitting engine](/subsystems/fitting.md) — the least-squares `Fit`/`FitGroup` path (distinct from this Poisson-MLE engine).
* [Imaging plugins](/plugins/imaging.md), [Burst plugins](/plugins/burst.md) — the consumers.
