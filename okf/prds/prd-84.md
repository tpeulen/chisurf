---
type: PRD
prd: "84"
title: "PRD-84: Units all the way out — parameters, axes and files that say what they mean"
description: A number in ChiSurf is a bare float. Its unit lives in a column name, an axis label, a docstring, or nowhere, and four different in-band conventions encode it. The container now carries units per column; this concept is the rest of the stack — fitting parameters, plot axes, model definitions and every reader — with one rule: unitless inside, units at every boundary a person or a file sees.
status: planned
phase: "vocabulary landed (mmfdb_units, PTO.MFDB column units); parameters, axes and readers open"
resource: chisurf/core/units.py
tags: [prd, units, parameters, fitting, plotting, data-io, mfdb]
timestamp: '2026-08-07T00:00:00Z'
---

# Where to pick this up

1. **The vocabulary exists and almost nothing uses it.** `_mmfdb_units` declares
   28 codes with their symbols and SI factors, `chisurf/core/units.py` reads it,
   and a `.pto` column carries its unit. Everything else in the tree is
   unchanged. Start where a wrong unit is most expensive, which is not the GUI:
   it is `FittingParameter`, because a fitted number leaves the program.
2. **The four conventions are the inventory.** Grep for them before writing
   anything: `"Name (unit)"` suffixes, `"Name | unit"` headers
   (`chisurf/core/expressions.py`), `_TIME_UNIT_US`
   (`core/experiments/deer/csv_loader.py`), `DARK_RATE_UNITS`
   (`core/fluorescence/fcs/saturation.py`). Each is a small table that disagrees
   with the others about spelling.
3. **Do not add conversion to the fitting engine.** The engine's numbers are
   unitless by design and must stay that way — see *Non-goals*. Every attempt to
   make a solver unit-aware ends with units inside a Jacobian.

# Summary

A number in ChiSurf is a bare `float`. What it is measured in lives in a column
name when somebody remembered, in an axis label when somebody typed one, in a
docstring, or nowhere. `Duration (ms)` and `Tau` sit in the same table;
`Count Rate (KHz)` capitalises the kilo; `Tau | ns` uses a different convention
again; and a lifetime that is nanoseconds in one model is picoseconds in the
file it came from, with nothing that notices.

The photon container now carries a unit per column, from a vocabulary the
dictionary declares. This concept is the rest of the stack, under one rule:

> **Unitless inside. Units at every boundary.** The arrays a model computes on
> and the numbers a solver moves are plain floats in a declared unit, and stay
> that way. Everything a *person* or a *file* sees says what it is in.

# Problem / motivation

## The unit is in the name, or nowhere

| Where | How the unit is carried | What goes wrong |
| --- | --- | --- |
| Burst tables | `"Duration (ms)"` suffix | absent on `Tau`, inconsistent on `KHz` |
| Expression columns | `"Name \| unit"` | a second convention, different splitter |
| DEER reader | `_TIME_UNIT_US` dict | its own spellings, its own factors |
| FCS saturation | `DARK_RATE_UNITS` dict | ditto, and `1/us` is not a unit name anywhere else |
| Fitting parameters | nothing at all | a fitted lifetime has no unit |
| Plot axes | a hand-typed string | says whatever the plotting call said |
| Model definitions | prose | the reader has to know |

Four in-band conventions and two bare dictionaries, none agreeing, none
checkable. A regular expression over any of them is that convention with more
machinery on top and the same blind spots.

## The cost is not cosmetic

A wrong unit is a wrong result that looks right. The specific failures this
prevents:

* A lifetime fitted against a decay whose x-axis is nanoseconds, exported to a
  file whose reader assumes picoseconds. Both numbers are plausible.
* A burst duration in milliseconds compared against a diffusion time in
  microseconds, because both columns are called "time".
* A rate entered in a GUI field labelled `1/us` and stored as `1/s`.
* Two containers merged whose `Mean Macro Time` columns are seconds in one and
  milliseconds in the other — the column names are identical.

None of these raise. All of them are silent, and all are the same defect: the
number and its unit travel separately.

## The vocabulary problem is already solved

`_mmfdb_units` in the MMFDB dictionary carries the code, the symbol a person
reads, and the SI factor. 15 of its 28 codes are mmCIF's own; the 13 it adds are
the gaps — mmCIF has `nanoseconds` and `femtoseconds` but neither `milliseconds`
nor `picoseconds`, and no concentration, rate multiple or count of photons.

So this is not a "choose a units library" problem. It is a plumbing problem.

# Goals

1. A `FittingParameter` knows its unit, and a fit result carries it.
2. Every `DataCurve` axis knows its unit; a plot axis label is *derived*, never
   typed.
3. Every reader records the unit it read, and every writer records the unit it
   wrote.
4. A model declares the unit each of its parameters is in, in its `view.json`
   rather than in prose.
5. One vocabulary — `_mmfdb_units` — and one seam, `chisurf/core/units.py`.
   Nothing else holds a unit table, a symbol, or a conversion factor.
6. Converting between incompatible quantities raises. Silently returning the
   value is how a millisecond becomes a nanosecond.

# Non-goals

- **A unit-aware numeric type.** No `pint`, no wrapper around `float`, no dtype
  carrying a unit. Arrays stay `numpy` arrays. The dependency cost is the
  smaller objection; the real one is that every model, every kernel and every
  C++ boundary would have to unwrap it, and the ones that forgot would be the
  ones that mattered.
- **Units inside the fitting engine.** A solver moves unitless numbers in a
  declared unit and must keep doing so. Dimensional analysis in a Jacobian is
  a way to make a fit slower and wrong.
- **Automatic conversion on read.** A reader records what the file said; it does
  not silently rescale into a preferred unit. Rescaling is an explicit act.
- **Dimensional algebra.** Nothing derives that a rate is one-over-a-time. The
  table says what each thing is; composing them is out of scope.
- **Retrofitting every historical file.** Files without units are read as
  unit-unknown, which is what they are.

# Design

## The one seam

`chisurf/core/units.py` already provides `canonical`, `symbol`, `convert`,
`split_label`, `known_units`. Everything below uses it and nothing duplicates
it. The legacy spelling table there is for *reading* files that exist; a writer
uses the code.

## Parameters

`FittingParameter` gains `units: str` — a code, or `""` for unknown. It is
metadata, not behaviour: the value stays a float and no arithmetic changes.

What it buys:

* a fit result that says `tau = 3.42 ns` instead of `tau = 3.42`;
* a linked-parameter check that refuses to link a `nanoseconds` parameter to a
  `milliseconds` one, which today is a silent factor of 10⁶;
* a GUI field whose suffix is derived rather than typed.

## Curves and axes

`DataCurve` gains `x_units` / `y_units`. A plot axis label becomes
`f"{name} / {symbol(units)}"` — derived, so it cannot disagree with the data.
This is the change most visible to a user and the least risky, because a wrong
label today is already wrong.

## Models

A `view.json` parameter section gains `"units"`, so a model declares what its
parameters are in where the rest of its interface is declared. The AutoForm
renders the symbol as the field suffix; the doc generator puts it in the table.

## Readers and writers

Every reader that knows its unit records it — the TCSPC readers know the TAC
resolution, the FCS readers know the correlation-time unit, the burst readers
now go through `burst_container`. Every writer records what it wrote. The four
ad-hoc tables are deleted and their call sites go through the seam.

## What "unitless inside" means concretely

A model computing a decay works in nanoseconds because its parameters are
declared in nanoseconds — not because anything converts at each step. The unit
is a *contract stated once* at the boundary, and the interior is plain floats.
The only conversions in the tree are at boundaries, and they are explicit calls
to `convert`.

# Staging

| Stage | What | Why first |
| --- | --- | --- |
| 1 | `chisurf/core/units.py` + `_mmfdb_units` | **done** — the vocabulary |
| 2 | Container columns carry units | **done** — files say what they hold |
| 3 | `FittingParameter.units`, and the link check | a fitted number leaves the program; this is where a wrong unit is most expensive |
| 4 | `DataCurve` axes + derived plot labels | most visible, least risky |
| 5 | `view.json` parameter units + AutoForm suffix | makes it declarative |
| 6 | Readers and writers; delete the four ad-hoc tables | the duplication is only gone when they are |

Stages 3–6 are independent of each other and can land in any order after 2.

# Rules

1. One vocabulary, `_mmfdb_units`. A unit ChiSurf needs that it lacks is added
   to the dictionary first.
2. One seam, `chisurf/core/units.py`. Nothing else holds a symbol or a factor.
3. A symbol is never written by hand. `Count Rate (KHz)` is what that produces.
4. No unit means **unknown**, not dimensionless.
5. Conversion between different quantities raises.
6. Units are recorded, never inferred from a name — except when *reading* a
   legacy file, which is what `split_label` is for.
7. The fitting engine stays unitless.

# Verification

* A guardrail test that no module outside `chisurf/core/units.py` defines a unit
  symbol table or a conversion factor — the shrinking-allowlist pattern, seeded
  with the four that exist.
* Linking parameters of different quantities raises, tested.
* A round trip: read a file with units, fit, write a container, read it back,
  and assert the unit survived every hop.
* A GUI screenshot per touched tool: an axis label that used to be typed is now
  derived, and the two must agree where the typed one was right.
