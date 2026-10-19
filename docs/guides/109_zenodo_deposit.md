---
type: Guide
title: Uploading a record to Zenodo
description: Review a deposition record item by item in the Zenodo deposit tool, then upload it as a draft and publish it.
tags: [guides, zenodo, deposit]
---

# Uploading a record to Zenodo

**File › Data › Zenodo deposit** ({src}`chisurf/plugins/core/zenodo_deposit/gui/app.py`). Theory:
{doc}`../concepts/data_deposition`.

The banner at the top always names the **one next step**; follow it and
nothing can be skipped.

## 0. Make the record

```{figure} figures/109_zenodo_deposit_create.png
:width: 100%

The Create tab, four steps: a new record, its data (here one measurement and one
calibration, hard-linked), the Zenodo metadata -- checked as it is typed, the
missing fields listed under the form -- and the scan for review.
```

1. **New record.** A name (lower case, no spaces; it becomes the folder and the
   archive name) and a title; *Create record* makes the empty record under the
   data root and opens it.
2. **Add data.** *Measurement* or *Calibration*, the item's folder name (a
   calibration also its group: setup and day, e.g. `2014-08-12_pq-hydraharp`),
   then *Add files…* or *Add folder…*. Files are hard-linked on the same disk,
   copied otherwise, never overwritten; where they came from is kept in the
   review file and shown as the item's origin.
3. **Zenodo metadata.** Title, type, date, access, license, creators (one per
   line: `Family, Given; Affiliation; ORCID`), description, keywords, related
   identifiers (`isSupplementTo 10.xxxx/...` for the paper). *Sent to Zenodo
   (JSON)* shows exactly what is sent.
4. **Scan for review.**

The metadata is the item *Zenodo metadata* in the review: it must be complete
(an incomplete one blocks the upload whatever the review says) and approved,
and any later edit voids the approval -- only approved metadata is sent.

**Advanced · Build from a project script.** A project whose records are
generated from a build config (one JSON per record) picks the config and
presses *Build record*: raw data linked, containers written, `metadata.cif`
generated and validated against the mmCIF, IHM, IHM-FLR and mmfdb dictionaries
(a non-conforming one fails the build and blocks the upload), record scanned.
Such a record takes its Zenodo metadata from the config.

## 1. Pick a record and review it

```{figure} figures/109_zenodo_deposit_review.png
:width: 100%

The Review tab: one row per item, flagged items marked in the Check column.
The selected metadata file is shown read-only in the code editor (mmCIF
highlighting for `metadata.cif`, JSON for `origins.json`).
```

Click a record (a folder never scanned is scanned when opened), then click
each item. Start with the flagged ones: hover a row or read the panel below
the table for why it is flagged, where it came from on the server, and which
files it holds. The code editor under the buttons lists a folder's files with sizes, or shows a metadata file; **Open in ndX** opens the item's `.mmfdb.pto` to look at the bursts. Then **Approve** or **Reject**, optionally with a note. Changing a
folder after approving it puts it back to *Pending (changed)* — press
*Rescan folder* after any change.

## 2. Build and upload

```{figure} figures/109_zenodo_deposit_upload.png
:width: 100%

The Upload tab: the Zenodo metadata that is submitted (title, creators,
license, keywords, description), then what still blocks the upload; *Upload
draft* stays grey until the list is empty.
```

*Build package* writes the archive (stored ZIP, every member CRC-checked).
*Upload draft* sends it into a Zenodo **draft** and compares its MD5; nothing
is published. *Check Zenodo* compares the draft with the local package at any
time. Tick *Trial run on the Zenodo sandbox* for a test against
sandbox.zenodo.org.

## 3. Token

In the *Zenodo token* tab, paste a personal access token (scopes
`deposit:write`, `deposit:actions`) and press *Save to keychain*; *Test token*
asks Zenodo whether it works.
The tool does not read the keychain just to open: until a press needs the
token (*Test token*, upload, *Check Zenodo*, *Publish*) the tab says it has not
been looked up yet, so opening the window never triggers a keychain prompt.

## 4. Publish

Look at the draft on Zenodo. When it is right, *Approve publish* (bound to
this package's MD5) and *Publish (irreversible)*.

## Terminal

```bash
python -m mmfdb.deposit new      /path/to/records <record> --title "..."
python -m mmfdb.deposit add      /path/to/records/<record> raw/run1 --as measurement --name 2014-08-12_0M-urea
python -m mmfdb.deposit add      /path/to/records/<record> raw/irf.ht3 --as calibration --name irf --group 2014-08-12_hydraharp
python -m mmfdb.deposit metadata /path/to/records/<record> --set zenodo.json   # prints what is missing
python -m mmfdb.deposit scan     /path/to/records/<record>
python -m mmfdb.deposit status   /path/to/records/<record>
python -m mmfdb.deposit review   /path/to/records/<record> <item-id> --note "checked"
python -m mmfdb.deposit package  /path/to/records/<record> /path/to/zips
python -m mmfdb.deposit upload   /path/to/records/<record>
```

## Python

```python
from mmfdb.deposit import scan, blockers, build_package, upload, ZenodoClient
from mmfdb.deposit.compose import new_record, add_data, zenodo_problems

rec = new_record("records", "my-record", title="...")
add_data(rec, ["raw/run1"], "measurement", "2014-08-12_7.5M-urea")
rec.metadata.update(creators=[{"name": "Family, Given"}], description="...")
print(zenodo_problems(rec.metadata))  # [] when complete
rec = scan(rec.folder, metadata=rec.metadata)
rec.approve("measurements/2014-08-12_7.5M-urea", note="checked")
build_package(rec, "zips")
print(blockers(rec))                  # [] when cleared
upload(rec, ZenodoClient())           # draft only
rec.save()
```
