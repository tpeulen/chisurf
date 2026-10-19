# Zenodo deposit

Every record that goes to Zenodo is checked here first, item by item. Nothing leaves the machine until you have approved everything it holds, and nothing is published until you approve that too.

## Records
A record is a folder that becomes one Zenodo entry, uploaded as one archive. Its review state lives beside it as `<record>.deposit.json`, so the review is never shipped with the data. The data root is usually an external disk: all data passes through this machine for review.

## Items
One row per unit of review: each `measurements/<date>_<condition>` folder, each `calibrations/<date>_<setup>/<sample>` folder, and each metadata file (README, flrCIF `metadata.cif`, `origins.json`, the checksum manifest). A ⚠ marks an item the builder could not decide on its own -- data added beyond the obvious, or a role inferred rather than recorded (for example a folder taken as the clean-water scatter because the burst analysis used it as such). Look at those first; hover a row to read why.

## Your decision is bound to the content
Approve, Reject or Reset the selected item, with an optional note. An approval records the item's content digest: when anything in the item changes later, it shows as **Pending (changed)** and must be approved again. Rescan re-reads the folder after a change.

## Upload
Build package writes the archive from the record as it is now. Upload draft is grey until every item is approved and the package was built from exactly that content; it uploads into a Zenodo **draft** and checks the file's md5 there. Check Zenodo reads the draft back and compares it with the local package at any later time. The sandbox switch sends everything to sandbox.zenodo.org for a trial run.

## Publish
Publishing is irreversible. It needs its own approval (Approve publish), bound to the md5 of the package in the draft, and a draft that matches it; a rebuilt package voids the approval.

## Same path from a terminal
`python -m mmfdb.deposit status|review|package|upload|check|approve-publish|publish <record>` uses the same review file and the same gate. The token is read from `ZENODO_TOKEN`.
