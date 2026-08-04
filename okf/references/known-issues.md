## chimol: every scene rebuild refits the camera, throwing your framing away

**Found 2026-08-04**, while photographing `cartoon_side_chain_helper` — the
framing kept resetting between the "off" and "on" shots.

`MolView._update_view(fit_camera=True)` is the default, and a rebuild is what
colouring, a representation change, a label, a bond edit and **every `set`** all
trigger. Measured on 148L: `zoom resi 20-26` puts the camera distance at
**1.26**, and the next `set` of *anything at all* puts it back to **5.0**. So
framing a binding site and then adjusting a stick radius loses the framing — in
a viewer, which is a serious thing to get wrong. PyMOL moves the camera only for
a camera command (`zoom`/`orient`/`center`/`reset`) or a load (`auto_zoom`).

**Attempted and reverted**: flipping the default to `False` and passing `True`
from the three load paths (`set_structure`, `set_coordinates`, `add_volume`) is
*not* sufficient, and the suite says so — `test_ray_command.py::
test_every_representation_reaches_the_image` then traces an **empty image** for
all four representations. `ray` and the headless load path both depend on this
refit to frame at all: at the point the load paths call it the scene has no
geometry to measure, so the first rebuild that *does* is what actually frames.
An `auto_zoom`-once flag (frame on the first build with geometry) does not fix
it either, because in that test the window is never shown and `_update_view`
returns early with no renderer.

The real fix moves framing to where a structure is loaded and the scene is
built, rather than flipping a default — six call sites had already been patched
to `fit_camera=False` one at a time, which is the signature of a default that is
wrong but load-bearing. Left as it was, because a half-verified change across
~64 call sites in a viewer is worse than a known defect.

Six call sites already pass `fit_camera=False`; the ones that matter for a user
are colouring, representations and `set`.

---

## Stale tests left behind by finished refactors

**Found 2026-08-03**, while running the guard suites for the PSF calculator's
guide/help and export work. Six failures in `test/gui` and `test/server` that
have nothing to do with that change, and are not flaky — they fail on an idle
machine, on paths with no uncommitted edits, so they are committed breakage
rather than another instance's work in flight.

* `test/gui/project/test_info_json.py::test_info_json_uppercase` and its
  duplicate `test_info_json_uppercase.py` monkeypatch
  `filter_widget.load_detector_setups`. That method moved off the widget and
  became the module-level `chisurf.core.data_io.detector_setups.load_detector_setups`
  in the SV-01 Qt-free split; the tests still patch the bound method, so they
  raise `AttributeError` before asserting anything.
* `test/gui/settings/test_acquisition_simulation_autoform.py` references an
  undefined `TestWidget` (`NameError`) in three tests.
* `test/gui/test_mmfdb_picker.py::test_shared_client_adopts_chisurf_login_session`
  expects the shared client's token to be `None` and finds one.

Not fixed in the change that found them: each is a test that a *completed*
refactor left pointing at the old shape, and repairing one means deciding what
the refactor intended it to assert — which belongs with whoever owns that
refactor, not with a change to a calculator plugin. Recorded rather than
silently skipped, because a red suite that everyone steps over is how the next
real regression gets missed.

Fixed in passing, since they were unambiguous and one line each: the
`node_editor` package promising names in `__all__` it never bound, the
`ReentrancyGuard` that never guarded, `to_elementary` keeping the keys it was
asked to skip, a missing `Path` import, and three stale
`serialize_reader_state` mocks.

## test/server: the shared-server integration file errors and then hangs

**Found 2026-07-28**, while test-gating an unrelated proxy fix (RF-722).
`pytest test/server` never finishes: `test_integration_lifecycle.py` runs its
module-scoped `ChiSurfServer` in-process, and most of its tests error in
*setup* with

```
chisurf.startup.services.AppStartupError: service 'mmfdb' did not become ready
within 5.0s
```

after which the run stalls indefinitely at
`TestParameterLifecycle::test_linked_info` (>180 s, no output). The 5 s
`ready_timeout` in `chisurf/startup/services.py` is the visible trigger and it
is load-dependent — the same tests pass when the machine is idle, so a machine
running several suites (or several agent instances) turns it red. Which of the
two symptoms causes the other is not yet established: a server whose startup
raised may leave the ZMQ socket half-alive, which would explain a later call
that never returns.

Not fixed in the change that found it: the failure is in the shared server
fixture, not in anything that change touched (nothing in the file calls the
insertion routes it altered), and diagnosing a startup-timeout-plus-hang is its
own change. The proxy behaviour itself is covered by `test_proxy.py` and
`test_proxy_integration.py`, which are green.

**Update 2026-07-28 — the startup half is fixed; two other faults were behind
it.** The `mmfdb` stage now declares `"ready_timeout": 30` in
`chisurf/startup/services.d/10_mmfdb.json`. Measured, the stage costs **3.8 s**
on an *idle* machine for its first import, so the 5 s default was never a budget
— it was a hang-detector consuming 76 % of itself on a good day. Raising it
costs nothing in failure latency: `_run_service` records the exception and sets
`ready_event` on the way out, so a service that *fails* still surfaces at once
and only a service that truly *hangs* waits out the budget
(`test_app_startup_manager_reports_background_failure_without_waiting` pins
that, and `test_config_background_services_budget_a_cold_import` stops a new
background stage from silently inheriting the bare default). The server now
constructs, and `TestProxyLifecycle`/`TestLargePayload` run to completion in 8 s.

What that uncovered, both still open:

1. **The fit tests ask for a model that does not exist.** Every
   `client.fit__create(..., model_name="TCSPC")` returns `model 'TCSPC' not
   found`. `fit_create` (`chisurf/server/services/fits.py:410`) resolves a model
   by walking `Model.__subclasses__()` for one whose `name` matches; after
   importing `chisurf.core.models` the only reachable names are `Global fit` and
   `Model name not available`, so no spelling of that call can succeed. Two
   faults stacked: the name is stale, *and* the subclass walk only sees models
   some other import happened to pull in.
2. **The intended skip guard is dead.** `TestParameterLifecycle._setup` writes
   `if not ft.get("ok"): pytest.skip(...)`, but since [SV-04](../specs/assessment.md#sv-04)
   moved service errors into the JSON-RPC `error` member, `fit__create` *raises*
   `RemoteError` instead of returning `{"ok": False}`. So the guard never runs
   and 7 tests fail where the author meant them to skip. Do **not** patch the
   guard to swallow `RemoteError` — that would hide finding 1 rather than fix it.

**The hang is still unexplained**, and it is not specific to `test_linked_info`:
with the timeout raised the run now stalls in the same class at
`TestParameterLifecycle::test_set_bounds` (>5 min, no output), while
`test_set_value` and `test_set_fixed` — which reach the identical `_setup` —
fail fast a moment earlier.

**To close it:** give `fit.create` a model lookup that does not depend on what
happens to have been imported (an explicit registry, as the model/UI split
already needs), fix the test's model name, then give the client a receive
timeout so the remaining stall is a failure with a traceback instead of silence.

**Update 2026-08-03 — the model name is not the only blocker.** Driving the
server directly, with `chisurf.core.models.tcspc.lifetime` imported first so
the subclass walk can see it, both real names (`"Lifetime "` — note the
trailing space — and `"Lifetime (new)"`) get past the lookup and then fail in
`fit.create` itself with

```
'tuple' object has no attribute 'x'
```

so a dataset loaded over `dataset.load` with a `curve_data` payload does not
arrive as something `FitGroup` can build a fit on. Fixing the test's model name
alone would therefore turn a wrong error into a different wrong error. The
whole-suite symptom is unchanged: `pytest test/ --ignore=test/gui` still stalls
at `TestParameterLifecycle::test_set_bounds` (main thread blocked in
`zmq_ctx_destroy` → `ctx_t::terminate` → `mailbox_t::recv`, i.e. a context
being torn down while a socket still holds queued data), and run on its own the
class fails fast instead. So the hang needs state from the tests that precede
it.

## fitting over a genuinely remote server still has a 5-second deadline (2026-08-03)

`FittingClient.run_fit` no longer crosses the socket when the server is embedded
in this process -- which is the GUI's normal case, and where the bug actually
bit: the fit ran on the server thread, the GUI thread blocked in `recv`, and the
`fitting_timeout_ms` deadline (5000 ms, `settings.mmfdb`) expired mid-fit and
disabled RPC for the rest of the session:

    FittingClient: disabling RPC after transport failure in 'fit.run':
    timeout: no response within 5000ms

A real two-state MFD fit takes about 130 s, so it lost that race every time.

**Still open for a genuinely remote server.** Any fit longer than the deadline
will do the same thing over the wire, and the blocking call freezes the GUI for
its duration regardless. The right shape is almost certainly a job submitted to
the server's `JobManager` with progress arriving over the event bus -- the
machinery already exists for sampling (`_watch_sampling_job` polls exactly that
way). Not attempted here because this tree has no remote server to test against,
and a fix that cannot be run is a guess.

## quest: the plugin's RPC layer targets a backend the package does not have

**Found 2026-07-28.** Starting the GUI logs

```
Failed to register services for plugin 'quenching_estimator'
ModuleNotFoundError: No module named 'quest.backend'
```

`chisurf/plugins/quenching_estimator/` is deliberately a thin shell: its
`rpc/services.py`, `api/contract.py` and `api/client.py` all forward to
`quest.backend.services` / `quest.backend.contract` so the CLI, the web backend
and ChiSurf share one implementation of the sixteen `quest.*` methods the
manifest declares. That backend package does not exist -- not in the checked-out
`modules/quest`, and not on any of its branches (`git ls-tree` over `master`,
`main`, `dev`, `devel`, `development`, `chisurf-pin` shows only `quest/lib` and
`quest/settings`). So every `quest.*` RPC is unreachable, and the plugin's own
tests for the contract cannot run either. The GUI entry point still works: it
imports `quest.gui` directly and never touches the backend.

**To close it:** write `quest/backend/{contract,services}.py` in the quest
repository, over `quest.core` / `quest.api`, matching the schemas already in
`chisurf/plugins/quenching_estimator/manifest.json` (that file is the contract's
written form). It belongs there, not here: a second implementation ChiSurf-side
is exactly the `LAY-01` duplication the shell was built to avoid. Until then the
failure is a logged registration error, not a crash.

## packaging: the LaTeX converter has no Python 3.12 conda build

**Found 2026-07-28.** `chisurf/gui/widgets/models/parse/latex.py` renders a
parse-model formula through the third-party `latexify` converter. The
conda-forge package for it stops at Python 3.11, so it cannot go into the
recipe's `run:` list, and the module-level `from latexify import ...` therefore
made the module -- and with it the whole parse-model widget -- unimportable in
the released conda package. Only a pip install ever had it.

The import is now inside the conversion function, next to the `except` that
already fell back to `_convert_python_expression_to_latex_fallback`, the in-tree
AST converter. A conda install renders through the fallback instead of failing:
it covers the operators the parse models use, and is less complete than
`latexify` for anything exotic.

**To close it:** either a Python 3.12 build lands on conda-forge (then declare it
in the recipe and drop the fallback path from the hot path), or the in-tree
converter grows to full parity and the dependency goes for good -- it is one
`ast.NodeVisitor`, so the second is the more likely end state.

## RESOLVED — chimol: large integrative models, and the "fix" that killed them

**Opened and closed 2026-07-27.** The nuclear pore complex was the case that
showed it.

| Entry | Beads | Load before | Load after |
| --- | --- | --- | --- |
| `PDBDEV_00000010` (one spoke) | 29,273 | 8.7 s → 4.3 s | **0.36 s** |
| `PDBDEV_00000012` (eight spokes) | 234,184 | **430 s**, ~11 GB | **1.6 s**, 0.7 GB |

The cost was never the reader — `ihm` reads the 31.5 MB file in well under a
second. It was **a cartoon splined through beads that have no backbone**: 234k
beads become thousands of short chains, each fully splined, framed and extruded.
A bead stands for a *range* of residues, so the ribbon was meaningless as well as
expensive.

**The trap, explained.** Switching beads to the sphere representation — the
correct depiction, and what `set_rmf_data` already did — appeared to make the
entry *die silently*. It did not die. `ball_mask` was left all-**false** by the
mmCIF path (only the RMF path set it), and the sphere branch's fallback for "no
selection" is a **sparse sampling of 50 points along the chain**. The viewer drew
fifty dots and called it a nuclear pore. Nothing raised, because nothing was
wrong as far as any single line of it was concerned.

**What landed.** A bead model is now recognised in the viewer, so every reader
agrees on it: all beads selected, spheres on, cartoon and trace off, no bond
inference, per-bead radii carried through `set_coordinates` and scaled with the
coordinates. Past 20,000 beads the depiction is **sphere impostors** — one vertex
each, shaded as a sphere in the fragment shader — instead of ~160 vertices of
merged mesh per bead, with the impostor's world radius projected to a sprite size
so it follows the camera. Pinned by `test/test_bead_model.py`.

**IMP RMF support landed on 2026-07-28** — and the shape of what was wrong is
worth keeping. RMF was not missing the bead rule because nobody had written it
for RMF; it was missing it because RMF had *its own route into the viewer* and
therefore could not receive anything the common route learned. Measured: one
global radius for every bead, decimation instead of impostors, and hierarchy
check boxes that moved nothing. All of it silent. The fix was to remove the
route, not to duplicate the rule — see the log for that date.

**Still open from that thread:** interior culling (`_get_surface_atom_mask`
exists and is unused), dynamic LOD on camera motion (the draft/settle mechanism
from the trajectory work generalises), and depth-cue fog.

---

## chimol: three atom dtypes — RESOLVED 2026-07-28

Chimol carried **three** transcriptions of "the atom dtype every reader
produces", no two of them the same: a six-field one in `io/beads.py` for the
PDB/mmCIF/RMF readers, a twelve-field `_MDTRAJ_ATOM_DTYPE` for trajectory
topologies, and a twelve-field `PSEUDOATOM_DTYPE` in `cmd/editing.py`. Two of
the three carried a comment asserting they matched the core's `keys_formats`.

All three are gone. `chimol/io/atoms.py` (renamed from `beads.py`, since it now
owns the atom row and not only the bead) imports
`chisurf.core.fio.structure.coordinates.atom_dtype`. Rows are built by field
name (`atom_row(**fields)`) rather than as twelve-long positional tuples.

**The interesting part was not the duplication but what it hid.** The canonical
dtype had `chain` as `|U1`. An mmCIF asym id runs `A..Z` then `AA`, `AB`, …, so
on the eight-spoke nuclear pore 518 of 544 chains needed two characters and
every one was stored as its first letter: **544 chains became 26**, silently.
`chain AB` selected the whole of A and colouring by chain painted twenty
molecules alike. The field is `|U4` now. Widening it made the PDB *writer* a
hazard in turn — `%1s` is a minimum width in Python, not a truncation, so a
two-character id would have shifted every following column — so the writer uses
`%1.1s` and warns, naming the chains whose identity a PDB file cannot carry.

**`modules/quest` still carries two more copies of that PDB format string**
(`quest/lib/io/PDB.py`, `quest/lib/structure/Structure.py`), with the same `%1s`
that does not truncate. They are deliberately untouched: quest builds its own
atom arrays, so the core's widened `chain` cannot reach them, and quest is
slated for deprecation rather than repair. If any of it is kept, the writer goes
with the rest of the duplication — it should not be ported forward as it is.

---

## chimol: a ray-traced mesh is shaded twice, and comes out muddy

**2026-08-03.** Mesh vertex colours arrive at the tracer with ambient occlusion
*and* a cast shadow already multiplied in — `Geometry.occlusion` says so in its
own docstring ("Already multiplied into `colors`") — and the tracer then applies
its own lighting and its own shadows on top. Measured on the 148L cartoon: the
bake costs 44 % of the vertex colour (mean 0.567 → 0.318), and the traced image
is mean 33.3 against 54.5 for the same scene built with baking off. The picture
reads as muddy rather than as shaded, and the baked shadow comes from a *fixed*
light direction that need not be one of the ray lights.

**Not fixed here, and why the obvious fix is wrong.** Dividing the bake back out
of the colours is inexact: the shadow is folded into the `occlusion` channel with
a different constant from the AO (`shadow_darkness` 0.45 vs `darkness` 0.7), so
recovery is off by a mean 0.03–0.05 and up to 0.44 on individual vertices — a
colour error that looks like a colour, not like a bug. The right fix is to carry
the **base** colour plus the occlusion channel and let each backend apply it,
which changes the `Geometry` contract and therefore the GL backend too, and needs
verifying in a real window (offscreen creates no GL context). Worth doing; it is
its own change.

The depth-cue half of the same darkness *was* fixed — see
[the parity tracker](/plugins/pymol-parity.md).

---

## chimol: five camera-framing tests are red

**2026-08-03.** `test_camera_framing.py` fails five ways, in isolation and in the
full run, and identically at `HEAD` with no working-tree changes:
`test_distance_follows_the_field_of_view[True/False]`,
`test_zoom_fits_every_atom_not_just_the_trace`, and
`test_camera_distance_matches_pymol[True/False]`. The measured distance is ~30×
the expected one (41429 against 1381), which points at a scale factor — chimol
scales coordinates by `_scale_factor` (default 10) — rather than at the framing
rule. Recorded here because it was found while working on something else and is
not that change's to fix; the assertions encode PyMOL's
`d = R / tan(fov/2)` and are worth keeping.

---

## chimol: a sphere impostor occludes as a flat disc (RF-522)

**2026-07-27.** The impostor is exact in silhouette and in shading, but every
fragment is written at the depth of the bead *centre*, because the fragment
shader assigns no `gl_FragDepth`. Where beads overlap each other or other
geometry, the nearer centre takes the whole disc instead of the two surfaces
intersecting — by up to one bead radius, which on the nuclear pore is tens of
ångström. Below `balls.impostor_min_atoms` the same beads are meshes and
intersect correctly, so the two depictions do not match across the threshold.

**Why it is not simply fixed.** Writing `gl_FragDepth` in *any* branch of a
GLSL 1.20 shader disables early-Z for every draw that shader serves — and this
one serves the cartoon and every mesh in the scene, which is the path a lot of
work has gone into keeping fast. The correct fix is a **separate shader program
for impostors** (its own vertex/fragment pair, the depth write confined to it),
not a branch in the shared one. Documented as a limitation in the viewer guide
in the meantime.

---

## chimol: `show` and `hide` say nothing on an empty viewer

**2026-07-27.** `spectrum`, `zoom` and `color` now answer "nothing is loaded" on
an empty viewer instead of describing a molecule that is not there, because they
all resolve a selection first and the resolver raises. `show spheres` and `hide
everything` do not go through the resolver — they go through
`RenderingMixin._toggle_representation` — so on an empty viewer they still
silently do nothing, which is the same class of wart one step quieter.

Not fixed with the others only because `rendering.py` had concurrent edits from
another working copy at the time; it is a two-line guard in
`_toggle_representation`.

---

## chimol: a point glyph's configured size never reaches the renderer

**2026-07-27.** `QtGLRenderer._geometry_to_draw_data` computes `size` from
`geom.meta["size"]` and then does not pass it to `_DrawData`, so every point
glyph draws at the 4-pixel default: `dots.size_px`, the overlay sizes, and the
`px_mode` flag that distinguishes a pixel size from a world one are all dead
configuration. Sphere impostors are unaffected — they carry a per-vertex radius,
which does reach the shader.

Not fixed in the change that found it because the fix changes the size of every
point glyph in the application at once, and the render fixtures would all need
re-inspecting; that is its own change, with its own before/after images.

---

## mmfdb: the shipped curated seed is two schema versions behind

**2026-07-28.** `tests/test_mmcif_database_resolver.py::test_packaged_seed_is_curated_and_on_the_current_schema`
is red at mmfdb `HEAD`: the packaged `data/sample_management.db` is stamped
schema **45** while `schema.SCHEMA_VERSION` is **47**. Since PRD-19 removed the
migration waterfall a stale seed is not fully migrated forward — missing
*columns* are added, stale *table structure* is not — so an unconfigured first
run copies a seed the current code cannot fully write to. The regenerator is
`build_tools/regenerate_curated_db.py` in chisurf (`--replace`).

Not fixed here because that script had concurrent edits from another working
copy at the time; regenerating and re-committing the binary seed belongs to
whoever bumped the schema.

---

## examples: a shipped example imports a package that moved, and no test reaches it

**2026-07-29.** `examples/fdb_burst_selection_roundtrip.py` opens with
`from chisurf.core.mmfdb import FluorescenceDatabase, BurstPipeline`. That
package no longer exists — MMFDB lives in `modules/mmfdb/src/mmfdb/` — so the
example fails on its second import line. It has failed silently ever since the
move because [PRD-46](/prds/prd-46.md)'s script runner
(`test/scripts/test_scripts.py`) discovers `examples/scripts/*.py` only:
anything in the `examples/` root is outside the glob and is never run.

Two separate repairs, which is why neither landed with the flrCIF alignment fix
that found it: the example needs porting to the current `mmfdb` API and a
verifying run against the `bh_spc132_sm_dna` SPC file it references, and the
runner's discovery needs widening (or the example needs moving into
`examples/scripts/`) so the next one cannot rot unnoticed. The other five root
examples at least resolve every top-level import; whether they still *run* is
exactly what nothing checks.

---
type: Reference
title: Known issues & recurring gotchas
description: Curated open functional bugs and cross-cutting engineering pitfalls distilled from working bug logs.
resource: chisurf/
tags: [bugs, gotchas, pitfalls, gui, qt]
timestamp: '2026-07-06T00:00:00Z'
---

# Purpose

This concept distills durable content out of ad-hoc working bug logs (formerly in
a top-level `notes/` folder) so the knowledge survives without keeping a raw log
in the tree. Two things are worth preserving from those logs: **functional bugs
that were still open** when the log was last touched, and **recurring root-cause
patterns** that keep re-biting across subsystems.

This is not a live issue tracker. Architecture-divergence items (spec violations,
review-found correctness bugs, schema/manifest drift) live in the
[cleanup backlog](/specs/assessment.md); this page is for runtime/functional
behaviour. The open list below was captured around **June 2026** — re-verify each
against the current tree before acting, as some may already be fixed.

# Recurring gotchas (durable — verify before you re-break them)

These are the patterns; each caused more than one bug.

- **pyqtgraph draws a 2-D array transposed.** `ImageItem`'s default axis order
  is column-major: axis 0 becomes *x*. Everything else in ChiSurf — numpy, the
  ROI subsystem, the AutoForm `image` section's own markers, click picks and
  rectangle gate, and its 3-D path — treats `(x, y)` as `(column, row)`. The
  mismatch is invisible on square or symmetric data and puts every marker and
  every drawn region on the transposed pixel otherwise. Set
  `axisOrder="row-major"` on any new `ImageItem`/`ImageView`; the array handed
  around is unchanged either way, so masks keep their `(row, col)` meaning.
- **Several pyqtgraph views destroyed together abort the process.** `ViewBox`
  registers itself in a process-global `NamedViews` dict and, when destroyed,
  walks every other registered view to rebuild its menu — reaching one whose
  `QComboBox` is already gone. At interpreter exit this aborts *after* the last
  test passed: a green run with a non-zero exit code, and no pytest summary to
  explain it. Keep at most one long-lived view per test module (module-scoped
  fixture) and build the rest under `qtbot`, which deletes them while Qt is
  still alive.

- **Collecting a TCSPC model widget between tests is a bus error.** Same
  signature as the entry above — every test prints a dot and then
  `Fatal Python error: Bus error` — but a different subject and a different
  trigger: `Fit(model_class=GaussianModelWidget, …)`. Building *five in one
  test* is stable; building one per test across five tests aborts on roughly
  four runs in five, so it is the per-test garbage collection of the fit and its
  Qt children (with the session `QApplication` still up), not the count. Not
  root-caused. Until it is, hold every such fit in a module-level list and never
  release it — see `test/gui/models/test_distance_widget_append.py`.

- **Qt Python-wrapper vs C++ lifetime.** `RuntimeError: wrapped C/C++ object …
  has been deleted` on window close. The Python wrapper outlives the destroyed
  C++ widget; a shared `_new_closeEvent` in `chisurf/gui/misc_helpers.py` calls
  through to a dead object. Any close-event / save-window-state handler must
  guard against an already-deleted widget (`sip.isdeleted`). Recurs across
  plugins (microtime histogram, MLE lifetime wizard).
- **`@property`-backed reader settings silently drop on serialize.**
  `serialize_reader_state()` / `_reader_settings_dict()` iterate
  `reader.__dict__` and skip `_`-prefixed keys. A `@property` (e.g. `is_vv_vh`)
  is not in `__dict__`; only its private backing field is, and that is filtered
  out — so the setting fails to persist across restart with no error. Any new
  `@property` on an `ExperimentReader` needs the serializer to look for the
  public property. PRD-40 aims to make AutoForm/`.view.json` own persistence and
  remove this class of bug.
- **`DataCurve[key]` returns 5 items, not 4** (since masks were added). Every
  consumer (`calculate_weighted_residuals`, `DataCurve.save`) must unpack 5. A
  `Curve.__getitem__` regression that returned `y` where `x` was expected
  produced huge residuals / wrong χ² rather than a crash — easy to miss.
- **Refresh derived outputs explicitly.** Updating input parameters and plots
  does *not* refresh derived/output parameters. After any fit switch or parameter
  edit, call `model.finalize()` and refresh the output-parameter controllers.
- **Propagate anisotropy calibration as a unit.** `g_factor`, `l1`, `l2` must
  travel together reader → dataset/group metadata → model kwargs → parameters;
  propagating `g_factor` alone was a repeated bug. Values may be scalar floats or
  parameter objects — handle both (no `.value` on a float). Coerce NaN/inf to
  finite before constructing parameters (non-finite calibration caused Windows
  access-violation crashes on project load). Steady-state anisotropy uses
  `r = (VV - VH)/(g*VV + 2*VH)` and should prefer dual-channel VV/VH.
- **pyqtgraph text overlays + threading.** Before `setHtml`/`updateTextPos` on a
  `TextItem`, verify both it and its backing `QGraphicsTextItem` are alive
  (`sip.isdeleted`); dangling items crash on Windows. Prefer plain `setText`.
  Qt-owning objects (MCP server, GUI executor) must be created/owned/destroyed on
  the main thread.
- **macOS ARM64 text rendering.** Emojis/special symbols in UI strings can hit
  CoreText paths that SIGBUS (`EXC_ARM_DA_ALIGN`); keep UI strings ASCII-safe on
  that platform. (Note this tension with the general emoji-toolbutton preference.)
- **Keep hot-path logging at DEBUG.** Logging a full DataFrame repr / per-redraw
  traces at INFO on every recompute was itself a major interactive slowdown.
  `resizeEvent` should rescale cached data (debounced), never re-bin/recompute.
- **A GUI log handler must batch, be bounded, and never touch the widget per
  record.** `QTextEditLogger` sits on the root logger, so *any* subsystem's
  logging pays its cost. Writing to the widget from the logging thread is
  undefined behaviour (`QBasicTimer` warnings, crashes); inserting one row per
  record pays a relayout plus `scrollToBottom` each; and running the O(rows)
  console filter per record makes a burst O(rows^2) — a data load logging a few
  hundred records took seconds. Records are queued and applied in batches on the
  GUI thread (one wake-up per batch, ~50 ms rate limit, newest-only for the
  status bar), the console is capped at `LogListWidget.max_rows`, and the filter
  pass is debounced and skipped entirely while no filter is active.
- **File-save dialogs seed from the data location.** Default the save dir to the
  loaded data file's folder / `cs.working_path` (not Qt's last-used dir) and
  update `cs.working_path` after save. `chisurf/gui/main.py` "Save Fit" is the
  reference.
- **Plugin menu-callback contract.** The menu system `exec`s a plugin file with
  `__name__ == "plugin"`; without an explicit `if __name__ == "plugin": load()`
  guard the plugin silently does nothing.
- **Plugin `.ui` paths must be plugin-relative and existence-checked** (cached
  resolver) before `uic.loadUi`; stale relative paths break silently after folder
  moves. Contract tests cover this — keep them.
- **Batch/action dispatch must not swallow per-item exceptions.** A batch
  `fit.add` that swallowed callback errors reported success while creating no
  fits. Route default actions to `cs.current_fit`, not fit index 0.
- **macOS QComboBox popups render translucent.** Node/embedded combos need an
  explicit opaque palette + `setAutoFillBackground(True)` and cleared
  `WA_TranslucentBackground` on the view; QSS `QComboBox QAbstractItemView`
  alone does not fix the popup window. (Seen in the light-path node editor — see
  [Light Path Simulator](/plugins/profiles/lightpath-simulator.md).)

# Open functional issues (re-verify against current tree)

Grouped by area; captured June 2026.

**The generated manual still names the retired emcee dependency at its source
(2026-07-28).** `docs/manual/*.rst` are generated from
`docs/_old_manual/manual.docx` by `pixi run -e docs docs-manual`. The three
places that said ChiSurf "uses emcee" (and showed `method: emcee` in the settings
listing) were corrected **in the generated RST**, because the sampler is now
in-tree; the `.docx` still says it, so a regeneration reintroduces the wrong
statement. Fixing it properly means editing the binary source or retiring that
manual page in favour of `docs/concepts/parameter_uncertainty.md`, which now
covers the same ground.

**Anisotropy now follows Schaffer/Eggeling throughout (settled 2026-07-27).**
`r = (Fp - G Fs) / ((1 - 3 l2) Fp + (2 - 3 l1) G Fs)` with **G = S_par/S_perp**,
the ratio a paper quotes and the one tttrlib's estimators already took. Four
sites moved together — `compute_g_factor_perrin` (was returning the reciprocal),
`anisotropy_from_integrals`, `LifetimeModel._tcspc_rt_curves`, and the
`vm_rt_to_vv_vh` generator (now divides the perpendicular channel by G). The
chain closes: the generator round-trips exactly at every G, the calibration's
output feeds its own consumer, tttrlib's formula and the VM combination
`vv + 2 G vh` and all three return the truth. That also retires the two splits
recorded here earlier — the cross-repo one and the VM one — without touching
tttrlib or the five VM call sites.

**The l1/l2 parameterisation is settled too (2026-07-27).** It was the
generator that was out of step, not the correction. `vm_rt_to_vv_vh` built an
ideal pair and mixed it with a 2x2 matrix (Koshioka 1995), which is a different
meaning for l1/l2 and does not invert the Schaffer correction. tttrlib states
the right one in its own forward model (`DecayFit23.cpp`:
`x_vv[2] = r0 (2 - 3 l1)`, `x_vh[0] = 1/g`, `x_vh[2] = r0 (-1 + 3 l2)/g`):

    VV = vm (1 + (2 - 3 l1) r),    VH = vm (1 - (1 - 3 l2) r) / G

Substituting that into `(sp - G ss) / ((1 - 3 l2) sp + (2 - 3 l1) G ss)` makes
numerator and denominator collapse to `3 vm (1 - l1 - l2) r` and
`3 vm (1 - l1 - l2)`, so the round trip is exact for any l1, l2 and G. The
generator now uses it, and the round-trip test covers a non-unit G and non-zero
mixing together — the combination that exposed the old one (0.274 and 0.318
against 0.300).



**Found 2026-07-27, not fixed: the PCH settings panel is clipped at its right
edge.** `chisurf/plugins/pch/gui/tool.py` puts the settings form in a
`QScrollArea` with `setHorizontalScrollBarPolicy(ScrollBarAlwaysOff)`, and the
form is wider than the splitter gives it, so the File / Channels / Bin Time /
Micro Time editors run past the window edge and their right-hand ends are
unreachable — visible in any screenshot of the tool at its default 1000×650. The
fix is a layout one (let the form shrink, or give the splitter a sensible initial
size, or stop suppressing the scroll bar), not a one-liner, so it was left out of
the message-groups change that surfaced it.

**Reported 2026-07-27. Plugin names and menu categories are never translated,
in any locale.** Everything a plugin's `manifest.json` shows *except* its name
is translated: `chisurf/core/plugin/manifest.py` runs `description`, `summary`,
`experimental_message` and `deprecation_message` (plugin-level and per RPC
method) through `tr()` at load time, and the extractor collects them. The two
fields the user actually reads in the menu — `display_name` and `categories` —
are excluded on purpose at *both* ends: `extract_strings.py` leaves them out of
`TEXT_KEYS` and `manifest.py` keeps them canonical, each with a comment saying
they double as menu-path / identity keys and are "localized at the nav seam".

**That nav seam does not exist.** The plugin-menu builder in
`chisurf/gui/__init__.py` (`parse_hierarchical_plugin_name`) splits
`display_name` on `:` into hierarchy parts plus a leaf and uses both verbatim —
there is no `tr()` call anywhere in that path — and the ribbon does the same via
`ribbon_categories.py::_parse_hierarchical_plugin_name`. So a manifest naming
`Spectroscopy:Single-Molecule:PCH` renders as those exact English words under
`de` and `fr`. Verified: "Burst Analysis", "Microtime Shifter" and
"Spectroscopy" have zero entries in `chisurf_en.ts` *and* `chisurf_de.ts` — the
strings are not merely untranslated, they were never offered to a translator.

This compounds with the ribbon entry below: the ribbon's plugin categories are
built from these same paths, so wrapping the ribbon's own literals in `i18n.tr`
would still leave every plugin-derived entry English until this seam is built.

The reason it cannot be fixed by wrapping the field is worth stating, because it
is the whole design problem: `display_name` **is** the identity key. It is the
menu path, it keys `plugin_order` in the ribbon, and it feeds
`get_plugin_settings_path(plugin_name)`. Translating it in place would move a
plugin's settings directory and lose its ordering when the user switches
language. A fix has to separate identity from display — keep the canonical path
as the key, translate each path segment and the leaf only at render time, and
teach the extractor to emit those segments (they are a small closed vocabulary:
Spectroscopy, Single-Molecule, FRET, Tools, Structure, Simulation, …). The same
anchoring rule as everywhere else then applies: any code re-deriving a key from
display text must repeat the identical `i18n.tr(...)` call.

**Reported 2026-07-27. The ribbon is not translated, and the mechanism that
looks like it covers it does not.** Switch the language and the whole top
navigation stays English. `chisurf/gui/widgets/ribbon/` contains **no**
`i18n.tr` call and no `.ui` file, so none of its text is translatable, and none
of it is even *extracted*: `build_tools/i18n/extract_strings.py` collects from
`.view.json`, `manifest.json`, `.ui` files and AST `i18n.tr(...)` calls, and the
ribbon matches none of those. Verified — "Other Tools", "Utilities" and
"Clipboard" have zero entries in `chisurf_en.ts`. ("Fitting" and "Analysis" do
appear, but from `fittingWidget.ui`; the ribbon's own literals are never looked
up, so those entries are a coincidence, not coverage.)

Two groups of strings are affected:

- **Category and panel titles**, hard-coded in `ribbon_categories.py`: Main,
  Edit, Analysis, Tools, Setup, View, Help, Documentation, Basic, Clipboard,
  Fitting, Utilities, Other Tools.
- **The ribbon's own chrome**, hard-coded across `titlewidget.py`,
  `ribbonbar.py`, `panel.py`, `toolbutton.py`, `ribbon_auto_fold.py`: "Collapse
  Ribbon" / "Expand Ribbon", "Panel options", "Remove from Quick Access
  Toolbar", "Show All Hidden Items", "Pin ribbon" / "Unpin ribbon", "Open Help
  Plugin", and the "ChiSurf" title and its tooltip.

Why it went unnoticed: `main.py::_retranslate_interface` tears the ribbon down
and rebuilds it on every language change, and its docstring says that rebuild
"re-reads every string through the freshly installed translator". That holds for
ribbon buttons derived from **QActions** — those come from `gui.ui` and are
retranslated in the step before — but a hard-coded literal re-read is the same
English literal. The rebuild is therefore not the fix, and the docstring
overstates what it achieves.

Fixing it is the ordinary in-place path already used for rich non-form tools
(wrap each static string in `i18n.tr`, see `tttr_time_windows` /
`tttr_microtime_shifter`), after which the extractor picks them up. Note the
ribbon is a **vendored** widget family: `ribbonbar.py`, `panel.py`,
`toolbutton.py`, `titlewidget.py` etc. carry upstream chrome strings, so decide
per file whether to localize in place or to keep the vendored copy pristine and
translate only ChiSurf's own layer (`ribbon_categories.py`,
`ribbon_auto_fold.py`, `ribbon_file.py`). Also mind the anchoring gotcha in
[/subsystems/i18n.md](/subsystems/i18n.md): the ribbon styles buttons by object
names derived from action text, so any `i18n.tr` added there must be mirrored
wherever a key is re-derived from display text.

**Found 2026-07-26 while unifying the progress bars. `PDBFolderLoad` cannot be
constructed at all.** `chisurf/gui/widgets/pdb/pdb.py` has rotted against a
refactored `TrajectoryFile`, in two places: `__init__` calls `TrajectoryFile()`
and `onLoadStructure` calls `TrajectoryFile(use_objects=…, calc_internal=…,
verbose=…)`, but the current constructor requires a positional `p_object` and
takes none of those keywords. The widget is reachable — the modelling
experiment page builds one (`gui/widgets/experiments/modelling/modelling.py`) —
so that page is broken too.

Half of it is fixed: `LoadThread`'s `procDone`/`partDone` signals had been
commented out during the PyQt-to-qtpy move (their `pyqtSignal` spelling did not
survive), so construction raised `AttributeError` one line earlier still; they
are restored as `QtCore.Signal`. The remaining `TrajectoryFile` calls need a
real port, and what `use_objects` / `calc_internal` were meant to select is no
longer expressed anywhere in that class — so the intent has to be recovered
before the call sites can be rewritten, which is why this is logged rather than
guessed at.

**Found and fixed 2026-07-26 — and the first diagnosis was wrong.**
`test_consistency_check_rejects_the_wrong_kinetic_scheme` was accepting a
deliberately wrong scheme at p = 0.297. It was filed here as "not the rename,
bisect the concurrent fitting-layer edits". That attribution was wrong: the
cause was the earlier change that made `k_ex` an **absolute rate in Hz**
(time-binned PDA) while this test still set it as the dimensionless
`K = (k1 + k2) T`. At 2 Hz over a 2 ms window that is K = 0.004 — the
"dynamic" data the test generated was *static*, so the static scheme it exists
to reject fitted it perfectly. The sibling test in
`test_pda2c_model_editor.py` had already been converted; this one was missed.

Fixed by converting through the dataset's observation time, as the sibling
does. With real dynamics the model recovers K = 2.04 against a truth of 2.0 and
the static scheme is crushed (chi2r 176 against 1.38), so the rejection is now
emphatic.

Worth keeping from the episode: **a unit change in a shared parameter needs a
sweep of every test that sets it**, because a test that silently generates the
wrong physics still passes — it just stops testing anything. And the acceptance
branch of that pair is now pinned to a typical realisation: at K = 2 the default
seed gives chi2r = 1.55 at the *true* parameters where seeds 2-8 give 0.80-1.18,
and the bootstrap correctly rejects that draw. Asserting on it would test the
noise, not the model.

**Found 2026-07-26 while making the PDA3c rate matrix fittable.** A rate fitted
by the three-colour dynamic model comes out **systematically fast, by some tens
of percent**, and more computation does not help. Measured on bursts simulated
from a known two-state scheme by an independent forward route (a fresh distance
triple per state per burst, mixed by sampled occupation times, then split
multinomially): the profile likelihood along `k_tot` peaks at 650–700 Hz for a
truth of 500 Hz, and the argmax moves by at most one grid step from 600 to 8000
sampled trajectories and from an occupancy resolution of 24 to 192. So it is
**not** Monte-Carlo noise in the occupation-time sampling — that part is exact
in distribution.

The cause is the approximation made *outside* the sampling, in
`Pda3cModel._mean_channel_probabilities`: each state is collapsed to its
distance-averaged per-photon probability vector *before* the occupation-time
mixing, so the intra-state distance spread contributes to the predicted
burst-to-burst width differently than it does to real bursts. Fixing it properly
means carrying the distance quadrature through the dynamic average (nodes x
occupancy nodes x bursts), which is a real cost increase and a design decision
about where to truncate — hence recorded rather than fixed in the change that
found it. Until then, `pda3c.py`, the concept page and the guide all say to read
a fitted rate as an exchange **timescale**, not a rate measurement; comparisons
between conditions are sound.

Note this was invisible before, because the rate matrix was a plain array
attribute nobody could fit — the bias only became reachable when the rates
became parameters.

**Narrowed down 2026-07-26, with the exact statement of the defect.** The same
approximation has a consequence with a *checkable* answer: **the multistate
route does not nest the static model.** At 1e-3 Hz over a 2 ms window nothing
switches, so every molecule sits in one state for the whole burst and the
likelihood must equal the static mixture's term for term. It is off by **2357
log-likelihood units** — because a pure trajectory is evaluated at its
distance-*averaged* probability vector where the static model integrates the
likelihood over the distance distribution, and those differ by Jensen. A
static-versus-dynamic comparison (an F-test, a model choice) is therefore
meaningless in exactly the regime where the two models are nested.
`test/models/test_pda3c_rates.py::test_the_multistate_route_nests_the_static_model`
records this as a **strict xfail**, so it will fail loudly when fixed.

**Two approaches tried and rejected, so nobody repeats them:**

1. *Exact atoms alone.* Giving pure trajectories the full static treatment, with
   the analytic weight `pi_i exp(-lambda_i T)` rather than their sampled
   frequency, makes the static limit exact to five decimals and removes a
   1901-unit spike at slow exchange (caused by occupancy quantisation merging a
   switching trajectory into a near-pure cell). But it leaves the *interior*
   annealed, and the halves are then inconsistent: the fit compensates by
   slowing exchange, the recovered rate moves from 199 to **65** against a truth
   of 200, and the profile bias flips from +30% to −30% (stably, 300–350 Hz at
   every sampling setting). Fixing one half alone is not an improvement.
2. *Sampling the joint average.* Drawing one quenched distance triple per state
   per occupancy node is the right average in principle, but the node labels
   *are* the occupancies, which shift continuously with the rates — so
   neighbouring evaluations see unrelated conformations however the draws are
   keyed (a per-node hash of the quantised occupancy included). The optimiser
   reads the noise as structure and walks off: 200 → 52.

**The fix is to carry the distance quadrature through the occupancy average** —
both halves together, deterministically — and the open question is where to
truncate it, since the product over states is combinatorial in the quadrature
nodes.

**Found 2026-07-26 while adding typeset labels.** `pytest test/fitting` used to
**abort the interpreter** part-way through (~47 %), so everything after it never
ran. `chisurf/macros/core_data.py::add_dataset` popped a `MyMessageBox` on its
two "nothing was read" paths; a modal dialog needs a GUI to close it, and with no
`QApplication` at all Qt aborts the process outright. The exception path a few
lines below already guarded on `gui is None` with exactly that reasoning — the
two earlier sites had been missed. Fixed by applying the same guard (head-lessly
the log is the report), which is what makes the suite run to completion.

That uncovered **14 pre-existing failures and 1 collection error** that the abort
had been hiding. All confirmed identical on an unmodified tree with only the
guard applied, so none belongs to the change that found them; recorded rather
than fixed because they span five unrelated subsystems:

- `test_fit_state.py` (5) — model `get_state`/`set_state` round-trips, including
  the FRET-Gaussian and PDA length-preservation contracts.
- ~~`test_grouping.py` (3) + `test_grouped_default_linking_contract.py` (1)~~ —
  fixed 2026-07-26; they read *source text* from paths that no longer exist and
  are now behavioural.
- ~~`test_experiment.py::test_FCS_Reader`~~ — fixed 2026-07-26. Remaining:
  `test_models_regression.py::test_parse_model_evaluation`,
  `test_parameter.py::test_equality`,
  `test_fit.py::test_fit_save_full_length_curves_have_nan_padding`,
  `test_reference_models.py::test_lifetime_model_convergence`.
- `test_derived_quantities.py::test_a_well_determined_ratio_is_where_the_delta_method_is_right`
  (noted 2026-07-28) — the skew diagnostic fires on a ratio it is meant to pass
  (`0.771 +0.0207 -0.0236`), so the asymmetry threshold is tripped by ordinary
  Monte-Carlo noise rather than by real skew. It samples with `method='de'`,
  which the ensemble-sampler change did not touch; recorded rather than fixed
  because the fix is a re-derivation of the threshold in `derived.py`.
- `test_sampling_diagnostics_report.py::test_posterior_summary_prefers_a_converged_chain`
  (noted 2026-07-28) — **flaky, roughly one failure in four** on an unchanged
  tree. It asserts that every posterior entry reports `method == 'mcmc'` after
  sampling; on a failing run they report `'laplace'`, i.e. the MCMC result was
  not adopted and the Laplace approximation stood. Measured by running the test
  alone five times: 2 failed, 3 passed, no edits in between.

  Worth knowing *how* this was established, because a single controlled run said
  the opposite. It first appeared while checking whether the atom-dtype change
  had caused it: reverted, the test passed; restored, it failed — a clean-looking
  A/B that was pure coincidence. Only repetition showed it flips on its own.
  A one-shot before/after cannot tell causation from flakiness, and a flaky test
  will happily frame whatever change is in flight.
- ~~`test_group_polarization_any_size.py` errors at collection.~~ — fixed
  2026-07-26.

**`test/gui` cannot currently run to completion (noted 2026-07-28).** It
**segfaults** (exit 139) about 19% in, at `test_channel_definition_lut_box.py`
— a file whose 8 tests all pass when it is run *alone*, so the crash is
cross-test state and not that file's doing. 17 failures precede it. Everything
after the crash is simply unrun, which is the worse part: the suite reports
nothing about roughly four fifths of itself.

Established as independent of the atom-dtype change by running the whole area
with the old `|U1` field and the new `|U4` one: **byte-identical** progress,
the same 17 failures, the same crash at the same point. The TTTR
channel-definition wizard and LUT tools had several files under concurrent edit
at the time, which is the first place to look.

**Update 2026-07-29 — there is also a hang, before the segfault.**
`test/gui/test_gui_plots.py::test_plot_updates_when_parameter_changes` did not
finish in **10 minutes** when run entirely on its own; it errors in the
`chisurf_app` fixture (`chisurf.gui.get_app()`, which boots the whole main
window) and then stalls. Seen while checking that a chiplot fix had not broken
plot consumers. A second instance's `pytest test/gui -q` was 87 minutes in at
the same moment, so a shared-resource conflict (server ports, the settings
directory) cannot be excluded and *neither run is a clean measurement of the
other* — but the solo run had the whole boot to itself and still did not
progress, which the concurrency explanation does not cover. Whoever picks this
up should time the fixture alone on an idle machine first.

**Found 2026-07-26 while closing [RF-182](/reviews/findings.md#rf-182).**
`test/core/test_curve.py::Tests::test_reading` passes when `test/core` runs on
its own and fails when `test/fitting` has run first in the same process: the
yaml round-trip comes back with a different `unique_identifier`. It is an
ordering artifact over process-wide registry state, not a defect in the curve
I/O, and it is identical with and without the `DataCurve` change that surfaced
it. Not fixed here because the poisoning module is somewhere in `test/fitting`
as a whole (no single file reproduces it) and chasing it is a separate job.
Two order-dependent failures in the *same* run **were** fixed:
`test_fit.py::test_fit_parse` and `::test_fit_data_setter` used
`chisurf.core.models.parse` / `chisurf.core.fitting.fit` while importing only
the package roots, so they passed only when another test module had imported
those submodules first; the test module now imports them itself.

**Found 2026-07-26 while closing [RF-168](/reviews/findings.md#rf-168) in the
BVA layer.** `test/plugins/burst/test_background_gui.py` has two failures that
are stale against the AutoForm conversion of the Burst Background tool
(`61a2803ae`, then `993577745`), unrelated to the BVA change that surfaced them.

- **`test_diagnostics_plots_build_and_render`** asserts
  `hasattr(w, "iht_plot")` on `BurstBackgroundEstimator`; the AutoForm rebuild
  no longer exposes named plot attributes on the tool, so the assertion fails at
  the first line and the render path is never exercised.
- **`test_semantic_detector_colors`** does
  `from chisurf.plugins.burst.burst_background import _det_color`, which no
  longer exists — the detector-colour mapping moved with the conversion.

  Both need re-pointing at the AutoForm section handles rather than a code fix;
  left open here because doing that properly means driving the tool headlessly
  and inspecting the render (the screenshot rule), which does not belong in an
  unrelated docstring/dedup change. The colour test in particular should assert
  through a public seam, not a private helper name.

**Found 2026-07-26 while routing the fit jobs through the job manager
([INC-08](/specs/assessment.md#inc-08)).** Two failures in the server suite,
both confirmed identical on the unmodified tree, both about the RPC *transport*
rather than the services under change — left open because fixing them means
re-deciding the client's error contract, which is [SV-04](/specs/assessment.md#sv-04)
territory and does not belong in an unrelated change.

- **Eight `test/server/test_rpc_edge_cases.py` tests are stale against the
  SV-04 error contract.** `ChisurfClient.call()` now raises `RemoteError` for
  application-level errors (that *was* the SV-04 fix), but these tests still
  expect an error **dict** back — e.g. `test_very_long_method_name` calls an
  unknown method and asserts on the returned payload, and gets
  `RemoteError: method '…' not found`. The tests need updating to
  `pytest.raises(RemoteError)`, not the code.
- **`pytest test/server` never terminates; the wedge is in
  `test_integration_lifecycle.py`.** Localised on 2026-07-26 by an A/B against a
  clean `HEAD` worktree: `pytest test/server --ignore=test/server/test_integration_lifecycle.py`
  finishes in **86 s** with **21 failed, 501 passed**, while the same run *with*
  that file idles indefinitely (0 % CPU) inside `TestParameterLifecycle` —
  stack in `zmq_ctx_destroy` → `zmq::mailbox_t::recv` → `poll`, i.e. a context
  termination waiting on a socket an earlier test left open. Run in isolation
  (`-k TestParameterLifecycle`) the class completes, so it is leaked state from
  earlier tests in the file, not the class itself. Until a socket is closed (or
  `LINGER` set) somewhere upstream, exclude that one file to run the suite.
  The 21 remaining failures are pre-existing at `HEAD` — the eight stale
  `test_rpc_edge_cases.py` expectations above plus fit-endpoint tests
  (`test_fit_save_endpoint`, `test_fit_list_includes_chi2r`,
  `test_model_finalize_endpoint`, …).

**Found 2026-07-25 while migrating the imaging tools onto the ROI subsystem.**
Three red tests, each pointing at real behaviour rather than a stale test alone.
Left open because each needs a decision from the owner of code being actively
worked in this tree; the fourth found alongside them (a `np.float` in
`test_fluorescence`, removed in NumPy 1.24) and three stale imports of the
retired `_dev/fluorophore_db` plugin were fixed on the spot. Two of the three —
the `calculcate_spectrum` term count and the binary `.pqres` read — were
resolved on 2026-07-25 and 2026-07-26 and are recorded below.

- **`test_structure.py::test_labeled_structure` fails on the labelled-structure
  path.** Molecular modelling has moved out of chisurf into the external
  framework, so this may be a test that outlived its subject rather than a
  live defect; confirm before either fixing or removing it.

**Found 2026-07-25 while closing [BUG-09](/specs/assessment.md#bug-09).** Both sit
in the anisotropy area; neither is reachable from a production call path today.

- ~~**`vm_rt_to_vv_vh` puts the g-factor in the one place that is not
  invertible.**~~ Fixed 2026-07-26 in its own change, as
  [RF-231](/reviews/findings.md#rf-231). It computed `vh = vm · (1 − g·r)`, while
  its sibling `calculcate_spectrum` — the one the fitting models actually call —
  computes `g · vm · (1 − r)`; only the latter satisfies
  `r = (I_VV − I_VH/g) / (I_VV + 2 I_VH/g)`, because a detection sensitivity scales
  the whole perpendicular channel, not just its depolarization term. The helper now
  uses that placement, the two doc pages that repeated the wrong formula were
  corrected with it, and `test_vm_rt_to_vv_vh_recovers_anisotropy` pins the round
  trip *and* term-for-term agreement with the spectrum path at `g ∈ {0.8, 1, 1.5}`.

**Fixed 2026-07-25/26 — kept here because the *patterns* keep recurring**

- **Five test files about one behaviour, and none of them could fail.**
  `test_group_polarization_any_size.py`, `test_polarization_fix.py`,
  `test_unified_polarization.py`, `test_group_reference.py` and
  `test_polarization_group_update.py` were written during a single bug hunt and
  between them contained *zero* assertions about polarization: each
  `logger.error(...)`d on a wrong value instead of asserting; one took a
  `num_datasets` argument with no fixture and no `parametrize`, so pytest errored
  at collection and the sizes were only passed from a `__main__` block; one ended
  `return True`. Consolidated into one parametrized file that asserts the
  contract stated in `Anisotropy.set_polarization_by_group_position`. The open
  question this was filed under — does a 3-fit group really alternate
  vv/vh/vv? — was not an owner call after all: the code answers it in so many
  words, and it does. The rewrite also found the expectation that had been
  logged-and-ignored for years: two fits *added separately* are two groups of
  one, so both are `vm`, not the `vv`/`vh` the old test wanted. **Pattern: a
  test that logs instead of asserting is worse than no test — it occupies the
  slot where a real one would go.**
- **Four "contract" tests grepped source text out of files they could not
  open.** `test_grouping.py` and `test_grouped_default_linking_contract.py`
  asserted that `"def _is_global_fit_dataset(" in Path("cs/macros/core_data.py")
  .read_text()`. The package was renamed `cs/` → `chisurf/` and one path was
  relative to the working directory, so all four raised `FileNotFoundError` —
  a test that asserts a substring appears in a file it cannot open tells you
  nothing twice over. Replaced with tests of what the functions do: which
  parameters count as nuisance, that grouping links the physics and leaves the
  instrument parameters local, that the global-fit dataset survives
  `remove_datasets`. **Pattern: asserting on source text pins the spelling, not
  the behaviour, and rots at the first rename.**
- **Every unnamed data group called itself `ExperimentDataCurveGroup`.**
  `DataGroup.name` documented a fallback to the current dataset's name, in a
  `except KeyError` branch that could never run: `Base.__init__` stamps
  `self.__class__.__name__` into `__dict__['name']` whenever no name is passed,
  so the key was always present. After loading an FCS file the dataset list
  showed the class name instead of the file. A stamped class name is now treated
  as absent. **Pattern: a fallback guarded by a condition its own constructor
  makes impossible is dead code that reads as a feature.**

- **A binary `.pqres` file was read with `np.loadtxt`, and three layers had to
  break for that to happen.** `FCS.read()` accepted a `reader_name` argument,
  documented it, and then dropped it on the floor — every call used the reader's
  configured default (`kristine`), so asking for `'pqres'` sent a binary file to
  a text parser and it died on byte 0xff. Behind that, `read_pqres_fcs` returned
  a `DataCurveGroup` where the dispatcher expects `list[dict]`, so the format had
  never worked through `read_fcs` at all. Behind *that*, every `<base>X`/`<base>Y`
  tag pair was promoted to a curve — the standard deviations, the weights and a
  25 025-point TCSPC decay included — yielding 10 curves where the file holds 3.
  **Pattern: a keyword argument that is accepted and ignored is worse than one
  that raises; and a test that `print`s and `return`s reports green over all of
  it.** (`test/fluorescence/test_pqres.py` now asserts the three named
  correlations, their 54 lag times and finite non-zero weights.)
- **The anisotropy spectrum test pinned a VH model that cannot be inverted.**
  The test asserted `−2·r` in the perpendicular channel where the code produces
  `−1·r`, and the "16 terms vs 8" term-count mismatch it was filed under was the
  union/concatenate mixing form, not a defect. The definition of `r` settles it:
  only `g · f_VM · (1 − r)` round-trips back to the `r(t)` that generated the
  pair. The test now compares the *decays* the spectra stand for against the
  analytic definitions, so it is immune to the term count. **Pattern: a test
  whose expectation was recorded from the implementation pins the bug as
  hard as it pins the behaviour — derive references from the definitions.**
- **A test loaded its subject from a hand-built file path and rotted silently.**
  `test/fitting/test_anisotropy_integrals.py` built
  `parents[1] / "chisurf" / "fluorescence" / ...` and `exec_module`d it; when the
  module moved under `chisurf.core` the path pointed at `test/chisurf/...` and the
  file errored at collection instead of failing loudly at a rename. Replaced with
  a normal import (the module pulls in nothing but numpy). **Pattern: importing by
  path defeats every tool that would have caught the move.**
- **A GUI modal reported an error from the macro layer, so head-less loading
  hung forever.** `core_data.add_dataset` caught every read failure and built
  `MyMessageBox`, whose `__init__` calls `exec_()`. With a `QApplication` but
  no user — CLI, script, test, the assistant — that blocks indefinitely; with
  no `QApplication` at all Qt *aborts the process*. A file that could not be
  read therefore looked like "loading is very slow". Errors are now re-raised
  when there is no GUI. **Pattern: never report from core/macro code with a
  modal; the caller cannot always click.**
- **`np.float` and `np.float_` were still used in 7 modules**, and NumPy
  removed them (1.24 and 2.0). Three FCS readers — ConfoCor3, ALV `.ASC` and
  PyCorrFit — raised `AttributeError` on the first data line they parsed, so
  those formats simply did not load. Fixed to `float`/`np.float64`, with a
  guardrail test that scans for the removed aliases. **Pattern: a removed
  alias only fails when its code path runs, so it hides in readers for
  formats nobody exercised recently.**
- **`GeneralFCSModel` exposed all three diffusion presets to the optimiser**
  while computing with one, so a fit reported its untouched defaults
  (`N = 1.0`, `D = 300.0`) as results and `n_free` was 15 instead of 5.
  **Pattern: when a model holds alternative parameter groups, the parameter
  list has to follow the active one.**

**Test collection**
- **RESOLVED — `test/core/test_rename.py`** no longer breaks collection of the
  whole `test/core` package. It used to be an ad-hoc tttrlib file-locking script
  that ran at import time against a hardcoded `e:\dev\chisurf\…\Leica_SP8.ptu`;
  it is now a real test over the repository's own `test/data/clsm/`, guarding
  that reading a photon file leaves no handle that blocks renaming or deleting it.
- **RESOLVED — the `chisurf.gui.widgets.yaml_utils` test modules are gone**
  (2026-07-26). Four modules imported `dump_yaml`/`prepare_for_yaml` from a
  module that **has never existed** — `git log -S` finds no commit adding or
  removing it — so they failed at collection with `ModuleNotFoundError` and took
  `test/settings`, `test/plugins` and `test/gui` down with them. They were
  print-driven prototyping scripts that never ran against real code (the same
  never-existed-API class as `test/models/test_user_models.py` below), so they
  were deleted and replaced by `test/settings/test_settings_yaml_lists.py`,
  which asks the same question — do list-valued settings survive as lists? — of
  the serializer that does exist (`chisurf/core/settings/settings_utils.py`).
- **RESOLVED — `test/plugins` collects again** (2026-07-26). Three further
  modules tested `chisurf.plugins._dev.chato`, a scratch tree that is
  **gitignored** (`.gitignore:78`) and absent from the repo, and one tested
  `chisurf.plugins.chat`, deleted in `c28d07b65`; all four were untestable by
  construction and were removed. `test_plugin_manager_mistral_icon.py` imported
  a real class (`AIIconRateLimitError`) that the package simply did not
  re-export — it now does. Two `test_manifest.py` files in `__init__.py`-less
  directories also collided on the module name (`import file mismatch`); the
  three `test/plugins/*/` subpackages got their `__init__.py`.
  **Pattern: a test module whose import fails takes its whole package's
  collection with it, so one dead import hides hundreds of live tests.**
- **OPEN — `test_plugin_manager_mistral_icon.py`: 6 tests red since the HTTP
  client swap** (found 2026-07-28 while test-gating an unrelated plugin-manifest
  fix). `085bd79b4` ("an HTTP client of our own") moved
  `PluginManagerWidget._post_mistral_json_with_retries` and its siblings off an
  injected session object onto the module-level `chisurf.core.http.post`, and
  dropped the `session` parameter — but the tests still pass a
  `SimpleNamespace(post=...)` as the second positional argument, so it binds to
  `path`, the real path binds to `headers`, and every call raises
  `TypeError: … got multiple values for argument 'headers'`. The signature is
  identical in HEAD and in the working tree, so this is not an in-flight edit:
  it is red on a clean checkout. The fix is test-side — monkeypatch
  `chisurf.core.http.post` instead of injecting a session — and it is small, but
  `chisurf/plugins/core/plugin_manager/gui/tool.py` has concurrent uncommitted
  edits in exactly this HTTP path from another instance, so rewriting the tests
  against a signature that may still be moving was left to whoever lands that
  migration. Nothing outside these 6 tests is affected; the rest of
  `test/plugins` (321 tests) is green.

**Qt teardown in test suites**
- `chisurf/plugins/fcs/fcs_filter_calculator/test/test_widgets.py` aborts with
  `libc++abi: Pure virtual function called!` when the file is run as one
  process. Every test passes individually, and the abort is independent of the
  test that happens to be running when it fires, so it is cross-test teardown
  (a C++ object outliving its Python wrapper, the usual pyqtgraph/`DockArea`
  shape) rather than a defect in any one test. Confirmed pre-existing in July
  2026 by reproducing it with the then-current working changes stashed.
  Workaround: run the file with `--forked`, or per-test, until fixed.

**Project save / restore**
- Project round-trip: decay/lifetime models do not save & reload (critical).
- Save→close→open resolves the active window via `chisurf.cs` after teardown
  removed it → `AttributeError: module 'chisurf' has no attribute 'cs'`.
- Dataset removal no longer confirms and closes dependent fits.
- TCSPC "stacked" (`is_vv_vh`) not persisted across restart (see the
  `@property` gotcha above).
- Undo/redo does not destroy stashed dataset/fit UI windows
  (`history_replay.apply_entity_lifecycle`) — stale windows linger.

**Fit creation / fitting**
- Access violation (`0xC0000005`) on fit creation after dataset load, in
  TCSPC/anisotropy chinet init — keep parameter init scalar/type-safe into the
  native layer (no catchable Python exception at the crash boundary).
- FCS MaxEnt fit does not autorange on creation → zero points in range →
  non-computable out of the box.
- Parameter-widget edits do not fully propagate to model/chinet.

**Plugins / tools**
- NDXplorer stays blocked after data load; clear-then-reload shows no data — a
  proper `reinit()` (reset caches, plot objects, combos) is needed rather than a
  partial `clear_plots`.
- TraceBrowser does not populate its file list on folder open (severe).
- Correlator/FCS channel-preset saving does not work.
- TTTR Image Browser exports to the wrong folder; anisotropy "Save CSV" ignores
  the loaded-data location (see file-save gotcha).
- BH / SPC-130 micro-time resolution is wrong and not corrected on load (data
  correctness).
- mmfdb-admin: cancelling the password prompt still opens the UI.

**Tests**

Found while verifying an unrelated change (2026-07-25) and **all resolved on
2026-07-25**; `pytest test/core` and `pytest test/models` both run clean (498
passed / 3 skipped, and 246 passed). Kept as a record of what each turned out to
be, because three of them were defects in the code rather than in the tests.

- `test/core/test_mmfdb_schema_migration.py` **did not finish** — this is what
  made a full `pytest test/core` run look like a hang. `sqlite3`'s `conn.backup()`
  retries a busy source forever, and the migration held an open write transaction
  while snapshotting. Fixed in the MMFDB repository (commit `38973c5`) by
  committing before the backup, with a regression test.
- `test/core/test_rename.py` failed at **collection** on a hard-coded Windows path
  (`e:\dev\chisurf\test\data\clsm\Leica_SP8.ptu`), taking the whole directory down
  with it. Rewritten against the repo's own test data.
- Of the four API-drift files, three were **code** defects, not stale tests:
  `Curve.__init__` did not coerce `None` axes and `to_dict` had lost
  `skip_qt_widgets`; `DataGroup.name` had lost its setter; and
  `Project.load` called the classmethod `Session.load` as if it mutated the live
  session, so opening a project restored no chinet nodes at all (`Session.clear()`
  was missing too). Only `test_base.py` was a stale test — one incidental
  assertion contradicted the dedicated UUID spec, and the spec wins.
- `test/models/test_fret_line.py` asserted frozen coefficient strings and lifetime
  arrays computed on `np.logspace(np.log(1), np.log(500))` — base-10 exponents, so
  that "1–500 Å" axis really ran to ~1.6 million Å. Worse, the axis is a module
  global that nothing restored, so those tests silently changed the distance grid
  for every test that ran afterwards. Rewritten to assert the relations that
  define a FRET line, with setUp/tearDown restoring the global. The `KeyError`s
  were real: fixed model constants (`R0`, `t0`, `s(G,n)`) live in
  `parameters_all_dict`, not `parameter_dict`, which holds only free parameters.
- `test/models/test_user_models.py` tested a registry —
  `register_user_model`, `load_user_models`, `iter_user_models_for_experiment`,
  `_user_model_registry` — that **has never existed**: `git log -S` across the
  whole history finds no commit adding or removing any of them, and the
  documentation page describing the same registry was rewritten against the real
  mechanism in `43e60f7f3`. So this was not API drift and needed no owner
  decision. Rewritten against what the code does offer: the
  `<dotted.module>__override__<timestamp>.py` exec-into-the-module injection.

**Environment**
- Built-in Jupyter/notebook integration is disabled/broken; the notebook menu is
  missing from the ribbon.
- `modules/ndxplorer/ndxplorer/utils/performance_optimizations.py` still calls
  `np.bool8`, removed in NumPy 2. In-process it is covered by
  `chisurf/core/compat.py` (chisurf is imported first, which restores the alias),
  but ndX run standalone would raise. The root fix belongs in the ndxplorer
  repository — left alone here only because that working tree currently holds
  another instance's uncommitted work.

# Deferred enhancements

- **A chimol dock's widgets were reported deleted, and the cause is not pinned
  down.** The report: closing/moving a dock left
  `_update_sequence_view` raising `RuntimeError: wrapped C/C++ object of type
  QListWidget has been deleted`, out of the *selection-changed* handler, so
  clicking an object killed the window.

  Two things landed. A guard in `_update_sequence_view` checks the widgets are
  alive and logs instead of raising, which stops the crash whatever deleted them.
  And a genuine latent defect in `dock_area.cleanup_empty_tab_widget` was fixed:
  it assumed a splitter holds exactly **two** children, moved the first sibling
  out and deleted the splitter — taking any third child with it, because Qt
  deletes an orphaned widget's children. chimol's default layout has a
  three-child vertical splitter (viewport / sequence / timeline), so the shape was
  present.

  **But that defect was not shown to be the reported cause.** Driving
  `removeTab` on the three-child splitter leaves every widget alive with the old
  code as well as the new, because `removeTab` detaches the page widget before
  cleanup runs. The remaining suspects are the drag paths (`_finish_drag`,
  floating windows) and `restore_tab`/`restore_all_tabs`, none of which has been
  driven. Next step: reproduce by *dragging* a dock out and closing the float,
  with a liveness probe on every page widget, rather than by calling `removeTab`.


- **The chimol accessibility doc figure is not reproducible byte-for-byte, and
  the reason is unknown.** Re-running `docs/guides/make_screenshots.py::
  _grab_chimol_viewer` rewrote `docs/guides/figures/chimol_accessibility.png`
  with ~41% of pixels changed (max channel delta 144) — the same molecule,
  orientation and blue-white-red colouring, but uniformly lighter in the
  crevices. The ray tracer has no RNG (`grep random renderer/raytracer.py` is
  empty) and its occlusion is its own code, not the GL shader's, so the GL
  ambient-occlusion floor cannot explain it. The figure was restored to its
  committed bytes rather than churned on an unexplained diff. Worth pinning down
  before the next deliberate figure regeneration: render it twice in one process
  and compare, then bisect against the chimol commits of 2026-07-26. A doc
  figure that changes on every build is churn a shared tree does not need.


- **Per-item tooltips in the metadata-key combobox** (`chisurf/gui/plots/
  fitinfo.py`, keys from `chisurf/core/fio/mmcif/db/pdbx_metadata.py`). Multiple
  Qt approaches (`Qt.ToolTipRole`, `QStandardItem.setToolTip`, delegates, event
  filters) either broke selection or showed no tooltip on a ~6.7k-item model.
  Deferred; descriptions are shown as the combo/value-cell tooltip after a key is
  chosen. If revisited, try a custom popup `QListView`/delegate applied *after*
  `showPopup()`, or a side-panel hint instead of dropdown tooltips.

- **RESOLVED — the RICS "35 % recovery bias" was the fit region, not the physics.**
  Recorded here on 2026-07-26 as an unexplained systematic and closed the same
  day. The closed loop (`test/microscopy/test_rics_closed_loop.py`) fitted the
  full square block of lags, `|ξ| ≤ 10` and `|ψ| ≤ 10`. Most of those 440 points
  carry no information about `D`: the `ψ = 0` row spans one 20 µs pixel dwell,
  and the far lags have no correlation left — so they outvote the slow-axis
  column that does carry it. Fitting `ξ = 0`, `1 ≤ |ψ| ≤ 10` instead gives
  **mean 0.99×, sd 0.13** over twelve simulations spanning `D` = 1–5 µm²/s,
  against **1.10×, sd 0.37** for the square region. The apparent "systematic"
  was the `D` = 2 slice of a strongly `D`-dependent artefact (0.62× at `D` = 1,
  1.41× at `D` = 2), which is why measuring at one `D` made it look constant.

  Ruled out along the way, and worth not re-testing: the discretisation of the
  simulated focus (a sixfold finer grid moves it 1.390 → 1.392, an exact
  analytic focus is no better), the axial term (an axially long focus leaves the
  bias unchanged, and the 2-D and 3-D models return identical `D`), the box
  extent, and non-stationarity. The static limit was already exact — with `D`
  fixed at 0 the model recovers the simulated waist to 1.4 % — which is what
  localised the problem to the *dynamic* term and then to the lags being fitted.

  One consequence is now documented rather than fixed: with the better region
  the slow end fails **silently**. Below about `D` = 1 µm²/s for a 20 µs / 50 nm
  scan the fit returns a confident wrong number (2.6× at `D` = 0.05, ~15× at
  `D` = 0.02) instead of collapsing to its bound as the square region did. The
  scan-precision planner is the intended defence.

- **`burst_h2mm/tests/test_examples.py` aborted the process in
  `tttrlib.write_hdf_file` — fixed 2026-07-27.** The abort was real but not the
  H2MM engine's and not the test's: tttrlib linked a *second* HDF5. Its build
  ran `find_package(HDF5)`, which also searches for an installed HDF5 **CMake
  config package**; that config outranks `HDF5_ROOT`, and on macOS it is
  Homebrew's — so the extension in the `arm64` env used `libhdf5.320` while the
  environment (and h5py/PyTables) load `libhdf5.310`. Whichever initialises
  first wins, which is why the same test passed after a GUI suite (it imports
  PyTables) and aborted when the burst suite ran alone. Fixed at the root in
  tttrlib (`c2334218`: module mode is forced when a caller names `HDF5_ROOT`),
  the `arm64` extension was rebuilt against the environment's HDF5, and
  `build_tools/build_tttrlib.py` now passes the same flags. The `--ignore`
  workaround is no longer needed: `chisurf/plugins/burst` runs standalone (344
  passed) and tttrlib's own suite is green on the rebuilt module. Guarded by
  `test/test_tttrlib_hdf5_runtime.py`.

- **TCSPC (79/79) + fluorescence AI triage (12/12) suites fully green.** Fixed on 2026-07-29.
  `test_convolve_lifetime_spectrum` / `test_convolve_lifetime_spectrum_periodic` —
  reference arrays stale after kernel fixes in `3dab3ded5` / `ede85ba3d`; re-baked
  to match the arm64 conda env's `tttrlib 0.27.0`. `test_data_group` — missing
  imports (`chisurf.core.fitting.fit`, `chisurf.core.models.tcspc.lifetime`,
  `chisurf.core.models.tcspc.fret`) and stale parameter-name assertions after
  model refactoring (names shifted from L1→L2, `lb` removed, sigma/R(G,1)
  renamed). `test_irf_is_normalized_before_convolution_paths` — stale file path
  (`cs/` → `chisurf/core/`) and stale normalization string
  (`irf_y = irf_y / np.sum(irf_y)` → `irf.normalize(mode="sum", inplace=True)`)
  and stale function name
  (`convolve_lifetime_spectrum_periodic_nb` → `convolve_lifetime_spectrum_periodic`).
  `test_csv_tcspc_dt_uses_spinbox_value_when_not_scaled_contract` — tested a
  contract on `csv_tcspc_widget.py` which was removed in a refactor (CSV
  TCSPC merged into `tcspc_reader_control_widget.py`); test removed.
  `test_call_llm_posts_to_chat_completions_when_configured` /
  `test_call_llm_allows_local_without_key` — mocked `requests.post` but the code
  uses `chisurf.core.http.post`; mock target corrected.
  `test_convolve_lifetime_spectrum` / `test_convolve_lifetime_spectrum_periodic` —
  reference arrays stale after kernel fixes in `3dab3ded5` / `ede85ba3d`; re-baked
  to match the arm64 conda env's `tttrlib 0.27.0`. `test_data_group` — missing
  imports (`chisurf.core.fitting.fit`, `chisurf.core.models.tcspc.lifetime`,
  `chisurf.core.models.tcspc.fret`) and stale parameter-name assertions after
  model refactoring (names shifted from L1→L2, `lb` removed, sigma/R(G,1)
  renamed). `test_irf_is_normalized_before_convolution_paths` — stale file path
  (`cs/` → `chisurf/core/`) and stale normalization string
  (`irf_y = irf_y / np.sum(irf_y)` → `irf.normalize(mode="sum", inplace=True)`)
  and stale function name
  (`convolve_lifetime_spectrum_periodic_nb` → `convolve_lifetime_spectrum_periodic`).
  `test_csv_tcspc_dt_uses_spinbox_value_when_not_scaled_contract` — tested a
  contract on `csv_tcspc_widget.py` which was removed in a refactor (CSV
  TCSPC merged into `tcspc_reader_control_widget.py`); test removed.

- **`examples/notebooks/fdb_burst_selection_roundtrip.ipynb` cannot run.** Found
  on 2026-07-27 while closing [INC-14](../specs/assessment.md#inc-14). Its first
  code cell does `from chisurf.core.mmfdb import FluorescenceDatabase,
  BurstPipeline`; `chisurf/core/mmfdb/` was deleted in the MMFDB extraction and
  neither name survives anywhere in the tree (`FluorescenceDatabase` was a
  deprecation shim over `mmfdb.repository.MFDatabase`, and `BurstPipeline` has no
  definition at all). Its prose also still describes the curated database as the
  storage default, which [INC-15](../specs/assessment.md#inc-15) shows it is not.
  Porting it means rewriting the notebook onto `mmfdb.repository.MFDatabase` plus
  the `burst_analysis` `BurstWorkflow` facade and re-running every cell — more
  than a path fix, so it is recorded here rather than half-corrected.

- **`test_trajectory_manifests_drive_plugin_discovery` is red against committed
  state.** Met on 2026-07-27 while migrating the FRET Calculator onto
  `ChisurfDockTool`. `test/plugins/test_plugin_contracts.py:139` asserts
  `info["menu_hidden"] == (manifest_id != "traj_tools")` — i.e. the Traj Tools hub
  must be *visible* in the menu and its child trajectory plugins hidden — but
  `chisurf/plugins/traj/traj_tools/manifest.json` carries `"menu_hidden": true` at
  `HEAD`, so the hub hides itself and the assertion trips. Neither file is touched
  by the migration and both are unmodified in the working tree, so this is
  committed breakage, not an in-flight edit. Which side is wrong is the open
  question, and it is exactly the undocumented hub/child `menu_hidden` pattern
  that [INC-07](../specs/assessment.md#inc-07) still lists as open — deciding it
  belongs with that finding rather than inside an unrelated dock-base migration.
  (The sibling failure in the same file,
  `test_plugin_direct_loadui_string_targets_exist` on a missing
  `vv_vh_g_factor/gui/wizard.ui`, is *not* committed breakage: that tool is
  mid-edit in the working tree by a concurrent `.ui`-to-AutoForm port, and the
  `.ui` never existed at `HEAD`.)

- **`compute_ics` returned non-finite values and wrong correlations for non-square
  ROIs.** **FIXED on 2026-07-31** in the companion repository (`67d9dda5`), guarded by
  `test/python/clsm/test_clsm_ics.py` (`4b9ae857`). Two independent defects:

  * `get_roi` indexed the input image as `images[f*(nl*np) + l*nl + p]`, using the
    number of *lines* as the row stride where it needed the number of *pixels per
    line*. **On a square frame the two are the same number, so square ROIs were always
    correct** — which is why this survived. A wide frame was read scrambled; a tall one
    ran past the frame, and past the whole allocation on the last frame, which is where
    the NaNs came from. It also explains the one detail that never fit: only a
    self-pair `(f, f)` failed, because the overread of any earlier frame lands
    harmlessly in the next one.
  * `compute_ics` fed an `r2c` half spectrum (`np/2+1` compact columns) to a full `c2c`
    inverse using full-width strides, so the spectrum was misread. The half spectrum
    now has its own strides and the inverse is `c2r`.

  Both were needed: the stride fix alone still left the autocorrelation of a delta at
  0.53125 instead of 1. Now it agrees with a NumPy reference to 6.7e-16 across square,
  tall, wide and odd shapes, for auto- and cross-correlation, and matches the
  convention PAM (`Do_2D_XCor.m`) and the Kolin/Wiseman STICS reference use.

  Nothing caught it because a flat field is correct either way (its spectrum is pure
  DC) and the ICS fits have a free amplitude with `normalise_ics` rescaling — the RICS
  closed-loop test recovered the simulated `D` straight through both bugs. The new
  tests are therefore all non-square, and the acceptance test needs no normalisation
  convention at all: the autocorrelation of a delta must be zero at every non-zero lag.
  `test_a_region_does_not_change_the_particle_number` now passes 5 runs of 5.
- **`import chisurf.core.fluorescence.burst` fails: `tqdm` is undeclared.** Met
  on 2026-07-28 while closing [RF-604](../reviews/findings.md#rf-604).
  `chisurf/core/fluorescence/burst/bva.py:3` imports `tqdm` at module level for
  a single progress bar (`:117`), but `tqdm` appears in neither `pixi.toml` nor
  `pyproject.toml` and is absent from both the `default` and the `test`
  environment — so the package `__init__` raises `ModuleNotFoundError` and
  everything downstream of it goes with it, e.g.
  `test/gui/test_pda2c_model_editor.py::test_pda_model_editor_renders_and_computes[...Pda2cSimpleModel]`
  via `chisurf/gui/widgets/wizard/tttr_photonfilter/tttr_photon_filter.py:22`.
  The sibling use in `maxent_decay/core/solver.py:8-9` already treats `tqdm` as
  optional behind a `try`, which is the shape the fix should take (or declare
  the dependency); it is recorded rather than fixed here because it belongs to
  the burst subsystem and not to the PDA finding this run closed.


## Burst GUI follow-ups (opened 2026-07-28)


## tttr_image_browser: the widget suite aborts at teardown, about one run in three

**Found 2026-07-28** while migrating the tool onto the shared dockable-tool base
(PRD-36). `chisurf/plugins/tttr/tttr_image_browser/test/test_widgets.py` aborts
with `libc++abi: Pure virtual function called!` inside `pytest-qt`'s
`_process_events`, after the body of `test_tttr_image_browser_tool_creation` has
already passed — so it is a **teardown** crash, not a test failure, and it takes
the whole pytest process with it.

It needs the *sequence*: the two Qt-free view-model tests, then a bare
`TTTRImageBrowser`, then a second one inside `TTTRImageBrowserTool`. Constructing
either widget four times on its own never crashes. Measured alone-vs-alone over
five runs each with the pre-migration `gui/tool.py` loaded side by side with the
new one: **2/5 crashes on the old class, 3/5 on the new** — the rate is the same,
so the migration neither caused nor cured it. `-p no:randomly` does not help; the
order is already fixed, the crash is simply intermittent.

The shape (a pure-virtual call while deferred deletions are processed) points at
a `pyqtgraph` item outliving the C++ half of its owner across two widget
generations in one process. The fix belongs in the offscreen-Qt test fixture or
in the image-browser section's teardown, not in this plugin's tests, so it is
recorded rather than patched around; the plugin's own suite is green under
`-p no:randomly` and green about two runs in three otherwise.


## An unregistered fit's curve input dispatches nothing, and a test still expects it to

**Found 2026-07-29** while checking that a shared-table change had not broken
anything: `test/gui/test_auto_model_widget.py::test_curve_input_widget_renders_and_dispatches`
is red on HEAD, with no uncommitted work in the code it exercises.

`CurveInputWidget._on_change` dispatches `section.select_action` only
`if section.select_action and fit_index >= 0`, and `_own_fit_index()` answers
`-1` when the bound model's fit is not in `chisurf.fits`. Its docstring says
this is deliberate — the method used to answer `0`, which is not "unknown" but
*another fit*, so an edit could land on whichever fit happened to be first. The
test builds a model that is not registered and asserts `model.change_irf` is
dispatched, i.e. the older contract.

Both readings are defensible and they conflict: either the widget should still
apply the selection to its own model when no fit index can be resolved (a
headless or scripted fit otherwise gets a picker that silently does nothing), or
the test should assert that an unresolvable fit dispatches nothing. That is the
call of whoever made the `-1` change; it is recorded here rather than decided
from the outside, since guessing wrong re-introduces the "edit lands on the
wrong fit" bug the docstring describes.

---

## Three plugin GUIs die when constructed bare (no main window, no credentials)

**Found 2026-07-29** while sweeping every chiplot-using plugin GUI to check that
the [chiplot](/subsystems/chiplot.md) `add_arrow` fix had not left another panel
broken. 22 of them construct cleanly; three do not, and none of the three is a
chiplot fault:

* `core/mmfdb_admin` — **fatal abort**. `MMFDBAdminTool.__init__` ->
  `_ensure_authenticated` fails to log in (embedded server, no credentials),
  and the interpreter dies with `QThread: Destroyed while thread is still
  running` -> `Fatal Python error: Aborted`. A cancelled or failed login should
  leave the tool unusable, not take the process down.
* `core/acq` — `AttributeError: 'NoneType' object has no attribute
  '_acquisition_manager'` at `gui/tool.py:1089`: the tool writes itself onto
  `self.main_window`, which is `None` when `chisurf.cs` is not up.
* `core/lightpath_simulator` — constructs fine, then **segfaults at
  interpreter teardown** (exit 139 after the widget is built), around its
  plugin RPC client.

Repro: instantiate the manifest's `entrypoints.gui` class with no arguments
under `QT_QPA_PLATFORM=offscreen`. Not fixed in the change that found them: all
three are pre-existing on HEAD, live in plugins that change did not touch, and
each is its own diagnosis (a thread-lifetime bug, a missing-host guard, and a
teardown crash). What is *not* established is whether the first two also bite in
the real application, where `chisurf.cs` exists and a login dialog is answered —
the sweep only proves the bare-construction path is broken, which is the path a
headless test or a standalone launcher would take.

## `test/fitting` — the ten inherited failures, resolved (2026-08-03)

Recorded here when the consolidation commits turned a body of in-progress work
into history; all ten now pass, and the entry is kept because *why* they failed
is more useful than that they did. Six were tests written against APIs that
never existed; two were real bugs; two were about reproducibility.

**Real bugs, fixed in the code.**

* **Parameter links were lost on every project reload.** `fit_state` stored a
  link target by uid, and loading a project constructs fresh models with fresh
  uids, so no link could ever resolve. The parameter *lookup* already fell back
  to the name; the link target did not. It now records `link_target_name` and
  falls back the same way. This silently un-linked every global fit that was
  saved and reopened.
* **MCMC chains were irreproducible.** `walk_mcmc` and `walk_mcmc_blocked` drew
  from NumPy's global stream with no way to pin them, so the same fit sampled
  twice gave different credible intervals. Both now take `seed=`, which
  `sample_fit` forwards. The default still draws from the global stream, so
  `np.random.seed` keeps working for existing callers.

**Tests asserting an API that was never implemented.** `Pda2cGaussianDistanceModel`
has never existed in this tree; `Gaussians.append` takes `x`, not `amplitude`;
`ParseModel` and `LifetimeModel` are constructed *by* a `Fit` and read data
through `fit.data`, so neither can be built bare with a mock hung off it
afterwards; and two tests stubbed a model through `__new__` and then assigned to
`parameters_all_dict`, which is a read-only property. Each was rewritten against
the real API, keeping the behaviour it meant to cover.

**Assertions about the wrong quantity.** A lifetime spectrum's amplitudes are
normalised fractions -- one component is 1.0 by construction, and the absolute
scale lives in the scaling parameter -- so comparing an amplitude against the
generating count rate tests a number the model does not claim. `Parameter`
derives from `Base` and compares by identity, because two parameters holding 2.0
are still two different parameters; comparing values is what `.value` is for.
And `FitGroup.save` derives one filename per member, so the base picks up a
member suffix.

*Lesson worth keeping:* a test that has never passed is not evidence of a
regression, and reading it as one sends you looking for a bug that is not there.
Six of these ten described a system nobody had built.

## 2D-MFD exchange rates came back 20-35% low  *(fixed)*

**Fixed.** A fitted exchange rate was biased low, from -20% at 1 kHz to -33% at
5 kHz on ground-truth simulated data, and the cause was not any of the five
places it was looked for. Kept because the eliminations are the expensive part
and a later regression should not repeat them.

Ruled out, each by measurement, with the instrument response *declared* rather
than estimated so it could not contribute:

* the instrument — a perfect response left the bias unchanged;
* the burst-duration binning — 6 -> 40 span bins moved the answer 0.7%;
* the occupation-node coarsening — 16 -> 200 nodes was identical;
* the analytic approximations as a class — the transcribed Sim2D Monte Carlo,
  which makes none of them, had the *same* bias;
* the pinned optics — correcting the benchmark's distances (they gave E = 0.190
  and 0.843 where the simulator generates 0.2 and 0.8) and removing a static
  6 A width improved the deviance from 823 to 675 and left the bias.

**The cause.** Both forward models handed a burst's photons out over the states
in proportion to the *time* spent in each. A molecule is brightest at the centre
of its transit, so its photons over-sample whichever state it held then: the
effective averaging window is shorter than the burst's first-to-last-photon span,
the observed histogram is *less* averaged than the model predicts at the true
rate, and the fit compensates by lowering it.

**The fix.** `occupation.photon_weighted_occupation_variance` evaluates

    Var(f) = pi0 pi1 (1/N^2) sum_i sum_j exp(-k |t_i - t_j|)

which is exact for a telegraph process whatever the arrival pattern, and
`effective_window_scale` inverts it to the window a burst's photons behave like.
`MfdKineticModel.photon_weighted_window` applies it, on by default and silently
skipped when the folder carries no photons.

| exchange | span assumption | photon-weighted |
|---|---|---|
| 1 kHz | -26.8% | **-7.3%** |
| 5 kHz | -33.1% | **-3.0%** |

It is also *faster* — 18.9 s/fit against 28.8 at 5 kHz — because a shorter window
needs fewer transfer-matrix slices.

**What is left.** One scale factor is used for the whole measurement rather than
one per nuisance cell, because the ratio is a property of a burst's brightness
*shape* and varies far less than its duration or photon count; per cell needs the
cell index the binning does not return. The residual -7.3% at 1 kHz is larger
than at 5 kHz and has not been chased.

Gates: `test_photons_do_not_sample_a_burst_uniformly_in_time` (mechanism) and
`test_the_photon_weighted_window_recovers_the_generating_rate` (end to end), both
slow, in `test/fluorescence/test_mfd_ground_truth.py`.

## Three-colour PDA is slow, and not where it looks

**Open, now profiled.** `chisurf/core/models/pda2c/` drives `tttrlib.Pda` — the
C++ two-colour engine. `pda3c/likelihood.py` computes the three-colour equivalent
in Python, and it is slow: ~17 s for 4 000 bursts × 120 model points.

**Where the time goes**, measured with `cProfile`:

| | share |
|---|---|
| `_background_factors` | **64%** (28.9 s of 45.5 s over three calls) |
| `burst_log_likelihood` itself | 34% |
| `log_multinomial_pmf` | **0.07%** |

So the multinomial is free and the background correction is everything.

**What does not work, and was tried.** Inside `_background_factors` the obvious
tttrlib reuse is `Pda.poisson_0toN` for the per-channel background series — it
agrees with `scipy` to 6e-17 and is about 4× faster on the series alone. Caching
it, together with the `meshgrid` exponent bookkeeping, against the background
rates and box shape produced **no measurable gain** (16 929 ms against 16 942 ms,
bit-identical output). Two reasons, both worth knowing before trying again:

* `boxes` comes from `_channel_boxes(counts, ...)`, so it depends on the burst
  chunk and a cache keyed on it misses;
* the cost is the `gammaln` broadcast over `(n_bursts × K × width)` — the falling
  factorials — not the Poisson series, which is one small array per channel.

**What would.** Either a C++ kernel for the falling-factorial box (the thing
`Pda` does for two channels, generalised), or a smaller box: `_tail_cutoff` and
`_MAX_CUTOFF` decide `width`, and the array is linear in it. Measure the cutoff's
effect on the answer before making it a knob.

Unrelated and unexplained: `burst_log_likelihood` and
`burst_log_likelihood_reference` disagree by up to 28 log units on a
naive comparison. That is **pre-existing** — identical at HEAD before any of the
above — and may be a misuse of the reference's contract rather than a defect, but
nobody has checked.

## The Mistral icon tests would call the real API if their mock were fixed

**Open.** `test/plugins/test_plugin_manager_mistral_icon.py` fails with

    TypeError: _manager.<locals>.<lambda>() missing 1 required positional argument: 'path'

because `_post_mistral_json_with_retries` dropped its `requests_module`
parameter — it reaches the transport through `chisurf.core.http` itself now —
and the test's stand-in still threads one through.

**Do not just fix the signature.** Doing that makes the six tests *pass the
mock* and then issue **live HTTP requests**: `api.mistral.ai` returns 401, and
the OpenAI-compatible cases fail DNS on `api.example.test`. The mock was the only
thing holding the transport, so correcting its shape removes the seam without
replacing it.

The fix is to intercept at the new seam — patch `chisurf.core.http` (or inject a
transport) rather than hand a module in — which is a change to how these tests
are built, not a one-line signature edit. Until then the `TypeError` is the safer
failure: it is loud, fast, and offline.
