---
type: Assessment
title: Code-Review Findings Queue
description: Auto-maintained queue of code-review findings — produced by the review job, consumed by the fix job.
tags: [review, findings, queue, automation]
timestamp: '2026-07-25T00:00:00Z'
---

# Code-review findings queue

The shared work queue between two scheduled jobs (see
[scheduled-jobs](/workflows/scheduled-jobs.md)):

- **`com.chisurf.review-code`** *appends* verified findings here (status `OPEN`).
- **`com.chisurf.fix-issues`** *consumes* them: picks one `OPEN` finding, fixes it
  behind a test+lint gate, and flips it to `FIXED` (or `WONTFIX` with a reason).

This is distinct from the curated [cleanup backlog](/specs/assessment.md): that is
the human-authored gap-vs-target list; this is the automated review↔fix channel.
Promote a recurring or structural finding into the assessment backlog by hand when
it deserves first-class tracking.

## Format

One finding per `###` block. `RF-NNN` ids increment monotonically; never reuse a
number. Keep each finding **small, specific, and independently fixable** — a
finding the fix job can close in one 30-minute, test-gated run.

```
### RF-001
- **Status:** OPEN | FIXED | WONTFIX
- **Severity:** S1 (correctness/crash) | S2 (contract/consistency) | S3 (cleanup)
- **Location:** path/to/file.py:LINE (symbol)
- **Finding:** one or two sentences — what is wrong and why, verified against the source.
- **Fix note:** (filled by the fix job) what was changed + the test that pins it, or why WONTFIX.
```

## Findings

<!-- The review job appends new ### RF-NNN blocks below this line. -->

### Review 2026-07-25 — phasor cursors, expression engine, canonical form

Slice: the three newest landings — `45dec1c9` (phasor cursors as regions),
`4e0ef54b` (safe expression engine), `fa5d649b` (canonical form / GaussianEngine).
The rotation convention claimed "bit-identical" in `45dec1c9` **does** match
(`EllipseROI.contains` rotates by `-angle`, the old cursor by `R(-a)`); the
degenerate-radius case does not. Findings RF-001..RF-006 below.

### RF-001
- **Status:** FIXED
- **Severity:** S1 (correctness)
- **Location:** `chisurf/plugins/microscopy/img_pixel_phasor/analysis.py:355` (`mask_from_circular_cursor`) via `chisurf/core/roi/roi.py:410` (`EllipseROI.contains`)
- **Finding:** A zero-radius circular cursor now selects **every** pixel instead of none. `EllipseROI.contains` treats a zero radius as unbounded (`rx = self.rx if self.rx > 0 else np.inf`), so `(dx/inf)**2 + (dy/inf)**2 == 0 <= 1` is True everywhere. The pre-`45dec1c9` implementation computed `(g-cg)**2 + (s-cs)**2 <= 0.0`, i.e. essentially nothing. Verified: `mask_from_circular_cursor([0,0.5,1],[0,0.5,0],(0.5,0.5),0.0)` returns `[True, True, True]`. The elliptic path is inconsistent with this — `cursor_roi` explicitly raises `ValueError` on a zero semi-axis, but the circular path performs no such check, and `phasor.cursor_mask` happily accepts `radius: 0` from an RPC client or a spin box wound to its minimum. Result: a silently whole-plane gate feeding `pseudo_color`/fraction maps.
- **Fix note:** Fixed at the root in `EllipseROI.contains`: a zero radius is now
  an axis with *no* extent rather than an unbounded one — the `np.inf`
  substitution still keeps the division finite, but the collapsed axis adds an
  exact-equality constraint (`dx == 0` / `dy == 0`), so a zero-radius circle
  selects only its centre and a single zero semi-axis collapses the ellipse onto
  a segment. That restores the pre-`45dec1c9` phasor behaviour and makes every
  ROI consumer (gating, `to_mask`, `regionprops`) degenerate-safe. The phasor
  inconsistency is closed on top: `cursor_roi` now refuses a zero *radius* on the
  circular path with the same `ValueError` the elliptic path already raised, so
  `phasor.cursor_mask` returns a structured error instead of a whole-plane mask
  for `radius: 0` from an RPC client. Pinned by
  `test/core/test_roi.py::test_ellipse_with_a_zero_radius_has_no_extent` (both
  the point-like and the segment case) and
  `img_pixel_phasor/test/test_analysis.py::test_a_zero_radius_cursor_is_refused`.
  `test/core/test_roi.py`, `test_regionprops.py`, `test_roi_builders_io.py`, the
  `img_pixel_phasor`, `img_coloc`, `clsm`, `img_pixel_mle`, `sm_image_mle`,
  `test_ratio_fret.py`, `test_frap.py` and `test_drift.py` suites all green
  (284 tests); `ruff check` adds no new findings on the touched files.

### RF-002
- **Status:** OPEN
- **Severity:** S2 (contract)
- **Location:** `chisurf/core/fitting/engine.py:599` (`GaussianEngine.form`)
- **Finding:** `form()` caches the canonical form in `self._form` and never invalidates it; the only resets are `__init__` and `run()`. `conditional()` calls `self.form()`, so once a form has been built, re-fitting the model (new optimum, new curvature) leaves `conditional()` silently answering from the stale posterior — no re-run, no warning, no staleness check. The base class has the `_ran`/`_require_run()` machinery for exactly this hazard, but `conditional()` bypasses it (deliberately — it is the "no re-run" fast path). Either tie `_form` to a fit/parameter version, or make `conditional()` state its precondition and `_require_run()`.
- **Fix note:**

### RF-003
- **Status:** FIXED
- **Severity:** S2 (missing invariant)
- **Location:** `chisurf/core/fitting/canonical.py:82` (`CanonicalForm.from_moments`), used at `canonical.py:190,254`
- **Finding:** `CanonicalForm` indexes its scope by name (`index = {n: i for i, n in enumerate(self.names)}`) but never enforces that names are unique, and `from_moments` accepts duplicates without complaint. A duplicate silently resolves to the **last** occurrence: verified with scope `('tau','tau','x')` and variances `(0.01, 4.0, 1.0)`, `marginal(['tau'])` returns the second one (`mean 5.0, var 4.0`) and `condition({'tau': 2.0})` drops only the second, leaving a form still containing a variable named `'tau'`. `__mul__` already assumes uniqueness (it dedupes the union scope by name). Wrong answers, not an exception. The `GaussianEngine` path happens to be safe today (global fits prefix names with the fit index, `globalfit.py:151`), so this is a latent contract gap in a public, composable module — fix by validating in `from_moments`/`__post_init__`.
- **Fix note:** `CanonicalForm.__post_init__` now rejects a scope that repeats a name (`ValueError`, listing the repeats), which covers `from_moments`, direct construction and `marginal(keep)` with a duplicated entry alike; `from_moments` and `marginal` document the new `ValueError`. Pinned by `test/fitting/test_canonical_form.py::test_a_repeated_name_is_refused`, which exercises all three routes. Reproduced against `HEAD` first: scope `('tau','tau','x')` with variances `(0.01, 4.0, 1.0)` silently returned `mean 5.0, var 4.0` from `marginal(['tau'])` and left `'tau'` in scope after `condition({'tau': 2.0})`. `test/fitting/test_canonical_form.py` (16), `test_posterior_engine.py` (16), `test_factor_graph.py` (13), `test_posterior_api.py` (8), `test_collapsed_sampler.py` (8), `test_independent_components.py` (11), `test_covariance_errors.py` (11) and `test_frozen_structure.py` (14) all green; `ruff check` clean.

### RF-004
- **Status:** FIXED
- **Severity:** S2 (correctness trap)
- **Location:** `chisurf/core/expressions.py:113` (`DEFAULT_CONSTANTS`) and `expressions.py:273` (`_RefRewriter.visit_Name`)
- **Finding:** `visit_Name` resolves a bare identifier against `policy.constants` **before** treating it as a reference, so a caller symbol whose name collides with a built-in constant is unreachable and silently replaced by the constant — with `validate_expression` reporting `ok=True`. `DEFAULT_CONSTANTS` contains `tau`, which in a time-resolved-fluorescence code base is *the* name for a lifetime. Verified: `evaluate_expression('tau * 2', {'tau': 5.0})` returns `12.566…` (= 4π), not `10.0`; `evaluate_expression('e + 0', {'e': 100.0})` returns `2.718…`. There is no escape hatch — quoting (`'tau'`) is the only workaround and it is undocumented. Either prefer the symbol table over constants when the name is present, or drop/rename `tau` and `e` in `DEFAULT_CONSTANTS` and warn on a shadowed name.
- **Fix note:** Fixed the general trap rather than the one name: a caller symbol
  now always wins over a named constant. The `tau` half of the finding was
  already stale — `9faa62b52` dropped `tau` from `DEFAULT_CONSTANTS` — but the
  structural hole was still live for `e`, `pi`, `inf` and `nan` (verified
  against `HEAD`: `evaluate_expression('e + 0', {'e': 100.0})` returned
  `2.718…`, and `validate_expression('e * 2', ['e'])` reported `ok=True` with
  `refs=()`, so the equation editor marked the row ✓ while ignoring the user's
  column). The decision cannot be taken in `visit_Name`, which runs at compile
  time and is cached per `(text, policy)` with no symbol table in sight, so a
  constant name is now rewritten to a `_c{j}` slot (deduplicated per name)
  alongside the existing `_r{i}` reference slots, and `evaluate_expression`
  fills it from the symbol table when a symbol of that name resolves and from
  `policy.constants` otherwise. `refs` is deliberately unchanged, so a constant
  is still neither an unresolved name in `validate_expression` nor a free
  parameter in `discover_parameters`. Pinned by
  `test/core/test_expressions.py::test_a_symbol_shadows_a_constant_of_the_same_name`,
  `::test_constants_still_apply_without_a_symbol` (including the
  repeated-constant case) and `::test_a_shadowed_constant_is_not_a_free_parameter`.
  `test/core/test_expressions.py` (33) plus `test/gui/test_equation_editor.py`,
  `test_expression_input.py` and `test_parse_widget_expression_editor.py` (23)
  all green; `ruff check` clean on both touched files (their `ruff format` drift
  is pre-existing at `HEAD` and was left alone).

### RF-005
- **Status:** OPEN
- **Severity:** S3 (consistency)
- **Location:** `chisurf/core/fitting/engine.py:756` (`GaussianEngine.conditional`)
- **Finding:** `conditional()` hard-codes `low=mean - sd, high=mean + sd, p_value=0.68`, while every other interval in the module derives the multiplier from the requested coverage (`z = _normal_quantile(0.5 + 0.5 * p_value)` at lines 127, 509, 697). For the same nominal `p_value=0.68` the two disagree (`z ≈ 0.9945` vs a hard `1.0`), and `conditional()` accepts no `p_value` argument at all, so a 95 % conditional interval cannot be requested from the one engine whose selling point is cheap conditional queries.
- **Fix note:**

### RF-006
- **Status:** OPEN
- **Severity:** S3 (validation hole)
- **Location:** `chisurf/core/expressions.py:271` (`_RefRewriter.visit_Name`)
- **Finding:** A whitelisted function name used outside a call is left in the AST as a plain `Name`, so a bare function name is accepted as a complete expression and evaluates to the callable itself. Verified: `validate_expression('sqrt', [])` returns `ok=True, refs=()` and `evaluate_expression('sqrt', {})` returns `<ufunc 'sqrt'>`. In the equation editor this marks the row ✓ green and lets a ufunc object flow into a derived data column instead of numbers. Not a sandbox escape (attribute access is still blocked), but the validator should reject a function reference that is not called.
- **Fix note:**

### Review 2026-07-25 (2) — RICS precision prediction, time-binned dynamic PDA

Slice: the two newest landings that carry physics — `2c3ea0317` (RICSPE port,
`chisurf/core/experiments/ics/precision.py`, 566 new lines) and `06b7340c2`
(time-binned dynamic PDA: reader segmentation + `k_ex` as a rate). Also read
`d230c59c1` (`ROI.to_indices`): the refactor is exactly equivalent to the
arithmetic it replaced (`selected[0] == iy0*nx+ix0`, `selected[-1] ==
(iy1-1)*nx+(ix1-1)`) — nothing to report there.

Method note: the two-point correlation `correlation_grid` is a useful control —
it is *exactly* invariant when every length is re-expressed in nm instead of µm,
which is what exposed RF-007. Findings RF-007..RF-011 below.

### RF-007
- **Status:** OPEN
- **Severity:** S1 (wrong math)
- **Location:** `chisurf/core/experiments/ics/precision.py:236` (`triple_correlation`, the `v15`/`t17`/`e3` block)
- **Finding:** The three-point correlation is **not dimensionless**, so its value depends on the unit lengths are expressed in — which a correlation function cannot. Verified by re-expressing the same physical situation in nm instead of µm (lengths ×s, `d` ×s²): `triple_correlation((3,2),(0,0),(3,2), …)` returns 0.01408 in µm, 0.02255 in nm — a factor 1.6 — while `correlation_grid` on the same rescaling is invariant to 1e-16. Isolating the factors shows `e1` and `e2` are invariant and **`e3` is the culprit**: its exponent `|v15|²/t17` scales as 1/s² (0.951 → 0.0095 → 9.5e-7 for s = 1, 10, 1000), i.e. it carries dimension L⁻². Two transcription errors are visible by inspection: inside `v15 = r1*(w²/4*t11 + 2*d*t2*t12) + r3*w⁴/16 + r2*t11` the first two terms are L⁵ and the third is L³; and `t17 = t16 * w⁶/64 * term7` is L¹² where |v15|² is L¹⁰ (compare the correct `e2`, where `|v13|²` and `t14` are both L⁶). Impact at the default µm units: `e3 = 0.62` instead of ~1, i.e. the shot-noise diagonal `term1` is off by ~1.6×; scaling `triple_correlation` by 1.6 moves the reported relative error of the test acquisition from 0.096 to 0.105, and zeroing it gives 0.094 — small at bright settings, larger wherever shot noise dominates. Re-derive against the reference `RICSPE` and pin with a unit-rescaling invariance test (which `correlation_grid` already passes).
- **Fix note:**

### RF-008
- **Status:** FIXED
- **Severity:** S2 (crash on valid input)
- **Location:** `chisurf/core/experiments/ics/precision.py:505` (`rics_precision`, the 3-D `q` brightness correction)
- **Finding:** `root = math.sqrt(1.0 - beta)` with `beta = 1/alpha²` makes the 3-D branch crash for any focus that is not elongated: `w_z == w_r` (alpha = 1, beta = 1) divides by `root == 0` — verified `ZeroDivisionError: float division by zero` — and `w_z < w_r` raises `ValueError: math domain error` from the sqrt. Neither is a genuine singularity: the limit exists and the function is smooth through alpha = 1. Verified by evaluating the same expression with `cmath`: q = 0.79796 at alpha = 1.5, 0.797959 at 1.000001, 0.797959 at 0.999999 and 0.79758 at 0.8 — continuous, real-valued and finite on both sides (for beta > 1, `atanh` of an imaginary argument is `i·atan`, and the `1/root` prefactor cancels it). The docstring documents only a `ValueError` for inconsistent scan timing, so this reaches the caller as a bare arithmetic error with no message.
- **Fix note:** The singularity was in the *transcription*, not in the physics:
  `sqrt(1 - beta)` appears both inside the `atanh` and as the divisor, so it
  cancels. Factoring it out — `atanh(z)/z` as a function of `z**2 = (1 - beta) *
  ((fact - 1)/(beta + fact - 1))**2`, which is real on both branches — removes
  it. The new `_atanh_over_argument` helper covers the three cases: `atanh(z)/z`
  for an elongated focus, `atan(y)/y` for a squat one (the analytic continuation
  through the imaginary axis) and the series `1 + z²/3 + z⁴/5` through the
  removable singularity at `z = 0`. Numerically identical to the old expression
  where the old one ran (rel. 1.6e-14 at the shipped `alpha = 5`, worst 8e-10
  over a grid of alpha/dwell/D — the residual is cancellation in the *old* form),
  and now continuous through `alpha = 1`: `q` = 0.0996812745046 / 0.0996812742930
  / 0.0996812740810 at alpha = 1.000001 / 1 / 0.999999 where the old code gave a
  value / `ZeroDivisionError` / `ValueError: math domain error`. Pinned by
  `test/experiments/test_ics_precision.py::test_a_focus_that_is_not_elongated_is_an_ordinary_acquisition`
  (predicts for `w_z` below, at and above `w_r`, and checks the spherical case
  against the limit approached from the elongated side). `test/experiments/`
  green (60 tests); `ruff check` adds no findings on the touched files.

### RF-009
- **Status:** FIXED
- **Severity:** S3 (validation hole)
- **Location:** `chisurf/core/experiments/ics/precision.py:485` (`rics_precision`), via `precision.py:385` (`correlation_covariance`, `denom`)
- **Finding:** Scan timing is validated (`pixel_time * nx > line_time` raises a clear `ValueError`), but the two other inputs that can only fail are not. `n_lags >= min(nx, ny)` makes `denom = (nx - xi) * … * f**4` zero: verified `rics_precision(10.0, …, nx=6, ny=6, n_lags=6)` → `ZeroDivisionError: float division by zero`, and `correlation_covariance(6, 6, 6, …)` the same, while `nx=8` still returns a matrix (whose smallest eigenvalue is -0.22, so `nearest_spd` is doing real work there rather than mopping up round-off). `diffusion_coefficient=0` divides by zero in `tau_c = w_r**2 / (4*d)`. Both are one-line guards next to the existing timing check; the defaults (`n_lags=6`, `nx=ny=64`) are safe, so this only bites a caller that shrinks the image or sweeps `D` down to zero.
- **Fix note:** Both halves are closed, neither by this entry. The
  `diffusion_coefficient=0` half was fixed earlier by the positivity block now
  at `precision.py:583` (it rejects `pixel_time`, `line_time`, `pixel_size`,
  `w_r`, `w_z` and `D` alike) and is pinned by
  `img_precision/test/test_img_precision.py::test_the_estimator_rejects_unphysical_settings`.
  The `n_lags` half is the same defect as the later, sharper
  [RF-057](#rf-057), which supersedes this one — it identifies the negative
  position count below `n_lags >= min(nx, ny)` and the `sweep_dwell`
  interaction that a bare `ValueError` would create — and was fixed there.
  Recorded as FIXED rather than WONTFIX because the behaviour the finding
  describes is genuinely gone: `rics_precision(10.0, …, nx=6, ny=6, n_lags=6)`
  and `correlation_covariance(6, 6, 6, …)` now both raise a `ValueError`
  naming the pair.

### RF-010
- **Status:** OPEN
- **Severity:** S2 (default contradicts its own docstring; biased result)
- **Location:** `chisurf/core/models/pda/dynamic.py:209` (`PdaDynamicTwoStateModel.__init__`, `n_grid: int = 41`)
- **Finding:** The parameter docstring immediately below states "512 is accurate to ~1e-4 in the mean occupancy even at fast exchange. The previous default of 41 was sized for a direct density evaluation and **is far too coarse here**" — yet the default is still 41, and `grep -rn n_grid` shows **no caller anywhere passes it**, so every fit runs at the value the docstring condemns. The bias is real and grows with exchange: `two_state_occupation_quadrature(p1=0.3, K, n_nodes=n)` gives E[f] = 0.30252 / 0.33593 / 0.34200 at K = 1e3 / 1e4 / 1e6 for n=41, against 0.30000 / 0.30000 / 0.30942 at n=512 and 0.3 exactly at n=4096 — a 14 % error in the mean occupancy where the model's own `x1` says 0.3 (at `p1 = 0.5` symmetry hides it, which is why the shipped tests do not catch it). This matters more since `06b7340c2`: `k_ex` is now an absolute rate with `ub=1e9` Hz and `K = k_ex * T`, so the fast-exchange regime is easy to wander into. Either raise the default to 512 or correct the docstring — the two cannot both stand.
- **Fix note:**

### RF-011
- **Status:** OPEN
- **Severity:** S2 (user-visible setting silently ignored)
- **Location:** `chisurf/core/experiments/pda/reader.py:626` (`PdaReader.read`, the `n_colors >= 3` branch) vs `pda.view.json` "Segmentation" panel
- **Finding:** The new `segmentation` choice is rendered unconditionally in the reader editor (the panel in `pda.view.json` carries no visibility condition), but the three-colour path `return`s at `reader.py:649` before `segmentation` is ever consulted — it is read only at line 666, in the two-colour loop. A user who selects "Fixed time bins (constant duration)" on a three-colour setup silently gets a burst search instead, and the `pda3c` payload built by `_three_color_curve` (`reader.py:195`) records neither `segmentation` nor `observation_time`, so nothing downstream can tell that the request was dropped — the same silent-disagreement failure the commit removed the `T_win` spinner to prevent. Either honour the setting on the tcPDA path, or gate the panel on `n_colors == 2` and say so.
- **Fix note:**

### GUI test 2026-07-25 — TCSPC lifetime fit walked through the main window

Driven headlessly through the real main window (experiment/setup combo boxes,
`macros.add_dataset`, `onAddFit`, the `ConvolveWidget` IRF selector,
`FittingControllerWidget.onRunFit`) on `test/data/tcspc/ibh_sample/`. The fit
itself is correct — χ²ᵣ = 1.63, τ = 4.2 ns with the Prompt as IRF — but the GUI
around it fails silently under a condition that costs the user their whole
session. See [usecases/tcspc-lifetime-fit](/usecases/tcspc-lifetime-fit.md).
Findings RF-012..RF-017 below.

### RF-012
- **Status:** OPEN
- **Severity:** S1 (silent total loss of function)
- **Location:** `chisurf/gui/widgets/fitting/fitting_client.py:207` (`FittingClient._try_bootstrap_transport`, the `if not rpc_is_available(...)` branch)
- **Finding:** A second ChiSurf instance adopts the **first instance's** RPC server instead of starting its own, and then every fitting operation silently does nothing. The bootstrap only asks whether *something* answers on `127.0.0.1:{cmd_port}/{pub_port}` (default 8765/8766) and, if so, skips server creation and connects a `ChisurfClient` to it; the sole validation is `client.call("meta.ping", {})`, which any ChiSurf server answers. There is no check that the server owns *this* process's session. Verified this run: with a live `python -m chisurf` (PID 22424) holding 8765, a freshly started instance attached to it and `fit.list` returned `{'ok': True, 'fits': []}` while `session_state_from_live_chisurf()` in the same process listed the fit — so `fit.range.auto`, `fit.set_fit_range`, `fit.update`, `fit.run`, `model.finalize` and `fit.set_result_idx` all returned `"fit not found"`, each merely logged by `_try_rpc`. User-visible result: **Fit** returns in 0.03 s, χ²ᵣ stays `-0.0000`, no parameter moves, no error is shown. Re-running the identical driver with `cs_settings["mmfdb"]["cmd_port"] = 18765` fits correctly (χ²ᵣ 5.22, then 1.63 with the IRF), which isolates the cause. Two ChiSurf windows is an ordinary thing to do, and a stale `python -m chisurf.server` reproduces it just as well. Either bind a per-process/per-session port, or verify session ownership after `meta.ping` and fall back to an own embedded server when the identity does not match.
- **Fix note:**

### RF-013
- **Status:** OPEN
- **Severity:** S1 (GUI displays a value the model does not have)
- **Location:** `chisurf/gui/widgets/fitting/fit_controller.py:907` (`FittingControllerWidget.onAutoFitRange`), same hole in `onFitRangeChanged` (`fit_controller.py:820`)
- **Finding:** The fit range is applied to the fit **only** through the RPC client; when that call fails the GUI keeps showing the range anyway. `onAutoFitRange` correctly falls back to a local `self.fit.data.data_reader.autofitrange(...)` for the *value*, writes it into the spin boxes (whose signals are blocked for the duration, so no `onFitRangeChanged` fires), then calls `fc.set_fit_range(...)`; the local assignment `self.fit.fit_range = (xmin, xmax)` sits in the `elif fc is None:` branch, so a *failed* RPC leaves the fit untouched. Verified: controller spin boxes read **522 / 3793** while `fit.fit_range == (0, 0)` and the plot annotation read `Range 0, 0`; `fit.run()` on that state raises `TypeError: Improper input: N=4 must not exceed M=(0,)` from `leastsqbound.py:436` because the range selects zero points. Typing the range in by hand does not recover it — `onFitRangeChanged` has the same RPC-only structure. The fallback must be on RPC *failure*, not only on RPC *absence*.
- **Fix note:**

### RF-014
- **Status:** OPEN
- **Severity:** S2 (success reported for work that did not happen)
- **Location:** `chisurf/gui/widgets/fitting/fit_controller.py:711-735` (`FittingControllerWidget._run_fit_impl`)
- **Finding:** `_run_fit_impl` treats "the RPC returned `None`" as success. `fc.run_fit(...)` swallows every failure inside `FittingClient._try_rpc` and returns `None`; only `OptimizationCancelled` is caught, so control falls into the `else:` branch, which logs **"Fitting finished!"**, sets `success = True`, closes the progress dialog with the text *"Fitting finished!"*, and records a `fit_run_finish` history entry with `"success": true`. Verified: with the fit unreachable over RPC (RF-012) the button reported a finished fit while χ²ᵣ stayed `-0.0` and no parameter changed; the only evidence of failure was an ERROR line in the log dock. Check the RPC result (`ok`/`chi2r`) and surface a failure to the user — a fit that did not run must not be recorded as a fit that did.
- **Fix note:**

### RF-015
- **Status:** OPEN
- **Severity:** S2 (crash from an offered choice)
- **Location:** `chisurf/gui/widgets/models/tcspc/convolve.py:120` (`ConvolveWidget.irf_select`) → `chisurf/macros/model.py:202` (`change_irf`)
- **Finding:** The IRF picker offers the auto-created **"Global Dataset"** (an `ExperimentDataGroup`, shown with data type `Global`) alongside the TCSPC curves, and selecting it raises an uncaught `AttributeError: ExperimentDataGroup object has no attribute 'x'` from `change_irf`, which does `DataCurve(x=irf_curve.x, y=irf_curve.y)` with no type check. Verified this run: the dialog listed `[(0, 'Global Dataset', 'Global'), (1, 'Decay_577D.txt', 'TCSPC'), (2, 'Prompt.txt', 'TCSPC')]` and clicking row 0 produced the traceback (twice — once via `handleSelectionChange`, once via the explicit `change_event`), after which the driver did not reach its next step. Two clicks from a freshly created fit. `ExperimentalDataSelector` filters on `isinstance(d.experiment, self.experiment)`, which does not exclude group datasets; filter to curve-like datasets, and make `change_irf` reject anything without `x`/`y` with a message instead of a traceback.
- **Fix note:**

### RF-016
- **Status:** OPEN
- **Severity:** S3 (clipped value — user reads the wrong number)
- **Location:** `chisurf/gui/widgets/models/tcspc/tcspc_convolve.ui` (the `FWHM` label + `lineEdit_2` row), rendered by `chisurf/gui/widgets/models/tcspc/convolve.py:50`
- **Finding:** In the **Convolve** section the `FWHM` label and its read-only value box collide with no spacing, and the box is clipped at the panel's right edge so the value loses its leading characters: with the Prompt IRF loaded, `fwhm = 0.2538` is set via `"%.3f" % v` = `"0.254"` but renders as **`.254`**; before the pick, `0.226` is likewise cut. Verified in two grabs of the widget at its natural width (463 px). A user reading `.254` cannot tell whether the leading digit was `0` or something else. Give the row a stretch/minimum width or move FWHM onto its own line.
- **Fix note:**

### RF-017
- **Status:** OPEN
- **Severity:** S3 (bare IndexError instead of a clear error)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:899` (`Convolve.__init__`, `dt = data.dx[0]`)
- **Finding:** `Convolve.__init__` indexes `data.dx[0]` with no guard on an empty array, so building a TCSPC model on a dataset that carries no points raises `IndexError: index 0 is out of bounds for axis 0 with size 0` from four frames below the call. Verified this run by dispatching `fit.add` with the auto-created empty Global dataset and `model_name="Lifetime "` (the console/macro path — `MainWindow.onCurrentDatasetChanged` filters the toolbar's model list by the dataset's experiment, so the toolbar does not reach it): the traceback surfaced through `FitGroup.__init__` → `Fit.model` → `LifetimeModel.__init__`. Guard the empty case and raise a message naming the dataset.
- **Fix note:**

### Review 2026-07-25 (3) — PSIS prior reweighting

Slice: the newest landing, `c3e4facb7` (reuse a finished chain under a different
prior) — `chisurf/core/fitting/reweight.py` (575 new lines), the `sampling_chain`
capture in `sample_fit` (`fit.py:2060`), `ChiSurfAPI.reweight_prior` and
`fits.fit_reweight_prior`.

**The PSIS core is sound and nothing is filed against it.** Checked directly
rather than taken on trust: `gpd_fit` recovers a *known* generalised-Pareto shape
and scale from simulated exceedances — over 200 fits of 2000 points, `k_hat` =
0.099 / 0.301 / 0.499 / 0.699 / 0.995 against k_true = 0.1 / 0.3 / 0.5 / 0.7 /
1.0, with `sigma_hat` = 2.00 throughout (true 2.0). End to end on a shifted-normal
importance problem the reported verdict tracks the real damage: mu = 0 / 0.5 / 1.5
/ 3 / 5 gives k = 0.00 / 0.23 / 0.44 / 0.91 / 1.57 and ESS 20000 / 15523 / 1831 /
60 / 7, with `reliable` flipping to False exactly where the mean first departs
(2.77 for a true 3.0). The Zhang–Stephens grid, the `expm1(lw - cutoff)`
factoring, the truncation at the largest raw weight and the shrinkage prior all
match Vehtari et al. as documented.

Every finding below is in the *integration* — what the module is handed and what
it hands back. RF-018..RF-023.

### RF-018
- **Status:** OPEN
- **Severity:** S2 (silently wrong numbers, reported as reliable)
- **Location:** `chisurf/core/fitting/reweight.py:542` (`reweight_prior._old_prior`), reached from `chisurf/server/services/fits.py:1338` (`model=getattr(fit, "model", None)`)
- **Finding:** `_old_prior` returns `None` both for "this parameter has no prior" and for "this parameter is not on the model I was given", and the caller cannot tell the two apart — so a failed lookup makes the reweighting *add* the new prior on top of the old one instead of replacing it, with no warning and `reliable=True`. Verified against ground truth: a chain drawn from N(4.0, 0.10) reweighted to the **identical** prior must be an exact no-op, and is when the old prior is supplied (`sd` 0.09926, equal to the chain's own 0.09926); with the old prior not found it returns `sd` 0.07035 — the double-counted 0.10/√2 — and `warnings` is empty. This is reachable, not hypothetical: `fit_reweight_prior` always passes `fit.model`, which for a chain sampled with `global_posterior=True` is the *selected member's* model and not `factorgraph.posterior_model(fit)`, the model the chain actually came from. Distinguish "absent" from "flat" — return a sentinel, or warn on `changed` entries whose old prior could not be located.
- **Fix note:**

### RF-019
- **Status:** OPEN
- **Severity:** S2 (ambiguous name silently resolves to one column)
- **Location:** `chisurf/core/fitting/reweight.py:531` (`reweight_prior`, the `short.setdefault(...)` map) and `:548` (`_old_prior`'s short-name comparison)
- **Finding:** Short-name resolution on a prefixed global chain is first-wins with no ambiguity check, so a name that matches several columns silently reweights one of them. Verified on a chain with `parameter_names = ['1:tau1', '2:tau1']`: `reweight_prior(..., {'tau1': ...})` reweighted column 0 (`1:tau1` moved 4.000 → 4.040, `2:tau1` untouched), raised nothing, and reported `changed = ['tau1']` — the caller's spelling, not the resolved column, so the output does not disclose which parameter was used. `'2:tau1'` is reachable only by its full name, while `'tau1'` silently means member 1. `_old_prior` has the identical flaw on the other side (`str(p.name).split(":")[-1] == name.split(":")[-1]` returns the first match in `parameters_all`), so a global fit can pick up member 2's prior for member 1's column. `_position` already raises `KeyError` for an unknown name — raise for an ambiguous one too, and put the resolved full names in `changed`.
- **Fix note:**

### RF-020
- **Status:** OPEN
- **Severity:** S2 (assumption not recorded and not checkable)
- **Location:** `chisurf/core/fitting/fit.py:2072` (the `sampling_chain` dict) vs `chisurf/core/fitting/sample.py:138` (and `:495`, `:674`, `:1218`)
- **Finding:** The reweighting identity `w ∝ π_new/π_old` holds only for draws from `L·π_old`, but every sampler accepts `temp` and targets `exp(lnprob/temp)` — the Metropolis ratio is `delta = (candidate - current) / temp` at all four sites. `sample_fit` forwards `temp` verbatim (`fit.py:1794`, and `fit_sample_start` merges `optimization.sampling` settings plus arbitrary `**kwargs` into it), so a tempered chain can reach `reweight_prior`, which then computes the untempered ratio and returns a wrong posterior. PSIS cannot catch it — a tempered chain is merely wider, so the weights stay benign and `pareto_k` stays low. The information needed to detect or correct it exists but is thrown away: `save_chain_to_file` deliberately keeps `chi2r` and `lnprior` per draw ("lets the stored posterior be reweighted under a different prior afterwards"), while `sampling_chain` stores only `parameter_values`/`chains`. Record `temp` (and ideally the per-draw `chi2r`/`lnprior`) on `sampling_chain` and refuse or correct when `temp != 1`. Note `chi2max` is *not* affected — the truncation multiplies the likelihood and cancels in the ratio.
- **Fix note:**

### RF-021
- **Status:** OPEN
- **Severity:** S3 (RPC contract: keys a client cannot predict)
- **Location:** `chisurf/server/services/fits.py:1332` (`tail = 0.5 * (1.0 - float(p_value))`) → `chisurf/core/fitting/reweight.py:404` (`str(q)` as the dict key)
- **Finding:** `weighted_summary` keys the quantile dict by `str(q)`, and the RPC derives `q` arithmetically from `p_value`, so the keys carry float noise. Verified: the default `p_value=0.68` yields `'0.15999999999999998'` and `'0.8400000000000001'`; `p_value=0.95` yields `'0.025000000000000022'` and `'0.975'` (one clean, one not, in the same response). Calling `reweight.reweight()` directly at the same nominal coverage gives `'0.16'` / `'0.84'` from the default tuple, so the two entry points disagree on the key for the same interval and a client keying on `'0.16'` gets a `KeyError` over RPC only. Round the derived quantiles, or key by a formatted probability.
- **Fix note:**

### RF-022
- **Status:** OPEN
- **Severity:** S3 (resource: the discarded burn-in is never released, and the kept draws are stored twice)
- **Location:** `chisurf/core/fitting/fit.py:2070-2076` (`kept = chain[:, burn_in:, :]`)
- **Finding:** The comment says the post-burn-in draws are kept, but `chain[:, burn_in:, :]` is a **view** — verified `kept.base is chain` — so storing it under `'chains'` pins the entire pooled array, burn-in included, on the fit for the life of the session. `'parameter_values'` is then `kept.reshape(-1, ...)`, which on a non-contiguous slice is an independent full **copy** (`flags['OWNDATA']` is False but `base` is neither `chain` nor `kept`), so the same post-burn-in numbers are resident twice. For the shipped defaults (`n_runs: 10`, `steps: 1000`) pooled over emcee's ≥10 walkers this is ~100 × 1000 × n_par doubles held twice per sampled fit, and it grows linearly with `steps`. One `np.ascontiguousarray(kept)` releases the burn-in and lets `'parameter_values'` be a reshape view of it rather than a second copy.
- **Fix note:**

### RF-023
- **Status:** OPEN
- **Severity:** S3 (inconsistent sanitisation)
- **Location:** `chisurf/server/services/fits.py:1349-1358` (`"pareto_k": float(k) if np.isfinite(k) else None`)
- **Finding:** The RPC comment states that `inf`/`nan` "neither survives JSON" and converts `pareto_k` to `None`, but the per-parameter payload on the *same* response can carry raw `NaN` and is not touched. Verified on the case the module is built to handle — a new prior whose support is disjoint from the chain — where every draw is excluded: `pareto_k = inf` (sanitised to `None`) while `parameters[0]` is `{'mean': nan, 'sd': nan, 'quantiles': {'0.025': nan, ...}}`, and `json.dumps` on that emits bare `NaN` tokens, which are invalid JSON. It happens to round-trip because both ends are Python (`send_json`/`recv_json`), but the special case for `pareto_k` is then either incomplete or unnecessary — pick one and apply it to the whole payload.
- **Fix note:**

### GUI test 2026-07-25 (2) — FCS diffusion fit walked through the main window

Driven headlessly through the real main window (experiment/reader combo boxes,
`macros.add_dataset`, the dataset tree, the **Add fit** tool button, the
`ParseFCSWidget` equation combo, the range spin boxes typed + Enter,
`FittingControllerWidget.button_fit`) on
`test/data/fcs/kristine/Kristine_with_error.cor`, on a private RPC port so RF-012
could not mask anything. The fit itself is fast and the plots are good, but every
run reports a physically impossible shape factor, the brightness readout is
wrong, and the headline diffusion time depends on a persisted reader setting.
See [usecases/fcs-diffusion-fit](/usecases/fcs-diffusion-fit.md). Findings
RF-018..RF-025 below.

### RF-018
- **Status:** OPEN
- **Severity:** S2 (physically impossible fitted values, reported with confidence)
- **Location:** `chisurf/core/models/fcs/models.yaml` (all 50 entries) via `chisurf/gui/widgets/models/parse/widget.py:268` (`load_model_file` / `set_default_parameter_values`)
- **Finding:** The shipped FCS parse-model catalogue defines **no parameter bounds** — every entry carries only `equation`, `initial`, `description` — so one click of **Fit** from the shipped defaults returns values that cannot exist. Verified this run on `Kristine_with_error.cor` with `3D Gauss`: `s = −4.26347 ± 0.0661`, likelihood interval `[−4.3296, −4.1973]`, printed in the editor and the *Info* tab in exactly the style of the good parameters. `s` is the axial/lateral aspect ratio ω_z/ω_xy and appears in the equation only as `1/s**2`, so ±s are indistinguishable: re-setting `s = +3.5` and re-fitting gives `+4.22866` with an **identical** χ²ᵣ of 7.69180 — the optimizer simply crosses zero and stays in the mirror branch. Note `abs(N)` in the same equation shows the author guarded `N`'s sign but nothing guards `s`. The same hole bites the bunching models: `3D Gauss, 1 bunching` converges to `ba = −0.36188 ± 9.49e-05 (0.0 %)` (a negative blinking amplitude, CI entirely below zero) and `bt = 6.2169e-06` ms ≈ 6 ps — three orders of magnitude below the 13.6 ns first lag, listed as "no estimate" — while χ²ᵣ *rose* from 7.6918 to 7.7777. `s > 0` (typically 1…20), `0 ≤ ba ≤ 1` and `bt ≥ first lag` are all knowable a priori, and the per-parameter editor already renders a *Bounds / Low / High* section (`parameter_widgets.py:167`), so this needs a bounds field in the YAML schema plus sane values, not new UI.
- **Fix note:**

### RF-019
- **Status:** OPEN
- **Severity:** S2 (same input, 5× different headline result, no warning)
- **Location:** `chisurf/core/experiments/fcs/reader.py:160` (`weight_mode_key`) + `fcs.view.json` "Noise model" panel; consequence surfaces in every FCS fit
- **Finding:** The reader's noise model silently decides the fitted diffusion time. Same file, same equation (`3D Gauss`), same range (20…206), same start values, only the *Noise model* combo differs: `Photon-noise (Suren)` → `td = 0.20858 ms`, `s = ±4.23`, `N = 0.3710`, χ²ᵣ = 7.6918; `From file (default)` → `td = 1.0564 ± 0.0224 ms (2.1 %)`, `s = 0.30531 ± 0.00568`, `N = 0.36208`, χ²ᵣ = 2.4137. That is a factor 5 in the quantity the measurement exists to determine, and both are reported with ~2 % likelihood intervals and no caveat. The weights themselves differ by ~2× (file `ey` mean 0.02551 vs photon-noise 0.01304), which explains the χ²ᵣ scale but not the parameter jump: with `s` unbounded (RF-018) the `(td, s)` pair has at least two minima (`td·s² ≈ 3.7` vs `td/s² ≈ 0.098`) and the weighting picks between them. Worse, the mode is **restored from user settings** (`Restored setup defaults from user settings` at startup; this machine had `weight_mode='photon_noise'` while the shipped default is `None` = from file), so which answer a user gets depends on a setting they may not remember choosing and which is not shown anywhere near the result. Bound `s`, and surface the active noise model in the fit window next to χ²ᵣ.
- **Fix note:**

### RF-020
- **Status:** OPEN
- **Severity:** S2 (every FCS fit logs 6 ERROR tracebacks; a control does nothing)
- **Location:** `chisurf/gui/widgets/models/fcs/parse_fcs_widget.py:376,412,445,464` (`fit_index=getattr(self.fit, "fit_idx", None)`)
- **Finding:** `ParseFCSWidget` addresses all its RPC writes with `fit_index=getattr(self.fit, "fit_idx", None)`, but `self.fit` is the **member `Fit` inside the `FitGroup`**, and only the group carries `fit_idx`. Verified this run: `cs.fits[-1]` is a `FitGroup` with `fit_idx = 0`, `model.fit` is a `Fit` with `fit_idx = None`; consequently the client sends no target and the server's `_resolve_fit(state, None, None)` returns `(None, -1)` → `RemoteError: fit not found`. Direct comparison on the live session: `fit.update({"fit_index": 0})` → `{'ok': True}`, `fit.update({})` → `fit not found`, while `fit.list` reports the fit at index 0. User-visible consequences: (a) **six ERROR tracebacks per created FCS fit** — `parameter.set_value` and `parameter.set_fixed` for `S`, `cpm`, `cpm_all` — each merely logged by `FittingClient._try_rpc`; (b) the **Apply background correction** checkbox is dead: `_on_bg_correction_toggled` calls `fc.update_fit(...)` with the same `None` index, so no recompute happens and the plotted model is unchanged (verified: `checked=True`, curve identical, χ²ᵣ identical; it only changes after an unrelated `model.update()`). Pass the group's index (or the member's `unique_identifier`, which `_resolve_fit` matches against group members) and stop treating a failed write as success.
- **Fix note:**

### RF-021
- **Status:** OPEN
- **Severity:** S2 (wrong number shown to the user)
- **Location:** `chisurf/gui/widgets/models/fcs/parse_fcs_widget.py:408-450` (`update_model`, the `cpm` / `cpm_all` block)
- **Finding:** Straight after a fit the *FCS parameters* block reports counts-per-molecule equal to the **total count rate**. Verified with a traced `compute_cpm`: at fit creation it is called with `N = 1` (`cpm = 18.2639 kHz = S`), during the fit it is called with the converged `N = 0.37083` and correctly returns `49.2511 kHz` — yet the editor, `model.parameters_all_dict['cpm']` **and** the server-side fit DTO (`fit.list`) all still read `18.2639` when the fit finishes, for both `cpm` and `cpm_all`. Only a subsequent `model.update()` (i.e. any later interaction) brings the display to `49.2511`. Because `cpm = S/N` is exactly the molecular brightness a user quotes to judge aggregation or labelling degree, reading the raw count rate instead is a silent factor-`N` error (here 2.7×). Related to RF-020 — the value is written only through the RPC client, with no local assignment and no check on the result — but the stale value persists even where the RPC is reachable, so the post-fit finalization path needs to recompute and push it.
- **Fix note:**

### RF-022
- **Status:** OPEN
- **Severity:** S2 (upgraded installs get a crashing experiment and lose new ones)
- **Location:** `chisurf/gui/main_helper.py:664` (`source_config_file = pathlib.Path(cs.core.settings.get_path('cs')) / "settings" / "experiment_configs.yaml"`)
- **Finding:** The GUI builds the experiment registry from the **user's** `experiment_configs.yaml` alone, because the path it uses for the shipped defaults never exists: `get_path('cs')` returns the *settings* directory (`~/.chisurf`), so `source_config_file` resolves to `~/.chisurf/settings/experiment_configs.yaml` (the packaged file lives at `chisurf/core/settings/experiment_configs.yaml`, which `chisurf/core/experiments/bootstrap.py:148` locates correctly). Two failure modes follow from `source_config_file.exists() == False`: the "Experiment configuration update available" prompt can never fire, and `default_configs` loads empty so `experiment_configs = user_configs` — no merge with the shipped defaults ever happens. Verified on this (upgraded) install: startup logs 7 `Failed to resolve class chisurf.core.experiments.rics.RICSReader / chisurf.core.models.rics.rics.Rics*Model` ERRORs; the Experiment combo offers `['TCSPC','PDA','DEER','FCS','PCF','RICS','PCH','Modelling']` — a **dead `RICS` entry** (the section was renamed to `ics` in the shipped file) whose selection leaves the reader combo empty and raises `IndexError: No experiment readers defined for the current experiment` from `Main.current_setup` (`chisurf/gui/main.py:156`) — while the shipped `Image correlation` and `tcPDA (3-colour)` experiments are absent. Re-run with `CHISURF_SETTINGS_DIR` pointing at an empty directory: 9 experiments, every one with readers (`Image correlation (RICS/STICS/TICS/iMSD)`, tcPDA's three readers, …), zero ERRORs — which isolates the cause to the missing merge. Also worth a guard: an experiment whose reader classes all fail to resolve should not be offered in the combo, and `current_setup` should not raise a bare `IndexError`.
- **Fix note:**

### RF-023
- **Status:** FIXED
- **Severity:** S3 (the only end-to-end GUI workflow tests are red)
- **Location:** `test/gui/test_gui_chisurf_main.py:145` (and `:104`, `:111`, `:157` via the shared `add_fit` helper)
- **Finding:** All three tests in the main-window GUI suite — `test_tcspc`, `test_fcs`, `test_global_fit`, i.e. the only tests that walk "choose experiment → load data → add fit" — fail with `AttributeError: 'Main' object has no attribute 'pushButton_2'. Did you mean: 'toolButton_2'?`. The **Add fit** button in `chisurf/gui/gui.ui` is `toolButton` (connected to `actionAdd_fit`); `toolButton_2` is the unrelated **+ Data** button. Verified: `pytest test/gui/test_gui_chisurf_main.py -x -q` → `1 failed` in 7 s. So the workflows in [usecases/tcspc-lifetime-fit](/usecases/tcspc-lifetime-fit.md) and [usecases/fcs-diffusion-fit](/usecases/fcs-diffusion-fit.md) currently have no regression cover at all; the fix is a one-word rename plus asserting something about the created fit (the tests only check that no exception escapes).
- **Fix note:** All three tests are green (`3 passed`, repeatedly and individually,
  in either order). The rename was only the first layer — the tests had silently
  rotted in four independent places, each of which is now an explicit assertion
  rather than a no-op, so the next drift fails loudly:
  1. **The button.** `pushButton_2` → `toolButton` (the *Analysis* button), and
     the helper parameter is renamed `add_fit_button` with the `toolButton_2`
     confusion written into its docstring.
  2. **Reader names.** `setup_name="TCSPCReader"` is a *class* name; the combo
     shows the `name` from `experiment_configs.yaml` (`TXT/CSV`). `findText`
     returned −1 and `setCurrentIndex(-1)` left the default reader selected, so
     the test passed a reader it never chose. `setup_reader` now asserts both
     indices are found.
  3. **Model names.** `'Lifetime fit'` is not offered — `LifetimeModel.name` is
     `'Lifetime '`, trailing space included (`chisurf/core/models/tcspc/lifetime.py:316`).
     `add_fit` now asserts the model is in the combo, and that the created fit's
     name starts with the model that was picked.
  4. **The dataset click.** `test_global_fit` clicked `'Global-fit'`, which is not
     in the tree (the row reads `Global Dataset`), and in a full-suite run the
     TCSPC row sits **below the viewport** — the tree is ~46 px tall, the third
     row's centre is at y=54, so `QTest.mouseClick` landed outside and selected
     nothing. `onAddFit` → `add_fits_for_datasets` returns silently on an empty
     `data_idx`, so no fit was created and nothing was logged. The helper now
     `scrollToItem`s first and asserts both that the row exists and that the
     click actually selected it.
  Each test additionally asserts the fit's data and that `parameters_all` is
  non-empty after one `model.update()` (parameter discovery is lazy —
  `Model.update` calls `find_parameters`, so a freshly added fit legitimately
  reports zero). Lint on the file went 21 → 9 errors (the remainder is the
  pre-existing `E402`/`I001` from the `sys.path` bootstrap); the stale
  "Test the kappa2 distribution GUI" class docstring is corrected.

### RF-024
- **Status:** OPEN
- **Severity:** S3 (internal class names presented as user-facing names)
- **Location:** `chisurf/core/fitting/fit.py:79` (`_raw_fit_name`, `data_name` from the group) and `chisurf/server/services/fits.py:117` (`model_name`)
- **Finding:** For every reader that returns a curve **group** (FCS, PDA, …) the fit is named after the container class instead of the data. Verified: the fit created on `Kristine_with_error.cor` is called `Parse-Model - ExperimentDataCurveGroup` in the fit list, in the *Info* tab (`sample: Parse-Model – ExperimentDataCurveGroup`), in the `Please wait fitting: …` log line and in the server DTO's `name`, while the sub-window title correctly reads `Parse-Model - Kristine_with_error` (the contained `DataCurve` *is* named `Kristine_with_error`; the group's `name` falls back to its class name via `Base.name`). The same screen shows the model as `ParseFCSWidget` — the *Model type* column of the fit list and the *Info* tab's `type:` both take the widget class name, although the model's user-facing name is `Parse-Model`, which is what the model combo box offered. Both names travel further than the screen: they are what a saved fit / exported table is labelled with.
- **Fix note:**

### RF-025
- **Status:** OPEN
- **Severity:** S3 (the equation display shows no equation)
- **Location:** `chisurf/gui/widgets/models/parse/parseWidget.ui:99` (the `textEdit` `QTextBrowser`'s `maximumSize.height = 120`), populated by `chisurf/gui/widgets/models/parse/widget.py:179` (`format_equation`, defined at `widget.py:491`)
- **Finding:** The model editor's description/equation panel opens with the typeset formula out of view: the `textEdit` is capped at **120 px** by its `maximumSize` while its document is **175 px**, so the visible area shows the description plus the bare heading "Equation:" and nothing else — the panel that exists to let a user verify which equation is being fitted appears empty. Verified for `3D Gauss` and `3D Gauss, 1 bunching`: `document().size().height() == 175`, scrollbar range 0…57, and scrolling to the bottom reveals the correctly rendered LaTeX formula (the embedded temp PNG is fine — 2021 bytes, `document().resource()` returns a valid pixmap). Give the box the document's height (or `sizeAdjustPolicy`-style growth) so the formula is visible without scrolling; it is also rendered black-on-white inside the dark theme.
- **Fix note:**

### Review 2026-07-25 (4) — the ROI subsystem and its region measurements

Slice: `chisurf/core/roi/` — `roi.py` (three landings in a row: `8769ddb84`
painted value gates, `d230c59c1` `to_indices`, `7e680e5df` the zero-radius fix),
`props.py`, `builders.py`, `io.py` — plus the one fit-indexing root cause the
slice ran into.

**The skimage parity claim mostly holds and is worth stating.** Checked rather
than taken on trust: 40 random speckle frames, every shared property against
`skimage.measure.regionprops` 0.26 — `area`, `perimeter`, `perimeter_crofton`,
`euler_number`, `solidity`, `area_convex`, `extent`, `equivalent_diameter_area`,
`feret_diameter_max` agree exactly, and `eccentricity` / `orientation` /
`axis_*_length` to 8e-16 relative. The `orientation` degenerate branch (`a - c ==
0` → `+pi/4` when `b < 0`) matches skimage 0.26 exactly, sign included.
`area_filled` is the one that does not (RF-027). `builders.py` and `io.py`
produced nothing worth filing.

**Queue hygiene, for whoever consumes this file:** `RF-018`..`RF-023` each appear
**twice** — once in the PSIS block (`ef1645ea2`) and once in the FCS block
(`be22f7c20`), which renumbered over them. The ids are not unique, so "fix
RF-020" is ambiguous; the FCS use-case note
[usecases/fcs-diffusion-fit](/usecases/fcs-diffusion-fit.md) refers to the second
set. Left as found rather than renumbered under a foreign commit; needs one
deliberate pass. Findings RF-026..RF-029 below.

### RF-026
- **Status:** OPEN
- **Severity:** S2 (contract: two regions answer the same question in different coordinate systems)
- **Location:** `chisurf/core/roi/roi.py:263-270` (`ROI.bounds`, the base implementation)
- **Finding:** `ROI.bounds` promises "the region's extent **in its own coordinates**" and takes an `extent` argument, but the base implementation ignores that argument: it returns `bounding_box`'s pixel indices shifted by half a pixel, so every region that has to be rasterised (`CompositeROI`, `ThresholdROI`, a pixel-index `MaskROI`) answers in pixel indices while the analytic shapes answer in value coordinates. Verified on the same geometry: `RectangleROI(2, 2, 4, 4).bounds((100, 100), extent=(0, 10, 0, 10))` → `(2.0, 2.0, 4.0, 4.0)`, but `(RectangleROI(2,2,4,4) | RectangleROI(6,6,8,8)).bounds((100, 100), extent=(0, 10, 0, 10))` → `(19.5, 19.5, 79.5, 79.5)` where the value-space answer is `(2, 2, 8, 8)` — a factor-10 mismatch that no caller can detect, since both return four plain floats. `MaskROI.bounds` already shows the fix (`roi.py:698-704` maps its bin box back through its own extent with one linear transform); the base needs the same map applied to the caller's `extent`. Nothing pins this: `test_analytic_regions_bound_themselves_without_a_grid` and `test_regions_that_need_a_grid_say_so` (`test/core/test_roi.py:380`, `:395`) both call `bounds` without an extent, and the two live callers (`img_coloc/gui/view_model.py:553`, `gui/autoform/sections/builtin.py:2090`) happen to pass none — so this is latent today and will bite the first value-axis composite gate.
- **Fix note:**

### RF-027
- **Status:** OPEN
- **Severity:** S3 (documented skimage parity broken for one property; the test that should catch it is vacuous)
- **Location:** `chisurf/core/roi/props.py:456-465` (`RegionProperties.image_filled` / `area_filled`)
- **Finding:** `image_filled` calls `ndi.binary_fill_holes(self.image)` with the **default** structuring element (4-connected background), while `skimage.measure.regionprops.image_filled` passes `np.ones((3, 3))` (8-connected background) — so ChiSurf fills every background pocket that reaches the outside only diagonally, and skimage does not. Verified through the public API on the smallest case, `[[0,1,1],[1,0,1],[1,1,1]]`: `regionprops(m)[0].area_filled == 8` against skimage's `7.0` (region area 7). On random speckle regions the gap is large: 324 vs 231 pixels on the same cropped mask. The module docstring states that "where an algorithm has a choice … the same choice is made, so the numbers agree to floating-point noise", and `test_matches_skimage_regionprops` (`test/core/test_regionprops.py:305`) *does* list `area_filled` — but its `blobs` fixture is a Gaussian-smoothed threshold whose 25 regions contain **no holes at all** (`all(p.area_filled == p.area)`), so the assertion compares `area` with `area`. Note the current behaviour is the self-consistent one (4-connected background is the complement of the 8-connected foreground `euler_number` assumes, where skimage is internally inconsistent), so this may be a documentation fix rather than a code fix — but the choice has to be made deliberately, and the parity test needs a region with a diagonal pocket either way.
- **Fix note:**

### RF-028
- **Status:** OPEN
- **Severity:** S3 (crash on a documented-compatible call)
- **Location:** `chisurf/core/roi/props.py:884` (`regionprops_table`, the final dict comprehension keyed off `rows[0]`)
- **Finding:** `regionprops_table` builds its columns from the keys of the **first** row, so any property whose flattened width varies between regions raises `KeyError` instead of returning a table. Verified: `regionprops_table(np.array([[1,1,0],[1,1,0],[0,0,2]]), properties=["label", "coords"])` → `KeyError: 'coords-1-0'` (region 1 has four pixels, region 2 has one), where `skimage.measure.regionprops_table` returns `coords` as an object-dtype column. `image`, `image_convex` and `image_filled` fail the same way. The function is documented as "the counterpart of `skimage.measure.regionprops_table`", and `coords` is the standard way to ask for a region's pixel list, so this is reachable from an ordinary call — the default `PROPERTIES` tuple simply happens to contain only fixed-width entries. Either emit an object column for variable-length properties (skimage's behaviour) or reject them with a message naming the property.
- **Fix note:**

### RF-029
- **Status:** FIXED
- **Severity:** S2 (a promised int is silently `None`, defeating every guard written against it)
- **Location:** `chisurf/core/fitting/__init__.py:128-142` (`find_fit_idx`) via `chisurf/core/fitting/fit.py:101` (`Fit.fit_idx`)
- **Finding:** `find_fit_idx` walks `chisurf.fits` looking for an identity match and has **no explicit return** for the not-found case, so it falls off the end and returns `None` despite `-> int` and a docstring promising "position of the fit in the global fit list". Verified: `find_fit_idx(<object not in cs.fits>)` → `None`. This is the root cause behind the FCS `RF-020`: only `FitGroup`s live in `cs.fits`, the member `Fit`s inside a group inherit the very same property (`FitGroup.fit_idx is Fit.fit_idx` → `True`), so any code holding a *member* fit gets `None`. The idiom every call site uses to defend against that — `getattr(fit, "fit_idx", None)` (`chisurf/core/models/fcs/mdf.py:177`, `gui/widgets/models/fcs/parse_fcs_widget.py:376`) and `getattr(self.fit, "fit_idx", 0)` (`gui/plots/residual_image.py:797`) — cannot work, because the attribute *exists*; the default is never reached and `None` is passed on as the target index, where `fit.range.set` (`core/actions/fit_actions.py:139`, which catches only `IndexError`/`AttributeError`) raises `TypeError` from `int(None)` and the server's `_resolve_fit` reports "fit not found". Fix it where it lives: make a member fit resolve to the index of the group that contains it (or return `-1` / raise, and correct the annotation), rather than patching each call site.
- **Fix note:** Fixed where it lives, both halves. (a) A member of a `FitGroup`
  now resolves to the index of the **group holding it**: only groups are listed
  in `chisurf.fits`, so the identity-only search left every member fit without
  an index — the root cause behind the FCS `RF-020`, where the member's
  `fit_index=None` reaches the server as "fit not found". Reproduced against
  `HEAD` first: for a two-member `FitGroup` at index 0, `find_fit_idx(group)`
  returned `0` while `find_fit_idx(member)` returned `None` for both members. A
  top-level identity match still wins over a membership match (two passes).
  (b) The not-found case now `return`s `None` **explicitly**, and both
  `find_fit_idx` and `Fit.fit_idx` are annotated `int | None` and document it,
  so the signature no longer promises an `int` it cannot deliver. `-1` was
  considered and rejected for the sentinel: `chisurf/core/actions/fit_actions.py`
  indexes `cs.fits[int(fit_index)]` directly, so `-1` would silently retarget
  the *last* fit — a wrong-fit mutation is worse than the honest `None`
  (the server's `_resolve_fit` already rejects both). Pinned by
  `test/fitting/test_fit_indexing.py` — member → group index, the same through
  the `Fit.fit_idx` property with two groups in `cs.fits` (so a wrong group
  would fail), and the not-in-the-list case. All 75 files of `test/fitting/`
  run **per file** give exactly the same exit codes as `HEAD` (13 pre-existing
  failures, unchanged) — per file because the whole-directory run aborts
  (`Fatal Python error: Aborted`) at `HEAD` too, a pre-existing cross-test
  interaction in this environment. Also green: `test/test_fitting_client.py` +
  `test/test_fix.py` + `test/test_crash.py` (71 passed, 1 failure that is red
  at `HEAD` as well) and the fit-addressing server suites
  `test_services_fits` / `test_services_parameters` / `..._uid` / `test_session`
  (75). `ruff check` on the two touched files reports three
  findings *fewer* than `HEAD` and none new, and the new test file is
  `ruff check` + `ruff format` clean.

### Use-case run 2026-07-25 — Imaging / CLSM-Draw (image → pixel selection → decay)

Driven headlessly through the real `CLSMPixelSelect` widget on
`test/data/clsm/Leica_SP5.ptu` (230 frames × 256 × 256, 6.7 M photons); see
[usecases/clsm-image-decay](/usecases/clsm-image-decay.md). The intensity /
selection / decay / ROI / export path is correct and fast; the findings below
are the mean-micro-time representation and four controls that do not do what
they say. Findings RF-030..RF-035.

### RF-030
- **Status:** FIXED
- **Severity:** S1 (wrong numbers, and a control that silently does the opposite of its label)
- **Location:** `chisurf/plugins/microscopy/clsm/core/imaging.py:111` and `:116` (`representation`)
- **Finding:** Both calls read `clsm_image.get_mean_micro_time(tttr, n_ph_min, False)`, but the installed tttrlib (0.27.0) signature is `get_mean_micro_time(tttr_data, microtime_resolution=-1.0, minimum_number_of_photons=2, stack_frames=False, correct_irf_offset=False)`. So `n_ph_min` lands in **`microtime_resolution`** and `False` (=0) in `minimum_number_of_photons`. Verified on `test/data/clsm/Leica_SP5.ptu`: the returned value is `mean_micro_time_channel × microtime_resolution`, so driving the GUI's *Min #Ph* spin box from 1 → 5 → 50 multiplies the whole image (max 57 648 → 288 240 → 2 882 406) while leaving it visually identical, and no pixel is ever discriminated (`(image < 0).sum() == 0`, `(image == 0).sum() == 5` at every setting), which is why the mean-micro-time background is pure noise. The correct 4-argument form is already used at every other call site in the tree — `chisurf/core/fluorescence/imaging/pixel_maps.py:327,334` and `chisurf/plugins/microscopy/img_pixel_micro_time/core.py:49`, `gui/view_model.py:73` all pass `(tttr, res_ns, n_ph, stack)`. Note that discriminated pixels come back as `-1 × resolution`, not zero (the tttrlib docstring says zeros), so whatever consumes the fixed call has to mask negatives before display. `test_core_image_representation_decay_frc` (`chisurf/plugins/microscopy/clsm/test/test_clsm.py:83`) only asserts `image.ndim == 3`, so nothing pins the values.
- **Fix note:** `representation` now routes the mean micro time through a new
  `imaging.mean_micro_time`, which calls the 4-argument form
  `get_mean_micro_time(tttr, micro_time_resolution_ns(tttr), n_ph_min, False)` —
  so the map is in nanoseconds and *Min #Ph* discriminates instead of scaling.
  Discriminated pixels (`-1 × resolution`) are mapped to `0.0` so the stack stays
  arithmetically reducible; the new helper `imaging.micro_time_resolution_ns`
  resolves the header resolution (s → ns) with tttrlib's `-1.0` sentinel as the
  fallback, mirroring `core/fluorescence/imaging/pixel_maps.py`. Pinned by
  `test_mean_micro_time_is_in_ns_and_discriminates`
  (`chisurf/plugins/microscopy/clsm/test/test_clsm.py`), which asserts the map
  lies inside the micro-time window, that raising *Min #Ph* drops pixel count,
  and that it does **not** rescale the maximum — all three fail on the old call.
  Verified on `test/data/clsm/Leica_SP5.ptu` (max 2000 / 10000 / 100000 at
  *Min #Ph* 1 / 5 / 50 before, valid-pixel count 1 875 925 / 99 663 / 4 and mean
  8.2 ns after) and by a headless grab of the **Image** tab, which now shows the
  cell rather than noise. The frame reduction on top of it is RF-031, still open.

### RF-031
- **Status:** OPEN
- **Severity:** S2 (a "mean" is displayed as a sum over frames, with no unit)
- **Location:** `chisurf/plugins/microscopy/clsm/core/imaging.py:143-146` (`reduce_frames`) as used by `gui/view_model.py:252` (`select_representation`) and `api/clsm.py:133,207,289`
- **Finding:** `representation("Mean micro time", …)` returns a `(frames, lines, pixel)` stack of **per-frame mean arrival times**, which `reduce_frames` then collapses with the default mode `sum` — so the *Image* panel displays the sum of 230 per-frame means (max 57 648, mean 9413) for a quantity whose physical value is ≈ 8 ns. `mean` is wrong too, because pixels with no photons in a frame contribute 0 and dilute the average (1.02 ns for the same data). Verified against tttrlib's photon-weighted stacking on the same file: `get_mean_micro_time(tttr, microtime_resolution=header.micro_time_resolution, minimum_number_of_photons=20, stack_frames=True)` → mean 8.076 ns over 20 282 valid pixels, against a true global mean micro time of 7.037 ns. Frame reduction by arithmetic is only meaningful for the `Intensity` representation; a mean-micro-time (or combined) representation needs the photon-weighted stack, or the intensity-weighted average of the per-frame means.
- **Fix note:**

### RF-032
- **Status:** OPEN
- **Severity:** S2 (three controls have no effect; the image and the decay silently describe different data)
- **Location:** `chisurf/plugins/microscopy/clsm/gui/view_model.py:260` (`refresh_current_image`, no callers) and `gui/clsm.view.json:69-74` (the `tac_coarsening`, `frame_mode`, `frame_idx` sections carry no `call`)
- **Finding:** `refresh_current_image` is documented as "re-reduce the active representation (after a frame-mode change)" and has **zero callers** in the tree (`grep -rn refresh_current_image chisurf/`), while the three view-spec fields that should trigger it declare no `call` action. Verified by driving the widget: with an intensity image displayed, setting **Frames** = `frame` and **Frame** = 150 through the real combo/spin leaves the displayed image byte-identical (`nanmean` 53.202 before and after), yet `recompute_decay` *does* read both — the decay drops from 2 619 451 to 11 900 photons — so the panel shows a 230-frame sum next to a single-frame decay with nothing indicating the mismatch. **Coarsen** has the same hole: selecting `8` leaves the plotted decay at 2000 channels (the model attribute updates to `'8'`), and only the next unrelated `recompute_decay` re-bins it to 250. Wire the three fields to `refresh_current_image` / `recompute_decay`.
- **Fix note:**

### RF-033
- **Status:** OPEN
- **Severity:** S3 (unbounded input; raw IndexError instead of a message)
- **Location:** `chisurf/plugins/microscopy/clsm/core/imaging.py:151` (`reduce_frames`, single-frame branch); the spin box is `gui/clsm.view.json:73-74` (`frame_idx`, `minimum: 0`, no maximum)
- **Finding:** The *Frame* spin box accepts 0 … 2 147 483 647 for an image that has 230 frames, and `reduce_frames` indexes `image[frame_idx]` with no bounds check. Reachable today through the documented CLI (the GUI spin is inert, see RF-032): `clsm representation test/data/clsm/Leica_SP5.ptu --setup 'Leica SP5' --channels 0,1 --frame-mode frame --frame-idx 5000` exits 1 with `IndexError: index 5000 is out of bounds for axis 0 with size 230` surfaced as a bare `RuntimeError`, naming neither the parameter nor the actual frame count. Clamp (or validate with a message) in `reduce_frames`, and set the spin's maximum from `ClsmViewModel.n_frames`, which already exists (`gui/view_model.py:241`) and is likewise unused.
- **Fix note:**

### RF-034
- **Status:** OPEN
- **Severity:** S2 (stale state on screen; a silent no-op afterwards)
- **Location:** `chisurf/plugins/microscopy/clsm/gui/view_model.py:207-212` (`remove_clsm`) and `:283-289` (`recompute_decay`)
- **Finding:** `remove_clsm` drops the CLSM image but leaves `self.representations`, `current_representation_name` and `current_image` untouched — `remove_representation` (`:228`) shows the intended pattern of clearing the display when its source disappears. Verified by clicking the **−** next to the CLSM combo with a representation displayed: `clsm_images == []` while the *Image* combo still lists `Leica_SP5_ch(0,1)_Intensity`, the image stays on screen, and `recompute_decay` then returns `None` on its first guard, so every subsequent brush stroke updates nothing with no message, no disabled control and no log line. Either drop (or grey out) the representations belonging to the removed CLSM image, or keep enough state to recompute.
- **Fix note:**

### RF-035
- **Status:** OPEN
- **Severity:** S3 (the user's own label is discarded)
- **Location:** `chisurf/plugins/microscopy/clsm/gui/view_model.py:305-307` (`add_decay_curve`)
- **Finding:** `add_decay_curve` builds its name as `f"{self.current_clsm_name}_ROI({roi})"` where `roi = self.current_representation_name or "selection"` — the text inside `ROI(…)` is the *representation* name, never a region name, even when the current selection was saved as a named ROI. Verified end-to-end: with an ROI called `bright` saved and re-applied, **Add decay → ChiSurf** exported `Leica_SP5_ch(0,1)_ROI(Leica_SP5_ch(0,1)_Intensity)` into `chisurf.imported_datasets`, and the same string is the decay-plot legend entry — so two decays taken from two different ROIs of the same representation get identical names. Use the name of the region the selection came from (the view model already tracks `rois`), falling back to `selection`.
- **Fix note:**

### Review run 2026-07-25 — Ratiometric FRET (`core/fluorescence/imaging/ratio_fret.py`)

The MIA `Do_FRET` port that landed in `82d95a7e0` (289 lines, 17 tests), reviewed
against its own docstrings. The physics framing is right and the "A/D is not E"
warning is the correct one to lead with; the defects are all in the plumbing
around it — the NaN handling that makes the map's default filter report a
neighbouring cell's ratio, two window arguments whose documented `(start, stop)`
form is silently reinterpreted, and a summary number that depends on an accident
of scaling. The module is exported from `chisurf.core.fluorescence.imaging` but
has no GUI/CLI caller yet, so these are cheap to fix now. Findings RF-036..RF-041.

### RF-036
- **Status:** OPEN
- **Severity:** S1 (wrong numbers on the default path: a pixel reports another region's ratio)
- **Location:** `chisurf/core/fluorescence/imaging/ratio_fret.py:284-288` (`ratio_image`, the `ratio_median` block)
- **Finding:** The comment claims "Median-filter only the defined pixels; NaNs would otherwise spread", but the code replaces every undefined pixel with the **global** `np.nanmedian(ratio)` and then runs an ordinary `median_filter` — so the injected constant votes in the median of its *defined* neighbours, and every pixel within `ratio_median // 2` of a hole (ROI border, `minimum_donor` exclusion, background) is pulled toward the image-wide median. Verified: a 40×40 field with a large cell at ratio 3.0 and a small 6×6 cell at ratio 1.0, background excluded by `minimum_donor`, defaults `ratio_median=5`: 12 of the small cell's 36 pixels come back as exactly **3.0** — the ratio of a cell 14 px away — and its mean rises from 1.0 to 1.667. `test_the_median_filter_erases_features_smaller_than_its_kernel` (`test/core/test_ratio_fret.py:133`) uses a fully-defined map, so nothing in the suite exercises the fill at all. Use a mask-aware median (e.g. `scipy.ndimage.generic_filter` with `np.nanmedian`, or filter a masked array) so undefined neighbours are excluded from the window rather than replaced by a constant.
- **Fix note:**

### RF-037
- **Status:** OPEN
- **Severity:** S2 (a documented `(start, stop)` window silently becomes a different frame set)
- **Location:** `chisurf/core/fluorescence/imaging/ratio_fret.py:167-171` (`ratio_trace`, `baseline`) and `:247-252` (`ratio_image`, `frames`)
- **Finding:** Both arguments are documented as "`(start, stop)` or an explicit index list" and both disambiguate with `len(x) == 2 and int(x[1]) > int(x[0]) + 1` — so a half-open window **one frame wide** fails the test and is reinterpreted as a two-element index list covering one frame too many. Verified on a stack whose ratio jumps from 1.0 to 4.0 at frame 1: `ratio_trace(d, a, baseline=(0, 1))` normalises by `2.5` (the mean of frames 0 *and* 1) instead of `1.0`, so the trace reads `[0.4, 1.6, …]` rather than `[1.0, 4.0, …]`; `ratio_image(d, a, frames=(0, 1))` likewise returns 2.5 where `frames=[0]` returns 1.0. A reversed window (`(5, 2)`) falls into the same branch and silently averages frames 5 and 2. Take the form from the argument's type (tuple ⇒ range, list/array ⇒ indices) or add an explicit keyword; a length-2 heuristic cannot be made correct. Note `test_an_empty_baseline_is_rejected` (`test/core/test_ratio_fret.py:103`) depends on the current heuristic, so it needs updating with the fix.
- **Fix note:**

### RF-038
- **Status:** OPEN
- **Severity:** S2 (the headline number changes meaning depending on an accident of scaling)
- **Location:** `chisurf/core/fluorescence/imaging/ratio_fret.py:54-66` (`RatioTrace.response`)
- **Finding:** `response` is documented as "the largest fractional excursion from the baseline" but selects its formula with `if self.normalisation != 1.0`, i.e. it infers *whether a baseline was given* from the baseline's numeric value. When a normalised trace happens to have a resting ratio of exactly 1.0 — the ordinary case of equal donor and acceptor signal at rest, and the case every synthetic dataset hits — it silently takes the unnormalised branch `max/min − 1`, which is peak-to-trough contrast, not excursion from rest. Verified: two traces with the identical normalised shape `[1, 1, 1, 0.5, 0.5]` report `response = 1.0` (resting ratio 1.0) and `0.5` (resting ratio 2.0). The unnormalised branch is also unguarded against a non-positive minimum: `np.min(finite) == 0` yields `inf`, and a negative ratio yields a meaningless negative "response". Record whether a baseline was applied (a `bool` field, or `Optional[float]` normalisation) instead of testing the value, and guard the fallback.
- **Fix note:**

### RF-039
- **Status:** OPEN
- **Severity:** S2 (an intensity-gated region is evaluated on data the map does not show)
- **Location:** `chisurf/core/fluorescence/imaging/ratio_fret.py:271-274` (`ratio_image`, the `donor_roi`/`acceptor_roi` loop)
- **Finding:** The loop passes the **whole** stack (`d` / `a`) as `image=` to `ROI.to_mask`, while the map itself is built from `d[idx].mean(0)` — the selected frame window, median filtered and clipped. `ThresholdROI.to_mask` averages a `(n_frames, ny, nx)` stack over *all* frames (`chisurf/core/roi/roi.py:773`), so an intensity gate is evaluated against a different image than the one being divided. Verified: a stack that is dark (donor 10) for frames 0–4 and bright (donor 1000) for frames 5–9, `donor_roi=ThresholdROI(low=500)`, `frames=(0, 5)` → all 64 pixels pass the gate, because the all-frame mean is 505; the correct answer for that window is zero pixels. Pass the frame-selected images (`d_img` / `a_img`) instead, and say in the docstring which image the gate sees.
- **Fix note:**

### RF-040
- **Status:** OPEN
- **Severity:** S3 (validation present in one entry point, absent in its twin)
- **Location:** `chisurf/core/fluorescence/imaging/ratio_fret.py:270-277` (`ratio_image`) vs `:98-102` (`_region_mean`)
- **Finding:** `_region_mean` checks that an array region matches the frame shape and that it selects at least one pixel; `ratio_image` does neither, so (a) a wrongly-shaped boolean mask is **broadcast** rather than rejected — verified: a 1-D mask of length `nx` passed as `donor_roi` against a `(6, 8)` frame silently selects 24 pixels by applying the per-column mask to every row, where `ratio_trace` raises "the region must match the frame shape"; and (b) a selection that keeps nothing returns an all-NaN map plus a bare `RuntimeWarning: All-NaN slice encountered` from the `np.nanmedian` fill at `:286` — verified with `minimum_donor=10.0` on a donor of 1.0. Reuse `_region_mean`'s shape check and raise the same "selects no pixel" error (or return early before the fill).
- **Fix note:**

### RF-041
- **Status:** OPEN
- **Severity:** S3 (a method documented as JSON-friendly emits invalid JSON)
- **Location:** `chisurf/core/fluorescence/imaging/ratio_fret.py:68-75` (`RatioTrace.to_dict`)
- **Finding:** `to_dict` is documented as returning "a JSON-friendly dictionary" but `ratio` is `a_mean / d_mean` computed under `errstate(divide="ignore", invalid="ignore")` (`:162`), so a frame whose donor region mean is 0 puts `inf` (or `nan` for 0/0) in the list. Verified: `json.dumps(ratio_trace(d, a).to_dict())` on a stack with one all-zero donor frame emits `"ratio": [1.0, 1.0, Infinity, 1.0]`, which `json.loads(..., parse_constant=raise)` and every strict/JS parser rejects. `response` is not affected — it filters non-finite values — but that filtering means the same frame is also silently dropped from the summary. Map non-finite entries to `None` in `to_dict` (and mention that dark frames yield `None`).
- **Fix note:**

### Review 2026-07-25 — FCS file readers and the noise/weight model

Slice: `chisurf/core/fio/fluorescence/fcs/` (the ALV, ConfoCor and Kristine
readers/writers) plus the `noise()` weight model in
`chisurf/core/fluorescence/fcs/__init__.py` that all of them call. Picked because
two of these files carry in-flight count-rate fixes and the subsystem had no
findings on record. Every claim below was reproduced in the `arm64` env against
files already committed under `test/data/fcs/` (or, for RF-042/RF-043, the ALV
multi-run examples under `junk/quickfit3/plugins/fccsfit/examples/`).

The slice is in worse shape than the in-flight count-rate work suggests: **three
of the reader's file formats cannot be loaded at all** (multi-run ALV-5000/6000,
dual-channel ALV-7004 AC+CC, single-curve ConfoCor), the Kristine **writer cannot
produce a file its own reader can read**, and the shared noise model computes its
baseline from a slice that is empty of meaning under its own default arguments —
so *every* FCS weight in the program is derived from a wrong amplitude. Findings
RF-042..RF-051. Note the line numbers for `asc_alv.py` / `confocor3.py` refer to
the working tree at review time (both have uncommitted count-rate edits by
another instance); the symbol names are given so they stay findable.

### RF-042
- **Status:** FIXED
- **Severity:** S1 (every curve in a multi-run ALV file is the same interleaved garbage)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:187` (`openASC_old`, `data = [[]]*len(curvelist)`)
- **Finding:** `[[]]*n` builds `n` references to **one** list, so `data[i].append(...)` in the row loop at `:190-192` appends every column of every row to a single shared list; all `np.array(data[t])` at `:245-332` are then the identical, row-major-interleaved array. Verified on the real ALV-5000 multi-run file `junk/quickfit3/plugins/fccsfit/examples/NUNC3_dil_050p_025_ccf.ASC` (183 lag times × 7 curves): `read_asc` returns 7 datasets that are **byte-identical**, each with 1281 points instead of 183, whose `correlation_times` begin `[0.0002, 0.0002, 0.0002, …]` — the same lag repeated once per curve. Duplicated lag times then make `np.diff(times)` zero inside `noise()`, which is where the `divide by zero encountered in divide` warnings from `chisurf/core/fluorescence/fcs/__init__.py:147` come from. Fix: `data = [[] for _ in curvelist]`. (RF-043 currently masks this by crashing first.) No test covers a multi-run ALV file.
- **Fix note:** `openASC_old` now builds one *independent* list per curve
  (`data = [[] for _ in curvelist]`, with a comment naming the aliasing trap).
  Re-checked on the real ALV-5000 file: seven curves of 183 points each with
  strictly increasing lag times instead of seven identical 1281-point arrays.
  Pinned by the new `test/fio/test_asc_alv_multi_run.py`, which writes a
  synthetic ALV-5000 "Correlation (Multi, Averaged)" export (one average + three
  runs, distinct column values) and asserts per-curve shape, per-curve values,
  strictly increasing `correlation_times`, and that the runs differ from one
  another — all three tests fail on the pre-fix reader.

### RF-043
- **Status:** FIXED
- **Severity:** S1 (removed NumPy alias; blocks the whole multi-run ALV path)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:571` (`mysplit`, `lensplit = np.int(np.ceil(N/n))`)
- **Finding:** `np.int` was removed in NumPy 1.24; the project env runs NumPy 2.4.6, where the attribute raises. `mysplit` returns early only for `n <= 1`, so every ALV-5000/6000 file with more than one run reaches it and dies with `AttributeError: module 'numpy' has no attribute 'int'` before any data is produced. Reproduced end-to-end: `read_asc('junk/quickfit3/plugins/fccsfit/examples/NUNC3_dil_050p_025_ccf.ASC')` → `AttributeError` from `openASC_old:239 → mysplit:571`; patching `np.int = int` lets the same call return 7 datasets. Per the CLAUDE.md dependency rule this is a pure rename and belongs in `chisurf/core/compat.py`, not a local rewrite — but the call site here can simply use the builtin `int`. Grep the tree for other `np.int`/`np.float`/`np.bool` survivors while fixing.
- **Fix note:** `mysplit` now computes the piece length with the builtin
  (`int(np.ceil(N/n))`). No `compat.py` alias was added: `np.int` was never an
  API of its own, only a spelling of the builtin, so the builtin is the one form
  that runs unchanged on NumPy 1 and 2 — `compat.py` is for names that moved
  (`np.trapz` → `np.trapezoid`), not for names that were always redundant.
  Reproduced against `HEAD` on the project's NumPy 2.4.6: `mysplit(trace, 3)`
  raised `AttributeError: module 'numpy' has no attribute 'int'`; it now returns
  the three pieces. The tree-wide grep found **no other survivor** — because the
  existing guardrail `test/agent/test_reader_failures.py::test_no_numpy_aliases_removed_in_numpy_2_remain`
  had `int` missing from its pattern, which is exactly how this one line
  survived the earlier `np.float`/`np.float_` sweep; `int` is now in that pattern
  (with a comment on why `bool` and `long`, both reinstated in NumPy 2, are not),
  and it flags the old line. Pinned by the new
  `test/fio/test_asc_alv_mysplit.py` (4 tests: the multi-run split itself — the
  case that raised — the piece shapes, the average-preserving contract from the
  docstring, the `n <= 1` early-out, and an uneven split). `test/fio` FCS suites
  + `test/agent/test_reader_failures.py` green (20 passed / 6 skipped, then 8
  passed); `ruff check` on `asc_alv.py` reports the same 113 pre-existing
  findings as `HEAD` and none new, and both test files are `ruff check` +
  `ruff format` clean. Two defects on the same path are deliberately **left
  open**: [RF-042](#rf-042) (`data = [[]]*len(curvelist)`), which this fix
  unmasks, and a Python-2 remnant next to it — `openASC_old:272,287,307,308`
  pass `len(curvelist)/2-nav`, a *float*, as `mysplit`'s `n`, which
  `np.linspace`/`np.split` reject; both belong to RF-042's multi-run path and
  neither is verifiable without fixing it.

### RF-044
- **Status:** FIXED
- **Severity:** S1 (a committed test file cannot be opened at all)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:553` (`openASC_ALV_7004`, `dictionary["Trace"] = np.array(tracelist)`)
- **Finding:** In the four-curve ALV-7004 mode `a-ch0+1  c-ch0/1+1/0`, `tracelist` mixes single traces (`trace1`, shape `(n, 2)`) with *pairs* for the cross-correlations (`[trace1, trace2]`, shape `(2, n, 2)`) — see `:482-497`. `np.array` on that ragged list raises since NumPy 1.24. Verified on the committed sample `test/data/fcs/asc/ALV-7004USB_ac01_cc01_10.ASC` (header `Mode : "A-CH0+1  C-CH0/1+1/0"`, `MeanCR0 152.07`, `MeanCR1 85.07`): `openASC(...)` → `ValueError: setting an array element with a sequence. The requested array has an inhomogeneous shape after 1 dimensions. The detected shape was (4,) + inhomogeneous part.` So every dual-channel FCCS measurement from this instrument is unreadable. `dictionary["Correlation"]` at `:552` is fine (all curves share a shape); the trace list must stay a plain Python list — `openASC_old` already returns it as one (`:342`), and `read_asc:650` explicitly branches on `isinstance(d['Trace'][i], list)`, so the consumer expects it.
- **Fix note:** `dictionary["Trace"]` is now the plain `tracelist`, with a
  comment saying why it must stay ragged. Reproduced against `HEAD` first —
  `openASC('test/data/fcs/asc/ALV-7004USB_ac01_cc01_10.ASC')` raised the quoted
  `ValueError`. Fixing only that line was **not enough**, and the second half is
  the reason this could not be a one-word change: with a list, the
  autocorrelation branch of `read_asc` (`:669-670`) hands out a *view* into the
  reader's own `trace1`/`trace2`, and those same arrays are handed out again for
  the `CC12`/`CC21` curves of the same file, so the in-place
  `intensity_time /= 1000.0` at `:673` scaled them a **second** time — with only
  the ragged fix applied the two cross-correlation traces ended at `0.0296 s`
  instead of `29.65 s` for a 30 s measurement, silently. The conversion is no
  longer in place. The four ALV files that already read return **bit-identical**
  datasets (correlation weights, trace times, count rate, acquisition time), so
  nothing that worked changed. Pinned by `test/fio/test_asc_alv_dual_channel.py`
  (4 tests: the four-curve mode opens and reports its `Duration`; the trace list
  is a list whose AC entries are `(n, 2)` arrays and whose CC entries are pairs;
  `read_asc` returns four datasets whose traces span the measurement — the
  assertion the 1e-6 scaling fails — with finite weights; and reading the file
  twice gives the same traces, which the in-place division broke). `test/fio`
  green (287 passed, 12 skipped); `ruff check` on `asc_alv.py` reports the same
  113 pre-existing findings as `HEAD` and none new, and the new test file is
  `ruff check` + `ruff format` clean. The count-rate misindexing on the same
  path ([RF-048](#rf-048)) is untouched and stays open — it is now reachable for
  the first time on this file.

### RF-045
- **Status:** FIXED
- **Severity:** S1 (the noise model's baseline is the mean of nearly the whole curve)
- **Location:** `chisurf/core/fluorescence/fcs/__init__.py:131` (`noise`, `correlation_offset = np.mean(correlation[-lb:-ub])`)
- **Finding:** With the default `correlation_amplitude_range = (0, 16)` this is `correlation[-0:-16]`, i.e. `correlation[0:-16]` — everything *except* the last 16 points, not the last 16 points. The offset is meant to be the long-lag baseline (the next line subtracts it from `mean(correlation[0:16])`, the short-lag amplitude), but it instead averages the amplitude region into the baseline. Verified on `test/data/fcs/asc/ALV-7004.ASC` (231 points): as coded the slice takes 215 points and gives `offset = 1.215952`; the intended tail `correlation[-16:]` gives `1.000315`. The derived amplitude is therefore `A = 0.152` instead of `0.368` — a factor 2.4. `A` enters `suren` quadratically (`S ∝ A²/ns`) and `starchev` as `N = 1/A` cubed, and it also shifts the half-amplitude crossing used to estimate `diffusion_time` at `:138`, so this biases **every** weight ChiSurf computes for FCS. No caller ever overrides `correlation_amplitude_range` (only three references tree-wide, all in this file), so the default is the only path. Fix the slice (`correlation[-ub:]` or an explicit `(baseline_lb, baseline_ub)` pair) and pin the offset with a test on a synthetic `G = 1 + A/(1+t/τ)`, where the answer is known exactly.
- **Fix note:** The baseline slice is now indexed from the front —
  `correlation[n - ub:n - lb]` — so it is the true mirror of the short-lag
  window `correlation[lb:ub]` at the end of the curve, and `lb = 0` selects up
  to the last point instead of dropping the whole tail. Confirmed against
  `HEAD` on a synthetic `G = 1 + 0.5/(1 + t/1 ms)` (200 log-spaced lags): the
  old slice averaged 184 of the 200 points and returned `offset = 1.310`, so
  the derived amplitude was `0.190` instead of `0.499` — a factor 2.6, in the
  same direction and of the same size as the 2.4 seen on the real ALV file. A
  non-zero `lb` was worse than biased: `(2, 16)` made the old expression
  `correlation[-2:-16]`, an **empty** slice, so the offset was `NaN` and every
  weight on the curve came out `NaN`. Pinned by
  `test/fluorescence/test_fcs_noise_weights.py`, which recovers the internal
  amplitude through the Starchev branch (with `a2 = c1 = p = 0` and `a1 = 1`
  the variance is exactly `A³/i`) and asserts the default window, the mirrored
  non-zero-`lb` window, that head and tail windows stay disjoint for three
  ranges, and that the estimated `diffusion_time` now tracks the exact one;
  plus a finiteness guard on the `suren` branch. Four of the five fail on the
  old slice. `test/fluorescence` + `test/fio` green (284 passed, 12 skipped,
  counting only the new file from `test/fluorescence`); the two long-standing
  `test/fluorescence` failures (`test_pqres`, `test_labeled_structure`) fail
  identically with and without this change. `ruff check` on
  `fcs/__init__.py` reports the same 17 pre-existing findings as `HEAD` and
  none new; the new test file is `ruff check` clean.

### RF-046
- **Status:** FIXED
- **Severity:** S1 (the Kristine writer emits a transposed file, or crashes)
- **Location:** `chisurf/core/fio/fluorescence/fcs/kristine.py:46-64` (`write_kristine`) — the `.T` at `:53`, the `np.vstack` at `:63`, the second `.T` at `:64`
- **Finding:** The branch that includes uncertainties transposes to `(n, 4)` at `:53` and is then transposed **again** at `:64`, so `np.savetxt` writes 4 rows of `n` columns; the no-uncertainty branch does not transpose at `:61` and comes out correct. Verified with a 20-point curve: without `mask`, the file is `(4, 20)` and `read_kristine` reads it back as **4** correlation points with `acquisition_time = 0.0043 s` (was 10.0) and `mean_count_rate = 1.50` (was 50.0) — silent, total corruption of a saved dataset. With a `mask` array it is worse: `np.vstack([(n,4), (n,)])` raises `ValueError: all the input array dimensions except for the concatenation axis must match exactly, but along dimension 1, the array at index 0 has size 4 and the array at index 1 has size 20`. Both paths are live: `write_single_fcs` (`fcs/__init__.py:337`) always passes `data_set.ey` as an ndarray and passes `mask` whenever the curve has one, and the `fcs_convert` CLI plugin (`chisurf/plugins/fcs/fcs_convert/cli.py:100`) routes user conversions through it. The reader is fine — both committed `test/data/fcs/kristine/*.cor` files round-trip correctly — so the fix is to build the column stack once, in `(n, ncol)` order, and drop the second transpose. A writer→reader round-trip test (4-column and 5-column-with-mask) is the guardrail; there is none today.
- **Fix note:** `write_kristine` now builds the column list once — time,
  amplitude, the metadata column, then the optional uncertainty and mask — and
  writes `np.column_stack(columns)`, so there is no transpose left to double.
  Reproduced against `HEAD` first: a 20-point curve with uncertainties came out
  as `(4, 20)` and read back as **4** points with `acquisition_time =
  5.46e-06 s` (was 10.0) and `mean_count_rate = 1.497` (was 50.0). The mask half
  was two bugs, not one: besides the `np.vstack` shape error, the
  *no-uncertainty* branch happened to place the mask in column 4 — the column
  the reader takes the **uncertainties** from. There is no slot for a mask
  without them, so that combination now raises a `ValueError` saying so (it
  raised an unrelated shape error before; the only live caller,
  `write_single_fcs`, always passes `ey`, which `DataCurve` guarantees to be an
  array). Pinned by `test/fio/test_kristine_roundtrip.py`: the 4-column and
  5-column-with-mask round trips (shape, point count, both metadata values,
  weights `1/ey`, the mask), the 3-column case as a regression guard, the
  refusal, and an end-to-end `write_fcs` → `read_fcs` of the committed
  `Kristine_with_error.cor` — the `fcs_convert` path, which carries a mask and
  therefore raised before anything was written. Three of the five fail on the
  old writer. `test/fio` green (279 passed, 12 skipped); `ruff check` on
  `kristine.py` reports one finding *fewer* than `HEAD` (the old `:param:`
  docstring is now NumPy-style) and none new, and the new test file is
  `ruff check` + `ruff format` clean.

### RF-047
- **Status:** FIXED
- **Severity:** S1 (Python-2 method; every single-curve ConfoCor file fails to load)
- **Location:** `chisurf/core/fio/fluorescence/fcs/confocor3.py:360` and `:379` (`openFCS_Single`, `Alldata.__getslice__(i, i+length)`)
- **Finding:** `list.__getslice__` was removed in Python 3 (`hasattr([], '__getslice__')` is `False` on the project interpreter), so both the trace and the correlation import raise `AttributeError` the moment they are reached. `openFCS` dispatches here for every `.fcs` file whose first line is not `Carl Zeiss ConfoCor3` — i.e. ConfoCor2 and older AIM single-curve exports. All 15 committed ConfoCor test files carry the multi-curve header, so the whole function is untested and has been dead since the Python 3 port. Replace with ordinary slicing (`Alldata[i:i+length]`, as `openFCS_Multiple` already uses at `:143` and `:173`). While there: `newtrace` (`:371`) and `corr` (`:387`) are assigned only inside `if length != 0`, so a zero-length section makes `:392`/`:396` raise `NameError`/`UnboundLocalError` instead of reporting a malformed file.
- **Fix note:** Both `__getslice__` calls replaced with ordinary slicing, matching
  `openFCS_Multiple`. `newtrace`/`corr` are pre-set to `None` and a section that
  stayed empty now raises `SyntaxError` naming the missing section and the file
  — the same exception type the function already uses for an unknown `##DATA
  TYPE`, so the two malformed-file conditions behave alike for callers. The
  docstring became NumPy-style while the function was open. Pinned by
  `test/fio/test_confocor_single_curve.py`: a synthetic ConfoCor2/AIM
  single-curve file (no committed sample has the single-curve header) is parsed,
  checked value-for-value through `openFCS`, carried end-to-end through
  `read_zeiss_fcs` (mean count rate 13 kHz, acquisition time 1.5 s, finite
  weights), and both empty-section variants are asserted to report the malformed
  file. Confirmed discriminating — all four fail on `HEAD` with the
  `AttributeError`. `test/fio` green (291 passed, 12 skipped); `ruff check` on
  `confocor3.py` reports three findings *fewer* than `HEAD` and none new, and the
  new test file is `ruff check` + `ruff format` clean.

### RF-048
- **Status:** OPEN
- **Severity:** S2 (per-channel count rates indexed by curve number)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:674` (`read_asc`, `mean_count_rate = d["Count rates"][i]`)
- **Finding:** `openASC_ALV_7004` collects one `MeanCR<k>` entry per **detector** in file order (`:422-425`), but `read_asc` indexes that list with `i`, the index of the curve in the *filtered* `corrlist` — and `openASC_ALV_7004` drops all-zero correlations (`:479-498`) and emits only the curves the mode selects, so the two indices coincide only for channel 0. Verified on the committed `test/data/fcs/asc/ALV-7004USB_ac3.ASC` (mode `a-ch3`, `Count rates = [0.0, 0.0, 0.0, 27.70182]`): the single curve is channel 3 but the code reads `count_rates[0] = 0.0`. It escapes visible damage only by accident — the zero trips the `mean_count_rate == 0.0` fallback at `:687`, which recovers 27.6899 from the trace mean but *also* overwrites the file's recorded `Duration` of 300.0 s with `intensity_time[-1] = 297.66 s`. A file whose misindexed slot holds a different non-zero rate would silently weight the curve with another detector's count rate and no fallback at all. Carry the channel index alongside each curve in `openASC_ALV_7004` (it already knows it — `corr1..corr4` map to `MeanCR0..3`) and look the rate up by channel; and do not clobber a known `Duration`.
- **Fix note:**

### RF-049
- **Status:** OPEN
- **Severity:** S2 (a `None` trace is arithmetically multiplied)
- **Location:** `chisurf/core/fio/fluorescence/fcs/confocor3.py:249` (`openFCS_Multiple`, `tracelist.append(1*traces[actids[0]])`)
- **Finding:** `traces` is deliberately padded with `None` for curves that carry correlation data but no `CountRateArray` (`:172` and `:194`), and the single-AC branch guards only the *correlation* (`if ac_correlations[actids[0]] is not None`) before evaluating `1*traces[actids[0]]` — which raises `TypeError: unsupported operand type(s) for *: 'int' and 'NoneType'` for exactly the case the padding exists to represent. The two-AC branch at `:275`/`:280` has the mirror problem without the crash: it appends the `None` straight into `tracelist`, and `read_zeiss_fcs:440` then calls `len(trace)` on it (`TypeError: object of type 'NoneType' has no len()`). The `1*` is also just a stale copy idiom — use `np.array(..., copy=True)` or nothing. Decide the contract (skip such curves, or carry a `None` trace through to an `FCSDataset` with no `intensity_trace`) and apply it in both branches.
- **Fix note:**

### RF-050
- **Status:** FIXED
- **Severity:** S3 (an exception generic handlers cannot catch)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:17` (`class LoadALVError(BaseException)`)
- **Finding:** The reader's own error type derives from `BaseException`, not `Exception`, so it passes straight through every `except Exception` in the import path and through `pytest.raises(Exception)` — the same class of escape as a `KeyboardInterrupt`. It is raised four times in `openASC_ALV_7004` (`:471, :478, :506, …`) for ordinary malformed-file conditions, right next to a `NotImplementedError` at `:549` that *is* an `Exception`, so two failures of the same kind in the same function behave differently for callers. Change the base to `Exception` (or to a shared `chisurf` IO error).
- **Fix note:** Base changed to `Exception`, with a docstring saying why (a
  malformed file is an ordinary IO failure, not an interpreter-level
  condition). A shared chisurf IO base was *not* introduced — there is none
  today, and inventing one here would be a wider change than the finding.
  Pinned by `test/fio/test_asc_alv_error_contract.py`: `issubclass(...,
  Exception)`, plus an end-to-end case that strips the `Mode` header off the
  committed `ALV-7004USB_ac3.ASC` and asserts a generic `except Exception`
  actually sees the failure. Confirmed discriminating — 2 of the 3 tests fail
  on the old base class, all 3 pass with it.

### RF-051
- **Status:** FIXED
- **Severity:** S3 (documented writer that writes nothing)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:724-755` (`write_asc`)
- **Finding:** `write_asc` carries a full NumPy-style docstring describing eight parameters and an output file, and its body is `pass`. It has no callers tree-wide (`write_fcs` only knows `kristine` and `yaml`), so nothing breaks today — but a stub that silently succeeds is the worst failure mode to leave in an IO module, and the docstring makes it look implemented. Either implement it against the `openASC_ALV_7004` format that `read_asc` parses (with a round-trip test) or delete it and drop ALV from the writer surface.
- **Fix note:** Deleted. ALV is a vendor acquisition format ChiSurf reads and
  never produces — `write_fcs` offers only `kristine` and `yaml`, and no caller
  tree-wide asked for `write_asc` — so implementing a writer would add a
  round-trip surface nobody needs, where removing the stub costs nothing.
  `test/fio/test_asc_alv_error_contract.py::test_alv_writer_stub_is_gone` keeps
  it from coming back.

### GUI-tester 2026-07-25 — burst selection / FRET (Burst Analysis workflow)

Slice: the integrated **Burst Analysis** workflow driven headlessly end-to-end on
`chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000-m002.spc`
(3 files, 533 699 photons → 71 802 selected → 620 bursts). Use case:
[burst selection → FRET histogram](/usecases/burst-selection-fret.md).
Findings RF-052..RF-056.

### RF-052
- **Status:** OPEN
- **Severity:** S2 (a documented column is 1000× off and contradicts its neighbours)
- **Location:** `chisurf/core/fio/fluorescence/burst.py:435` (`generate_burst_dataframe`, `crate = (npix / dur)/1e3`), header at `:353`
- **Finding:** `dur` is already in milliseconds (`:432`, `(macro[stop]-macro[start]) * res * 1e3`), so `npix/dur` is photons per ms — i.e. **kHz** — and dividing by `1e3` again writes **MHz** into a column headed `Count Rate (KHz)`. The per-detector rates in the same row are computed correctly (`rate = idxs.size / d_ms`, `:469`), so one burst row carries two `… (KHz)` columns whose scales differ by 1000 and the burst's *total* rate reads smaller than its own green sub-rate. Verified on `m000.spc`, first burst: 21 photons between macro times of photons 1786 and 1807 = 0.8980875 ms → 23.383 kHz; the GUI *Bursts* table and the written `.bur` both show `0.023383`, next to `Green Count Rate (KHz) = 20.817`. The older writer in the same file gets it right because its `duration` is in seconds (`:218`, `:227`). Note before fixing: the bundled legacy reference (`burstwise_All 0.1000#15/bi4_bur/m000.bur`) carries the same 1000× scaling (29 photons / 0.3969 ms → `0.0730`), so this convention predates the port — decide explicitly whether to correct the value (and version the `.bur`) or relabel the column, and pin it with a test that asserts the total rate ≥ every per-detector rate.
- **Fix note:**

### RF-053
- **Status:** FIXED
- **Severity:** S1 (both export menu items raise on every non-empty dataset)
- **Location:** `chisurf/plugins/burst/burst_selection/gui/tool.py:3055` (`export_bur`) and `:3071` (`export_flr_cif`)
- **Finding:** Both guards are `if not self._last_frame:` and `_last_frame` is a `pandas.DataFrame`, so the guard raises `ValueError: The truth value of a DataFrame is ambiguous. Use a.empty, a.bool(), a.item(), a.any() or a.all()` exactly when there *is* something to export — before the file dialog opens, so the whole *File → Export → Export as .bur / Export as flrCIF* surface is dead. Verified by driving the widget: with 620 bursts loaded both calls raise; after `clear()` both correctly write "No burst data to export." to the summary (`not None` is `True`), which is why the bug is invisible to a smoke test that never loads data. Use `if self._last_frame is None or self._last_frame.empty:` (the same idiom the rest of the class already uses at `:2040`, `:2438`, `:2543`) and add a test that exports a non-empty frame to `tmp_path` with the file dialog patched.
- **Fix note:** Both guards are now `if self._last_frame is None or
  self._last_frame.empty:`. Reproduced against `HEAD` first, through the real
  widget headlessly: with a three-row frame assigned to `_last_frame`, both
  `export_bur()` and `export_flr_cif()` raised the quoted `ValueError`. Fixing
  the `None` half alone would have left the second, quieter defect the same
  line carries: an **empty** frame passed the old guard (`not <empty frame>` is
  `True`, so it returned early — but only by accident of pandas' own error
  path; with `.empty` the intent is explicit and the header-only file the
  flrCIF writer would emit for a zero-row frame is no longer written). Pinned
  by the new `test/plugins/burst_selection/test_export_guards.py` (6 tests: a
  non-empty frame round-trips through `.bur` — read back with the same columns
  and row count — and through flrCIF, which carries the `loop_` block and one
  `_column` tag per column; and the four `None` / empty-frame combinations
  report "No burst data to export." without creating the target file). Four of
  the six fail against `HEAD` — the two writes with the `ValueError`, the two
  empty-frame cases by writing a file that should not exist.
  `test/plugins/burst_selection` + `test/plugins/test_burst_selection_transformer.py`
  green (22 passed); `ruff check` on `tool.py` reports the same 5 pre-existing
  findings as `HEAD` and none new, and the new test file is `ruff check` +
  `ruff format` clean.

### RF-054
- **Status:** OPEN
- **Severity:** S2 (the preview contradicts both the run and its own parameters)
- **Location:** `chisurf/gui/widgets/wizard/tttr_photonfilter/tttr_photon_filter.py:765` (`burst_start_stop`) feeding `update_burst_info` at `:1033`; displayed in the Burst Selection *Filter Settings* → *Info* box
- **Finding:** The Info box derives its burst statistics from `find_bursts(self.selected, max_gap)` — contiguous runs of the *photon-selection mask* over the full photon array — not from the burst search the settings above it describe and the **🚀** run actually performs (tttrlib `sliding_window`, L=20, m=10, T=0.5 ms, applied to the filtered photon stream). The two disagree by more than an order of magnitude and the box is not refreshed after a run, so both numbers sit on screen at once. Verified on `m000.spc` with the shipped `BS` setup: the Info box reports *Bursts 7730, mean duration 4.103 ms, mean photons/burst 15.0* while the run reports 152 bursts of mean 113 photons (620 over three files) — and *mean photons/burst 15.0* is impossible beside the *Min photons (L) = 20* the same panel displays two rows lower, which is the self-evident tell. Either compute the preview with the configured search on the filtered stream (so it predicts the run), or label it as "photons passing the filter, grouped" and drop the burst-search-shaped statistics.
- **Fix note:**

### RF-055
- **Status:** OPEN
- **Severity:** S2 (an exception per repaint; error bars never drawn)
- **Location:** `chisurf/plugins/burst/burst_bva/gui/tool.py:467-468` (`_setup_plot`, `plot.errorbars(..., height=np.array([]))`) with `:522` (`set_data(x_centers, mean, top=sd, bottom=sd)`)
- **Finding:** The item is created with an empty `height` and thereafter only ever updated with `top`/`bottom`. `_ErrorBars.set_data` (`chisurf/gui/chiplot/backends/pyqtgraph_backend.py:288`) forwards only the keys it is given, and pyqtgraph's `ErrorBarItem.setData` merges into existing opts, so the stale `height=array([])` survives and `drawPath` takes the `height` branch: `y1 = y - height/2.` → `ValueError: operands could not be broadcast together with shapes (31,) (0,)`, raised from both `paint` and `boundingRect` on every repaint. Verified by opening the BVA panel on a 620-burst folder (`Done – 555 bursts with Std > 0 on 620 total`): the console fills with the traceback and the binned-mean curve is drawn with no uncertainties at all. Create the item without `height` (or pass `height=None` in `set_data` alongside `top`/`bottom`) and guard the empty-data case; a test that calls `_plot_2d_histogram` on a small array and asserts the item's opts carry no `height` would pin it.
- **Fix note:**

### RF-056
- **Status:** OPEN
- **Severity:** S3 (a primary button that is a no-op until an undiscoverable field is changed)
- **Location:** `chisurf/plugins/burst/burst_selection/gui/tool.py:774` (`_build_histogram_group`, `gmm_components_spin` created with `setRange(0, 10)` and no `setValue`) with `_plot_gmm` at `:2489`
- **Finding:** The spin box therefore starts at 0, `_plot_gmm` reads `n_components = 0`, the auto-component branch is only taken when *Auto components* is ticked, and the fall-through writes "GMM fitting skipped: not enough data points or zero components." So **🎯 Fit GMM** does nothing on a fresh session and the message leads with the wrong cause — verified on a 620-burst proximity-ratio histogram, which has plenty of data. Default the spin to 1 (or 2, the usual smFRET case), or tick *Auto components* by default, and split the message so "zero components" is reported as its own, actionable text.
- **Fix note:**

### Review 2026-07-25 — scan-precision planner (`img_precision` + `ics.precision`)

Slice: the newly landed *Plan* panel (commit `bf7a5cb38`) — the `img_precision`
plugin (`core.py`, `gui/view_model.py`, `gui/tool.py`, `cli/main.py`) and the
`RICSPE` port it wraps, `chisurf/core/experiments/ics/precision.py`. Every
finding below was reproduced against the source in the `arm64` env. The
estimator's own algebra (the `q` brightness correction, `_atanh_over_argument`
through and below a spherical focus, the master-grid slice bounds in
`correlation_covariance`, the `correlation_grid` closed form against its
docstring) was checked numerically and is sound. Findings RF-057..RF-063.

### RF-057
- **Status:** FIXED
- **Severity:** S1 (`ZeroDivisionError` from a GUI-reachable setting; silently negative variance below it)
- **Location:** `chisurf/core/experiments/ics/precision.py:415` (`correlation_covariance`, `denom`) and `:402` (`term1`, `2 * (nx - 2 * xi) * (ny - 2 * psi)`), unguarded by the validation block at `:521-535`
- **Finding:** `rics_precision` validates the times, the sizes and `D`, but never `n_lags` against `nx`/`ny`, and both are user-facing spin boxes: `precision.view.json:87` gives `nx` a **minimum of 8** while `:109` gives `n_lags` a **maximum of 15**. At `n_lags >= nx` the loop reaches `xi == nx`, `denom = (nx - xi) * … = 0`, and the call dies with `ZeroDivisionError: float division by zero` — verified through the GUI view model (`nx = ny = 8`, `n_lags = 8` → `compute()` returns False with status `Prediction failed: float division by zero`). That contradicts the documented contract (`Raises ValueError …`) *and* defeats `sweep_dwell`'s per-point recovery, which catches `ValueError` only, by deliberate comment (`core.py:175-179`) — so one bad *global* setting takes the whole curve down rather than one point. Below that, for `2 * n_lags > nx`, `2 * (nx - 2 * xi)` — a count of pixel positions where the triple product fits — goes **negative** (nx=16 → −4 at xi=9) and subtracts from a variance with no error at all. One guard fixes both: reject `2 * n_lags >= min(nx, ny)` with a `ValueError` naming the offending pair, and clamp the overlap count at 0. Pin it with a test that asserts the raise for `nx=8, n_lags=8` and that `sweep_dwell` propagates it rather than returning a curve of NaNs.
- **Fix note:** Guarded at the root — in `correlation_covariance` itself, which
  owns the division, so the public function and `rics_precision` are both
  covered by one check: `2 * n_lags >= min(nx, ny)` raises a `ValueError` naming
  the pair and the largest lag that would fit (*"n_lags=8 is too large for a
  8x8 image … so at most n_lags=3"*). The strict form is deliberate, as the
  finding argues: above half, the triple-product term's position count goes
  negative. The **clamp was deliberately not added**: with the guard in place
  `xi <= n_lags` and `2 * n_lags < nx`, so `nx - 2 * xi > 0` always and a
  `max(…, 0)` would be unreachable code.
  The second half of the finding is the trap the first half creates.
  `sweep_dwell` swallows `ValueError` per point on purpose, so simply turning
  the `ZeroDivisionError` into a `ValueError` would have converted a loud crash
  into a silent curve of NaNs, which the panel then blames on the waists and the
  pixel size. The recovery is therefore narrowed to a new
  `precision.UnrealisableScan(ValueError)`, which marks settings describing an
  acquisition that could not be performed (a zero dwell or waist, a line shorter
  than the pixels it holds) — the cases where the *next* dwell time may still
  work. A request no acquisition satisfies stays a plain `ValueError` and takes
  the sweep down with its own message; the GUI view model, which already catches
  `Exception`, now reports `Prediction failed: n_lags=8 is too large for a 8x8
  image …` instead of `Prediction failed: float division by zero`. The finer
  line (per-point = *timing only*, so a zero waist would also propagate) was
  tried first and rejected: it changes the total-failure message `RF-060`'s fix
  settled on, which is beyond this finding.
  Reproduced against `HEAD` first — `ZeroDivisionError: float division by zero`
  from `correlation_covariance(6, 6, 6, …)`, from `rics_precision(…, nx=8,
  ny=8, n_lags=8)` and out of `sweep_dwell`. Pinned by
  `test/experiments/test_ics_precision.py::test_a_lag_the_image_cannot_hold_is_rejected`
  (both entry points, that the error is *not* an `UnrealisableScan`, and that the
  largest allowed lag still predicts) and by
  `img_precision/test/test_img_precision.py::test_a_request_no_acquisition_satisfies_takes_the_sweep_down`;
  all three fail at `HEAD`. The constraint is documented where it is set — the
  `n_lags` `description` in `precision.view.json` (tooltip *and* generated docs
  cell) and `docs/guides/45_scan_precision.md`. `test/experiments/` +
  `img_precision/test/` green (84 passed); `ruff check` findings on the four
  touched Python files are identical to `HEAD` (all pre-existing).

### RF-058
- **Status:** OPEN
- **Severity:** S2 (a documented geometry flag that only half applies)
- **Location:** `chisurf/core/experiments/ics/precision.py:537` (`gamma = gamma_factors(two_d)`) versus `:572`, `:582` and `:601` (the three `correlation_grid` calls) — `correlation_grid` (`:138`) takes no `two_d` parameter
- **Finding:** `two_d` is exposed as **Membrane (2-D)** (`precision.view.json:65`) and documented in `docs/guides/45_scan_precision.md:47`, and it switches the shape factors (`gamma_factors`) and the number-density geometry (area instead of volume, `:541-545`) — but the correlation model that both *generates* the noiseless data and *fits* it keeps the 3-D axial denominator `sqrt(1 + 4Dτ/(αw)²)` unconditionally. Ticking the box therefore predicts a hybrid: 2-D brightness statistics on a 3-D correlation decay. Measured on the fitted lag grid at the **slow end of the default sweep** (dwell 0.5 ms, `nx=64`, overhead 1.2, D=10 µm²/s, `w_z/w_r=5`) the retained axial factor suppresses the correlation by up to **2.2×** (ratio 0.45 at ψ=4) against a true 2-D shape — i.e. it distorts exactly the half of the curve the user is choosing a dwell time from. At the fast end it is 0.2 % and invisible, which is why it survives the shipped tests. Either thread `two_d` into `correlation_grid` (drop the axial term) or state in the flag's `description` and in the guide that only the shape factors change.
- **Fix note:**

### RF-059
- **Status:** OPEN
- **Severity:** S2 (two CSV writers, one header, different contracts)
- **Location:** `chisurf/plugins/microscopy/img_precision/gui/tool.py:107-113` (`_export_csv`) via `gui/view_model.py:198` (`sweep_rows`), against `cli/main.py:81-86` (`--out-csv`)
- **Finding:** Both write a file whose header is `dwell_us,line_ms,frame_ms,error_percent`, but the GUI export reuses `sweep_rows()` — the **display** formatting — so an unrealisable point lands in the numeric `error_percent` column as the em dash `—` (verified: `sweep_rows` returns `{'error': '—', 'dwell': '1', …}` for a NaN row) where the CLI writes an empty field, and every value is pre-rounded to `%.3g`/`%.1f` where the CLI writes `%.6g`/`%.4g`. A `dwell_us` of `1.5811388300841894e-05` s is exported by the CLI as `15.8114` and by the GUI as `15.8`. Give the view model a numeric export accessor (or reuse the CLI's row builder) and have both paths call it; a test that exports a sweep containing one NaN row from both paths and asserts the two files agree would pin it.
- **Fix note:**

### RF-060
- **Status:** FIXED
- **Severity:** S3 (invalid JSON and a success exit code on a total failure)
- **Location:** `chisurf/plugins/microscopy/img_precision/cli/main.py:88-96` (the `as_json` branch returns before the realisability check)
- **Finding:** The `--json` branch emits `sweep.to_dict()` and returns *above* the "no dwell time is realisable" guard, so a configuration in which every point failed exits **0** with `"relative_error": [NaN, NaN, NaN]`, `"best_dwell_s": NaN`. Verified with `--w-r 0`: exit 0 and a payload that a strict parser rejects (`json.loads(..., parse_constant=raise)` → `bare NaN`), while the identical invocation without `--json` correctly exits 1 with `Error: no dwell time is realisable …`. The scripting path is the one that most needs the non-zero exit. Move the check above the branch and emit the failure as JSON (`{"error": …}`) with a non-zero exit.
- **Fix note:** The realisability test is now computed once above both output
  branches (`cli/main.py`, `realisable` / `nothing_works`), and the `--json`
  branch emits `{"error": …}` and `ctx.exit(1)` when nothing is realisable, so
  the two modes agree on the exit status and the human-readable path keeps its
  `ClickException`. The NaN half was fixed at the source rather than in the
  branch: `PrecisionSweep.to_dict` maps every non-finite entry (the swept
  errors and both `best_*` scalars) to `None` via a new `_or_none` helper, so a
  *partially* unrealisable sweep is strict JSON too — not just the total
  failure. Pinned by
  `test_cli_json_reports_a_total_failure_instead_of_a_curve_of_nulls` (exit 1
  from both output modes, error object parsed with a `parse_constant` that
  raises) and by `test_summary_is_json_friendly`, now sweeping a zero dwell and
  asserting that entry is null under the same strict reader.

### RF-061
- **Status:** OPEN
- **Severity:** S3 (observer plumbing that is never triggered)
- **Location:** `chisurf/plugins/microscopy/img_precision/gui/view_model.py:57` (`notify`) and `gui/tool.py:76-77` (`modelEvent` / `add_observer`)
- **Finding:** `PrecisionViewModel.notify()` has no caller anywhere — not in the plugin, not in `chisurf/gui/autoform/`, not in `ChisurfDockTool` (grepped `.notify(` and `add_observer` across all three). The `modelEvent` signal, its comment ("re-emitted so they are always handled on the GUI thread") and `_handle_model_event` are therefore dead: the panel refreshes only because `_on_finished` also calls `_refresh()`. Either call `notify()` where state changes (and fix RF-062 first, which that would immediately expose) or delete the three-part observer path so the next reader does not assume a live channel.
- **Fix note:**

### RF-062
- **Status:** OPEN
- **Severity:** S3 (a plotted point whose coordinates were never computed together)
- **Location:** `chisurf/plugins/microscopy/img_precision/gui/view_model.py:181` (`sweep_series`, `"x": np.array([float(self.pixel_time_us)])`)
- **Finding:** The "your setting" marker takes its **x** from the live spin-box attribute and its **y** from `s.current.relative_error`, the prediction made for whatever `pixel_time_us` was when `compute()` ran. `s.current.pixel_time` carries the value that was actually predicted and is ignored. Any refresh that is not preceded by a recompute plots the old error at the new dwell. Latent today only because nothing refreshes the plot without recomputing (RF-061); it becomes a live wrong-data bug the moment that observer path is wired. Use `s.current.pixel_time * 1e6`. `_summary()` (`:165`) reads the same live attribute for its `At {…} µs:` prefix and should follow.
- **Fix note:**

### RF-063
- **Status:** OPEN
- **Severity:** S3 (docstrings describing a different tool)
- **Location:** `chisurf/plugins/microscopy/img_precision/gui/tool.py:47` (`ImgPrecisionTool`) and `:25` (`_ComputeTask`)
- **Finding:** Copy-paste from the `img_drift` panel survived: the class docstring reads *"Drift-correction tool: action toolbar + `AutoForm(view_model)`"* and `_ComputeTask` is documented as *"Run the Qt-free measurement off the UI thread (image reads are slow)"*. This tool corrects no drift and reads no images at all — it takes no data, which is the single most important thing about it and is exactly what the class docstring should say (the CLI's help text and `test_precision_is_registered_in_the_imaging_toolbox` both make the point correctly). Also note the panel has no re-entrancy guard on **▶ Predict** (`:81`): a second press starts a second `_ComputeTask` against the same view model, and the slower run's `_sweep`/`_status` win regardless of order. At GUI defaults a sweep takes 0.9 s so the window is small, but cost grows as `n_lags⁴` and the spin box allows 15 (≈ 3 min), where a double press is likely.
- **Fix note:**

### Review 2026-07-25 (5) — the MCMC sampling backends (`core/fitting/sample.py`)

Slice: `chisurf/core/fitting/sample.py` and its driver `sample_fit` /
`pool_chains` in `chisurf/core/fitting/fit.py` — the recently reworked warm-up
(`086422d51`), the collapsed shared-parameter sampler and the independent-component
decomposition. Every finding below was reproduced in the `arm64` env against the
`_collinear_fit` / `_global_fit` fixtures the existing suites use. The parts that
check out: the DE snooker Jacobian (`0.5*(d-1)*log(‖x*-z‖²/‖x-z‖²)`) and its
projection step match ter Braak; the Laplace normalisation in `_profile_locals`
(`½[d ln 2π - ln det JᵀJ]` with Σ = (JᵀJ)⁻¹) is right for `-lnL = ½χ²`; the
closed-form component merge `χ² = Σ_c χ²_run,c - (C-1)χ²_0` holds even when a run
is cancelled part-way through the component list; and `_adaptation_windows`
produces a valid schedule at both the clipped minimum (100) and maximum (500).
Findings RF-064..RF-069.

### RF-064
- **Status:** OPEN
- **Severity:** S1 (the collapsed target counts a shared parameter's prior twice)
- **Location:** `chisurf/core/fitting/sample.py:1421-1426` (`_target`, the `shared_prior` loop) against `:1259`/`:1208` (`_profile_locals` → `_restricted_wres(..., include_priors=True)`) and `chisurf/core/fitting/fit.py:2475` (`_prior_residuals`)
- **Finding:** `_prior_residuals` appends a prior residual for **every** free parameter of the local model, and `_shared_and_private` documents at `:1177` that one local model's free list still holds the *shared* parameter (the link master lives on that dataset). So `_profile_locals` already folds the shared prior into `ln_z` as `-½r² = +lnpdf`, and `_target` then adds `shared_prior` on top. Verified on the 4-dataset star-linked `_global_fit` with `NormalPrior(mu=1.25, sigma=0.01)` on the shared `a`: the master's local model reports one prior residual (`-4.91`) while the other three report none, and over a grid of shared values `T(v) - [T_noprior(v) + lnpdf(v)]` equals `lnpdf(v)` to the last digit (`[-12.5, -8, -4.5, -2, -0.5, 0, …]` for both). The shared parameter's collapsed posterior is therefore narrowed by √2 in the prior-dominated limit — `sample_fit(method='collapsed')` reports a credible interval that is too small exactly when an informative prior is in play. Fix by profiling the locals with the shared parameter's prior excluded (or by dropping `shared_prior` and letting `_profile_locals` own it), and pin it with a collapsed run against `walk_mcmc_blocked` on a fit with a prior on the shared parameter — `test/fitting/test_collapsed_sampler.py` has no prior test at all.
- **Fix note:**

### RF-065
- **Status:** OPEN
- **Severity:** S1 (recorded draws violate the parameter bounds; the chain file and the diagnostics then disagree about which draws exist)
- **Location:** `chisurf/core/fitting/sample.py:1504-1505` (`sample_marginal_shared`, `draw[indices] = theta + chol @ rng.normal(...)`) with `chisurf/core/fitting/fit.py:1932` (`save_chain_to_file`, `mask = np.where(np.isfinite(chi2))`) and `:2096` (`pool_chains`)
- **Finding:** The private parameters are drawn from their *untruncated* conditional Gaussian, so any private parameter whose bound sits within a few σ of its profiled optimum yields out-of-range draws. `lnprob_parts` then returns `(-inf, -inf, inf)` for them, and the two consumers diverge: `save_chain_to_file` drops every non-finite-`chi2` row from the `.er4` file, while `pool_chains` reads `r['chains']` unmasked and hands the invalid draws straight to `summarize`/`convergence_warnings` and to `fit.sampling_chain`. Verified on the 4-dataset `_global_fit` with a lower bound placed on one private `c` at its optimum: **117 of 300 recorded draws** violate a bound, all 117 carry `chi2r = inf` and `lnprior = -inf`, and all 117 survive into the pooled diagnostics but not into the saved chain. A bound at zero on a background offset or an amplitude fitted near zero is the routine version of this. Either truncate/reject the conditional draw against `model.parameter_bounds` or discard the recorded state, and make the file and the diagnostics apply the same mask either way.
- **Fix note:**

### RF-066
- **Status:** OPEN
- **Severity:** S2 (`sample_fit`'s `n_runs` are not the independent runs its R-hat is computed from)
- **Location:** `chisurf/core/fitting/sample.py:812` (`walk_mcmc_blocked`, `state = np.asarray(model.parameter_values, …)`) and `:97` (`walk_mcmc`), neither of which restores the model before returning — unlike `:714` (`sample_differential_evolution`) and `:1518` (`sample_marginal_shared`) — reached through `:1096-1101` (single-component fallback) and `chisurf/core/fitting/fit.py:1953` (the `n_runs` loop), against `:2102` (`pool_chains`: *"Independent runs are exactly what a cross-chain R-hat is computed from"*)
- **Finding:** `_lnprob` sets `model.parameter_values` on every evaluation, and the last evaluation of a sweep is the *trial*, so both walkers return with the model parked on the final proposal — possibly a rejected one. Verified on `_collinear_fit`: after `walk_mcmc_blocked`, the model reads `[1.0792, 1.8657, 0.5523]`, which is neither the optimum `[0.9411, 2.0776, 0.4763]` nor the last recorded draw `[0.9949, 2.0029, 0.5019]`. `sample_fit` restores the starting values only *after* all `n_runs`, so for `method='mcmc'` and for `method='blocked'` on a single-component fit (the common case) runs 2..N start from the previous run's leftover proposal — the runs are one continued chain, and the cross-run R-hat can no longer detect a failure to reach the typical set. It also breaks `_seed_block_covariances`, whose docstring promises "the curvature of the objective at the optimum": from run 2 on, `fit.covariance_matrix` is evaluated at that arbitrary leftover point. Restore `model.parameter_values` before returning from both walkers (as the other two backends already do).
- **Fix note:**

### RF-067
- **Status:** OPEN
- **Severity:** S2 (a documented pass-through option silently ignored by one backend)
- **Location:** `chisurf/core/fitting/sample.py:1302` (`sample_marginal_shared` takes no `chi2max`) and `chisurf/core/fitting/fit.py:1995-2002` (the `method == 'collapsed'` branch, which is the only one of the five not to pass `chi2max`)
- **Finding:** `sample_fit`'s docstring states that "steps, thin, chi2max, n_runs, step_size, temp" are "passed through to `cs.core.fitting.sample`", and the `de`, `blocked`, `mcmc` and `emcee` branches all forward `chi2max`. `sample_marginal_shared` has no such parameter, so a user-set cutoff is silently dropped for the collapsed backend — and its two fallbacks to `sample_independent_components` (`:1384` and `:1440`) drop it as well, so a fit that falls back is *also* sampled without the cutoff the caller asked for. Either thread `chi2max` through `_target` (rejecting a shared state whose profiled χ² exceeds it) or raise when a non-infinite `chi2max` reaches this backend; do not accept it and ignore it.
- **Fix note:**

### RF-068
- **Status:** OPEN
- **Severity:** S3 (a parameter docstring that documents the value the change replaced)
- **Location:** `chisurf/core/fitting/sample.py:783-784` (`walk_mcmc_blocked`, the `n_adapt` parameter) against `:886` (`n_adapt = int(np.clip((n_samples * thin) // 20, 100, 500))`)
- **Finding:** The perf change `086422d51` shortened the default warm-up from `min(2000, max(200, n_steps // 2))` to `clip(n_steps // 20, 100, 500)` and updated the inline comment (`:879-885`) and `okf/subsystems/fitting.md:277`, but not the docstring, which still reads "Defaults to half the chain (bounded to ``[200, 2000]``)" — i.e. exactly the behaviour the commit removed, and the message a caller reading `help()` or the API docs gets. On the shipped default of 1000 steps the real value is 100, not 500. Correct the sentence to match `:886`.
- **Fix note:**

### RF-069
- **Status:** OPEN
- **Severity:** S3 (a return annotation that contradicts the function)
- **Location:** `chisurf/core/fitting/sample.py:228` (`_seed_block_covariances(...) -> list[np.ndarray]`) against `:305` (`return out, from_curvature`)
- **Finding:** The function returns a 2-tuple — its own Returns section says so ("``(covariances, from_curvature)``") and the sole caller unpacks two values at `:831` — but the annotation claims a bare list. `pixi run typecheck` runs mypy over `chisurf/`, so this is a live annotation error rather than a cosmetic one. Change it to `tuple[list[np.ndarray], list[bool]]`.
- **Fix note:**

## GUI-tester run — Calculators hub (2026-07-25)

Driven headlessly through the real Qt widgets (`CalculatorHub` walked row by row,
then `FretCalculatorTool`, `Kappa2Dist` and `FRETLineTool` driven directly with
committed `editingFinished` edits, button clicks and tab switches; modal dialogs
captured with a polling `QTimer`). Use case:
[FRET calculators](/usecases/fret-calculators.md). Findings RF-070..RF-077.

### RF-070
- **Status:** OPEN
- **Severity:** S2 (drawing a line silently rewrites the user's model)
- **Location:** `chisurf/plugins/fret_line/gui/tool.py:552-577` (`_add_fret_line`) → `chisurf/plugins/fret_line/core/algorithms.py` (`compute_fret_line_for_models`)
- **Finding:** Computing a FRET line sets the swept parameter on the live model for each of the `n_pts` samples and never restores its original value, so the model is left parked at the last point of the sweep. Verified on a fresh `FRETLineTool`: `R(G,1)` reads `50.0` before, and after a single **+ Add FRET line** over Min 20 → Max 90 it reads **90.0** — the *Editor* panel now shows 90 Å where the user typed 50. Every subsequent line is computed from the mutated model, which is how a sequential walk of the nine sweep targets produced eight consecutive `division by zero` dialogs while each target driven from a fresh widget succeeded. Snapshot the swept parameter's value (and restore it in a `finally`) around the sweep, as `sample_differential_evolution` already does for the sampler; pin it with a test asserting the parameter is unchanged after `_add_fret_line`.
- **Fix note:**

### RF-071
- **Status:** OPEN
- **Severity:** S2 (a shipped default that makes the tool's only action fail)
- **Location:** `chisurf/plugins/fret_line/gui/tool.py:282-285` (`_min_spin`, never given a `setValue`) and `:552-575` (`_add_fret_line`'s bare `except` → message box)
- **Finding:** `_max_spin` is initialised to `100.0` but `_min_spin` is not, so the sweep range starts at exactly **0** out of the box. The sweep then evaluates the model at 0, which for the lifetime-valued targets `t0` and `tL1` is a zero lifetime: the computation raises `ZeroDivisionError` and aborts the whole line. It surfaces as a `QMessageBox` with an **empty window title** whose entire body is the raw exception string `division by zero` — no mention of which parameter, which sample, or that the range is at fault — and no line is added. Verified with a fresh widget per trial: `t0` and `tL1` fail at `[0, 100]` and both return 100 distinct points (`E` 0.069–0.830 and 0.153–0.822) at `[1, 100]`; `R0`, `k2`, `R(G,1)`, `s(G,1)`, `k(G,1)` survive 0 unharmed. Seed Min/Max from the selected parameter's own bounds (which would also fix RF-072), and make a non-finite sample yield `NaN` for that point instead of discarding the entire line.
- **Fix note:**

### RF-072
- **Status:** OPEN
- **Severity:** S2 (shipped defaults produce a silently degenerate result)
- **Location:** `chisurf/plugins/fret_line/gui/tool.py:453-478` (`_refresh_sweep_targets`, which selects index 0) and `chisurf/plugins/fret_line/core/algorithms.py` (`sweep_targets_for_models`, whose first entry is `xL1`)
- **Finding:** The sweep-target combo defaults to its first entry, `C0 [FRET: FD (Gaussian)] · xL1` — the amplitude of the *only* lifetime component. Amplitudes are normalised (`lifetime.py:66`, `vs /= abs(vs.sum())`), so a lone component's amplitude is exactly scale-invariant and cannot change the result. Clicking **+ Add FRET line** with everything as shipped therefore returns 100 identical samples (`E = 0.5799`, `τ_F = 1.92613 ns`, `τ_X = 1.68039 ns`, plus a `NaN` at the 0 sample), which pyqtgraph auto-ranges into a **blank-looking plot** while the *FRET lines* list and the legend both show a confident "Line 1". `x(G,1)` is degenerate in the same way. Nothing warns the user. Default the combo to a parameter that moves the line (`R(G,1)`, the mean donor–acceptor distance, is the canonical static-FRET-line sweep) and warn when a completed sweep yields a constant `E`.
- **Fix note:**

### RF-073
- **Status:** OPEN
- **Severity:** S2 (a failed conversion leaves contradictory numbers on screen)
- **Location:** `chisurf/plugins/calculator/fret_calculator/gui/tool.py:294-300` (`_on_E_changed`), `:302-308` (`_on_kFRET_changed`), `:277-285` (`_on_tau_changed`) — each `if r.get("ok"):` with no `else`
- **Finding:** All three inverse handlers ignore a failed backend call entirely: no dialog, no status line, no reset of the dependent fields. The backend fails for exactly the inputs that mean "I measured no transfer" — `compute_fret_from_efficiency(E=0)` → `{'ok': False, 'error': 'division by zero'}`, `compute_fret_from_rate(kFRET=0)` → `'0.0 cannot be raised to a negative power'`, `compute_fret_from_lifetime(tau_DA=tau0)` → `'division by zero'` — and the spin-box ranges (`E ∈ [0, 1]`, `kFRET ∈ [0, 9999]`) allow every one of them. Driven in the GUI, typing `E = 0` leaves the panel showing **Efficiency 0.000000 beside Distance DA 0.10 Å, Lifetime DA 0.0000 ns and kFRET 9999.000000** — zero transfer displayed together with maximum transfer, with no indication the calculation never ran. Either report the failure in the panel and blank the derived fields, or handle the no-transfer limit explicitly (`R → ∞`).
- **Fix note:**

### RF-074
- **Status:** OPEN
- **Severity:** S2 (the same panel converts in two mutually inconsistent conventions)
- **Location:** `chisurf/plugins/calculator/fret_calculator/gui/tool.py:262-275` (`_compute`, passes `sigma=` and `distribution=`) against `:277-308` (the three inverse handlers, which pass neither)
- **Finding:** The forward direction averages the transfer efficiency over the distance distribution of width `Sigma`, while all three inverse directions call single-distance Förster inverses — their results echo `sigma: 0.0` regardless of what the *Sigma* box shows. The pair of fields is therefore not self-consistent: at the default `σ = 6 Å`, typing `R = 60 Å` yields `E = 0.309307`, and typing that identical efficiency straight back yields **`R = 59.450 Å`** — a 0.55 Å shift with nothing changed and no explanation. Setting `σ = 0.1 Å` collapses the drift to 0.010 Å (spin-box rounding), confirming `Sigma` as the cause. A user who types an experimental `E` gets a distance computed as if σ were 0 while the panel displays σ = 6. Thread `sigma`/`distribution` through the inverse RPCs (numerically inverting `⟨E⟩(R)`), or state in the UI that the inverses are single-distance.
- **Fix note:**

### RF-075
- **Status:** OPEN
- **Severity:** S3 (the selected item's label is invisible)
- **Location:** `chisurf/plugins/calculator/hub/gui/tool.py:71-86` (the `QListWidget` stylesheet, which has no `::item:selected` rule)
- **Finding:** The stylesheet restyles `QListWidget::item` (height, padding, radius, margin, bold 14 px) but never gives `:selected` a background, so the selected row keeps the white `Base` while Qt still paints its text with `HighlightedText` — which is `#ffffff` on this palette. The selected calculator's name is white on white. Confirmed by sampling the text area of every row: the selected row contains **no** `#000000` pixels (only the emoji's own colours) while every unselected row contains hundreds, so the selected entry reads as a bare "🎯" or "📉". Reproduced on all six rows. Add `QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }` — the rule is missing entirely, so the list also has no selection affordance beyond a faint focus rectangle.
- **Fix note:**

### RF-076
- **Status:** OPEN
- **Severity:** S3 (an empty collapsible header renders above the first control)
- **Location:** `chisurf/plugins/calculator/kappa2_dist/k2dist.view.json` (first section, `"title": ""`)
- **Finding:** The first section of the κ² view spec has an empty title, and AutoForm renders it as a full-width grey collapsible header containing a `▼` and nothing else, directly above the *Model* radio row — it reads as a broken or unlabelled group. Confirmed both visually and by enumerating the panel's buttons, where it appears as `('QPushButton', '▼  ')` alongside the correctly titled `'▼  Anisotropy Parameters'`, `'▼  Calculation Options'` and `'▼  Results'`. Either give the section a title (it holds the model selector, so "Model" fits) or make AutoForm render a titleless section as a plain container with no header bar.
- **Fix note:**

### RF-077
- **Status:** OPEN
- **Severity:** S3 (a dimensionless bounded axis labelled with an SI multiplier)
- **Location:** `chisurf/plugins/calculator/phasor_calculator/gui/tool.py` (the phasor plot's left axis)
- **Finding:** The phasor plot's `s` axis is handed to pyqtgraph's automatic SI scaling, so it renders as `s (x0.001)` with ticks running 0…600 — the apex of the universal semicircle, `s = 0.5`, displays as "500". `s = Im(phasor)` is dimensionless and bounded above by 0.5 by construction, and the `g` axis beside it is correctly 0…1.0, so the two axes of a semicircle are drawn on scales that differ by 1000×. Disable the auto-multiplier (`axis.enableAutoSIPrefix(False)`) for both phasor axes and fix the range to `g ∈ [0, 1]`, `s ∈ [0, 0.5]`. The same auto-multiplier appears on the FRET calculator's distribution plots (`p(R) (x0.001)`, and `p(k) (x0.` clipped mid-label).
- **Fix note:**

### Review 2026-07-25 (6) — chimol's two coordinate arrays, and the new `scene` store

Slice: commit `119a63e46` — `renderer/view.py` (`_apply_rigid_transform`,
`apply_transform_to_object`), the length-reporting commands in
`cmd/measurements.py` (`rms`, `align`/`super`, `pair_fit`), and the new
`renderer/scenes.py` + `cmd/rendering.py::scene`. Every finding below was
reproduced in the `arm64` env against 148L, the same fixture the new
`test_transform_sync.py` uses. What checks out: `translate` now moves both arrays
by exactly the same distance in their own units (10 Å and 100 scene units);
`rms` reports Å in **both** its branches, since `all_atom_coords` is in scene
units too, so the single division by `_scale_factor` is right for the all-atom
path as well as the CA path; `pair_fit` reads Angstrom, reports Angstrom and
scales its translation into scene units correctly; every name in
`_REPRESENTATION_FIELDS`/`_COLOR_FIELDS` exists on `_MolViewObjectState`;
`SceneStore.step` wraps correctly from either end and from an unknown key.
Findings RF-078..RF-082.

### RF-078
- **Status:** OPEN
- **Severity:** S1 (a rotation still leaves the two coordinate arrays describing different geometries)
- **Location:** `chisurf/plugins/chimol/chimol/renderer/view.py:583-586` (`apply_transform_to_object`, the atom-array branch) against `:743-764` (`_transform_world_coords_to_scene`), with `chisurf/plugins/chimol/test/test_transform_sync.py:113-125`
- **Finding:** Scene coordinates are `(atom_xyz - raw_center) * scale`, so a render-space transform `(R, t)` corresponds to `x' = R·(x - c) + c + t/s` in atom space. The new code applies `x' = R·x + t/s` — it rotates the atom array about the **PDB coordinate origin** while the render arrays rotate about the molecule's centre. The error is `(I - R)·c`, which vanishes only for a pure translation, and a pure translation is the only case the new tests cover. Verified on 148L (`raw_center = [8.30, 45.17, 34.63]`, ‖c‖ = 57.5 Å, `_scale_factor` = 10): the invariant `(atoms["xyz"] - raw_center) * scale == all_atom_coords` holds to **0.0 Å** at load and after `translate`, and breaks by **53.5 Å** after `rotate z, 90`. Across two objects it is worse — after `copy mob, ref` and `rotate z, 90, mob` the mean per-atom mob↔ref separation is **15.8 Å as drawn** (and as `save` writes it, since `save` unscales `all_atom_coords`) but **66.1 Å in the atom array** that `get_area`, `alter_state`, `pair_fit`/`_selection_coordinates` and every `within`/distance selection read. That is precisely the "one geometry, not two" defect the commit set out to remove, still live for rotations. `test_a_rotation_reaches_the_atom_array` misses it because it re-centres each side on its own mean before comparing distances, which is invariant to the pivot. Rotate the atom array about `state.raw_center`, and pin it with the invariant above rather than a centred-distance check.
- **Fix note:**

### RF-079
- **Status:** FIXED
- **Severity:** S1 (`align`/`super` print a length ten times too large with an Angstrom sign on it)
- **Location:** `chisurf/plugins/chimol/chimol/cmd/measurements.py:708` (`f"(RMSD: {final_rmsd:.3f} Å)"`) against `:426-432` (the identical bug fixed in `rms` by the same commit)
- **Finding:** `_align_or_super` measures `get_residue_positions`, which returns `state.coords` in **scene units**, and prints the Kabsch RMSD straight out labelled Å — exactly the defect `119a63e46` corrected 280 lines above in `rms`, left untouched in the sibling command the guide presents beside it (`docs/guides/44_molecular_viewer.md:141-149`). Verified: a copy of 148L carrying 0.5 Å Gaussian noise on its CA coordinates (true CA RMSD 0.87 Å) is reported by `align mob, ref, cutoff=100` as **8.728 Å** — `_scale_factor` (10) times too large, and ten times what `rms` and `pair_fit` say about the same pair. Divide by `_scale_factor` as `rms` now does. No test can catch this today: `test_transform_sync.py` only aligns a *rigidly displaced* copy, where the answer is 0.000 in either unit.
- **Fix note:** Confirmed, and the same unit boundary was wrong twice in that
  function: besides the printed RMSD, the outlier `cutoff` — a distance the user
  types in Angstrom — was compared against distances in scene units, so the
  default `cutoff=2.0` really meant 0.2 Å. On 148L jiggled by 0.5 Å of noise the
  rejection loop ran itself down to `using 3/165 atoms`, superposing the whole
  molecule on three residues and announcing it as a 0.100 Å fit. Rather than
  convert the two results separately, `_align_or_super` now divides **both**
  coordinate sets by `_scale_factor` on the way in, so the fit runs in Angstrom
  throughout and only the fitted translation is scaled back for
  `apply_transform_to_object` (which takes scene units) — the conversion
  `pair_fit` already did. Dividing both sets by one scalar leaves the Kabsch
  rotation untouched and scales its translation exactly, so nothing inside the
  loop changed. The same case now reports `165/165` and 0.866 Å.
  Pinned by three tests in `chisurf/plugins/chimol/test/test_transform_sync.py`,
  all on a *jiggled* copy — the existing tests use a rigid displacement, which no
  unit error can survive being visible in, because the fit removes it and the
  answer is 0.000 either way: `test_align_reports_angstrom` (against an
  independent Kabsch over the Angstrom atom array),
  `test_align_and_rms_agree_on_a_noisy_copy`, and
  `test_align_cutoff_is_in_angstrom` (no residue rejected at `cutoff=2.0`).
  Docs: the `align`/`super` section of `docs/guides/44_molecular_viewer.md` now
  states the units of `cutoff` and of the reported RMSD.

### RF-080
- **Status:** OPEN
- **Severity:** S2 (the outlier cutoff is compared in the wrong unit, so the documented default never applies)
- **Location:** `chisurf/plugins/chimol/chimol/cmd/measurements.py:682` (`new_mask = dists <= cutoff`) with `:447-451`/`:580-583` (`cutoff: float = 2.0`) and `:690-694` (the keep-half fallback)
- **Finding:** `dists` are distances between `get_residue_positions` outputs, i.e. **scene units**, but `cutoff` is PyMOL's parameter, defaulted and understood as 2.0 **Å**. At the shipped scale of 10 the default therefore rejects everything beyond **0.2 Å**, so on any genuinely non-identical pair the mask collapses, `np.sum(new_mask) < 3` fires, and the code silently substitutes "keep the best half" — a quantile the user never asked for. Verified on the 0.5 Å-noise copy above: `align mob, ref` reports "using **82/165** atoms", which is exactly `max(3, count // 2)` (the emergency branch), while `cutoff=100` — i.e. 10 Å — keeps 165/165. Scale the cutoff into scene units once before the loop, and emit a message when the fallback fires instead of silently changing what the cutoff means.
- **Fix note:**

### RF-081
- **Status:** OPEN
- **Severity:** S2 (renaming a scene onto an existing name destroys it and corrupts the order list)
- **Location:** `chisurf/plugins/chimol/chimol/renderer/scenes.py:275-284` (`rename`) with `:100-102` (`names`), `:262-273` (`delete`) and `:286-306` (`step`)
- **Finding:** `rename` never checks whether `new_name` is taken. `self._scenes[new_key] = scene` overwrites the existing scene, while `self._order[self._order.index(key)] = new_key` leaves the target's original entry in place — so `_order` holds the key twice and carries more entries than `_scenes`. Verified: storing `a` then `b` and calling `rename("b", "a")` returns `True`, after which `names()` reports `['a', 'a']` while `len(store)` is `1`; `delete("a")` then removes only the first occurrence, leaving an empty store whose `names()` still lists `'a'`. `step()` hands that ghost key on, and `SceneStore.recall` raises `KeyError` for it (the `scene` command's `if name not in store` guard converts that into a misleading "no scene named 'a'"). Refuse the rename when `new_key` is already stored and return `False` so `cmd.scene` reports it. `test_scenes.py` has no collision case.
- **Fix note:**

### RF-082
- **Status:** OPEN
- **Severity:** S2 (the camera is held across the rebuild only when the caller passes `view=0`, not when the scene has no view)
- **Location:** `chisurf/plugins/chimol/chimol/renderer/scenes.py:216-221` (`keep_view`, captured only `if "view" not in aspects`) with `:244-258` and `:147-151`
- **Finding:** `recall` restores representations, calls `viewer._update_view()`, then puts the view back **last**, because "the camera's offset is stored relative to the scene centre, and changing what is drawn moves that centre" (the module's own comment at `:249-252`). But `keep_view` is captured only when the caller *excludes* view. A scene stored with `view=0` — the colour-only or rep-only scene the module docstring advertises as the whole reason the flags exist — has `scene.view is None`, so recalling it with the command's default flags takes the `"view" in aspects` branch, `wanted` is `None`, and nothing is restored after the rebuild. Verified: with two objects 80 Å apart, `scene s1, store, view=0` then `disable mob` then `scene s1, recall` moves the camera state by **398.9**, while the same recall with an explicit `view=0` holds it to **0.0000** — the protection is present but unreachable for exactly the scenes it was written for. The same hole opens when `store` silently swallows a `get_view_state` failure at `:148-151`. Capture `keep_view` whenever no view will be restored: `if "view" not in aspects or scene.view is None`.
- **Fix note:**

### Review 2026-07-26 (7) — the project↔chinet session round trip, and the `to_dict` contract

Slice: commit `0f7e07e69` — `chisurf/core/project/project.py::_restore_chinet_session`,
`modules/chinet/chinet/session.py` (`Session.load`, the new `clear`),
`chisurf/core/curve.py::_set_axis`, and the `skip_qt_widgets` parameter the same
commit threaded through `Curve`/`ExperimentalData`/`DataCurve`. Everything below was
reproduced in the `arm64` env through the real `Project.save`/`Project.load` path.
What checks out: `Session.load` really is a classmethod and the old call discarded
its result, so the direction of the fix is right; `Session.clear` empties both
`nodes` and `_document["nodes"]`; `Curve.__init__`'s `float64` coercion removes the
object-dtype `None` array and the one-sided `x`/`y` fill is symmetric; the
`parameters_all_dict` switch in `fret_line.py` targets keys that really are absent
from `parameter_dict` for fixed model constants; `DataGroup.name`'s setter matches
its getter's `__dict__` lookup. Findings RF-083..RF-089.

### RF-083
- **Status:** OPEN
- **Severity:** S1 (opening a project detaches every live parameter port from the object registry; the next save persists pre-open values)
- **Location:** `chisurf/core/project/project.py:210-221` (`_restore_chinet_session`) via `modules/chinet/chinet/session.py:179` (`DB.clear()` inside `Session.load`), against `chisurf/core/parameter.py:661-667` (every `FittingParameter` owns a `chinet.Port`)
- **Finding:** `Session.load` wipes the process-global `DB` registry and re-registers *file copies* under the very same oids, so after a project is opened `DB.get(p._port.oid)` no longer returns the live port an open parameter reads and writes — it returns a detached duplicate frozen at the value stored in the archive. Verified end to end: a `Parameter(value=3.0)` saved to `probe.csp`, the project re-opened, then `p1.value = 42.0` — `DB.get(p1._port.oid).value` still reads `[3.]`, and the *next* `Project.save` writes `('alpha', [3.0])` into `session.jsonl` instead of `42.0`. `Session.save` serialises `DB.dump_all()`, so the persisted node graph silently records the state at the moment of the last open, and every object created before that open is dropped from the registry entirely. Either re-point the registry at the live objects after a restore, or scope `Session.load`'s `DB.clear()` to the session being built instead of the process-wide singleton.
- **Fix note:**

### RF-084
- **Status:** OPEN
- **Severity:** S2 (every restored object is registered twice, so each save after a load duplicates the graph in the file)
- **Location:** `modules/chinet/chinet/base.py:68` (`DB.register(self)` in `BaseObject.__init__`) with `:72-75` (the `oid` setter) and `:147-151` (`set_document`)
- **Finding:** `BaseObject.__init__` registers the new object under a freshly minted uuid; `Session.load` then rebinds that object's oid to the one read from the file (`n.oid = oid`, `set_document`) and re-registers it — but nothing removes the first key, so `DB._objects` ends up holding two keys per restored object, both pointing at the same instance. `DB.dump_all()` iterates keys, so the object's document is emitted twice. Verified: a session with one node and one port saves as 3 lines; after one load/save cycle the same graph saves as **5** lines (`{'node': 2, 'port': 2, 'session': 1}`) with the node and port documents byte-identical and duplicated, and `len(DB._objects)` is 6 for 3 objects. Cross-process it is worse — opening a project written elsewhere and saving leaves **two** `type: "session"` documents in the file, since the live session is no longer registered under the restored session's oid. Reload still works (pass 2 skips oids already in `id_map`, pass 1 takes the first session line), so this is bloat and confusion rather than loss. Drop the stale key in the `oid` setter / `set_document` (`DB.remove(old_oid)` before re-registering).
- **Fix note:**

### RF-085
- **Status:** OPEN
- **Severity:** S2 (the restored-node loop never executes — nothing ever puts a node into the process session)
- **Location:** `chisurf/core/project/project.py:217-219` (the `for name, node in restored.get_nodes().items()` loop) against `chisurf/core/models/__init__.py:81` (`self._node = cn.Node()`) and `chisurf/core/parameter.py:661-667`
- **Finding:** No code in `chisurf` ever calls `chinet.session.add_node` / `create_node` — model nodes and parameter ports are constructed standalone and reach the archive only because `BaseObject.__init__` registers them in the global `DB`. The session document therefore always saves with an empty node map, which the commit's own goal ("restore the chinet graph on project load") depends on. Verified through the real path: `session.jsonl` written by `Project.save` contains `session doc nodes: [{}]` plus loose `port` documents, and after `Project.load` `chinet.session.get_nodes()` is `[]` — the new loop body runs zero times. What the restore actually does is repopulate `DB` with detached copies (see RF-083). Either register model nodes in `chinet.session` at construction so the graph is real, or drop the session-node round trip and persist what is actually used.
- **Fix note:**

### RF-086
- **Status:** OPEN
- **Severity:** S1 (a length mismatch that used to raise now silently truncates the other axis and desynchronises `ex`/`ey`/`mask`)
- **Location:** `chisurf/core/curve.py:148-176` (`Curve._set_axis`, new in `0f7e07e69`) against `chisurf/core/data.py:232-243` (`DataCurve`'s `ex`/`ey`/`mask`), `:176-186` (the `data` property) and `:498` (`__getitem__`)
- **Finding:** Before this commit `curve.y = v` was `self.d[1] = v` and a wrong length raised `ValueError: could not broadcast`. `_set_axis` now rebuilds the 2×N storage instead, keeping `min(old, new)` samples of the *other* axis and zero-padding the rest — so assigning one axis silently rewrites the other, and on a `DataCurve` it leaves the error and mask arrays at the old length. Verified: a 10-point `DataCurve`, then `dc.y = np.ones(4)` → `dc.x` is silently truncated to `[0,1,2,3]` while `len(dc.ex) == len(dc.ey) == len(dc.mask) == 10`; `dc[:]` returns arrays of lengths `(4, 4, 10, 10, 10)`, `to_dict()` writes `x`/`y` of 4 against `ex`/`ey`/`mask` of 10 into the project file, and the `data` property raises `ValueError: all the input array dimensions … must match exactly` from its `np.vstack` — a curve that no longer describes a dataset, produced by an assignment that reports success. The intended case (filling an empty curve) is served by the `storage.size == 0` situation alone; restrict the rebuild to that, or resize the companion arrays too and raise on a genuine mismatch. `test/core/test_curve.py:28-32` only covers the empty-curve fill, so nothing catches this.
- **Fix note:**

### RF-087
- **Status:** OPEN
- **Severity:** S2 (the `to_dict` contract this commit repaired is still broken in two Base subclasses)
- **Location:** `chisurf/gui/widgets/general.py:750-755` (`Controller.to_dict`) and `:788-793` (`View.to_dict`)
- **Finding:** Both override `Base.to_dict` without the `skip_qt_widgets` parameter — exactly the defect `0f7e07e69` fixed in `Curve`, `ExperimentalData` and `DataCurve`, and these are the two classes for which the flag exists (they *are* `QWidget` subclasses). Verified offscreen: `Controller().to_dict(skip_qt_widgets=True)` and `View().to_dict(skip_qt_widgets=True)` both raise `TypeError: to_dict() got an unexpected keyword argument 'skip_qt_widgets'`, and so does `to_json(skip_qt_widgets=True)` — which is the path `Base.save(..., skip_qt_widgets=True)` takes for `json` and `yaml` (`chisurf/core/base.py:363-366`). Saving a controller or a plot view with widgets skipped is therefore impossible. Add the parameter and forward it, as the three core classes now do. A guardrail test asserting every `Base` subclass's `to_dict` accepts the full signature would stop the next one.
- **Fix note:**

### RF-088
- **Status:** OPEN
- **Severity:** S3 (`skip_qt_widgets` is silently ignored on the elementary-conversion path)
- **Location:** `chisurf/core/base.py:481-484` (`to_elementary(d)` with neither flag forwarded) against `:527-537` (`to_json`, which forwards both)
- **Finding:** `Base.to_dict` skips Qt objects only when they are *direct* attributes; the subsequent `to_elementary(d)` call drops both `skip_qt_widgets` and `remove_protected`, so a widget nested inside a list or dict survives the conversion. Verified: an object carrying `widgets = [QWidget()]` serialised with `to_dict(remove_protected=True, convert_values_to_elementary=True, skip_qt_widgets=True)` yields `['<PyQt5.QtWidgets.QWidget object at 0x…>']`, while the same value through `to_elementary(..., skip_qt_widgets=True)` yields `[None]`. The caller asked for a widget-free dictionary and got a memory address baked into the payload. Forward both arguments, as `to_json` already does.
- **Fix note:**

### RF-089
- **Status:** OPEN
- **Severity:** S2 (a damaged optional entry makes the whole project unopenable)
- **Location:** `chisurf/core/project/project.py:174-184` (`Project.load`'s `except (ImportError, AttributeError, KeyError)`) against `modules/chinet/chinet/session.py:164-176` (`Session.load`'s bare `except:` → `json.load`)
- **Finding:** The chinet session is optional — a missing entry (`KeyError`) and an empty file (`Session.load` returns `None`) are both tolerated, and the save side is wrapped in the same kind of guard. A *malformed* `session.jsonl` is not: `Session.load` falls back to `json.load` on the whole file and raises `json.JSONDecodeError`, which is a `ValueError` and escapes the guard. Verified by rewriting the `session.jsonl` entry of a valid `.csp` to `{not json at all`: `Project.load` raises `JSONDecodeError: Expecting property name enclosed in double quotes`, so the datasets and fits in `project.json` — all intact — become unreachable, over a graph that is empty in practice (RF-085). The same archive with an *empty* session entry loads fine. Catch `ValueError`/`OSError` there too and log the skipped restore.
- **Fix note:**

### GUI test 2026-07-26 — TTTR micro-time histogram (raw photons → fittable decay)

Workflow: [TTTR micro-time histogram](/usecases/tttr-microtime-histogram.md) —
`chisurf.plugins.tttr.microtime_histogram`, driven headlessly against
`test/data/tttr/BH/132/BH_SPC132.spc` (SPC-130, 183 657 photons) with the shipped
`BS` detector setup, both standalone and with a real `chisurf.gui.main.Main`
window booted. What checks out: the stream is split correctly into parallel
`[8, 3]` / perpendicular `[0]`, the stacked result is 2 × 4096 values totalling
135 967 counts, `_apply_setup_lut` and the polarization gating behave, and the
plot — once given room — carries a correct legend and a *Micro Time (ns)* axis.
Findings RF-090..RF-097.

### RF-090
- **Status:** OPEN
- **Severity:** S1 (the "Transfer to ChiSurf" button does nothing and reports nothing, in two plugins)
- **Location:** `chisurf/core/actions/project_actions.py:60` (`set_setup_params`, `setup = cs.cs.current_setup`), reached from `chisurf/plugins/tttr/microtime_histogram/wizard.py:820` and `chisurf/plugins/fluorescence_decay/irf_estimator/gui/tool.py:1058`
- **Finding:** The `setup.params.set` action reads `cs.cs.current_setup`, an attribute that exists on no main window — `grep` finds the name nowhere else in the tree except an unrelated `_current_setup_idx` and per-plugin locals. Verified both ways: standalone (`cs.cs is None`) it raises `AttributeError: 'NoneType' object has no attribute 'current_setup'`, and with `Main()` constructed and assigned to `cs.cs` it raises `AttributeError: 'Main' object has no attribute 'current_setup'. Did you mean: 'current_fit'?`. Because the dispatch happens inside a Qt slot the exception is swallowed to stderr, so clicking **Transfer to ChiSurf** after a successful compute yields no dialog, no dataset and no error — `chisurf.imported_datasets` goes 0 → 0 — and the following `dataset.add` never runs. The same three-dispatch sequence (`experiment.set` → `setup.params.set` → `dataset.add`) is the IRF estimator's hand-off, so that path is dead too. Either give the main window a `current_setup` property over the active reader or route the action through the reader the way `setup.select` does, and add a smoke test that dispatches the action.
- **Fix note:**

### RF-091
- **Status:** OPEN
- **Severity:** S2 (a preview action writes an unrequested file into the user's raw-data directory)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/wizard.py:1532-1539` (the "Auto-save the histogram" tail of `compute_microtime_histogram`) with `:957-1015` (`update_output_filename`, which defaults the path to the input file's directory)
- **Finding:** `compute_microtime_histogram` ends by calling `save_cumulative_histogram` on whatever is in the *Output* box, which defaults to the folder the TTTR file came from. The panel has a separate **Save** button, so pressing **Compute** to look at a decay silently persists it as well. Verified by copying the sample into a scratch folder and pressing **Compute** exactly once, never **Save**: `sample_A_green_(8,3)-(0).dat` appeared beside `sample_A.spc`. Driving the repo sample the same way dropped a stray `.dat` into `test/data/tttr/BH/132/`. Every parameter sweep (binning, timeshift, detector) leaves another differently-named file behind, since the proposed filename encodes the channels. Drop the auto-save, or default the path to a scratch/output directory and tell the user a file was written.
- **Fix note:**

### RF-092
- **Status:** OPEN
- **Severity:** S2 (a displayed physical width tracks the display setting, not the data)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/wizard.py:1159-1192` (`calculate_fwhm`), displayed at `:1329` as *FWHM (VV + 2G*VH)*
- **Finding:** `calculate_fwhm` takes the global `argmax` and walks out to the *first* bin at or below half-max on each side. On shot-noise counting data the nearest sub-half-max bin is a random dip a few channels from the peak, so the result measures the noise realisation rather than the pulse width — and coarser binning averages the noise away, letting the walk run further. Verified on one file, one detector, changing only *Binning*: 1 → **0.27 ns** (82 ch), 2 → **1.07 ns** (162 ch), 4 → **8.94 ns** (678 ch), 8 → **9.12 ns** (346 ch) — a 34× swing in a quantity that must be binning-invariant, shown to two decimals with no caveat. (At binning 4 the "FWHM" of 8.94 ns exceeds two thirds of the 13.5 ns window.) Estimate the half-max crossings from a smoothed or interpolated curve and search outward from a baseline-relative maximum, and pin it with a test that computes the width at two binnings and asserts they agree.
- **Fix note:**

### RF-093
- **Status:** OPEN
- **Severity:** S2 (two enabled input boxes are ignored, while the filename they drive claims otherwise)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/wizard.py:70-133` (`_get_interleaved_channels`) with `:531-532` (their only signal connections)
- **Finding:** The *Parallel* and *Perpendicular* channel line edits (`lineEdit_2` / `lineEdit`) are enabled and editable, but `_get_interleaved_channels` returns the detector-wizard page's channels first and only falls back to parsing the boxes when no setup supplies any — and a setup always does (`BS` ships and is auto-selected). Verified: with `green` selected the channels are `[8, 0, 3]`; setting the boxes to `0` and `8` leaves `_get_interleaved_channels()` at `[8, 0, 3]` and `parallel_channels` at `[8, 3]`. Their `textChanged` is wired only to `update_output_filename`, so the proposed output filename *does* change to encode channels the computation never uses, which is worse than doing nothing. Make them read-only while a setup drives them (they are already repopulated from it on every detector change), or add an explicit override that `_get_interleaved_channels` honours.
- **Fix note:**

### RF-094
- **Status:** OPEN
- **Severity:** S2 (the documented CLI entry point crashes on its primary argument)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/__main__.py:106` (`widget.listWidget_BID.add_file(str(bst_file))`) against `chisurf/gui/autoform/sections/path_list_section.py:316-330` (`add_paths` / `set_paths`)
- **Finding:** The BID lists were migrated from the hand-rolled `FileListWidget` to the unified `PathListWidget`, which has no `add_file`; the CLI's call site was not updated. Verified: `PathListWidget` exposes `add_paths`, `set_paths`, `paths`, `checked_paths`, `selected_paths` and no `add_file`, and calling it raises `AttributeError: 'PathListWidget' object has no attribute 'add_file'`. So `microtime-histogram --bid-folder …` — the entry point the plugin README documents, and the same hand-off NDXplorer uses after saving burst IDs — fails for every `.bst` it finds, inside a `QTimer.singleShot` slot where the traceback goes to stderr and the window is simply left empty. One `add_paths([str(f) for f in bst_files])` call replaces the loop. (The README additionally names the command `csc_microtime_histogram` while the manifest registers `microtime-histogram`.)
- **Fix note:**

### RF-095
- **Status:** OPEN
- **Severity:** S2 (the house VV/VH writer is bypassed, so the saved decay carries no G-factor, layout or version)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/wizard.py:752` (`np.savetxt(str(path_obj), self.cumulative_ps.astype(int), fmt="%d")`) against `chisurf/core/fio/vv_vh.py:51-66` (`write_vv_vh`) and [the VV/VH format](/references/vv-vh-decay-format.md)
- **Finding:** `save_cumulative_histogram` hand-rolls the write instead of calling the canonical `write_vv_vh`, so the output is a bare column of 8192 integers with no `#`-footer. Verified: setting *G-Factor* to 1.25 and saving produced a file whose lines are all bare counts and which contains the string "1.25" nowhere, while `write_vv_vh(..., g_factor=1.25)` on the same shape emits `#format_version: 1.0`, `#channels: VV, VH` and `#g_factor: 1.25`. Nothing in the saved file records the G-factor the user typed in this very panel, the `dt`, or the fact that it is two stacked 4096-bin channels rather than one 8192-bin decay — so the file cannot be re-read without the operator remembering the settings, and the value is lost for anisotropy work downstream. Call `write_vv_vh(path, vv=..., vh=..., g_factor=self.g_factor, metadata={"dt": self.time_step})`. Note that `write_vv_vh` itself currently doubles the comment marker (`# #g_factor: 1.25`), because a `#`-prefixed footer is passed to `numpy.savetxt`, which prefixes it again — worth fixing in the same pass.
- **Fix note:**

### RF-096
- **Status:** OPEN
- **Severity:** S3 (the tool's only output is a 93-pixel sliver at every window size)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/wizard.ui` (`QSplitter` named `splitter`, no `stretch`/`sizes` property) with `wizard.py:515-519` (the plot added to `verticalLayout` on the right pane)
- **Finding:** The `Histogram` tab is a two-pane splitter whose stretch factors and initial sizes are never set, so Qt sizes it from size hints and the form pane wins outright. Verified offscreen: `splitter.sizes()` is `[899, 93]` at 1000 px of window width, `[1179, 93]` at 1280, `[1499, 93]` at 1600 and `[2099, 93]` at 2200 — the plot is pinned at **exactly 93 px** and every additional pixel goes to the form, so enlarging the window makes the plot relatively worse. At that width the x axis degenerates to a "5 10" tick pair, the axis label clips from "Micro Time (ns)" to "Micro Time", and the legend the code explicitly creates is entirely off-screen; two mostly-empty file-drop lists meanwhile hold ~570 px of height. A single `setSizes`/`setStretchFactor` call in `__init__` restores the readable plot (verified: `setSizes([700, 900])` yields the full labelled decay with its three-entry legend).
- **Fix note:**

### RF-097
- **Status:** OPEN
- **Severity:** S3 (a no-op action leaves the previous result on screen as though it were fresh)
- **Location:** `chisurf/plugins/tttr/microtime_histogram/wizard.py:1362` (`compute_microtime_histogram`, which has no empty-`selected_files` guard) against `:790-792` and `:849-852`, where `add_to_chisurf` and `open_save_dialog` both do warn
- **Finding:** **Compute** with no files ticked logs "Computing microtime histogram…", iterates an empty list and returns, without clearing the plot, the FWHM box or `original_histograms`. Verified: after computing a decay, clearing the file list and pressing **Compute** again, the previous curves stay drawn and the FWHM box still reads `0.27 ns (82.0 channels)` — no dialog, no status line, nothing disabled. Pressing it on a freshly opened tool is equally silent. A user who swaps datasets and re-computes cannot distinguish a stale result from a new one. The sibling actions in the same class already raise a "No Files" warning; do the same here (and clear the display) before the loop.
- **Fix note:**

### Review 2026-07-26 (8) — the in-tree graph layer and the MCMC diagnostics

Slice: the two newest algorithm landings — `1d4634cf6`
(`modules/chinet/chinet/graph/`, the containers/algorithms/layouts/GraphML that
replaced the external graph library) and `fad49246f`
(`chisurf/core/fitting/diagnostics.py`). Everything below was reproduced in the
`arm64` env.

What checks out, and is worth not re-reviewing: over **800 random directed graphs**
(1–7 nodes, three densities, self-loops in 30 %) `simple_cycles`, `topological_sort`,
`is_directed_acyclic_graph`, `connected_components`, `maximum_spanning_tree` weight
and weighted all-pairs `shortest_path_length` agree with the reference
implementation **exactly, 0 mismatches**. Self-loop bookkeeping matches too
(`degree`, `number_of_edges`, `copy`, `subgraph`, directed in/out-degree). The
spectral layout collapsing each component to a point on a disconnected graph is an
inherent property of the method and is bit-for-bit what the old library did — not a
regression. In `diagnostics.py` the ESS estimator recovers the AR(1)
autocorrelation time correctly (φ=0.5 → 2.95 vs 3.00; φ=0.9 → 19.36 vs 19.00 over
4×20000 draws), and the Geyer initial-positive-and-monotone truncation, the
Gelman–Rubin pooled variance and the Blom rank transform are all the standard
forms. Findings RF-098..RF-102.

### RF-098
- **Status:** OPEN
- **Severity:** S2 (a GraphML file written for a graph with graph-level attributes is rejected outright by conforming readers, and those attributes are lost on every round trip)
- **Location:** `modules/chinet/chinet/graph/graphml.py:131-135` (`write_graphml`, the `graph.graph` loop) and `:236-245` (`read_graphml`, which handles only `node` and `edge` children)
- **Finding:** Graph-level attributes are emitted as `<data key="title">` — the *attribute name*, not a `<key>` id — and no `<key for="graph">` element is ever declared, while node and edge attributes correctly go through `key_ids`. GraphML requires `data/@key` to refer to a declared `<key>`, so the document is invalid. Verified: `Graph(title="run 7", threshold=0.5)` with one weighted edge writes `<data key="title">run 7</data>` under a keys block declaring only `d0` for the edge weight, and the reference GraphML reader refuses **the whole file** with `NetworkXError: Bad GraphML data: no key title` — the nodes and edges are lost with it. The reverse direction fails silently: `read_graphml` iterates only `node`/`edge` tags, so a well-formed third-party file's graph-level `<data>` is dropped and `.graph` comes back `{}` (checked against a reference-written file that declares `d0`/`d1` `for="graph"`). Both contradict the module docstring's "opens in yEd, Gephi or Cytoscape unchanged, and a file written by those opens here". Declare graph-scope keys in `key_ids` alongside node/edge, and read graph-level `<data>` in `read_graphml`. Neither direction is covered — `test_chinet_graph.py`'s four GraphML tests all use graphs with an empty `.graph`.
- **Fix note:**

### RF-099
- **Status:** FIXED
- **Severity:** S1 (a parameter the sampler never moved is reported as the best-converged one in the table, with no warning — or as the worst, decided by floating-point luck)
- **Location:** `chisurf/core/fitting/diagnostics.py:157-160` (the `not (within > 0.0)` guard in `_ess_1d`) against `:114-124` (`autocovariance`, FFT-based)
- **Finding:** The guard meant to catch a constant parameter is unreachable for a real constant chain: `autocovariance` centres with `x - x.mean()` and transforms through the FFT, so lag 0 comes back as a rounding residual (~1e-31) rather than `0.0`, and the entire ESS/τ/MCSE machinery then runs on that noise. Verified on `np.full((4, 2000), v)` — a parameter that is *bit-identical in all 8000 draws*: `v = 1.234`, `0.001`, `3.7` → `ess = 4.0`, `tau = 1998`; `v = 0.0`, `1.0`, `0.5`, `2.5` → the residual happens to be exactly `0.0`, the guard fires, and `ess = 8000`, `tau = 1.0`, `mcse ≈ 0`, `rhat = 1.0`, **`convergence_warnings` returns `[]`**. Identical situations, opposite verdicts, decided only by whether the constant is binary-exact — and the silent branch is the one a parameter pinned at a bound of `0.0` takes. This is on the live path: `sample_fit` → `_write_sampling_diagnostics` (`chisurf/core/fitting/fit.py:2166-2167`) writes it to `diagnostics.json` and logs the warnings. Test the *range* (`np.ptp(block) == 0.0`, as `rank_normalized_rhat:361` and `bulk_tail_ess:399` already do) instead of a floating-point variance, and report a frozen parameter as such rather than as either extreme.
- **Fix note:** `_ess_1d` now tests the *range* (`np.ptp(chains) == 0.0`) before it
  touches the FFT autocovariance, and returns `nan` for a frozen parameter — the
  same refusal `rank_normalized_rhat` and `bulk_tail_ess` already give the same
  input, so `tau` and `mcse` follow. The old variance guard is kept only as an
  underflow net and now returns `nan` too. Because a frozen parameter has a
  perfectly comfortable `rhat = 1.0`, `summarize` gained a `frozen` flag and
  `convergence_warnings` a line that names it, so the case that used to pass in
  silence is now stated; `suggest_burn_in` and `PosteriorEngine`'s `converged`
  test both improve for free (a frozen parameter no longer inflates the burn-in
  nor counts as a converged marginal). Pinned by
  `test/fitting/test_mcmc_diagnostics.py::test_a_frozen_parameter_gets_one_verdict_whatever_its_value`,
  parametrised over the binary-exact constants (`0.0`, `1.0`, `0.5`, `2.5`) and
  the ones that leave an FFT residual (`1.234`, `0.001`, `3.7`) — pre-fix those
  two groups gave `ess = 8000, no warning` and `ess = 4.0, low-ESS warning` —
  plus `test_a_moving_parameter_is_not_reported_as_frozen` for the converse.

### RF-100
- **Status:** FIXED
- **Severity:** S1 (one non-finite draw makes `summarize` report the full draw count as the effective sample size)
- **Location:** `chisurf/core/fitting/diagnostics.py:157-160` (`_ess_1d` falls through to `return total` whenever `within` is not `> 0.0`, which includes `nan`) with `:472-477` (`mcse`) and `:556` (`summarize`)
- **Finding:** A single `nan`/`inf` draw makes `autocovariance` return all-`nan`, so `within` is `nan`, `not (nan > 0.0)` is `True`, and the function returns `total` — the *raw* draw count, the value reserved for "a constant parameter carries no information". Verified on 4×1000 draws with one element set to `nan`: `summarize` reports `ess = 4000.0` and `tau = 1.0` (i.e. perfectly independent draws) beside `rhat = nan`, `ess_bulk = nan`, `ess_tail = nan` and `mcse = nan`; `+inf` behaves the same. Every companion statistic correctly refuses to answer while the headline ESS reads as the best possible value, and `mean`/`sd` are quietly computed over the finite subset only (`summarize:571`), so the row describes three different samples at once. `rank_normalized_rhat:358` and `bulk_tail_ess:399` already gate on `np.all(np.isfinite(block))`; `_ess_1d` should do the same and return `nan`.
- **Fix note:** `_ess_1d` now gates on `np.all(np.isfinite(chains))` before any
  autocovariance is computed and returns `nan` — the same refusal its companions
  give — so a contaminated parameter no longer reports the raw draw count as its
  effective sample size (it also stops the FFT emitting `RuntimeWarning`s on that
  input). `autocorrelation_time` and `mcse` propagate that `nan` instead of
  folding it into their `ess <= 0` branch, which means `inf`: "infinitely
  correlated" / "the mean is pure noise" are claims about a *known* chain, not
  about an unknown one. `summarize` therefore reports `ess`/`tau`/`mcse` as `nan`
  beside the already-`nan` `rhat`/`ess_bulk`/`ess_tail`, and
  `convergence_warnings` still excludes the parameter from the low-ESS lists
  (both already gate on `np.isfinite`). The constant-parameter branch (RF-099) is
  untouched. Pinned by
  `test/fitting/test_mcmc_diagnostics.py::test_a_non_finite_draw_leaves_the_sample_size_undefined_not_maximal`,
  parametrised over `nan`, `+inf` and `-inf`, which also asserts the clean chain
  still gets a finite ESS. Docs: the estimator's contract is now stated in
  [subsystems/fitting.md](/subsystems/fitting.md).

### RF-101
- **Status:** OPEN
- **Severity:** S2 (three unrelated conditions are all reported to the user as "never moved or disagree completely between chains")
- **Location:** `chisurf/core/fitting/diagnostics.py:659-664` (`convergence_warnings`, `stuck = [... not np.isfinite(e["rhat"])]`) against `:358-363` (`rank_normalized_rhat`, which returns `nan` for two different reasons and `inf` for a third)
- **Finding:** The message is keyed off `rhat` merely being non-finite, but `rank_normalized_rhat` returns `nan` for a chain that is too short (`block.shape[1] < 2`), `nan` for a chain containing any non-finite draw, `nan` for a single chain of fewer than four draws (via `np.var(..., ddof=1)` on one element), and `inf` only for the genuinely stuck case. Verified — all four produce the identical line `1 parameter(s) never moved or disagree completely between chains (e.g. p)`: a 4×1 chain, a 4×1000 chain with one `nan`, a 1×3 chain, and four constant chains at different values. Only the last is what the text describes; for the `nan`-draw case (RF-100) it actively points the reader at the wrong diagnosis, and **no** message anywhere reports that the chain contains non-finite draws. Separate the cases and say which one fired.
- **Fix note:**

### RF-102
- **Status:** OPEN
- **Severity:** S3 (`rank_normalized_rhat` reports an unsplit statistic as a split one, and leaks numpy RuntimeWarnings)
- **Location:** `chisurf/core/fitting/diagnostics.py:307-311` (`_split` returns the chains untouched when `n // 2 < 2`) with `:357-368` (`rank_normalized_rhat`) against `:431-433` (`split_rhat`, which returns `nan` instead)
- **Finding:** For two or three draws per chain `_split` silently declines to split, and `rank_normalized_rhat` proceeds anyway — so `summarize` publishes a `rhat` that was never split under a docstring promising "``nan`` when the chains are too short" and a warning string that calls it "rank-normalised split R-hat". Verified: `m=2, n=2` → `rank_normalized_rhat` `1.932` while `split_rhat` is `nan`; `m=2, n=3` → `1.067` vs `nan`. Separately, `m=1` with `n < 4` reaches `_rhat_1d` with a single chain mean, so `np.var(means, ddof=1)` leaks `RuntimeWarning: Degrees of freedom <= 0 for slice` and `invalid value encountered in scalar divide` out of a diagnostics call before returning `nan`. Return `nan` when `_split` could not split (as `split_rhat` does), and guard the one-chain case rather than letting numpy warn.
- **Fix note:**

### Review 2026-07-26 (9) — the What-if conditional sweep

Slice: `ab913c34e`, the newest landing — `GaussianEngine.conditional_scan`
(`chisurf/core/fitting/engine.py:761-849`), its widget
`chisurf/gui/plots/conditional_scan.py`, and the guide section it added.
Reproduced in the `arm64` env, offscreen, on the guide's own parabola fit.

What checks out, and is worth not re-reviewing: **the algebra is exact.** Against
an independent Schur-complement reference computed from `form.covariance` — the
conditional of the *full joint* given one variable, not a pairwise shortcut —
the swept means agree to `2.2e-16` at every point and the conditional widths to
`4.4e-16`; the per-target `sd = σ_j√(1−ρ²)` is precisely the diagonal of that
Schur complement, so reporting it as a scalar independent of the held value is
right, not an approximation. `held`/`held_z` span what the axis label claims, the
targets come back in the form's own order, the 23 tests in
`test/fitting/test_canonical_form.py` pass, and the marker really does move
rather than accumulate (41 slider steps leave the plot item count at 4). The
`np.clip(rho, -1, 1)` is unreachable defence, not a silent repair:
`CanonicalForm.from_moments` Choleskys the covariance and `form()` catches the
resulting `LinAlgError`, so an indefinite curvature never reaches the sweep.
Findings RF-103..RF-106; the two that matter are in the widget and in the
evidence contract, not in the math.

### RF-103
- **Status:** OPEN
- **Severity:** S1 (fixing parameters leaves a full, confident-looking what-if analysis on screen that describes the *previous* posterior; the "not usable" message it was supposed to show is overwritten in the same call)
- **Location:** `chisurf/gui/plots/conditional_scan.py:100-120` (the `len(form.names) < 2` branch, whose `self.parameter_box.clear()` at `:106` is **not** inside the `blockSignals` pair at `:112-119`) with `:122-132` (`_rebuild`, which then runs on the stale `self._engine` / `self._full_names`)
- **Finding:** `update()` writes "needs a converged fit with at least two free parameters", clears the plot, and *then* clears the combo box outside the signal block. That emits `currentIndexChanged`, which is connected to `_rebuild`; `_full_names` and `_engine` still hold the previous update's values, `currentIndex()` is now `-1` and `max(0, -1)` turns it into `0`, so the widget immediately re-runs the sweep on the **old** engine and redraws. Verified offscreen on the guide's `c+a*x+b*x**2` fit: after `a` and `b` are fixed (leaving one free parameter), the panel is pixel-for-pixel the earlier one — title "Fixing c — what the rest become", both curves, and a table quoting `a = 2.07759 ± 0.00804`, `b = 0.476323 ± 0.00495`, "90% narrower" — for two parameters that are no longer free at all, while the *Fix* combo is visibly empty; `w._scan is None` is `False` and the intended message never survives the call. The same stale state is reachable through the `except` branch at `:95-99`, which does not clear the combo at all, so switching parameter there also draws from the dead engine. Clear `_scan`/`_full_names`/`_engine` (and block signals around the `clear()`) before returning. There is no widget test for this plot at all — a two-line construct-update-degrade test would pin it.
- **Fix note:**

### RF-104
- **Status:** OPEN
- **Severity:** S2 (the whole point of the design is that the answer is free; opening the tab once makes every later `fit.update()` pay a full numerical Hessian, forever, even while another tab is showing)
- **Location:** `chisurf/gui/plots/conditional_scan.py:89-93` (`update()` unconditionally builds `GaussianEngine(...).add_all_targets().run()`), reached from `chisurf/gui/widgets/models/model_widget.py:47-49` (`update_plots` loops **every** created plot) via `chisurf/gui/widgets/fitting/fit_subwindow.py:198` (`fit.plots = self._created_plots`)
- **Finding:** Plots are created lazily per tab, but once created they stay in `fit.plots` and `ModelWidget.update()` calls `update()` on all of them with no visibility test — so `ConditionalScanPlot` re-evaluates the curvature on every `fit.update()`, hidden or not. Verified by counting `model.update_model` calls across one `plot.update()`: **4 model evaluations** for a 3-free-parameter model (n+1, the forward-difference Jacobian), plus the matrix inverse; for a global TCSPC fit with 30 free parameters that is 31 full convolutions per model update, spent on a tab nobody is looking at. Contrast the sibling plots that already guard: `chisurf/gui/plots/deer_pr.py:46` and `chisurf/gui/plots/table_plot.py:340` both start with `if not self.isVisible(): return`. Add the same early-out (the visible-tab path, `fit_subwindow.refresh_current_plot`, already calls `update()` when the tab is shown, so nothing is lost). `PosteriorGraphPlot` has the identical exposure and is worth the same guard.
- **Fix note:**

### RF-105
- **Status:** OPEN
- **Severity:** S2 (a parameter the caller pinned with `condition()` is reported by the sweep as a free target, with a width and a value that moves — the same engine answers the same question two different ways)
- **Location:** `chisurf/core/fitting/engine.py:805` (`conditional_scan` starts from `self.form()`, the *unconditioned* cached form) against `:683-685` (`GaussianEngine.run`, which does apply `self._evidence` — but to a local variable, never back to `self._form`); `conditional` at `:740` has the same gap
- **Finding:** `PosteriorEngine.condition(name, value)` is the engine's evidence API, and `run()` honours it — the held parameter correctly comes back as an empty `Marginal`. `conditional_scan` does not: it reads the cached form, which `form()` built before the conditioning, so the sweep is taken in a posterior where the held parameter is still free *and lists it as one of the targets*. Verified on the guide's fit: after `eng.condition('1:a', 5.0); eng.run()`, `eng.marginal('1:a')` is `value=nan, sd=nan, method='none'` (correctly "held, no marginal of its own"), yet `eng.conditional_scan('1:c')` returns `1:a` as a target with `sd = 0.00804` and a mean sweeping around `2.0776` — the old optimum, not the 5.0 it was pinned at. `eng.conditional({})` on the same engine likewise returns all three unconditioned means. Nothing warns. Apply `self._evidence` in one shared helper that `run`, `conditional` and `conditional_scan` all start from, and drop held parameters from `targets`.
- **Fix note:**

### RF-106
- **Status:** OPEN
- **Severity:** S3 (the guide's headless recipe cannot run as printed — it returns `None` and the next line raises)
- **Location:** `docs/guides/39_parameter_uncertainty.md:296-297` (`scan = eng.conditional_scan('tau1', points=61, span=3.0)` followed by `for t in scan['targets']`) against `chisurf/core/fitting/engine.py:805-807` (`if form is None or name not in form.names: return None`)
- **Finding:** The engine's scope is `posterior_model(fit).parameter_names`, which for a `FitGroup` — the object the same guide builds at line 24, and what the GUI always holds — is prefixed with the member index. Verified: `eng.form().names` is `('1:c', '1:a', '1:b')`, and `eng.conditional_scan('a')` returns `None`, so the loop under it dies with `TypeError: 'NoneType' object is not subscriptable`. The name in the snippet is also `'tau1'`, which belongs to a lifetime model and not to the `c+a*x+b*x**2` fit the section is running. OKF already states the rule ([subsystems/fitting](/subsystems/fitting.md): "group names are prefixed (`3:tau`)"); the guide neither states it nor obeys it. Use a name taken from `eng.form().names` in the example and say in one clause that the sweep is keyed by the form's own (prefixed) names.
- **Fix note:**

### GUI walk 2026-07-26 (FCS correlator) — raw TTTR to a correlation curve

Use case: [FCS correlation from raw TTTR](/usecases/fcs-correlate-tttr.md). The
unified **FCS** tool (`chisurf/plugins/fcs/fcs_toolbox`) driven offscreen in the
`arm64` env against a scratch copy of `test/data/tttr/BH/132/BH_SPC132.spc`
(183 657 photons, 62.3 s, channels 0/1/8/9), with `QMessageBox` intercepted:
channel definitions → files → correlate → merge → save → *Add to ChiSurf*.

The happy path holds — `Correlate` on an empty tool refuses correctly, four
chunks correlate in about a second, the merger picks them up automatically and
`Add to ChiSurf` produces a 180-point FCS dataset. The **Fine** (micro-time)
correlation is also fine: 181 points from 3.3 ps to 0.031 ms, all finite. The
findings below are the things that break or mislead on the way. RF-107..RF-112.

### RF-107
- **Status:** OPEN
- **Severity:** S1 (step 1 of the correlator workflow feeds nothing to step 4; naming detectors becomes unreachable and a blank channel field silently correlates every routing channel against itself)
- **Location:** `chisurf/plugins/fcs/fcs_correlator/tool.py:535-543` (`_channel_def_context`) and `:246-250` (`_bind_channel_def_panel`), against `chisurf/plugins/fcs/fcs_channel_preset/gui/tool.py:66-86` (`FCSChannelWidget`, the AutoForm port) and `.../gui/view_model.py:42-110`
- **Finding:** `_channel_def_context` still reads `widget.setup_combo.currentText()`, `widget._detector_setups` and `widget._channels_for_setup`. The AutoForm port moved all three onto `widget.model` (`current_setup`, `_detector_setups`, `_channel_names`), so the lookups fail inside their own `try`/`getattr` defaults and the function returns `('', {}, {})` — for a panel that is at that moment reporting setup `BS` with channels `['green', 'red', 'yellow']`. Verified offscreen: after visiting step 1, `tool._channel_def_context(chdef)` → `('', {}, {})` and `workflow_context.detector_settings` → `{'setup_name': '', 'detectors': {}, 'tttr_reading': {}}`. Downstream, `load_fcs_presets('', {})` finds no block **and** skips the `_default_pairs_from_detectors` fallback (guarded on `detectors`), so `_fcs_presets == []` → the *FCS Preset* combo is permanently empty; `model._channel_defs` stays `{}` → `_ChannelComboWidget.refresh` fills the *A:* / *B:* combos with `[]`. The user's only remaining input is raw routing numbers in `Ch A`/`Ch B`, and if those are left blank `correlate_data` (`correlator_panel.py:249-254`) falls back to *all* used routing channels for both sides with nothing said in the UI — verified: a correlation ran over `[0, 1, 8, 9] × [0, 1, 8, 9]`. `_bind_channel_def_panel` fails the same way (`widget.setup_combo.currentIndexChanged` inside a bare `except: pass`), so `_on_channel_setup_changed` never fires and switching setup does not invalidate the stale filter selection it exists to drop. Read the three values off `widget.model`; the docstring at `:530-533` already describes the intended contract.
- **Fix note:**

### RF-108
- **Status:** OPEN
- **Severity:** S2 (the last point of every exported correlation curve is a zero with a zero error, which the reader turns into a divide-by-zero on the way back in)
- **Location:** `chisurf/plugins/fcs/fcs_correlator/correlator_panel.py:386-394` (`_correlate_one`: the `y[x > dur] = 1.0` guard covers lags past the chunk duration but not the empty terminal multi-tau bin) with `chisurf/core/fio/fluorescence/fcs/kristine.py:110-116` (`w = 1./data[:, 3][i]`, no zero guard)
- **Finding:** Every chunk comes back with `G = 0` at the first lag (`x = 0.0`, undrawable on the log axis) and `G = 0` at the last lag. The `x = 0` point is filtered out downstream (`kristine.py:100`, `x > 0`), but the terminal zero is not: verified on 4 chunks of `BH_SPC132.spc`, per-chunk `y` has zeros at indices `[0, 180]`, the merged curve keeps `y[-1] = 0.0` **and** `ey[-1] = 0.0`, and that row is written into the `.cor`. Pressing **Add to ChiSurf** immediately re-reads it and raises `RuntimeWarning: divide by zero encountered in divide` at `kristine.py:112`; the loaded dataset ends `y[-3:] = [1.0914, 1.0825, 0.0]`. Both plots show it as a vertical dive to zero at the right edge. Two independent fixes: flatten/drop the empty terminal bin in `_correlate_one` the way the beyond-duration lags already are, and guard the `1/ey` in the Kristine reader so a zero error becomes a zero weight (masked point) rather than `inf`.
- **Fix note:**

### RF-109
- **Status:** OPEN
- **Severity:** S2 (in every navigation-panel window the user cannot read the name of the step or tool they are currently on)
- **Location:** `chisurf/gui/widgets/navigation.py:438-454` (the `nav_list` stylesheet: `QListWidget::item` is styled but there is no `::item:selected` rule)
- **Finding:** Styling `::item` without a `:selected` rule makes Qt paint the selected row's label in `HighlightedText` while the stylesheet suppresses the `Highlight` background — on this palette that is `#ffffff` text on a white row. Verified by pixel histogram of each row's `visualItemRect`: in the FCS tool the selected row (`'📂 2. Files & Steps'`) contains **no** `#000000` pixels, against 162, 97 and 162 for its unselected neighbours; the row renders as its emoji and nothing else. Reproduced identically in a second, unrelated tool — the TTTR Toolbox's selected `'🏷️ TTTR Header Editor'` row is likewise blank next to its icon (`nav_tttr.png`) — so this is the shared shell, and it affects the FCS, Burst Analysis, Decay Analysis, Imaging Tools and Converter windows alike. Disabled rows are unaffected (they use the disabled text colour), which is why the greyed-out steps stay readable while the active one does not. Add an explicit `QListWidget::item:selected { background: …; color: …; }` pair.
- **Fix note:**

### RF-110
- **Status:** OPEN
- **Severity:** S2 (the two navigation buttons walk the user into steps the same window has explicitly greyed out, and that step then does real work that is thrown away)
- **Location:** `chisurf/gui/widgets/navigation.py:676-692` (`goto_next_step` / `goto_prev_step` skip rows flagged `separator` but never test `ItemIsEnabled`) against `chisurf/plugins/fcs/fcs_correlator/tool.py:230-259` (`_set_nav_enabled` / `_update_step_nav_state`, which disable optional steps)
- **Finding:** `FcsCorrelatorTool` disables the **3. Photon / Burst Filter** and **5. FCS Merger** rows when their *Steps:* checkbox is off — the rail greys them out and they cannot be clicked. **Next ▶** and **◀ Back** ignore that: verified with the filter unticked, `Next` from row 2 lands on row 3 with `enabled=False`, and `Back` from row 4 returns to it. The panel is not merely displayed, it is fully live — it read the file, ran with `Mode=burst, enable=✓` and reported `96 774 / 183 657 photons kept (52.7 %)` — while `workflow_context.use_photon_filter` is `False`, so `_apply_context_to_correlator` correlates the raw stream and every one of those decisions is silently discarded. Skip disabled (and separator) rows when stepping, as the click path already does.
- **Fix note:**

### RF-111
- **Status:** OPEN
- **Severity:** S2 (a Save button with no dialog, no feedback and no undo, writing an implementation-named file into the user's data folder)
- **Location:** `chisurf/plugins/fcs/fcs_correlator/merger_panel.py:128-142` (`target_filepath` / `save_mean`) with `chisurf/plugins/fcs/fcs_correlator/correlator_panel.py:96` (`_output_subdir = pathlib.Path("cr5")`)
- **Finding:** **Save Merged** calls `save_mean(None)`, which derives the path from `folder_path` — set by the tool to `<analysis folder>/cr5`, the correlator's internal output-subdirectory constant — and writes `<data folder>/cr5.cor`. Verified: with the TTTR file in a scratch folder, pressing the button produced `…/data2/cr5.cor` with **no** file dialog, **no** confirmation, **no** status text and nothing in the log; `DIALOGS` was empty and the only way to learn the path was to read it off the model. Two consequences: the output is named after an implementation detail rather than the measurement (every dataset in every folder becomes `cr5.cor`), and a second run overwrites the first without a word. The sibling **Add to ChiSurf** does warn ("No Correlation File") on the failure path, so the pattern exists. Offer the path (a save dialog defaulting to the TTTR stem), or at minimum report the written path in the status line.
- **Fix note:**

### RF-112
- **Status:** OPEN
- **Severity:** S2 (opening the Filter Calc panel raises during its own plot reset; the exception is swallowed and reported as a computation error, leaving the panel's plots empty)
- **Location:** `chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/main_window.py:1430` (`_clear_recon_plot`, `self.plot_recon.addItem(region)`) reached from `:3146` (`_update_plots`) inside the `try` at `:2670` (`_compute_filters_multi_detector`)
- **Finding:** `region` is a chiplot `_Region`; `plot_recon` falls through to the pyqtgraph backend (the call already emits `ChiplotPassthroughWarning: chiplot has no native 'addItem' (Plot scope)`), and `QGraphicsScene.addItem` rejects it: `TypeError: addItem(self, item: Optional[QGraphicsItem]): argument 2 has unexpected type '_Region'`. Verified by walking the FCS tool's navigation rail — selecting **Filter Calc** produces the traceback, logged at ERROR as `Multi-detector computation error: addItem(...)`, so the user sees empty plots and no error. A chiplot migration gap of exactly the kind the passthrough warning is meant to flag: either give chiplot a native `addItem`/region API on the `Plot` scope, or add the region through the chiplot handle rather than the raw `PlotItem`. (Noted separately, not filed: the panel then sat at 0 % CPU for over three minutes without completing and the walk had to be killed there — not characterised, so not claimed as a defect.)
- **Fix note:**

### Review 2026-07-26 — the server fit-job path, end to end

Slice: `e46b80fe4` (INC-08, one job manager for sampling and parameter scans) and
the two GUI consumers it feeds — `chisurf/server/jobs.py`,
`chisurf/server/services/fits.py:1072-1546`,
`chisurf/gui/widgets/fitting/fit_controller.py:_watch_sampling_job` and
`chisurf/gui/plots/parameter_scan/parameter_scan.py`.

The refactor itself holds: the id-space split by action is real, the cooperative
`CANCELLING` state is honest about a worker that is still walking the live model,
`cleanup()` prunes, and the cancel path does hand the borrowed parameter back.
The findings are on either side of it — what the worker does when it *fails*
rather than when it is cancelled, what happens when two jobs drive the same live
fit, and what the two pollers make of a response that is not a job status.
Reproduced in the `arm64` env against the service functions directly (the fakes
from `test/server/test_fit_jobs_use_job_manager.py`). RF-113..RF-119.

### RF-113
- **Status:** FIXED
- **Severity:** S1 (a scan that raises leaves the user's fit sitting at an arbitrary probe value, silently, and the model is re-evaluated there)
- **Location:** `chisurf/server/services/fits.py:1477-1498` (`fit_parameter_scan_start._run`: the restore at `:1497-1498` is reachable only by falling off the end of the loop) against `:1478-1483` (the cancel checkpoint, which *does* restore)
- **Finding:** The scan borrows the live parameter (`param.value = float(v)`; `model.update_model()`) and owes it back. Cancellation pays that debt — the comment at `:1479-1480` says so — but an exception does not: `update_model()` raising on step *k* propagates straight out of `_run`, `_execute_job` records FAILED, and `param.value` keeps the probe value forever. Verified with the test file's own fakes: a model that raises on its 4th update leaves `parameters_all_dict['a'].value == 1.6` for a parameter that started at `2.0`, with the job reporting only `status='failed', error='model blew up'`. A raising `update_model` is not exotic — it is the normal outcome of a probe value outside the model's domain, which a scan deliberately walks towards. `test_a_failing_scan_is_reported_as_failed` already drives this path and asserts only the status, so the corruption is uncovered. Wrap the loop in `try/finally` so the single restore serves the normal, cancelled and failed exits alike, and extend that test with the value assertion the cancel test already makes.
- **Fix note:** The scan loop in `_run` is now wrapped in `try`/`finally` and the
  restore lives in the `finally`, so the one restore serves the normal,
  cancelled and failed exits alike — the cancel checkpoint just returns and the
  duplicated restore it carried is gone. The assignment (`param.value = value`)
  precedes the re-evaluation (`model.update_model()`), so the parameter is put
  back even when evaluating at the restored value raises in turn. Pinned by
  `test/server/test_fit_jobs_use_job_manager.py::test_a_failing_scan_still_restores_the_parameter`
  (a model that raises on its 4th update — the case the finding measured at
  `1.6`) plus the value assertion added to
  `test_a_failing_scan_is_reported_as_failed` for the raises-immediately case.
  Both fail with `1.6 != 2.0` against the pre-fix restore placement.
  `test/server/test_fit_jobs_use_job_manager.py`, `test_services_fits.py`,
  `test_service_robustness.py`, `test/fitting/test_posterior_api.py`,
  `test_sampling_job_reports_convergence.py` and `test_prior_reweighting.py` all
  green (149 tests); `ruff check` reports the same 93 pre-existing findings on
  `fits.py` as at HEAD and none on the test file.

### RF-114
- **Status:** OPEN
- **Severity:** S1 (a second scan captures a mid-flight value as "the original", scans the wrong interval, and restores the fit to that wrong value permanently)
- **Location:** `chisurf/server/services/fits.py:1463-1469` (`_run` reads `value = getattr(param, "value", 0)` **inside** the worker thread, and derives `lo`/`hi` from it) with `:1456-1506` (nothing prevents a second job on the same fit) and `chisurf/gui/plots/parameter_scan/parameter_scan.py:150` (`processEvents()` inside the poll loop, with the Scan action never disabled)
- **Finding:** The starting value is read when the thread runs, not when the RPC is served, so it is whatever the parameter happens to hold at that moment. Two scans on one fit therefore corrupt each other: verified with the service functions directly — scan A running (200 steps, 4 ms/step), scan B started 0.1 s later captured `1.3077` as the original, centred its window there instead of on `2.0`, and because B finished last its restore left `param.value == 1.3077` for a parameter whose true value was `2.0`. Both jobs report `completed`; nothing warns, and B's χ² curve is a scan of a region the user never asked about. This is reachable from the GUI precisely because `_poll_scan_result` pumps Qt events in its own loop while leaving `actionScanParameter` enabled, so a second click re-enters `scan_parameter`; a scan concurrent with a `fit.sample.*` job on the same fit is the same collision. Two independent halves: capture `value` (and `lo`/`hi`) in `fit_parameter_scan_start` before `start_threaded`, and refuse a second job against a fit that already has a live one (`INVALID_STATE`) rather than letting two threads drive one model.
- **Fix note:**

### RF-115
- **Status:** OPEN
- **Severity:** S2 (an unreachable or unknown sampling job is announced to the user as a finished run with no convergence problems)
- **Location:** `chisurf/gui/widgets/fitting/fit_controller.py:554-577` (`_watch_sampling_job._poll`: `state = str(status.get("status", ""))` with no test of `status["ok"]`) against `chisurf/gui/widgets/fitting/fitting_client.py:951-955` (`sampling_status` returns `{"ok": False}` when `_try_rpc` fails) and `chisurf/server/services/__init__.py:27-49` (`service_error` payloads carry no `status` key)
- **Finding:** Every failure mode of the status call — RPC unavailable, transport dropped, `RemoteError`, or a job the server no longer knows (`_JOBS.cleanup()` prunes past `max_history`, and a restarted server knows none) — produces a dict without a `status` key, so `state` is `""`. That value is not in `("queued", "running", "cancelling")`, so polling stops; it is not `"failed"`, so the error branch is skipped; `warnings` is then empty and the poller logs **"Sampling finished; no convergence problems detected (? chains x ? draws)"**. The `?` placeholders are the only hint that the run was never observed. The function's own docstring says its point is that "a finished run is not the same as a trustworthy one" — this path reports an *unobserved* run as the most trustworthy kind. Treat a response with `ok` false or no `status` as lost contact (the `except` branch's wording already exists at `:557-559`).
- **Fix note:**

### RF-116
- **Status:** OPEN
- **Severity:** S2 (an error response makes the parameter-scan widget re-issue the same RPC ~6000 times over five minutes while pumping Qt events, then give up leaving the server job running)
- **Location:** `chisurf/gui/plots/parameter_scan/parameter_scan.py:124-152` (`_poll_scan_result`: the `while` loop breaks only on `"completed"` / `"failed"` / `"cancelled"`)
- **Finding:** `parameter_scan_result` returns `{"ok": False}` on any RPC failure and `service_error(...)` — also without a `status` key — for an unknown job id, so `status` is `""`: neither the completion branch nor the `("failed", "cancelled")` break fires and the loop runs to its full 300 s deadline at 20 Hz, calling `processEvents()` each turn (the reentrancy that makes RF-114 reachable). Three fixes, all small: break when `not result.get("ok")` or `status` is empty; call `fc.cancel_parameter_scan(job_id)` on the deadline instead of abandoning a job that is still walking the live model; and disable `actionScanParameter` for the duration so the pumped events cannot start a second scan. A `QTimer`-driven poll like `_watch_sampling_job`'s would remove the blocking loop altogether.
- **Fix note:**

### RF-117
- **Status:** OPEN
- **Severity:** S2 (the widget's two range spin boxes are computed, then silently discarded on the RPC path, so the same button scans a different interval depending on whether RPC is up)
- **Location:** `chisurf/gui/plots/parameter_scan/parameter_scan.py:162` (`scan_range = ((1.0 - p_min) * value, (1.0 + p_max) * value)`, used only by the local fallback at `:183-187`) and `:168-173` (`start_parameter_scan(..., range_factor=2.0)`, hard-coded) against `chisurf/server/services/fits.py:1432-1472` (the endpoint takes no range at all)
- **Finding:** `fit_parameter_scan_start`'s signature is `(state, parameter_name, fit_index, fit_uid, n_steps, range_factor)` — there is no way to express the interval the user typed. The server invents its own: `half_range = err * range_factor` when the parameter carries an `error_estimate`, else `abs(value * 0.5)`, else `1.0`. So on the RPC path the ± spin boxes do nothing, and before a fit has converged (no error estimate) even `range_factor` is ignored, making the hard-coded `2.0` doubly inert — every scan is a fixed ±50 % of the current value. The local path honours the spin boxes exactly. Add an optional `scan_range` (or explicit `lo`/`hi`) to the endpoint and send the widget's, keeping the error-estimate heuristic as the default when it is absent.
- **Fix note:**

### RF-118
- **Status:** OPEN
- **Severity:** S3 (`max_history=0` — "keep no history" — is the one setting under which the documented pruning does nothing at all)
- **Location:** `chisurf/server/jobs.py:269-277` (`JobManager.cleanup`: `to_remove = terminal[:-self._max_history] if len(terminal) > self._max_history else []`)
- **Finding:** `-0` is not a negative index: with `_max_history == 0` the guard passes (any terminal job is `> 0`) and `terminal[:-0]` evaluates to `terminal[:0]`, the empty list, so nothing is pruned and the manager grows without bound in exactly the configuration that asks for the least memory. Verified: `JobManager(max_history=0)` with three completed jobs returns `cleanup() == 0` and still holds 3, while `max_history=1` correctly removes 2. `terminal[: max(0, len(terminal) - self._max_history)]` handles every value uniformly and lets the `if` go. `test/server/test_jobs.py:103` only covers `max_history=2`.
- **Fix note:**

### RF-119
- **Status:** OPEN
- **Severity:** S3 (the server exposes a `job_manager` that no job is ever registered in, while the real registry is a module-level singleton nothing can reach)
- **Location:** `chisurf/server/app.py:51` (`self.job_manager = JobManager()`, plumbed on to `AppStartupServiceManager` at `:68` and into every `AppStartupContext` — `chisurf/startup/services.py:159`, `:406`, `:587`) against `chisurf/server/services/fits.py:1081` (`_JOBS = JobManager()`, where the fit jobs actually live)
- **Finding:** There are two managers. Every `create_job` in the tree goes to the `fits.py` module-level `_JOBS`; `ServerApp.job_manager` is constructed, handed to the startup-service context and to `chisurf/gui/background_startup.py:84`, and never has a job put in it or taken out of it — grep finds only assignments. A startup service or plugin handed `context.job_manager` therefore sees an empty registry and cannot list, poll or cancel the sampling and scan jobs the server is actually running, and a generic `jobs.*` endpoint cannot be written against it; `test/server/test_app.py:45` asserts only that the attribute is not `None`. It is also process-global rather than per-session, so two `SessionState`s in one process share a job id space. Either inject the app's manager into the fits service (the dispatcher already carries `state` and `event_bus` the same way) or drop the unused attribute and the context field, so "one job manager" (INC-08) is true of the code and not only of the commit message.
- **Fix note:**

### Review 2026-07-26 — the LLM agent harness (`chisurf/core/agent/`)

Slice: the agent loop and its transport — `runtime.py`, `llm.py`, `spec.py`,
`context.py`, `prompt.py`, `cli.py`, `skills.py` and `tools/scripting.py` —
picked because the package has no findings on record and carries recent
landings (`da896d13b`, `d5d1c11b4`, `448c8538e`). The core design holds: the
multi-call turn, the failure-signature counter, the safety tiers and the
portable-assistant-message normalisation (`test_provider_dialects.py`) all do
what they claim. The findings are on the paths the tests do not follow — what
the *conversation* looks like after a run stops early, what a provider dialect
outside the three replayed ones produces, and the budgets that are documented
but not enforced. Reproduced in the `arm64` env with the scripted-LLM harness
from `test/agent/test_runtime.py`. RF-120..RF-125.

### RF-120
- **Status:** OPEN
- **Severity:** S1 (a run that hits any budget, or is cancelled, leaves the conversation permanently malformed — every later question in the same session re-sends it and is rejected by the provider)
- **Location:** `chisurf/core/agent/runtime.py:292-319` (the `for call in calls` loop breaks on `cancelled` / `tool_budget` / `repeated_failures` **after** `_append_assistant` at `:290` has already written the assistant turn carrying every `tool_call` id) with `:413-431` (`_append_tool_result`, run only for the calls that were executed)
- **Finding:** The OpenAI dialect requires each `tool_call.id` in an assistant turn to be answered by a `tool` message; the loop appends the assistant turn with *all* the ids and then executes only some of them. Verified with the test file's own `ScriptedLLM`: a three-call turn under `max_tool_calls=2` leaves `messages` as `system, user, assistant(call_0, call_1, call_2), tool(call_0), tool(call_1)` — `call_2` unanswered — and the follow-up question posts that same list verbatim to the provider. The other two early exits do the same: cancelling after the first call orphans `['call_1', 'call_2']`, and `max_consecutive_failures=2` on a five-call turn orphans `['call_2', 'call_3', 'call_4']`. Because `ask()` clears `_cancelled` and keeps `self.messages` (the "conversation survives across questions" property in the module docstring, and the reason `reset()` exists separately), the session is poisoned from then on: `cancel()` is the *documented* way to stop a run, and it makes the next question fail with a 400 rather than a cancellation. `test_tool_call_budget_is_enforced` and `test_cancel_stops_the_loop` assert only `stop_reason` and the invocation count, so nothing covers the resulting history. Fix in one place: when the loop exits early, append a synthetic `{"ok": false, "error": "not run — the request stopped"}` result for every unanswered id (which is also honest to the model), or drop the assistant turn. The same shape is reachable from `cli.py:249-254`, where a Ctrl-C mid-tool unwinds out of `ask()`.
- **Fix note:**

### RF-121
- **Status:** OPEN
- **Severity:** S2 (against a provider that sends tool arguments as an object rather than a string, every single tool call fails — and fails with a message accusing the model of malformed JSON)
- **Location:** `chisurf/core/agent/llm.py:263-279` (`parse_response`: `raw_arguments = function.get("arguments") or "{}"`, `json.loads(raw_arguments)` guarded by `except (TypeError, ValueError, AttributeError)` → `arguments = {}`) with `chisurf/core/agent/runtime.py:539-545` (the "is not a JSON object" rejection)
- **Finding:** The parser assumes `function.arguments` is a JSON *string*. Several OpenAI-compatible servers (the local-model providers this client explicitly targets in its module docstring) emit it as an already-decoded object. That case is not malformed — it is the parsed form — but `raw_arguments.strip()` raises `AttributeError`, the blanket `except` discards it, and `raw_arguments=str(raw_arguments)` stores the Python `repr`. Verified end to end: a reply whose arguments are `{"directory": "tcspc", "pattern": "*.dat"}` produces `ToolCall.arguments == {}` and `raw_arguments == "{'directory': 'tcspc', 'pattern': '*.dat'}"`, and `_execute` then returns `could not parse the arguments for 'load_data': "{'directory': 'tcspc', 'pattern': '*.dat'}" is not a JSON object` — with the arguments plainly visible in the error. The model cannot correct this, so the run burns its whole budget on `repeated_failures`. One `isinstance(raw_arguments, dict)` branch (use it directly, `raw_arguments=json.dumps(...)`) fixes it; `test_provider_dialects.py` is the right home for the case, alongside the three reply shapes already replayed there.
- **Fix note:**

### RF-122
- **Status:** OPEN
- **Severity:** S2 (a documented per-call wall-clock limit that no code reads; a model-written `while True:` hangs the GUI or CLI with no way back except killing the process)
- **Location:** `chisurf/core/agent/context.py:43,56` (`code_timeout_s : float — Wall-clock limit for a single run_python call`, default `60.0`) against `chisurf/core/agent/tools/scripting.py:152-161` (`exec(compile(...))` with no timeout), grep: the attribute is only ever defined, never read
- **Finding:** `run_python` runs the model's code synchronously in the calling thread and returns whenever it returns. Verified: `AgentContext(code_timeout_s=0.1)` running `time.sleep(2.0)` took **2.11 s** and reported `ok=True`. Nothing else covers the gap — `AgentConfig.time_budget_s` is tested only at the top of the loop (`runtime.py:269`), and `cancel()` is documented to "stop after the current tool call" (`:229-231`), so both are unreachable while the snippet runs. In the GUI the agent panel drives the loop, so a non-terminating snippet freezes the event loop with no cancel button that can bite. Either enforce the field (run the snippet on a worker thread and report a timeout as a `ToolError`, which is what the model needs to hear) or delete it and say plainly in the docstring that the snippet is uninterruptible.
- **Fix note:**

### RF-123
- **Status:** OPEN
- **Severity:** S3 (an empty session turns a clean tool error into a raw `IndexError` that the model is asked to interpret)
- **Location:** `chisurf/core/agent/tools/fitting.py:474-506` (`set_parameter`: `targets = list(range(len(context.fits)))` under `all_fits`, then `context.fits[targets[0]]` in the `if not changed` branch at `:499-502`)
- **Finding:** With `all_fits=True` and no fits in the session, `targets` is `[]`, the loop body never runs, and the "no fit has a parameter called …" branch indexes `targets[0]`. Verified: `set_parameter(ctx, parameter="tau", value=1.0, all_fits=True)` on an empty session raises `IndexError: list index out of range`, which `runtime._execute` hands back as `IndexError: list index out of range` — no mention of fits, parameters or what to do instead. Every sibling path raises a `ToolError` that names the fix (`run_fit:367-368`, `context._resolve:213-216`). The single-fit path is fine because `resolve_fit` raises first; only `all_fits` skips it. Guard the empty-target case with the same `ToolError` text `run_fit` uses.
- **Fix note:**

### RF-124
- **Status:** OPEN
- **Severity:** S3 (a reply cut off by `max_tokens` is shown to the user as the finished answer, JSON braces and all)
- **Location:** `chisurf/core/agent/llm.py:285` (`finish_reason` parsed onto `LLMResponse` and, by grep, never read anywhere) with `chisurf/core/agent/prompt.py:262` (`parse_text_protocol` returns the raw text as `{"answer": ...}` when it does not parse) and `chisurf/core/agent/runtime.py:285-288` (no tool calls ⇒ this is the final answer)
- **Finding:** `finish_reason == "length"` is the provider saying "this is not the whole reply", and the runtime never asks. In text-protocol mode a truncated object is not JSON, so it falls through to the "treat it as prose" branch and the user is shown the source: verified, `parse_text_protocol('{"answer": "the fit converged with chi2r =')` returns `{'answer': '{"answer": "the fit converged with chi2r ='}`. In native mode a truncated `tool_calls` argument string fails to parse and the model is told its JSON was malformed (RF-121's message) rather than that its answer was cut off. `max_tokens` is user-settable and the client already explains it to the user on an HTTP 402 (`llm.py:392-401`), so a short setting is an expected state, not an exotic one. Surface it: mark the result when `finish_reason == "length"` and say so in the answer text.
- **Fix note:**

### RF-125
- **Status:** OPEN
- **Severity:** S3 (the interactive CLI's Ctrl-C handler calls a cancel that can no longer do anything)
- **Location:** `chisurf/core/agent/cli.py:249-254` (`except KeyboardInterrupt: session.cancel()`) against `chisurf/core/agent/runtime.py:229-231` (`cancel` sets a flag the loop tests) and `:251` (`ask` clears `_cancelled` on entry)
- **Finding:** By the time the `except` runs, `KeyboardInterrupt` has already propagated out of `ask()` and unwound the loop, so setting `_cancelled` has no loop left to stop; the next question clears the flag before anything reads it. The cooperative cancel the runtime provides is therefore never exercised by the CLI — the only path is the hard unwind, which is also what leaves the orphaned tool ids of RF-120 (and, unlike the loop's own cancel path, produces no `agent.completed` event and no `stop_reason`). Either install a SIGINT handler that calls `session.cancel()` from outside the call (so the loop stops itself at its next checkpoint) or, at minimum, `session.reset()` here so the next question starts from a conversation the provider will accept.
- **Fix note:**

## GUI-tester run — Anisotropy wizard (2026-07-26)

Driven headlessly through the real widgets: the Read-data experiment/reader combo
boxes in VV/VH mode, `WizardHub`, the AutoForm `WizardWidget` Back/Next rail, the
bound file-path line edits, the embedded `IrfNormalizationWidget` and
`ComponentsWidget`, and the **Create fits** button, with screenshots at every
step. Data: the VV/VH-stacked `test/data/tcspc/Jordi/` decay and water IRF. Use
case: [anisotropy wizard](/usecases/anisotropy-wizard-global-fit.md). The
workflow does work end to end — 14 VV↔VH links applied, global fit converged to
χ²ᵣ = 4.58 — but only once the fitting RPC was pinned to a private port; the
first two attempts hit RF-012 (a foreign ChiSurf on 8765) and every link call
returned *"fit not found"* while the wizard reported success. RF-126..RF-130.

### RF-126
- **Status:** OPEN
- **Severity:** S2 (the only feedback control on the wizard's Data step is dead — it reports "no file" for four files that are loaded and fitted)
- **Location:** `chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/view_model.py:311-323` (`data_html`) rendered by the `{"type": "info", "source": "data_html"}` section of `anisotropy.view.json:32`, fed by `chisurf/gui/autoform/sections/builtin.py:1066-1069` (`_commit_file`) → `:369` (`_commit`) which never calls `model.notify()` / `model.update()`
- **Finding:** `data_html` builds a four-row checklist (`IRF VV / IRF VH / Data VV / Data VH`, ✓ or `—`, plus the path) and is rendered once when the step is built. Committing a path — typing it and pressing Enter, or picking it with the **…** browse button — sets the model attribute but fires no model notification, so the info panel is never re-rendered. Verified across a whole session: after all four paths were set (`model.data_ready == True`) the panel still read `IRF VV —`, `IRF VH —`, `Data VV —`, `Data VH —`; after navigating to *Normalize IRF* and back it still read `—` on all four rows (`05_data_step_filled.png`, `05b_data_step_revisited.png`), and it was still `—` after the curves had been loaded and a global fit run off them. The nav ✓ on **Data** has the milder version of the same bug: it is driven by `WizardWidget.refresh()`, which only runs from `_on_nav_changed`, so it appears one navigation late — the nav labels are `['✓ Welcome', 'Data', ...]` immediately after filling and `['✓ Welcome', '✓ Data', ...]` after a Next+Back. A user who types the paths sees no acknowledgement anywhere on the step. Have `_commit_file`/`_commit` notify the model (the wizard already re-renders info sections on `AUTOFORM_REFRESH`), and refresh the nav on model change rather than only on navigation.
- **Fix note:**

### RF-127
- **Status:** OPEN
- **Severity:** S2 (the wizard reports "created … with all parameters linked" when not one link was applied; the links are the whole purpose of the tool)
- **Location:** `chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/view_model.py:428` (`self._set_status(True, "Created VV, VH and global anisotropy fits.")`, reached unconditionally after `core_fits.apply_link_plan`) with `chisurf/plugins/fluorescence_decay/tr_anisotropy/core/fits.py:81-120` (`apply_link_plan` ignores every return value) and `chisurf/gui/widgets/fitting/fitting_client.py:125-169` (`_try_rpc` logs and returns `None` on failure)
- **Finding:** `apply_link_plan` replays ~40 `link_parameters` / `set_parameter_value` / `set_parameter_fixed` / `update_fit` calls through the fitting client. Each one swallows its own failure (`_try_rpc` → `None`), the plan ignores the results, and `create_fits` then prints the green success message regardless. Observed twice in this run: with the RPC transport pointing at a foreign ChiSurf every call failed (`RemoteError: fit not found`, `RemoteError: source fit not found` — ~40 tracebacks in the log) and the Finish step still showed *"Created VV, VH and global anisotropy fits."* in green (`14_finish_after_create.png`). The resulting fits had `g = 1`, `l1 = l2 = 0` (typed: 1.15 / 0.12 / 0.44), `n0` fixed, and an empty `Link` column in the global fit's *Info* tab — i.e. two unrelated single-channel fits presented as a linked anisotropy analysis. The wizard is the one place a user cannot check the wiring by hand, so a silent failure here is unrecoverable. Make `apply_link_plan` collect the failed operations and have `create_fits` report them (`_set_status(False, …)` already exists and is used for the two pre-flight checks).
- **Fix note:**

### RF-128
- **Status:** OPEN
- **Severity:** S3 (the datasets the wizard registers are named with an absolute path and a doubled polarisation suffix)
- **Location:** `chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/view_model.py:266-280` (`_make_curve`: `name=os.path.splitext(template.name)[0] + suffix` at `:278`) called at `:264-265` with `suffix="_vv"` / `"_vh"` on templates whose `name` was already given the suffix at `:246`
- **Finding:** `load_data` names each loaded curve `<path-without-extension>_<pol>`; `apply_region` then passes that curve to `_make_curve` with the *same* suffix again. Verified: the corrected IRFs are appended to `chisurf.imported_datasets` as `/Users/…/test/data/tcspc/Jordi/H2O_8-0 ps_2048 ch_vv_vv` and `…_vh_vh`, and the sample decays as `/Users/…/02_18-577+7.5uM(577)UP_8ps_vv`. Every dataset the wizard creates therefore carries the user's full filesystem path as its display name (it is the fit-window title, the dataset-tree row and the IRF-picker entry — the fit window title truncates to `…/Jordi/02_18-577+7.5uM(577)UP_8ps_U`, so the `_vv`/`_vh` that distinguishes the two windows is the part that gets cut). Use the basename, and do not re-append a suffix the template already carries.
- **Fix note:**

### RF-129
- **Status:** OPEN
- **Severity:** S3 (the two polarisation channels of one measurement are fitted over different time windows, both running into the next excitation pulse, and the wizard offers no way to set the range)
- **Location:** `chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/view_model.py:371-380` (`create_fits` dispatches `fit.add` for the two datasets and never touches the range) with the per-fit auto-range in `chisurf/gui/widgets/fitting/fitting_widget.py` (`onAutoFitRange`)
- **Finding:** Each of the two fits auto-ranges from its own curve, so the VV fit gets `(328, 1809)` and the VH fit `(343, 1827)` — a 15-channel (0.5 ns) difference in start and an 18-channel difference in stop, on two channels that share one time axis, one IRF position and (after the link plan) one `ts`, one `n0` and one lifetime spectrum. Verified in this run's fit windows (`Range 328, 1809` / `Range 343, 1827`). Both stops also sit past the end of the usable window: at `dt = 0.032` ns and 25 MHz, channel 1809 is 57.9 ns and the data are already rising into the following pulse there, which is the +20 σ spike at the right edge of the VV weighted residuals (`16_fitwindow_0.png`) and a large part of the χ²ᵣ = 4.67. The wizard has no fit-range step, so a user who follows it end to end never sees or sets this. Give the wizard one common range for both channels (auto-detected from VV, editable), or at minimum link `start`/`stop` in the plan alongside `ts` and `n0`.
- **Fix note:**

### RF-130
- **Status:** OPEN
- **Severity:** S3 (two model outputs are `nan` in every fit the wizard builds)
- **Location:** `chisurf/gui/widgets/models/tcspc/anisotropy.py:635-657` (`_compute_vv_bg_corrected_integral` / `_compute_vh_bg_corrected_integral` → `float('nan')` when the diagnostics are unavailable) reached via `:482-501` (`_extract_vv_vh_bg_corrected`, whose stacked branch requires `polarization_type in ('vv/vh', 'vvvh')`) against `chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/view_model.py:418-419`, which sets `polarization_type` to `"vv"` and `"vh"`
- **Finding:** The anisotropy model exposes `vv_bg_int` / `vh_bg_int` as `is_output=True` parameters (`VV_bg-corr` / `VH_bg-corr` in the panel, and rows in the fit's *Info* tab). In both wizard-built fits they read `nan` after a converged global fit — verified by dumping `model.parameters_all` on the VV fit after `chi2r = 4.6712`: `vv_bg_int = nan fixed=True`, `vh_bg_int = nan fixed=True`, while every other output (`r_ss_l = 0.2569`, `r_ss_i = 0.1820`) is finite. The wizard puts one polarisation per fit and sets `polarization_type` to `"vv"`/`"vh"`, so the stacked branch of `_extract_vv_vh_bg_corrected` is skipped and the fit-group branch does not find a usable VV/VH pair either. Either make the diagnostics work for the wizard's split-channel layout (the group branch already looks for local fits by `polarization_type`) or hide the two outputs when they cannot be computed — printing `nan` next to real numbers invites it into a table.
- **Fix note:**

## Review run — chiplot core (2026-07-26)

Slice: the renderer-neutral plotting seam `chisurf/gui/chiplot/` (`canvas.py`,
`style.py`, `handles.py`, `backends/base.py`, `backends/pyqtgraph_backend.py`) —
~2 600 lines with no findings on record, freshly changed by
`f06fa93a3` (link_x/link_y + text fill/border) and the target of the ~30-batch
PRD-64 migration, so every defect here is inherited by every migrated plot.
Every finding below was reproduced in the `arm64` env against pyqtgraph 0.14.0
(offscreen Qt); RF-132 and RF-133 were additionally confirmed by rendering and
inspecting the PNG. RF-131..RF-137.

### RF-131
- **Status:** OPEN
- **Severity:** S2 (in a `Grid`, a click on one panel fires `clicked` on *every* panel, each with a coordinate mapped through its own unrelated viewbox)
- **Location:** `chisurf/gui/chiplot/backends/pyqtgraph_backend.py:749-757` (`_PgCanvas.on_click`) and `:759-768` (`on_mouse_move`), reached from `chisurf/gui/chiplot/canvas.py:954` (`PanelPlot.__init__`) and `:70-71` (`Plot.__init__`)
- **Finding:** Both handlers connect to `self._host.scene()`, and for a grid panel `_host` is the whole `GraphicsLayoutWidget` (`_PgGrid.add_panel:786-789` hands every panel the same widget), so the signal is scene-wide while the mapping (`vb.mapSceneToView`) is panel-local. Verified on a 2-panel grid: emitting a click at the centre of the *bottom* panel's `sceneBoundingRect` produced `[('p0', 4.50, -10.92), ('p1', 4.50, 448.03)]` — the top panel reported y = -10.9, outside its own view range (-0.83, 9.83), for a click it never received. The `on_mouse_move` guard `self._host.scene().sceneRect().contains(pos)` looks like a bounds check but is not one: `sceneRect` is the whole scene (measured 0,0,600×1135 for a 600×400 widget), so it is true for every position, including the axis margins outside any viewbox. Scope both to the panel — `self._pi.getViewBox().sceneBoundingRect().contains(pos)` before mapping — which also fixes the single-`Plot` case, where a click in the axis/title margin currently reports extrapolated data coordinates.
- **Fix note:**

### RF-132
- **Status:** OPEN
- **Severity:** S2 (`plot.line(x, y, symbol="o")` documents "draw a marker at each point" and draws nothing at all)
- **Location:** `chisurf/gui/chiplot/backends/pyqtgraph_backend.py:499-502` (`add_curve`: `kw["symbolBrush"] = _brush(symbol_brush) if symbol_brush is not None else None`, same for `symbolPen`) against the contract in `chisurf/gui/chiplot/canvas.py:114-121`
- **Finding:** `Plot.line` defaults `symbol_brush`/`symbol_pen` to `None`, and the backend forwards that `None` verbatim to pyqtgraph, which means *no fill* and *no outline* rather than "use the default". pyqtgraph's own defaults are `symbolBrush=(50, 50, 150)` and `symbolPen=(200, 200, 200)`. Verified: the resulting `ScatterPlotItem` carries `QBrush.style() == NoBrush` and `QPen.style() == NoPen`, and a rendered PNG shows the curve's markers completely absent next to a `pg.PlotDataItem` reference drawn with the same arguments (`/tmp/chiplot_symbol.png`). Note `Plot.scatter` is unaffected — it defaults `brush="w"`. Live call site: `chisurf/plugins/burst/burst_fcs_correlator/wizard.py:274` draws the correlation data as `line([], [], pen="w", symbol="o", symbol_size=4)`, i.e. the markers it asks for never appear. Fall back to a sensible default brush/pen when `symbol` is given and neither is specified (or omit the keys so pyqtgraph applies its own).
- **Fix note:**

### RF-133
- **Status:** OPEN
- **Severity:** S2 (a plot asked for a white background renders white inside the axes and black everywhere else — a visible regression against the pyqtgraph call site it replaced)
- **Location:** `chisurf/gui/chiplot/canvas.py:68-69` (`Plot.__init__` routes `background` to `self._canvas.set_background`) and `chisurf/gui/chiplot/backends/pyqtgraph_backend.py:683-686` (`set_background` → `vb.setBackgroundColor`), versus `:894-900` (`create_canvas`, which *does* have a widget-level `pw.setBackground` path that `Plot` can never reach because `background` is an explicit keyword and never lands in `backend_opts`)
- **Finding:** `ViewBox.setBackgroundColor` paints only the plot rectangle; the axis strips, tick labels and title keep the process-wide pyqtgraph background, which ChiSurf sets to `k` (`chisurf/core/settings/settings_chisurf.yaml:120`). Verified by rendering `cp.Plot(background="w")` after `cp.configure(background="k")`: white data rectangle framed by black margins with grey text. The affected call site is `chisurf/plugins/fret_line/gui/tool.py:92`, whose pre-migration form was `pg.PlotWidget(parent=parent)` + `pw.setBackground("w")` — the whole widget white. Second half of the same defect: `background=None` is treated as "not given" (`if background is not None`), so the pyqtgraph idiom for a *transparent* panel is silently a no-op; `chisurf/gui/widgets/spectrum_view.py:121` and `chisurf/plugins/core/lightpath_simulator/gui/node_types.py:91` both pass it. Route the constructor's `background` (including an explicit `None`) into `create_canvas` so the widget is painted, and document that `set_background` on a live plot only reaches the viewbox.
- **Fix note:**

### RF-134
- **Status:** OPEN
- **Severity:** S2 (a colour spec the module docstring itself gives as an example silently produces near-black instead of red)
- **Location:** `chisurf/gui/chiplot/style.py:136-143` (`to_color`: `is_float = all(isinstance(v, float) for v in vals) and all(v <= 1.0 for v in vals)`) against its own docstring at `:102-103` and the advertised example at `chisurf/gui/chiplot/canvas.py:12`
- **Finding:** The docstring says 0–1 floats are "auto-detected: all values `<= 1` are treated as floats", but the code *additionally* requires every element to be a Python `float`, so any tuple mixing floats with integer literals falls into the 0–255 branch and is truncated by `int(v)`. Verified: `to_color((1.0, 0, 0))` — the exact spelling `canvas.py`'s module docstring offers as "pass `(1.0, 0, 0)`" — returns `Color(r=1, g=0, b=0)`, i.e. black; `to_color((0.5, 0.5, 1))` returns `Color(r=0, g=0, b=1)`, discarding both 0.5 channels. `(1.0, 0.0, 0.0)` is correctly red, so the failure depends only on how the caller happened to spell the zeros, and nothing raises. Either drop the `isinstance` requirement (match the documented rule, which is also what makes the docstring's `(1, 0, 0)`-style examples work) or reject mixed tuples explicitly; keep `to_color` and the two docstrings saying the same thing.
- **Fix note:**

### RF-135
- **Status:** OPEN
- **Severity:** S3 (the abstract backend contract no longer matches what the wrapper actually calls — a second backend written to `base.py` raises `TypeError` on the first text label)
- **Location:** `chisurf/gui/chiplot/backends/base.py:139-149` (`Canvas.add_text`, no `fill`/`border`) against `chisurf/gui/chiplot/canvas.py:389-397` (`Plot.text` always passes `fill=`/`border=`, `None` or not) and `chisurf/gui/chiplot/backends/pyqtgraph_backend.py:595` (which grew the two parameters in `f06fa93a3`)
- **Finding:** The `fill`/`border` feature was added to the concrete pyqtgraph canvas and to the public `Plot.text`, but the abstract method it implements was not updated: `inspect.signature(base.Canvas.add_text)` is `(self, text, pos, *, color, anchor, draggable)` while the pyqtgraph implementation is `(..., draggable, fill=None, border=None)`. `base.py` is the document a second renderer is written against ("Swapping to a different renderer means writing a sibling module with the same classes"), so it is exactly the thing that must not drift. Add the two keyword parameters to the abstract signature and its docstring. Worth checking the neighbours in the same commit while there — `link_x`/`link_y` were added to `base.py` correctly, as defaulted no-ops.
- **Fix note:**

### RF-136
- **Status:** OPEN
- **Severity:** S3 (CSV export includes series the user removed from the plot, and the plot keeps them alive)
- **Location:** `chisurf/gui/chiplot/canvas.py:419-427` (`Plot.remove`, which touches only the canvas) against `:147`/`:181` (`self._series.append(...)`) and `:485-497` (`export_csv` iterating `self._series`)
- **Finding:** `line()`/`scatter()` register their handle in `self._series` for the CSV export action; `clear()` empties that list but `remove(handle)` does not. Verified: drawing curves `gone` and `kept`, calling `plot.remove(gone)`, then `export_csv` writes the header `gone x,gone y,kept x,kept y` — the removed curve is exported with full data. The handle also stays referenced by the `Plot`, so the pyqtgraph item is never collected. Drop the matching entry in `remove()` (identity match on the handle).
- **Fix note:**

### RF-137
- **Status:** OPEN
- **Severity:** S3 (a docstring promises overlays are cleared; they survive, so a stale overlay is drawn over the next image)
- **Location:** `chisurf/gui/chiplot/canvas.py:833-835` (`ImageView.clear`, *"Clear the image and overlays."*), the same claim in `chisurf/gui/chiplot/backends/base.py:335-337`, implemented at `chisurf/gui/chiplot/backends/pyqtgraph_backend.py:829-831` as a bare `self._iv.clear()`
- **Finding:** `pg.ImageView.clear()` clears the image item only; items added to the view by `add_overlay` (`:849-857`) and `add_roi` (`:859-871`) are unaffected. Verified: after `set_image` + `add_overlay`, the view holds 4 added items; after `ImageView.clear()` it still holds 4 and the overlay handle's native item is still in `view.addedItems`. A caller following the docstring re-shows an image with the previous overlay still on top. Either track the items this canvas added and remove them in `clear()`, or correct both docstrings to say overlays and ROIs must be removed through their handles.
- **Fix note:**

## Review run — the plugin contract layer (2026-07-26)

Slice: `chisurf/core/plugin/` (`manifest.py`, `registry.py`, `client.py`, ~1 000
lines) — the manifest/discovery/entrypoint seam every plugin depends on, with
**zero** findings on record and freshly changed by `7855cb4fc` (category-spelling
validation). Reviewed together with the two consumers that must agree with it:
`chisurf/core/cli.py` (the production `csc` registration path) and
`chisurf/server/app.py:71-78` (discovery at server startup). Every finding below
was reproduced in the `arm64` env against the real registry, the real manifests
and — for RF-138 — the real `csc` command. RF-138..RF-146.

### RF-138
- **Status:** FIXED
- **Severity:** S1 (a shipped CLI command is dead: `csc trace-browser` cannot start)
- **Location:** `chisurf/plugins/tttr/trace_browser/manifest.json:29` (`"cli": "trace-browser=chisurf.plugins.tttr.trace_browser.cli:cli"`) resolving to `chisurf/plugins/tttr/trace_browser/cli/__init__.py`, which does not export `cli`, while the intended `chisurf/plugins/tttr/trace_browser/cli.py` ("Trace Browser CLI compatibility shim", re-exporting `cli.main:cli`) is permanently shadowed by the sibling `cli/` package
- **Finding:** A regular package always wins over a same-named module in the same directory, so `import chisurf.plugins.tttr.trace_browser.cli` yields the package and the shim file is unreachable. Reproduced through the real production path: `python -m chisurf.core.cli trace-browser --help` → `Error: Failed to import plugin CLI 'Spectroscopy:Single-Molecule:Trace Browser:cli': module 'chisurf.plugins.tttr.trace_browser.cli' has no attribute 'cli'`. The failure only appears at invocation because `chisurf/core/cli.py` registers commands from the manifest without importing the plugin, so `csc --help` lists a command that always errors. The sibling plugins that got this right point their manifest at `cli.main:cli` (e.g. `tttr_microtime_shifter`) or re-export `cli` from `cli/__init__.py` (e.g. `tttr_time_windows`); do one of the two here and delete the unreachable shim. A static resolve of every in-tree manifest entrypoint (`entrypoints.gui/cli/services` → module file → attribute defined or imported) flags this as the only broken one, so it is a one-plugin fix.
- **Fix note:** `trace_browser/cli/__init__.py` now re-exports `cli` from `.main`
  (the `tttr_time_windows` pattern) and the shadowed `trace_browser/cli.py` shim is
  deleted; `python -m chisurf.core.cli trace-browser --help` prints the command
  group. The static resolve written as the guardrail found **a second** instance of
  the same defect that the review's sweep missed — `tttr_image_browser` had the
  identical `cli.py` shim next to a `cli/` directory that had *no* `__init__.py`, so
  the shim won the import and then failed on its own
  `from …tttr_image_browser.cli.main import cli` (`'…cli' is not a package`); fixed
  the same way in this change (CLAUDE.md "fix breakage the moment you find it").
  Pinned by the new `test/core/test_plugin_entrypoint_resolution.py`: it resolves
  every `entrypoints.gui`/`.cli`/`.services` in every built-in manifest statically —
  module path → file, honouring package-shadows-module, then an AST scan for the
  named attribute (189 targets, all green) — plus a focused test that imports both
  `…cli` packages and asserts `cli` is a `click.Group` and no sibling shim is back.
  Both tests fail on the pre-fix tree.

### RF-139
- **Status:** OPEN
- **Severity:** S2 (the manifest's declared command name is discarded, so in-process CLI registration collapses ~14 plugins onto one command called `cli`)
- **Location:** `chisurf/core/plugin/registry.py:190-192` (`if hasattr(cli_obj, "name"): cmd_name = cli_obj.name` — overwriting the `cmd_part` parsed at `:184-186` — then `main_group.add_command(cli_obj, name=cmd_name)`) against `chisurf/core/cli.py:52-76` (`_parse_cli_entrypoint`, which treats the `alias=` prefix as authoritative)
- **Finding:** `entrypoints.cli` has the form `alias=module:attr` and the alias *is* the public command name — that is what `csc` uses. `register_cli` parses it, then throws it away for the click object's own name, which for most plugins is derived from the decorated function and is simply `cli`. Verified with the real objects: `chisurf.plugins.pch.cli:cli` and `chisurf.plugins.fcs.flc_2d.cli:cli` are both named `cli`, and registering both manifests (`pch=…`, `flc-2d=…`) through `register_cli` leaves a single command — `sorted(main.commands) == ['cli']`, help text *"Run 2D-FLCS analysis tasks."* — i.e. the PCH CLI is silently replaced. A static scan of all 40 manifests with a CLI entrypoint finds exactly **2** whose click name matches the declared alias (`help`, `tttr-image-browser`); ≥14 resolve to the name `cli` and 8 to `main`. Use the manifest alias and fall back to `cli_obj.name` only when no alias was given, matching `_parse_cli_entrypoint`; and log a collision instead of overwriting.
- **Fix note:**

### RF-140
- **Status:** OPEN
- **Severity:** S2 (one malformed `manifest.json` anywhere on the search path aborts *all* plugin discovery, and with it server startup)
- **Location:** `chisurf/core/plugin/manifest.py:229-234` (`load_manifest` catches only `json.JSONDecodeError, KeyError, TypeError`) reached from `chisurf/core/plugin/registry.py:88` (`manifest = load_manifest(manifest_path)`, not guarded) and `chisurf/server/app.py:74` (`self.plugin_registry.discover()` in `ChisurfServer.__init__`, not guarded)
- **Finding:** `load_manifest` is documented to return `None` when a manifest "cannot be parsed", and `discover()` relies on that to fall back to legacy metadata. But a manifest whose top-level JSON is valid and *not an object* — a bare string or number — reaches `PluginManifest.from_dict`, where `data.get("entrypoints", {})` raises `AttributeError`, which is outside the caught tuple. Verified on a two-plugin temp tree (one good manifest, one containing `"just a string"`): `PluginRegistry().discover([tmp])` raises `AttributeError: 'str' object has no attribute 'get'` and the *good* plugin is never returned. Since `~/.chisurf/plugins` is a default search path, a user's hand-edited file takes down every plugin service on the server. Catch `AttributeError`/`ValueError` too (or reject a non-dict `data` up front, as `validate_manifest` already does at `:415-416`), and guard the per-directory work in `discover()` so one bad plugin cannot break the rest.
- **Fix note:**

### RF-141
- **Status:** OPEN
- **Severity:** S2 (the sanctioned local plugin transport accepts event subscriptions and delivers nothing — silently)
- **Location:** `chisurf/core/plugin/client.py:126-155` (`InProcessClient.subscribe`/`unsubscribe`, which fill `self._subscriptions` / `self._pattern_subs`) against `chisurf/server/dispatcher.py:74-77` (the dispatcher holds the real `_event_bus`) and `chisurf/server/eventbus.py:63-140` (`InProcessEventBus`, which is what actually publishes)
- **Finding:** `InProcessClient` is the local implementation of the `PluginClient` protocol — "the **only** way GUI code should communicate with the backend" (`client.py:9`). Its `subscribe` mints a token and stores the callback in registries that nothing ever publishes to; `_pattern_subs`/`_subscriptions` are referenced nowhere outside this file, and the class has no `publish`. Verified: with a dispatcher built on a real `InProcessEventBus`, `client.subscribe("burst_selection.jobs.progress", cb)` returns a token, the bus reports **0** subscribers, and `bus.publish(...)` delivers nothing. So every long-running plugin method that declares progress events in its manifest (`burst_selection.jobs.*`, `tttr_time_windows.jobs.*`, `maxent_decay.jobs.*`, `irf_estimator.jobs.*`) is unobservable in local mode, and a client written against the protocol looks subscribed. Delegate to `dispatcher._event_bus` (it already implements the same token/fnmatch contract) or raise `NotImplementedError`; the unused `import fnmatch` at `:135` and the docstring's "Uses fnmatch-style pattern matching" claim go with it.
- **Fix note:**

### RF-142
- **Status:** OPEN
- **Severity:** S2 (two plugins with the same `id` silently shadow each other, and the two consumers of discovery disagree about which exist)
- **Location:** `chisurf/core/plugin/registry.py:90-92` (`manifests.append(manifest)` *and* `self._manifests[manifest.id] = manifest`) with `:121-123` (`all_manifests`) and `:143` / `:178` / `:216` (all registration loops iterate `self._manifests.values()`)
- **Finding:** `discover()` deduplicates by *directory*, not by plugin id, so the returned list and the internal map diverge: the list contains every manifest found, the dict keeps only the last one written for a given id. Verified on a temp tree with two directories declaring `id: "same.id"`: `discover()` returns `[('same.id', 'Alpha'), ('same.id', 'Beta')]` while `reg._manifests` holds only `Beta` — no warning is logged. Because `~/.chisurf/plugins` is searched after the built-in tree, a user copy of a built-in plugin silently wins for services/CLI/GUI registration while still appearing twice to any caller that uses the returned list. Either make the override explicit (log it at `INFO` and keep the last), or reject the duplicate — but say so; today the behaviour is invisible either way.
- **Fix note:**

### RF-143
- **Status:** OPEN
- **Severity:** S3 (`validate_manifest` never runs on a manifest that loads, so user-plugin manifests are never validated at runtime)
- **Location:** `chisurf/core/plugin/registry.py:93-108` (validation lives in the `else` branch, reached only when `load_manifest` returned `None`) against `chisurf/core/plugin/manifest.py:399-436` (`validate_manifest`)
- **Finding:** `from_dict` performs no validation, so any manifest whose JSON parses and carries `id`/`version` loads successfully and skips the validator entirely — the only branch that calls it is the *unparseable* fallback. Verified: a manifest with `"categories": ["Structure", "structure"]` loads fine and discovery logs nothing, while `validate_manifest` on the same data returns `["duplicate category 'structure' (already listed as 'Structure')"]`. The category rule added in `7855cb4fc` is therefore enforced only by the in-tree guardrail test (`test/core/test_plugin_registry.py:343`), never for a plugin dropped into `~/.chisurf/plugins`, which is exactly the population that has not been reviewed. Validate on the success path too and log the errors at `WARNING` (loading can still proceed).
- **Fix note:**

### RF-144
- **Status:** OPEN
- **Severity:** S3 (a 90-line JSON Schema that nothing uses, drifted from the manifest it claims to describe, next to a docstring that says it is applied)
- **Location:** `chisurf/core/plugin/manifest.py:237-324` (`_MANIFEST_SCHEMA`) and `:399-412` (`validate_manifest`, *"Validate manifest data against the standard schema"*)
- **Finding:** `_MANIFEST_SCHEMA` is referenced nowhere in the tree (grep: one definition, zero uses) — `validate_manifest` hand-rolls a much smaller set of checks (`id`, `version`, `rpc_methods` names/summaries, categories, statefulness) and never consults it. Being dead, it has drifted: it has no `experimental` / `experimental_message` properties even though `from_dict` reads both (`:155-156`), so a reader who trusts the "standard schema" gets a stale contract. Either wire it up (which means taking on a `jsonschema` dependency — the tree has none today) or delete it and reword the docstring to describe what is actually checked.
- **Fix note:**

### RF-145
- **Status:** OPEN
- **Severity:** S3 (a per-plugin setting spelled `false` in `settings_chisurf.yaml` *enables* window-state persistence)
- **Location:** `chisurf/core/plugin/registry.py:305-311` (`return bool(override)` for a `per_plugin` entry) against `:313-317` (the `mode` key, which does accept the strings `"false"` / `"disabled"`)
- **Finding:** The `per_plugin` override is normalised only against the literal string `"plugin_default"`; everything else goes through `bool()`, and every non-empty string is truthy. Verified against a manifest whose default is enabled and an override map: `False → False`, `0 → False`, but `"false" → True`, `"no" → True`, `"off" → True`. The neighbouring `mode` key parses exactly these string spellings, so the two halves of the same setting disagree — and YAML users who quote the value get the opposite of what they asked for. (Second half, same seam: `mode` accepts `"disabled"`/`"force_disabled"`/`"false"` but not `"off"`/`"no"`, which silently fall through to the plugin default.) Parse both sides through one string→bool helper.
- **Fix note:**

### RF-146
- **Status:** OPEN
- **Severity:** S3 (eight "compatibility" shim modules that Python can never import, one of them promising an attribute its shadowing package does not provide)
- **Location:** `chisurf/plugins/tttr/tttr_time_windows/cli.py` + `gui.py`, `chisurf/plugins/tttr/tttr_microtime_shifter/cli.py`, `chisurf/plugins/tttr/trace_browser/cli.py`, `chisurf/plugins/core/lightpath_simulator/cli.py`, `chisurf/plugins/core/globalview/gui.py`, `chisurf/plugins/burst/burst_selection/cli.py` + `gui.py` — each shadowed by a sibling package of the same name
- **Finding:** All eight are single-import re-export shims ("Compatibility CLI entrypoint for …") sitting next to a regular package with the identical name, which always wins the import. Verified by importing each dotted path: every one resolves to the package's `__init__.py`, never to the `.py` file. Six are harmless because the package happens to re-export the same names, but two are not: `chisurf.plugins.tttr.trace_browser.cli` has no `cli` (the manifest depends on it — RF-138) and `chisurf.plugins.tttr.tttr_microtime_shifter.cli` has no `cli` either, so the compatibility path the shim advertises raises `ImportError` for any caller that uses it. Delete the dead files and, where the shim was the documented import path, re-export from the package `__init__.py` instead.
- **Fix note:**

### Review 2026-07-26 (10) — the three-colour PDA model (`chisurf/core/models/pda3c/`)

Slice: `tcpda.py` (1027 lines, PRD-65 stage 2, last touched 2026-07-25) with its
`tcpda.view.json`, read against the compute core in
`chisurf/core/fluorescence/pda3c/` and the reader at
`chisurf/core/experiments/pda/reader.py:195-307`. The likelihood core itself is
in good order — the "mix once, not twice" factorisation, the untruncated
`background_series` reference and the effective-rate cutoff in `_channel_boxes`
all hold up, and the two-colour reduction and PAM/Octave A/B tests pin them.

Everything below sits in the **model wrapper**, and it splits into two themes:
(a) the objective and the displayed curve are computed by two different code
paths that were never reconciled — background, exchange and the brightness
correction reach one and not the other; (b) the three GUI toggles
(`stochastic_labeling`, `brightness_correction`, `dynamic`) are each tested
alone and never in combination, and the combination is where the species list
stops meaning what the dynamic path assumes it means.

All findings were verified by running the real model on the simulator reader
(`Pda3cSimulatorReader`) in the `arm64` env; no source was changed.

### RF-147
- **Status:** OPEN
- **Severity:** S1 (any failure inside the likelihood is reported as chi2r = 0.0 — a perfect fit — and then kills `fit.run()` with an unrelated `TypeError`)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:498-504` (`TcPdaModel.get_wres`, `except Exception: return np.zeros(0)`) and `:436-439` (`burst_counts`, `except Exception: return None`)
- **Finding:** `get_wres` wraps the whole evaluation in a bare `except` and returns a **zero-length** residual, while `n_points` (`:471-487`) keeps reporting `3 * n_bursts` from the same cached counts. The two disagree, so `sum(wres**2) / (n_points - n_free)` evaluates to `0.0` — the best chi2r the GUI can show. Verified on an 800-burst simulated dataset: healthy `chi2r = 2.487` with `wres.size = 800`; after setting a rate matrix whose state count does not match the species list, `chi2r = 0.0`, `wres.size = 0`, `n_points = 2400` — no log line, no message. Pressing **Fit** then raises `TypeError: Improper input: N=7 must not exceed M=(0,)` from `chisurf/core/math/optimization/leastsqbound.py:436`, which names neither the model nor the real cause. A model that cannot evaluate must report that, not a zero residual: let the exception through (or log it and return `nan`s of the right length so the optimiser fails loudly at the right place).
- **Fix note:**

### RF-148
- **Status:** OPEN
- **Severity:** S1 (with two of the model's own toggles on, the "two exchanging states" are a species and its own mirror image; the multistate route raises and is swallowed by RF-147)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:732-733` (`exchanging, static = species[:2], species[2:]`) and `:652-653` (`_multistate_log_likelihood` stacking one row per species), against `TcPdaSpecies.as_species` at `:240-254`
- **Finding:** `as_species` interleaves each population with its label-swapped mirror when `stochastic_labeling` is on and `F(labeling) < 1`, so the returned list is `[s1, s1_mirror, s2, s2_mirror, …]` — but `_per_burst_log_likelihood` still slices `species[:2]` as "the first two species", which the view-spec panel describes as *"Treat the first two species as two conformational states"*. Verified on a two-species model with `dynamic = True`, `K_ex = 2`, `F(labeling) = 0.8`: `as_species` returns four components and `species[:2]` is `(55, 50, 65)` and its mirror `(55, 65, 50)`, while the **real** second state `(52, 66, 48)` and its mirror are handed to the static branch; the log likelihood moves from -8241.8 to -7898.1 with no warning. Both toggles are user-reachable in `tcpda.view.json` (*Corrections* and *Exchange (dynamic)* panels). The same seam breaks the multistate route harder: with a 2x2 rate matrix and labelling on, `fractions @ blue` gets 4 rows for 2 states and raises `ValueError: matmul: … size 4 is different from 2`, which RF-147 turns into an empty residual. Either expand the mirrors *after* the exchanging pair is chosen, or carry the state identity on the component instead of relying on list position.
- **Fix note:**

### RF-149
- **Status:** OPEN
- **Severity:** S2 (the plotted model curve ignores the background parameters the objective fits with, so a converged fit shows a displaced curve and structured residuals)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:848-904` (`predicted_ratio_histograms`, which takes no background argument) called from `update_model` (`:802-805`) and `get_tcpda_ratio_curves` (`:958-961`)
- **Finding:** The objective adds Poisson background per channel — `_species_log_likelihood` forwards `self.setup.background_blue` / `background_green` into `burst_log_likelihood`, which is the whole point of the factorisation in `pda3c/likelihood.py`. The display path builds its binomial marginals straight from `blue_channel_probabilities` / `green_channel_probabilities` and never sees a background at all; the parameters are only reachable as `TcPdaSetup` properties, and `ThreeColorSetup` (what `predicted_ratio_histograms` receives) does not carry them. Verified on 20 000 simulated bursts at 30/25 signal photons: with zero background, observed and predicted mean proximity ratios agree to <0.001 in all three panels; with 3 background photons per channel, the observed means move to 0.4073 / 0.3358 / 0.4235 while the prediction stays at 0.4281 / 0.3373 / 0.4052 — a 0.02 offset in two of the three panels, i.e. a visible systematic residual on a fit that is in fact converged. The five `BG(*)` parameters are exposed in the *Instrument / corrections* table, so this is the ordinary configuration, not a corner. Pass the two background vectors through and convolve them into the marginal.
- **Fix note:**

### RF-150
- **Status:** OPEN
- **Severity:** S2 (the plotted curve and residual panel of a dynamic fit show the static mixture; nothing on screen responds to `K_ex`)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:790-807` (`update_model`) and `:938-967` (`get_tcpda_ratio_curves`), both calling `predicted_ratio_histograms` with the plain species list
- **Finding:** `update_model` calls `predicted_ratio_histograms(counts, species, setup, …)` unconditionally — an amplitude-weighted static mixture. Neither `dynamic` / `K_ex` (the `_dynamic_log_likelihood` and `_multistate_log_likelihood` routes) nor `brightness_correction` (the per-species photon-number pmfs of `_species_photon_number_pmfs`) has any way into that function. Verified on a two-species model: sweeping `K_ex` over 0, 5 and 50 moves the log likelihood from -7907.7 to -8836.9 to -11488.1 while `model.d[1]` is **bit-identical** at all three (`max|Δ| = 0.000e+00`). So the *Proximity ratios* plot, the residual panel that shares it, and chi2r describe different models, and the user has no visual signal that exchange is switched on. Either route the display through the same per-burst probabilities the likelihood uses, or state on the plot that it is the static projection.
- **Fix note:**

### RF-151
- **Status:** OPEN
- **Severity:** S2 (data and model curve are normalised differently whenever a burst has no photons in one excitation period — i.e. on every dataset with a donor-only population)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:907-925` (`observed_ratio_histograms`, which normalises the concatenation by its *joint* total over bursts with `sizes > 0`) against `:810-845` (`_binomial_marginal_histogram`, which `continue`s on `n <= 0` but keeps those bursts in `total_weight`) and `:904` (`return out / 3.0`)
- **Finding:** The two normalisations agree only when every burst has photons under both excitation periods. `observed_ratio_histograms` divides by `stacked.sum()`, which counts each panel's *valid* bursts; `predicted_ratio_histograms` divides each panel by the *full* burst weight and then by three. A donor-only molecule contributes nothing under green excitation, so `n_green = 0` is the normal case, not a pathology — and the reader (`chisurf/core/experiments/pda/reader.py:278-307`) applies no such filter. Verified on 4000 simulated bursts with 30 % of them zeroed under green excitation: every panel's data area comes out **1.111x** the model area (1481.5 vs 1333.3, and 1037.0 vs 933.3), against exactly 1.000 when no burst is empty. The objective is unaffected (it is the burst likelihood), so this is purely the displayed curve — but an 11 % uniform offset reads as a badly wrong model. Normalise both sides the same way, per panel, over the bursts each panel actually uses.
- **Fix note:**

### RF-152
- **Status:** OPEN
- **Severity:** S2 (the P(R) plot is not a density: species weights are wrong by their width ratio, the grid is non-uniform and stops at 130 A while R is bounded at 200 A)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:970-996` (`get_tcpda_distance_distributions`), the accessor behind the *Distance P(R)* plot in `tcpda.view.json:152-162`
- **Finding:** Three faults in one nine-line loop, all verified. (1) The Gaussian is summed as `amplitude * exp(-0.5 ((r-mu)/sigma)**2)` with **no `1/sigma`**, so a species' plotted area scales with `amplitude * sigma`: two species at amplitude 0.5 with `sigma = 2` and `sigma = 10` plot with areas 0.346 and 0.654 — a 1.89x weight the user never entered. (2) It borrows `cs.core.models.tcspc.fret.rda_axis`, which is **non-uniform** (96 points, 1-130 A, spacing 0.05 A at the bottom and 6.5 A at the top), and then normalises by the bare `density.sum()` — not an integral on that grid, so the curve's height depends on where the species sits. Near 50 A the spacing is 2.58 A while `s(*)` is bounded below at 0.5 A, so a narrow species is undersampled to the point that its peak height is decided by where the nodes happen to fall. (3) The axis stops at 130 A while the mean-distance parameters are bounded at 200 A: a species at 150 A plots as a flat 0.004 — an empty panel with no explanation. (4) The function reads `cs.core.models.tcspc.fret` without importing it; `chisurf/core/models/__init__.py` does not pull in `tcspc`, so on a headless path where no TCSPC model has been touched it raises `AttributeError: module 'chisurf.core.models' has no attribute 'tcspc'` (reproduced). Build a uniform axis spanning the species (mu +/- 5 sigma), normalise as a density, and import the module you use.
- **Fix note:**

### RF-153
- **Status:** OPEN
- **Severity:** S3 (`brightness_correction` truncates the stretched burst-size distribution at the reference grid, so a species brighter than the reference gets a 14 % low photon budget)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:999-1027` (`scale_photon_number_pmf`, `np.interp(grid / brightness, grid, pmf, …)` on the reference `grid`)
- **Finding:** `P_scaled(n) = P(n / brightness)` is evaluated on the *reference* grid, whose length is the largest observed burst size + 1 (`_burst_size_pmfs` uses `np.bincount`). For `brightness > 1` the stretched distribution extends to `brightness * n_max` and everything past `n_max` is dropped, then the remainder is renormalised — so the correction moves the mean less than it should, by an amount that depends on where the observed maximum happened to fall. Verified on a Poisson(30) reference: on a grid ending at 60, `brightness = 1.5` gives mean 44.31 (want 45.00) and `brightness = 2.0` gives 51.75 (want 60.00, 14 % low); widening the same grid to 80 moves those to 45.00 and 59.06, i.e. the answer depends on the grid, not the physics. `relative_brightness` explicitly documents values above one ("above one larger"), which is what a gamma above unity produces, so this is reachable. Interpolate onto a grid extended to `ceil(brightness * (pmf.size - 1)) + 1`.
- **Fix note:**

### RF-154
- **Status:** OPEN
- **Severity:** S3 (the fast-exchange short-circuit fires at half its documented threshold when the rate matrix is spelled as a generator)
- **Location:** `chisurf/core/models/pda3c/tcpda.py:682-683` (`transitions = float(np.abs(rates).sum(axis=0).max()) * window`) against `chisurf/core/fluorescence/kinetics.py:86-108` (`generator_from_rate_matrix`: *"The diagonal is ignored and rebuilt, so a matrix with arbitrary diagonal entries is accepted"*)
- **Finding:** `_multistate_log_likelihood` measures transitions per window off the **raw** `rate_matrix`, including its diagonal — the one part every other consumer of that matrix explicitly discards. For a proper generator the diagonal is minus the column sum, so `np.abs(rates).sum(axis=0)` is exactly twice the escape rate. Verified on the same physical two-state system at 3e5 Hz and a 2 ms window: spelled off-diagonal-only it measures 600 transitions, spelled as a generator 1200, while `generator_from_rate_matrix` maps both to the identical generator. Since `dynamic_max_transitions = 500` decides whether the model samples trajectories or short-circuits to the equilibrium occupancy, two spellings of one system can take different code paths (and the documented meaning of the attribute, "transitions per window", is only right for one of them). Take the estimate from `generator_from_rate_matrix(rates)`'s diagonal.
- **Fix note:**

### RF-155
- **Status:** OPEN
- **Severity:** S1 (the first Run of the pixel-wise MLE on a normal multi-frame FLIM image allocates ~86 GB and the OS kills ChiSurf, losing the session)
- **Location:** `chisurf/plugins/microscopy/img_pixel_mle/core/pixel_mle.py:236-256` (`_extract_vv_vh_fast`, `clsm.get_fluorescence_decay(..., micro_time_coarsening=binning, stack_frames=False)`) reached from `chisurf/plugins/microscopy/img_pixel_mle/gui/view_model.py:455-534` (`run`), with `binning_factor` defaulting to 1 (`core/pixel_mle.py:119`, `gui/pixel_mle.view.json` "Micro-time binning" minimum 1)
- **Finding:** The fast extraction materialises the *whole* per-pixel micro-time cube before slicing the fit window: `n_frames × n_lines × n_pixel × (n_micro_channels / binning)` bytes, **per polarisation**. Verified on `test/data/clsm/PQ_Olympus_MFIS.ht3` (40 frames × 256 × 256, 32 768 micro-time channels): the returned array is `(40, 256, 256, 32768/binning)` uint8 — 0.671 GB at binning 128, i.e. **85.9 GB at the default binning of 1**, twice over. Driving the Image Tools pipeline exactly as documented (Setup → Browser → Next → … → 6. Pixel-wise MLE → Run) killed the process with SIGKILL (exit 137) on both attempts on a 17 GB machine, with no warning, no progress and no error. Narrowing the fit window does not help — the allocation happens before `[start:stop]`. Estimate the size from `n_frames`, the image shape and `n_channels/binning` before allocating and either refuse with a readable message or extract per frame/chunk; nothing in the UI currently hints that binning is a memory setting.
- **Fix note:**

### RF-156
- **Status:** OPEN
- **Severity:** S1 (a standard multi-frame FLIM stack yields a lifetime map with 0.01 % of its pixels fitted, and the GUI has no control to fix it)
- **Location:** `chisurf/plugins/microscopy/img_pixel_mle/api/models.py:9` (`PixelMleSettings` — no `stack_frames` field) and `chisurf/plugins/microscopy/img_pixel_mle/gui/pixel_mle.view.json` (no such section), against `chisurf/plugins/microscopy/img_pixel_mle/core/pixel_mle.py:123` (`stack_frames: bool = False`) and `:351-353` (`clsm_p.stack_frames()`)
- **Finding:** The Qt-free core can sum the frames before fitting, but the transport-agnostic settings dataclass the GUI/RPC/CLI share does not carry the flag, so the GUI always fits each frame separately. Verified on `test/data/clsm/PQ_Olympus_MFIS.ht3` (40 frames, 15.6 M photons ⇒ ~1 photon per pixel per frame): through the GUI at `Min photons = 50` the fit produced **277 fitted rows out of 2 621 440**, and the *Lifetime map* tab shows a handful of scattered dots. The identical core call with `stack_frames=True` (min 20 photons) fits **46 150 of 65 536 pixels in 1.6 s**, median τ = 2.42 ns — a proper lifetime image. Per-frame fitting is the right default only for time-lapse work; expose the flag (a "stack frames" toggle bound to a new `stack_frames` field on the API settings, plumbed into the core settings in `gui/view_model.py:494-520` and `backend/services.py`), and consider defaulting it to on when `n_frames > 1`.
- **Fix note:**

### RF-157
- **Status:** OPEN
- **Severity:** S2 (two different units share one field: the fit window is binned channels, everything that fills it is raw channels)
- **Location:** `chisurf/plugins/microscopy/img_pixel_mle/gui/view_model.py:195-221` (`apply_setup_settings`) and `:230-260` (`apply_calibration`) writing `micro_time_start/stop`, against `chisurf/plugins/microscopy/img_pixel_mle/gui/pixel_mle.view.json` ("Fit start … on the binned micro-time axis") and `core/pixel_mle.py:330-337` (`n_channels = header.number_of_micro_time_channels // binning; stop = min(stop, n_channels)`); IRF side `chisurf/plugins/microscopy/img_pixel_mle/backend/services.py:33-41` (`np.bincount(micro // binning, minlength=n_ch)[start:stop]`)
- **Finding:** The detector setup's micro-time range and the IRF & BG step's convolution range are raw micro-time channels (the step 4 plot's x axis is `micro-time channel`, 0…31 250 for a 1 ps HydraHarp file) and are copied verbatim into fields the MLE interprets on the *binned* axis. With binning 1 the two coincide, which hides the bug — but binning 1 is exactly what RF-155 forces the user off. Verified with binning 128 on `PQ_Olympus_MFIS.ht3`: a transferred window of `0:31250` is silently clipped to the full 0:256 binned axis (any restriction the user set in step 4 is lost), and a transferred `start = 1500` makes `_build_irf_vv_vh` slice `[1500:20000]` of a 256-long histogram and return an **empty IRF (size 0)** without complaint, after which the core raises `ValueError: empty micro-time window: start=1500, stop=256`. Convert the transferred range by the current binning (and re-convert when binning changes), and make `_build_irf_vv_vh` reject a window outside the binned axis.
- **Fix note:**

### RF-158
- **Status:** OPEN
- **Severity:** S2 (a fit that failed is indistinguishable from a tool that was never run — the error message is set and then wiped)
- **Location:** `chisurf/plugins/microscopy/img_pixel_mle/gui/view_model.py:524-534` (`except … self.status_text = f"{stem}: {exc}"; continue` followed unconditionally by `self.status_text = ""`), rendered by `:414-424` (`info_html`)
- **Finding:** `run()` writes the per-file exception into `status_text` and then clears `status_text` for every exit path after the loop, so the message never survives to a repaint. Verified in the GUI: with `Micro-time binning = 128` and a fit window of `1500…20000` (the raw-channel range step 4 transfers, see RF-157) pressing **▶ Run** returns in 0.8 s, `results` stays empty, and the info panel reverts to the generic *"Add confocal (CLSM) TTTR image file(s) and an IRF … then press Run"* instruction — no dialog, no status-bar text, nothing in the log at INFO. The swallowed message is `PQ_Olympus_MFIS: empty micro-time window: start=1500, stop=256`. Only clear the status when at least one file succeeded (or keep an error list and render it), and log failures at WARNING rather than DEBUG.
- **Fix note:**

### RF-159
- **Status:** OPEN
- **Severity:** S2 (a two-colour detector setup is silently collapsed into one ∥/⊥ pair, so photons from different spectral channels are fitted together)
- **Location:** `chisurf/plugins/microscopy/img_pixel_mle/gui/view_model.py:195-211` (`apply_setup_settings`, *"Even routing channels are taken as parallel (∥), odd channels as perpendicular (⊥)"*) via `chisurf/core/fluorescence/mle.parse_detector_setup`; the view (`gui/pixel_mle.view.json`) offers no detector/window selector
- **Finding:** The MLE step takes the *union* of the setup's routing channels and splits it by parity, ignoring which detector each channel belongs to. Verified by walking the Image Tools pipeline with the ordinary MFIS setup — `green = 0,1` and `red = 4,5` — where the step arrives holding `detector_chs_p = [0, 4]`, `detector_chs_s = [1, 5]`: green and red photons land in one fit, and the fitted τ is a mixture. Every other step in the same window is per-detector-window (the maps carry `(green)`/`(red)` columns and a channel combo), so the fit is the odd one out; the parity rule also mis-assigns any single-channel instrument whose channel number is odd (a Leica SP8 PTU detects on channel 1 → ∥ empty). Give the step the same detector-window selector the neighbouring steps have and take ∥/⊥ from that detector's own channel pair.
- **Fix note:**

### RF-160
- **Status:** OPEN
- **Severity:** S2 (a folder full of imaging files lists as empty, with the reason invisible)
- **Location:** `chisurf/plugins/tttr/tttr_image_browser/api/io.py:44-90` (`allowed_exts_for_setup`) used by `:142-180` (`list_files`), surfaced through `chisurf/plugins/tttr/tttr_image_browser/gui/view_model.py:75-86` (`_rescan`) and `:254-259` (`info_html`)
- **Finding:** The Browser silently restricts its file list to the extensions implied by the **File Type** of the shared detector setup. The only shipped setup, `BS`, declares `SPC-130`, so opening a folder of PicoQuant files shows nothing at all: verified by opening a folder holding `PQ_Olympus_MFIS.ht3` and `crn_clv_mirror.ht3` — the list is empty and the summary reads *"0 image(s) in data"*; switching the setup's File Type to `HT3` lists both immediately. Nothing in the panel mentions the filter, and the Browser is the window's *default* panel, so this is the first thing a new user meets. Either list every supported TTTR file and mark the ones the current setup cannot read, or say so in the summary line ("0 of 2 files match the setup's file type `SPC-130`").
- **Fix note:**

### RF-161
- **Status:** OPEN
- **Severity:** S2 (Leica PTU scans are analysed with a wrong image geometry — 14 of 512 lines — and the only signal is a console warning)
- **Location:** `chisurf/core/fluorescence/imaging/pixel_maps.py:123-128` (`build_clsm`: *"markers auto-detected from header"*, `tttrlib.CLSMImage(tttr, channels=…, fill=True)`) and `chisurf/plugins/tttr/tttr_image_browser/core/image.py:355` — no reading-routine/marker settings anywhere in `chisurf/plugins/microscopy/imaging_tools`, unlike `chisurf/plugins/microscopy/clsm/core/clsm_settings.yaml` which carries `Leica SP5`/`Leica SP8`/`MFIS Olympus` presets
- **Finding:** Every Image Tools step builds its CLSM image from tttrlib's header auto-detection, which fails for the two Leica files shipped in `test/data/clsm`. Verified: `Leica_SP8.ptu` auto-detects as **1 frame × 14 lines × 512 px** (`WARNING: no complete frames; salvaging 1 frame(s) with 14 line(s)`) against **93 × 512 × 512** with the SP8 routine (`marker_frame_start=[4,6]`, `marker_line_start=1`, `marker_line_stop=2`, `marker_event_type=15`, `reading_routine="SP8"`); `Leica_SP5.ptu` auto-detects as **1 × 7921 × 256** where CLSM-Draw's `Leica SP5` preset gives 230 × 256 × 256. The Browser mosaic is a 14-line stripe and the intensity/N&B/phasor/MLE maps built from it are meaningless — with no in-window way to correct it, since the setup panel's *TTTR Reading routine* box has file type and micro-time binning but no CLSM markers. Carry the CLSM-Draw preset (or at least the reading routine + marker fields) through the shared setup into `build_clsm`, and surface the "no complete frames" salvage in the UI rather than on stderr.
- **Fix note:**

### RF-162
- **Status:** OPEN
- **Severity:** S3 (library-side crash; needs triage in the TTTR library, chisurf users are not currently hit)
- **Location:** the TTTR library's `CLSMImage` marker auto-detection (`WARNING: no complete frames; salvaging …` path), reached from `chisurf/core/fluorescence/imaging/pixel_maps.py:123-128`
- **Finding:** `python -c "import tttrlib; t = tttrlib.TTTR('test/data/clsm/Leica_SP8.ptu'); tttrlib.CLSMImage(t, channels=[1], fill=True)"` **segfaults** (exit 139) in a bare interpreter, before the warning is printed; `fill=False` and `channels=[0]` crash identically, so it is the construction/auto-detection, not the fill. The same call preceded by `import chisurf` prints the salvage warning and returns a (wrong, see RF-161) 1 × 14 × 512 image, which is why the GUI never crashes here. Reproduced with tttrlib 0.27.0 in the `arm64` env. Worth pinning down in the library — a stray segfault in the marker-salvage path will eventually reach a chisurf entry point that does not import the whole package first (e.g. a plain worker process).
- **Fix note:**

### Review 2026-07-26 (11) — burst statistics: the burst table, BVA and RASP

Slice: the per-burst statistics layer, chosen because it has no findings on
record yet and everything downstream (E/S histograms, BVA, H2MM, PDA, MLE) reads
its numbers. Files read in full: `chisurf/core/fio/fluorescence/burst.py`
(`generate_burst_dataframe`, `write_bur_file_old`), `chisurf/core/math/signal.py`
`find_bursts`, and the burst core `chisurf/core/fluorescence/burst/`
(`background.py`, `bva.py`, `recurrence.py`, `es.py`, `count_rate.py`,
`burst.py`, `utils.py`), against their consumers in
`chisurf/plugins/burst/burst_analysis/api/workflow.py`,
`chisurf/plugins/burst/burst_bva/core/computation.py` and
`chisurf/plugins/burst/burst_background/`.

What holds up: the E/S correction chain in `es.py` is sound — I checked the
claimed two-colour reduction of `corrected_es_general` by hand
(`emission = [[1, α], [0, γ]]`, `excitation = [[1, δ], [0, 1]]` really does give
`E = F_da / (γ·F_dd + F_da)`), and `corrected_es_matrix`'s coupled donor budget
reduces to `corrected_es` for a single acceptor. The Poisson-MLE tail fit in
`background.py` and the pair-counting in `same_molecule_probability` (ordered
pairs vs `λ²(T−τ)dτ`, edge correction included) are both right.

Everything below was verified by running the real code in the `arm64` env; no
source was changed. Findings RF-163..RF-168.

### RF-163
- **Status:** OPEN
- **Severity:** S1 (every burst in every `.bur` loses its last photon: `Number of Photons` is one short and `Count Rate (KHz)` is biased low by `N/(N+1)`)
- **Location:** `chisurf/core/fio/fluorescence/burst.py:432-435` and `:451` (`generate_burst_dataframe`), against its producer `chisurf/core/math/signal.py:436-498` (`find_bursts`)
- **Finding:** `generate_burst_dataframe` uses **two different conventions for `stop` in the same four lines**. `dur = (macro[stop] - macro[start])` and `meanm = (macro[stop] + macro[start]) / 2` index the photon *at* `stop`, i.e. treat it as the inclusive last photon; `npix = stop - start` and `sl = slice(start, stop)` (which drives every per-detector and per-window count below) treat it as an exclusive end. `find_bursts` — the producer for the burst-selection API, the photon-filter wizard and the trace browser — documents and doctests its pairs as **inclusive** (`chisurf/core/math/signal.py:454`, `:497` "stop is exclusive, so subtract 1"), so the count side is the wrong one and the last photon of every burst is dropped from all counts. Verified on a synthetic 11-photon stream (10 burst photons 1 µs apart, then one background photon 1 ms later): `find_bursts` returns `[[0, 9]]` and the table reports `Number of Photons = 9`, `Number of Photons (g) = 9`, `Duration = 0.009 ms`, `Count Rate = 1.000 kHz` against the true 10 photons / 1.111 kHz. The bias is `1/N` per burst, so it is largest exactly where burst counts matter most — the short, dim bursts. Fixing it means `stop + 1` in the slice and `stop - start + 1` in the count (or normalising the producer), and it will move every existing burst table, so the fix must also re-baseline the counts asserted in `chisurf/plugins/burst/burst_selection/tests/test_real_data.py` — note that test compares two chisurf paths to each other, not to a reference implementation, so it never caught this. The now-unreachable `write_bur_file_old` (`:203-217`) carries the identical mix, plus a guard (`stop_idx > n_ph`) that admits `stop_idx == n_ph` and then indexes `macro_times[n_ph]`.
- **Fix note:**

### RF-164
- **Status:** OPEN
- **Severity:** S2 (a purely static, shot-noise-only sample reports 31–41 % "dynamic" bursts, and the number drifts with burst length)
- **Location:** `chisurf/plugins/burst/burst_analysis/api/workflow.py:210-225` (`Bva.dynamic_fraction`)
- **Finding:** `dynamic_fraction` is documented as the "fraction of bursts above the shot-noise static line (dynamics)" and computes exactly that: `mean(stds > expected)`, where `expected` is the *expected* standard deviation from `compute_static_bva_line`. But a burst's measured slice-SD scatters around that expectation, so a sample with no dynamics at all does not give 0 — it gives whatever fraction of the SD sampling distribution lies above its own mean. Verified by simulating purely static bursts (per-slice counts drawn from `Binomial(5, E)`, `E ~ U(0.1, 0.9)`, 3000 bursts) and feeding them straight into `Bva`: **0.308** at 5 slices per burst, **0.353** at 10, **0.410** at 20. So the metric has a large non-zero null baseline *and* that baseline grows with burst duration, which makes it non-comparable between datasets and between detection settings. Standard BVA compares against a confidence band of the static line (e.g. the simulated 95th percentile per bin), not the mean; `compute_static_bva_line` already draws `n_samples` per bin, so the percentile is one line away. Until then the number should not be presented as a dynamics fraction.
- **Fix note:**

### RF-165
- **Status:** OPEN
- **Severity:** S2 (the headless CLI and the GUI report different background rates for the same file, and the PAM parity the module docstring claims holds for neither)
- **Location:** `chisurf/core/fluorescence/burst/background.py:144-150` (`tail_fraction: float = 0.2`) vs `:185-191` (`tail_fraction: float = 0.8`), with `chisurf/plugins/burst/burst_background/cli.py:43` (`0.2`) against `chisurf/plugins/burst/burst_background/view_model.py:148` (no argument → `0.8`) and `chisurf/core/fluorescence/burst/irf_bg.py:160` (`0.8`)
- **Finding:** The same parameter has two different defaults in the same module. `estimate_background_from_interphoton_times` defaults to `0.2` and its docstring explains that this "reproduces the PAM criterion `dt > max(dt)/5`", while `estimate_background_from_bursts` — the documented "main public entry point" — defaults to `0.8`, i.e. the last 20 % of the range and *not* the PAM criterion the module docstring at `:1-10` claims to follow. The drift reaches the user: the Burst Background CLI passes `0.2` while the GUI view-model calls `background_diagnostics_from_bursts(tttr, detectors)` with no argument and gets `0.8`, so the same file analysed headlessly and in the window yields different background rates and hence different corrected E/S. Verified on a synthetic mixture (200 k background intervals at 2 kHz plus 50 k burst intervals): `0.2` → 2.431 kHz, `0.8` → 2.079 kHz on identical input. Pick one default, state which convention it is, and make the diagnostics plot and the estimator share it by construction.
- **Fix note:**

### RF-166
- **Status:** OPEN
- **Severity:** S2 (an empty recurrence window returns an all-NaN histogram instead of zeros, so the RASP plot silently draws nothing)
- **Location:** `chisurf/core/fluorescence/burst/recurrence.py:171` (`rec_h, _ = np.histogram(rec, bins=edges, density=True)`)
- **Finding:** `recurrence_efficiencies` legitimately returns an empty array whenever no burst recurs in the chosen window — a narrow `dt_range_s`, an `e_range` that selects nothing, or simply a sample without recurrence; the module's own test `test_recurrence_efficiencies_respects_time_window` exercises exactly that. `np.histogram` with `density=True` then divides by `n.sum() == 0` and returns **all NaN** plus an unsuppressed `RuntimeWarning: invalid value encountered in divide`. Verified through the public API: `recurrence_histogram([0, .01, 1, 1.01], [.2, .8, .2, .8], (0, .4), (5, 10), bins=5)` → `[nan nan nan nan nan]` and the warning. `Recurrence.plot` (`workflow.py:373-392`) bars those NaNs, so the recurrence overlay simply does not appear and nothing says why; any downstream `sum`/`argmax` on the result is NaN too. Return zeros for an empty input (and guard the same call for `e_all`).
- **Fix note:**

### RF-167
- **Status:** OPEN
- **Severity:** S2 (one noisy large-lag bin stretches the reported recurrence window ~4×, i.e. the window in which "the same molecule" is assumed)
- **Location:** `chisurf/plugins/burst/burst_analysis/api/workflow.py:345-353` (`Recurrence.recurrence_time`)
- **Finding:** The method is documented as the "largest lag at which `P_same` still exceeds `threshold`" and used as "a practical upper bound for the recurrence-time window", but it takes `tau[p_same >= threshold].max()` over *all* bins — not the first crossing. `P_same = 1 - 1/G` is computed per log-spaced lag bin, and at large lags the bins hold few pairs, so `G` fluctuates upward and single isolated bins cross the threshold long after the real decay. Verified on six simulated recurrence datasets (300 molecules over 600 s, 2–3 bursts each within a 50 ms recurrence window, 50 bins): five seeds give 0.045–0.051 s, matching the true window, while seed 2 returns **0.204 s** because bin 38 alone crosses — the contiguous run of above-threshold bins ends at index 27 (0.045 s) in every case. A 4× over-long window is not a rounding error here: it decides which recurring bursts are treated as the same molecule. Take the first lag at which `P_same` drops below the threshold (end of the leading contiguous run), and return NaN when even the first bin is below it.
- **Fix note:**

### RF-168
- **Status:** FIXED (2026-07-26)
- **Severity:** S3 (the NumPy docstring is a no-op string expression; `help()`, tooltips and generated docs show only the one-line summary)
- **Location:** `chisurf/core/fluorescence/burst/bva.py:11-42` (`compute_static_bva_line`) and `:110-112` (`compute_bva`)
- **Finding:** `compute_static_bva_line` opens with the one-liner `"""Compute static BVA line"""`, then `import pandas as pd`, and only then the 28-line NumPy docstring — which, following a statement, is a discarded expression, not `__doc__`. Verified: `compute_static_bva_line.__doc__` is exactly `'Compute static BVA line'`, so every parameter description (`prox_mean_bins`, `number_of_photons_per_slice`, `n_samples`) and the returns block are invisible to `help()`, to Sphinx and to the ruff `D` rules that are supposed to enforce them. The `import pandas as pd` that displaced it is itself unused — in both `compute_static_bva_line` and `compute_bva`, whose identical "lazy import to avoid circular import" line at `:112` is likewise never referenced. Move the text into the real docstring and drop both imports. While here: `chisurf/plugins/burst/burst_bva/core/computation.py:80-91` defines a second, vectorized `compute_static_bva_line` with the same name and signature (numerically equivalent — `total_photons` in the core version is `number_of_photons_per_slice` by construction, so its `np.where` guard is dead); `Bva.plot`/`dynamic_fraction` use the plugin copy while `chisurf.core.fluorescence.burst` re-exports the core one. One of the two should go.
- **Fix note:** The 28-line text is now the real `__doc__` of
  `compute_static_bva_line` (verified by asserting on `__doc__`), and both unused
  `import pandas as pd` lines are gone. The duplicate was resolved in favour of
  the vectorized body — one binomial draw of shape `(n_samples, n_bins)` instead
  of a Python loop over bins — moved into the core module, with the dead
  `np.where(total_photons > 0, …)` guard replaced by an explicit
  `number_of_photons_per_slice <= 0` early return (the vectorized form would
  otherwise divide by zero, which the loop form did not).
  `chisurf/plugins/burst/burst_bva/core/computation.py` re-exports the core
  function rather than redefining it, so `Bva.plot` / `Bva.dynamic_fraction` and
  the GUI tool now share the one implementation the package re-exports.
  `test/fluorescence/test_bva_static_line.py` pins the docstring, the
  single-implementation identity, agreement with the binomial shot-noise limit
  `sqrt(E(1-E)/n)`, and the zero-photon edge case.

## GUI-tester run — Decay Analysis hub (2026-07-26)

Drove the **Spectroscopy:Decay Analysis** hub headlessly (`QT_QPA_PLATFORM=offscreen`,
arm64 env, private RPC port) the way a user does: a `Lifetime` fit of
`test/data/tcspc/ibh_sample/Decay_577D.txt` with `Prompt.txt` as IRF
(χ²ᵣ = 1.6259, τ = 4.1494 ns), then panel *2. MaxEnt MEM* (Refresh → Run →
L-curve), panel *1. IRF Estimation* on the VV/VH files in
`test/data/tcspc/Jordi/`, and panel *5. VV/VH G-Factor*. Screenshots at every
step. The MEM analysis itself is sound — 1.2 s to a distribution peaked at
τ = 4.219 ns, ⟨τ⟩ₓ = 4.108 ns, `chisq = 1.352`, flat weighted residuals, matching
the discrete fit. Everything below is a defect seen while driving; no source was
changed. Use case: [/usecases/decay-analysis-maxent.md](/usecases/decay-analysis-maxent.md).
Findings RF-169..RF-173.

### RF-169
- **Status:** OPEN
- **Severity:** S2 (every IRF estimation — including the successful ones — ends in a red error dialog, and the error handler raises again, uncaught)
- **Location:** `chisurf/plugins/fluorescence_decay/irf_estimator/gui/tool.py:762-770` (`IRFEstimatorTool.estimate_irf`)
- **Finding:** `estimate_irf` finishes the estimation, updates `irf_data`, the result fields and every plot, and then calls `self._status_bar.showMessage("IRF estimation completed", timeout=5000)`. `QStatusBar.showMessage` takes `msecs`, not `timeout`, so this raises `TypeError: showMessage(self, message: Optional[str], msecs: int = 0): 'timeout' is not a valid keyword argument` on the *success* path. The surrounding `except Exception` then shows a modal `QMessageBox.critical(self, "Estimation Error", str(e))` quoting that PyQt signature at the user, and its own `self._status_bar.showMessage("IRF estimation failed", timeout=5000)` (`:769`) raises the identical `TypeError` a second time — this one escapes the handler entirely (the `traceback.print_exc()` below it is unreachable), so the Qt slot terminates on an uncaught exception. Verified twice in the same session, on `02_18-577+7.5uM(577)UP_8ps.dat` and on `H2O_8-0 ps_2048 ch.dat`: the estimate takes 0.12 s, the results (`τ`, `k`, `A`, `C`) and the plot are correct and visible *behind* the dialog, and the status bar stays frozen on "Estimating IRF…" because the "completed" message never lands. In the headless driver the modal blocked the run for minutes. Both call sites need `msecs=`; `_setup_statusbar` (`:155`) already uses the positional form correctly.
- **Fix note:**

### RF-170
- **Status:** OPEN
- **Severity:** S2 (the advertised "detect optimal nu via L-curve corner" never fires — 5.5 s of computation is discarded on every dataset)
- **Location:** `chisurf/plugins/fluorescence_decay/maxent_decay/gui/gui_run.py:167` (`_MaxentRunMixin._run_lcurve`)
- **Finding:** The corner is only accepted if `np.any(mask) and getattr(chisurf, "math", None) is not None` — but `chisurf.math` no longer exists (the package moved to `chisurf.core.math`; `getattr(chisurf, "math", None)` returns `None`), so `corner_idx` stays `None` and `self.spin_nu.setValue(...)` at `:174-177` is never reached, on any data. Everything else in the button works: the 16-point `nu` scan runs, the L-curve is plotted, and the detector itself is fine — `chisurf.core.math.regularization.discrete_lcurve_corner` is importable and returns `6` on a synthetic L-curve. Verified through the GUI: `nu` read `0.001` before the click and `0.001` after a 5.55 s scan, although the scanned grid is `10**linspace(-5, -1, 16)`, which contains no point at `1e-3` — so a working corner selection could not have left the value unchanged. The `chisurf` name here comes from `ensure_qt_stack()`, so the stale reference is invisible to a grep for `import chisurf.math`. Two lines below, the plot itself is drawn unconditionally, which is why the button looks like it worked.
- **Fix note:**

### RF-171
- **Status:** OPEN
- **Severity:** S2 (lifetimes and the whole time axis are reported in the wrong unit — 125× off on the test file — and the control that would fix it is disabled)
- **Location:** `chisurf/plugins/fluorescence_decay/irf_estimator/gui/tool.py:568` (`load_decay_file`, `dt = float(metadata.get("dt", 1.0))`) with `:190-196` (`dt_spinbox.setEnabled(False)`)
- **Finding:** The panel's own file filter is `VV/VH Files (*.dat)`, and `chisurf.core.fio.read_vv_vh` returns `metadata = {}` for legacy VV/VH files (`_parse_footer_metadata` finds no footer), so `dt` silently falls back to **1.0 ns/channel**. The *Time/Channel (ns)* spin box is created with `setEnabled(False)` and the tooltip "automatically set from data", so the user cannot correct it. Verified on `test/data/tcspc/Jordi/H2O_8-0 ps_2048 ch.dat` (8 ps/channel, the value is only in the file name): the status bar reads `Time: 0.00 to 2047.00 ns (Δ = 2047.00 ns, dt = 1.0000 ns, 2048 pts)`, the plot's x axis runs to 2000 **ns** for a 16.4 ns record, and *Estimation Results* reports `Lifetime (τ) = 27.6563 ns` / `Decay Rate (k) = 0.036158 ns⁻¹` where the true tail lifetime is 27.66 channels × 8 ps = **0.221 ns**. `estimate_irf` propagates the same `dt` into `time_axis`, `lifetime_ns` and `decay_rate_ns` (`core/estimation.py:74-88`), so the saved/transferred IRF carries the wrong axis too. Either make the box editable when the file brings no `dt`, or refuse to display a lifetime in ns until one is supplied.
- **Fix note:**

### RF-172
- **Status:** OPEN
- **Severity:** S2 (a nonsense lifetime is presented as a result to four decimals, with no warning and with the plot rendered unreadable)
- **Location:** `chisurf/core/fluorescence/tcspc/irf_estimation.py` (`IRFEstimator.find_t0_t1` → `fit_exponential`), surfaced by `chisurf/plugins/fluorescence_decay/irf_estimator/gui/tool.py:723-764` (`estimate_irf` → `_update_results`)
- **Finding:** `find_t0_t1` can select a tail window inside the **zero-padded** end of a decay, and the exponential fit that follows is then fitted to nothing. Verified on `test/data/tcspc/Jordi/02_18-577+7.5uM(577)UP_8ps.dat` (VV half: 2048 channels, peak at 380, last non-zero channel 1806): `find_t0_t1(window_length=11, polyorder=3)` returns `t0 = 1807`, `t1 = 2047`, and `fit_exponential` returns `k = 470.85` per channel, i.e. a decay to 1/e in **1/470 of one channel**. The GUI prints that straight into *Estimation Results* as `Lifetime (τ) = 0.0021 ns`, `Decay Rate (k) = 470.850919 ns⁻¹`, and the "IRF ⊗ Exp (Forward Model)" overlay degenerates into a dense comb spanning the whole plot that hides both the measured decay and the estimated IRF (screenshot). The neighbouring file `H2O_8-0 ps_2048 ch.dat` takes the good branch (`t0 = 381`, `k = 0.0362`/channel) from the same button with the same settings, so this is data-dependent and silent. A sanity check on the fitted rate (e.g. `1/k` must be several channels and `t0` must sit within the region carrying counts) belongs either in `find_t0_t1` or in front of `_update_results`.
- **Fix note:**

### RF-173
- **Status:** OPEN
- **Severity:** S2 (the calibration constant is biased upward at low counts, and the uncertainty shown next to it is ~19× too large)
- **Location:** `chisurf/plugins/vv_vh_g_factor/core/calculations.py:194-210` (`calculate_g_factor_core`)
- **Finding:** Tail matching is implemented as the **mean of the per-channel ratios** `VV[i]/VH[i]` and the reported *StdDev* is `np.std` of that same population. Both are wrong for photon-counting data: `E[A/B] > E[A]/E[B]` by Jensen's inequality, so the mean of ratios is biased upward exactly where tails are dim, and the population spread of per-channel ratios is not the uncertainty of G — it does not shrink as the matching region grows. Verified by simulation: two independent Poisson streams at 10 counts/channel over 4000 channels with a **true ratio of exactly 1.0** give mean-of-ratios `1.1172` (SD 0.585) against ratio-of-sums `0.9966`. Verified through the GUI on `test/data/tcspc/Jordi/H2O_8-0 ps_2048 ch.dat` with the panel's own default matching region (70–90 % of the record, channels 1433–1843, ≈ 12 counts/channel): the panel shows `G-Factor 1.7418`, `StdDev 1.3884`, where the ratio of summed counts over the same region is `1.3211` and the standard error of the mean is `0.0718`. A third bias comes from the validity filter at `:203` — `g_factors_uncorrected > 0` drops the 36 of 410 channels where `VV == 0`, i.e. exactly the low-ratio ones. The estimator should be `sum(VV)/sum(VH)` over the region with a Poisson-propagated error (and the same for the background-corrected branch at `:230+`, which shows the same pattern).
- **Fix note:**

### Review 2026-07-26 (12) — the action layer (`chisurf/core/actions/`)

Slice: the action/dispatch layer, chosen because it mediates *every* state change
in the app (`CLAUDE.md`: "State changes are mediated by `chisurf/core/actions/`")
yet had a single finding on record. Files read in full: `_infra.py`
(`ActionSpec`, `ActionRegistry`, `ActionDispatcher`), `_decorator.py`,
`__init__.py`, and all five action modules (`dataset_`, `fit_`, `model_`,
`parameter_`, `project_actions.py`), against the lazy accessors in
`chisurf/__init__.py:256-264`, the scheduler installed in
`chisurf/gui/__init__.py:54-77`, and the GUI dispatch sites in
`chisurf/gui/autoform/sections/builtin.py`.

What holds up: `canonical()` / `resolve_name()` really are collision-free for
names with underscores inside a verb; `filter_payload` correctly drops surplus
payload keys for handlers without `**kwargs`; the leading-edge half of the
debounce behaves as its test asserts.

Everything below was reproduced by running the real code in the `arm64` env; no
source was changed. The debounce machinery is where it concentrates — its own
tests (`test/macros/test_action_dispatcher.py`) cover the leading edge and exact
duplicates only, never the trailing edge, the scheduler, the registry/dispatcher
identity, or concurrency. Findings RF-174..RF-180.

### RF-174
- **Status:** OPEN
- **Severity:** S1 (in the wrong import order every one of the 60 registered actions dispatches to nothing — `dispatch()` logs "unknown action" and returns `None`)
- **Location:** `chisurf/__init__.py:256-264` (`__getattr__` branches for `action_dispatcher` / `action_registry`)
- **Finding:** The lazy `action_dispatcher` branch calls `importlib.import_module("chisurf.core.actions._infra")`, which imports the **package** `chisurf.core.actions`, whose `__init__` imports the five action modules; every `@action` there does `getattr(cs, "action_registry")`, which re-enters `__getattr__` and builds *and caches* a dispatcher `D_inner` — the 60 actions register into `D_inner.registry`. The outer frame then resumes, builds its own `D_outer` and overwrites `globals()["action_dispatcher"]`, so the cached registry belongs to a dispatcher nobody dispatches through. Verified in a fresh interpreter: after `d = cs.action_dispatcher; r = cs.action_registry`, `r is cs.action_dispatcher.registry` is **False**, `len(cs.action_registry.list_actions()) == 60` while `len(cs.action_dispatcher.registry.list_actions()) == 0`, and `chisurf.core.actions.dispatch("fit.add.start", {})` returns `None` with `WARNING dispatch('fit.add.start'): unknown action`. This is not hypothetical: `import chisurf.gui; chisurf.gui.initialize_gui_executors()` alone reproduces it (`chisurf.gui` does not import `chisurf.core.actions`, and `chisurf/gui/__init__.py:58` touches `cs.action_dispatcher` first) — the path taken by the standalone `csg_*` plugin GUIs and by `run_on_gui_thread` (`chisurf/gui/__init__.py:136`) when it initializes executors from a worker thread. The full main-window import set happens to import `chisurf.macros` first, so the invariant holds there and the breakage stays latent. Fix: have `__getattr__` return an already-cached `globals()` entry instead of rebuilding (or derive the registry without re-entering), and pin the invariant `cs.action_registry is cs.action_dispatcher.registry` in a test that imports `chisurf.gui` first.
- **Fix note:**

### RF-175
- **Status:** OPEN
- **Severity:** S1 (in the GUI every debounced trailing-edge action is silently dropped, so the swallowed state change is lost rather than deferred)
- **Location:** `chisurf/gui/__init__.py:66-73` (`qt_scheduler`) driven from `chisurf/core/actions/_infra.py:232-255` (`_schedule_trailing_edge`)
- **Finding:** `_schedule_trailing_edge` runs `delayed_execute` on a `threading.Timer` thread, and that callback invokes the scheduler, whose whole body is `QtCore.QTimer.singleShot(0, lambda: func(**kwargs))`. A `QTimer` started on a plain Python thread has no event loop to fire it, so the callback **never runs** — and the `except` around it only catches a raised exception, which there is none, so the fallback direct call never triggers either. Verified with an offscreen `QApplication`: `singleShot(0, cb)` called from the main thread fires within one `processEvents` round, the identical call made from a `threading.Timer` thread has still not fired after 1.5 s of `processEvents`. End to end through the real dispatcher (`initialize_gui_executors()` then two `execute()` calls inside the window): the handler runs **once** — the debounced second call is swallowed at `:278` and its trailing edge is dropped. So in the GUI a debounced action (`parameter.value`, `parameter.fixed`, `parameter.bounds.*`, `fit.update`, `model.update`, `fit.mask_set`, `fit.range.set`) whose repeat lands inside the window loses that change permanently and silently. The scheduler must post to the GUI thread from any thread — `QMetaObject.invokeMethod` on a main-thread `QObject` with `Qt.QueuedConnection`, or the `_GuiExecutor` signal that already exists two functions above.
- **Fix note:**

### RF-176
- **Status:** OPEN
- **Severity:** S1 (a value written to one fit suppresses the same-named parameter write to a *different* fit)
- **Location:** `chisurf/core/actions/parameter_actions.py:7,15,51,59` (`debounce_keys=("parameter_name",)`) with `chisurf/core/actions/_infra.py:192-196` (`_fingerprint`)
- **Finding:** The debounce identity of `parameter.value` (and `parameter.fixed`, `parameter.bounds.set`, `parameter.bounds.on`) is `parameter_name` alone, but the handler's target is `fit_index` — which is *not* part of the identity, and `dispatch(name, payload)` (`_decorator.py:101`) never passes a `source_uid`, so the third fingerprint component is always empty. Two fits therefore share one debounce slot: verified with the real dispatcher, `parameter.value{tau1, 1.0, fit 0}` followed within 200 ms by `parameter.value{tau1, 9.0, fit 1}` applies only the fit-0 write immediately; the fit-1 write is deferred to a Timer thread — and with RF-175 in play, dropped. This is on a hot path: `builtin.py:1202-1220` (`_read_values`, the "read values from another fit" button) dispatches `parameter.value` in a loop over every parameter of the target group with an explicit `fit_index`, so pressing it on two fits in quick succession, or any linked/global update that touches the same parameter name in several fits, silently loses writes. `fit_index` belongs in `debounce_keys`.
- **Fix note:**

### RF-177
- **Status:** OPEN
- **Severity:** S2 (the debounce on `fit.range.set` cannot coalesce the drag it exists for, and its fingerprint cache grows without bound)
- **Location:** `chisurf/core/actions/fit_actions.py:135` (`fit.range.set`, `debounce_ms=60`, no `debounce_keys`), same pattern at `:60`, `:113`, `:119`, `:127` and `chisurf/core/actions/model_actions.py:163`
- **Finding:** With no `debounce_keys`, `_fingerprint` hashes the **whole** payload, so two calls only coalesce when every value is identical. For `fit.range.set` the payload *is* the changing quantity: dragging a range slider produces a different `(xmin, xmax)` at every step, so nothing is ever debounced. Verified: 200 successive `fit.range.set` calls with a moving `xmax`, all inside the 60 ms window, produce **200** handler calls and **200** history records; ten identical calls produce zero. The decorator documents `debounce_ms` as "coalesce repeated identical calls", which is what it does — but the actions were configured expecting drag coalescing. The same run leaves 200 entries in `ActionDispatcher._recent_fingerprints`, which has no eviction anywhere in `_infra.py`: every distinct payload of a debounced action is retained for the lifetime of the process, i.e. one entry per range the user ever dragged through. Give the range/update actions an identity that excludes the changing values (`("fit_index",)`) and expire fingerprints older than the window.
- **Fix note:**

### RF-178
- **Status:** OPEN
- **Severity:** S2 (two *different* fit masks collide on one fingerprint and the second is treated as a duplicate)
- **Location:** `chisurf/core/actions/_infra.py:178-183` (`_safe_json`) with `chisurf/core/actions/fit_actions.py:127` (`fit.mask_set`, `debounce_ms=200`, payload key `mask`)
- **Finding:** `_safe_json` calls `json.dumps(..., default=str)`; a NumPy mask is not JSON-serializable, so it falls through to `str(array)` — and NumPy *truncates* the repr of any array longer than 1000 elements. Verified: two 5000-element boolean masks differing in exactly one element both stringify to `"[False False False ... False False False]"`, so `_safe_json(a) == _safe_json(b)` is `True`. Since `fit.mask_set` is debounced with no `debounce_keys`, the two distinct masks share a fingerprint and the second one is swallowed as a repeat (and, per RF-175, its trailing edge is then dropped in the GUI). Any payload carrying a large array has the same problem. Either hash the array content (`ndarray.tobytes()`/`hashlib`) or exclude non-JSON payload values from the identity instead of silently mapping them onto a truncated repr.
- **Fix note:**

### RF-179
- **Status:** FIXED
- **Severity:** S2 (a concurrent call to the same action bypasses validation, debounce and history while still mutating state)
- **Location:** `chisurf/core/actions/_decorator.py:71-89` (`wrapper._executing`), beside the correctly thread-local `is_dispatching` at `:8-13`
- **Finding:** The re-entrancy guard is stored as an attribute **on the wrapper function**, i.e. shared by every thread, while the flag right above it (`_threading_local.is_dispatching`) is deliberately thread-local. So while thread A is inside `dispatch`, any call to the same action from thread B sees `_executing == True` and takes the `return func(*args, **kwargs)` shortcut: the body runs and mutates state, but the payload is never validated, the debounce never applies, and nothing is recorded in history. Verified: with one thread held inside a slow `test.slow` handler, a concurrent `slow("not-an-int")` **executed the body** with a payload the `{"x": int}` schema rejects, and only one history record exists for the two calls. Actions are dispatched from worker threads (fit runs, staged loading, the Timer thread of RF-175), so this is reachable. Make `_executing` thread-local like its neighbour.
- **Fix note:** The guard moved off the wrapper function onto the same
  `threading.local()` that already carries `is_dispatching`: a per-thread set of
  action names (`_executing_actions()`), added on entry and discarded in the
  `finally`. Same-thread re-entrancy still short-circuits to the bare body;
  another thread now gets a full `dispatch` — validation, debounce, history.
  Pinned by `test/macros/test_action_reentrancy.py` (2): the nested same-thread
  call records exactly one history event, and a concurrent bad-typed call made
  while a handler thread is parked inside the body raises `TypeError` from the
  schema instead of running. Both probe actions register into a scratch
  registry/dispatcher so the process-wide action vocabulary stays untouched.
  **Fixed in passing:** `test/macros/test_actions.py` restored
  `cs.action_dispatcher` in `tearDown` but not `cs.action_registry`, leaking its
  scratch registry (with `test.*` actions and no builtins) into the rest of the
  session — which is why `test/history/test_vocabulary.py` failed whenever
  `test/macros` ran before it; and
  `test_action_dispatcher.py::test_chisurf_action_execute_accessor` asserted
  `project.save` returns `None` or a dict when it returns the written archive
  `Path`, and wrote that archive to a literal `C:/tmp/demo` directory inside the
  repo. Both fixed; the combined run is now green.

### RF-180
- **Status:** OPEN
- **Severity:** S3 (Qt imported from `chisurf/core/`; `project.load` silently does half its job headlessly, and core reaches into a plugin's GUI package)
- **Location:** `chisurf/core/actions/project_actions.py:83-89` (`load_project`) and `:111` (`archive_project`)
- **Finding:** `load_project` — a `chisurf.core` action — does `from qtpy import QtCore` and schedules the second half of the load with `QtCore.QTimer.singleShot(0, lambda: restore_gui_from_fits(fit_uids))`. In any Qt-free context (`csc`, `python -m chisurf.server`, a plugin backend) that import is the only Qt dependency in the whole `core/actions` package, and where Qt is importable but no event loop is running the timer never fires (same mechanism as RF-175): `load_project_data` has already mutated `cs.fits`, the restore step never runs, and the action returns `None` with nothing logged. The GUI-restore step belongs behind the existing GUI hop (`chisurf.gui.run_on_gui_thread`) or in a GUI-side listener, not in core. In the same file `archive_project` imports `chisurf.plugins.core.project_browser.gui.client` — core depending on a plugin's *GUI* module, against the plugin contract in `CLAUDE.md`. While here: `@action("project.save", schema={"project_name": str})` omits the handler's other required argument `target_path` (verified: `spec.schema` is `['project_name']`, `spec._handler_params` is `['project_name', 'target_path']`), so a dispatch without it fails with a bare `TypeError` from the handler instead of the `ValueError` the validation contract promises.
- **Fix note:**

### Review 2026-07-26 (13) — the foundational data model (`base.py` / `curve.py` / `data.py`)

Slice: `chisurf/core/base.py`, `chisurf/core/curve.py` and `chisurf/core/data.py`
— the three files every dataset, curve, parameter and fit inherits from. Chosen
because the layer carries the serialization contract for the whole app yet had
only four findings on record (RF-086..RF-088), all from one commit.

What holds up: the `_SETATTR_PROPERTY_CACHE` memoisation in `Base.__setattr__` is
correct (properties do not change at runtime, and the sentinel really does
distinguish "not looked up" from "not a property"); `__copy__`/`__deepcopy__`
keep the documented UID identity; `Curve.__init__`'s float64 coercion does
prevent the object-array trap its docstring describes; `DataGroup.name`'s setter
and `DataCurve.data`'s stack/unstack round-trip cleanly.

Everything below was reproduced by running the real classes in the `arm64` env
(one finding end-to-end through the real DEER reader); no source was changed.
The damage concentrates in `DataCurve.__init__` and in the `save`/`load` pair,
neither of which has a test that exercises the argument combination that breaks.
Findings RF-181..RF-189.

### RF-181
- **Status:** FIXED
- **Severity:** S1 (every dataset produced by five readers reports its filename as the literal string `'None'`)
- **Location:** `chisurf/core/data.py:199-222` (`DataCurve.__init__`, the `super().__init__(...)` call)
- **Finding:** `filename` is a named parameter of `DataCurve.__init__`, so it is consumed there and is **not** in `**kwargs` — and the `super().__init__` call passes `x`, `y`, `copy_array`, `data_reader`, `experiment` and `**kwargs` but never `filename`. `chisurf.core.base.Data.__init__` therefore always sees its default `filename="None"`, and `os.path.normpath("None")` stores the four-character string. Verified end-to-end through a real reader: `DeerReader().read('test/data/deer/deer_trace.csv')` yields a curve with `name='deer_trace'` and `filename='None'`. The same constructor kwarg with no follow-up assignment is used by `chisurf/core/experiments/ics/__init__.py:496`, `deer/reader.py:170`, `pch/reader.py:369`, `pda/reader.py:231`/`:794` and `chisurf/core/fio/fluorescence/pqres.py:244`/`:325` — none of them re-assigns `.filename` afterwards. Only the TCSPC reader escapes, because it works around this by hand (`chisurf/core/fio/fluorescence/tcspc.py:397`, `:409`, `:426`: `data.filename = filename` right after construction). Downstream this is what the dataset-list tooltips show (`chisurf/gui/widgets/experiments/widgets.py:165`, `:181`, `:194`) and what `DataGroup.filename` reports. Forward `filename=filename` to `super().__init__` and drop the three hand-patches.
- **Fix note:** `DataCurve.__init__` now forwards `filename=filename` to `super().__init__`, so `Data.filename` receives the real path (`chisurf/core/data.py:214-223`). Since `DataCurve` defaults `filename=''` while `Data` defaults `"None"`, the `Data.filename` setter now stores an empty path as `''` instead of running it through `os.path.normpath` — `normpath('')` is `'.'`, which would make every in-memory curve claim the working directory as its source file (`chisurf/core/base.py:898-915`). An in-memory curve therefore reports `''`, a curve from a reader its path. The TCSPC hand-patches were **kept**: those call sites never pass `filename` to the constructor, and moving it into the constructor would trip the `load_filename_on_init` branch and re-read the file over the rebinned arrays (RF-182). Pinned by `test/core/test_data.py::TestDataCurve::test_filename_is_forwarded_to_base` and `::test_filename_empty_for_in_memory_curve`, plus a reader-level assertion in `test/experiments/test_deer_reader.py::test_reader_loads_csv`.

### RF-182
- **Status:** OPEN
- **Severity:** S1 (constructing a curve from a file silently replaces the file's `ey` with ones — the weights every chi2 is computed from)
- **Location:** `chisurf/core/data.py:227-243` (`DataCurve.__init__`, the `self.load(...)` call followed by the `ex`/`ey`/`mask` block)
- **Finding:** `DataCurve.__init__` loads the file *first* (`:227-229`) and only *then* initialises the error and mask arrays from its own arguments (`:232-243`). Since `ex`/`ey`/`mask` default to `None`, the `isinstance(..., np.ndarray)` guards all fail and the freshly loaded columns are overwritten with `np.zeros_like(self.x)`, `np.ones_like(self.y)` and `np.ones_like(self.y)`. `x` and `y` survive only because nothing writes them afterwards. Verified on a 5-column CSV (`ex=0.1`, `ey=0.5`, `mask=0`): `DataCurve(filename=fn)` gives `ex=[0…0]`, `ey=[1…1]`, `mask=[1…1]`, while the identical file through `DataCurve().load(fn)` gives the correct `[0.1…]`, `[0.5…]`, `[0…]`. So the documented constructor form (`chisurf/core/models/tcspc/av_decay.py:23-26`, `chisurf/core/structure/av/__init__.py:758-759`) reads a 3-, 4- or 5-column file and throws its uncertainty columns away, leaving unit weights. Initialise `ex`/`ey`/`mask` before the load, or skip the defaults for arrays the load already set.
- **Fix note:**

### RF-183
- **Status:** OPEN
- **Severity:** S1 (`DataGroup.save()` raises `TypeError` — a data group cannot be saved at all)
- **Location:** `chisurf/core/data.py:588-592` (`DataGroup.to_yaml`) against `chisurf/core/base.py:363-364` (`Base.save`)
- **Finding:** `Base.save(file_type='yaml')` calls `self.to_yaml(skip_qt_widgets=skip_qt_widgets)`, but `DataGroup.to_yaml` overrides the base signature with `(remove_protected, convert_values_to_elementary)` only. Verified: `DataGroup([curve]).save(path)` raises `TypeError: DataGroup.to_yaml() got an unexpected keyword argument 'skip_qt_widgets'`, and `yaml` is the default `file_type`, so the plain `group.save(path)` call is the broken one. This is the same class of defect as RF-087 (`Controller.to_dict` / `View.to_dict`) but on `to_yaml`, so a guardrail written only for `to_dict` would not catch it. `DataGroup` is what every reader returns, and `DataCurveGroup` / `ExperimentDataGroup` / `ExperimentDataCurveGroup` all inherit the override. Add `skip_qt_widgets` and forward it to both `to_dict` calls.
- **Fix note:**

### RF-184
- **Status:** OPEN
- **Severity:** S2 (`convert_values_to_elementary=True` is silently ignored on the default path — the caller gets NumPy arrays and live objects back where the docstring promises floats, ints and lists)
- **Location:** `chisurf/core/base.py:463-484` (`Base.to_dict`, the `return d` at `:478`)
- **Finding:** With `remove_protected=False` (the default) and `copy_values=True` (also the default, and forced by `convert_values_to_elementary=True` at `:442-443`), `to_dict` returns from inside the `if copy_values:` block at `:478` — *before* the `if convert_values_to_elementary: return to_elementary(d)` at `:481-482`. The flag is therefore only honoured when `remove_protected=True`. Verified: `Base(arr=np.array([1.,2.])).to_dict(convert_values_to_elementary=True)['arr']` is still an `np.ndarray`. The documented contract at `:426-431` ("the values ... will be converted using the function `to_elementary`") is unmet, and callers that rely on it get a dict that `json.dumps`/`yaml.dump` cannot serialize — including `DataCurve.to_dict` and `ExperimentalData.to_dict`, both of which default to `remove_protected=False` and pass the flag straight down. Move the elementary conversion so both branches reach it (and, per RF-088, forward `remove_protected`/`skip_qt_widgets` when it does).
- **Fix note:**

### RF-185
- **Status:** OPEN
- **Severity:** S2 (the `pkl` route is write-only: `save` writes a file `load` cannot read, and what it writes has lost the object's state)
- **Location:** `chisurf/core/base.py:357-373` (`Base.save`) against `:375-407` (`Base.load`) and `:686-692` (`Base.__getstate__`)
- **Finding:** `save` advertises `supported_save_file_types = ["yaml", "json", "pkl"]` and writes pickles under `file_type="pkl"`, while `load` only recognises `"json"` and `"p"` and treats everything else — including `"pkl"` — as YAML. Verified: `b.save(fn, 'pkl')` writes 144 bytes, and `Base().load(fn, 'pkl')` raises `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 0`, because `from_yaml` opens the pickle in text mode. Even with the vocabulary aligned the file is close to empty: `Base.__getstate__` returns only `{'meta_data', 'name'}`, so `pickle.loads(pickle.dumps(Base(lol=1, parameter="ala")))` comes back with `__dict__` keys `['meta_data', 'name']` and no `lol`. That minimal state is deliberate for the `Parameter`/`Fit` hierarchy, which re-adds what it needs (`chisurf/core/fitting/fit.py:537`, `chisurf/core/fitting/parameter.py:202`, `:483`), but for a plain `Base` subclass it makes the pickle route lossy on top of unreadable. Either make `load` accept `"pkl"` (and open binary) and give `Base` a state-preserving `__getstate__`, or drop `"pkl"` from `supported_save_file_types`.
- **Fix note:**

### RF-186
- **Status:** OPEN
- **Severity:** S3 (an unsupported `file_type` writes nothing, raises nothing, and logs that it is saving)
- **Location:** `chisurf/core/base.py:349-373` (`Base.save`, the unguarded `if file_type in self.supported_save_file_types:`)
- **Finding:** `save` logs `"<name> of type <cls> is saving filename <fn> as file type <ft>"` at INFO *before* checking the type, then does nothing at all when the type is not one of `yaml`/`json`/`pkl` — no file, no exception, no warning. Verified: `Base(...).save('/tmp/…/t.txt', file_type='txt')` returns `None` and neither `t.txt` nor any other file exists afterwards, with the log line claiming the save happened. Any caller passing a format this class does not implement (`csv` is the obvious one — `Curve.save` and `DataCurve.save` handle it themselves *around* this call) believes it succeeded. Raise `ValueError` on an unknown type, or at minimum log a warning and move the INFO line after the guard.
- **Fix note:**

### RF-187
- **Status:** OPEN
- **Severity:** S2 (`Curve.load(fn)` with its own default `file_type` crashes, and its `except IndexError` handler is a verbatim copy of the code that raised)
- **Location:** `chisurf/core/curve.py:209-238` (`Curve.load`, the `super().load(...)` at `:221-224` and the `try/except IndexError` at `:233-238`)
- **Finding:** Two defects in one method. (1) `Curve.load` forwards *every* file type to `Base.load` before doing its own CSV parsing; `Base.load` routes anything that is not `json`/`p` to `from_yaml`, so a CSV is fed to `yaml.safe_load` and the result to `from_dict`. Verified: `Curve().load(fn)` on a two-column CSV raises `ValueError: dictionary update sequence element #0 has length 1; 2 is required` from `self.__dict__.update(...)` — the default argument is the broken one. (2) The `except IndexError` block at `:236-238` re-executes `self.x = csv.data[0]; self.y = csv.data[1]` — byte-for-byte the statements that raised — so a one-column CSV raises `IndexError` again from inside the handler. Skip the `super().load` call for `file_type == 'csv'`, and either handle the short-file case properly or drop the dead `except`.
- **Fix note:**

### RF-188
- **Status:** OPEN
- **Severity:** S3 (`NCurve.__getitem__` raises `AttributeError` for every `NCurve`, and would return mismatched arrays if it did not)
- **Location:** `chisurf/core/curve.py:54-70` (`NCurve.__getitem__`)
- **Finding:** The method slices `self.d` into `y` and then builds `x = np.arange(0, len(self.y))` — but `NCurve` has no `y` attribute or property (it is introduced by `Curve`, which overrides `__getitem__` anyway), so `Base.__getattr__` raises. Verified: `NCurve(d=np.arange(6.))[0:3]` → `AttributeError: NCurve object has no attribute 'y'`. Even on a subclass that does define `y`, the index array is built from the *full* length while `y` is the *selected* slice, so the returned pair is inconsistent for any key that is not the whole array. Either build `x` from the sliced result (`np.arange(len(y))`) and use `self.d`, or delete the method — nothing in the tree calls it.
- **Fix note:**

### RF-189
- **Status:** OPEN
- **Severity:** S3 (three type-dispatch gaps in the one function all serialization funnels through)
- **Location:** `chisurf/core/base.py:96-114` (the dict branch) and `:121-145` (the type ladder) in `to_elementary`
- **Finding:** (1) The protected-key test is `if (k[0] == "_")`, which assumes every mapping key is a non-empty string: verified `to_elementary({1: 'a'})` → `TypeError: 'int' object is not subscriptable` and `to_elementary({'': 'a'})` → `IndexError: string index out of range`. A single integer-keyed dict anywhere in an object graph aborts the whole save. (2) `isinstance(obj, Iterable)` at `:129` is reached before any bytes handling, so `bytes` become a list of integers — verified: a `Data` with 1 KiB of embedded content serialises to a 13 183-character JSON whose `_data` is an array of 1024 ints, and it restores as a `list`, not `bytes` (`embed_data` defaults to `false`, so this needs the setting turned on). (3) `np.bool_` and `complex` match none of the branches and fall through to `str(obj)` — verified `to_elementary(np.bool_(True))` → `'True'` and `to_elementary(1+2j)` → `'(1+2j)'`, each with a "was not converted to basic type" warning and a stray `print` to stdout at `:167`. Guard the key test with `isinstance(k, str)`, handle `bytes` explicitly (base64 or hex), and add `np.bool_`/`complex` to the ladder.
- **Fix note:**

### Review 2026-07-26 (14) — the TCSPC nuisance layer (`models/tcspc/nusiance.py`)

Slice: `Generic` / `Corrections` / `Convolve` — the three parameter groups every
TCSPC decay model composes — plus the two kernels they call
(`fluorescence/tcspc/corrections.py`, `fluorescence/tcspc/tcspc.py:rescale_w_bg`)
and the widgets that drive them (`gui/widgets/models/tcspc/convolve.py`,
`corrections.py`). This is the layer that turns a lifetime spectrum into a
comparable model decay, and it is essentially untested: the only files in `test/`
that mention `Convolve` assert *method names* via `ast` (`test_convolve_widget_contract.py`),
and nothing exercises `_process_irf`, `scale`, `pileup` or the mode dispatch.
Every finding below was reproduced in the `arm64` env against the real objects.
Findings RF-193..RF-201.

### RF-193
- **Status:** OPEN
- **Severity:** S1 (the pile-up correction silently turns the entire model decay into `NaN`)
- **Location:** `chisurf/core/fluorescence/tcspc/corrections.py:170-186` (`add_pile_up_to_model`), called from `chisurf/core/models/tcspc/nusiance.py:280-294` (`Corrections.pileup`)
- **Finding:** `n_excitation_pulses = max(live_time * rep_rate, n_pulse_detected)` and then `p = data / (n_excitation_pulses - np.cumsum(data))`. Whenever the first term loses the `max` — i.e. whenever the assumed measurement time is too short for the number of recorded photons — `n_excitation_pulses` equals `cumsum[-1]`, so the **last** denominator is exactly `0`, `p[-1]` is `inf`, and `-log(1 - inf)` is `NaN`. The single `NaN` is then broadcast over the whole array by the normalisation `sf = sf / np.sum(sf) * len(data)`. Verified: `add_pile_up_to_model(y, m, rep_rate=20.0, dead_time=85.0, measurement_time=1.0, modify_inplace=False)` on a 64-channel decay holding 1e8 photons returns **64 NaN of 64**; the same call with `measurement_time=300.0` returns none. This is reachable by default, not exotic: `Corrections.measurement_time` reads `generic.t_exp`, whose `FittingParameter` default is `1.0` s and which the user must set by hand, so ticking the pile-up box on any long measurement poisons the model. The function is `@nb.jit(nopython=True)`, so there is no warning — the fit just reports `NaN` chi². Clamp the denominator (and `p < 1`) or refuse to correct when `live_time <= 0`.
- **Fix note:**

### RF-194
- **Status:** OPEN
- **Severity:** S1 (the convolution on/off checkbox and the `convolution_on_by_default` setting have no effect)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:497-505` (`Convolve.do_convolution`), written at `:979`, `:1038` and `chisurf/gui/widgets/models/tcspc/convolve.py:167`
- **Finding:** `do_convolution` is written from four places — the settings key `tcspc.convolution_on_by_default`, the GUI checkbox in `onConvolutionModeChanged`, `Convolve.set_state` on project load, and `fluorescence/decay_fit_model.py:135` — and **read by nobody**. `grep -rn do_convolution chisurf --include='*.py'` returns only the property, those writes, and a doc mention in `core/dataspec/__init__.py:328`; neither `Convolve.convolve` nor `Lifetime.update_model` consults it, and `update_model` calls `self.convolve.convolve(...)` unconditionally. So unticking the box in the Convolve panel leaves the model convolved with the IRF, and the state faithfully round-trips through a project save while meaning nothing. Either honour the flag in `Convolve.convolve` (return the raw decay when it is off) or remove the flag, the checkbox and the setting.
- **Fix note:**

### RF-195
- **Status:** FIXED
- **Severity:** S1 (a loaded IRF has the lamp background subtracted twice, a synthetic one once)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:535-554` (`Convolve._process_irf`)
- **Finding:** The `isinstance(self._irf, Curve)` branch at `:535-538` already does `irf -= self.lamp_background` followed by `np.clip(irf.y, 0, None)`, and lines `:553-554` — outside the `if/else` — do exactly the same two statements again. `Curve` defines `__sub__` but no `__isub__`, so `-=` rebinds to a fresh curve each time and the stored IRF is not mutated; the result is simply `clip(clip(irf - lb, 0) - lb, 0)`. Verified on a real `Convolve`: with `lamp_background = 1.0` and IRF `y = [0,4,10,6,3,1,0,0]`, `_process_irf(normalize=False)` returns `[0,2,8,4,1,0,0,0]` where a single subtraction gives `[0,3,9,5,2,0,0,0]`. The synthetic-IRF branch (`:539-551`) never subtracts inside the branch, so it gets the background removed exactly once — the two paths disagree. `lb` is a fittable parameter whose upper bound is set to half the lamp height when an IRF is loaded (`:726-732`), so any non-zero value doubles. Delete the duplicated pair inside the `if`.
- **Fix note:** The duplicated `irf -= self.lamp_background` / `np.clip` pair
  inside the loaded-IRF branch was deleted; the shared pair below the
  `if`/`else` is now the single subtraction for both branches, so a loaded and a
  synthetic IRF lose the background exactly once
  (`chisurf/core/models/tcspc/nusiance.py:535-537`). `Curve.__sub__` still
  rebinds to a fresh curve, so the stored `_irf` remains unmutated. Confirmed on
  the finding's own case: `[0,4,10,6,3,1,0,0]` with `lb=1.0` now processes to
  `[0,3,9,5,2,0,0,0]` instead of `[0,2,8,4,1,0,0,0]`. Pinned by
  `test/tcspc/test_convolve_lamp_background.py` (3 tests, 6 cases: the single
  offset for a range of `lb`, non-mutation of the stored IRF across repeated
  processing); all four value-bearing cases fail against the pre-fix file.
  Note for whoever takes RF-196 and neighbours: the `irf_start`/`irf_stop`
  *setters* (`:467-485`) wrap the value in `np.array([v], dtype=np.int64)`,
  which `FittingParameter` rejects with `Cannot set parameter … to <class
  'numpy.ndarray'>` — the window can only be set through `_irf_start.value` /
  `_irf_stop.value`. Not in scope here; worth its own finding.

### RF-196
- **Status:** OPEN
- **Severity:** S2 (the user-facing `start` channel of the Convolve panel can never take effect)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:764` (`Convolve.scale`) and `:843` (`Convolve.convolve`)
- **Finding:** Both read `start = min(0, self.start)`. `self.start` is `int(self._start.value // self.dt)` and is non-negative in every realistic setting, so `min(0, ...)` is **always 0** — this is a `max`/`min` inversion. `_start` is a real widget (`gui/widgets/models/tcspc/convolve.py:90` builds a fitting-parameter widget for it next to `_stop`, whose `min(self.stop, len(decay))` clamp *is* correct), and `Lifetime.update_model` calls `self.convolve.scale(decay, bg=...)` with no explicit `start`, so the analytic n0 rescale always runs over `[0, stop)` and silently ignores the channel the user asked to start at. In `convolve` the local is dead as well: `convolve_lifetime_spectrum_periodic` drops its `start` argument entirely and the `exp` path never receives one. Use `max(0, self.start)` in `scale` and delete the unused local in `convolve`.
- **Fix note:**

### RF-197
- **Status:** OPEN
- **Severity:** S2 (the analytic autoscale weights channels by their variance instead of its inverse, so `n0` is not the chi²-optimal amplitude)
- **Location:** `chisurf/core/fluorescence/tcspc/tcspc.py:87-91` (`rescale_w_bg`), called from `chisurf/core/models/tcspc/nusiance.py:772-781` (`Convolve.scale`)
- **Finding:** The kernel computes `iwsq = 1.0 / (w[i] * w[i] + 1e-12)` and multiplies both sums by it, i.e. it treats its `experimental_weights` argument as an *error* σ. Both callers pass the reciprocal: `Convolve.scale` uses `weights = 1.0 / data.ey` and `plugins/fluorescence_decay/lltf/core/scaling.py:97` uses `1.0 / np.sqrt(...)`. `data.ey` is σ (`counting_noise` returns `sqrt(counts)`, and `calculate_weighted_residuals` divides by `data.ey`), so the sums end up weighted by **σ² instead of 1/σ²** — the inverse of the weighting the fit itself minimises. Verified on a 1024-channel Poisson decay: the closed-form WLS optimum `Σ m·d/σ² / Σ m²/σ²` is `20041.73` (chi²r `1.39442`); calling `rescale_w_bg` with `ey` reproduces it to 4 decimals, while the call as chisurf makes it returns `20017.59` (chi²r `1.39621`). Since autoscale exists precisely to place `n0` at its conditional optimum, it currently leaves chi² systematically above what the same model can reach. Fix in the kernel (`iwsq = w[i]*w[i]`, matching the parameter name) or at both call sites, not half of each.
- **Fix note:**

### RF-198
- **Status:** OPEN
- **Severity:** S2 (the `curve` convolution mode is offered by the lifetime widget, where it convolves the lifetime *spectrum*; an unknown mode returns a zero decay)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:845-871` (`Convolve.convolve`, the mode ladder), exposed by `chisurf/gui/widgets/models/tcspc/lifetime.py:390` (`hide_curve_convolution=False`)
- **Finding:** Two defects in the mode dispatch. (1) `mode == "full"` runs `np.convolve(data, irf_y)`, which is only meaningful when `data` is a *decay* — as it is for `ParseDecayModel`, which passes `self.y`. `Lifetime.update_model` passes the interleaved lifetime spectrum `(a₁, τ₁, a₂, τ₂, …)`, so the "curve" radio produces the IRF smeared by a 2n-element amplitude array with no exponential tail at all. Verified with a τ=4 ns single exponential and a Gaussian IRF: `per` decays as `[1e-4, 2.3e-3, 0.031, 0.166, 0.423, 0.606, 0.593, 0.485, 0.380, …]`, `full` gives `[1e-4, 5e-3, 0.072, 0.458, 1.367, 1.838, 1.022, 0.220, 0.018, 5e-4, 0, 0]` — dead within ten channels. `ConvolveWidget` hides that radio by default, but the lifetime, MaxEnt and parse widgets all pass `hide_curve_convolution=False`. (2) The ladder has no `else`: an unrecognised mode returns the untouched zero buffer plus `scatter * irf_y`. Verified: `convolve(spec, mode='banana')` returns all zeros. `Convolve.set_state` assigns any string from a project file straight to `self.mode` with no validation, so a stale or corrupted project silently yields an all-zero model. Restrict the mode list per model and raise on an unknown mode.
- **Fix note:**

### RF-199
- **Status:** OPEN
- **Severity:** S2 (changing the smoothing window raises `AttributeError` when no linearization curve is loaded, swallowed by a bare `except`)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:180-195` (`Corrections.window_length` / `window_function` setters), `_curve` initialised to `None` at `:399`
- **Finding:** Both setters end with `self._lintable = self.calc_lintable(self._curve.y)`, but `_curve` is only assigned by the `lintable` setter — it is `None` until a linearization curve is loaded, and `unload_lintable` puts it back to `None`. So `model.corrections.window_function = 'hamming'` on a fit with no lintable raises `AttributeError: 'NoneType' object has no attribute 'y'`. In the GUI the combo box routes through `model.set_correction` → `chisurf/macros/model.py:71-75`, whose `try/except Exception: pass` swallows it silently, and `Corrections.set_state` (`:355-360`) swallows it again on project load. Guard both setters with `if self._curve is not None` — and note the bare `except` in the macro hides *every* failure of every correction, not just this one.
- **Fix note:**

### RF-200
- **Status:** OPEN
- **Severity:** S3 (two divergent copies of `rescale_w_bg`)
- **Location:** `chisurf/plugins/fluorescence_decay/lltf/core/scaling.py:12-62` versus `chisurf/core/fluorescence/tcspc/tcspc.py:53-94`
- **Finding:** The plugin ships a private numba copy of `rescale_w_bg` with the same name, signature and docstring as the core one, and the two have already drifted: the plugin indexes the weights as `w[i - start]` (its caller passes a sliced array) while core uses `w[i]` (its caller passes the full array), and the plugin guards the division as `sum_nom / max(1.0, sum_denom)` while core uses `if sum_denom != 0.0`. Any fix to the weighting convention (RF-197) has to be made twice or the two silently disagree. Import the core function and pass the full array plus `start`/`stop`, or move the sliced variant into core as the single implementation.
- **Fix note:**

### RF-201
- **Status:** OPEN
- **Severity:** S3 (dead state plus a docstring that describes behaviour the code does not have)
- **Location:** `chisurf/core/models/tcspc/nusiance.py:684-694` (`Convolve.unnormalized_irf`), `:709` and `:981` (`n_photons_irf`)
- **Finding:** `unnormalized_irf`'s docstring says it "scales the IRF by the `n_photons_irf` factor to restore its original height", but the property just calls `_processed_irf(normalize=False)`, which only *skips* the normalisation and logs `'No IRF scaling'` — no factor is applied anywhere. `n_photons_irf` itself is written in `__init__` and in the `_irf` setter and never read: the only other mention is the commented-out `# / self.n_photons_irf` at `:424`. Either apply the factor or drop the attribute and correct the docstring; as written, a reader has to run the code to find out which of the two is true.
- **Fix note:**

### Use-case walk 2026-07-26 — fFCS filter calculator (GUI tester)

Found by driving the **FCS → 🧪 Filter Calc** panel headlessly the way a user does
(see [the use case](/usecases/ffcs-filter-calculator.md)). Findings RF-190..RF-192.

### RF-190
- **Status:** OPEN
- **Severity:** S1 (the tool cannot be used: five modal error boxes on open, permanently empty reconstruction/residual plots, and a hang that also stops the plugin's own test suite)
- **Location:** `chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/main_window.py:1427-1430` (`_clear_recon_plot`), with the region created at `:266-272` (`self.plot_recon.region(...)`) — regression from `ff7aec4ba` ("refactor(chiplot): migrate FCS filter-calculator off pyqtgraph", 2026-07-26)
- **Finding:** `_clear_recon_plot` does `self.plot_recon.clear()` then `self.plot_recon.addItem(region)`, where `region` is `self._fit_region` — since the chiplot migration a chiplot `_Region` **wrapper**, not a `QGraphicsItem`. `chiplot.Plot` has no native `addItem`, so the call falls through to the pyqtgraph backend and dies: `TypeError: addItem(self, item: Optional[QGraphicsItem]): argument 2 has unexpected type '_Region'`. `ViewBox.addItem` appends the wrapper to `addedItems` *before* the failing `scene.addItem`, so the **next** `plot_recon.clear()` then fails the same way on `removeItem` — the two errors alternate. `_update_plots` calls `_clear_recon_plot` at `:3146`, so every recompute (open, detector change, range change, unmix) aborts there, and the `except` at `:2675-2679` / the single-detector and unmix equivalents turn each one into a modal `QMessageBox.critical` quoting the raw PyQt signature. Verified: constructing `FcsFilterCalculatorWidget` offscreen produced **5** modal dialogs; the *Reconstruction / decay* and *Weighted residuals* plots stayed empty (0…1 axes) even after a successful auto-fit and a successful unmix (which had already computed 70.9 % / 29.1 % correctly); the status bar was left showing the `TypeError` text. Because the dialog is raised from the widget **constructor**, an offscreen run blocks in the modal's nested event loop indefinitely — the first driver hung 6 min at 0 % CPU, and `pytest chisurf/plugins/fcs/fcs_filter_calculator/test` never terminated (11 min, 0 % CPU, stack in `qt_safe_poll`). The region is already on the plot from `Plot.region(...)`; either have chiplot's `clear()` preserve it, or re-add it through a chiplot API instead of the pyqtgraph passthrough. This is the only place in the tree that combines `.region(` with `addItem(region)`.
- **Fix note:**

### RF-191
- **Status:** OPEN
- **Severity:** S1 (the toolbar Auto-fit silently ignores the component count and returns a wrong, mono-exponential result)
- **Location:** `chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/main_window.py:296-301` (`autofit_action.triggered.connect(self._auto_fit_components)`) vs. the correct `:395` (`clicked.connect(lambda: self._auto_fit_components())`); handler at `:1616`, `:1640-1641`; fitter at `chisurf/core/fluorescence/decay_fit_model.py:266` (`fit_lifetime_model`, `n_components: int = 2`)
- **Finding:** `QAction.triggered` emits `checked: bool`, so connecting it directly to `_auto_fit_components(self, n_components=None)` passes **`False`** as `n_components`. The `if n_components is None` guard at `:1640` therefore does not fire, the dock's *Components / states* value is discarded, and `int(False) = 0` reaches `fit_lifetime_model(..., n_components=0)` — which silently fits **one** component instead of raising. Verified on the built-in 70/30 example (τ = 1.2 / 4 ns) with *Components / states* = 2 on screen: the toolbar **🎯 Auto-fit** reported `1 components (χ²ᵣ=2.9) — 100 %·1.53 ns` and replaced the component list with that single species, while the dock's **🎯 Fit + generate filters** button on the same widget reported `2 components (χ²ᵣ=1.03) — 67 %·1.20 ns, 33 %·3.74 ns` (the ground truth). A spy on the handler recorded the two argument values as `False` and `None`. Nothing warns that the typed number was ignored, and the wrong species set is what the filters are then computed from. Wrap the toolbar connection in a lambda (or accept and discard the `checked` argument), and make `fit_lifetime_model` reject `n_components < 1` instead of degrading to 1.
- **Fix note:**

### RF-192
- **Status:** OPEN
- **Severity:** S2 (opening the panel runs the full filter computation six times, nested two deep; one programmatic range set costs two more)
- **Location:** `chisurf/plugins/fcs/fcs_filter_calculator/gui_parts/main_window.py:1445-1477` (`_set_fit_range` / `_on_range_spin_changed` / `_on_fit_range_committed`), reached from `_init_fit_region` at `:1432-1443` inside `_update_plots` (`:3051`)
- **Finding:** `_set_fit_range` guards itself with `self._syncing_range`, but the guard only makes the **nested `_set_fit_range`** return early — `_on_range_spin_changed` (`:1474-1477`), which each programmatic `sb_fit_start/stop.setValue()` triggers, then calls `_on_fit_range_committed()` → `_on_data_changed()` → `_compute_filters()` unconditionally. Since `_init_fit_region` is called from *inside* `_update_plots`, which is called from *inside* `_compute_filters_multi_detector`, a full filter computation is launched from within the previous one. Verified by counting calls to `_compute_filters`: constructing the widget runs it **6** times with a maximum recursion depth of **2**; one `_set_fit_range(20, 240)` call costs **2** further full recomputes (one per spin box), while a genuine user spin edit correctly costs 1. On the 256-bin built-in example this is only wasteful; on real multi-detector 4096-bin data it is a multi-second freeze with no progress indication, and the re-entrancy is what makes the RF-190 error cascade fire repeatedly. Either extend the `_syncing_range` guard over the commit callback, or have `_set_fit_range` block the spin boxes' signals while it writes them.
- **Fix note:**

### Review 2026-07-26 — dataspec / AutoForm binding seam

Slice: `chisurf/core/dataspec/__init__.py` (the Qt-free view-spec vocabulary) and
its renderer `chisurf/gui/autoform/` (`auto_form.py`, `sections/builtin.py`) —
recently churned (`data_source` section, `options_source` pairs, `hidden_when`,
chiplot migration) and carrying **zero** findings on record while ~100
`.view.json` specs and every ported plugin depend on it. Everything below was
reproduced headlessly in the `arm64` env (`QT_QPA_PLATFORM=offscreen`); the
declared `Section` fields were cross-checked against the shipped specs to
confirm each defect has real authored users, not just a hypothetical one.
Findings RF-202..RF-207.

### RF-202
- **Status:** OPEN
- **Severity:** S2 (headless introspection and the model-editor guard tests see *one* section for a whole plugin UI)
- **Location:** `chisurf/core/dataspec/__init__.py:620-641` (`ModelView.flat_sections` / `section_targets`)
- **Finding:** `flat_sections()` documents "all sections in depth-first order, recursing into panels", but its `_walk` only recurses when `isinstance(s, PanelSection)` — `DockAreaSection.sections` and `WizardSection.steps` (each `WizardStepSection.sections`) are never entered, although both nest children exactly like a panel and the renderer *does* build them (`auto_form.py:585-623`, `:675-691`). Any spec whose UI lives inside a dock area or a wizard therefore reports a single section and **no targets at all**. Verified: `load_view_spec('chisurf/plugins/tttr/tttr_count_rate_analysis/gui/count_rate.view.json')` gives `flat_sections()` length **1** and `section_targets() == []`, while the dock area holds 4 children (3 panels + a plot); `.../tr_anisotropy/anisotropy.view.json` likewise reports 1. This is not cosmetic: `flat_sections()` is the introspection API the headless guards use — `test/gui/test_pda_model_editor.py:128`, `test_fcs_model_editor.py:60`, `test_tcpda_model_editor.py:129`, `test_ics_model_editor.py:113` and `test_model_editor_integration.py:168` all iterate it to assert every section's `target` resolves on the model, so for a dock/wizard-hosted editor those loops iterate zero bodies and pass vacuously. Recurse into `DockAreaSection.sections` and `WizardSection.steps`/`WizardStepSection.sections`.
- **Fix note:**

### RF-203
- **Status:** OPEN
- **Severity:** S2 (typing a number into any AutoForm int/float field commits every intermediate prefix, each firing the model callback and a fit update)
- **Location:** `chisurf/gui/autoform/sections/builtin.py:973` and `:988` (`ValueWidget.__init__`, the `int` / `float` branches)
- **Finding:** Both numeric kinds connect `self.editor.valueChanged` to `self._commit`. `QSpinBox`/`QDoubleSpinBox` default to `keyboardTracking = True`, so `valueChanged` fires on **every keystroke**, and `_commit` (`:369-404`) then performs the `setattr`/`set_action` dispatch, the model `call`, `_refresh_host_form()` (a full `sync_fields()` + `refresh_plots()`) and a `fit.update` dispatch — once per digit. Verified headlessly: typing `1024` into a `kind="int"` field bound to `call="on_n"` recorded the call payloads `[1, 10, 102, 1024]` (`keyboardTracking` confirmed `True`). Every other kind in the same constructor commits on `editingFinished` (`:997`, `:1013`, `:1021`, `:1029`), so this is an inconsistency inside one widget, not a deliberate policy. **34** authored `value` sections across the tree are `int`/`float` *and* carry a `call`/`set_action`, several of them expensive — `img_calibration`'s four channel-window fields and two background fields call `refresh_display`, `tttr_lut_tools` has eight fields calling `update`, `synthetic_decay_editor` seven calling `field_changed` — so a user typing a 4-digit channel number triggers four full recomputes and redraws, the last three of them on meaningless prefix values. Set `setKeyboardTracking(False)` on both spin boxes (or commit on `editingFinished` like every sibling branch).
- **Fix note:**

### RF-204
- **Status:** OPEN
- **Severity:** S2 (`"expand": true` on a `table` section is silently defeated, leaving the panel with a fixed-height table and a dead gap below it)
- **Location:** `chisurf/gui/autoform/sections/builtin.py:756-760` (`TableWidget.__init__`, the `expand` branch) versus `:812-828` (`_fit_height`), which runs unconditionally from `refresh()` at `:810` — itself called at the end of `__init__` (`:764`)
- **Finding:** The `expand` branch sets `_autoform_expanding = True` and an `Expanding` vertical size policy so the enclosing form/dock hands the table the spare vertical space (`auto_form.py:145-151`, `:601-608`). `refresh()` then calls `_fit_height`, which unconditionally re-applies `setSizePolicy(Expanding, Maximum)` and pins the height — `setFixedHeight(header + rows)` when no explicit `height` is declared, `setMinimumHeight(h)` + `setMaximumHeight(h)` when one is. `_fit_height` never consults `section.expand`. Verified: a two-row `TableSection(expand=True)` yields `_autoform_expanding == True` but vertical policy `Maximum` (4, not `Expanding` = 7) and `minimumHeight == maximumHeight == 64`; adding `height=300` gives `min == max == 300`. The layout therefore assigns the row the stretch while the widget refuses to use it, so the table stays short and the space below it is dead. Four shipped specs ask for this and get neither behaviour: `accurate_fret.view.json` (*Correction factors*), `img_coloc` (*Coefficients*), `img_drift` (*Shifts*), `img_precision` (*Numbers*). Make `_fit_height` a no-op (or a minimum-only hint) when `section.expand` is set.
- **Fix note:**

### RF-205
- **Status:** OPEN
- **Severity:** S3 (dock-area children skip the shared section post-processing: no `description` tooltip, no `visible`/`hidden_when`, and build failures vanish without a log line)
- **Location:** `chisurf/gui/autoform/auto_form.py:585-623` (`_build_dock_area`, the child loop) versus `_emit_sections` at `:259-286`
- **Finding:** Every other section reaches its widget through `_emit_sections`, which applies three things after `_build_section`: the `visible` / `hidden_when` evaluation (`:267-270`), the `description` → wrapped tooltip (`:276-280`), and an `logging.error` on a failed build (`:262-263`). `_build_dock_area` calls `self._build_section(child)` directly for every non-`panel` child and wraps it in a bare `except Exception: widget = None` (`:619-620`), so none of the three apply. Concretely, **29** authored `custom` sections that are direct children of a `dock_area` carry a `description` that never becomes a tooltip — e.g. `phasor_calculator` (*Phasor plot*), `flc_2d` (*2D-FLCS map*, *2D residual*, *L-curve*), `img_pixel_mle` (*Lifetime map*), `img_calibration` (*Decay & IRF*), `img_coloc` (*Colocalized pixels*); the `plot` children escape only because `PlotWidget` happens to set its own tooltip at `builtin.py:1313` (unwrapped, unlike the shared path). The silent `except` is the worse half: a custom section whose factory raises simply loses its dock tab with nothing in the log. Route dock children through the same post-processing (or factor those three steps into a helper both paths call), and log the exception.
- **Fix note:**

### RF-206
- **Status:** OPEN
- **Severity:** S3 (a control whose fit is not registered silently addresses fit **0** instead of doing nothing)
- **Location:** `chisurf/gui/autoform/auto_form.py:897-904` (`AutoForm._dispatch_fit_update`) and the four copies of `_own_fit_index` in `chisurf/gui/autoform/sections/builtin.py:150-158`, `:347-355`, `:1191-1201`, `:2240-2251`
- **Finding:** All five resolve the edited model's fit by scanning `cs.fits` and fall back to index **0** when it is not found — `next((i for i, f in enumerate(fits) if f is fit), 0)` in the first, a bare `return 0` after the loop in the others. Nothing distinguishes "the model belongs to fit 0" from "this model's fit is not registered" or "this view-model has no fit at all", so the fallback dispatches at an unrelated, arbitrary fit rather than declining. The consequences differ by call site and the worst is `CurveInputWidget` (`:184-189`, `:199-204`): selecting or unloading a curve dispatches `section.select_action` / `unload_action` with `fit_index = 0`, i.e. an **IRF, background or linearization curve loaded into the wrong fit**, followed by a `fit.update` on that same wrong fit. `_BoundControlMixin._commit` already knows the distinction — it guards its extra `fit.update` with `if getattr(self._model, "fit", None) is not None` (`:400`) — but still passes the fallback index into the primary `set_action` payload (`:377`). Return `None`/`-1` on failure from one shared helper and have every caller skip the dispatch instead of defaulting. Note the five copies are identical modulo the `fits`/`cs.fits` spelling; deduplicate while fixing.
- **Fix note:**

### RF-207
- **Status:** OPEN
- **Severity:** S3 (a misspelled field in a `.view.json` is silently ignored, while a misspelled `type` raises)
- **Location:** `chisurf/core/dataspec/__init__.py:710-711` (`_section_from_dict`)
- **Finding:** The loader validates the section `type` strictly (`:707-709` raises `ValueError: unknown section type …`) and then drops every key the target dataclass does not declare: `kwargs = {k: v for k, v in d.items() if k in fields}`. A typo, a field placed on the wrong section type, or a key that a refactor renamed produces a section that builds cleanly and quietly does the default thing. Verified: `_section_from_dict({'type': 'value', 'label': 'x', 'attr': 'a', 'colapsed': True, 'hidden_when': {...}, 'typo_field': 5})` returns a `ValueSection` with all three extras discarded and no diagnostic — note `hidden_when` is a *real* field, just not on `ValueSection`, which is exactly the mistake an author would make after reading the `PanelSection` docstring. With ~100 shipped `.view.json` specs and a growing field vocabulary, this asymmetry (strict on `type`, silent on everything else) is the reason such a bug is only found by staring at the UI. Log a warning listing the unknown keys and the valid field names for that section type; keep dropping them so old specs still load.
- **Fix note:**

### Use-case walk 2026-07-26 — PCH molecular brightness (GUI tester)

Found by driving the **Spectroscopy → Single-Molecule → PCH** tool headlessly the
way a user does — load a TTTR file, compute the photon counting histogram, fit
one and then two species, move the fit region, export, open Help — on
`test/data/clsm/Leica_SP5.ptu` and `Leica_SP8.ptu`
(see [the use case](/usecases/pch-molecular-brightness.md)). Findings RF-208..RF-214.

### RF-208
- **Status:** FIXED
- **Severity:** S1 (every fit ends in a modal error box; the fitted curve is never drawn and the results box never fills)
- **Location:** `chisurf/plugins/pch/gui/tool.py` — `np` used at `:478-484` (`_plot_fit`) and `:500-505` (`_update_results_text`), while the only `import numpy as np` is local to `_save_outputs` at `:534`; module imports at `:1-34`
- **Finding:** The module imports `csv`, `logging`, `typing`, Qt and chiplot but never numpy, so the first statement of `_plot_fit` that builds a mask raises `NameError: name 'np' is not defined`. `_on_fit` (`:377`) calls `_plot_fit()` then `_update_results_text()` inside its `try`, and the `except` turns the `NameError` into `QMessageBox.critical(self, "Error", str(e))`. Verified by driving the real `QAction`: the backend fit **succeeded** (ε = 0.6722, ⟨N⟩ = 2.6581 were written back into the spin boxes at `:403-404`, which runs before the plotting) and the status bar's "Fit complete: χ²=…" line at `:408` is never reached — the user sees a dialog reading `name 'np' is not defined`, an unchanged histogram with no red model curve, and a permanently empty *Fit Results* box (screenshots `04_fit1.png`, `05_fit2.png`). `_update_results_text` is also the region-drag handler (`_on_region_changed`, `:441`), so step 8 of the workflow — re-scoring χ² over a new k range — is silently inert as well: dragging the region produced no text and no error, because that path has no `try`. Add `import numpy as np` at module level and drop the local import.
- **Fix note:** `import numpy as np` moved to the module imports and the local
  import inside `_save_outputs` dropped, so `_plot_fit`, `_update_results_text`
  and `_save_outputs` all resolve `np` from one place. `ruff check` on the file
  went from **8** `F821 Undefined name 'np'` to none (the remaining findings
  there are pre-existing and unrelated). Pinned by
  `chisurf/plugins/pch/test/test_widgets.py::TestPCHApp::test_fit_plot_and_results_text`,
  which fabricates a `PchResult`/`FitResult`, calls `_plot_fit()` and
  `_update_results_text()` directly — bypassing the `except` in `_on_fit` that
  used to hide the `NameError` — and asserts the *Fit Results* box actually
  fills with the per-component and reduced-χ² lines. Verified the test pins the
  fix: deleting `tool.np` at runtime makes `_plot_fit()` raise
  `NameError: name 'np' is not defined` again. `chisurf/plugins/pch/test` +
  `chisurf/plugins/pch/tests` green (13 tests).

### RF-209
- **Status:** OPEN
- **Severity:** S1 (the **Components** spin box does nothing, so multi-species PCH — the plugin's stated purpose — is unreachable from the GUI)
- **Location:** `chisurf/plugins/pch/gui/tool.py:302` (`_update_species_inputs`), connected at `:246` (`self.spin_comp.valueChanged.connect(self._update_species_inputs)`)
- **Finding:** The row-clearing loop reads `for _ in range(len(self.species_layout.count()), 0, -1):` — `QFormLayout.count()` already returns an `int`, so this raises `TypeError: object of type 'int' has no len()` on the first line of the handler. Qt swallows exceptions raised inside a slot, so nothing is shown: the ε/⟨N⟩ rows are never rebuilt and the panel keeps exactly the species rows created by `_init_species_inputs(1)` in the constructor while the spin box displays the new number. Verified: after `spin_comp.setValue(2)` the widget reported `len(self.eps_boxes) == 1` and `species_layout.rowCount() == 2` (one ε + one ⟨N⟩), with the box reading `2` on screen (`05_fit2.png`, `10_recovered.png`). The manifest, the README, the Help text and the plugin description all advertise multi-species fitting; it cannot be reached. Note the loop is also wrong once the `len()` is removed — it should clear `rowCount()` rows, not `count()` items (two items per row). Use `while self.species_layout.rowCount(): self.species_layout.removeRow(0)`.
- **Fix note:**

### RF-210
- **Status:** OPEN
- **Severity:** S1 (`pch.fit` returns `ok: True` with a degenerate model when the parameter lists disagree with `n_components`, and that garbage is what gets exported)
- **Location:** `chisurf/plugins/pch/backend/services.py:130-165` (`_fit_handler`, `params_init = init_eps + init_Ns` at `:143`, the `p[:n_components]` / `p[n_components:]` split at `:146`), with the GUI writeback at `chisurf/plugins/pch/gui/tool.py:402-404`
- **Finding:** The handler concatenates `initial_epsilons` and `initial_Ns` into one flat vector and then splits the optimiser's answer at `n_components`, without ever checking that either list has `n_components` entries. Given `n_components=2` with one ε and one ⟨N⟩ — exactly what the GUI sends while RF-209 keeps a single species row on screen — the split yields **two epsilons** (the ε *and* the ⟨N⟩) and an **empty** occupancy list, so `pch_mixture` convolves nothing, `p_fit` is `[1, 0, 0, …]` (a delta at k = 0), `fractions` is `[]` from `Ns_arr/Ns_arr.sum()` on an empty array, and the handler still returns `{"ok": True, …, "chi2": 581023.7}`. Verified directly against `_fit_handler` and through the GUI. The GUI then raises `IndexError: list index out of range` in the writeback loop — but only *after* `self._fit_result` has been assigned at `:400`, so the degenerate result is live: **💾 Save Results** wrote `pch_results.csv` with a `P_fit` column of `1.0, 0.0, 0.0, …`, a **0-byte** `pch_results.txt` and an npz whose `fit_results` array is empty, all under a "Results saved as: …" success dialog. Validate the lengths (pad or reject) and refuse `len(initial_Ns) != n_components` instead of returning `ok: True`; guard the export on a valid fit.
- **Fix note:**

### RF-211
- **Status:** OPEN
- **Severity:** S2 (the reported goodness of fit is meaningless — χ²ᵣ ≈ 1e18 is printed as a normal result — because the fit is unweighted while the score is Poissonian)
- **Location:** `chisurf/plugins/pch/backend/services.py:145-148` (`resid` returns `pmod[mask] - pe[mask]`, no weights) versus `:156-160` (Pearson χ² on counts); mirrored in the GUI at `chisurf/plugins/pch/gui/tool.py:500-507` and printed by `chisurf/plugins/pch/cli/main.py`
- **Finding:** `least_squares` minimises the plain difference of probabilities, so the fit is dominated by the first few k (P ≈ 0.4 at k = 0) and the whole shoulder of the histogram carries essentially zero weight, while the quality is then scored as a Pearson χ² on *counts* over 1.5 M bins. For a counting histogram the residual has to be weighted by the Poisson error (σ = √(N·P)); as written the two disagree by ~18 orders of magnitude. Verified on `Leica_SP5.ptu` (channels 0,2 / 100 µs, 126 k-values, 1 501 367 bins), 1 component from the shipped defaults: the fit converged to ε = 0.6722, ⟨N⟩ = 2.6581 and reported **χ²ᵣ = 1.1325e18** (dof 75). The fitted model's mean is 1.124 counts/bin against the data's **4.433**, and it predicts P ≈ 4e-18 at k = 32…40 where **4 574–5 657** bins were actually observed — the top five χ² contributions are all from that region. The GUI shows this in the status bar and `csc pch analyze` prints `red. χ² = 1132474425680562304.000` with no warning that the fit failed; a user reading the ε/⟨N⟩ that were written back into the boxes has nothing telling them the numbers are worthless. Weight the residual by the expected counts and flag an out-of-range χ²ᵣ (and consider reporting the model vs. measured mean counts/bin, which is already available).
- **Fix note:**

### RF-212
- **Status:** OPEN
- **Severity:** S2 (the toolbar **ℹ Help** button is dead — nothing opens, no message)
- **Location:** `chisurf/plugins/pch/gui/tool.py:94` (`HelpDialog.__init__`) — `QDialogButtonBox` is not in the `from qtpy.QtWidgets import (...)` list at `:8-28`
- **Finding:** `HelpDialog` builds its OK button with `QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)`, a name that was never imported, so constructing the dialog raises `NameError: name 'QDialogButtonBox' is not defined`. `_show_help` (`:526-528`) has no `try`, so in the running application Qt swallows the exception at the signal boundary and the button simply does nothing — the one place that documents the workflow and the CLI is unreachable. Verified by calling `win._show_help()` directly. Add `QDialogButtonBox` to the import list. (The dialog also renders the plugin's own click group help, which prints `Usage: cli [OPTIONS]` rather than the real command name — worth fixing in the same pass.)
- **Fix note:**

### RF-213
- **Status:** OPEN
- **Severity:** S3 (the documented headless invocation does not exist and hangs by launching the GUI instead)
- **Location:** `chisurf/plugins/pch/README.md:41-42` and the Help text in `chisurf/plugins/pch/gui/tool.py:70-90`; real registration in `chisurf/core/cli.py` (manifest `entrypoints.cli` = `pch=chisurf.plugins.pch.cli:cli`)
- **Finding:** Both the README ("### CLI") and the in-app help tell the user to run `python -m chisurf pch analyze data.ptu --components 2 --bin-time 50`. `python -m chisurf` is the **GUI** entry point and ignores the extra arguments: `python -m chisurf pch --help` started the application (offscreen) and never returned — killed after 300 s with an empty output file. The plugin CLI is registered on `csc`, and `csc pch analyze test/data/clsm/Leica_SP5.ptu --components 1 --bin-time 100` runs end to end and prints the fit. Fix the two documented lines (and `csc pch refit`, which the README calls `pch refit`); a user following the README gets a hung process with no error.
- **Fix note:**

### RF-214
- **Status:** OPEN
- **Severity:** S3 (an empty channel selection dies on a raw numpy message and leaves the previous file's result on screen)
- **Location:** `chisurf/plugins/pch/backend/services.py:75` (`t_max = times.max()` on the masked array), surfaced by the `except` at `chisurf/plugins/pch/gui/tool.py:374-375`; the unused metadata is `routing_channels` from `_load_tttr_handler:38`
- **Finding:** The *Channels* field is free text defaulting to `0,2`, and nothing validates it against the file. Loading `test/data/clsm/Leica_SP8.ptu` (routing channels **1** and 15) and pressing **Compute PCH** with the default selects zero photons, so `times` is empty and `times.max()` raises `ValueError: zero-size array to reduction operation maximum which has no identity`, which the GUI shows verbatim in a "Error" box. Two things make it worse than a bad message: the status bar still reads `Loaded: /…/Leica_SP8.ptu (3,104,829 photons)` (the failing `_on_compute` never updates it), and both plots still show the **previous** file's data — the screenshot after the failure (`09_wrongchannels.png`) is indistinguishable from a successful run on the wrong file. `pch.load_tttr` already returns the file's `routing_channels`, and the GUI discards them: `_on_load` (`:325-343`) uses only `n_photons`. Populate/validate the channel field from the loaded file, raise a named error for an empty selection ("no photons in channels 0, 2 — the file has 1, 15"), and clear the plots when a new file is loaded or a compute fails.
- **Fix note:**

### Review 2026-07-26 — `chisurf/core/math/` (statistics, regularization, datatools)

Slice chosen by coverage rather than recency: the three general-purpose numeric
modules under `chisurf/core/math/` had **zero** findings on record, while
`discrete_lcurve_corner` alone is the corner detector behind every regularized
inversion in the tree (TCSPC MaxEnt, FCS MaxEnt, DEER Tikhonov/MaxEnt, the
`maxent_decay` RPC service, `flc_2d`). Every claim below was executed in the
`arm64` env (NumPy 2.4.6) against the real functions, not reasoned about.
Findings RF-215..RF-227.

### RF-215
- **Status:** OPEN
- **Severity:** S2 (the Durbin-Watson statistic is silently rescaled — perfect anti-correlation can be reported as strong positive correlation)
- **Location:** `chisurf/core/math/statistics.py:256` (`durbin_watson`, `return nom / max(1.0, denomminator)`)
- **Finding:** The denominator guard clamps the *value*, not the zero case: whenever `sum(r**2) < 1` the statistic is divided by `1.0` instead of by the sum, so the returned number is not a ratio at all and is not in `[0, 4]`. Verified: `durbin_watson([0.1, -0.1, 0.1, -0.1])` returns **0.12**, where the statistic is exactly **3.0** — a perfectly anti-correlated series reported as if it were strongly *positively* autocorrelated. The scaling is silent and magnitude-dependent (multiplying the same residuals by 10 changes the answer). This is consumed as a fit-quality verdict: `chisurf/core/fitting/fit.py:283` and `:1313` expose it as `Fit.durbin_watson`, `chisurf/gui/plots/residual_image.py:511` prints it, and `chisurf/core/agent/tools/decay.py:274` turns `durbin_watson < 1.5` into the sentence "the residuals are correlated" in an LLM-facing report. Reached whenever the weighted residual sum of squares is below one (a short fit range, over-estimated errors) or when the public helper is called on raw residuals. Guard the zero case instead (`return nom / den if den > 0 else 0.0`). `test/math/test_durbin_watson.py` pins the current behaviour via a `_reference` that copies the same clamp, so the fix must update that helper too.
- **Fix note:**

### RF-216
- **Status:** OPEN
- **Severity:** S2 (deprecated NumPy call on the shared L-curve corner path; already warns on the installed NumPy, breaks when it is removed)
- **Location:** `chisurf/core/math/regularization.py:417` (`discrete_lcurve_corner`, `dist = np.abs(np.cross(chord, P - P[0])) / chord_norm`)
- **Finding:** `np.cross` on 2-dimensional vectors was deprecated in NumPy 2.0 and is slated for removal. Verified in the project env (NumPy 2.4.6): `discrete_lcurve_corner(rho, eta)` emits `DeprecationWarning: Arrays of 2-dimensional vectors are deprecated. Use arrays of 3-dimensional vectors instead.` on every call. This is not a corner of the tree — the function is called from `chisurf/core/models/tcspc/maxent.py:198,376`, `chisurf/core/models/fcs/maxent.py:1020`, `chisurf/core/models/deer/tikhonov.py:94`, `chisurf/core/models/deer/maxent.py:161`, `chisurf/core/models/deer/deer.py:591`, `chisurf/plugins/fluorescence_decay/maxent_decay/{backend/services.py:239,gui/gui_run.py:174}` and `chisurf/gui/widgets/models/fcs/maxent_widget.py:274,1193`, so under a `-W error` run or a future NumPy every L-curve corner in ChiSurf fails at once (and most call sites swallow it in a bare `except`, so it degrades to "no corner" rather than an error). The 2-D cross product here is one line of arithmetic: `chord[0]*d[:, 1] - chord[1]*d[:, 0]`. Per the repo's compatibility rule this belongs in `chisurf/core/compat.py` if it is kept as a shim.
- **Fix note:**

### RF-217
- **Status:** FIXED
- **Severity:** S1 (`maxent.lcurve` **always** returns `corner_index: null` — the auto-selected regularization weight never reaches the client)
- **Location:** `chisurf/plugins/fluorescence_decay/maxent_decay/backend/services.py:239`, inside the `try` at `:236-241`
- **Finding:** The handler writes `corner_index = int(np.asarray(discrete_lcurve_corner(...))[0])`. `discrete_lcurve_corner` returns a **Python `int` or `None`**, so `np.asarray(...)` is a 0-dimensional array and `[0]` raises `IndexError: too many indices for array: array is 0-dimensional, but 1 were indexed` — verified directly. The surrounding `except Exception: corner_index = None` swallows it, so the RPC always answers `corner_index = None` even when a corner was found. The field is a declared part of the contract (`api/contract.py:114`, `api/models.py:75`) and the consumer reads it (`chisurf/gui/widgets/models/fcs/maxent_widget.py:257,1176`), falling back to recomputing the corner client-side — so the failure is invisible and the backend computation is wasted. Drop the `np.asarray(...)[0]` wrapper and handle `None` explicitly rather than by exception. See RF-218 for the masking defect in the same expression.
- **Fix note:** The one-line expression (and the `except Exception` that hid it)
  was replaced by a documented `_lcurve_corner_index` helper in the same module:
  it filters the sweep to the finite, positive points, returns `None` when fewer
  than three survive or when `discrete_lcurve_corner` finds no corner, and
  otherwise maps the corner back through `np.nonzero(usable)[0]` so the reported
  index refers to the unfiltered `log10_nu`/`chi2r`/`sol_norm` arrays — which
  also closes the `services.py` site of RF-218. Pinned by
  `chisurf/plugins/fluorescence_decay/maxent_decay/test/test_lcurve_corner.py`
  (corner is reported and never swallowed to `None`; index is offset back past
  filtered leading points; `None` without three usable points).

### RF-218
- **Status:** OPEN
- **Severity:** S2 (the corner index is an index into a *filtered* array but is reported against the unfiltered one)
- **Location:** `chisurf/core/models/tcspc/maxent.py:196-200` and `:374-378` (the `services.py` site was fixed with RF-217; only the two `tcspc/maxent.py` sites remain)
- **Finding:** All three sites build `mask = isfinite(chi2) & isfinite(sol_norm)`, call `discrete_lcurve_corner(chi2[mask], sol_norm[mask])`, and store the result as an index into the **unmasked** `_l_curve_log10_nu` / `chi2r` / `sol_norm` arrays that they also publish. As soon as one grid point fails to converge (a `NaN` χ², which is exactly what the surrounding code prepares for) the index is shifted and points at the wrong regularization weight. `discrete_lcurve_corner` already handles non-finite input itself — `_clean_lcurve_points` drops it and `return int(idx_all[k_local])` maps back to the *original* index — so the pre-masking is both unnecessary and the cause of the misalignment; `chisurf/core/models/fcs/maxent.py:1020` gets this right by passing the raw arrays. Secondary: `int(...)` on a `None` return raises `TypeError` into the bare `except`, and `_l_curve_corner_index` in `tcspc/maxent.py` is written but never read anywhere in the tree — the TCSPC MaxEnt L-curve has no consumer for its corner.
- **Fix note:**

### RF-219
- **Status:** OPEN
- **Severity:** S2 (linear interpolation with an inverted slope, plus a last point that is the mean of the tail)
- **Location:** `chisurf/core/math/datatools.py:228-241` (`align_x_spacing`, `method='linear-close'`)
- **Finding:** Two independent defects in the one interpolation branch. (1) The slope is built as `m = (ry2 - ry1) / (rx1 - rx2)` — the denominator is reversed, so `m` is the negative of the true slope and `ny[j] = m * tx[j] + ry1 - m * rx1` reflects the interpolated value about `ry1` instead of interpolating. (2) The guard `if j < len(tx) - 1` excludes the **last** template point, whose `else` branch runs `ny[j] = ry[i:].mean()` once per remaining sample, so the final value ends up as `ry[-1]` (the mean of a one-element tail) rather than an interpolated value. Verified on exactly linear data `y = 2x + 1`, template `x = [0.6, 1.7, 2.8]`: returns `[1.8, 3.6, 9.0]` where the correct answer is `[2.2, 4.4, 6.6]`. The function has no test (`test/math/test_datatools.py` covers its neighbours but not this one) and no caller in the tree; it is public API of `chisurf.core.math.datatools`, so either fix it with a test or delete it.
- **Fix note:**

### RF-220
- **Status:** FIXED
- **Severity:** S2 (returns uninitialized heap memory, and the moving average is not an average; the test that "covers" it asserts on that uninitialized memory)
- **Location:** `chisurf/core/math/datatools.py:396-421` (`smooth`), test at `test/math/test_datatools.py:89-99`
- **Finding:** Three defects. (1) `xz = np.empty(x.shape[0])` is filled only for `i in range(l - m)`; every element from `l - m` on is returned **uninitialized**. Verified: `smooth(np.arange(1, 11.), 8, 2)` returned `[..., 0, 0, 0, 0]` on a clean heap and `[..., 7., 8., 9., 10.]` on a dirtied one — the same call, two different answers. (2) The division `xz[i] /= (2 * m + 1)` sits *inside* the accumulation loop, so each partial sum is divided again on every iteration; a window of ones gives `0.2496` instead of `1.0`. (3) The window `range(i - m, i + m)` is asymmetric (it omits `i + m`, so it is `2m` wide, not `2m + 1`) and for `i < m` the negative indices wrap to the end of the array. `test_smooth_edge_cases` asserts `np.all(smoothed[2:] == 0)`, which only holds when the freshly-allocated page happens to be zero — a flaky test that documents the bug rather than catching it. The function has no caller in the tree (`chisurf/plugins/chimol/chimol/geometry/spline.py:42` defines an unrelated `smooth`); delete it or rewrite it against `np.convolve` with a real test.
- **Fix note:** Rewritten as a real centred moving average over a running sum:
  `smooth(x, m)` now returns a same-length array whose element `i` is the mean of
  `x[i - m : i + m + 1]`, with the window **clipped** to the array bounds instead
  of wrapping, and `m <= 0` (or an empty input) returning an unmodified copy. The
  `l` parameter is gone — it existed only to bound the loop that left the tail
  uninitialized, and the function had no caller in the tree. The flaky
  `test_smooth_edge_cases` (which asserted on the uninitialized page) is replaced
  by three real tests in `test/math/test_datatools.py`: a constant signal is a
  fixed point including at the edges, a unit spike spreads symmetrically over
  `2 * m + 1` samples, the first element never sees the tail, an over-wide `m`
  averages everything, and every element is finite and bracketed by the input
  range for `m` in `0..5`.
  Incidental in the same module: `distance_between_gaussian` now zeroes
  non-finite weights before normalizing, so one NaN distance no longer turns the
  whole distribution into NaN — this had been failing the "NaN handling" case of
  `test_distance_between_gaussian` (`np.sum` of an array containing NaN can never
  be 1.0). Note this `datatools` copy is a plain Gaussian and is *not* the
  distance distribution between two Gaussians that the two same-named functions
  in `chisurf/core/math/functions/{rdf,distributions}.py` compute; it has no
  caller and the name collision is recorded separately as RF-228.

### RF-228
- **Status:** OPEN
- **Severity:** S3 (three public functions share one name; one of them computes a different quantity)
- **Location:** `chisurf/core/math/datatools.py:13-45`, `chisurf/core/math/functions/rdf.py:283-320`, `chisurf/core/math/functions/distributions.py:322-370`
- **Finding:** `distance_between_gaussian` exists three times. The two under `functions/` agree — `p(r) = r/d * (N(r; d, σ) - N(r; -d, σ))`, the distance distribution between two Gaussian-distributed points — and `chisurf/core/models/tcspc/fret.py:327` binds the `rdf` one. The copy in `datatools.py` is a **plain Gaussian** `exp(-(r - d)² / 2σ²)` under the same name, which is a different quantity, and it has no caller in the tree. `functions/rdf.py` and `functions/distributions.py` are themselves character-for-character duplicates of each other. → Keep one implementation (the `functions/` one the model already uses), re-export it, and either delete the `datatools` copy or rename it to what it computes (`gaussian_distance_distribution` / `normal_pdf`). Do not merge blindly: the `datatools` signature is the one covered by `test/math/test_datatools.py`.
- **Fix note:**

### RF-221
- **Status:** OPEN
- **Severity:** S2 (`IndexError` on the upper bin edge — the one x-value the caller is most likely to pass)
- **Location:** `chisurf/core/math/datatools.py:75-79` (`histogram_rebin`)
- **Finding:** The out-of-range test is `xi > max(bin_edges) or xi < min(bin_edges)`, so `xi == max(bin_edges)` falls through to `sel = np.where(xi < bin_edges)`, which is empty, and `sel[0][0]` raises `IndexError: index 0 is out of bounds for axis 0 with size 0`. Verified: `histogram_rebin(np.array([0, 5, 10, 15]), np.array([0, 2, 1]), np.array([15.0]))` raises. The docstring example and `test/math/test_datatools.py:19` both dodge it by choosing new edges that never land exactly on the last edge. Either make the upper edge inclusive of the last bin or exclude it explicitly (`xi >= max(...)`), and add the boundary to the test. Same loop recomputes `max(bin_edges)`/`min(bin_edges)` for every new edge. Also: the return list mixes Python `0.0` floats with raw `counts` elements, so under NumPy 2 the docstring example renders as `np.int64(0), np.int64(2), …` and its doctest fails — latent today only because `test-doctest` runs `pytest test --doctest-modules` and never collects `chisurf/`. Returning `float(...)` uniformly fixes the example on both NumPy majors and matches the declared "list or float" contract.
- **Fix note:**

### RF-222
- **Status:** OPEN
- **Severity:** S2 (values below `bin_min` are counted into a bin near the *top* of the histogram instead of being discarded)
- **Location:** `chisurf/core/math/datatools.py:285-288` (`bin_count`)
- **Finding:** `bin_index = int(np.rint(data[i] / bin_width) - n_min)` is only checked against the upper limit (`if bin_index < n_bins`). For any sample below `bin_min` the index is negative and Python's negative indexing wraps it to the far end of `count`, so out-of-range data is silently added to a valid-looking bin. Verified: `bin_count(np.array([0, 10]), bin_width=16, bin_min=1000, bin_max=4095)` — both samples are far below `bin_min` — returns a histogram with counts at indices **132 and 133** of 194 and a total of 2.0, instead of an empty histogram. The existing test only uses `bin_min=0`, where the bug cannot fire. Add the lower bound to the guard (`if 0 <= bin_index < n_bins`). Note the function is unused in the tree.
- **Fix note:**

### RF-223
- **Status:** OPEN
- **Severity:** S3 (misleading docstring on a public numeric helper: it is not the KL divergence and does not skip what it says it skips)
- **Location:** `chisurf/core/math/statistics.py:259-293` (`kl`)
- **Finding:** The docstring says "Compute the Kullback-Leibler divergence D(P || Q)" and "If either p[i] or q[i] is zero, that term is skipped in the summation". Neither is accurate. The body accumulates `s += qi` **unconditionally** and then `s += pi*log(pi/qi) - pi` when both are positive, i.e. it computes the *generalized* KL divergence (I-divergence) `sum(p log(p/q) - p + q)` — which coincides with KL only for normalized inputs, and which returns a finite number for `q_i == 0, p_i > 0` where the true divergence is infinite. Verified: `kl([1, 0], [0.5, 0.5])` = `log 2` (right, because normalized), while for unnormalized inputs the answer differs from `sum(p log(p/q))` by `sum(q) - sum(p)`. Either rename it to `generalized_kl_divergence` and state the formula, or restrict it to KL. The function has no caller in the tree, and is `@nb.jit(nopython=True)` without `cache=True` — the same first-use compile stall that `durbin_watson` (`:245-249`) was explicitly de-JIT-ed to avoid.
- **Fix note:**

### RF-224
- **Status:** OPEN
- **Severity:** S3 (two public functions with different names, parameter names and defaults compute exactly the same expression)
- **Location:** `chisurf/core/math/statistics.py:296-333` (`chi2_max`) and `:336-368` (`chi2_threshold`)
- **Finding:** The two bodies are the same formula character for character — `chi2 * (1 + n_params/nu * scipy.stats.f.isf(1 - level, n_params, nu))` — differing only in argument names (`chi2_value`/`number_of_parameters`/`conf_level` vs `chi2_min`/`n_extra_params`/`p_value`) and in the default confidence (0.95 vs 0.99). They already drift in intent: `chi2_threshold` is what the support-plane scan uses (`chisurf/core/fitting/support_plane.py:239,395`), `chi2_max` is what the F-test plugin panel uses (`chisurf/plugins/core/f_test/gui/tool.py:80`), and `chisurf/plugins/core/f_test/test/test_widgets.py:90` exists only to assert the two agree. Keep one and alias the other, so the two user-facing tools cannot diverge.
- **Fix note:**

### RF-225
- **Status:** OPEN
- **Severity:** S3 (the docstring contradicts the code in both branches; whoever calls it will pass the wrong quantity)
- **Location:** `chisurf/core/math/statistics.py:182-219` (`bayesian_information_criterion`)
- **Finding:** The two branches interpret `value` in opposite ways and the docstring matches neither. The `'gaussian'` branch returns `n * value + k * log(n)`, which is the standard Gaussian BIC only if `value` is `ln(RSS/n)`; the docstring says it is "the maximized value of the likelihood function", and the `Parameters` block says it is "the reduced chi-squared (chi2/n)" — as written, passing either gives a number that is not a BIC (the missing `log` is the whole point of the form). The `else` branch returns `k*log(n) - 2*log(value)`, which *does* treat `value` as a likelihood — the opposite of what the `Parameters` block claims for the non-Gaussian case. The doctest (`bic(k=3, n=100, value=2.5) == 263.8155...`) only pins the arithmetic, not the meaning. The function has no caller in the tree; fix the contract (one meaning for `value`, stated) or remove it.
- **Fix note:**

### RF-226
- **Status:** OPEN
- **Severity:** S3 (silent `inf`/`nan` solution for a rank-deficient matrix instead of an error or a rank clamp)
- **Location:** `chisurf/core/math/regularization.py:179-180` (`tsvd`)
- **Finding:** `k` is clamped to `[0, s.size]` but never to the numerical rank: `x = V[:, :k] @ ((U[:, :k].T @ b) / s[:k])` divides by any zero (or denormal) singular value inside the first `k`, producing `inf`/`nan` that then propagate into the returned `rho`/`eta` norms with no warning. `csvd` returns the full compact spectrum including exact zeros for a rank-deficient forward matrix, and truncated SVD is precisely the tool one reaches for when the matrix *is* rank-deficient, so the degenerate input is the expected one. Clamp `k` to `np.count_nonzero(s > tol * s[0])` or drop the zero components from the sum. `gcv` (`:216`) and `l_curve` (`:262`) already filter with `s[s > 0.0]`; `tsvd` is the odd one out.
- **Fix note:**

### RF-227
- **Status:** OPEN
- **Severity:** S3 (the L-curve corner index it returns cannot be mapped back to a regularization weight)
- **Location:** `chisurf/core/math/regularization.py:234-276` (`l_curve`), dead assignment at `:264`
- **Finding:** `l_curve` builds `reg_param = np.logspace(...)` internally and returns only `(rho, eta, corner)`, so a caller holding the corner index has no way to recover the corresponding `lam` short of duplicating the `lo`/`hi`/`logspace` derivation. The sibling `sample_lcurve` gets this right by returning an `LCurveData` that carries `reg` alongside the norms and exposes `corner_reg`. Also at `:264` the degenerate branch assigns `reg_param = np.array([1.0, 10.0])` and then returns `np.ones(2), np.ones(2), None` without using it — dead code that hints the return signature was meant to include it. Return `reg_param` (or an `LCurveData`) so the function is usable for what it exists to do. Only caller today is `test/fitting/test_regu.py:80`.
- **Fix note:**

## Review run — the anisotropy / orientation-factor layer (2026-07-26)

Slice: `chisurf/core/fluorescence/anisotropy/` (`kappa2.py`, `decay.py`,
`integrals.py`, `__init__.py`) plus the `nusiance` seam it shares with
`chisurf/core/fluorescence/fret/__init__.py` — a subsystem with no findings on
record. Every claim below was executed against the tree in the `arm64` env, not
read off. Two of them are live in shipping code paths: `kappasq_all` feeds the
κ² calculator's default cone model, and `calculate_kappa_distance` feeds the FRET
trajectory tool. RF-229..RF-238.

### RF-229
- **Status:** FIXED
- **Severity:** S1 (the isotropic orientational average is wrong by up to a factor of two — dipoles are sampled from one octant of a cube, not from the sphere)
- **Location:** `chisurf/core/fluorescence/anisotropy/kappa2.py:361-362` (`kappasq_all`: `d1 = np.random.random(3)`, `d2 = np.random.random(3)`)
- **Finding:** `np.random.random(3)` draws each component uniformly from `[0, 1)`, so both transition-dipole vectors are confined to the **positive octant** of the unit cube and are not uniform on the sphere (corner-biased). `kappasq_all` exists to produce the orientational average for the wobbling-in-a-cone model, so this is its entire job. Measured over 60k–100k samples against the same `kappasq` with proper isotropic (Gaussian) vectors: at `sD2 = sA2 = 1` the code gives ⟨κ²⟩ = **0.334 ± 0.428** where the exact answer is **2/3** (isotropic sampling reproduces 0.6667 ± 0.717); at the docstring's `sD2 = 0.3, sA2 = 0.5` it gives 0.6164 ± 0.1372 versus 0.6665 ± 0.1943, i.e. a biased mean and a width understated by ~30 %. The bug is invisible at `sD2 = sA2 = 0` (where `kappasq` returns 2/3 for any angle), which is why the doctest — which only checks `len` and `sum` of the histogram — never caught it. The sibling `kappasq_dwt` in the same file gets this right at `:66-67` with `np.random.randn`. Live: `chisurf/plugins/calculator/kappa2_dist/core/algorithms.py:87` calls `kappasq_all` for the cone model whenever `rAD_known` is false, and the reported ⟨κ²⟩/σ(κ²) and the κ²-derived distance range are read straight off it. Fix by drawing `np.random.randn(3)` (normalising is unnecessary — the code already divides by the norm) and add a test asserting ⟨κ²⟩ ≈ 2/3 at `sD2 = sA2 = 1`.
- **Fix note:** Already closed before this run reached it — commit `09eee6e9a`
  ("fix(kappa2): isotropic dipole sampling, unbiased moments, and plugin discovery")
  switched both draws to `np.random.randn(3)` and added
  `test/fitting/test_kappa2_distribution.py`, which pins ⟨κ²⟩ ≈ 2/3 across the order
  parameters. Re-verified against the source; status flipped only.

### RF-230
- **Status:** FIXED
- **Severity:** S1 (frames whose computation raises are filled with uninitialized heap memory and only announced on stdout)
- **Location:** `chisurf/core/fluorescence/anisotropy/kappa2.py:617-631` (`calculate_kappa_distance`: `np.empty` + `except Exception: print(...)`)
- **Finding:** `ks`/`ds` are allocated with `np.empty` and written only inside the `try`. When `kappa_distance` raises — it raises `ZeroDivisionError` for any frame where the two dipole endpoints coincide, e.g. a missing/duplicated atom — the loop body is abandoned *after* the allocation and *before* the assignment, so `ks[i_frame]`/`ds[i_frame]` keep whatever was on the heap. Verified: a `(3, 4, 3)` all-zero trajectory returns `[0., 0., 0.]` on a clean heap and `[7777., 7777., 7777.]` after dirtying the allocator with `np.full(3, 7777., dtype=np.float32)` buffers — the same call, two different answers, and the second is indistinguishable from a real κ². The only signal is `print("Frame ", i, "skipped, calculation error")` to stdout, which is neither logged nor returned. Live consumer: `chisurf/plugins/traj/fret_trajectory/traj2fret.py:305` writes these arrays into a FRET trajectory. Fill the skipped entries with `np.nan` (and use `logging`, not `print`), or return a validity mask. Same class as RF-220.
- **Fix note:** `ks`/`ds` are now allocated with `np.full(..., np.nan)`, so a frame the
  loop abandons reads `NaN` rather than whatever the allocator handed over, and the
  skip is reported through the module logger (`logging.getLogger(__name__)`) instead
  of `print`. The docstring says so under *Returns*. Pinned by
  `test/fitting/test_kappa2_trajectory.py`: the all-degenerate trajectory must be all
  `NaN` **and** must answer the same after the allocator has been dirtied with a
  recognisable `7777.0` pattern (which is exactly what the old code returned), a good
  frame next to a degenerate one keeps its `kappa = 1.0` / `d = 0.86603`, and the skip
  reaches `caplog`. Also fixed in passing: the `s2delta` doctest compared a NumPy bool
  (`np.True_`) against `True` and failed under NumPy 2.

### RF-231
- **Status:** OPEN
- **Severity:** S2 (two functions in the same module build "the VV and VH decays" with the G-factor in different places; they disagree for every g ≠ 1)
- **Location:** `chisurf/core/fluorescence/anisotropy/decay.py:102` (`vm_rt_to_vv_vh`: `vh = vm * (1. - g_factor * rt)`) against `:233-236` (`calculcate_spectrum`: `vh = e1tn(hstack([f, e1tn(d, -1.0)]), g_factor)`)
- **Finding:** `calculcate_spectrum` places `g` on the *whole* perpendicular channel — `f_VH = g · f_VM · (1 − r)` — and its own docstring (`:129-133`) argues explicitly that this placement is what makes the pair invert back to the anisotropy it was built from. `vm_rt_to_vv_vh` places `g` on the depolarization term only — `f_VH = f_VM · (1 − g·r)` — which does not. Verified with `r0 = 0.38`, `g = 1.5`, `τ = 4 ns`: the spectrum path gives `vh(0) = 0.930 = g·(1 − r0)` and inverting with `r = (VV − VH/g)/(VV + 2·VH/g)` recovers **0.3800**; `vm_rt_to_vv_vh` gives `vh(0) = 0.430 = 1 − g·r0` and the same inversion recovers **0.6314** — a 66 % error in the anisotropy. `g` is a detection sensitivity, so `calculcate_spectrum` is the correct one (and it is the one wired into `chisurf/core/models/tcspc/anisotropy.py:264`). The two agree at `g = 1`, which is exactly the value the `vm_rt_to_vv_vh` doctest uses, so nothing catches it. `vm_rt_to_vv_vh` has no caller in the tree but is public, documented and doctested; fix the placement (and its docstring at `:25`) or delete it.
- **Fix note:**

### RF-232
- **Status:** OPEN
- **Severity:** S2 (a documented parameter raises `TypeError` for every value except its default)
- **Location:** `chisurf/core/fluorescence/anisotropy/integrals.py:79-80`, `:100-101` and `:165-166` (`float(np.sum(..., axis=axis))` in `compute_g_factor_isotropic`, `compute_g_factor_perrin` and `anisotropy_from_integrals`)
- **Finding:** All three functions take `axis: Optional[int] = None`, documented as "Axis along which to sum", and then wrap the reduction in `float(...)`. For any non-`None` axis on a ≥2-D input the reduction returns an array and `float()` raises. Verified on `(2, 2)` inputs with `axis=0`: all three raise `TypeError: only 0-dimensional arrays can be converted to Python scalars`. The parameter is therefore unusable as documented, and `AnisotropyResult` is a scalar dataclass that could not hold a per-axis result anyway. Either drop `axis` from the three signatures and the docstrings, or make the whole path array-valued (and change `AnisotropyResult`'s field types with it). No caller in the tree passes `axis`, and `test/fitting/test_anisotropy_integrals.py` never exercises it.
- **Fix note:**

### RF-233
- **Status:** OPEN
- **Severity:** S2 (a decorator that writes its arguments into the wrapped function's module globals — cross-call leakage, not thread-safe, and it destroys the function's identity)
- **Location:** `chisurf/core/fluorescence/intensity.py:21-44` (`nusiance.m` assigning into `f.__globals__`), applied at `chisurf/core/fluorescence/anisotropy/__init__.py:13,62` and `chisurf/core/fluorescence/fret/__init__.py:15,53,93,127,167,212,255,290`
- **Finding:** Each call writes `Gfactor`, `Bp`, `Bs`, `l1`, `l2`, `Bg`, `Br`, `crosstalk`, `phiA`, `phiD`, `R0` into the *module dictionary* of the wrapped function and then calls it, so (a) two concurrent callers with different correction factors read each other's values — the ChiSurf server runs handlers off the main thread — and (b) every call resets to the hard defaults (`Gfactor=1.0`, `l1=l2=Bp=Bs=0.0`, `phiA=phiD=1.0`) any factor the *previous* caller set, silently. Verified: `fr.fret_efficency_to_fdfa(E=0.4, phiA=0.32, phiD=0.80)` leaves `chisurf.core.fluorescence.fret.phiA == 0.32`, and the next unrelated call rewrites it to `1.0`. Secondly, the wrapper has no `functools.wraps`, so `chisurf.core.fluorescence.anisotropy.r_exp.__name__` is `'m'`, its `__doc__` is `'Set the correction globals, then call the wrapped function.'` and its signature is `(*args, **kwargs)` — `doctest.DocTestFinder` finds **zero** doctests in either module, so the ten carefully written examples in these two files are never collected by `pytest --doctest-modules` and `help()` shows nothing. Also `nusiance(f, *args, **kwargs)` declares `*args, **kwargs` it never uses. Pass the corrections as real keyword arguments with defaults (or a small frozen `Corrections` dataclass) and delete the global write; at minimum add `functools.wraps`.
- **Fix note:**

### RF-234
- **Status:** OPEN
- **Severity:** S2 (the module's five "instrument constants" are dead, and both documented example results are unreachable)
- **Location:** `chisurf/core/fluorescence/anisotropy/__init__.py:5-10` (`Bp`, `Bs`, `Gfactor`, `l1`, `l2`) with the doctests at `:48-55` and `:92-98`
- **Finding:** The module defines `Bp = 10.0`, `Bs = 5.0`, `Gfactor = 1.2`, `l1 = 0.1`, `l2 = 0.2` under the comment "normally defined elsewhere", and the two docstrings walk through arithmetic based on exactly those numbers — `r_scatter(signal_vertical=100, signal_parallel=150)` → `0.3193...` and `r_exp(signal_parallel=150, signal_vertical=100)` → `0.3305...`. But `@nusiance` overwrites all five with `1.0`/`0.0` on entry to *every* call unless the caller passes them as kwargs, so the first call to either function permanently zeroes the module constants. Verified: both calls return **0.14285714285714285**, and after them `an.Bp, an.Bs, an.Gfactor, an.l1, an.l2 == (0.0, 0.0, 1.0, 0.0, 0.0)`; only `r_exp(..., Gfactor=1.2, l1=0.1, l2=0.2)` reproduces the documented `0.3305785123966942`. Nothing catches this because the doctests are not collectable (RF-232). Delete the five module constants and rewrite both examples to pass the corrections explicitly. Neither function has a caller in the tree.
- **Fix note:**

### RF-235
- **Status:** OPEN
- **Severity:** S2 (a function documented as the inverse of its sibling is not the inverse, and cannot be given the parameters it needs)
- **Location:** `chisurf/core/fluorescence/fret/__init__.py:290-319` (`fdfa2transfer_efficency`) against `:255-287` (`fret_efficency_to_fdfa`)
- **Finding:** Two defects. (1) `fret_efficency_to_fdfa` returns `fdfa = (phiA/phiD)·(1/E − 1)`; inverting that gives `E = 1/(1 + fdfa·phiD/phiA)`, but `fdfa2transfer_efficency` computes `1.0/(1.0 + fdfa*phiA/phiD)` — the yield ratio is upside down, and the docstring ("performs the inverse conversion of the relation used in `fret_efficency_to_fdfa`") states the wrong formula alongside it. (2) `fdfa2transfer_efficency(fdfa)` is the one `@nusiance`-decorated function in the module with **no `**kwargs`**, while the decorator forwards `**kwargs` to it verbatim — so the only channel for supplying `phiA`/`phiD` raises. Verified with `phiA = 0.32`, `phiD = 0.80`: `E = 0.4` → `fdfa = 0.6` (correct); `fdfa2transfer_efficency(0.6, phiA=0.32, phiD=0.80)` raises `TypeError: got an unexpected keyword argument 'phiA'`, and the only callable form, `fdfa2transfer_efficency(0.6)`, returns **0.625** against the true inverse **0.4**. Add `**kwargs` and swap the ratio, with a round-trip test at `phiA != phiD`.
- **Fix note:**

### RF-236
- **Status:** OPEN
- **Severity:** S2 (returns `nan` for physically reachable inputs, with no guard and no documented failure mode; the `nan` propagates into a user-facing κ² histogram)
- **Location:** `chisurf/core/fluorescence/anisotropy/kappa2.py:568-570` (`s2delta`)
- **Finding:** `s2_delta = r_inf_AD / (r_0 · s2_donor · s2_acceptor)` is fed straight into `arccos(sqrt((2·s2_delta + 1)/3))` with no clamp, so the result is `nan` whenever `s2_delta > 1` or `s2_delta < −0.5`, and `ZeroDivisionError`/`inf` when either order parameter is zero. Verified: `s2delta(s2_donor=0.2, s2_acceptor=0.3, r_inf_AD=0.1)` returns `(4.386, nan)` with only a `RuntimeWarning`. Those are values a user can type: `chisurf/plugins/calculator/kappa2_dist/core/algorithms.py:60-75` derives `sd2 = −sqrt(r_Dinf/r_0)` (deliberately negative) and `sa2 = +sqrt(r_Ainf/r_0)` from three residual anisotropies entered in the GUI, so the product is negative and the ratio is unbounded; the `nan` delta then goes into `kappasq_all_delta(delta=nan, …)` at `:79` and the plotted histogram is empty with no error shown. The docstring documents neither the `nan` nor the domain. Validate the ratio (raise or return `nan` explicitly with a documented contract) and have the plugin surface it.
- **Fix note:**

### RF-237
- **Status:** OPEN
- **Severity:** S3 (copy-paste in the histogram weight: `sin(beta1)²` instead of `sin(beta1)·sin(beta2)`)
- **Location:** `chisurf/core/fluorescence/anisotropy/kappa2.py:173` (`kappasq_all_delta_new`: `weight_beta2 = np.sin(beta1)`)
- **Finding:** The inner loop runs over `beta2` but computes its solid-angle weight from `beta1`, so `weights.append(weight_beta1 * weight_beta2)` accumulates `sin(beta1)²` and the returned `k2hist` is weighted by the wrong measure — the `beta2` dependence of the weight is dropped entirely. The `_new` variant has no caller in the tree (the plugin uses the numba `kappasq_all_delta`, which builds `beta2` geometrically and weights only by `sin(beta1)`, correctly for its parameterisation) and no test, so this is dead code with a latent bug: either fix the line to `np.sin(beta2)` with a test, or delete the function rather than leaving two divergent implementations of the same distribution.
- **Fix note:**

### RF-238
- **Status:** OPEN
- **Severity:** S3 (two implementations of the same one-line formula with different parameter names and opposite error contracts)
- **Location:** `chisurf/core/fluorescence/anisotropy/integrals.py:18-48` (`perrin_steady_state_anisotropy(tau, rho, r0)`) and `chisurf/plugins/vv_vh_g_factor/core/calculations.py:291-312` (`perrin_steady_state_anisotropy(tau_ns, rho_ns, r0)`)
- **Finding:** Same body — `r0 / (1 + tau/rho)` — but the core version **raises `ValueError`** for `rho <= 0` while the plugin version **returns `np.nan`**, and the keyword names differ (`tau`/`rho` vs `tau_ns`/`rho_ns`), so the two are not interchangeable at a call site. The plugin's RPC handler (`chisurf/plugins/vv_vh_g_factor/backend/services.py:89`) and its GUI (`gui/tool.py:668`) both bind the plugin copy, and `chisurf/plugins/vv_vh_g_factor/test/test_calculations.py:29` pins the plugin copy while `test/fitting/test_anisotropy_integrals.py:14` pins the core copy — nothing asserts they agree. Keep the core one (it is the shared physics layer), re-export it from the plugin under the `tau_ns`/`rho_ns` spelling, and pick one behaviour for `rho <= 0`.
- **Fix note:**

### Review 2026-07-26 — the FRET calibration layer (light-path prior → posterior)

Slice: `chisurf/core/fluorescence/fret/{calibration,accurate,lines,forster}.py` — the
smFRET correction-factor stack behind the accurate-FRET tool
(`95472049`), a subsystem with three findings on record against ~5300 lines.

The Bayesian scaffolding is sound (the Gaussian precision-weighting in
`refine_calibration` and `_combine_with_optics_priors` is the correct combination,
and the derivatives in `efficiency_uncertainty` / `distance_from_efficiency` all
check out against `E = F_DA/(F_DA + γ·F_DD)`). What does not hold is the **units of
the two sides being combined**: for both `alpha` and `delta` the light-path prior
mean and the data estimator compute *different quantities* of the same name, and
`_combine_with_optics_priors` precision-averages them (RF-239, RF-240). Findings
RF-239..RF-248 below.

### RF-239
- **Status:** OPEN
- **Severity:** S1 (the light-path prior mean for `alpha` is a different quantity from the `alpha` every consumer applies; biases every corrected E)
- **Location:** `chisurf/core/fluorescence/fret/calibration.py:289-290` (`lightpath_correction_factors`: `den_a = gG*c_gd + gR*c_rd`)
- **Finding:** The light path computes `alpha = gR·c_rd / (gG·c_gd + gR·c_rd)` — the *fraction of all detected donor photons* landing in the red channel (the legacy MFD convention, cf. `chisurf/core/models/pda/nusiance.py:261-273`, whose docstring spells it `alpha = R_D0/(G_D0 + R_D0)`). But every consumer of `CalibrationParameters.alpha` uses the Hellenkamp definition `alpha = I_DA/I_DD`, i.e. the ratio to the **green channel only**: `correct_three_cube` via `es.corrected_es` subtracts `alpha*F_DD`, `global_es_correction:505` computes `f_da = r - alpha*g - delta*y`, and this module's own data estimator `leakage_from_donor_only:938-941` returns `<i_da>/<i_dd>`. The class docstring at `:67` explicitly claims Hellenkamp nomenclature. Verified on one optics payload (`c_gd = 0.85`, `c_rd = 0.06`, `gG = gR = 1`): `lightpath_correction_factors` returns `alpha = 0.06593` while `leakage_from_donor_only` on donor-only counts generated by those same optics returns `0.07059` — the light-path value is `alpha/(1+alpha)`, ~6.6 % low here and worse for leakier dyes. `_combine_with_optics_priors` (`accurate.py:1336-1364`) then precision-averages the two, and `set_priors_from_lightpath:462` seeds the parameter and its `TruncatedNormalPrior` from the wrong one. The fix is `den_a = gG * c_gd` (with `qy_d` cancelling); `test/fitting/test_fret_calibration.py:20-22` builds its payload to match the *current* formula (`c_rd = alpha/(1-alpha)*c_gd`) and must be updated together with a cross-check that the light-path α equals `leakage_from_donor_only` on donor-only counts synthesised from the same matrices.
- **Fix note:**

### RF-240
- **Status:** OPEN
- **Severity:** S1 (the light-path `delta` is referenced to the donor, the consumed `delta` to the acceptor-excitation channel; they differ by the factor `beta`)
- **Location:** `chisurf/core/fluorescence/fret/calibration.py:284,291` (`lightpath_correction_factors`: `ex_ag = _cell(exc, laser, acceptor)`, `delta = ex_ag / ex_dg`)
- **Finding:** `delta` is computed as `exc[green_laser, acceptor] / exc[green_laser, donor]` — direct acceptor excitation relative to **donor** excitation by the same laser. Every consumer treats `delta` as the coefficient of the acceptor-excitation signal: `es.corrected_es` forms `F_DA = (I_DA−B) − alpha·F_DD − delta·F_AA`, `global_es_correction:505` subtracts `delta*y` (`y = i_aa`), and this module's data estimator `direct_excitation_from_acceptor_only:972-977` returns `<F_DA>/<F_AA>`. Those two ratios differ by exactly the excitation-flux ratio `beta` (the light-path `excitation` payload holds per-`(laser, dye)` excitation *probabilities* including the laser's own flux — `lightpath_simulator/backend/simulator.py:196-213`), so they agree only when `beta = 1`. The acceptor-excitation laser row that the correct expression needs — `exc[red_laser, acceptor]` — is present in the payload and never read; the function only ever consults the single `laser` row. As in RF-239, `_combine_with_optics_priors` precision-averages this prior mean with the acceptor-only data estimate of a different quantity, and `set_priors_from_lightpath:463` makes it the `TruncatedNormalPrior` mean. Take the acceptor-excitation laser as a second argument and return `exc[green, acceptor]/exc[red, acceptor]`, or state the convention and convert by `beta` at the seam.
- **Fix note:**

### RF-241
- **Status:** OPEN
- **Severity:** S2 (a mislabelled detector silently yields `alpha = 1.0` and `gamma = NaN` instead of the documented default)
- **Location:** `chisurf/core/fluorescence/fret/calibration.py:225-232` (`_cell`) and `:280-292`
- **Finding:** `_cell(payload, row, column, default)` returns its `default` only when the payload is **empty**; when the payload exists but lacks the requested label, `crosstalk.matrix_from_payload:64-69` contributes a **zero** row/column by design ("Requested labels missing from the payload contribute a zero row/column"), so the `default=1.0` given for `c_gd` and `c_ra` is dead in exactly the case it was written for. A typo'd or renamed detector/dye label therefore produces `c_gd = 0` → `den_g = 0` → `gamma = NaN`, and, worse, `den_a = gR·c_rd > eps` → `alpha = 1.0`, i.e. "100 % of the donor signal leaks into the red channel". Verified: with a valid payload and `green_detector="GREEN"` instead of `"gdet"`, `lightpath_correction_factors` returns `{'gamma': nan, 'alpha': 1.0, 'delta': 0.03}` with no warning; `set_priors_from_lightpath` then seeds those as prior means, and `parameters.py:250-253` in the light-path plugin skips only the non-finite `gamma`, keeping `alpha = 1.0`. Have `_cell` verify the label is present in the payload (`payload["rows"]`/`["columns"]`) before falling back to `default`, and raise or warn when a requested label is unknown. Compare `pda/nusiance.py:21-37` (`_matrix_cell`), which does return its default on a missing label.
- **Fix note:**

### RF-242
- **Status:** OPEN
- **Severity:** S2 (the donor-excitation laser is guessed from row order; a differently ordered payload silently drops the direct-excitation correction)
- **Location:** `chisurf/core/fluorescence/fret/calibration.py:278` (`laser = green_laser if … else (exc.get("rows", [None]) or [None])[0]`)
- **Finding:** With no explicit `green_laser` the donor-excitation laser is taken to be the payload's **first** excitation row, with no check that this laser actually excites the donor — and `lightpath_simulator/core/parameters.py:243` passes exactly that default (`self.lasers[0]`). `get_excitation_rows` sorts its records by `(laser, dye)` label, so the ordering is alphabetical on the laser name, not physical: a setup whose acceptor-excitation laser sorts first (e.g. `"635"` before `"cw532"`, or any name-based ordering) silently yields `ex_dg = 0` → `delta = 0.0`. Verified: on a payload identical except for `rows = ["635", "532"]`, `lightpath_correction_factors` returns `delta = 0.0` — the direct-excitation correction is dropped entirely and nothing reports it. Pick the row that maximises the donor's excitation (or require the label), and warn when the chosen row's donor excitation is zero.
- **Fix note:**

### RF-243
- **Status:** OPEN
- **Severity:** S1 (a failed E-S fit is written back as `gamma = 0.05`, the parameter's lower bound, and reported as a normal result)
- **Location:** `chisurf/core/fluorescence/fret/calibration.py:597-609` (`refine_calibration`)
- **Finding:** `refine_calibration` never checks that the data estimate is finite. When `global_es_correction` returns `NaN` — which it does for reachable data, e.g. a population with zero total signal makes `1/S` infinite and `np.polyfit` return all-`NaN` — `data_sigma` becomes `NaN` (`max(NaN, 1e-6)` is `NaN`), `gamma_post` becomes `NaN`, and `calib.gamma = float(np.clip(NaN, 0.05, 20.0))` writes `NaN` into the bounded `FittingParameter`, which silently degenerates it to the **lower bound**. Verified end-to-end: with one all-zero population, `global_es_correction` returns `{'gamma': nan, 'beta': nan, …}` and `refine_calibration` leaves `calib.gamma == 0.05` while the returned dict reports `gamma_data = nan`, `data_sigma = nan` — so `out["gamma"]` looks like a plausible number and flows on to `calibration_to_setup` and every corrected `E`. The sibling path already gets this right: `calibrate_from_samples:1033` gates on `np.isfinite(est["gamma"])` before assigning. Gate the assignment the same way (keep the prior/current value and say so in the result) and pin it with a test on a degenerate population.
- **Fix note:**

### RF-244
- **Status:** OPEN
- **Severity:** S2 (`NaN` from an empty or fully background-cancelled reference sample passes the zero-guard and lands in the calibration)
- **Location:** `chisurf/core/fluorescence/fret/calibration.py:940-941` (`leakage_from_donor_only`) and `:976-977` (`direct_excitation_from_acceptor_only`)
- **Finding:** Both estimators guard with `return float(np.mean(f_da) / denom) if denom != 0 else 0.0`, which does not catch `NaN`: `np.mean([])` is `NaN` and `NaN != 0` is `True`, so an empty reference selection returns `NaN` rather than the intended fallback. Verified: `leakage_from_donor_only([], [])` and `direct_excitation_from_acceptor_only([], [])` both return `nan` (only a `RuntimeWarning`), and `calibrate_from_samples(calib, fret, donor_only=(array([]), array([])))` leaves `calib.alpha == 2.2250738585072014e-308` — the `NaN` written into the bounded parameter reads back as a denormal, i.e. silent garbage that neither raises nor looks like a failure. Reachable from the GUI whenever a gate selects no bursts, and from `_estimate_alpha_delta` if a class mask is non-empty but its background-corrected mean is zero. Use `np.isfinite(denom) and denom != 0`, and document the fallback.
- **Fix note:**

### RF-245
- **Status:** OPEN
- **Severity:** S2 (`UnboundLocalError` on a documented parameter value)
- **Location:** `chisurf/core/fluorescence/fret/accurate.py:1118-1199` (`auto_calibrate`: `estimated` bound only inside the iteration loop)
- **Finding:** `estimated` (and `es`) are assigned only inside `for iteration in range(1, int(n_iterations) + 1)`, but they are read afterwards at `:1199` (`_combine_with_optics_priors(calib, uncertainties, estimated, messages)`). `n_iterations` is a public parameter documented as "Maximum self-consistency iterations", so `0` is a natural way to ask for "no self-consistency"; it raises instead. Verified: `auto_calibrate(dd, da, aa, n_iterations=0)` → `UnboundLocalError: cannot access local variable 'estimated' where it is not associated with a value`. Initialise `estimated = {"alpha": False, "delta": False, "gamma": False}` before the loop (`split` is already handled defensively at `:1207`), or validate `n_iterations >= 1`.
- **Fix note:**

### RF-246
- **Status:** OPEN
- **Severity:** S2 (documented as a precision-weighted mean, implemented as an unweighted one)
- **Location:** `chisurf/core/fluorescence/fret/accurate.py:1274-1276` (`_select_gamma`, `source == "combined"`) against the `gamma_source` docstring at `:1044-1046`
- **Finding:** `auto_calibrate`'s docstring advertises `gamma_source="combined"` as the "precision-weighted mean of both" estimates, but `_select_gamma` computes `float(np.mean(vals))` — a plain average, so a `gamma` the data pins to ±0.001 is dragged halfway toward one that is barely identified. Verified: `_select_gamma("combined", {"es": 1.0, "lifetime": 2.0, "lifetime_sigma": 0.001}, [])` returns `1.5`; precision weighting with those widths would return ≈2.0. The lifetime estimator's own width is already available (`gamma_from_lifetime` returns `sigma`, stored as `gamma_estimates["lifetime_sigma"]` at `:1161`) and is simply unused here; the E-S width is not, which is presumably why the weighting was skipped — either weight by the widths that exist (falling back to equal weights when one is `NaN`) or correct the docstring.
- **Fix note:**

### RF-247
- **Status:** OPEN
- **Severity:** S2 (the reported `sigma_gamma` can describe a different estimator than the `gamma` that was adopted, inflating it by the systematic difference between the two)
- **Location:** `chisurf/core/fluorescence/fret/accurate.py:1401-1424` (`_bootstrap_uncertainties`) and `:1196-1197`
- **Finding:** Two ways the `gamma` uncertainty stops describing the reported `gamma`. (1) Inside the bootstrap loop the branch is chosen *per resample*: `if aa is not None and len(np.unique(labels)) >= 2` uses the E-S fit, `elif tau is not None and line is not None` uses `gamma_from_lifetime`. So with ALEX data whose resamples occasionally contain only one sub-population, both estimators feed the **same** `collected["gamma"]` list whose `np.std` becomes `uncertainties["gamma"]`. The two are not interchangeable by design — `gamma_from_lifetime`'s own docstring (`:817-819`) says "compare its `gamma` against the E-S value: a mismatch is itself the evidence for sub-burst dynamics" — so the reported width absorbs that systematic offset. (2) `:1196-1197` falls back to `gamma_estimates["lifetime_sigma"]` whenever the bootstrap width is non-finite, even when `gamma_source="es"` and the adopted `gamma` came from the E-S fit; that width is then propagated into `accurate_fret` and into `calibration_to_setup`'s stored `uncertainties`. Keep one estimator per bootstrap (skip the resample instead of switching), and tag the fallback width with the estimator it came from.
- **Fix note:**

### RF-248
- **Status:** OPEN
- **Severity:** S2 (the "Gaussian" distance distribution puts ~3.5× too much amplitude on the clipped lower bound)
- **Location:** `chisurf/core/fluorescence/fret/lines.py:133-135` (`gaussian_distance_distribution`)
- **Finding:** The weight is evaluated at the **clipped** distance rather than at the sampled offset: `r = np.clip(mean + offsets, r_min, None)` and then `w = exp(-0.5*((r - mean)/sigma)**2)`. Every sample whose distance was clipped therefore receives the *same* weight — that of `r_min` — instead of its own, much smaller, tail weight, so the pile-up at `r_min` is over-weighted by the number of clipped samples. Verified for the default line parameters (`mean = 10 Å`, `sigma = 6 Å`, `n_points = 81`, `n_sigma = 3.5`, `r_min = 1 Å`): 23 of 81 samples are clipped and carry **0.2176** of the normalised weight, against **0.0626** when the weight is computed from the offset. The effect on the static line's `E` is small because those samples are fully quenched either way (ΔE ≈ 1.0e-4 at 10 Å, 5.6e-5 at 15 Å, zero beyond ~20 Å), but `fret_lifetime_spectrum` returns this amplitude spectrum *directly* for decay simulation, where 21.8 % rather than 6.3 % of the amplitude sits at `tau ≈ 0` — a visibly wrong simulated decay at short mean distance. Compute `w` from `offsets` (the distribution the docstring describes) and keep the clip only on the distance used for `(r0/R)^6`.
- **Fix note:**

### Review 2026-07-26 — PDA N-state rate matrices (`c47687c62`)

Slice: the newest landing — `PdaDynamicNStates` / `PdaDynamicNStateModel`
(`chisurf/core/models/pda/dynamic_mc.py`), the shared `rate_matrix` AutoForm
section it is the first consumer of, and the Szabo–Gopich quadrature that is now
the model's **default** route. The headline claim holds: the rates really are
discovered by `find_parameters` now (verified — `k1_2 … k3_2` all appear in
`parameters_all_dict`), and `rate_matrix()` / `rate_values` agree on the
`K[target, source]` convention. Below it, the default quadrature matches its beta
on the wrong interval (RF-258), the editor rewrites the parameters it renders
(RF-259, RF-260), and resizing the scheme silently undoes the fixed/free and link
setup the class docstring advertises as the way to express a scheme (RF-261).
Findings RF-258..RF-262.

### RF-258
- **Status:** OPEN
- **Severity:** S1 (the default route puts ~30 % of the probability spectrum on FRET states the scheme cannot produce, and is ~8× further from the exact law than the same approximation on the right support)
- **Location:** `chisurf/core/fluorescence/kinetics.py:205-206` (`szabo_gopich_quadrature`, `lower: float = 0.0, upper: float = 1.0`) with `:247-249` and `:268`, called at `chisurf/core/models/pda/dynamic_mc.py:372-375` without `lower`/`upper`
- **Finding:** The beta is moment-matched on ``[lower, upper] = [0, 1]`` rather than on the interval the observable can actually reach. A time average of a piecewise-constant observable taking values ``v_i`` is a convex combination of them, so it lives on ``[min(v), max(v)]`` — support ``[0, 1]`` is only correct when a state has ``pG = 0`` and another ``pG = 1``. Verified against **two independent references** (the exact two-state law `two_state_occupation_quadrature`, and a direct Gillespie simulation) for two states with ``pG = 0.35 / 0.65``, symmetric exchange, `n_nodes=2048`, total variation on 81 bins over ``[0, 1]``:

  | K = k_ex·T | TV, beta on [0,1] | TV, beta on [min,max] | weight outside [0.35, 0.65] |
  |---|---|---|---|
  | 0.4 | 0.786 | **0.065** | 0.305 |
  | 1.6 | 0.436 | **0.150** | 0.216 |
  | 8 | 0.060 | 0.056 | 0.031 |
  | 40 | 0.007 | 0.008 | 0.000 |

  In slow exchange (`K = 0.4`) **30.5 % of the weight sits at green probabilities no mixture of the two states can produce**, including spikes at ``pG = 0`` and ``pG = 1``; that spectrum goes straight into `tttrlib.Pda`, so the modelled S1S2 histogram carries donor-only-like and acceptor-only-like populations the scheme never contains. The same holds at wider spans (`pG = 0.1/0.9`: TV 0.799 vs 0.096 at `K = 0.4`). This also revises the commit message's own explanation: the slow-exchange error is dominated by the wrong support, not by "a beta density cannot represent the point masses" — on ``[min(v), max(v)]`` the ``concentration → 0`` limit *is* two atoms at the state values, which is why TV falls 12×. Pass ``lower=float(np.min(values)), upper=float(np.max(values))`` (defaulting to the value range inside `szabo_gopich_quadrature` is the cleaner fix, since every caller wants it). Note the moments are preserved either way, so `test_the_quadrature_reproduces_the_moments_it_was_matched_to` cannot see this; the discriminating test is TV against `two_state_occupation_quadrature`, or simply asserting `nodes` never leaves ``[min(values), max(values)]``.
- **Fix note:**

### RF-259
- **Status:** OPEN
- **Severity:** S1 (merely opening the model editor silently rewrites rate parameters — a 5 MHz rate is written back as 1 MHz, a factor of 5, with no message)
- **Location:** `chisurf/gui/autoform/sections/rate_matrix_section.py:156` (the unconditional `self._write_back(n)` closing `_build`) with `:135` (`spin.setRange(self._min, self._max)`) and `:140` (`spin.setValue(...)`)
- **Finding:** `_build` populates each `QDoubleSpinBox` from the model and then pushes **all** spin values straight back onto the model attribute. A `QDoubleSpinBox` silently clamps to its range and rounds to its `decimals`, so any model value outside the section's configured `minimum`/`maximum` — or with more precision than `decimals` — is destroyed by the round trip, without the user touching anything. Verified headlessly with the exact options from `dynamic_mc.view.json` (`minimum: 0.0, maximum: 1e6, decimals: 2`) on a `PdaDynamicNStates` whose rates were set to `k1_2 = 5.0e6`, `k2_1 = 2.5e6`, `k1_3 = 123.456`: `rate_values` before construction `[0, 5e6, 123.456, 2.5e6, …]`, immediately after `RateMatrixWidget(...)` `[0, 1e6, 123.46, 1e6, …]` — and `rates_by_name()["k1_2"].value` is `1000000.0`, i.e. the **fitting parameter itself** was moved. The same corruption is reachable through `refresh()`: it clamps the display silently (signals blocked, so no write), after which editing *any other* cell calls `_write_back` and commits every clamped value. `_build` should not write back values the user has not edited; the write-back belongs on `valueChanged` only, and a value outside the configured range should be reported rather than clamped.
- **Fix note:**

### RF-260
- **Status:** OPEN
- **Severity:** S2 (the editor's range is three decades narrower than the parameter's own bounds, so a legitimate rate is unreachable and — via RF-259 — destroyed)
- **Location:** `chisurf/core/models/pda/dynamic_mc.view.json:45,48` (`"decimals": 2`, `"maximum": 1000000.0`) against `chisurf/core/models/pda/dynamic_mc.py:144` (`lb=0.0, ub=1e9`)
- **Finding:** Every rate parameter is created with `ub=1e9` Hz, but the rate-matrix grid is configured with `maximum: 1e6`. Verified: `rates_by_name()["k1_2"].bounds == (0.0, 1e9)` while the grid's spin box refuses anything above `1e6`. Rates between 1 MHz and 1 GHz are ordinary for fast conformational exchange and are exactly what the optimiser is allowed to explore — so a fit can converge to a rate the editor cannot display, and (with RF-259) will overwrite with `1e6` the next time the panel is built. `decimals: 2` has the same shape of problem at the other end: a rate below 0.005 Hz rounds to zero, which the model reads as "no transition". Derive the grid's range from the bound parameters (or raise `maximum` to `1e9` and use a sensible relative precision), and keep the two in one place so they cannot drift again.
- **Fix note:**

### RF-261
- **Status:** OPEN
- **Severity:** S2 (changing the state count silently re-fixes every freed rate and drops every link — undoing exactly the setup the class docstring says is how you express a scheme)
- **Location:** `chisurf/core/models/pda/dynamic_mc.py:137-146` (`n_states` setter: `self._rates = []` then a fresh `FittingParameter` per pair) against the class docstring at `:71-79` and `dynamic_mc.view.json:36` (`"Adding one keeps the rates already set"`)
- **Finding:** The resize carries over `p.value` only (`old_rates` at `:122`); `fixed`, the bounds, and any link are rebuilt from the defaults, and the parameter **objects are replaced**, so anything holding a reference to the old ones is silently orphaned. Verified on a three-state group: freeing `k1_2`/`k2_1` and linking `k2_1 → k1_2` (a detailed-balance constraint, the exact idiom `rates_by_name()`'s docstring at `:155-165` advertises), then `n_states = 4`, gives `free = []`, `k2_1.is_linked == False`, and `rates_by_name()["k1_2"] is` the old object `== False`. So a user who sets up a linear chain (`k1_3 = k3_1 = 0`, fixed) and frees the rest, then adds a state, gets every rate fixed again with no indication — and the linear-chain zeros survive only as values, not as an intent. Carry the surviving parameter *objects* across the resize (append/pop rather than rebuild) so `fixed`, bounds and links are preserved, and pin it with a test that frees + links a rate, resizes both ways, and asserts the flags survive.
- **Fix note:**

### RF-262
- **Status:** OPEN
- **Severity:** S2 (the sampling route the module documents as the answer in slow exchange has no control, while the spinner that configures it is on screen)
- **Location:** `chisurf/core/models/pda/dynamic_mc.py:278` (`self.method = "szabo-gopich"`) and `:366`, with `dynamic_mc.view.json` (no section for `method`) and `dynamic_mc.py:104-106` (`n_windows`)
- **Finding:** `method` is assigned once in `__init__` and read once in `update_model`; it is written nowhere else in the tree (`grep -rn "\.method\s*=" chisurf/` finds only the constructor) and `dynamic_mc.view.json` contains no control for it, so from the GUI the model is permanently on the analytic route. The module docstring (`:33-37`) and the `method` comment (`:267-277`) both say the Monte-Carlo route is the one to use in the slow-exchange limit "where the distribution is multimodal and no two-moment match has three peaks" — which is also where RF-258 bites hardest — yet a user has no way to select it. The inverse is on screen: `n_windows` is a `FittingParameter` on the states group (verified present in `parameters_all_dict`), so the `N_win` spinner is rendered in the *N-state kinetics* parameter table where it does nothing at all in the default mode. Add a `choice` section for `method` (and hide or annotate `n_windows` when the analytic route is selected).
- **Fix note:**
