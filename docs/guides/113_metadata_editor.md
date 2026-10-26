---
type: Guide
title: Editing a metadata record
description: Open, edit, check and save a JSON metadata record in the Metadata Editor, and use the same editor inside Burst Selection and the Zenodo deposit.
tags: [guides, metadata, flrcif, zenodo]
---

# Editing a metadata record

**File › Data › Metadata Editor** ({src}`chisurf/plugins/core/metadata_editor/gui/app.py`). Theory:
{doc}`../concepts/metadata_editor`.

The same editor sits inside every tool that has metadata; standalone it edits
one JSON file.

## 1. Pick a schema and open a file

```{figure} figures/113_metadata_editor_flrcif.png
:width: 100%

The *flrCIF* schema over an opened `metadata.json`: the typed fields filled,
*Ionic strength* typed with its unit and reported (*must be a number*), so
**Apply** is grey. The table lists every entry, the two extras (`operator`,
`sample_id`) below the schema fields.
```

1. **Schema.** *free-form* (no typed fields), *flrCIF* (the analysis metadata
   of a burst export) or *Zenodo* (a deposit). Switching keeps what has been
   typed. **Guide** walks these steps on the real controls; **?** opens the
   help.
2. **Open…** a `.json` file. It must hold one JSON object; anything else is
   reported in red under *File:*. Its keys fill the schema's fields; every
   other key becomes an extra.

## 2. Edit and check

- Type into the fields. A `*` marks a required field; dates take
  `YYYY-MM-DD`, a real calendar day (calendar button beside the field). Zenodo
  creators are one person per line, `Family, Given; Affiliation; ORCID` (leave a
  part empty between the `;` rather than dropping it).
- **Further entries.** *Add key* + *Add value*, then **Add entry** adds the
  pair, or replaces the value when the key exists (a schema key edits that
  field). To remove an entry, select its row in the table and press Delete.
- Every check that fails is listed in red above the buttons; **Apply** stays
  grey until the list is empty. Extras are never checked.

```{figure} figures/113_metadata_editor_zenodo.png
:width: 100%

The *Zenodo* schema on a new record (*File: no file*): upload type, date,
license and access filled, the two required fields still empty and reported.
```

## 3. Save

- **Apply** writes the entries into the open file (two-space indented JSON;
  values as text, creators/keywords/related back as lists) and the editor stays
  on it — *Written to …* beside the file name. Without an open file, Apply asks
  for one.
- **Save as…** writes the entries to a new file and makes it the open one —
  the way to save a record that started without a file.
- **Cancel** reverts the form to the file as last opened or applied; nothing
  is written.

## Inside other tools

- **Burst Selection** → toolbar **Metadata**: the flrCIF schema over the
  analysis metadata; *Apply* replaces the stored entries (keys you removed are
  deleted) and *Export flrCIF* writes them with the burst table
  ({doc}`34_exporting_burst_data`).
- **Zenodo deposit** → Create tab, *Zenodo metadata* panel: the Zenodo schema
  over the selected record; an edit voids the metadata's approval
  ({doc}`109_zenodo_deposit`).

## Python

```python
from chisurf.plugins.core.metadata_editor.core import EditorModel, flrcif_schema

model = EditorModel(flrcif_schema(), {"pH": "7.5", "operator": "TP"})
model.values["temperature"] = "295.15"
model.extra_key, model.extra_value = "sample_id", "T4L-S44pAcF-I150C"
model.add_extra()
assert model.errors() == {}
record = model.entries()   # {'pH': '7.5', 'temperature': '295.15', 'operator': 'TP', 'sample_id': ...}
```

To embed the editor in a tool, draw
`MetadataEditorWidget(on_apply=..., on_cancel=...)`
({src}`chisurf/plugins/core/metadata_editor/gui/widget.py`): `open(schema, initial)`
fills it, `draw()` draws the body into the host's panel, and the callback
receives `entries()` on Apply.

Figures: `docs/guides/screenshots/metadata_editor_shot.py`.
