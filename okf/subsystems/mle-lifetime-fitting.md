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
| Region-wise imaging | `region_mle` → `Fit2xSettings`, fitting the regions `spot_finder` found |

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
- `display.py` — **what a fit looks like, decided without a screen.**
  `decay_curves(data, model, …)` returns everything a decay panel draws:
  per-half windows, an area-matched IRF and background, weighted residuals, and
  pinned ranges. Every rule in it exists because the obvious version looks fine
  on a good fit and unreadable on a bad one — a **diverged** model clipped to
  10× the data (raw, it takes a log view to 1e6 and hides the decay); overlays
  **area**-normalised, never peak-normalised (one hot bin otherwise sets the
  scale); the y-range pinned to the **data** (a background-dominated fit spans
  1e±27 and the auto-range shows all of it); the residual band the **99th
  percentile with a floor** (one bad channel otherwise flattens every other
  residual). Two traps are structural rather than remembered: VV and VH get
  **separate** windows, and residuals are computed on the **full** stacks before
  windowing.

  Two conventions are worth stating because each was got wrong once. The decay
  range is **in counts** — `chiplot`'s `set_ylim` takes data units on every axis
  and log-converts itself, so pre-logging logs twice, which is what put the burst
  tool's decay off the top of its own panel. And divergence can be **told**
  rather than inferred: a parameter pinned at its bound is a fact about the fit,
  where a large drawn amplitude is only a symptom.

The Qt side is `chisurf/gui/widgets/decay_panel.py` (`DecayPanel`) and the
`decay_panel` AutoForm section, so a `view.json` gets the whole two-panel view —
residuals above, decay below, x-linked — in one line. The burst-wise wizard and
the region-wise tool draw the same picture from the same rules; the burst suite
passing against the shared implementation is what says the extraction changed
nothing.

The plugin-scaffolding layer (`gui/tool.py`, `gui/view_model.py`, `api/`, `cli/`)
of the two imaging tools is still largely duplicated; a shared `AutoFormMleTool`
/ `MleViewModelBase` base is a pending refactor.

# Model selection is registry-driven, not hardcoded

The burst wizard offers **every fit2x model tttrlib advertises** rather than a
fixed fit23. The model combo is populated from `tttrlib.registry("fit")` (via
`chisurf.core.tttrlib_registry`, category `FIT_MODEL`); each entry carries a
`method` (the estimator class name), a `label`, and a `params_schema` (JSON
Schema whose `properties` order matches the estimator's `initial_values`
layout). The wizard:

- builds the estimator from the registry's `method` (`_fit_class`, no
  model→class table), and
- rebuilds the parameter editor from the schema (`_rebuild_dyn_params` +
  `_fit_param_names`, which read the schema `properties`), so fit25's `r0` row
  appears automatically without a code change.

Only models whose constructor takes the acquisition inputs (`dt`, `irf`,
`background`, …) are offered — `_is_fit2x_constructible` inspects the class
signature and **skips** reference-decay models like fit26 (`pattern_1`/
`pattern_2`). fit23 keeps its authored rows (with the anisotropy extras); every
other model uses the generic schema-driven editor, the two panels swapping
visibility.

## Batch Run export is model-generic (not fit23-only)

The per-burst batch export (the **Run** button → `process_bursts` → the
multiprocessing `_mp_worker.process_one_file_worker`) runs **every fit2x model**
(fit23/24/25), not just fit23. Three things are wired model-aware:

- the worker builds the **raw tttrlib estimator named by the registry**
  (`cfg['method']`, e.g. `Fit24`), exactly as `wizard.create_fit_instance` does
  for the live preview — so batch and preview use the same estimator and free-
  parameter layout (fit25 keeps its trailing `r0` input; the `Fit2x` facade's
  batch layout drops it, so the worker deliberately bypasses the facade). The
  background is area-normalised in `_build_fitter`, the same rule the facade
  applies (see "background must be area-normalised" below);
- the start vector is per-detector for fit23 (its authored rows differ per
  detector) but a single registry-editor vector for the other models (that
  editor is not per-detector);
- output columns follow the model (`_burst_result_columns` +
  `_mp_worker._record`): fit23 keeps its historical `.b?4` layout byte-for-byte
  (tau/gamma/r0/rho + the two anisotropy columns); other models write `Tau`
  (the best lifetime, `x[0]`) plus one column per registry free parameter and
  **drop** the fit23-only anisotropy columns. `_save_burst_results_fast`
  reindexes so a model that did not emit a column writes NaN rather than raising.

The **tail fit** stays preview-only in batch: it is a different estimator family
(`DecayFitNExp`, no per-burst gamma/anisotropy) and a per-burst multi-exponential
tail fit is under-determined at burst photon counts, so `process_bursts` warns
and returns for it.

## Pixel-wise imaging has the same selector (via the facade batch kernel)

The pixel-wise FLIM tool (`img_pixel_mle`) offers the same **fit23/24/25**
selector, driven through the shared **facade** batch kernel
(`fit_matrix_threaded` → `Fit2x.fit_many`) rather than the raw estimator — that
is the whole point of the fast pixel path (a GIL-released `fit_matrix` per thread
over pixel chunks). Consequences of routing through the facade:

- `fit_matrix_threaded` allocates the result width from the model
  (`len(PARAMETER_NAMES[model]) + 1`), not a hardcoded 5, so fit24/fit25 (6
  columns) work; `img_pixel_mle/core` builds the τ map from `x[0]` for every
  model and the ρ map only for fit23 (`x[3]` is the rotational time only there).
- The **free-parameter set is the facade's** `PARAMETER_NAMES`, so **fit25 has
  no editable `r0`** here (the facade fixes it as a batch input) — unlike the
  burst wizard, which uses the raw estimator and shows the registry's 6th `r0`
  row. The two tools deliberately differ: pixel MLE is bound to the batch kernel.
- The **tail fit is not offered** for pixels (no `fit_matrix` kernel, and a
  per-pixel multi-exponential tail fit is under-determined) — fit2x only.

The GUI is AutoForm-driven: `PixelMleViewModel.view_spec()` is model-aware — it
loads the JSON as a dict and **injects** a `fit_model` combo plus one value/fix
row per free parameter of the selected model (bound to static `p0…p4`
value/fix slots that proxy that model's start vector / fixed mask). The combo's
`call` (`set_fit_model`) fires a `"rebuild"` event; the shared
`AutoFormMleTool._on_model_event` defers a full `auto_form.rebuild()` to the next
event-loop tick (the combo is mid-commit, so an immediate rebuild would delete it
under itself). The core `PixelMleSettings` carries `fit_model` +
`initial_values`/`fixed_flags`; when the latter are `None` it falls back to the
fit23 `tau`/`gamma`/`r0`/`rho` fields (CLI/RPC back-compat). fit23's per-pixel CSV
schema is unchanged byte-for-byte; other models write `tau` + one column per free
parameter + `2I*`.

## Tail fit (a different estimator family)

The combo also offers a **Tail fit (multi-exp)** entry that is *not* a fit2x
model: it routes to `tttrlib.DecayFitNExp` with `DecayFitNExpOptions.tail_start`
set. Each component is a pure exponential from `tail_start` with **no IRF
deconvolution** (the prompt/rise is excluded from the likelihood) — the standard
treatment for FRET sensitised-emission decays whose rise is not a simple
instrument response. Its parameters (a `tail_start` channel + N `tauN` lifetimes)
come from a **local** `_tail_schema()` rather than the fit2x registry, but flow
through the same schema-driven editor. `_run_tail_fit` builds the options from
the header `dt`/`period`, calls `DecayFitNExp.fit` (IRF ignored, background is the
detector's), and exposes the result through the fit2x plotting interface
(`SimpleNamespace(data, model)`), so `plot_fit_result`/`update_fit_ui` are
unchanged; the IRF overlay and the IRF-required guard are skipped in tail mode.

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
