# Zenodo deposit

Every record that goes to Zenodo is checked here first, item by item. Nothing leaves the machine until you have approved everything it holds, and nothing is published until you approve that too.

## Create -- a record by hand, in four steps
*0 · Create* walks you through it; the banner at the top always names the step you are on.

1. **New record** -- a name (lower case, no spaces: it becomes the folder and the archive) and a title. *Create record* makes the empty folder with `measurements/` and `calibrations/` under the data root and opens it.
2. **Add data** -- choose *Measurement* or *Calibration*, name the item (one folder, e.g. `2014-08-12_0M-urea`; a calibration also names its group, the setup and day it calibrates, e.g. `2014-08-12_pq-hydraharp`), then *Add files…* or *Add folder…*. Files are hard-linked when they are on the same disk (no second copy), copied otherwise; nothing is ever overwritten. Files you put into the folder yourself (*Show in Finder*) count too.
3. **Zenodo metadata** -- title, type, date, access and license, creators (one per line: `Family, Given; Affiliation; ORCID`), description, keywords, related identifiers (e.g. `isSupplementTo` and the paper's DOI). It is checked as you type; what is missing is listed under the form. *Sent to Zenodo (JSON)* shows exactly what the upload sends.
4. **Scan for review** -- the record's items, ready for *1 · Review*.

The metadata is reviewed like any folder: approve the item *Zenodo metadata*. Any later edit voids that approval -- the upload carries only metadata you approved.

**Advanced · Build from a project script** is for projects whose records a script generates from a config (T4L): pick the config, *Build record*; it links the raw data, writes the burst-analysis containers, generates and validates `metadata.cif` and scans the record. A record built this way takes its Zenodo metadata from the config -- edit it there, not in step 3.

## Records
A record is a folder that becomes one Zenodo entry, uploaded as one archive. Its review state lives beside it as `<record>.deposit.json`, so the review is never shipped with the data. The data root is usually an external disk: all data passes through this machine for review.

## Items
One row per unit of review: each `measurements/<date>_<condition>` folder, each `calibrations/<date>_<setup>/<sample>` folder, and each metadata file (README, flrCIF `metadata.cif`, `origins.json`, the checksum manifest). A ⚠ marks an item the builder could not decide on its own -- data added beyond the obvious, or a role inferred rather than recorded (for example a folder taken as the clean-water scatter because the burst analysis used it as such). Look at those first; hover a row to read why.

## Look before you approve
The code editor below the buttons fills the rest of the window: a folder lists every file it holds with its size; `metadata.cif` (mmCIF), `origins.json` (JSON) and the README are shown read-only with highlighting. **Open in ndX** opens the selected item's burst-analysis container (`.mmfdb.pto`) in ndX, to look at the bursts themselves.

## Your decision is bound to the content
Approve an item with the button on its row; right-click a row to Reject it, Undo the decision or open it in ndX (a double click opens it too). The Note under the item is stored with your next decision. Hover a row for its content, where it came from and the review so far. An approval records the item's content digest: when anything in the item changes later, it shows as **Pending (changed)** and must be approved again. Rescan re-reads the folder after a change.

## Upload
The Zenodo metadata at the top of *2 · Upload* is what is submitted with the draft -- the version you approved in *1 · Review*.

Build package writes the archive from the record as it is now. Upload draft is grey until every item is approved and the package was built from exactly that content; it uploads into a Zenodo **draft** and checks the file's md5 there. Check Zenodo reads the draft back and compares it with the local package at any later time. The sandbox switch sends everything to sandbox.zenodo.org for a trial run.

## Publish
Publishing is irreversible. It needs its own approval (Approve publish), bound to the md5 of the package in the draft, and a draft that matches it; a rebuilt package voids the approval.

## Same path from a terminal
`python -m mmfdb.deposit new|add|metadata|scan|status|review|package|upload|check|approve-publish|publish` uses the same review file and the same gate. The token is read from `ZENODO_TOKEN`.
