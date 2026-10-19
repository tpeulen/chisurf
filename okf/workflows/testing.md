---
type: Playbook
title: Testing
description: The non-GUI, GUI, smoke, and doctest suites and how to run a single test.
resource: pixi.toml
tags: [testing, pytest, ci]
timestamp: '2026-07-05T00:00:00Z'
---

# Environment (canonical: the `arm64` conda env)

Run all tests and any `python`/`pytest` in the project's **`arm64` conda env**,
never conda `base`. It provides the full stack the suite needs: the Qt bindings,
the compiled C++ extensions, and **IMP + IMP.bff** (`has_imp()` → True).
Since 2026-08-10 that IMP is **not** the conda package but a local build of IMP
**2.25** (`develop`) from `/Users/tpeulen/dev/imp`, with `modules/bff` symlinked
at the `../imp.bff` checkout and the build tree wired in by a single `.pth` —
see [IMP from source](imp-local-build.md). The conda `imp` package is removed
from the env; re-installing it would shadow the build.
Because IMP is present, the IMP-gated tests (the FRET plugin's
`refine`/`errors`/docking, `test_imp_engine.py`, `test_dock_project.py`) **run
here** — a `skipif not has_imp()` test only skips on a machine that lacks IMP,
not in `arm64`. As of 2026-08-10 they also **pass**: the FRET plugin suite is
6 failed / 122 passed, and the six are `test_examples.py` wanting the absent
`../olga` checkout. Until that date ten failed on
`IMP.bff.restraints.AVNetworkRestraintWrapper` — not because IMP lacked it, but
because `modules/imp-tricks/src` shadowed the package that has it; see
[IMP from source](imp-local-build.md#what-the-build-fixed-and-what-it-did-not).

```bash
source ~/.zshrc && conda activate arm64      # activate first
```

Local module sources are on `PYTHONPATH`, not installed as packages, so when
running pytest directly (outside `pixi run`) prepend them:

```bash
PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:." \
  python -m pytest <targets> -p no:cov -o addopts="" -q
```

`-p no:cov -o addopts=""` avoids the repo coverage config (which errors with
"Can't combine branch coverage"). GUI tests drive emtk apps on the offscreen
canvas and need no display.

# Test tasks

The pixi tasks wrap the above (CI uses pixi; they `build-extensions` first):

```bash
pixi run test           # default suite: everything not marked slow, e2e, gui or widget
pixi run test-gui       # tests marked gui or widget (not slow, not e2e)
pixi run test-slow      # tests marked slow
pixi run test-e2e       # test/e2e (marked e2e by test/e2e/conftest.py), not slow
pixi run test-smoke     # fast smoke test (test/test_basic.py)
pixi run test-doctest   # doctests
```

The four suites partition the whole tree by **marker**, never by path list or
`-k` substring (a node id that merely contained "gui" once fell out of every
suite, and `tests/` directories were on no list); precedence is slow, then e2e,
then gui/widget, then the rest, and `test/test_suite_partition.py` fails when a
test belongs to zero or two suites. Process-wide state a test changes is handed
back by the autouse fixtures of the root `conftest.py`
(`test/test_process_state_isolation.py` proves each).

All `test*` tasks `depends-on` `build-extensions`, so the
[compiled modules](/subsystems/compiled-modules.md) are built first.

# Single test

Run one test directly with pytest, e.g.

```bash
pytest test/test_basic.py::test_name -q
```

The `slow` marker is excluded from default runs. Tests live in `test/`, in
per-plugin `**/test/` directories, and in
`chisurf/gui/widgets/node_editor/tests`.

# Feature testing

Every feature should have a headless test path (API/CLI), not GUI-only.
Model/UI changes have a dedicated headless check via the `test-model-editor`
skill.

# Guarded imports are checked, because they fail quietly

`test/architecture/test_guarded_imports.py` walks the tree and re-resolves
every absolute import that a `try` body depends on. A `try: import x / except:
x = None` is how an optional dependency is handled *and* how a renamed module
becomes a feature that silently stops working — three such cases were live when
the test was written (ndX's reorganisation had disconnected two tools; a
renamed editor had degraded a labelling view to raw text).

Two patterns are deliberately not flagged: a handler re-importing the *same*
names is a version shim (a private SciPy symbol moving between releases), and a
nested handler is a direct-execution fallback. Anything genuinely optional goes
in the test's `OPTIONAL` map **with a reason**, so "this may be absent" is a
decision on the record rather than an anonymous `except`.

# A failure path must not open a dialog nobody can close

A modal question on an `except` branch of a headless run waits for a press that
never comes: the run wedges and the traceback is never seen, which is worse than
a crash because a hung run looks like a slow one. The emtk dialogs
(`emtk.message_dialog.MessageDialogs`) take an `auto_answer` for tests and
headless runs, and the shell logs before it asks. If a suite stops producing dots
and no test has failed, suspect a modal question before suspecting the machine
(`faulthandler.dump_traceback_later` names it). The Qt-era guard on raw
`QMessageBox` calls went with the Qt shell (W9 slice S6).

# A test that opens the shell must not write the developer's own settings

The emtk shell persists its layout, size and open plugins under
`<settings>/emtk/emtk_shell.*.json`. A test or a figure script that builds the
real window therefore runs with `CHISURF_SETTINGS_DIR` pointed at a scratch
folder; a headless frame (`--screenshot`, `make_headless_app`) persists nothing
at all, and `test_python_m_chisurf_opens_the_emtk_surface` asserts the real file
is untouched.

# GUI work is never blind — screenshot and look at it

**Any change that touches a GUI is unfinished until the widget has been rendered
and the rendering has been *looked at*.** Passing construction tests only prove
the widget did not crash; they say nothing about clipped labels, fields that
wrapped into a nonsensical two-column pairing, a status box that swallowed the
panel, a plot drawn upside-down, or a tab bar overlapping its content. Those are
the defects users actually report, and every one of them is invisible to
assertions and obvious in a PNG.

The loop, for every GUI change:

1. Build the app headlessly in the `arm64` env: an emtk app on the offscreen
   canvas (`emtk.testing.Driver(app, size)`, or the whole window with
   `python -m chisurf --screenshot PATH --size WxH`) — no display needed.
2. Drive it into the state a user would see (load a real test file, run the
   analysis, switch to each tab) — an empty app hides most layout defects.
3. Save the frame into the scratchpad (`emtk.testing.render` / `save_png`), then
   **read the PNG and inspect it**. The agent inspects it; do not hand PNGs to
   the user to eyeball.
4. Fix what looks wrong and repeat until it looks right. Draw at a second size
   before the final grab — some layout artefacts only show after a resize.

**A 3-D viewport** (ChiMOL) draws through the same offscreen canvas:
`ChimolApp` renders into `draw_frame`, and
`chisurf/plugins/chimol/test/screenshot.py` (`grab_window` / `grab_view` /
`save_png`) saves it and refuses a uniform image rather than passing a blank one.

The Qt-era recipe (`QT_QPA_PLATFORM=offscreen`, `widget.grab()`,
`WA_DontShowOnScreen` for GL children) went with the Qt shell (W9 slice S6).

Until this existed, the appearance of the one part of ChiMOL where appearance
matters most was judged either through the ray tracer — a different renderer,
with no materials and no transparency — or by asking a human to look. Both were
misleading in practice: a metaball material tuned against the ray tracer looked
entirely different in the viewport.

Interactive behaviour (a dragged ROI, a picked point) is still verified by
driving the signal programmatically and asserting the model changed, not by
looking.

Screenshots that end up in `docs/guides/` are produced the same way from the real
widget — see `docs/guides/make_screenshots.py` — never as mockups.

# A migration is proven by a before/after pair

Rendering the *new* widget answers "does this look right". Replacing a
hand-written widget asks a different question: **was anything lost?** A panel can
look immaculate and be missing the one control the fit needed. So a migration —
porting a legacy widget to AutoForm, or any like-for-like replacement — is
verified as a **pair**.

The loop:

1. **Grab the legacy widget first, before touching the code.** Once it is deleted
   or aliased away the baseline is unrecoverable. Settle the comparison format
   first as well: changing what you record invalidates baselines already taken.
2. Grab the replacement in the **same state**, at the same render width — a
   different width reflows the layout and confounds the comparison.
3. Diff the control inventories, read both PNGs, and accept only on parity.

`test/gui/migration_parity.py` provides the pieces: `capture(widget, name, phase)`
writes `<name>.{before,after}.png`; `control_inventory` extracts the comparable
content; `compare_inventories` reports what was lost or gained; `layout_tripwire`
catches gross failures.

**Parity is control inventory, not pixels.** An AutoForm port *deliberately*
changes layout — a `parameter_group_table` replaces stacked labelled rows,
because that is the improvement. Any pixel-similarity or SSIM gate is therefore
either red on every migration or tuned so loose it proves nothing. Compare *what
controls exist*:

- Enumerate every control in the before-image — each parameter, its fixed/bounds
  toggles, every button, picker and toggle.
- Confirm each is present and reachable in the after-image, and that values
  round-trip identically for the same loaded data.
- Record deliberate differences ("6 stacked rows → 1 table"). A **missing**
  control is a blocker.

**Two traps that make a naive diff useless.** Both were hit on the Lifetime
migration:

- *A name that moved into a table cell reads as lost.* `findChildren(QLabel)`
  cannot see cell text, so porting to a parameter table reports every parameter
  as missing. `control_inventory` walks item-view models for exactly this reason —
  a comparison blind to table content is red on every migration.
- *Renames masquerade as losses.* `r[MHz]`→`rep`, `Linearize`→`DNL` (the same
  `correct_dnl` flag, relabelled by an old `.ui`), `curve`→`full`, `...`→`…`,
  `update`→`🔄`. Text is normalized (rich-text tags, disclosure glyphs, case,
  whitespace) before diffing, and the remainder still needs reading by a human
  who knows which control is which.

Keep the mechanical **tripwire** alongside the human read — `layout_tripwire`
checks non-empty render size, enough visible children, and nothing positioned
outside its parent. That catches the blank-panel and collapsed-layout class the
eye skims past; the inventory diff catches the semantic loss.

# Citations

[1] [Project instructions (CLAUDE.md)](/references/claude-md.md)

## Release-readiness schema and e2e foundation

The native view vocabulary is exported by emtk's readers, with extension keys
owned by the relevant preprocessor. `test/test_ui_schemas.py` now covers native
form maps/templates and tour routing as well as the legacy loader. Rejection
cases stay green; accepting a native dictionary is not permission to drop its
fields into a Qt dataclass. Source integration was 649 targeted passes; the
pinned package plus workflow/triage guards passed 677.

`build_tools/dev_utils/triage_failures.py --junit <file> [--write <report>]` groups
JUnit failures and errors by owning workstream without importing the GUI. CI
runs a separate e2e job with always-uploaded render artifacts, checks smoke
before packaging, and fails explicitly if the private chimol deploy key is
missing. The click-all harness is being verified one isolated plugin at a time.


## Isolated plugin interaction gate

`test/e2e/test_click_all_plugins.py` discovers native entrypoints and the
remaining Qt-only factories. Each plugin runs in its own process with scratch
settings, metadata, object storage and cache. Worker JSON/log/PNG artifacts
live in `renders/e2e`; their harness_sha256 must match the tested source.
Timeouts, native crashes, missing tours/tooltips and unreachable controls are
explicit failures. A failed factory cannot retain an older PNG as evidence.

Native clicks require a visible effective clip and real engine delivery to
the intended context. The recorder maps translated/scaled child painters to
global coordinates, distinguishes independent engines with identical IDs,
opens actual AutoForm folds and scrolls reachable controls. Tour checks walk
introductions and operate the first real awaited target; duplicate labels
resolve through authoritative geometry/context, and ambiguity fails.
Field text retained for interaction is private to the worker, not serialized.
OS dialogs cancel; service/network and external-process actions remain
guarded. Slow local computations must expose a working Cancel/Stop control.

Re-derive the harness regressions with
`pixi run -e test python -m pytest test/e2e/test_click_all_harness.py -q`
(36 passed), and select real plugin cases with `-k <plugin_id>` on the click-all
file. A complete plugin matrix remains a programme gate after the owning
workstreams supply tours, demos, reachable layouts and source prerequisites.
The C27 matrix and intermediate hash runs are diagnostic, not acceptance.


## Real-use QA matrix

The click-all sweep, the slice parity tests and most widget tests drive a synthetic
`emtk.testing.Driver`: one fixed size, English, scale 1, a press and its release delivered back
to back at one point. The owner found three bugs that every one of those tests passed: clicks
missing after a window resize, an emtk shell without the ribbon, console plots shown as text.
Each sat on an axis the harness never varied, or between the areas the slice tests owned. The
matrix varies those axes, one at a time.

**1. Realistic input (`~/dev/emtk/emtk/testing_realistic.py`).** `RealisticDriver` is a `Driver`
subclass, so every existing helper keeps working. Events are `rendercanvas` dicts queued by
rendercanvas' own `EventEmitter`, which merges consecutive pointer moves and wheel deltas between
frames as a desktop does. They are translated by `emtk.native.CanvasEvents`, the code a real
window runs. A click travels to its target over `move_steps` frames. Press and release land in
different frames while the hand drifts `jitter` px. Wheel notches arrive one per frame. Held keys
repeat on a virtual platform clock (`hold_key`), and `blur()` releases held keys. `resize()` and
`set_scale()` arrive as resize events, and `move_window()` moves the window under a still hand.
Frames draw into the real `QuadPainter` at the device scale (`HostPainter` records and forwards).
`HostedDriver` runs a real `NativeHost`, either on an offscreen canvas with a chosen pixel ratio
or on a **hidden glfw window**. The window's `show_window` is suppressed. It exercises the
display's content scale, framebuffer vs window size, `glfw.set_window_size` resize callbacks and
the live cursor query. Only the OS cursor is simulated (`glfw.get_cursor_pos`), so the real
pointer is never warped. Trap: a hidden window's swap chain is occluded, so wgpu cancels the
frame before the app draws (`DrawCancelled: Occluded`). The glfw driver therefore runs the
surface's CPU half itself. `clipped_texts(painter)` lists labels the active clip cuts. Tests:
`tests/test_testing_realistic.py` (17, including the glfw cases on macOS).

**2. Click-all matrix axis (`test/e2e/test_click_all_plugins.py::test_emtk_plugin_real_use`).**
Each variant reruns the whole sweep (tour, tooltips, every safe control) with one change.

| variant | change | extra failure |
|---|---|---|
| `size_800x600`, `size_1920x1080` | window size | a control's own caption clipped |
| `resize` | 1100×720, then 800×600 after half the clicks; later clicks re-resolve | as above |
| `scale2` | `RealisticDriver(scale=2.0)`, the real painter at ratio 2 | as above |
| `lang_de`, `lang_fr` | `EMTK_LANG` | a clipped *translated* string; an English source drawn although the catalogue translates it; two controls sharing one id (captions that translate alike) |
| `realistic` | `RealisticDriver` at scale 1 | — |

A "caption" is the label of a button, checkbox, radio button, menu item, header, tab or fold
(`CAPTION_KINDS`). List rows and fields hold content, and a long name clipped in a narrow list is
by design. Document viewers (`CONTENT_VIEWERS`: `help`) show English documentation by design, so
they skip the untranslated check.

Selection is set by `CHISURF_E2E_MATRIX`. `sample` is the default and runs
`CHISURF_E2E_MATRIX_SAMPLE` plugins per variant (3). They are a hash-ranked choice that rotates
with `CHISURF_E2E_MATRIX_SEED`, so successive CI seeds cover the catalogue. `full` runs every
variant times every plugin. A comma list of variant names runs those variants in full, and `off`
runs none. Artifacts go to `renders/e2e/<variant>/<id>.{json,png,log}`. The JSON adds
`clipped_labels`, `untranslated_visible`, `missing_translation` (the catalogue backlog: an
extracted source whose translation is unfinished, which is recorded but does not fail) and
`resized_at`. Realistic variants get 3× the worker timeout, and the others 1.5×. The base sweep is
unchanged. Run one case with
`python -m pytest test/e2e/test_click_all_plugins.py -k "real_use and lang_de-synthetic_decay"`.

**3. Whole-app parity (`test/native_emtk/test_emtk_shell_whole_parity.py`).**
`capture_shell_whole_qt_before.py` records everything the Qt main window offers in
`shell_whole_qt_inventory.json`. That covers the ribbon (tabs, panels, buttons, corner controls),
every menu action, every toolbar action, each dock's title, labels and buttons, and one behaviour:
the console draws a figure. Trap: the ribbon builds after the window shows, so the script waits
for it. A capture without it would pass every comparison, which is why
`test_the_inventory_covers_the_whole_window` exists. The test draws the emtk shell at 1440×900,
opens each menu and shows each dock, then matches by caption, so a ribbon button that became a
menu item still counts. A **ribbon tab** must be a tab or button: a menu header of the same name
does not count, because that is how the missing ribbon hid. Gaps go in `KNOWN_GAPS`, each with a
reason, and the list only shrinks: `test_known_gaps_only_shrink` fails on an entry the shell now
has.

**4. Settle after every input (one-shot input is spent by the frame loop).** A wheel notch, a click, a key,
typed text and a drop are *one* event. The owner found a plot that zoomed on every frame after a single notch,
until the pointer left it (2026-10-12). Every test passed it: each looked only at the frame *after* the notch, and
the hand-rolled test drivers zeroed `io.mouse_wheel` themselves after each frame, doing the frame loop's job. Five
tools had also patched the symptom locally (`self.io.mouse_wheel = 0.0` after their draw) instead of fixing it in
emtk. The rule:

- emtk's frame loop spends every one-shot input (`IO.ONE_SHOT`) when the outermost frame on an `IO` ends. A widget
  never clears input "for the next frame", and an app never zeroes the wheel after its draw; a widget may zero it
  only to route it away from widgets drawn later in the *same* frame.
- Replay input as the real sequence, not one synthetic call: the notch **and the hover that follows it**, the
  release **and the idle frames after it**. `emtk.testing_realistic.assert_settles(driver, action, observe,
  frames=30)` performs the gesture, then draws idle frames with the hand still and fails if the observed state (by
  default the whole drawn frame) changes again or the app keeps asking the host for frames. `driver.swipe(dy)` is a
  trackpad gesture (many small deltas and a momentum tail): hosts turn raw deltas into notches in proportion
  (`emtk.events.WheelAccumulator`), never one notch per platform event.
- emtk runs it over every input widget and gesture (`tests/test_settle_sweep.py`). The click-all sweep runs it as
  the `settle` phase (`CHISURF_E2E_PHASES=settle`, `exercise_settle`): one notch over each plot and overflowing
  scroll region of every tool, before and after the tour, and *every* recorded view range and scroll offset must
  hold still for 30 frames. Results land in the worker JSON under `settle`.

**First runs (2026-10-11).** Two sampled seeds of 21 cases each were run. Sizes, scale 2 and realistic input
passed everywhere they ran, and so did resize on `burst_gs`. Two tools resized only after their sweep ended,
because a resize after a fixed number of clicks missed tools with few controls; that is fixed. The language
variants found seven code defects, all fixed:
plot titles and axes, padded captions (19 tools), layouts measuring the English source (5 tools), check marks before
translation, untranslated placeholders, button ids that collide when translated (help), and button rows. A 4.5 s
help frame was also found and fixed. The open findings are in
[known issues](../references/known-issues.md), under "Real-use matrix: layout and tour defects outside the language
checks" and "emtk shell: Qt main-window controls it does not have yet". The hidden glfw driver reproduced the wheel
after a window move at emtk `84ce461`, which `2021c7b` fixed.

Where to pick this up:

1. Measure: run `CHISURF_E2E_MATRIX=full` once, about 7 × 124 workers and several hours, in the background. Seeds
   0 and 1 cover 42 of 868 cases. Group the failures by the last error line of `renders/e2e/<variant>/*.json`, as
   for the base sweep.
2. Open: the catalogue backlog dominates the language variants' `missing_translation`; that is the queued i18n job.
   The untranslated check only fires when a catalogue translation exists but English was drawn, which is a code bug
   by definition.
3. Open: `HostedDriver` is not yet a matrix variant. The click-all workers drive the synthetic and realistic
   drivers only, so the glfw path is covered by `tests/test_testing_realistic.py` and `test_native_resize_clicks.py`
   alone. A `hosted_glfw` variant needs a display session, so it cannot run in CI.
4. Open: a Qt-host driver is still missing. emtk docks hosted in the Qt main window go through `emtk/qt_host.py`,
   which this driver does not exercise; that is where the resize-click lane fixed its bug.
5. Measure: the settle phase (2026-10-12), `CHISURF_E2E_PHASES=settle CHISURF_E2E_MATRIX=off pytest
   test/e2e/test_click_all_plugins.py -k survives_every_control -m e2e` against emtk b82aa06: 123 workers passed,
   40 tools offered 130 targets (114 plots, 16 overflowing scroll regions), and every one settled. Trap: run it
   against the *installed* emtk (reinstall arm64 after an emtk push). The workers import it, and a stale install
   tests the old frame loop. The phase measures only what is on screen in the first frame and after the tour, so
   a scroll region that overflows only once data is loaded is not visited. Open: it notches only; drag, click and
   key settles over every plot run in emtk's `tests/test_settle_sweep.py`, not per tool. `swipe` is not used in
   the e2e phase yet.

## Simple user sequences: open every popup, close it every way, click elsewhere

The owner right-clicked ndX's map in the emtk shell, chose *Fit gate to the population here*, and no
click landed anywhere after; the menu stayed drawn (2026-10-12). Every test passed, because none
did what a person does next: open the menu again, let the hand cross its rows, close it, and click
something else. Two defects hid there. The menu's *Send selection to ▸* row is a submenu
(`emtk.widgets.menus.Menu`) that had no `tooltip`, so highlighting it raised inside the popup in
every frame. The popup was drawn, never closed, and held the ndX frame's input. Also, a press
outside a hosted child never reached it, so its menu stayed up and the first click back into it
only closed the menu.

**The invariant.** After a popup closes by any path (a pick, Escape, a click outside, a second
right-click, the wheel), nothing holds the input and the next click lands on its target. "Popup"
covers a context menu, a combo's list, a plot's right-click menu, a modal or a tooltip. Check it
with `emtk.testing_realistic.assert_input_released(driver, target, landed, apps=(shell, child))`.
It fails when any frame in `apps` still holds an overlay (`held_overlays` names it), or when the
click on *target* did not register. Give it a target away from where the popup was, and a
`landed()` that reads real state: a tab changed, a toggle flipped, the form's `on_used` fired.

**Where it runs.**

- The click-all sweep (`test/e2e/test_click_all_plugins.py`) has a **context-menu phase**,
  `exercise_context_menus`. It runs before the click sweep and again after the tour has loaded
  the demo data. It right-clicks every plot (implot and chiplot) and every data table, up to
  `CONTEXT_MENU_TARGETS` per tool, then closes the menu by each path in
  `CONTEXT_MENU_CLOSE_PATHS`. `hover_rows` walks the hand over every row, submenus and disabled
  rows included. After each close it clicks a reference control (a selected tab, or a fold header
  or checkbox, clicked twice) and checks the press arrived. It also reports a menu that runs
  outside the window. Plot right-click menus are implot windows, not overlays, and the phase finds
  them through `implot._show_menu_window`. `CHISURF_E2E_PHASES=tour,context_menu` runs just this
  phase across the catalogue in about half an hour. The sweep's clipboard is kept in memory, so a
  *Copy* row never overwrites the user's clipboard.
- The emtk shell with a hosted tool: `test/native_emtk/test_ndx_context_menu_release.py`. It runs
  13 close paths on ndX's map menu, then a click inside ndX and one on the ribbon.
- emtk: `tests/test_popup_input_release.py`.

**What the fixes made structural (emtk).** An overlay that raises is closed and dropped
(`overlays._run`, `Context.draw_overlays`), so it can no longer hold input in every later frame.
`im.frame` restores the outer context even when a nested frame's end raises; before the fix, the
docks drawn after a failed child went blank. `overlays.dismiss(storage)` is what a host calls for
every hosted frame a press did not go to; the shell's `pointer_press` does it. Escape closes a
plot's right-click menu. A menu row is at most `MAX_LABEL_LINES` (26) line heights wide; a longer
one ends in "…" and shows its whole text, or the row's `tooltip`, while highlighted.

**First run (2026-10-12)**, `CHISURF_E2E_PHASES=tour,context_menu`, 123 tools, 228 right-click
targets, 111 menus opened. Every close path released the input. Three tools failed:
`burst_fcs_correlator`, `burst_fusion` and `fcs_filter_calculator`, whose plot right-click menus
ran out of the window at the right or bottom edge. That is fixed: emtk's implot now keeps the
menu inside the frame (`_keep_menu_inside`). A rerun of the three passed.

Where to pick this up:

1. The phase drives tools standalone (`load_plugin`), so the hosted-child path (a press outside a
   child must close its menu) is covered only by the ndX shell test. To cover it everywhere, host
   each tool in the shell for this phase. That costs about 2× the worker time.
2. Not exercised yet: combo lists (the click sweep opens them but closes them only with Escape),
   tooltips, modals, and the dock header's context menu. Add them as targets with the same five
   close paths.
3. The phase's `item` path picks only rows that pass `skip_reason`. A plot's own menu (implot) is
   closed with Escape, because its rows toggle the plot's own settings.

## Type-check ratchet

CI runs `pytest test/test_mypy_baseline.py -m slow` (blocking): `test/mypy_baseline.json` holds each
file's mypy error count and may only shrink. A file whose count rises, a new file with errors, or a
count that dropped without being written back fails. After fixing errors run
`python test/test_mypy_baseline.py --update`. Qt modules are `follow_imports = "skip"` in
`pyproject.toml` (the conda PyQt5 ships no stubs), so Qt names are `Any` rather than noise.

Re-derive it with a Python that has mypy: `pixi run -e dev python test/test_mypy_baseline.py --update`
(CI uses the `dev` env; the `test` env has no mypy module, so the guard raises there instead of
reading an empty run as zero errors). Baseline refreshes must only lower counts; an edit that raises
one is fixed, not recorded.

## Lint A/B targets

The approved lint worktree's target inventory is retained below. Select the
files relevant to a change; this list is not a command to run a full suite.
Use separate read-only revisions/archives for an A/B comparison and preserve
their working contents. Do not copy the old script's checkout loop into the
shared working tree.

Pixi remains the standard runner. For the documented arm64 alternative,
the old environment line required offscreen Qt, Agg, no bytecode and local
module source paths; use a task-specific root and cache:

```sh
READINESS_REPO_ROOT=/Users/tpeulen/dev/chisurf
MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=.:modules/mmfdb/src:$READINESS_REPO_ROOT/modules/chinet:$READINESS_REPO_ROOT/modules/imp-tricks/src:modules/chimol \
  NUMBA_CACHE_DIR=/private/tmp/readiness-numba-cache \
  /Users/tpeulen/mambaforge/envs/arm64/bin/python -m pytest <targeted-files> -q
```

The imp-tricks namespace startup repair is a prerequisite for this alternate
source path. Use scratch settings/MMFDB storage for every GUI judgment.

```text
chisurf/plugins/burst/accurate_fret/test
chisurf/plugins/burst/alex_suite/tests
chisurf/plugins/burst/burst_2cde/tests
chisurf/plugins/burst/burst_background/test
chisurf/plugins/burst/burst_browser/test
chisurf/plugins/burst/burst_bva/tests
chisurf/plugins/burst/burst_ebfret/tests
chisurf/plugins/burst/burst_fcs_correlator/test
chisurf/plugins/burst/burst_fusion/tests
chisurf/plugins/burst/burst_gs/test
chisurf/plugins/burst/burst_h2mm/tests
chisurf/plugins/burst/burst_irf_bg/test
chisurf/plugins/burst/burst_mle_analysis/tests
chisurf/plugins/burst/mfd_prepare/tests
chisurf/plugins/calculator/fcs_saturation_calc/tests
chisurf/plugins/calculator/fret_calculator/tests
chisurf/plugins/calculator/hub/test
chisurf/plugins/calculator/kappa2_dist/test
chisurf/plugins/calculator/kappa2_dist/tests
chisurf/plugins/calculator/phasor_calculator/tests
chisurf/plugins/calculator/psf_calculator/tests
chisurf/plugins/calculator/rics_precision/test
chisurf/plugins/calculator/rics_precision/tests
chisurf/plugins/core/batch_analysis/test
chisurf/plugins/core/boarding/test
chisurf/plugins/core/code_editor/test
chisurf/plugins/core/f_test/test
chisurf/plugins/core/globalview/tests
chisurf/plugins/core/help/test
chisurf/plugins/core/hmm/test
chisurf/plugins/core/lightpath_simulator/tests
chisurf/plugins/core/model_manager/test
chisurf/plugins/core/plot_settings/test
chisurf/plugins/core/plugin_check/test
chisurf/plugins/core/plugin_manager/test
chisurf/plugins/core/project_browser/test
chisurf/plugins/core/pto_inspector/test
chisurf/plugins/core/setup_channel_definition/test
chisurf/plugins/core/setup/test
chisurf/plugins/core/style_manager/test
chisurf/plugins/core/switch_user/test
chisurf/plugins/core/tttr_to_pto/test
chisurf/plugins/core/updater/test
chisurf/plugins/core/user_editor/test
chisurf/plugins/core/wizards/test
chisurf/plugins/fcs/fcs_calculator/test
chisurf/plugins/fcs/fcs_filter_calculator/test
chisurf/plugins/fcs/fcs_lfcs_sim/test
chisurf/plugins/fcs/fcs_merger/test
chisurf/plugins/fcs/flc_2d/test
chisurf/plugins/fluorescence_decay/irf_estimator/test
chisurf/plugins/fluorescence_decay/lltf/test
chisurf/plugins/fluorescence_decay/maxent_decay/test
chisurf/plugins/fluorescence_decay/synthetic_decay/test
chisurf/plugins/fluorescence_decay/tr_anisotropy/test
chisurf/plugins/microscopy/clsm_generator/test
chisurf/plugins/microscopy/clsm/test
chisurf/plugins/microscopy/imaging_tools/test
chisurf/plugins/microscopy/img_calibration/test
chisurf/plugins/microscopy/img_coloc/test
chisurf/plugins/microscopy/img_drift/test
chisurf/plugins/microscopy/img_flow/test
chisurf/plugins/microscopy/img_frc/test
chisurf/plugins/microscopy/img_pixel_intensity/test
chisurf/plugins/microscopy/img_pixel_micro_time/test
chisurf/plugins/microscopy/img_pixel_mle/test
chisurf/plugins/microscopy/img_pixel_nb/test
chisurf/plugins/microscopy/img_pixel_phasor/test
chisurf/plugins/microscopy/img_tracking/test
chisurf/plugins/microscopy/psf_determination/test
chisurf/plugins/microscopy/psf_determination/tests
chisurf/plugins/microscopy/region_mle/test
chisurf/plugins/microscopy/spot_finder/test
chisurf/plugins/microscopy/spot_finder/tests
chisurf/plugins/misc/games/test
chisurf/plugins/modelling/hydropro/test
chisurf/plugins/modelling/fret/test
chisurf/plugins/modelling/fps_json_editor/test
chisurf/plugins/traj/fret_trajectory/test
chisurf/plugins/traj/potential_energy/test
chisurf/plugins/traj/traj_align/test
chisurf/plugins/traj/traj_convert/test
chisurf/plugins/traj/traj_join/test
chisurf/plugins/traj/traj_remove_clashes/test
chisurf/plugins/traj/traj_rotate_translate/test
chisurf/plugins/traj/traj_save_topology/test
chisurf/plugins/traj/traj_tools/test
chisurf/plugins/tttr/audifier/test
chisurf/plugins/tttr/microtime_histogram/tests
chisurf/plugins/tttr/photon_table/tests
chisurf/plugins/tttr/ptu_alex_creator/test
chisurf/plugins/tttr/trace_browser/test
chisurf/plugins/tttr/tttr_count_rate_analysis/test
chisurf/plugins/tttr/tttr_count_rate_analysis/tests
chisurf/plugins/tttr/tttr_image_browser/test
chisurf/plugins/tttr/tttr_lut_tools/tests
chisurf/plugins/tttr/tttr_microtime_shifter/tests
chisurf/plugins/tttr/tttr_time_windows/tests
test/core/test_dye_definition_shipped.py
test/core/test_emtk_preview_gate.py
test/fio/test_ndxplorer_rpc_bridge.py
test/fio/test_setup_store_fresh_database.py
test/fitting/test_bff_sampler_result_boundary.py
test/gui/emtk_layout_checks.py
test/gui/emtk_port_parity.py
test/gui/test_emtk_port_parity.py
test/gui/test_metadata_editor_first_use.py
test/native_emtk/test_channel_definition.py
test/plugins/burst/test_background_diagnostics.py
test/plugins/burst/test_irf_background_window.py
test/test_build_tttrlib_sibling_envs.py
```


## Source companion path precedence

The launcher/cwd stays first when ChiSurf adds bundled source roots. An
editable ndxplorer finder already resolving the package needs no extra
module root on sys.path. Plugin test helpers can be imported after a native
plugin; preimporting test.gui to conceal a shadowing companion is unnecessary.
Verify test/core/test_bundled_packages.py and the existing foreign-environment
path tests. Keep ndxplorer tests in tests/ rather than a top-level test package.


## Companion test layout

ndxplorer keeps test modules and their fixtures under tests/. The former
top-level test package is retired, so source imports cannot shadow ChiSurf
test.gui. The parity scenarios now resolve their MFD and sampling fixtures
under tests/; the three real sampling tables remain unchanged.


## Runtime package-data selection

Release artifacts exclude test/test-descendant namespaces and fixtures in
package discovery, wheel data and sdist manifests. The package-data guard
uses actual setuptools namespace selection, FileList and build_py selection
(including stale SOURCES), rather than treating every checkout file as runtime
data. Runtime shaders, reader declarations and settings remain required.
Chimol demos use their owning packaged resources and explicit user overrides;
a checkout test directory must not replace those inputs.


## Text ink in layout diagnostics

Text collision and painted-overflow checks use aligned glyph ink bounds, not
the allocated remaining-line rectangle. Keep independent clipping assertions
active; a wide unused rectangle is harmless, a real glyph collision/overflow
is a failure. Mixed Qt/native captures must exit normally before they provide
acceptance: assertions printed before a shutdown crash are only diagnostics.

## Resource guard: memory, disk and leaked threads

A single pytest process runs ~33k tests. Two failure modes have taken the machine down
(2026-10-19): resident memory carried from test to test until swap, and `tmp_path` data
(~8 GB per full run, photon files and `.pto` containers) piling up under
`$TMPDIR/pytest-of-<user>/` until the disk was full mid-run.

- `pyproject.toml` sets `tmp_path_retention_policy = "failed"` and
  `tmp_path_retention_count = 1`: a passing test's directory is removed at teardown, and
  only the last run's failures are kept.
- `test/resource_guard.py`, loaded by the root `conftest.py`, appends one CSV row per
  test (RSS of the process and of its whole process tree, threads, child processes, disk
  drop, `tmp_path` size) as the test finishes, to `CHISURF_TEST_RESOURCE_LOG` or else
  `~/.cache/chisurf/test-resources/run-<time>-<pid>.csv` (newest 10 kept), and prints a
  "resources" summary. The record is written incrementally and outside `$TMPDIR` on
  purpose: the 2026-10-19 crash rebooted the machine, which wiped `/private/tmp` and with
  it a record that was only written at the end.
- The limits are enforced by `test/resource_watchdog.py`, a **separate process** polling
  every 0.25 s. A watchdog thread inside pytest failed to save the machine: a C extension
  that allocates while holding the GIL starves it, and it cannot see child processes. It
  stops the run (SIGKILL of the whole tree, exit 137) when the tree RSS >
  `CHISURF_TEST_MAX_RSS_MB` (4096), system memory available < `CHISURF_TEST_MIN_FREE_MB`
  (1024), swap grew by > `CHISURF_TEST_MAX_SWAP_GROWTH_MB` (2048) or free disk on the tmp
  volume < `CHISURF_TEST_MIN_DISK_MB` (4096); it prints the running test and the biggest
  growers from the CSV and deletes the run's `tmp_path` tree. `0` disables a limit. The
  swap and free-memory limits also trip when *other* processes (other agents' suites) eat
  the memory — that is intended: the run yields rather than tipping the machine.
- **The gate runs in chunks.** `python -m build_tools.dev_utils.run_tests_chunked [--resume]`
  runs every top-level `test/` directory, the loose `test/test_*.py` files and every plugin
  family as a pytest process of its own (52 chunks), waits for 3 GB available before each,
  and records `~/.cache/chisurf/test-resources/gate/<chunk>.log` + `summary.json`. A guard
  stop costs one chunk, not the run; `--resume` continues. Two single-process gate runs on
  2026-10-19 were stopped at 27 % and 25 % by the swap rule -- correctly, other agents' suites
  and the owner's own fits had swap at 5 of 6 GB.
- **Where to pick this up (2026-10-19).** Measured: the first 7228 tests (27 %, up to
  `test/native_emtk/test_emtk_shell_model_sections.py`) — no unbounded growth, peak tree
  2.2 GB in `test/fluorescence/test_mfd_simulation.py`; record
  `~/.cache/chisurf/test-resources/run-20261019-183924-12409.csv`. Open: the remaining 73 %
  (the crash that started this happened at 34–47 %, so the culprit is likely there): run
  `test/native_emtk` onwards plus `chisurf/` under the guard on a quiet machine — with ~30
  agents running, swap was already 7 of 8 GB before the run started, and the
  free-memory floor stops the run for that, as it should. Per-module growers still worth a
  look: `test/fluorescence/test_mfd_ground_truth.py` (+630 MB),
  `test/gui/test_emtk_port_parity.py` (+545 MB), `test/fitting/test_description_model.py`
  (+524 MB).
- Trap: never pass `--basetemp` into a long-lived scratch folder — pytest only clears it
  at the start of the next run with the same path, so it is never reclaimed.
