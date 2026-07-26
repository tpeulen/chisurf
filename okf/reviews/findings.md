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
- **Status:** OPEN
- **Severity:** S1 (every curve in a multi-run ALV file is the same interleaved garbage)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:187` (`openASC_old`, `data = [[]]*len(curvelist)`)
- **Finding:** `[[]]*n` builds `n` references to **one** list, so `data[i].append(...)` in the row loop at `:190-192` appends every column of every row to a single shared list; all `np.array(data[t])` at `:245-332` are then the identical, row-major-interleaved array. Verified on the real ALV-5000 multi-run file `junk/quickfit3/plugins/fccsfit/examples/NUNC3_dil_050p_025_ccf.ASC` (183 lag times × 7 curves): `read_asc` returns 7 datasets that are **byte-identical**, each with 1281 points instead of 183, whose `correlation_times` begin `[0.0002, 0.0002, 0.0002, …]` — the same lag repeated once per curve. Duplicated lag times then make `np.diff(times)` zero inside `noise()`, which is where the `divide by zero encountered in divide` warnings from `chisurf/core/fluorescence/fcs/__init__.py:147` come from. Fix: `data = [[] for _ in curvelist]`. (RF-043 currently masks this by crashing first.) No test covers a multi-run ALV file.
- **Fix note:**

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
- **Status:** OPEN
- **Severity:** S1 (Python-2 method; every single-curve ConfoCor file fails to load)
- **Location:** `chisurf/core/fio/fluorescence/fcs/confocor3.py:360` and `:379` (`openFCS_Single`, `Alldata.__getslice__(i, i+length)`)
- **Finding:** `list.__getslice__` was removed in Python 3 (`hasattr([], '__getslice__')` is `False` on the project interpreter), so both the trace and the correlation import raise `AttributeError` the moment they are reached. `openFCS` dispatches here for every `.fcs` file whose first line is not `Carl Zeiss ConfoCor3` — i.e. ConfoCor2 and older AIM single-curve exports. All 15 committed ConfoCor test files carry the multi-curve header, so the whole function is untested and has been dead since the Python 3 port. Replace with ordinary slicing (`Alldata[i:i+length]`, as `openFCS_Multiple` already uses at `:143` and `:173`). While there: `newtrace` (`:371`) and `corr` (`:387`) are assigned only inside `if length != 0`, so a zero-length section makes `:392`/`:396` raise `NameError`/`UnboundLocalError` instead of reporting a malformed file.
- **Fix note:**

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
- **Status:** OPEN
- **Severity:** S1 (both export menu items raise on every non-empty dataset)
- **Location:** `chisurf/plugins/burst/burst_selection/gui/tool.py:3055` (`export_bur`) and `:3071` (`export_flr_cif`)
- **Finding:** Both guards are `if not self._last_frame:` and `_last_frame` is a `pandas.DataFrame`, so the guard raises `ValueError: The truth value of a DataFrame is ambiguous. Use a.empty, a.bool(), a.item(), a.any() or a.all()` exactly when there *is* something to export — before the file dialog opens, so the whole *File → Export → Export as .bur / Export as flrCIF* surface is dead. Verified by driving the widget: with 620 bursts loaded both calls raise; after `clear()` both correctly write "No burst data to export." to the summary (`not None` is `True`), which is why the bug is invisible to a smoke test that never loads data. Use `if self._last_frame is None or self._last_frame.empty:` (the same idiom the rest of the class already uses at `:2040`, `:2438`, `:2543`) and add a test that exports a non-empty frame to `tmp_path` with the file dialog patched.
- **Fix note:**

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
- **Status:** OPEN
- **Severity:** S1 (a parameter the sampler never moved is reported as the best-converged one in the table, with no warning — or as the worst, decided by floating-point luck)
- **Location:** `chisurf/core/fitting/diagnostics.py:157-160` (the `not (within > 0.0)` guard in `_ess_1d`) against `:114-124` (`autocovariance`, FFT-based)
- **Finding:** The guard meant to catch a constant parameter is unreachable for a real constant chain: `autocovariance` centres with `x - x.mean()` and transforms through the FFT, so lag 0 comes back as a rounding residual (~1e-31) rather than `0.0`, and the entire ESS/τ/MCSE machinery then runs on that noise. Verified on `np.full((4, 2000), v)` — a parameter that is *bit-identical in all 8000 draws*: `v = 1.234`, `0.001`, `3.7` → `ess = 4.0`, `tau = 1998`; `v = 0.0`, `1.0`, `0.5`, `2.5` → the residual happens to be exactly `0.0`, the guard fires, and `ess = 8000`, `tau = 1.0`, `mcse ≈ 0`, `rhat = 1.0`, **`convergence_warnings` returns `[]`**. Identical situations, opposite verdicts, decided only by whether the constant is binary-exact — and the silent branch is the one a parameter pinned at a bound of `0.0` takes. This is on the live path: `sample_fit` → `_write_sampling_diagnostics` (`chisurf/core/fitting/fit.py:2166-2167`) writes it to `diagnostics.json` and logs the warnings. Test the *range* (`np.ptp(block) == 0.0`, as `rank_normalized_rhat:361` and `bulk_tail_ess:399` already do) instead of a floating-point variance, and report a frozen parameter as such rather than as either extreme.
- **Fix note:**

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
- **Status:** OPEN
- **Severity:** S1 (a shipped CLI command is dead: `csc trace-browser` cannot start)
- **Location:** `chisurf/plugins/tttr/trace_browser/manifest.json:29` (`"cli": "trace-browser=chisurf.plugins.tttr.trace_browser.cli:cli"`) resolving to `chisurf/plugins/tttr/trace_browser/cli/__init__.py`, which does not export `cli`, while the intended `chisurf/plugins/tttr/trace_browser/cli.py` ("Trace Browser CLI compatibility shim", re-exporting `cli.main:cli`) is permanently shadowed by the sibling `cli/` package
- **Finding:** A regular package always wins over a same-named module in the same directory, so `import chisurf.plugins.tttr.trace_browser.cli` yields the package and the shim file is unreachable. Reproduced through the real production path: `python -m chisurf.core.cli trace-browser --help` → `Error: Failed to import plugin CLI 'Spectroscopy:Single-Molecule:Trace Browser:cli': module 'chisurf.plugins.tttr.trace_browser.cli' has no attribute 'cli'`. The failure only appears at invocation because `chisurf/core/cli.py` registers commands from the manifest without importing the plugin, so `csc --help` lists a command that always errors. The sibling plugins that got this right point their manifest at `cli.main:cli` (e.g. `tttr_microtime_shifter`) or re-export `cli` from `cli/__init__.py` (e.g. `tttr_time_windows`); do one of the two here and delete the unreachable shim. A static resolve of every in-tree manifest entrypoint (`entrypoints.gui/cli/services` → module file → attribute defined or imported) flags this as the only broken one, so it is a one-plugin fix.
- **Fix note:**

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
