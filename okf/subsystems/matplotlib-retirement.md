---
type: Subsystem
title: Retiring matplotlib from the runtime dependencies
description: What matplotlib was doing in the shipped tree (colours, static figures, two plots, LaTeX images), where each use goes instead -- emtk.colormaps, emtk.figure, chiplot, an emtk math typesetter -- and the shrinking allow-list that tracks it.
resource: test/matplotlib_import_allowlist.txt
tags: [dependencies, plotting, emtk, chiplot, colormaps, seam]
timestamp: '2026-10-05T00:00:00Z'
---

# Where to pick this up

Allow-list `test/matplotlib_import_allowlist.txt`: **31 -> 4** (2026-10-05/06),
guard `test/test_matplotlib_seam.py`. Routes done: **colormap** (all 12, via
`emtk.colormaps`), **delete** (1), **figure** (all but the two below, via
`emtk.figure`). Open, in order:

1. **trace browser DOCX picture -- DONE 2026-10-06.** The cause was not
   nesting: the export runs on a job thread (`chisurf/emtk/jobs.py`), and
   `emtk.figure` swapped implot's `gp` and im's current context (process
   globals) while the GUI thread was mid-frame. emtk `a89dc09` adds
   `im_core.FRAME_LOCK`, held by every `frame()` and by `figure._isolated()`;
   the port is re-applied and `test_emtk_trace_browser_t4.py -k docx` is green
   (3/3). Before/after picture on BH_SPC132 (ALEX): same title, labels,
   legend, channels. **Rule for any off-thread emtk drawing: it goes through
   `frame()`/`emtk.figure`, never a hand-made Context.**
2. **ndXplorer publication figure -- DONE 2026-10-06** (ndxplorer `88318a6`,
   emtk `0797f09`). emtk gained `SvgPainter`/`PdfPainter`
   (`emtk/vector_painter.py`: text laid out with the atlas exactly as
   PixelPainter does; SVG pins `textLength`, PDF uses base-14 Courier +
   Symbol, nothing embedded), `ScaledPainter` for `png_bytes(dpi=)`,
   `Axes.mesh` (pcolormesh over arbitrary edges, LogNorm) and log colour bars.
   Grid rows now align **per column** -- one alignment group across the grid
   had squeezed a y-marginal and its colour bar to negative width on the kept
   frame. Before/after inventory: all controls present; the colour bar moved
   into the right marginal's cell. ndXplorer no longer declares matplotlib nor
   ships it to Pyodide. Known gap: `transparent=True` is accepted but the
   figure is drawn on white paper. Checking a vector file by eye: `rsvg-convert`
   (SVG) and `sips` (PDF) render them independently of emtk.
3. **plot route**: `plugins/fluorescence_decay/lltf/lltf_gui.py`, legacy Qt
   `FigureCanvasQTAgg`. Another lane is building the emtk LLTF app
   (`lltf/gui/app.py`); the Qt wizard goes with it. Do not port in parallel.
4. **math route -- engine DONE 2026-10-06; 3 callers left.** emtk `e1e04d5`
   (+ `11d64c4`, sans) adds `emtk/tex.py`, a TeX box-layout typesetter
   (scripts, fractions, roots, grown delimiters, big operators with limits,
   accents on ink, font commands, math alphabets, under/overset) drawing
   FreeType glyphs through Pillow; `emtk.mathtext.render_math_to_texture` uses
   it, so emtk itself no longer needs matplotlib. Coverage measured: all 2005
   formulas in `docs/` + help pages (after `normalise_latex`) typeset; 32 of
   the most complex checked side by side against matplotlib's renders. The
   help viewer (`help/api/mathtext.py` MathRenderer, `help/gui/help_app.py`)
   is ported. **Left:** `gui/widgets/{equation_editor,expression_input,
   general}.py` -- each builds a pyplot figure only to draw one formula; swap to
   `emtk.tex.render_rgba` (white background) and screenshot the editor before
   and after. Traps: Pillow's `getbbox` clamps an accent's ink bottom to the
   baseline (use the mask, `tex._ink`); STIX Two Text has no bold face.
5. **Static exports go through emtk.figure, not chiplot**: `chisurf.gui`
   imports Qt, and callers include Qt-free api/server/agent code. chiplot
   stays the API for plots *inside* GUIs.
6. **Manifests** once the list is empty: drop `matplotlib-base` from
   `pixi.toml` `[dependencies]` (keep it for `test`/`docs` --
   `docs/guides/make_figures.py`), `matplotlib` from the recipe `run:` and
   `modules/ndxplorer/pyproject.toml`; add it to `RETIRED` in
   `test/test_no_retired_dependency_imports.py`.

Trap when committing here: the tree is shared and most of these files carry
other lanes' edits. Save `git diff <file>` before editing, stage via a temp
`GIT_INDEX_FILE` with `git merge-file` (HEAD, HEAD+foreign, working tree);
where hunks overlap, stage HEAD with only your function swapped in. One
concurrent commit in ndXplorer took this lane's content under another
session's message (`ea40470` = the report port).

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
- 2026-10-05 `gui/widgets/wizard/tttr_channeldefinition/lut_thumbnail.py` (tooltip
  thumbnail; needed `line(..., right=True)`, emtk `figure: lines on a right-hand
  y-axis`). Text is relatively larger at 240 px than matplotlib's 6 pt ticks;
  legible, inventory at parity. 15 -> 14.
- 2026-10-05 `make_unres_lookup.py` moved to `build_tools/dev_utils/` (it ran a
  plot window and wrote `unres.npy` into the CWD on import); preview plot
  dropped; regenerates the shipped table bit-identically. 14 -> 13.
- 2026-10-05 audifier `plot_waterfall` (returned None after `plt.show()`; now
  returns the panel). Grid lines show through heatmap cells, unlike an
  `imshow` -- cosmetic, noted. 13 -> 12.
- 2026-10-05 ndXplorer folder reports (`export/report.py`): 1-D, 2-D and
  2-D-with-marginals renderers at parity. **Its commit is ndXplorer `ea40470`,
  whose message is another session's** (a concurrent commit raced on the
  message file; the content is only `report.py`). 12 -> 11.
- 2026-10-05 lltf fitter (`core/fitter.py`): its module-scope pyplot import is
  gone; the scan's figures land on `decay.figures` instead of blocking windows;
  `plot(filename)` writes the PNG. The decay panel's y range now follows the
  data -- the IRF's Gaussian tails used to flatten the decay at the top of a
  1e-300 axis. The fit-information box became the panel title. 11 -> 10.
- 2026-10-05 H2MM native app's `save_plot` (2x2 result PNG), rendered through
  its click test before/after; a name without `.png` gets the suffix. Fit
  padding fixed in emtk (`6df5352`): implot pads by a fraction of *half* the
  range, so 0.1 is matplotlib's 5% a side. 10 -> 9.
- 2026-10-05 audifier lifetime waterfalls (single and multi-channel). **Both
  had drawn lifetimes in the wrong place**: the log-spaced tau grid was spread
  linearly by `imshow` and then given a log axis, so a 1 ns peak showed near
  30 ns. Now columns are uniform in log10 tau with decade ticks. Also fixed: the
  colour-bar label typo ("log₁₁" -> ln(1 + counts)) and the multi-channel
  colour bar overlapping the panels (one bar per panel, shared levels). A
  heatmap panel now fills its frame (emtk `fdaafdd`). 9 -> 8.
- 2026-10-05 trace browser's DOCX trace picture (`_render_trace_png`), at
  parity on BH_SPC132. 8 -> 7. **Reverted** (see Where to pick this up, 1):
  7 -> 8.
