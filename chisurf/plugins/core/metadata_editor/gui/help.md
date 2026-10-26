# Metadata editor

One editor for every metadata record: typed fields from a schema plus free key/value entries,
validated before they are applied. Burst Selection (the flrCIF metadata of an export) and the Zenodo
deposit (a record's metadata) embed it; this window edits a JSON metadata file on its own.

## How it works
1. Pick the **Schema**: *free-form* (no typed fields), *flrCIF* (pH, temperature, ionic strength,
   buffer, solvent, labelling fractions) or *Zenodo* (title, creators, license, dates, ...).
   Switching keeps what has been typed.
2. **Open…** a `.json` file holding one object. Schema keys fill the fields; every other key is a
   free entry. Add more with *Add key* / *Add value* and **Add entry**; select a table row and press
   Delete to remove one.
3. Fix what is listed in red (a number that is not a number, a date that is not `YYYY-MM-DD`, a
   required field left empty) — **Apply** stays grey until the list is empty.
4. **Apply** writes the open file and the editor stays on it; **Cancel** reverts to what is on disk;
   **Save as…** writes a new file and makes it the open one.

## Before trusting a result
Values are stored as text, as typed: a number field is checked, not converted, and units belong in
the field's meaning, not the value (`150 mM` fails a number field). Zenodo creators are one person
per line, `Family, Given; Affiliation; ORCID`; they are written back as a list.

Further reading: [Metadata editor](docs/concepts/metadata_editor.md),
[Editing metadata](docs/guides/113_metadata_editor.md).
