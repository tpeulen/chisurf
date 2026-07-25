---
type: Concept
title: Measurement files
description: >-
  What the common file types contain, and how to tell a sample from a
  reference measurement before loading anything.
tags: [files, formats, readers, irf]
timestamp: '2026-07-25T00:00:00Z'
---

# Extensions are a hint, not a guarantee

| extension | usually | read as |
| --- | --- | --- |
| `.dat`, `.txt`, `.csv` | a decay or a curve, in columns | TCSPC text |
| `.pqres` | a PicoQuant result file | TCSPC |
| `.sdt` | a Becker & Hickl measurement | TCSPC |
| `.ptu`, `.ht3`, `.pt3`, `.spc` | a raw photon stream, not a curve | TTTR |
| `.cor`, `.asc`, `.sin`, `.fcs` | a correlation curve | FCS |
| `.dta`, `.dsc` | a DEER trace | DEER |
| `.pdb`, `.cif` | a structure | modelling |

A photon stream is not a curve: it is the raw arrival times, from which a
decay, a correlation curve or a burst analysis can be *derived*. Loading one
and expecting a decay is a category error.

# Telling samples from references

Instrument-response measurements live beside the samples they belong to and
are named for it: `irf`, `prompt`, `lamp`, sometimes `scatter`. They are
inputs to a fit, never things to fit. Fitting an IRF as if it were a sample
produces a meaningless "lifetime" and wastes the user's time.

Names also carry the experiment design, and are worth reading before asking:

* `D0`, `Donly`, `DOnly` — donor-only reference.
* `DA` — the donor–acceptor sample.
* `_ps`, `_ns` — time units of the axis.
* Repeated numbers with a suffix — usually repeats of one condition.

Pair samples with their own references by name, and **say what you assumed**.
A decay fitted against the wrong IRF is wrong in a way the chi-square may not
reveal.

# Before loading a folder

List it first. A folder often holds several experiment types, references,
already-processed exports and notes. Loading everything indiscriminately
produces a session where nothing can be told apart.
