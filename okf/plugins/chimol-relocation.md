---
title: ChiMOL moves to its own repository — sever first, move second
status: in-progress
group: plugins
updated: 2026-08-13
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

## Where to pick this up

The chimol suite is **green**: 3909 passed, 38 skipped, no segfault. All
eighteen failures the crash had been hiding are resolved.

The open front is the relocation itself, in this order:

1. **`MENU_BAR`/`TOOLBAR` out of `app/menu_bar.py`.** They are data, and
   `host/run.py` -- the toolkit-free host -- imports them from the Qt package.
   One of the three remaining engine->`app/` edges, and the only one that is
   pure movement. (The others: `cmd/base.py` is a `TYPE_CHECKING` annotation
   and costs nothing; `cmd/volumes.py` -> `app/volume_panel.py` is real, and
   `volume_panel` stays behind because it resolves an AutoForm view spec.)
2. **The twelve Qt-widget files to the shim** (see the widget rule above).
   `cmtk/qt_painter.py`, `host/qt_overlay.py` and `testing/mock_viewer.py` are
   *not* among them -- they use no `QtWidgets`.
3. **Retarget `test_qt_seam.py` at `QtWidgets`** rather than at Qt as a whole.
   That is the property that decides whether chimol runs in a browser; the
   current check over-reports by flagging painting-only modules.
4. **The move**: `git mv` to `~/dev/chimol`, `git init` (no remote), rewrite
   the `chisurf.plugins.chimol.chimol` -> `chimol` call sites, symlink into
   `modules/`.

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
   of that rule is `atom_dtype`, still defined in both places and held in step
   by an equality test — a copy kept honest by a test is still a copy, and the
   dependency points the wrong way. Vendor it the same way the element table
   was vendored, then have ChiSurf's `coordinates.py` take it from chimol.

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
4. **Then move**, and only then: `git mv`, rewrite `chisurf.plugins.chimol.chimol`
   → `chimol` at the ~20 ChiSurf call sites (already the correct direction —
   `renderer.view` ×6, `cmtk` ×4, `io.rmf`, `io.structure`, `config`), add the
   symlink, and let `test_chisurf_seam.py` say whether it was really ready.

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
