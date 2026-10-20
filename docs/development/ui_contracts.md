---
type: Development Note
title: Auditing shared UI text and tooltips
description: Verify authored form strings, translation source coverage and tooltip declarations without importing plugin GUIs.
tags: [development, plugins, contracts]
audience: developer
---

# Auditing shared UI text and tooltips

The renderer exports immutable `emtk.view_form.TEXT_KEYS`. The translation
extractor covers those fields, including label/description arrays, numeric
sentinel text and choice fallback labels. Explicit choice labels replace raw
binding values; custom options retain their binding identities. Bare `view.json`
and named guide files are included. Invalid shipped JSON/Python is an error.

Run `pixi run -e test python -m pytest test/test_i18n_extraction.py test/test_i18n.py -q`.
The catalogue check measures committed package bytes so unrelated unfinished
plugin migrations do not become release claims. New strings can remain
unfinished; runtime installs only finished singular translations. Retired Qt
contexts retain a finished translation in the flat context only when its source
has one unambiguous prior translation. Different context meanings are not guessed.

Regenerate with `pixi run i18n-extract --locales de fr` and compile with
`pixi run i18n-compile`. Preserve human translations. In a shared tree, generate
from committed/prospective owned package bytes and keep a separate live ledger.

Run `pixi run -e test python -m pytest test/test_tooltips.py -q` or inspect
`pixi run -e test python build_tools/dev_utils/ui_contract_audit.py --revision HEAD --output /tmp/tooltips.json`.
The audit handles named form envelopes, buttons, radio descriptions, columns
and imperative controls with same-item tooltip helpers. Companion repositories
are read at their recorded commits; malformed sources are not silently dropped.

The initial measured tooltip baseline contains 1,143 omissions. It is a shrinking
worklist, not complete coverage: new omissions and obsolete allowances both fail.
Remove an allowance only with a meaningful tooltip fix and runtime render/hover
proof where static code cannot establish delivery. Dynamic metadata still needs
runtime checks. The release target is an empty baseline. Do not infer working
controls, tours, scientific results or release readiness from this static guard.

## Initial window geometry

A top-level `window: {"width": 640, "height": 480}` in the loaded view spec
declares logical pixel dimensions. Both fields are required integer values
from 120 to 8192; unknown fields are rejected. Native applications read it with
`chisurf.plugins.emtk_layout.window_size(spec, family_default)` before hosting.
The imaging pipeline window (Image Tools, `imaging_tools/gui/app.view.json`) uses 1100×720, the FRET calculator
640×480, and the TTTR image browser 1200×800. Setup step uses the same parser. The pipeline window's empty section
list declares only its geometry; each step's form remains a separate spec.

`attach_native_state` restores saved user dimensions after this default. Both
emtk Qt and native hosts read `window_size`, including callable declarations;
`preferred_size` is obsolete. Qt clamps startup size to the display. Keep
viewport-relative `Cond.ALWAYS` calls for rails, headers and status regions: they
follow resizing and are not initial window defaults.

Run `pixi run -e test python -m pytest test/native_emtk/test_declared_window_size.py test/native_emtk/test_state.py -q`.
Regenerate the schema with `pixi run -e test python -m chisurf.core.dataspec.schema`.
Only the measured consumers above are covered so far; the committed factory
map in OKF identifies the remaining families and unresolved primary loaders.

The shared imaging and trajectory shells read geometry from the raw loaded
spec before preparing or flattening form sections. A missing declaration uses
1100×720. Drift correction and rotate/translate declare that size explicitly;
other primary specs still need their individual sizing/render review. Automatic
plot labels use their final measured bounds to stay separate in narrow panes.
Explicit custom labels remain as requested; tick/grid positions and data ranges
are unchanged.

## Imperative translation worklist

Use `pixi run -e test python build_tools/dev_utils/ui_contract_audit.py --contract translation --revision HEAD --output /tmp/i18n-literals.json`
to measure bare visible literals at the declared emtk text sinks and input hints.
Imports using aliases or direct widget names are included. Numeric decoration
and hidden `##` identifiers are exempt. Parse errors are findings. The audit
reads committed source and the recorded companion revisions; it does not import
GUI code or create a translation allowance. Dynamic expressions require separate
runtime review. The initial measured worklist remains open; pure scanner tests
do not establish completed wrapping.

Layout checks now consume the recorder's per-draw visible logical font bounds,
with alignment and active clips. Text alignment boxes do not implicitly clip
text. Real overlap and overflow remain errors; actual PNG inspection is needed
for rasterized ink. Tracking fit tests compare exact data and independently
profiled least-squares objectives, preserving unrestricted nuisance offsets
and checking bootstrap results independently. Optimizer-specific decimals in
old archived output are not an accuracy oracle.

## Fresh compact calculator layouts

Native calculators declare 640×480 initial dimensions, with saved user geometry
taking precedence. FRET Line selects a compact layout once for a fresh viewport
under 900 pixels: its live editor becomes a full-width tab above the plots. Wide
initial and saved custom layouts are retained. The SDK's atomic default-layout
API also records this declaration for Reset; applications do not inspect private
persistence fields. Empty text commits on Enter, Escape cancels buffered edits,
and fractional-height rows can scroll completely into view without growing the
scroll range.

The shared help gate reads committed manifest enrollment. Local uncommitted
native ports remain a separate diagnostic; deleting a Qt entry cannot hide a
committed native tool. Native resources may live beside a gui module or at the
plugin root, and string tour targets are valid runtime names.

Use `pixi run -e test python build_tools/dev_utils/check_plugin_guide.py traj_save_topology /tmp/guide-check --width 1100 --height 720`.
The checker records targets, truncation and actual wait states. It presses a
real `load_example` control when present and settles its worker; other awaited
file, save or external actions remain pending. Pending/unwired actions fail
the interaction gate. `--all` runs isolated bounded workers. Release enrollment
comes from frozen HEAD; `--live` explicitly diagnoses local prototypes, and
reports qualify current runtime bytes. No wait is marked satisfied by fiat.
