---
type: Concept
title: Depositing data — a reviewed path to Zenodo
description: How a record goes from a folder to a published Zenodo entry, and why every step that leaves the machine needs a person's approval bound to the content it approves.
tags: [concepts, data, deposition]
---

# Depositing data — a reviewed path to Zenodo

A **record** is a folder that becomes one repository entry, uploaded as one
archive: raw photon files, the analysis containers beside them, the
calibrations of each measurement day, and the metadata (README, flrCIF
`metadata.cif`, `origins.json`, a checksum manifest).

## Review is part of the data

Before anything leaves the machine a person checks it, and the check is
recorded beside the folder as `<record>.deposit.json` (never inside it, so the
review is not shipped). The record is split into **items** — each
measurement folder, each calibration folder, each metadata file — and every
item carries where it came from, what it holds, and the **flags** the builder
raised where it could not decide on its own (data added beyond the obvious, a
role inferred from analysis provenance rather than recorded).

An approval is **bound to the item's content digest**. If anything in the
item changes afterwards, the approval no longer applies and the item is
pending again: an approval of other bytes is not an approval of these.

## A record is made by hand or by a script

A record can be **composed by hand** -- an empty record, data put into it item
by item (hard-linked, never overwritten, the source remembered in the review
file), the Zenodo metadata typed in -- or **generated** by a project's build
script from a config. Both end in the same folder layout and the same review.

The repository's own metadata (title, creators, description, license) is what
the world reads first about the data, so it is an item too: machine-checked for
a complete deposition (`mmfdb.deposit.compose.zenodo_problems`), approved like
a folder, its approval void after any edit. The upload sends only the approved
metadata.

## The gate

`mmfdb.deposit.blockers` lists everything between a record and an upload:
every item approved at its current content, and a package built from exactly
that content. Upload creates a **draft** and compares the file's MD5 on the
repository with the local one. Publishing is irreversible and needs its own
approval, bound to the MD5 of the package in the draft.

The same gate serves the GUI ({doc}`../guides/109_zenodo_deposit`,
{src}`chisurf/plugins/core/zenodo_deposit/gui/app.py`) and the terminal
(`python -m mmfdb.deposit`).

## The token

The repository token lives in the operating system's credential store
(Keychain on macOS), one per repository host, with `ZENODO_TOKEN` as a
fallback — never in a file or in ChiSurf's settings.
