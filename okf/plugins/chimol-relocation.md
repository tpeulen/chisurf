---
title: ChiMOL moves to its own repository — sever first, move second
status: done
group: plugins
updated: 2026-08-14
---

# ChiMOL moves to its own repository — sever first, move second

**Target** (user, 2026-08-13): chimol becomes `~/dev/chimol` — a local git
repository, **no remote**, symlinked into chisurf's `modules/` the way
`tttrlib`, `imp-tricks` and `mmfdb` already are.

**The invariant** (user, same round): *"chisurf can depend on chimol, not the
other way around."* ChiSurf may import chimol; chimol may not import ChiSurf.

**The order** (user, same round): *"do the refactor before reloc so that it can
all be tested in place and the reloc remains mechanical."* Everything below
happens **here**, in `chisurf/plugins/chimol/`, against the real suite. The
move itself is then a directory move and an import rewrite — not a debugging
session in a repository where the tests do not yet run.

**cmtk goes with it** (2026-08-14): ChiSurf consumes cmtk **via chimol**, and
the ChiSurf↔cmtk interface is still floating — so this relocation is the
prerequisite for the cmtk work too (see
[chimol-cmtk.md](chimol-cmtk.md)).

## Where to pick this up

**The move is done (2026-08-14).** The engine lives at `~/dev/chimol` — a
local git repo, no remote, full 329-commit history extracted with
`git filter-repo --path` — symlinked as `modules/chimol` exactly like
`tttrlib`, `imp-tricks` and `mmfdb`, editable-installed via the new
`build-chimol` pixi task. ChiSurf imports it as bare `chimol`; the plugin
wrapper `chisurf/plugins/chimol/` (manifest, `__init__`, `__main__`, `test/`)
stays behind and is the only place that knows about ChiSurf. The seam and
portability suites stayed green through the move; the plugin window grab is
pixel-identical before/after.

### What was carried, and where each state lives

Three states existed at move time and none was dropped:

| state | where it lives now |
|---|---|
| full history (329 commits) | `~/dev/chimol` — extracted with filter-repo, rewritten to `chimol/` at repo root |
| the **staged index snapshot** (204 files, the cmtk→`renderer/ui` rename direction that never materialised on disk and matches no commit) | `~/dev/chimol` commit `d13209b` — "snapshot: chisurf staged-index engine state, carried verbatim" |
| the **disk state** the suite was green on (cmtk layout + `menus.py` + working-tree edits) | `~/dev/chimol` HEAD lineage, commit `cf9076d` |

The staged snapshot is byte-identical (verified by blob-hash comparison) and
sits in history one commit *before* the disk state, so the renderer/ui
direction is recoverable with `git checkout d13209b -- .` if it is ever
wanted. It was a rewind-era index: it deletes `repl.py`/`tour.py`/
`keybindings.py` that HEAD ships and that the browser host imports, so it
could not have become the final state.

### What the move changed on the ChiSurf side

* ~230 files rewritten `chisurf.plugins.chimol.chimol` → `chimol` (call
  sites, the whole plugin test suite, manifest, pyproject entry points,
  docs guides).
* `test_chisurf_seam.py` / `test_qt_seam.py` / `test_engine_is_portable.py`
  resolve the package through the import system
  (`Path(__import__("chimol").__file__).parent`) instead of relative paths —
  they follow whatever installation the host uses.
* `test_plugin_help_guide_seam.py` learned to resolve GUI modules in sibling
  checkouts (`modules/X/X/...`); chimol's allow-list key became
  `modules/chimol/chimol/app`.
* Found-and-fixed in passing: the `chimol-cli` console script pointed at
  `chimol.app.cli:main`, which never existed — the REPL moved to
  `chimol.cli` months ago. Now `chimol.cli:main`.
* `test_qt_seam.py` no longer counts `TYPE_CHECKING`-only imports as Qt
  (same rule the chisurf seam already applied); `menus.py` was the file that
  exposed it.

### The open front, in order

0. **The full-suite verdict on the move itself**: 3625 passed, 41 skipped,
   one failure — `test_keyboard_layout`'s browser case, which is
   T-20260814-01's half-finished `web/demo.py` rewire (`key()` reads
   `self.sink`, the test stubs `.gui`) and fails identically on the pre-move
   disk state (see known-issues). Everything else the move touched was
   either green on arrival or fixed in the same change.
1. **`test_prd_mentions.py` and `test_plugin_help_guide_seam.py` were red
   before the move** (offenders: `mfd_prepare`, `plot_settings`,
   `tttr_to_pto`, `filetools`, `lumis_quest` help.md, fret-core PRD mentions,
   stale `tttr/converter/gui` allow-list line). All belong to other plugins'
   modernisation debt — verify against HEAD before "fixing" anything there;
   none is relocation fallout.
2. **Retarget `test_qt_seam.py` at `QtWidgets`** rather than Qt as a whole
   (unchanged from below — the TYPE_CHECKING fix was not this).
3. **The twelve Qt-widget files to the shim** (widget rule below).
4. **`io/structure.py` DCD reader decision** — standalone chimol opening a
   trajectory (PRD-80 context) now has its own repo to decide it in.

### What the eighteen taught, and the trap to keep

Two of them were **real defects**, not tests pointed at a deleted widget, and
that ratio is the reason to keep checking:

* `apply_surface_quality` rewrote every splat name (`splat`, `gauss`,
  `interactive`, ...) to `"fast"` and applied the marching-cubes grid, so
  asking for the screen-space surface silently produced a different one and
  `is_splat_quality` then answered False downstream. The pipeline was
  unreachable through that path.
* `_targets_for` and the missing `registry.touch()` in
  `set_object_group`/`set_group_open` -- described under the dock removal
  above.

**A third was worse than a defect: the suite was reading the developer's real
preferences.** `test/conftest.py` isolated `CHISURF_SETTINGS_DIR`, but
`chimol.settings_dir` reads **`CHIMOL_SETTINGS_DIR`** and falls back to
ChiSurf's directory only when that is unset. So the isolation had been a no-op
for chimol's own files, and two assertions about *defaults* were really
assertions about whatever the developer last clicked -- a background asserted
black against a saved white, a surface quality asserted `splat` against a saved
`fast`. Both now pass, and a guard fixture fails loudly if chimol ever resolves
to a real settings directory again.

The fixture also had to move to **import time**: `_DISPLAY_CONFIG` is
module-level and loads while pytest collects, before any `autouse` fixture
runs. A session fixture is too late.

### Rules of thumb this left behind

* Before repointing a test at the panel, ask **what the deleted dock knew that
  nothing else does**. Two behaviours only existed inside that widget.
* Do not re-derive an implementation's formula in its test. The trajectory
  test compared against `stored[0:5].mean(axis=0)`, which encoded a boxcar
  window that has since become a clamped Bartlett one; it now asserts the
  *property* (displace the far end, the near end must not notice), which holds
  whatever the window's shape.
* `SequenceRow.colors` is float 0-1; the old dock's `QColor.getRgb()` was
  0-255. Scale, rather than weaken a threshold written in the other units.

### Panel equivalents for repointing

| the dock had | the panel has |
|---|---|
| `win.object_list.itemWidget(i)` | `gui.rows[i]` (`GuiRow`) |
| `widget.disclosure` / `widget.group` | `row.is_group`, `row.name` |
| `widget.check.isChecked()` | `row.enabled` |
| `widget.layout().contentsMargins().left()` | `row.indent` |
| `widget.buttons` | `gui._button_rects[i]` after `gui.layout(w, h)` |
| a `QAction` trigger | `gui._emit(entry.command, row.name)` |
| `win.seq_list` item colours | `gui.sequences[i].colors` (float 0-1) |
| a rebuild | `win.sync_internal_gui()` |

`gui.rows` includes the `all` header and `sele`; filter on `is_header`,
`is_selection`, `is_measurement`.



## The browser host, and what "1:1 with the desktop" costs

User: *"cm in browser: make demo look 1:1 like desk, still sele and mouse
clicks not landing only obj rot works."*

**The pick was never asked for.** `web/demo.py`'s `press` sent the pointer
either to the panel or to the trackball and had no third case, so every click
was consumed as a zero-length drag and `MolView.handle_mouse_click` was never
called from the page at all. Nothing had to be *written*: the page runs the
real `MolView`, its windowless renderer projects, and `renderer/picking` is
duck-typed (`x()`, `y()`, `modifiers()`). A press/release with a travel
threshold and a small event shim is the whole fix. `boot.js` already builds
the modifier mask from `chimol.host.events` values, so nothing translates.

### Why the rest of 1:1 is not a small change

`supported_features` is the measure (`chimol.testing.parity.HOST_FEATURES`).
The Qt-free desktop host `CanvasView` declares eleven; the browser now
declares six. Missing: **box_select, context_menu, double_click, resize,
wheel_modifiers**.

They are missing for one structural reason, and it is worth stating plainly:

```
CanvasRenderer(CameraState, Renderer)   <- owns on_pointer_press/move/release/wheel,
  CanvasView(CanvasRenderer)               the mouse-mode table, _BOX_ACTIONS,
  WgpuRenderer(widget, CanvasRenderer)     _CLICK_ACTIONS, CLICK_SLOP
SceneSink(CameraState, Renderer)        <- the browser's renderer: a SIBLING, not a child
```

Both desktop hosts inherit the whole event layer. `SceneSink` bypasses it, so
the browser hand-rolls a partial copy -- which is exactly why it had a click
tolerance of its own and no picking.

The fix is to re-base `SceneSink` on `CanvasRenderer`, and the obstacle is
that **`init_viewport` conflates input state with GPU setup**: it creates
`_internal_gui`, `_press_button` and `_right_dragged` *and* calls
`self._surface().get_context("wgpu")`, which a windowless renderer has no
surface for. Split it -- an input-state half the headless/browser hosts call,
a GPU half only a surfaced host calls -- and the browser gets all five
remaining features from the shared implementation rather than five more
hand-rolled copies.

Encouraging: the four handlers (`canvas_base.py` 1549-2050) reference
`_surface()` **zero** times. The split is real but shallow.

### Menu and CLI

Both already exist in the page -- `InternalGui` is constructed with
`sequence_visible`, the command line takes `cmd.do` and completions. What is
missing is the *input* to reach them: `context_menu` (a right press opening
the viewer's own menu) and `double_click` (the panel opens menus on one) are
two of the five features above, and `boot.js` sends neither. So the menu is
drawn and unreachable, which reads as "no menu".


## Desktop vs browser, photographed (2026-08-14)

**The comparison was blocked by a broken camera, not by the browser.**
`test/screenshot.py` finds the 3-D view with `findChildren(QOpenGLWidget)` and
captures it with `grabFramebuffer()`; the renderer is WebGPU, so it finds
nothing and falls back to `widget.grab()`, which returns a uniform grey
rectangle of the right size. Silent. See known-issues.

The working capture already existed and nothing used it:
`CanvasRenderer.grab_image(chrome=True)` renders the frame offscreen and
composites the panel -- one call, real pixels (29,804 distinct colours where
`shoot()` gave one).

**What the photographs showed.** Everything matched except two controls, and
they were the two the browser could not reach:

| control | desktop | browser (before) |
|---|---|---|
| menu bar (File..Help) | yes | **absent** |
| toolbar (Open..Tree) | yes | **absent** |
| sequence strip, Object List, Mouse block, command line | yes | yes |

**Cause, and it was already on this page as the next task.** `MENU_BAR` and
`TOOLBAR` are plain tuples of labels and command strings, and they lived in
`app/menu_bar.py` -- the Qt package, which a page cannot import. `InternalGui`
draws both whenever `gui.menubar` is filled and `menubar_visible` is already
`True` by default, so the page had nothing to draw. The toolkit-free desktop
host reached across the same boundary (`host/run.py` imported
`..app.menu_bar`), which is the same smell from the other side.

Fixed by splitting the file at its natural seam: `chimol/menus.py` holds the
data (523 lines, no Qt), `app/menu_bar.py` keeps `build_menu_bar`/`_populate`/
`_run` and re-exports the names so every caller is unchanged. Both hosts and
the page now read one source. Engine->`app/` edges: **2** (`cmd/base.py` is a
`TYPE_CHECKING` annotation; `cmd/volumes.py` -> `volume_panel` is the last real
one).

**A latent crash the move exposed.** `demos/catalog.py` computed its
sample-data path with `parents[5]` at *module import time*. That index only
exists five directories inside a ChiSurf checkout; in the browser bundle the
package is three deep, so it raised `IndexError` and took the whole page down
-- a traceback about a demo search path while the viewer was still booting. Now
computed in a function that returns `()` when the root is not there: a missing
sample directory degrades to "no samples", never to an exception.

## Injection beats a guarded import

User, on seeing `settings_dir.py` keep its `try: import chisurf`: *"why not
conf dir inject? chisurf inject conf dir in chimol."* Right, and it generalises.

A guarded import is the *tolerable* shape for a dependency that runs the wrong
way. It is not the correct one. `settings_dir.py` asked
`chisurf.core.settings` where to keep files and fell back to `~/.chimol` when
that raised. That worked, and it was wrong twice over:

* **Direction.** chimol is packaged to run where there is no ChiSurf. A module
  that names ChiSurf -- even guarded, even only in a fallback -- is one the
  move has to keep explaining away, and one more line on the allow-list that
  looks permanent.
* **Visibility.** Nothing on the ChiSurf side said "chimol keeps its settings
  with mine". The decision lived in chimol, which is the one place a reader of
  the *plugin* would not look.

So the host tells the engine. `chisurf/plugins/chimol/__init__.py` calls
`settings_dir.set_settings_dir(...)` at import -- the only moment the answer is
both known and correct -- and chimol names nobody. The allow-list lost an
entry rather than gaining an explanation, and `SOFT` is down to three.

Resolution order is `$CHIMOL_SETTINGS_DIR`, then the injected directory, then
`~/.chimol`. The environment winning over injection is load-bearing for the
test suite: importing the plugin package injects `~/.chisurf` as a side effect,
and the throwaway directory has to survive that.

**Apply this to what is left.** `analysis/ss.py` and `io/atoms.py` are the same
shape -- chimol asking ChiSurf for something the host could hand it. Before
guarding a new dependency, ask whether the host can inject it instead; a
guarded import should be the answer only when there is no host to ask, which
for a *plugin* is never.

## The package boundary moved (2026-08-13)

Six modules left `app/` -- the ChiSurf/Qt integration layer -- for the engine,
because none of them touches Qt and the engine had to reach *up* into `app/` to
use them:

| was | is | why it is engine |
|---|---|---|
| `app/picking.py` | `renderer/picking.py` | a projection and an `argmin`; the viewer calls it on every click |
| `app/command_dispatch.py` | `cmd/dispatch.py` | adapts chimol's command language to a console protocol |
| `app/command_history.py` | `cmd/history.py` | where the prompt's history file lives |
| `app/demo_catalog.py` | `demos/catalog.py` | now sits beside the `.pml` scripts it describes |
| `app/demo_data.py` | `demos/data.py` | generates the material demos run on |
| `app/cli.py` | `cli.py` | the REPL; see below |

`demos/` gained an `__init__.py` and `DEMO_DIR` became `parent` rather than
`parent.parent / "demos"` -- all ten demos still resolve.

Engine->`app/` edges went from ~11 to **three**: `cmd/base.py` (a
`TYPE_CHECKING` annotation), `cmd/volumes.py` -> `app/volume_panel.py`, and
`host/run.py` -> `app/menu_bar.py` for `MENU_BAR`/`TOOLBAR`, which are data and
should move next.

### The CLI was the interesting one

Moving it turned the seam test red, and the failure was worth having: `cli.py`
is **toolkit-free but ChiSurf-bound** -- `from chisurf.core.console import
dispatch` at module scope. The Qt audit could never have found it. Moving it to
the engine would merely have swapped a Qt dependency for a ChiSurf one, and
`HARD` would have stopped being empty.

The first fix was to put it back. The right one, on the user's instruction
(*"cli must be portable impl mecha to attach different repl"*), was to make the
routing **attachable**: `chimol/repl.py` owns the protocol -- `is_command` and
`is_incomplete_python` -- ChiSurf's console is attached when it imports, and
chimol carries the same rule on `codeop` for when it does not.

The fallback is not a stub, and that is the part a test has to hold down: it
implements the full rule (a line that compiles as Python is Python **unless**
its leading name is undefined), because the naive version -- "is the first word
a command" -- sent `set` to chimol's `set` rather than the builtin. Two
independent implementations of one rule drift, and when they do the same line
means different things depending on whether chimol was launched inside ChiSurf
or alone -- a bug that reproduces for one person and not the other. So
`test_repl_seam.py` runs both routers over a 15-line corpus and asserts they
**agree**, skipping where ChiSurf is absent, which is exactly the case the
fallback is for.

## `gui_overlay` moved to `host/`

`renderer/gui_overlay.py` -> `host/qt_overlay.py`. It opens a `QPainter`, and
`renderer/` is the half that has to run in a browser. Compositing chrome is a
*host* job: the Qt host paints it into an image, a browser host builds it as
quads. It could not go in `cmtk` beside `qt_painter.py` -- it calls
`refresh_gui_state`, and cmtk imports nothing from `renderer/`, a layering
worth keeping.

`renderer/` now has Qt in two files, both widgets (`view.py`, `wgpu_view.py`),
plus one docstring mention in `canvas_base.py`.


**Do the package boundary first — it is mechanical and it unblocks the rest.**
Eight `app/` files use **no Qt at all** (`cli`, `command_dispatch`,
`command_history`, `demo_catalog`, `demo_data`, `picking`, `volume_panel`,
`__init__`). That is engine code sitting in the Qt package, and it is why the
engine imports *into* `app/` in ~11 places (`cmd/loader` -> `demo_catalog`,
`host/app` -> `demo_data`, `cmd/volumes` -> `volume_panel`, `host/run` ->
`menu_bar`). Move those eight into the engine and most of the engine-to-shim
coupling dissolves without touching a line of Qt.

Only then is `app/` what its name says: the Qt shim, and the thing that stays
behind.

### Remaining, in the order to do them

1. ~~**HARD — one file left.**~~ **Done — see 5 above.** What that entry
   argued for is now the standing rule, per the user: *"chisurf should not own
   structures, only for opt exp data (inherit from chimol)"*. Structure data
   belongs to chimol; ChiSurf keeps what is specific to experimental/optical
   data and inherits or imports the rest **from** chimol. The next application
   of that rule was `atom_dtype`, still defined in both places and held in step
   by an equality test — a copy kept honest by a test is still a copy, and the
   dependency points the wrong way. It is now **vendored and inverted
   (2026-08-14)**: `chimol.io.atoms` owns `ATOM_DTYPE` unconditionally, and
   `chisurf.core.fio.structure.coordinates` imports it from chimol and
   re-exports `atom_dtype`/`keys`/`formats`/`keys_formats` (the DCD reader
   pattern). `test_engine_is_portable.py` now asserts identity (`is`) rather
   than equality, the allow-list lost `io/atoms.py`, and `SOFT` in
   `test_chisurf_seam.py` dropped it.

   Original entry, for the record: `analysis/elements.py` imports
   `chisurf.core.fio.structure.elements` at **module scope**, unguarded: the
   element tables. It is the only unconditional ChiSurf import left in the
   engine.

   The invariant says the fix is *not* another guarded fallback: chimol should
   **own** the element tables and ChiSurf import them from chimol. Same
   argument for `atom_dtype`, whose duplicated definition is currently held in
   step by an equality test — a copy kept honest by a test is a copy, and the
   dependency points the wrong way. Inverting both is the clean end state and
   the one the target architecture asks for.

   Separately: `io/structure.py` still needs a real DCD reader decision
   (vendor one, or inject one through a seam) before standalone chimol can
   open a trajectory at all. `okf/prds/prd-80.md` is retiring mdtraj in the
   same area — check it before choosing.
2. **`app/` (6 files)** — decide per module whether it moves or stays. Most of
   it is already scheduled for deletion by `HANDOVER_CHIMOL.md` §3.4 and
   [PRD-101](../prds/prd-101.md): *thirteen of sixteen `HOSTS` entries are
   `app/` panels drawing with Qt widgets what the in-viewport chrome already
   draws with quads*. Deleting them removes the dependency for free, so **do
   that refactor before deciding anything about `app/`**.
3. **The engine reaches into `app/`** — and this is the trap in the "app stays
   behind" plan: `cmd/volumes.py`, `cmd/loader.py`, `cmd/base.py`,
   `host/run.py`, `host/app.py`, `renderer/dbg_window.py`, `__init__.py` and
   `__main__.py` all import from `app/` (mostly lazily, mostly
   `demo_catalog`/`menu_bar`/`volume_panel`). The split is therefore **not**
   simply "engine moves, `app/` stays" — that coupling has to be inverted or
   the imported pieces moved into the engine first. Measure it again before
   committing to a boundary; `app/demo_catalog.py` was already staged for
   deletion by another instance while this was written.
4. ~~**Then move**~~ **Done (2026-08-14)**: the engine is `~/dev/chimol`
   (full history via filter-repo), the call sites say `chimol`, the symlink
   is `modules/chimol`, and `test_chisurf_seam.py` confirmed it was ready —
   green before and after the move.

## Counting it

```bash
pytest chisurf/plugins/chimol/test/test_chisurf_seam.py -q
```

17 tests. `test_the_engine_does_not_import_chisurf` is the one that answers
"is the move ready" — it asserts the engine's ChiSurf dependencies are exactly
`SOFT | HARD`, so severing one means deleting a name from `HARD` and watching
it stay green.

## See also

* [`HANDOVER_CHIMOL.md`](../../HANDOVER_CHIMOL.md) §3 — the refactor plan whose
  §3.4 (delete the Qt `app/` panels) is most of step 2 above.
* [PRD-101](../prds/prd-101.md) — one UI drawn in the viewport; the reason the
  `app/` panels are deleted rather than ported.
* [chimol-web](chimol-web.md) — the portability work (no Qt, no GPU binding at
  module scope) that made a toolkit-free engine possible in the first place.
