---
type: Architecture
title: GUI Startup
description: The staged, JSON-declared GUI startup path and the laziness invariants that keep it fast.
resource: chisurf/startup/
tags: [startup, gui, performance, plugins]
timestamp: '2026-10-05T00:00:00Z'
---

# Where to pick this up

0. Measure: **All 122 emtk plugins draw a first frame under 100 ms** (worst `ndxplorer` 85 ms;
   26 were over, `chimol` 1634 ms). Re-derive with `python -m build_tools.dev_utils.plugin_frame_times`
   (table in `docs/development/benchmarks.md`). It now also reports `next5` (max of the five frames after
   the first) and `settle` (max frame while worker results land): a first-frame fix that only moves the
   cost one frame later shows there -- `psf_calculator`'s settle was 1290 ms (chimol starting when the
   first volume landed) although its first frame was 48 ms. Traps: the harness shares one warmed emtk
   font cache per run (`EMTK_CACHE_DIR`); on a machine with load average > 10 (parallel agents) first
   frames of 80-ms plugins read 100-180 ms -- check `uptime` and repeat before believing a regression.
   - Open: any new hub or first-frame read follows the pattern -- a hub makes the tool it shows with `chisurf.emtk.background_build.BackgroundBuild` and draws
     `draw_opening(...)`; `ensure_child`/`select` stay synchronous and join a build under way. chimol
     (`ChimolHostApp`, `ChimolView.start/ready`) starts the same way. A store/registry read on the first
     frame goes to a thread and is adopted in `poll()` (`SetupToolbar.reload_async`,
     `catalog.prefetch()`, the saturation dye list). Test drivers that draw frames back to back call
     `background_build.join_all()` first (the shared `emtk_test_input.Driver`, `imaging_emtk.testing`,
     count-rate `Pointer` do); a new local `draw()` helper in a test must too, or it sees the placeholder.
   - Open: closest to the budget are `ndxplorer` 85, `structure_tools` 78 (the rail and heading font;
     its card's `fio.structure` import now lands on the adopt frame), `user_editor` 78
     (markdown details + its own first-frame job thread contending for the GIL), `filetools` 75 and
     the phasor calculator 71. Profile with cProfile around `Driver.frame()` in the harness subprocess.
   - Open: worker threads contend for the GIL with the UI thread: `fcs_saturation`'s `next5` is 26 ms
     while the MMFDB import runs beside it. Heavy imports belong in the plugin's backend process, not a
     thread, if this grows.
   - Tried and reverted: a small `_vocabulary_cache.json` in mmfdb `models.py` -- no gain, because
     `mmfdb.schema.schema` loads the full dictionary cache (~130 ms, 19k `from_dict`) at import anyway
     for six DDL strings. The real fix is a faster dictionary cache load (pickle-speed ~40 ms) or lazy DDL
     in mmfdb; until then the MMFDB open stays off the first frame by threading.

1. Measure: **Embedded server ctor is ~2.2 s** (was 4.3 s on 2026-10-05). Measure with
   `python -X importtime -c "from chisurf.server.app import ChiSurfServer; ChiSurfServer(cmd_port=0, pub_port=0)"`
   and walk each heavy leaf (`scipy.*`, `matplotlib`, `fastapi`, `IMP.bff`, `mmfdb.models`)
   up to its nearest `chisurf.plugins.*.backend.services` ancestor -- that ancestor is
   what the registration loop imported. Trap: `ServiceDispatcher` is created and
   torn down in-process, so time the ctor, not `python -m chisurf` wall time
   (that is noise-dominated on a loaded machine, ±1 s).
2. Open: Left on that path: `IMP.bff` via `core.fitting` (0.3 s; pinned eager by
   `test_bff_is_the_backend`, see `core/fitting/__init__.py`), ebfret `dist`
   (scipy.special, 0.06 s -- goes away with the bff numerics), `mmfdb.models` (0.15 s).
3. Measure: Every RPC method has exactly one owner. The dispatcher's registration
   transaction raises on a second registration; a startup log line
   `Failed to register services for plugin` means a manifest `services` entry
   duplicates the central config (`server_methods.json`, the mmfdb startup
   service). Drop the manifest entry, keep the central owner.

## Resume history (moved out of Where to pick this up)

Moved here unchanged: notes that are history, done work or standing rules rather than the next step.

4. **Post-show services only see declared dependencies.** The `post_gui_show`
   runner builds `context.dependencies` from `depends_on`; the window comes via
   `context.main_window` (`_get_window`). Model classes are resolved post-show,
   so anything that lists models must resolve its own experiment first
   (`_ensure_experiment_models`) -- the start-up sample is selected before the
   service runs. Check with a TCSPC dataset selected, not the Global one, which
   has its models eagerly.

# Staged startup

GUI startup is declarative. `AppStartupServiceManager`
(`chisurf/startup/services.py`) loads service specs from JSON files in
`chisurf/startup/services.d/` and runs them in dependency order, grouped by
`surface` (`gui`) and `phase`. The entrypoints live in
`chisurf/startup/gui_services.py`.

Two phases matter:

* **`splash`** — the critical path behind the splash screen, ending with a
  usable main window (`20_gui_splash.json`).
* **`post_show`** — work deferred until after the window is up
  (`30_gui_post_show.json`), including `deferred_gui_imports` and plugin
  population.

`_start_service` times every stage. Stages slower than `_SLOW_STAGE_SECONDS`
log at INFO; the full map is available as `AppStartupServiceManager.timings`.
That timing is the measurement tool for any startup regression — read it before
optimizing anything here.

# Laziness invariants

Startup cost is dominated by work that is *discarded*, not by work that is
inherently needed. Four invariants keep it that way; breaking any of them
silently costs seconds.

**Aggregator packages do not import their sub-packages eagerly.**
`chisurf/core/fio/__init__.py` and `chisurf/core/fluorescence/__init__.py`
expose sub-modules through a PEP 562 module `__getattr__`. Importing a small
reader (e.g. `chisurf.core.fio.ascii`) must not drag in the whole
fluorescence/pandas/scipy stack behind the package `__init__`.

**Plugin discovery is cached.** `chisurf.plugins.iter_plugins()` memoizes a
full-tree walk that reads and parses every plugin `__init__.py` and
`manifest.json`. Startup calls it from several places (main window, ribbon
categories). Anything that installs, renames or removes a plugin must call
`invalidate_plugin_cache()`.

**Menu construction does not import plugin code.** Names, descriptions and
icons all come from `manifest.json` and on-disk icon files. `chisurf.gui.plugin_icons.
create_plugin_icon_with_fallback` accepts a *callable* module provider so the
import happens only for the few plugins whose icon comes from a module
attribute. Importing plugins to build a menu is what made the ribbon slow, and
plugin modules have import-time GUI side effects that make it fragile besides.

**Reader controllers are built on demand.** `ExperimentReader.controller`
(`chisurf/core/experiments/core/reader.py`) is a property backed by a factory
registered via `set_controller_factory`. The GUI configures many experiments
with several readers each but shows only the selected one, so eager
construction built roughly eighteen widgets to display one.

**The plugin toolbar is keyed by display name, so a rename empties it quietly.**
The `plugins.toolbar_plugins` setting lists plugins by the name shown in the
menus. Rename a plugin and its entry stops resolving: the button is not added,
one `Could not find module for plugin` line goes to the log, and startup carries
on. Three of the seven shipped entries had been dead that way — `Burst
Selection` had gained a space, `Burst MLE` and `ndX` had been shortened — so the
toolbar had been shipping four buttons where it promised seven.

Correcting the shipped list is not enough, and this is the general trap with
anything in `settings_chisurf.yaml`: user settings are copied to `~/.chisurf`
**once** and never refreshed, so an edit to the shipped defaults reaches new
installs only. `find_toolbar_plugin` (`chisurf/gui/main.py`) therefore resolves
leniently — exact name, then last-`:`-segment and module name compared without
case or punctuation, then a *unique* prefix relationship. Ambiguity is never
resolved: two candidates mean no match and the warning stands, because a toolbar
button that silently opens the wrong tool is worse than a missing one. Pinned by
`test/gui/test_toolbar_plugin_names.py`, which asserts every shipped entry
resolves *and* that the legacy names still sitting in existing `~/.chisurf`
files reach the right module.

**Service registration imports every plugin backend, so backends import lazily.**
`ChiSurfServer.__init__` calls each manifest's `services` entrypoint, which
imports that plugin's backend module and everything it imports at module
scope. A heavy library imported at module scope in *any* backend -- or in a
core module a backend reaches -- is paid by every start-up whether the tool is
ever opened or not. scipy.signal (via the IRF estimator), scipy.optimize (burst
background, `core.fluorescence.general`), pyplot (FCS MaxEnt) and fastapi (the
FRET API's optional HTTP surface) were each costing 0.3-0.8 s this way; they are
imported inside the function that uses them now.

# Stylesheet

The application stylesheet is applied once. `_apply_stylesheet`
(`chisurf/gui/__init__.py`) early-returns when the sheet is unchanged, because
re-applying an identical sheet makes Qt rebuild `QStyleSheetStyle` and
re-polish the entire widget tree for no visual change.
