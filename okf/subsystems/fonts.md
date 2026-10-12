---
type: Subsystem
title: Fonts and magnification
description: One font configuration (emtk.fonts) for every text role of the emtk window -- interface, code, documentation prose and headings, formulas, captions -- plus interface zoom, glyph oversampling, anti-aliasing and fallback chains; Settings → Fonts stores it in gui.fonts and applies it live.
resource: chisurf/plugins/core/setup/gui/fonts_app.py
tags: [gui, emtk, fonts, settings, accessibility, autoform]
timestamp: '2026-10-12T00:00:00Z'
---

# Where to pick this up

1. Measure: **a change the way it was verified.** The scratch drivers used on
   2026-10-12 render the real shell on the GPU offscreen (`emtk.testing_realistic.HostedDriver`,
   `scale` 1 and 2): open the Console and the Documentation dock, then set
   `FontSettingsModel(persist=False).ui_size / zoom / code_family / prose_size` and
   `drv.screenshot(...)` after ~15 frames. Read the PNGs; `clipped_texts(drv.painter)`
   lists text cut by a clip. **Trap:** a `RealisticDriver(real_painter=False)` measures with
   the screenshot painter, which ignores the interface size -- a font test must use the real
   painter (the default) or it sees no change at all. Second trap: a script run outside the
   emtk checkout imports the *installed* emtk; reinstall (`pip install --no-deps
   --force-reinstall git+file://…@<rev>`) before judging.
2. Open: **the Qt shell has no font settings.** `--qt` keeps `gui.application_font_size` (Qt
   points; 13 is not 8 emtk points). Only its console takes a *named* face from
   `gui.fonts.code` (`chisurf/core/console/settings.py`). Mapping sizes between the two point
   systems was not attempted: Qt is legacy.
3. Measure: **zoom lives in `emtk.app.ControlSurface`** (and `OverlaySurface`, the test drivers).
   The Qt-hosted surfaces (`emtk.qt_host.ControlHost`, `emtk.wgpu_host` Qt canvas) follow
   font changes live (`fonts.generation()`) but **do not zoom** -- nothing in the emtk shell
   uses them; a Qt-hosted emtk panel in the `--qt` window stays at 1.0.
4. Open: **the `zoom_125` click-all variant (800 × 600, magnification 1.25) equals a 640 × 480
   window.** Measured 2026-10-12 on a 12-plugin sample (`CHISURF_E2E_MATRIX=sample
   CHISURF_E2E_MATRIX_SAMPLE=12 pytest test/e2e/test_click_all_plugins.py -k "real_use and
   zoom_125"`) and re-run on the six failures with a temporary unzoomed 640 × 480 realistic
   variant: **the same findings, item for item**, so the zoom is faithful and what remains
   are small-window defects of those tools, not of the fonts: `accurate_fret`,
   `burst_irf_bg` ("could not reveal 'Read'"), `burst_analysis` (navigation list
   "IRF & Background" off screen with no scroll), `microtime_shifter` (plot "A" outside its
   plot; fold clicks after a plot menu do not land), `tttr_toolbox` (clipped "Register
   shifts in MMFDB"), `setup` (Channel Definition's "Add all channels to setup" clipped; at
   zoom also one "❓ Help"). **Trap:** the harness measured visibility against
   `driver.size`; under a zoom the layout box is smaller -- it now asks `_layout_size(driver)`
   (the surface box). Fixed on the way: the Fonts form now scrolls in a short dock (it had
   no scroll route), the documentation toolbar's A− / Reset zoom / A+ wrap as a group
   (`help_app.py`), emtk headers / tree rows / selectables end in "…" instead of being cut
   mid-letter (emtk `334c83c`), and a realistic screenshot is the GPU's own frame at device
   size with the zoom applied (emtk `7bffd4f`; it used to replay the app's box at scale 1).
   Dock tab strips scroll rather than fit ("Plot set…" behind ◀ ▶) by design.
5. Blocked: **hinting is not offered.** FreeType through Pillow exposes no hinting control; adding it
   means a different rasteriser, not a setting. The baked interface face (`monospace`) is a
   fixed bitmap: oversampling and anti-aliasing apply to installed faces only.

# What it is

`emtk.fonts` (emtk `136d300`) is one `FontConfig`: per role -- `ui`, `code`, `prose`,
`heading`, `math`, `caption` -- a family (a name, a generic `monospace`/`prose`/`sans-serif`/
`serif`, or a comma-separated **fallback chain**), a size in points (`0` follows: the
interface size, or the prose size by the type-scale steps for headings and captions) and
bold; plus `zoom`, `oversample`, `antialias`, `heading_step` and global `fallbacks`.
`fonts.apply()/update()` clear the glyph, layout and formula caches and bump
`fonts.generation()`, which every host compares to rebuild its painter: a change shows on
the next frame, no restart. `FontConfig.to_dict()/from_dict()` round-trip a plain dict and
clamp a hand-edited one; a family that is not installed falls back to the role's default,
so a settings file from another machine never stops a window drawing.

The type scale (`emtk.type_scale`, see [documentation browser](documentation-browser.md))
reads faces, own sizes and the heading step from it; the defaults reproduce the previous
look exactly (8 pt baked interface face, Verdana/DejaVu Sans prose, 1.125 step). The
`TextEditor` draws in the `code` role unless its host pushed a font of its own (the code
editor plugin's own picker wins when set; its defaults follow the role). A role's own chain
is tried for a missing glyph before the system coverage faces
(`emtk.dynamic_font.FONT_CANDIDATES`).

# In ChiSurf

* **Settings → Fonts** (`chisurf/plugins/core/setup/gui/fonts_app.py`, `fonts.view.json`,
  `fonts_model.py`, `fonts_guide.json`, `fonts_help.md`): an AutoForm spec over
  `FontSettingsModel`; every setter calls `fonts.update` and saves the whole block to
  `gui.fonts` (`chisurf/core/settings/fonts.py`). The only hand-drawn part is the preview
  line per role (a `custom` section `font_preview` with `source` = role).
* **Startup:** `chisurf.emtk.main_app.main` calls `apply_stored()` before the first window.
* **Defaults:** the packaged `gui.fonts` block in `settings_chisurf.yaml` equals
  `FontConfig()`; `test_defaults_are_the_shipped_look` guards it.
* **Tests:** emtk `tests/test_fonts_config.py` (widths linear in size, caches dropped,
  fallback chain wins, dict round trip, zoomed click lands); chisurf
  `chisurf/plugins/core/setup/test/test_emtk_fonts_panel.py` (typed sizes, magnification,
  Reset, startup apply, console face); click-all variant `zoom_125`.
* **Docs:** [Settings and fonts](../../docs/getting_started/settings.md).
