---
type: Architecture
title: Declarative analysis definitions
description: The inputs, outputs and computed feature set of every analysis pipeline are declared in a settings file beside the code, never hardcoded — so a schema can drift without a code change. One flat declaration per analysis; no framework layers.
resource: chisurf/core/fio/fluorescence/burst_features.yaml
tags: [architecture, settings, features, burst, mle, imaging, rule]
timestamp: '2026-09-03T00:00:00Z'
---

# Where to pick this up

1. **Converted (2026-09-03)**: the `.bur` burst-summary schema
   (`chisurf/core/fio/fluorescence/burst_features.yaml`, walked by
   `generate_burst_dataframe`; cell-for-cell parity pinned in
   `test/fio/test_burst_feature_declaration.py`, which also proves a
   dropped column actually drops); the pixel-MLE legacy export
   (`plugins/microscopy/img_pixel_mle/core/result_columns.yaml` — only
   fit23 needs a file; every other model's schema *is* the tttrlib
   parameter registry); the region-MLE shape features
   (`plugins/microscopy/region_mle/core/result_columns.yaml`, one list
   serving the fitted table and the preview).
2. **Next**: `imaging/pixel_maps.py` — the `kind` if/elif chain and each
   branch's fixed map-name dict; the meaningful conversion is a
   requested-kinds list plus declared output-map names per kind (a run
   currently cannot even ask for a *set* of maps), and
   `MFD_INTENSITY_COLUMNS` (line ~452) belongs in the same declaration.
3. Then sweep: any new analysis lands with its declaration from day one;
   any touched analysis converts in the same change (the same
   walk-past-it rule as chiplot).

# The rule (owner, 2026-09-03)

> "The input/output definitions and what is actually computed in a burst,
> mle, image analysis etc must be coded in some settings files, along with
> the computed features, so that it can drift without code changes. This
> is a general rule — no hardcoding there. Also do not make too many
> abstraction layers."

Two halves, and the second constrains the first:

- **Declared, not coded.** Which features an analysis computes, under
  which output names, in which order — that is configuration. A feature
  set spelled in code is spelled at least twice (writer and reader, or
  header list and filler), and the copies drift; the `.bur` writer
  carried a diverged duplicate (`Mean Macro Time` vs `Mean Macrotime`)
  for exactly this reason.
- **Flat.** One declaration file per analysis, beside the code that walks
  it (the `view.json` precedent). The *quantity vocabulary* — what a
  `source` name means, its arithmetic, its empty-value sentinel — stays
  in code, in one plain function per scope: algorithms are code,
  selections are settings. No registry classes, no plugin framework, no
  schema-of-schemas. A brand-new quantity is one `elif` plus its
  declaration line.

# The shape that works

```
analysis code
  └── walks ──> <analysis>_features.yaml     (names, order, instantiation)
                  └── source: names into ──> one flat vocabulary function
```

- **Families over instances**: the declaration holds column *templates*
  (`"S {window} {detector} (kHz)"`); the instances come from the
  measurement configuration that already exists (`detector_setups.json`).
  The setup declares how many; the features file declares what.
- **A registry can be the declaration.** `mle/fit2x.py` needs no file:
  its columns come from `tttrlib.decay_fit_parameter_names` /
  `result_names`, and adding an engine result column reaches chisurf with
  no edit. A file is for layouts *history* fixed (fit23's export), not
  for schemas an engine already owns.
- **Sentinels are semantics, not layout** — they stay with the vocabulary
  function (`_SPAN_EMPTY`), because "what does empty mean for this
  quantity" is part of the quantity.
- **A format schema is still a format.** Declaring it does not license
  changing it: the `.bur` columns are parsed back by name downstream
  (ndxplorer, the MFD reader's setup inference), so a rename in the YAML
  is a format change and the readers move with it. The declaration makes
  drift *possible and reviewable*, not free.

# Cost, measured

The `.bur` writer pays ~9% for the declaration walk (108.9 → 118.3 ms
for 3000 bursts, fair A/B against the old function whole) — once per
analysed measurement, not per iteration; accepted for the schema being
editable without a release.
