---
type: Guide
title: Auditing shared UI text and tooltips
description: Verify authored form strings, translation source coverage and tooltip declarations without importing plugin GUIs.
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
Shared tool/calculator hubs use 1100×720, the FRET calculator 640×480, and the
TTTR image browser 1200×800. Setup step uses the same parser. The hub's empty
section list declares only its geometry; child forms remain separate specs.

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
