---
type: Concept
title: 'The measurement database: records, provenance and who may change them'
description: What the MMFDB stores about samples, experiments and data, why the derivation of every product is kept as a graph of operations and artifacts, and how the vocabulary and the access rules are fixed.
tags: [concepts, database, provenance, mmcif]
anchor: concept-measurement-database
---

(concept-measurement-database)=
# The measurement database: records, provenance and who may change them

A fluorescence result rests on more than its numbers. It depends on the sample
(the molecule, its labels, the buffer), the instrument (the setup, its detector
channels and PIE windows), the raw data, and every processing step between the
raw data and the number. The Multiparametric Fluorescence Database (MMFDB) keeps
all of these as records, so that a result can be traced back to what it was
measured on.

## Records come from a dictionary

The MMFDB tables are not designed by hand. They are **generated from mmCIF
dictionaries**: the wwPDB / PDB-IHM family, the FLR dictionary for fluorescence
restraints, and a local extension for what the others lack. A sample's *Solvent
Phase* is the same `_flr_sample.solvent_phase` item a deposition uses, and a
field's help text is the item's dictionary definition. Two consequences follow.
A record exports to an FLR / PDBx CIF file without translation. And the
vocabulary is shared: a new quantity becomes a new dictionary item, never a
column that exists in one tool only.

## Provenance is a graph

Each processing step is recorded as an **operation** with its settings. Each
thing it reads or writes is an **artifact**, and each relationship is an
**edge** (`input_to`, `produced`). Raw data enters as an artifact. A burst
search is an operation that consumes it and produces a burst table, and a fit is
an operation that consumes that table and produces parameters. Asking *where did
this product come from* walks the graph upstream to the raw data. Asking *what
was computed from this file* walks it downstream.

Provenance is kept as a graph, not a list, because steps join. A burst-wise
lifetime fit reads both the bursts and the background estimate. A tree would
have to repeat a node or drop an edge, while a directed acyclic graph records
both inputs.

Records are never overwritten silently. Deleting an artifact is a *soft* delete
that also removes its direct links. Branches let a user restart from a recorded
operation without losing the history before it.

## Who may change what

Every change goes through the MMFDB server, and the server checks the caller:
it authenticates the session, then applies per-record ownership and group
permissions. The client cannot bypass these rules. Administrators can manage
users, reset passwords and administer every table. A database with no
administrator yet (a fresh installation) is open to anyone, so that the first
administrator can be created.

## Where to go next

- {doc}`Administering the measurement database </guides/102_mmfdb_admin>`: the
  MMFDB Admin tool, step by step.
- {doc}`The photon container </concepts/photon_container>`: the same provenance
  model, inside a single measurement file.
