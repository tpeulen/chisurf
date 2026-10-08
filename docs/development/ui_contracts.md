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
