---
type: Index
title: ChiSurf assistant knowledge base
description: >-
  What the assistant needs to know about fluorescence analysis and about
  ChiSurf's object model in order to give answers that are right, as opposed
  to answers that merely run.
tags: [agent, knowledge, fluorescence, reference]
timestamp: '2026-07-25T00:00:00Z'
---

# What this is

An Open-Knowledge-Format bundle carried **by the assistant**, and deliberately
not the same thing as the `okf/` bundle at the root of the repository:

| bundle | question it answers | audience |
| --- | --- | --- |
| `okf/` (repository) | how is ChiSurf *built* — architecture, subsystems, PRDs | someone changing the code |
| this bundle | how is fluorescence data *analysed*, and what do ChiSurf's objects mean | the assistant, while operating the program |

A language model arrives knowing a little textbook spectroscopy and nothing
about this program. Skills tell it *what to do*; these concepts tell it *what
the things are and what the numbers mean*, so that a procedure can stay short
and a judgement can be made when a procedure runs out.

# How it is used

The knowledge search (`search_docs`, `read_doc`) covers this bundle alongside
the repository documentation, so a concept is one lookup away when a skill
refers to it. Skills link here rather than repeating the background.

# Concepts

* [The ChiSurf session](concepts/chisurf-session-model.md) — datasets, fits,
  models, parameters, and what "the fit" actually is.
* [Time-resolved decays](concepts/tcspc-decays.md) — what a TCSPC measurement
  contains, why the instrument response matters, how many components are
  honest.
* [FRET from lifetimes](concepts/fret-from-lifetimes.md) — efficiency,
  distance, the Förster radius as an input, and the donor-only fraction.
* [Correlation spectroscopy](concepts/correlation-spectroscopy.md) — what an
  FCS curve carries and which parameters are calibration rather than result.
* [Uncertainty and model choice](concepts/uncertainty-and-model-choice.md) —
  why a covariance error is optimistic, what a support-plane interval is, and
  when an extra component is justified.
* [Measurement files](concepts/measurement-files.md) — what the formats are,
  and how to tell a sample from a reference.

# Adding to it

A concept belongs here when it is knowledge about the *science or the
session*, is needed more than once, and is too long to repeat in every skill.
Anything about the *codebase* belongs in the repository `okf/` bundle
instead. Every claim should be checkable against the program — a wrong
concept is worse than a missing one, because the assistant will act on it
with confidence.
