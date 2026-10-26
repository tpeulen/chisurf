---
type: Concept
title: Metadata records — typed fields plus free-form extras
description: The one metadata model behind every ChiSurf tool that carries metadata — a schema of typed, validated fields, free key/value extras beside it, and a flat string mapping handed back to the host.
tags: [concepts, metadata, flrcif, zenodo]
---

# Metadata records — typed fields plus free-form extras

A metadata record is a flat mapping of keys to text: pH, temperature, buffer of
a measurement; title, creators, license of a deposit. Tools that carry metadata
do not each grow their own key/value form. One model and one editor serve all of
them ({src}`chisurf/plugins/core/metadata_editor/core.py`, package `chisurf/plugins/core/metadata_editor/`): the **Metadata Editor**
plugin, hosted standalone or embedded in another tool's window.

## Schema and extras

A **schema** (`Schema`) is an ordered, immutable tuple of typed fields
(`Field`); keys must be unique. Each field has:

| Attribute | Meaning |
| --- | --- |
| `key` | the entry's key in the record (required) |
| `label` | display label; empty → the key with `_` as spaces, an all-lower-case key with a capital first letter (`upload_type` → *Upload type*); a key already cased is kept (`pH`) |
| `kind` | `str`, `text` (multi-line), `int`, `float`, `date`, or `choice` |
| `options` | the allowed values of a `choice` (a `choice` without options is rejected) |
| `required` | the entry must not be empty; drawn with a trailing `*` |
| `placeholder`, `help` | input hint and tooltip |
| `parts`, `part_sep` | the stored value is a list of records: one per line, the values of these keys in this order joined by `part_sep` (default `; `) |
| `list_sep` | the stored value is a list of strings joined by this separator |

Everything in a record that is not a schema key is an **extra**: a free
key/value pair, kept in order and edited through the *Add key* / *Add value*
row. Adding an extra whose key is a schema key edits that field instead;
adding an existing extra key replaces its value.

Three schemas ship:

| Schema | Factory | Typed fields |
| --- | --- | --- |
| free-form | `freeform_schema()` | none — every entry is an extra |
| flrCIF | `flrcif_schema(extra_keys=())` | `pH`, `temperature` [K], `ionic_strength` [mM], `buffer_composition`, `solvent_phase`, `labeling_efficiency`, `donor_only_fraction`, `acceptor_only_fraction`; *extra_keys* join as plain strings |
| Zenodo | `zenodo_schema()` | `title`*, `upload_type` (choice), `publication_date` (date), `description` (text), `creators`* (records `name; affiliation; orcid`, one per line), `keywords` (list, `, `), `license`, `access_right` (choice), `embargo_date` (date), `version`, `related` (records `relation identifier`, one per line) |

`*` = required.

## Validation

`EditorModel.errors()` maps each failing key to a message; an empty dict means
the record checks out. The rules, applied to the stripped text:

- a required field that is empty → *"<Label> is required."* (no further check);
- an empty optional field is not checked;
- `int` must parse with `int()`, `float` with `float()` (so `150 mM` fails —
  units belong in the field's definition, not the value);
- `date` must be `YYYY-MM-DD` and a real calendar day (`2026/10/26`,
  `20261026` and `2026-02-30` fail).

Extras are never validated. While any error stands, **Apply** is disabled.

## What a host gets back

`EditorModel.entries()` returns every non-empty entry — schema fields and
extras merged, extras winning on a key clash — as **strings**: a `float` field
is validated as a number but handed back as its text (`"7.5"`). Loading
converts the other way: `None` becomes empty, a list becomes text in its field's
declared shape — Zenodo creators one person per line,
`Family, Given; Affiliation; ORCID`, a missing middle part left empty
(`Doe, Jane; ; 0000-…`) so the parts stay in place; keywords joined with `, `. A
list under a key with no declared shape becomes one line per item.
`EditorModel.structured_entries()` parses the shaped fields back, so a record
read and written again keeps its lists and records.

The model never writes anything itself. **Apply** hands `entries()` to the
host's callback; **Cancel** leaves the host's store as it was. An embedded
editor closes on either; the standalone window (`keep_open=True`) stays on the
record — after Apply on the applied entries, after Cancel on what it was opened
with. The host decides what applying means:

| Host | Schema | On Apply |
| --- | --- | --- |
| Burst Selection — *Metadata* | `flrcif_schema()` over the analysis metadata | every entry set, every key missing from the result deleted; written with the next *Export flrCIF* |
| Zenodo deposit — *Zenodo metadata* panel | `zenodo_schema()` over the selected record | known deposit fields set, other keys stored as record metadata; an edit voids the metadata's approval ({doc}`data_deposition`) |
| Metadata Editor (standalone) | free-form, flrCIF or Zenodo | written to the open JSON file (`structured_entries()`); the editor stays on it |

## File format

The standalone editor reads and writes a single JSON object, indented by two
spaces; values are strings, shaped fields lists:

```json
{
  "pH": "7.5",
  "temperature": "295.15",
  "buffer_composition": "50 mM HEPES, 150 mM NaCl, 1 mM TCEP",
  "operator": "TP"
}
```

A file whose top level is not an object is refused. Switching the schema keeps
what has been typed: entries that match the new schema's keys become its
fields, the rest stay extras.

Workflow: {doc}`../guides/113_metadata_editor`.
