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
| `.cor`, `.asc`, `.sin` | a correlation curve | FCS |
| `.fcs` | a ConfoCor **measurement archive**, see below | FCS |
| `.dta`, `.dsc` | a DEER trace | DEER |
| `.pdb`, `.cif` | a structure | modelling |

A photon stream is not a curve: it is the raw arrival times, from which a
decay, a correlation curve or a burst analysis can be *derived*. Loading one
and expecting a decay is a category error.

# One file is not always one curve

A Zeiss ConfoCor `.fcs` is a **measurement archive**, not a single curve. One
885 kB sample file holds twenty data sets — the instrument sorts them by
channel, repeat, position and kinetics — and inside them **sixteen
correlation curves** of 184 lag points, eight count-rate traces, eight
photon-count histograms, the acquisition and pinhole settings, and a hundred
blocks of the Zeiss software's own fit results.

ChiSurf loads such a file as **one dataset group containing all sixteen
curves**. That matters the moment there is more than one file: four files are
not four curves but four groups of sixteen, and "fit every curve" then means
something very different from "fit every file". Check what actually arrived —
`list_datasets`, or the number of curves in the group — before creating fits,
and tell the user what you found.

## The curves in a group are not interchangeable

In that sample file the sixteen curves are **four repeats of four different
kinds**, and the reader names them accordingly:

| name ends in | is | fit it for |
| --- | --- | --- |
| `AC1` | autocorrelation of detector 1 | `N` and `D` of the species seen by detector 1 |
| `AC2` | autocorrelation of detector 2 | `N` and `D` of the species seen by detector 2 |
| `CC12`, `CC21` | cross-correlation between the two detectors | the co-diffusing fraction — how much of the two species moves together |

This is a **cross-correlation (FCCS) measurement**: two labels, two
detectors, and the question is how much of them is bound to each other. The
autocorrelations and the cross-correlations answer different questions, so
they are not repeats and must never be averaged together. `CC12` and `CC21`
are the same physical quantity computed in both directions and should agree —
if they do not, say so.

`list_datasets` reports each curve's `correlation_type`. Use it: group the
curves by kind, fit each kind for what it can tell you, and treat the four
curves *within* a kind as the repeats they are.

## Fitting a group

`create_fit` on a dataset group makes **one fit with one member per curve** —
sixteen members for the file above — and `run_fit` optimises all of them.
The reported reduced chi-square belongs to the *selected* member, so the tool
result also carries `n_members` and the spread across members. Report the
spread, and name any curve that is far out of line; a single number from a
sixteen-curve group is not the result.

Beware also that `.fcs` is the extension of the unrelated **Flow Cytometry
Standard** binary format. A file named `.fcs` that is not ConfoCor text will
not read as a correlation curve, and the honest answer is that it is a
different kind of file, not that the data is corrupt.

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
