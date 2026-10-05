---
type: Subsystem
title: Retiring matplotlib from the runtime dependencies
description: What matplotlib was doing in the shipped tree (colours, static figures, two plots, LaTeX images), where each use goes instead -- emtk.colormaps, emtk.figure, chiplot, an emtk math typesetter -- and the shrinking allow-list that tracks it.
resource: test/matplotlib_import_allowlist.txt
tags: [dependencies, plotting, emtk, chiplot, colormaps, seam]
timestamp: '2026-10-05T00:00:00Z'
---

# Where to pick this up

The tracker is `test/matplotlib_import_allowlist.txt` (31 files at the start,
2026-10-05; the two console files are optional integrations, not entries); the guard is `test/test_matplotlib_seam.py` (no new importer, no
stale entry, console integrations import only inside functions). Open front,
in order:

1. **figure route, remaining files.** Each is a mechanical port to
   `emtk.figure` once a before-PNG is taken with the matplotlib code: render
   the result with realistic data, `savefig`, port, re-render, compare the
   control inventory (see "How a figure port is proven" below). Files:
   `gui/widgets/wizard/tttr_channeldefinition/lut_thumbnail.py`,
   `plugins/burst/burst_h2mm/gui/native.py`, `plugins/tttr/audifier/{core,lifetime_analysis}.py`,
   `plugins/tttr/trace_browser/gui/model.py`, ndXplorer
   `export/{publication_figure,report}.py`. ndXplorer's publication figure
   uses `LogNorm`/`Normalize` and figure-level layout -- check `emtk.figure`
   covers it (log colour scale on `heatmap` is not there yet) before porting.
2. **plot route.** `plugins/fluorescence_decay/lltf/{core/fitter.py,lltf_gui.py}`:
   a Qt `FigureCanvasQTAgg` inside a legacy Qt tool and a module-scope pyplot
   in the fitter. The GUI half goes to `chiplot.Plot`; the fitter's plotting
   belongs out of the fitter.
3. **math route -- the hard one, needs a design, not a port.** Five files
   render LaTeX to an image with matplotlib's mathtext:
   `gui/widgets/{equation_editor,expression_input,general}.py`,
   `plugins/core/help/{api/mathtext.py,gui/help_app.py}`. **emtk.mathtext is
   not an alternative today**: it is itself a front end to matplotlib's
   mathtext with a Unicode fallback (`latex_to_unicode`). What is missing is a
   small TeX box-layout typesetter in emtk drawing glyphs from emtk's atlas:
   fractions, sub/superscripts, square roots, big operators with limits,
   stretchy delimiters, accents, `\text`. The atlas already covers Greek and
   the math symbols (checked: `∈ ≤ ≥ ± × → ∞ ≈ ∑ √` all `covers()`); what is
   missing is layout. Do it as an emtk module with golden tests against
   matplotlib's renders, then route the five callers. Until then those five
   stay on the list.
4. **delete route.** `core/structure/potential/database/make_unres_lookup.py`
   is a developer script with a module-scope pyplot inside the package --
   move it to `build_tools/` or delete it.
5. **Manifests.** When the list is empty: drop `matplotlib-base` from
   `pixi.toml` `[dependencies]` (keep it in the `test` and `docs` features --
   `docs/guides/make_figures.py` draws the guide figures with it), drop
   `matplotlib` from `rattler-recipe/recipe.yaml` `run:` and from
   `modules/ndxplorer/pyproject.toml`, and add it to `RETIRED` in
   `test/test_no_retired_dependency_imports.py`.

Not in scope here and left as found: `tttr_photon_filter_plots.py` still
imports pyqtgraph directly (its colour parse is routed). Its consumer is the
Qt burst-selection wizard, which the BURSTEMTK lane is replacing with a native
emtk app; porting the plots inside another lane's claim would conflict.
`BurstWorkflow.recurrence()` raises on the demo simulation's burst table (no
proximity-ratio column); the RASP plot was proven on a `Recurrence` built
directly.

# Why

The owner asked (2026-10-05): "try to get also rid of matplotlib, do not
understand what for it is needed." Measured, the answer was four things, none
of which needs matplotlib:

| Use | Files at start | Goes to |
|---|---|---|
| Colour tables, colour-name parsing | 12 | `emtk.colormaps` |
| Static figures written to a file | 11 | `emtk.figure` |
| Interactive plots in a GUI | 2 | `chiplot.Plot` |
| LaTeX rendered to an image | 5 | an emtk math typesetter (to build) |
| Developer script in the package | 1 | delete / `build_tools/` |

Plus the console's `%matplotlib` support, which is not a dependency: it
serves the **user's own** matplotlib code, imports it inside functions, and
since 2026-10-05 says "matplotlib is not installed" instead of raising when it
is absent. It is listed in the guard's `_OPTIONAL_INTEGRATIONS`, not the
allow-list.

# The two new homes

**`emtk.colormaps`** (emtk `363e58e`, `66dae85`): 104 colour tables in one
generated JSON (`tools/build_colormaps.py`) -- viridis family, turbo, the CET
maps, pyqtgraph's palettes, the classic and ColorBrewer maps -- with
matplotlib's lookup semantics (float `x` -> entry `int(x*N)`, integer ->
index, NaN -> transparent) so ported code keeps its pictures, and
`to_rgba`/`to_rgb`/`to_hex` for CSS4 names, one-letter, `C0..C9`, hex and
0..1 or 0..255 tuples. No dependency; numpy used when present. ndXplorer's
copy of pyqtgraph's map files is gone -- it reads emtk's tables and keeps its
own pyqtgraph-exact interpolation. **cividis** is pyqtgraph's published table,
which differs from matplotlib's by up to 0.09 per channel; that is pinned by a
test, not a bug. **Quantise half up** when regenerating: `round()` is
half-to-even and moved two CET-L9 entries by one step against pyqtgraph.

**`emtk.figure`** (emtk `0d6dee0`, `81bdc8e`, export option `e0705be`): a
`Figure`/`Axes` recorder of a small plotting vocabulary drawn by implot on
the CPU rasteriser -- no window, GPU, Qt or matplotlib -- for pictures an
application *writes*. `ax.figure.save("x.png")`; Jupyter shows `Figure` and
`Axes` inline (`_repr_png_`). It lives in emtk, not chiplot, because
`chisurf.gui` imports Qt on import and the callers include the Qt-free server,
agent tools and `api/` modules. chiplot stays the API for plots *in* a GUI.
Three traps found building it, each now handled in emtk:

- **Render through an `ImApp`.** A bare gui callable keeps no state between
  frames, so every frame is a first frame: no y-axis label is drawn and a
  `vspan` sizes itself to the default 0..1 limits.
- **Set plot colours through implot's setter** (`_style_colors`); raw tuples
  written into `style.colors` lose the rotated axis label.
- **Fit padding.** implot fits data exactly to the frame; matplotlib pads 5%.
  Without it an IRF spike at t=0 vanished into the axis.

`painter="pil"` on `emtk.export` draws the same picture with Pillow's inner
loops: a 900x600 four-panel figure 6.6 s -> 2.0 s.

# How a figure port is proven

Before touching the code, render every figure the file produces with
realistic data through the matplotlib path (`savefig`) -- the burst workflow
used `BurstWorkflow.demo()` + `simulate()` -- then port, render the same data
through `emtk.figure`, and compare the **control inventory**, not pixels:
every series, label, legend entry, span, tick name, colour bar and annotation
of the before-image present in the after-image. Write down deliberate
differences. Burst workflow (2026-10-05): all nine plots at parity; deliberate
differences -- transition-matrix tick labels are horizontal (implot does not
rotate tick text) and its colour bar now has a "1/s" label; state-population
labels sit a fixed 10 px above the bar.

# Found on the way (not matplotlib's fault, all pre-existing)

- **Two of the plots had never drawn.** `plot_fcs_maxent_result` used
  `r"$\\tau$"` labels -- a literal double backslash, which mathtext rejects
  with a `ParseException`; nothing called it, so nobody saw. The IRF guide's
  diagnostics example called `run()` and then plotted: `run()` hands the whole
  estimate to the photon library's engine and keeps none of the step
  pipeline's intermediates, so `plot_raw_and_fit` raised "Run
  generate_data_fit() first". The guide now shows the step pipeline the plots
  need. Whether `run()` should expose `t0/t1/params/kernel` from the engine is
  open (it would let the diagnostics follow `run()` again).
- **chitable's value colouring had silently lost its colormap.** Both of
  `resolve_lut`'s paths were dead -- pyqtgraph's `colormap.get` and
  matplotlib's `cm.get_cmap` (removed in 3.9) -- so every name fell back to
  the HSV ramp. It now gets the real table from `emtk.colormaps`.
- **`fcs_maxent` fits `G(tau)` with `G(inf) = 1`**: a curve normalised to
  decay to 0 gives a flat fit and a near-zero `P(tau_D)` with no warning.

# Done

- 2026-10-05 seam (33 files), colormap route (12 files), burst workflow
  figures (`plugins/burst/burst_analysis/api/workflow.py`). 31 -> 18 (the
  first commit's message says 33 -> 20: it counted the two console files).
- 2026-10-05 `core/models/fcs/maxent.py`, `core/fluorescence/tcspc/irf_estimation.py`,
  `core/agent/tools/decay.py` (`plot_fit`; now refuses a non-PNG path instead of
  guessing a format). `emtk.figure` gained hidden cells, row/column ratios and
  aligned panels (emtk `85bf146`) for them. 18 -> 15.
