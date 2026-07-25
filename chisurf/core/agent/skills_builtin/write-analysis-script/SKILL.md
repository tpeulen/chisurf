---
name: write-analysis-script
description: >-
  Do things the built-in tools do not cover, by running Python inside the live
  ChiSurf session or writing a reusable script. Use when the user asks for a
  custom calculation, a bespoke plot, an unusual export, or "a script that
  does this".
triggers:
  - script
  - python
  - code
  - custom
  - automate
  - calculate
  - compute
  - macro
  - programmatically
tools:
  - run_python
  - write_file
  - read_file
  - describe_session
---

# Writing analysis code

`run_python` executes in the **live** session: the same datasets and fits the
user is looking at, not a copy. That is what makes it useful and why it needs
care.

## Working style

* **Look before you compute.** `describe_session` or a first small snippet
  that prints shapes and names beats a long script written against assumed
  attribute names.
* **Small steps.** Run a few lines, print what you got, then build on it. A
  40-line script that fails on line 3 wastes a whole turn.
* **Print what you need to see.** The tool returns stdout; assigning to
  `result` returns that value as well.
* **Prefer the real tools** for loading, fitting and exporting. They handle
  the awkward details — fit ranges, parameter discovery, reader selection —
  that hand-written code gets wrong.

## What is in scope

`cs` (the chisurf package), `datasets`, `fits`, `np`, `Path` and `WORKDIR`.
A fit exposes `fit.data` (the measurement), `fit.model` (with
`parameters_all_dict` keyed by name), `fit.chi2r`, `fit.fit_range` and
`fit.weighted_residuals`.

## When the user wants a script, not an answer

Write it to a file with `write_file` and tell them how to run it. Make it
standalone and readable: imports at the top, paths as variables near the top,
a comment for each step, and printed output that says what happened. They will
edit it, so favour clarity over cleverness.

## Care

This code can modify or delete the user's work and files. Do not clear
sessions, overwrite data files, or delete anything unless that is explicitly
what was asked. Anything irreversible deserves a sentence of warning before
you do it, not after.
