---
type: PRD
prd: "02c"
title: "PRD-02c: Aligning ChiSurf MMFDB Export to flrCIF"
description: Map ChiSurf's internal parameter short names to canonical flrCIF dictionary items on export
status: done
phase: "foundation"
resource: modules/mmfdb/src/mmfdb/
tags: [prd, mmfdb]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Ensures parameters exported from ChiSurf to MMFDB strictly adhere to the flrCIF
standard, with the flrCIF dictionaries (plus the local `mmfdb_flr_ext.dic`
extension) as the canonical source of truth for parameter definitions. ChiSurf's
internal short abbreviations (e.g. `E_FRET`, `bg`) are mapped to canonical
dictionary item IDs via a `flrcif_item_id` field in a renamed internal parameter
registry, and parameters missing from the standard dictionary are added to the
extension `.dic`. Export logic then emits each parameter under its canonical
flrCIF identifier and category rather than the internal short name.

# Status
Done (2026-08-08). Export alignment is delivered and tested: the internal
registry maps to dictionary items, the extension dictionary carries the
ChiSurf-specific parameters absent from the standard, and the alignment script
now **updates existing** saveframe descriptions (not just appends missing ones),
with a drift guardrail test (`test_registry_and_dictionary_descriptions_do_not_drift`)
that fails if the registry and dictionary fall out of step. The registry is the
de-facto source of truth (it drives GUI tooltips and doc generation); the
alignment script propagates it into the `.dic` so the archive matches.

# Goal
Ensure that parameters exported from ChiSurf to `mmfdb` strictly adhere to the
flrCIF standard. The flrCIF dictionaries (and the local `mmfdb_flr_ext.dic`
extension) are the **canonical source of truth** for parameter definitions;
ChiSurf's internal short abbreviations must be mapped to these standard
definitions so that stored data matches flrCIF exactly.

# Background
ChiSurf internally uses short abbreviations (e.g. `E_FRET`, `bg`) defined in
`chisurf/core/settings/constants/fitting_parameters.json` with their
descriptions. Since these are not exclusively "fitting" parameters, the registry
should be renamed to `parameter_registry.json`. flrCIF is the public standard for
archiving fluorescence data, and MMFDB's schema mirrors it, so exports must match
strict flrCIF naming. To avoid duplication, the `.dic` files remain canonical:
the JSON registry is internal-only and maps internal short names to canonical
`.dic` parameter IDs rather than dictating `.dic` contents.

# Requirements
1. **`.dic` as canonical source** — the standard flrCIF dictionary (and
   `mmfdb_flr_ext.dic` for extensions) is the absolute source of truth for
   parameter definitions, names, and descriptions; the JSON registry maps
   internal short names to flrCIF parameter IDs.
2. **Add missing parameters to `.dic`** — identify ChiSurf parameters absent
   from the standard dictionary and add them to
   `modules/mmfdb/src/mmfdb/data/mmfdb_flr_ext.dic`, strictly following flrCIF
   formatting and naming. The short names/descriptions in the JSON registry help
   draft the initial entries, but the `.dic` then becomes canonical.
3. **Map internal short names to flrCIF** — add a `"flrcif_item_id"` field to
   the JSON registry (e.g. `"flrcif_item_id": "_flr_chisurf_parameter.E_FRET"`).
4. **Update export logic** — when a short-named parameter is exported from
   ChiSurf to MMFDB, write it under its canonical flrCIF identifier and category.

# Implementation steps
**Step 1 — Rename and audit the registry.** Rename
`fitting_parameters.json` → `parameter_registry.json` and update all references:
`chisurf/core/settings/__init__.py` (loaded filename + `fitting_parameters` →
`parameter_registry` variable); `chisurf/core/parameter.py` (~line 372,
`getattr(chisurf.core.settings, "parameter_registry", {})`); the
`build_tools/dev_utils/` export/fill scripts; and
`docs/parameter_registry_tools.rst`.

**Step 2 — Extend `mmfdb_flr_ext.dic`.** Write
`build_tools/dev_utils/align_flrcif_parameters.py` to read
`parameter_registry.json`, check each short name against standard flrCIF, and
auto-generate + append `.dic` entries for the missing ones. Example:

> **Historical note (2026-09-03):** `flr_chisurf_parameter` was renamed
> `flr_fit_parameter` — dictionary keywords are software-agnostic by
> rule. The snippets below show the original spelling.

```text
save__flr_chisurf_parameter.E_FRET
   _item.name                "_flr_chisurf_parameter.E_FRET"
   _item.category_id         flr_chisurf_parameter
   _item_type.code           float
   _mmfdb_schema.table_name  flr_chisurf_parameter
   _mmfdb_schema.column_name e_fret
   _item_description.description
;     Apparent FRET efficiency parameter E_FRET (0e00..1).
;
```

The schema-binding tags are the store-keyed `_mmfdb_schema.*` ones; the
application-branded `_chisurf_schema.*` spelling this PRD originally generated
was retired by [PRD-44](prd-44.md).

Ensure a matching category definition `save_flr_chisurf_parameter` exists.

**Step 3 — Create the mapping in `parameter_registry.json`.** The same script
modifies the JSON in place, adding `"flrcif_item_id"` to each parameter (e.g.
`E_FRET` → `_flr_chisurf_parameter.E_FRET`). To avoid duplication, prefer pulling
descriptions dynamically from the loaded `.dic` schema; the JSON `"description"`
field can become a fallback or be removed.

**Step 4 — Update export logic.** In the export mechanisms that save fitting
parameters and model results to MMFDB (typically `pdbx_metadata.py`,
`dictionary_schema_map.py`, or the MMFDB SQLAlchemy models), write each model
parameter using its canonical `flrcif_item_id` so the exported database mirrors
flrCIF.

**Step 5 — Tests (`test/fio/`).** Verify that all mapped parameters translate to
their `flrcif_item_id`, that the extended `mmfdb_flr_ext.dic` parses with the CIF
parser, and that exported MMFDB data validates against the combined flrCIF
dictionaries.

# Acceptance criteria
- [x] `fitting_parameters.json` renamed to `parameter_registry.json` and all references updated
- [x] `mmfdb_flr_ext.dic` contains standard-compliant definitions for all ChiSurf parameters missing from core flrCIF
- [x] `parameter_registry.json` has a `"flrcif_item_id"` field linking each internal short name to the canonical `.dic` item
- [x] Parameter-description duplication minimized/eliminated by treating `.dic` files as canonical
- [x] The ChiSurf → MMFDB export correctly translates internal short names into standard flrCIF identifiers

As built, the alignment injected `flrcif_item_id` mappings from ChiSurf's
internal abbreviations to 230 generated standard-compliant entries in
`mmfdb_flr_ext.dic`, and export routes through
`chisurf/core/project/mmfdb_adapter.py`, which injects
`resolve_parameter_name` as the `parameter_name_resolver` of
`mmfdb.adapters.chinet`, so internal abbreviations do not pollute external
archives. `test/fio/test_flrcif_alignment.py` passes (18/18).

# Remaining work

**Closed (2026-08-08).** The alignment script's `process()` now compares each
existing saveframe's `_item_description.description` against the registry text
and rewrites it when they differ (`update_dic_descriptions`). The drift
guardrail `test_registry_and_dictionary_descriptions_do_not_drift` enforces
agreement. The registry owns the text (it is what the GUI tooltips and
`build_tools/docs/generate_plugin_docs.py` render); the alignment script
propagates it into the `.dic`, so there is one editable source and one
test-enforced sync path rather than two independent copies.

# Relationships
- Builds on the dictionary API from [PRD-02a](prd-02a.md) and the sample model from [PRD-02](prd-02.md).
- Emits the vendor-neutral schema-binding namespace defined by [PRD-44](prd-44.md).
- Enforces dictionary-as-authority for export in the [MMFDB (current)](/architecture/mmfdb.md) store toward the [MMFDB target](/specs/mmfdb.md).
