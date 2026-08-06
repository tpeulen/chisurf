---
type: Plugin
title: ndX multidimensional explorer
description: The interactive explorer for burst and image parameter tables — projection, gating, curve overlays, and playing a measurement back along one of its own columns.
resource: modules/ndxplorer/
tags: [plugins, ndxplorer, bursts, gating, playback]
timestamp: '2026-08-06T00:00:00Z'
---

ndX is ChiSurf's interactive explorer for wide numeric tables: burst data (E, S,
lifetime, brightness), imaging-derived parameters, posterior draws. You project
the cloud onto one or two axes, gate a sub-population, overlay a parameterised
curve and fit it. Theory in
[`docs/concepts/multidimensional_exploration.md`](../../docs/concepts/multidimensional_exploration.md),
usage in [`docs/guides/46_ndxplorer.md`](../../docs/guides/46_ndxplorer.md).

It lives in its **own repository**, vendored as the git submodule
`modules/ndxplorer` (branch `development`); the ChiSurf side is a thin plugin
wrapper (`chisurf/plugins/ndxplorer/`) that puts the module on `sys.path` and
builds the window. Changes to ndX commit **there**, and ChiSurf records only the
gitlink. It declares `chisurf` as a hard dependency and a test enforces it —
running without ChiSurf is a broken environment, not a supported configuration —
but every chisurf import is lazy or guarded, so nothing pulls the GUI stack at
module import time.

## Where to pick this up

1. **Playback on a real burst folder.** The gate, the panel and the axis
   detection are covered headlessly
   (`ndxplorer/tests/test_playback_controller.py`,
   `tests/test_ui/test_playback_panel.py`,
   `tests/test_ui/test_open_image_hdf5.py`), all on synthetic tables. What is
   *not* measured is what playing back an hour of real bursts costs: a redraw is
   ~20 ms on the sizes those tests use, and the panel offers up to 60 fps. Take
   the measurement by timing `update_plots` over a loaded `.bur` folder at
   several step counts before deciding whether the speed cap needs lowering or
   the redraw needs to skip a tick it cannot keep up with.
   - **The trap:** the mask is cached on
     `(axis, mode, position, n_steps, bounds, data_version)` and the *identity*
     of the array returned by `DataManager.get_value_mask` is load-bearing
     downstream. A benchmark that rebuilds the controller per step measures the
     uncached path and reports a cost the app never pays.
2. **`integrate` mode has no normalisation.** Each step draws more points than
   the last, so a colour scale that autoranges makes the early steps look empty
   and a fixed one makes the late ones saturate. Neither is wrong; there is
   simply no decision recorded. Deciding it (autorange per step vs. fix on the
   final frame) is what makes integrate mode readable rather than merely correct.
3. **Nothing exports a playback.** The obvious next thing a user asks for after
   watching a population move is a GIF/MP4 of it, and the screenshot helper
   (`utils/screenshot_helpers.py`) already grabs a single frame. Stepping it over
   the range and encoding is a small job that has not been done.
4. **ndX still owes a `?` and a Guide.** It is on
   `test/plugin_help_guide_allowlist.txt`: no `add_toolbar_help`, no
   `gui/guide.json` anywhere in the module. Every *control* now carries a
   `description` (the playback panel's are in its view spec, and AutoForm turns
   them into tooltips), but a dense window of documented settings is still
   unusable without a tour that says which control to touch first. The playback
   panel is the natural opening step of one, since it is the only control that
   changes what the plot means rather than how it looks.
5. **Tried and rejected: a fixed window width in seconds.** It was the first
   design, and it makes playback duration proportional to acquisition length — a
   three-minute playback of a one-hour measurement and an instant one of a short
   file. A fixed *step count* was chosen instead, so the wall-clock length of a
   playback is the same whatever the file; the width is derived and shown in the
   readout.

## Playing a measurement back

A burst table is a time series: each row carries `Mean Macro Time (s)`, made
monotonic across every `.bur` file of a measurement by the reader
(`io/reader.py::_process_burst_analysis_dir`, which also rebases milliseconds to
seconds — the HDF5 and CSV readers do neither, so a table loaded that way still
spells it `(ms)` and restarts per file). A static 2-D histogram integrates that
time away, which is why a photobleaching sample and a stable one with broader
populations draw the same picture.

This used to be two features. An image stack got a frame selector — a spin box,
five transport buttons and a timer in the `Image` group box — and burst data got
nothing; the frame-column detector explicitly rejected any column whose name
contains "time". They are now one:

| Piece | Where | What it owns |
| --- | --- | --- |
| `PlaybackController` | `ndxplorer/core/playback.py` | Qt-free. Axis, mode, step, step count, bounds; produces the keep-mask and the scalar key it was built from. |
| `PlaybackViewModel` | `ndxplorer/plotting/playback_view_model.py` | The AutoForm binding and the `QTimer`. Every field is a property forwarding to the controller. |
| `playback.view.json` | `ndxplorer/plotting/` | The panel: axis combo, step count, step slider, transport row, mode radios, speed slider, live readout. Rendered by ChiSurf's [AutoForm](../subsystems/gui-autoform.md) as a foldable `panel`. |
| `setup_playback` | `plot_control.py` | Picks the axis after **every** load — frame index first, then macro time, else idle with all columns offered. |

The three modes are three questions. `window` (`edges[i] <= v < edges[i+1]`) is
the population as it was then; `integrate` (`v < edges[i+1]`) is everything so
far, which converges to the static plot and shows a late-arriving population
arriving; `stack` is no gating, and is how a file opens.

Two details carry the design:

- **A frame index is the same gate.** Its bounds are pushed half a step outwards
  (`lo = -0.5`, `hi = n − 0.5`, one step per value), so a window over it reduces
  *exactly* to the `column == frame` the frame selector did. That equivalence is
  pinned by a test; without it the unification would be a second implementation
  wearing the same name.
- **The last step includes the top edge.** Half-open on every step leaves the
  largest value — the last burst, the last frame — in no step at all, so playing
  to the end shows an empty plot.

The slice reaches the data layer as `MaskState.slice_mask` plus
`MaskState.slice_key` (`core/data/mask_state.py`). The array is never in the
cache key: it is expensive to compare and, compared by identity, wrong. The key
is the scalars.

## Gating: one path, one answer

`plot_main._collect_mask_state()` is the only place the GUI is read to decide
which points are visible. It gathers drawn selections, the z-range, the isolated
cluster and the playback slice into a Qt-free `MaskState`;
`DataManager.get_value_mask()` applies all of them and caches on
`(data_version, state.key())`, deliberately returning the *same array object*
while nothing changed, because the histogram layer keys on that identity.
Polarity throughout: `True` means **excluded** in the value mask, `True` means
**keep** in the slice mask that feeds it.

## Related

- [AutoForm](../subsystems/gui-autoform.md) — the panel is a view spec, not widget code.
- [Burst companions](../subsystems/burst-companions.md) — where the columns ndX merges come from.
- [Burst analysis](burst.md) — the plugins that write tables ndX opens.
