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
- **Status:** OPEN
- **Severity:** S3 (validation hole)
- **Location:** `chisurf/core/experiments/ics/precision.py:485` (`rics_precision`), via `precision.py:385` (`correlation_covariance`, `denom`)
- **Finding:** Scan timing is validated (`pixel_time * nx > line_time` raises a clear `ValueError`), but the two other inputs that can only fail are not. `n_lags >= min(nx, ny)` makes `denom = (nx - xi) * … * f**4` zero: verified `rics_precision(10.0, …, nx=6, ny=6, n_lags=6)` → `ZeroDivisionError: float division by zero`, and `correlation_covariance(6, 6, 6, …)` the same, while `nx=8` still returns a matrix (whose smallest eigenvalue is -0.22, so `nearest_spd` is doing real work there rather than mopping up round-off). `diffusion_coefficient=0` divides by zero in `tau_c = w_r**2 / (4*d)`. Both are one-line guards next to the existing timing check; the defaults (`n_lags=6`, `nx=ny=64`) are safe, so this only bites a caller that shrinks the image or sweeps `D` down to zero.
- **Fix note:**

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
- **Status:** OPEN
- **Severity:** S1 (removed NumPy alias; blocks the whole multi-run ALV path)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:571` (`mysplit`, `lensplit = np.int(np.ceil(N/n))`)
- **Finding:** `np.int` was removed in NumPy 1.24; the project env runs NumPy 2.4.6, where the attribute raises. `mysplit` returns early only for `n <= 1`, so every ALV-5000/6000 file with more than one run reaches it and dies with `AttributeError: module 'numpy' has no attribute 'int'` before any data is produced. Reproduced end-to-end: `read_asc('junk/quickfit3/plugins/fccsfit/examples/NUNC3_dil_050p_025_ccf.ASC')` → `AttributeError` from `openASC_old:239 → mysplit:571`; patching `np.int = int` lets the same call return 7 datasets. Per the CLAUDE.md dependency rule this is a pure rename and belongs in `chisurf/core/compat.py`, not a local rewrite — but the call site here can simply use the builtin `int`. Grep the tree for other `np.int`/`np.float`/`np.bool` survivors while fixing.
- **Fix note:**

### RF-044
- **Status:** OPEN
- **Severity:** S1 (a committed test file cannot be opened at all)
- **Location:** `chisurf/core/fio/fluorescence/fcs/asc_alv.py:553` (`openASC_ALV_7004`, `dictionary["Trace"] = np.array(tracelist)`)
- **Finding:** In the four-curve ALV-7004 mode `a-ch0+1  c-ch0/1+1/0`, `tracelist` mixes single traces (`trace1`, shape `(n, 2)`) with *pairs* for the cross-correlations (`[trace1, trace2]`, shape `(2, n, 2)`) — see `:482-497`. `np.array` on that ragged list raises since NumPy 1.24. Verified on the committed sample `test/data/fcs/asc/ALV-7004USB_ac01_cc01_10.ASC` (header `Mode : "A-CH0+1  C-CH0/1+1/0"`, `MeanCR0 152.07`, `MeanCR1 85.07`): `openASC(...)` → `ValueError: setting an array element with a sequence. The requested array has an inhomogeneous shape after 1 dimensions. The detected shape was (4,) + inhomogeneous part.` So every dual-channel FCCS measurement from this instrument is unreadable. `dictionary["Correlation"]` at `:552` is fine (all curves share a shape); the trace list must stay a plain Python list — `openASC_old` already returns it as one (`:342`), and `read_asc:650` explicitly branches on `isinstance(d['Trace'][i], list)`, so the consumer expects it.
- **Fix note:**

### RF-045
- **Status:** OPEN
- **Severity:** S1 (the noise model's baseline is the mean of nearly the whole curve)
- **Location:** `chisurf/core/fluorescence/fcs/__init__.py:131` (`noise`, `correlation_offset = np.mean(correlation[-lb:-ub])`)
- **Finding:** With the default `correlation_amplitude_range = (0, 16)` this is `correlation[-0:-16]`, i.e. `correlation[0:-16]` — everything *except* the last 16 points, not the last 16 points. The offset is meant to be the long-lag baseline (the next line subtracts it from `mean(correlation[0:16])`, the short-lag amplitude), but it instead averages the amplitude region into the baseline. Verified on `test/data/fcs/asc/ALV-7004.ASC` (231 points): as coded the slice takes 215 points and gives `offset = 1.215952`; the intended tail `correlation[-16:]` gives `1.000315`. The derived amplitude is therefore `A = 0.152` instead of `0.368` — a factor 2.4. `A` enters `suren` quadratically (`S ∝ A²/ns`) and `starchev` as `N = 1/A` cubed, and it also shifts the half-amplitude crossing used to estimate `diffusion_time` at `:138`, so this biases **every** weight ChiSurf computes for FCS. No caller ever overrides `correlation_amplitude_range` (only three references tree-wide, all in this file), so the default is the only path. Fix the slice (`correlation[-ub:]` or an explicit `(baseline_lb, baseline_ub)` pair) and pin the offset with a test on a synthetic `G = 1 + A/(1+t/τ)`, where the answer is known exactly.
- **Fix note:**

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
- **Status:** OPEN
- **Severity:** S1 (`ZeroDivisionError` from a GUI-reachable setting; silently negative variance below it)
- **Location:** `chisurf/core/experiments/ics/precision.py:415` (`correlation_covariance`, `denom`) and `:402` (`term1`, `2 * (nx - 2 * xi) * (ny - 2 * psi)`), unguarded by the validation block at `:521-535`
- **Finding:** `rics_precision` validates the times, the sizes and `D`, but never `n_lags` against `nx`/`ny`, and both are user-facing spin boxes: `precision.view.json:87` gives `nx` a **minimum of 8** while `:109` gives `n_lags` a **maximum of 15**. At `n_lags >= nx` the loop reaches `xi == nx`, `denom = (nx - xi) * … = 0`, and the call dies with `ZeroDivisionError: float division by zero` — verified through the GUI view model (`nx = ny = 8`, `n_lags = 8` → `compute()` returns False with status `Prediction failed: float division by zero`). That contradicts the documented contract (`Raises ValueError …`) *and* defeats `sweep_dwell`'s per-point recovery, which catches `ValueError` only, by deliberate comment (`core.py:175-179`) — so one bad *global* setting takes the whole curve down rather than one point. Below that, for `2 * n_lags > nx`, `2 * (nx - 2 * xi)` — a count of pixel positions where the triple product fits — goes **negative** (nx=16 → −4 at xi=9) and subtracts from a variance with no error at all. One guard fixes both: reject `2 * n_lags >= min(nx, ny)` with a `ValueError` naming the offending pair, and clamp the overlap count at 0. Pin it with a test that asserts the raise for `nx=8, n_lags=8` and that `sweep_dwell` propagates it rather than returning a curve of NaNs.
- **Fix note:**

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
