# Zenodo deposit

Every record that goes to Zenodo is checked here first, item by item. Nothing leaves the machine until you have approved everything it holds, and nothing is published until you approve that too.

## Create -- a record by hand
*1 · Create* holds the panels *New record*, *Add data*, *Zenodo metadata* and *Scan for review*; the banner at the top always names the one thing to do next.

- **New record** -- a name (lower case, no spaces: it becomes the folder and the archive) and a title. *Create record* makes the empty folder with `measurements/` and `calibrations/` under the data root and opens it.
- **Add data** -- choose *Measurement* or *Calibration*, name the item (one folder, e.g. `2014-08-12_0M-urea`; a calibration also names its group, the setup and day it calibrates, e.g. `2014-08-12_pq-hydraharp`), then *Add files…* or *Add folder…*. Files are hard-linked when they are on the same disk (no second copy), copied otherwise; nothing is ever overwritten. Files you put into the folder yourself (*Show in Finder*) count too.
- **Zenodo metadata** -- title, type, date, access and license, creators (one per line: `Family, Given; Affiliation; ORCID`), description, keywords, related identifiers (e.g. `isSupplementTo` and the paper's DOI). It is checked as you type; what is missing is listed under the form. *Sent to Zenodo (JSON)* shows exactly what the upload sends.
- **Scan for review** -- the record's items, ready for *2 · Review*.

The metadata is reviewed like any folder: approve the item *Zenodo metadata*. Any later edit voids that approval -- the upload carries only metadata you approved.

**Advanced · Build from a project script** is for projects whose records a script generates from a config (T4L): pick the config, *Build record*; it links the raw data, writes the burst-analysis containers, generates and validates `metadata.cif` and scans the record. A record built this way takes its Zenodo metadata from the config -- edit it there, not in the form.

## Records
A record is a folder that becomes one Zenodo entry, uploaded as one archive. Its review state lives beside it as `<record>.deposit.json`, so the review is never shipped with the data. The data root is usually an external disk: all data passes through this machine for review.

## Items
One tree of review: each `measurements/<date>_<condition>` folder, each `calibrations/<date>_<setup>/<sample>` folder, and each metadata file (README, flrCIF `metadata.cif`, `origins.json`, the checksum manifest) -- with every folder's files nested under their item (a numbered rollover series as one foldable row). Double click a file to view it; double click an item to open it in ndX. A ⚠ marks an item the builder could not decide on its own -- data added beyond the obvious, or a role inferred rather than recorded (for example a folder taken as the clean-water scatter because the burst analysis used it as such). Look at those first; hover a row to read why.

## Look before you approve
Double click a file row in the tree to open it in a modal viewer: text, `metadata.cif` (mmCIF), `origins.json` (JSON), the manifest and the README with highlighting or rendered Markdown; a numbered rollover series opens its first file; TTTR photon files open in the inspector; binary raw data shows a short info card (its parameters live in the sidecar JSON and the protocol, its checksum in the manifest). Double click an item row (or **Open in ndX** in the right-click menu) to look at the item's burst-analysis container (`.mmfdb.pto`) in ndX.

## Your decision is bound to the content
Approve an item with the button on its row; right-click a row to Reject it, Undo the decision or open it in ndX (a double click opens it too). The Note under the item is stored with your next decision. Hover a row for its content, where it came from and the review so far. An approval records the item's content digest: when anything in the item changes later, it shows as **Pending (changed)** and must be approved again. Rescan re-reads the folder after a change.

## Upload
*Before upload* names every file operation the upload would run now: what is sent, what replaces a changed file, what is identical already on the draft, and what would be deleted from it -- nothing leaves the machine until you press the upload button. Press *Check* (in *DOI & publish*) to compare the plan against the live draft.

The Zenodo metadata at the top of *3 · Upload* is what is submitted with the draft -- the version you approved in *2 · Review*.

Build package writes the archive from the record as it is now. With **Build the metadata separate** it leaves EVERY metadata file out of the archive -- the editable README.md and metadata.cif and the provenance, `origins.json` and `manifest_sha256.csv`, are uploaded beside it as sidecars (a real draft holds five files: the zip plus these four) -- so the raw archive stays byte-identical no matter how often you correct or regenerate them; the manifest hashes the editable files, so a correction carries its regenerated manifest along. Upload draft is grey until every item is approved and the package was built from exactly that content; it uploads into a Zenodo **draft** and checks the file's md5 there. **Swap metadata** updates an unpublished draft without sending the raw archive: the changed sidecars and the reviewed Zenodo metadata only -- each sidecar is compared independently, so a README correction sends the README and its regenerated manifest, and untouched provenance stays. It is grey while anything is unapproved (a metadata edit must be reviewed again), before the first upload, once the record is published (a published version is immutable; a correction is a new version), and when the draft does not hold the raw archive unchanged -- changed raw data always means: rebuild, then upload the archive. Check Zenodo reads the draft back and compares it with the local package at any later time. The sandbox switch sends everything to sandbox.zenodo.org for a trial run.

## Publish
Publishing is irreversible. It needs its own approval (Approve publish), bound to the md5 of the package in the draft, and a draft that matches it; a rebuilt package voids the approval.

## Same path from a terminal
`python -m mmfdb.deposit new|add|metadata|scan|status|review|package|upload|check|approve-publish|publish|migrate-remote` uses the same review file and the same gate. `package --separate-metadata` builds the archive without the editable metadata; `upload --metadata-only` swaps the draft's metadata without sending the raw archive (add `--dry-run` to see the plan first). The token is read from `ZENODO_TOKEN` (zenodo.org) or `ZENODO_SANDBOX_TOKEN` (sandbox.zenodo.org).
