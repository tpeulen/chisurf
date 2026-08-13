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

**2026-08-13 — the seam is measured and guarded; two of five groups severed.**

`test/test_chisurf_seam.py` is the ledger and the guard. It parses the import
graph (never greps — `test_qt_seam.py` learned that the hard way, flagging a
module whose only mention of Qt was a docstring saying it *stopped* importing
Qt), and holds a **shrinking** allowlist in
`test/chisurf_import_allowlist.txt`. It distinguishes three things:

* **HARD** — imports ChiSurf unconditionally. Every one is a place the move
  breaks. This is the remaining work.
* **SOFT** — asks inside a `try` and carries its own answer when ChiSurf is
  absent. These **survive the move**; they are the target shape.
  `test_soft_dependencies_are_guarded` proves each is really wrapped, so a
  soft label cannot be used to smuggle an unguarded import past the check.
* **`app/`** — the ChiSurf integration layer (Qt panels, console, dock). It
  may stay behind, so it is excluded from the engine assertion.

`TYPE_CHECKING` blocks are excluded deliberately, not by oversight: they never
execute, so an annotation import is not a runtime dependency.

### Done

1. **Self-referential absolute imports (2)** — `cmd/sele_parser.py` and
   `app/command_dispatch.py` imported *chimol itself* as
   `chisurf.plugins.chimol.chimol.…`, hard-coding chimol's current location.
   These were the purest relocation hazard in the tree: they break **on move**,
   not before. Now relative.
2. **The settings group (4)** — `config.py`, `app/cli.py`,
   `app/command_history.py`, `app/demo_data.py` each resolved the settings
   directory by asking `chisurf.core.settings` directly, re-implementing what
   `settings_dir.py` already does correctly and *skipping its environment
   override*. All four now go through `settings_dir`, and `config.py`'s
   ChiSurf import is gone entirely.

   Two side effects worth knowing. Standalone chimol used to fall through to
   the read-only package copy (so it forgot every setting), and
   `app/demo_data.py` fell back to a temp directory (so demo material was
   re-generated every session) — both fixed by routing through the one seam.
   And **three tests were patching `config._cs_settings`**, a seam that no
   longer exists; one of them documented in its own docstring that patching it
   was already load-bearing. They now set `CHIMOL_SETTINGS_DIR`, which is the
   documented override and now covers *every* path into the config. That
   consolidation is the point: one override, not two.
3. **`cmd/exporting.py`** — moved from HARD to SOFT. Its
   `chisurf.gui.progress.ChiSurfProgress` import is now guarded and falls
   through to `_render_ray_in_viewport`, the in-viewport progress path that
   already existed for windowless hosts and already draws a bar, an ETA and a
   Cancel button with chimol's own chrome.

4. **What the guard corrected.** Writing the soft/hard split down and running
   it showed three of the four "hard" engine dependencies were **already
   guarded** and had been for some time — `io/atoms.py` (its own copy of the
   dtype, with `test_engine_is_portable` asserting the two are equal, from the
   browser port), `analysis/ss.py`, and one of `io/structure.py`'s two
   `read_dcd` sites. That is the value of writing the distinction down rather
   than estimating it: the engine was much closer to movable than the raw
   import count suggested. `io/structure.py`'s *second* site — the loader
   itself — was genuinely unguarded and now raises a chimol-owned
   `TrajectoryFormatError` naming the missing reader, instead of an
   `ImportError` from a package chimol is not supposed to need.

5. **The element table is vendored; HARD is empty.** `analysis/elements.py`
   was a re-export of `chisurf.core.fio.structure.elements`. Two facts settled
   it: the **generator** (`analysis/make_elements.py`) already lived in chimol,
   so only its *output* sat in core; and **nothing in ChiSurf imported the
   table** — the only consumers were that generator and this module. Core was
   holding a periodic table on chimol's behalf, and it was the last thing
   stopping the engine from importing cleanly. chimol owns it now (109 masses,
   119 radii, verified byte-identical to the core copy before the switch), and
   `make_elements.py` writes beside itself. A peer had *already staged the
   deletion* of the core file; this makes that deletion safe.

   **`HARD` is now empty**: the engine has no unconditional ChiSurf import
   anywhere. What remains is `app/` (the integration layer) and the soft
   dependencies, which are the target shape rather than debt.


6. **The DCD reader moved, and ChiSurf now takes it from chimol.** This is the
   first application of the user's rule in the *inverting* direction rather
   than the vendoring one: `dcd.py` had **thirteen ChiSurf callers** (core
   structure code and the `traj_*` plugins), so unlike the element table it
   could not simply be lifted. It moved to `chimol/io/dcd.py` and
   `chisurf.core.fio.trajectory` re-exports it, so all thirteen callers are
   untouched. The file was already self-contained (numpy, pathlib,
   dataclasses -- no ChiSurf import of any kind), which is what made a move
   rather than a port possible. `io/structure.py` now uses `from .dcd import
   read_dcd` at both sites and is off the allow-list entirely.

7. **Sequence colours are chimol's, not a Qt dock's.**
   `SequenceDock.default_sequence_palette` / `.gap_palette` were
   ``staticmethod``s on a Qt widget, so "what colour is a helix residue" could
   only be asked through a window system -- in a viewer that draws its
   sequence in three hosts and has Qt in one. The logic was never Qt's (a
   config lookup and a luminance test). They are now
   `chimol.colors.sequence_palette` / `gap_palette`, returning plain
   ``(r, g, b)`` tuples; `molview_main_window` keeps two small adapters that
   wrap them in ``QColor``, which is the only genuinely Qt part.

### The Qt docks: measured, and *not* a safe `rm`

The user cleared them to go, and the in-viewport chrome already replaces both.
The blocker is not the panels but their **call sites**, and the number in the
source was wrong: `molview_main_window.py` says the sequence dock is kept
"until the ~100 call sites that still feed it are unwound", and the real count
is **49**, all in that one file and nothing outside it:

| | count |
|---|---|
| `self.sequence.*` | 22 |
| `self.object_list.*` | 17 |
| `self.objects.*` | 10 |

`SequenceDock` is **already built, parented and hidden** — so those 22 call
sites are populating a table nobody can see, every time the sequence changes.
Removing it is therefore a performance win as well as a deletion, but it is a
49-site unwind inside a 3,478-line `QMainWindow`, not a file deletion, and it
wants its own change with the window driven headlessly to prove the strip
still shows what the dock did. Attempted as a quick `rm` it produced exactly
the half-removed state it should have: imports gone, constructors still
calling them.

**What has been peeled off so far.** The dock's surface is being reduced from
the outside in, taking the parts that were never Qt's first — the same move
that worked for the palettes, and each one shrinks the unwind:

| moved to `chimol.colors` | was | call sites freed |
|---|---|---|
| `sequence_palette` | `SequenceDock.default_sequence_palette` | 3 |
| `gap_palette` | `SequenceDock.gap_palette` | 1 |
| `sequence_config` | `SequenceDock.sequence_config` | 5 |
| `rgba_to_rgb` | `SequenceDock.color_from_rgba` (returned a `QColor`) | 4 |

`self.sequence` uses: **22 → 13**. The Qt window keeps two thin adapters
(`_seq_colors`, `_qcolor_from_rgba`) that wrap chimol's plain-RGB answers in
`QColor` — the only genuinely Qt part of what was moved. `test_panel_layout`
no longer needs a window system to ask what colour a gap is.

**What is left, exactly.** The 13 remaining `self.sequence` uses are the
constructor (which also parents and hides it) and **ten attribute aliases**
(`self.seq_list = self.sequence.seq_list`, and nine like it). Those aliases
are the real depth: **77 uses** across the file, concentrated in
`self.seq_list` (34), `self.seq_numbers_list` (19) and `self.seq_label` (16).
Every one writes into a table that is parented and hidden — so this is dead
work on every sequence change, and deleting it is a performance change as
much as a deletion. That is the next unwind, and it is the whole of it: no
other file touches them.

**And it is safe — established, not assumed.** The reason to be careful was
`_selected_residue_indices()`: it reads the hidden table's *selection* back
(`self.seq_list.selectedIndexes()`) and is called from six places, two of
which feed the info panel and the viewport. If the hidden dock were still
holding selection state, deleting it would break selection silently. Traced:

* `self.seq_list` is created with **`ExtendedSelection`** (`sequence_dock.py:92`),
  so it is not disabled by construction — the `NoSelection` at
  `molview_main_window.py:1519` is a *different*, local list (the per-object
  extra rows), which is the easy misread here.
* But the widget is **hidden at startup** (`:383`), so nothing can click it;
* and **nothing selects it programmatically** — there is no `setCurrentRow`,
  `setCurrentItem`, `selectAll` or `setSelected` against it anywhere. The only
  selection call is `clearSelection()`.

So `selectedIndexes()` is always empty, every caller of
`_selected_residue_indices()` gets `[]`, and the readback is dead **in
effect**. It is dead because the widget is unreachable rather than because
selection is switched off — a distinction worth writing down, because the one
thing that would resurrect the dependency is somebody making the dock visible
again. Do not do that; the in-viewport strip is the replacement.

**Done, 2026-08-13.** `app/sequence_dock.py` is deleted and
`molview_main_window.py` is ~360 lines lighter. Removed with it: the six
dock-only methods (`_populate_sequence_numbers`,
`_apply_sequence_selection_styles`, `_selected_residue_indices`,
`_reset_scroll_targets`, `on_seq_row_toggled`, `_add_sequence_row_for_object`),
three handlers orphaned by them (`on_seq_label_toggled`,
`on_sequence_selection_changed`, `_update_sequence_row_colors`), the ten
widget aliases, both signal connections, and `_apply_representation_to_selection`
-- which had **no callers at all** and began by early-returning on the
always-empty selection, so it had never done anything.

`_update_sequence_view` **stays**, because four `cmd/` modules call it, and is
now a documented no-op. The obvious implementation -- delegate to
`_refresh_objects_from_viewer`, as the toolkit-free host does -- is *wrong
here* and was caught immediately as a `RecursionError`: that method calls
`_update_sequence_view` itself. The strip is refreshed by `sync_internal_gui`
off the object-registry subscription, so there is genuinely nothing left to do.

Five tests in `test_panel_layout.py` pinned the dock's own geometry
(scrollbar origin, row stacking, column alignment) and went with it, plus one
asserting its "no sequence" message. `test_engine_is_portable`'s `HOSTS` is
one shorter. What survives is the colouring, which needs no window at all.
Verified: 33 passing across panel-layout/portability/seam, 152 across the
chrome, menu and interaction suites, 3937 collected.


### The objects dock is invisible but **not** inert — do not `rm` it

Asked to remove it as unused. Half true, and the other half would have broken
something silently, so it is written down here.

`self.objects.widget` is **never added to a layout, dock area or shown** — the
same state the sequence dock was in, and the reason it looks unused. But the
two are not alike:

* the sequence dock's list could never emit, because nothing could select in
  it (hidden, and no programmatic `setCurrentRow`/`setSelected` anywhere), so
  every read-back returned `[]` and the whole path was dead **in effect**;
* the objects list is **mutated programmatically** — `create_item`,
  `attach_row`, `set_current_object` — and those mutations *do* emit
  `itemChanged` / `itemSelectionChanged`. `_block_object_list_signals` only
  guards item **creation** (a ~12-line window), not the rest.

Measured rather than reasoned: instrumenting both handlers and loading 148L
into a real (offscreen) window gives **3 signal firings, all 3 unblocked** —
`on_object_selection_changed` and `on_object_item_changed` running their real
bodies, which reach `_handle_active_object_change` -> `viewer.set_active_object`
and `_update_system_info`. Deleting the list would drop that propagation with
nothing to notice it: no test asserts it, and the widget it hangs off is
invisible, so the symptom would be "the active object sometimes does not
change" long after the fact.

**Done, 2026-08-13 — refactor first, then the deletion.** `_select_object_in_ui`
now calls `_handle_active_object_change` **directly** instead of setting a
list row and letting `itemSelectionChanged` carry the change. With the
propagation no longer routed through a widget, the widget could go:
`objects_panel.py` deleted, along with `on_object_selection_changed`,
`on_object_item_changed`, `_on_object_list_context_menu`,
`_delete_selected_objects`, `_add_object_list_item`, `_add_group_list_item`
and the four calls into them (the object *store* was always written
separately, and the chrome rebuilds its rows from that).

The probe is the proof, run before and after on the same 148L load:

| | before | after |
|---|---|---|
| dock widget visible | `False` | *(gone)* |
| unblocked signal firings | **3** | — |
| `_handle_active_object_change` calls | *(via signal)* | **1**, `active_id='obj2'` |

Four `test_panel_layout` tests pinned the dock's own row geometry and went with
it; `HOSTS` is down another entry. `app/` is **14 files**, from 16.


### chimol must be Qt-free — the strip list

User, 2026-08-13: *"chimol supposed to run on web, no qt there, must strip
away"*, and *"only in chisurf, should be qt shim embedding chimol (this is how
chimol should be embedded as plugin in chisurf)"*. That settles the one
architectural question this concept had open. The target:

* **chimol** — no Qt, no ChiSurf. It is the engine, and it must import on a
  machine that has neither. The browser build already proves the shape.
* **chisurf** — a Qt shim that *embeds* chimol. Every `QWidget` lives here.

`test/test_qt_seam.py` already tracks this and is the ledger; its allow-list is
the strip list, **15 files** after the two docks came out:

| group | files | where they go |
|---|---|---|
| the shim itself | `app/molview_main_window` (45 Qt refs), `app/rmf_panel` (30), `app/demos` (11), `app/menu_bar` (9), `app/controls_panel` (9), `app/settings_table` (5) | **chisurf** — this *is* the shim |
| the Qt half of chimol's own seams | `renderer/wgpu_view` (20), `cmtk/qt_host` (11), `host/widget` (9), `renderer/view` (12) | **chisurf** — see the widget rule below |
| stragglers | `cmd/exporting` (12), `cmd/inspect` (2), `testing/mock_viewer` (3) | lazy imports and adapters; small, do last |


**The line is a Qt *widget*, not Qt.** User, refining the above: *"qt painter
can stay in cmtk, just different endpoint as long as nothing breaks, just no
qt widget, or interfering stuff."* A painter backend is an **endpoint** -- one
implementation of a protocol chimol defines -- and it cannot interfere with a
web build that simply never imports it. A `QWidget` is different in kind: it
is a window system, and it is what cannot exist on the web.

Splitting the allow-list by `QtWidgets` usage makes the rule mechanical, and
three files come off the strip list entirely:

| stays in chimol | QtWidgets | what it is |
|---|---|---|
| `cmtk/qt_painter.py` | **0** | the `Painter` protocol's Qt endpoint -- `QPainter`/`QColor`/`QFont`, no window |
| `renderer/gui_overlay.py` | **0** | rasterises the chrome into a `QImage`; same shape, no window |
| `testing/mock_viewer.py` | **0** | test scaffolding, `QtCore` only |

| must move to the shim | QtWidgets |
|---|---|
| `app/molview_main_window.py` | 17 |
| `app/rmf_panel.py` | 16 |
| `renderer/view.py` | 11 |
| `app/demos.py`, `app/menu_bar.py` | 9 |
| `app/controls_panel.py` | 6 |
| `cmtk/qt_host.py` | 5 |
| `app/settings_table.py`, `host/widget.py` | 4 |
| `renderer/wgpu_view.py`, `cmd/exporting.py`, `cmd/inspect.py` | 2 |

So the strip is **12 files, not 15**, and the guard should assert on
`QtWidgets` rather than on Qt as a whole -- that is the property that actually
decides whether chimol runs in a browser.



## Where to pick this up

The full chimol suite **completes** now (3891 passed) -- it used to segfault at
~7%, which hid 18 failures. Nine are fixed; **nine remain**, and they are the
worklist:

| file | tests | what it reaches for |
|---|---|---|
| `test_object_menus.py` | 4 | `window.objects` -- the deleted dock's `_rows`, `set_run_command` |
| `test_split_chains.py` | 2 | `window.objects.object_list` -- checkbox state, "panel rebuild" |
| `test_render_appearance.py` | 1 | `window.seq_list` -- the deleted sequence dock |
| `test_background.py` | 1 | colour `(1,1,1)` vs `(0,0,0)` -- **not** a dock; unread |
| `test_surface_splat.py` | 1 | `'fast' == 'splat'` -- **not** a dock; unread |
| `test_trajectory_controls.py` | 1 | window clipping; one array 100% mismatched -- **not** a dock; unread |

**Take the three non-dock ones first.** They are the only ones that might be
real defects rather than tests pointed at a deleted widget, and they have never
been read -- the suite has not reached them in a single run until today.

### The trap in this work

A test reaching into the deleted dock is **not** automatically a test to
repoint. Two of the nine already fixed were hiding real regressions:

* `_targets_for` -- whether a menu entry on a group runs once per member --
  existed **only** on the dock. Deleting the widget deleted the rule, and a
  menu entry on a group silently applied to the group name, which resolves to
  nothing. It is `object_menus.targets_for` now, and the in-viewport panel
  calls it.
* `set_object_group`/`set_group_open` never called `registry.touch()`, so
  `objects_revision` did not move and no view learned that a group had been
  created. This was invisible while the dock existed because the dock
  refreshed on its own path. `group ligands, lig nag` left the panel showing a
  flat list.

So for each remaining failure, **ask what the dock knew that nothing else
does** before repointing the assertion. Check the behaviour by hand in a live
window first (`win.viewer._renderer._internal_gui.rows`), not by reading.

### Panel equivalents for repointing

| the dock had | the panel has |
|---|---|
| `win.object_list.itemWidget(i)` | `gui.rows[i]` (`GuiRow`) |
| `widget.disclosure` / `widget.group` | `row.is_group`, `row.name` |
| `widget.layout().contentsMargins().left()` | `row.indent` |
| `widget.buttons` | `gui._button_rects[i]` after `gui.layout(w, h)` |
| `win.seq_list` item colours | `colors.sequence_palette` / `gap_palette` |

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
