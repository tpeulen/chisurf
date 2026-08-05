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
the compiled C++ extensions, **IMP + IMP.bff** (`IMP` 2.24, `has_imp()` → True), and
mdtraj. Because IMP is present, the IMP-gated tests (the FRET plugin's
`refine`/`errors`/docking, `test_imp_engine.py`, `test_dock_project.py`) **run and
pass here** — a `skipif not has_imp()` test only skips on a machine that lacks IMP,
not in `arm64`.

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
"Can't combine branch coverage"). GUI/widget tests additionally need
`QT_QPA_PLATFORM=offscreen` and their own pytest process (mixing GUI and non-GUI
modules can segfault at Qt teardown).

# Test tasks

The pixi tasks wrap the above (CI uses pixi; they `build-extensions` first):

```bash
pixi run test           # non-GUI test suite (build-extensions first)
pixi run test-gui       # GUI/widget tests (-k 'widget or gui')
pixi run test-smoke     # fast smoke test (test/test_basic.py)
pixi run test-doctest   # doctests
```

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

`QMessageBox.critical(...)` spins its own event loop until a button is pressed.
Under `QT_QPA_PLATFORM=offscreen` — every headless suite, every CI job, every
screenshot script — no button can ever be pressed, so a dialog on an `except`
branch does not report the error: it **wedges the process**, and the traceback
is never seen. That is worse than a crash, because a hung run is
indistinguishable from a slow one. The fFCS filter-calculator module was hanging
this way and had to be diagnosed with `sample(1)` and
`faulthandler.dump_traceback_later`, which is the tell: if a suite stops
producing dots and no test has failed, suspect a modal dialog before suspecting
the machine.

Report through [`chisurf/gui/dialogs.py`](../../chisurf/gui/dialogs.py) —
`report_error` / `report_warning` / `report_information`. They log
unconditionally and raise the box only when `QGuiApplication.platformName()` is
a real window system, so interactive behaviour is unchanged. The same
`is_interactive()` predicate is the right guard for any modal built by hand:
"a `QApplication` exists" is *not* the same question as "a person is there".

`test/test_headless_dialog_seam.py` fails when a **new** file calls a raw
`QMessageBox` static from inside an `except` handler, tracking the remaining
ones in `test/headless_dialog_allowlist.txt` (the same allow-list-as-tracker
convention as the pyqtgraph seam). A confirmation prompt on a button click is
deliberately not flagged: there the user is right there, which is the point.

# A test that closes the main window writes the developer's own settings

`Main.closeEvent` calls `_save_window_state()`, which writes the dock layout to
`QSettings("ChiSurf", "MainWindow")` — the **real** user preferences. Anything
that closes the window therefore edits them, including `qtbot.addWidget(win)`,
whose teardown closes every widget it was given. A test run then silently
replaces the window layout the developer had, and the *next* run of that
supposedly isolated test restores it and measures the wrong window.

Redirecting `QSettings` is not enough, and on macOS the obvious redirect does
not work at all: `QSettings.setPath` **has no effect on the native format**, so
a script that sets it goes on reading and writing
`~/Library/Preferences/com.chisurf.MainWindow.plist` while looking isolated.
Two things that do work:

* In a test — patch `QtCore.QSettings` with a subclass that ignores the
  organisation/application arguments and opens an ini file under `tmp_path`,
  **and** neutralise `_save_window_state` on the instance in the fixture's
  finalizer, because `qtbot` closes the window *after* `monkeypatch` has put the
  real class back. `test/gui/test_dock_layout.py` does both.
* In a headless script — run it with `HOME` pointed at a scratch directory. The
  native store is resolved under `$HOME`, so this isolates reads as well as
  writes without touching the code under test.

The symptom to recognise: a layout/geometry test that passes alone and drifts
in a suite, or a "default layout" screenshot that quietly stops being the
default.

# GUI work is never blind — screenshot and look at it

**Any change that touches a GUI is unfinished until the widget has been rendered
and the rendering has been *looked at*.** Passing construction tests only prove
the widget did not crash; they say nothing about clipped labels, fields that
wrapped into a nonsensical two-column pairing, a status box that swallowed the
panel, a plot drawn upside-down, or a tab bar overlapping its content. Those are
the defects users actually report, and every one of them is invisible to
assertions and obvious in a PNG.

The loop, for every GUI change:

1. Build the widget headlessly in the `arm64` env with
   `QT_QPA_PLATFORM=offscreen` — no display needed.
2. Drive it into the state a user would see (load a real test file, run the
   analysis, switch to each tab) — an empty widget hides most layout defects.
3. `widget.grab().save(...)` into the scratchpad, then **read the PNG and inspect
   it**. The agent inspects it; do not hand PNGs to the user to eyeball.
4. Fix what looks wrong and repeat until it looks right. Resize once before the
   final grab — some layout artefacts only settle after the first real resize.

**A 3-D viewport needs a different shutter.** The offscreen platform cannot
create an OpenGL context at all — it says so, once, and then every grab of a
`QOpenGLWidget` is a black rectangle, which reads as a broken renderer rather
than a broken camera. A `QOffscreenSurface` under that platform does not help:
context creation still fails.

What works is the *ordinary* platform with `WA_DontShowOnScreen`. The window is
realised — real backing store, real GL context, everything renders exactly as a
user would see it — and is never mapped onto the display, so nothing appears and
nothing steals focus. `chisurf/plugins/chimol/test/screenshot.py` wraps it:

```python
from chisurf.plugins.chimol.test.screenshot import ensure_app, shoot

app = ensure_app()          # refuses QT_QPA_PLATFORM=offscreen rather than lying
paths = shoot(window, "npc_demo")   # {"window": ..., "view": ...}
```

`grab_window` composites the GL children in at their own geometry, because
`QWidget.grab()` renders the widget tree and does *not* read back a child GL
surface — a plain whole-window grab of a 3-D application comes out with a hole
where the interesting part is. It needs a logged-in session, so it is skipped
rather than failed where there is no window server.

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

# Citations

[1] [Project instructions (CLAUDE.md)](/references/claude-md.md)
