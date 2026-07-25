---
type: PRD
prd: "67"
title: "PRD-67: Two-Channel Image Colocalization"
description: A colocalization plugin for multi-channel microscopy images — Pearson/Manders/Costes/Li coefficients with automatic thresholds and a randomization significance test — over one shared image-source seam that reads both camera image stacks and photon-stream (confocal-scan) files.
status: done
phase: "feature track"
resource: chisurf/plugins/microscopy/img_coloc/
tags: [prd, imaging, microscopy, colocalization]
timestamp: '2026-07-25T00:00:00Z'
---

# Summary

Colocalization analysis — "do these two labelled species occupy the same
structures?" — was the one standard multi-colour imaging question ChiSurf could
not answer. This PRD adds it as an imaging plugin with the full established
coefficient set (Pearson, Manders overlap and split fractions, Costes automatic
thresholds and randomization significance, Li's ICQ, Spearman, van Steensel's
shift profile), an interactive intensity-scatter gate, and both a CLI and a
Qt-free API.

It also closes a structural gap the feature exposed: every imaging plugin so far
could only read **photon streams**, because image loading was fused into the
per-pixel CLSM pipeline. Colocalization is routinely done on camera images, so
loading is now its own seam, returning the same `(frame, channel, y, x)` stack
for a TIFF hyperstack and for a confocal scan reconstructed from a photon
stream. Any later multi-channel pixel analysis reuses it instead of re-deciding
how to read an image.

# Status

**Done — and audited feature-complete against both reference
implementations** (see [Parity audit](#parity-audit)). Coefficients, image-source
seam, plugin (core/CLI/GUI), the detector-setup workflow, painted ROI, 2-D
cross-correlation plane, intensity-resolved PCC profiles, eight reusable AutoForm
additions, the in-app `?` help, the concept + guide documentation pair, and 29
headless tests landed. Follow-ups are listed under [Deferred](#deferred).

Related: [PRD-40](prd-40.md) (AutoForm), [PRD-51](prd-51.md) (imaging
correlation), [PRD-52](prd-52.md) (phasor imaging), [PRD-49](prd-49.md)
(multiparameter-fluorescence parity).

# Motivation

The reference survey of the established imaging-analysis suite
([quickfit3-mining](/references/quickfit3-mining.md), item 11) scored a
colocalization plugin at value 4/5 as a **clear gap**: no correlation metrics, no
scatter-plot UI, no automatic thresholding anywhere in ChiSurf. It is the
standard validation step for any multi-colour experiment, and every imaging user
already has the data for it.

The reference implementation offers Pearson's coefficient, Manders' overlap
coefficient, a 5 %-quantile background estimate, and a rectangle gate in the
scatter plot. That is the *interaction* worth copying but not the *coefficient
set*: the field's practical guide (Dunn, Kamocka & McDonald 2011, Am. J. Physiol.
Cell Physiol. 300:C723) treats Manders' split fractions, Costes' automatic
thresholds and Costes' randomization test as the minimum defensible reporting
set, because raw Pearson/MOC values are background- and threshold-dependent and
therefore not comparable between images. ChiSurf implements the full set.

# Scope

## Coefficients (`core/fluorescence/imaging/colocalization.py`)

Qt-free NumPy implementations, reimplemented from published formulas (documented
prior art, no code copied):

- **Pearson's PCC** — covariation of the two channels, reported over all pixels
  and over the thresholded selection.
- **Manders' overlap coefficient (MOC)** — co-occurrence without mean
  subtraction.
- **Manders' split coefficients M1/M2** — the fraction of each channel's
  intensity lying in pixels where the other channel is present; the pair of
  numbers PCC cannot express.
- **Costes' automatic thresholds** — orthogonal (total-least-squares) regression
  of the channel pair, then a descending scan along that line, bracket-refined by
  bisection, to the highest threshold pair whose below-threshold pixels are no
  longer positively correlated. Removes the hand-chosen threshold, the single
  largest source of irreproducibility in reported coefficients.
- **Costes' randomization significance test** — one channel is scrambled in
  PSF-sized blocks (preserving the intensity distribution and local texture,
  destroying the spatial relation) to build a null distribution for PCC;
  reproducible via an explicit seed.
- **Li's ICQ** — sign agreement of the two channels' deviations from their means,
  in `[-0.5, 0.5]`; distribution-free.
- **Spearman rank correlation** — monotonic-but-non-linear channel relations.
- **van Steensel's CCF** — PCC versus horizontal shift; a peak away from zero
  exposes a registration/chromatic offset rather than true colocalization.
- **Joint histogram** — the 2-D intensity scatter, plus a rectangular gate in
  that plane yielding its own gated coefficients and pixel mask.

## Image-source seam (`core/fluorescence/imaging/image_source.py`)

One `load_image_stack(path)` returning an `ImageStack`
(`data (frame, channel, y, x)`, `channel_names`, `kind`, `metadata`):

- **Camera / TIFF images** — axis order taken from the file (ImageJ hyperstack
  metadata / TIFF series axes) rather than guessed; `C`/`S` axes are channels,
  `T`/`Z` frames. A single unlabelled axis is genuinely ambiguous and is resolved
  by a documented short-axis heuristic the caller can override (`channel_axis`);
  the GUI exposes it as an "Axis order" selector.
- **Photon streams** (`.ptu`, `.ht3`, …) — a confocal-scan image per detector
  routing channel, or per named detector window (so a micro-time/PIE-gated window
  is a "colour" like any other), reusing the existing cached CLSM fills.

## Plugin (`plugins/microscopy/img_coloc/`)

- `core.py` — the single `compute_colocalization()` entry the GUI, CLI and tests
  share, plus the ordered presentation table.
- `cli/` — `img-coloc FILE -a ch0 -b ch1 …`, text or JSON output, every knob
  exposed (headless path per the project's headless-mode rule).
- `gui/` — AutoForm over a Qt-free `ColocViewModel` with an authored
  `coloc.view.json`: a Settings dock (source, channel pair, frame,
  background/thresholds, gate, significance/profile options) beside a tabbed view
  dock (coefficient table, both channel maps, the colocalized-pixel mask, the
  intensity scatter, the van Steensel profile). Compute runs on a worker thread;
  the host is a `ChisurfDockTool` with file drops and a Run / Estimate-background
  / Export-CSV toolbar.

## Shared AutoForm additions

Everything the tool needed beyond the existing sections was added as a *general*
capability, authored in JSON and available to every plugin:

- **`setup_selector` section** — the detector-setup picker every photon-stream
  tool used to embed in hand-written Qt is now declarative. It writes the setup
  name to a model attribute and calls the established `apply_setup_settings`
  hook with `{"name", "detectors"}`, so a view-model needs no extra glue.
- **`image` section: `rect_roi_call` / `rect_roi_source`** — a draggable,
  resizable rectangle on any image reporting its bounds to the model.
  Colocalization uses it as the scatter gate; anything needing a 2-D region
  (histogram gating, ROI cropping) now can.
- **`image` section: `invert_y`** — images that are really plots (a 2-D
  histogram) read bottom-up instead of following the top-left image origin.
- **`table` section: `expand`** — a table fills its panel/dock instead of
  leaving dead space below its rows.
- **`info` section: `max_height`** — a short live status line can no longer grow
  into the panel's spare space.
- **`image` section: painted-ROI reuse** — the existing brush option now backs a
  spatial region of interest, so the analysis can be restricted to a hand-drawn
  area without any bespoke Qt.
- **`help` section: view-relative `resource`** — a relative help file is resolved
  next to the view spec that declares it (the model's `_view_json`, else the
  model's module directory), so a plugin ships its `?` modal text beside its
  `view.json` instead of inlining Markdown into JSON.
- **`data_source` section** — the one-file counterpart of `path_list`: a path
  field plus **browse**, **database** (the shared MMFDB dataset picker, which
  resolves the artifact to a *local* path so object-store/S3 access stays inside
  the database) and drag-and-drop, bound to one model attribute. Every tool's
  "which measurement do I analyse?" control is now one declarative section rather
  than a plain file field that can only see the local disk.
- **`ChisurfDockTool.add_toolbar_help()`** — a right-aligned `?` in the tool's own
  toolbar opening the same modal. Long help never occupies panel space, and live
  status goes to the status bar rather than an inline text block.

The plugin-catalogue generator was taught to document bound custom sections
(their `attr`/`label`/`description` live in `options`), so a tool that uses these
sections keeps a complete per-parameter table.

## Workflow: setup → file → channels → coefficients

Colocalization is a *channel-pair* question, and in ChiSurf channels are named
detector windows, not routing-channel numbers. The tool therefore follows the
same order as the rest of the imaging stack: pick a **detector setup** (its
windows — green / red / yellow — become the pickable channels *before* any file
is read), load the **image**, pick the **pair**, then set background/thresholds.
For a camera image the setup does not apply and the file's own channels are used;
the view-model decides that per file, so one tool covers both worlds.

## Documentation

Per the [change-tracking rule](/workflows/change-tracking.md), the plugin is
documented in **theory** (`docs/concepts/colocalization.md` — what each
coefficient measures, the orthogonal-regression threshold search, the
randomization null model, the registration check, and what a defensible report
contains) and in **application** (`docs/guides/38_colocalization.md` — the
step-by-step workflow with real screenshots, the CLI, and the Python API), plus
the generated catalogue page whose per-parameter table comes from the view spec's
`description` fields. The same descriptions are the in-app tooltips, and a
condensed version of the guide is the `?` modal's Markdown.

# Design decisions

- **Coefficients live in `core/fluorescence/imaging/`, not in the plugin.** They
  are physics, not UI; the plugin is glue. They are therefore reusable from a fit
  model or a script.
- **The gate is a model concept, not a widget concept.** The rectangle reports
  bin coordinates; the view-model converts them to intensities through the
  histogram edges. The gate is thus settable headlessly (four numbers), and the
  interactive rectangle is merely one way to set it.
- **Background and threshold are separate.** Background is subtracted first (a
  per-channel offset); thresholds then select pixels in the corrected data — the
  reference implementation's semantics, and what makes Costes' method well-posed.
- **No new dependencies.** `tifffile`/`imageio` and SciPy are already in the
  environment.

# Acceptance

Headless (`plugins/microscopy/img_coloc/test/`, 16 tests):

- PCC is `+1` / `-1` / `≈0` for identical / inverted / independent channels; MOC
  is `1` for proportional channels; M1/M2 reproduce hand-computed split
  fractions; ICQ is `±0.5` at the limits; Spearman stays `1` under a monotonic
  non-linear transform where PCC drops.
- Costes' thresholds land strictly between background and signal on a simulated
  blob image; the randomization test returns `p > 0.95` for real colocalization
  and `p < 0.95` for independent noise.
- van Steensel's profile peaks at the known offset of a translated channel, and
  at `0` for an aligned one.
- A written 2-frame/2-channel TIFF hyperstack loads as `(2, 2, 64, 64)` with
  named channels; a plain 2-D image becomes a 1-frame, 1-channel stack; a
  single-channel file is rejected with a clear error.
- The Qt-free view-model computes, populates the channel list, produces the maps
  and histogram, and applies a gate.

Additionally, the view spec is checked structurally: every attribute it binds
exists on the view-model **and carries a tooltip**, and the `?` modal's help file
resolves next to the spec and covers every coefficient family. A detector setup's
windows become the pickable channels before any file is read, and are ignored for
camera images.

Verified on real data: a multi-detector confocal photon stream
(`test/data/clsm/PQ_Olympus_MFIS.ht3`) runs end-to-end through the CLI *and* the
GUI with named `green`/`red` windows (PCC 0.988, CCF peak at shift 0), with the
whole workspace, both channel maps, the mask, the gated scatter and the CCF
rendered headlessly — the same grabs that produce the guide's figures.

# Parity audit

Both references were read line by line and every capability accounted for.

| Capability | This suite's plugin | The multiparameter suite's image module | ChiSurf |
| --- | --- | --- | --- |
| Pearson PCC | ✅ | ✅ | ✅ |
| Manders overlap (MOC) | ✅ | ✖ (branch commented out) | ✅ |
| Manders split M1 / M2 | ✖ | ✖ (commented out) | ✅ |
| Costes automatic thresholds | ✖ | ✖ (commented out) | ✅ |
| Costes randomization significance | ✖ | ✖ | ✅ (seeded) |
| Li ICQ | ✖ | ✖ (commented out) | ✅ |
| Spearman rank | ✖ | ✖ | ✅ |
| Background estimate (5 % quantile) | ✅ | ✅ (ROI/rate based) | ✅ |
| Scatter gate + live pixel mask | ✅ | ✖ | ✅ |
| Frame / all-frames selection | ✅ | ✅ | ✅ |
| van Steensel shift profile (1-D) | ✖ | ✅ | ✅ |
| **2-D cross-correlation plane** | ✖ | ✅ (FFT) | ✅ (FFT; central row reproduces the 1-D profile) |
| **PCC versus intensity / ratio** | ✖ | ✅ | ✅ (three axes, with standard errors) |
| **Spatial (hand-drawn) ROI** | ✖ | ✅ | ✅ (painted brush; thresholds, null model and profiles all honour it) |
| Camera TIFF **and** photon-stream input | ✅ (image stacks) | ✅ | ✅ (one loader) |
| Named detector windows as channels | ✖ | ✖ | ✅ |
| Headless CLI / scripting API | ✖ | ✖ | ✅ |
| Object-based colocalization | ✖ | ✖ (commented out) | ✖ (non-goal) |

The three capabilities the multiparameter suite had and ChiSurf lacked — the
hand-drawn ROI, the intensity-resolved profiles and the 2-D plane — were ported
in the same PRD; the only remaining ✖ is object-based colocalization, which
neither reference implements either and which needs a segmentation layer.

# Non-goals

- **Object-based colocalization** (segment objects, then measure centroid
  distances / overlap). A different analysis family needing a segmentation layer
  this PRD does not introduce.
- **Registration / chromatic-shift correction.** The van Steensel profile
  *diagnoses* a shift; correcting it belongs to an image-registration step.
- **3-D / z-stack colocalization.** The frame axis is currently summed or
  indexed; volumetric statistics are a later extension.

# Deferred

- Object-based (segmentation) colocalization and per-object statistics.
- Costes randomization over a 2-D block grid including diagonal correlation
  lengths (currently square blocks) plus a scrambled-image preview.
- Registering results in MMFDB ([PRD-03](prd-03.md) / [PRD-07](prd-07.md)) once
  the result registry lands.
- Translation catalogue entries (`de`/`fr`): the view spec passes through the
  `tr()` seam automatically, so this is a catalogue regeneration
  ([PRD-63](prd-63.md)), not code.

# Relationships

- Reference survey: [quickfit3-mining](/references/quickfit3-mining.md) (item 11).
- Sibling imaging PRDs: [PRD-51](prd-51.md), [PRD-52](prd-52.md).
- UI framework: [PRD-40](prd-40.md), [PRD-38](prd-38.md).
- Plugin group concept: [imaging plugins](/plugins/imaging.md).
