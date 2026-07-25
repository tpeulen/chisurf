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

Two practical notes: the offscreen platform refuses to create an OpenGL context,
so a GL viewport must be grabbed under `cocoa` with an offscreen surface instead;
and interactive behaviour (a dragged ROI, a picked point) is verified by driving
the signal programmatically and asserting the model changed, not by looking.

Screenshots that end up in `docs/guides/` are produced the same way from the real
widget — see `docs/guides/make_screenshots.py` — never as mockups.

# Citations

[1] [Project instructions (CLAUDE.md)](/references/claude-md.md)
