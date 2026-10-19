---
type: Guide
title: Uploading a record to Zenodo
description: Review a deposition record item by item in the Zenodo deposit tool, then upload it as a draft and publish it.
tags: [zenodo, deposition, review, guide]
---

# Uploading a record to Zenodo

**File › Data › Zenodo deposit** (`zenodo_deposit` plugin). Theory:
{doc}`../concepts/data_deposition`.

The banner at the top always names the **one next step**; follow it and
nothing can be skipped.

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

The Upload tab lists what still blocks the upload; *Upload draft* stays grey
until the list is empty.
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

## 4. Publish

Look at the draft on Zenodo. When it is right, *Approve publish* (bound to
this package's MD5) and *Publish (irreversible)*.

## Terminal

```bash
python -m mmfdb.deposit status   /path/to/records/<record>
python -m mmfdb.deposit review   /path/to/records/<record> <item-id> --note "checked"
python -m mmfdb.deposit package  /path/to/records/<record> /path/to/zips
python -m mmfdb.deposit upload   /path/to/records/<record>
```

## Python

```python
from mmfdb.deposit import scan, blockers, build_package, upload, ZenodoClient

rec = scan("records/my-record")      # or DepositRecord.load(...)
rec.approve("measurements/2014-08-12_7.5M-urea", note="checked")
build_package(rec, "zips")
print(blockers(rec))                  # [] when cleared
upload(rec, ZenodoClient())           # draft only
rec.save()
```
