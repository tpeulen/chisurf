---
type: PRD
prd: "84"
title: "PRD-84: Units all the way out — parameters, axes and files that say what they mean"
description: A number in ChiSurf is a bare float and stays one. The interior has a fixed, declared unit per quantity — ns for lifetimes, ms for correlation times, nm for coordinates — enforced by convention and review rather than at runtime, so unit awareness costs nothing to compute. Units are carried as metadata at the boundaries a person or a file sees, and nothing checks or converts on the hot path.
status: planned
phase: "vocabulary landed (mmfdb_units, PTO.MFDB column units); parameters, axes and readers open"
resource: chisurf/core/units.py
tags: [prd, units, parameters, fitting, plotting, data-io, mfdb]
timestamp: '2026-08-07T00:00:00Z'
---

# Where to pick this up

1. **The vocabulary exists and almost nothing uses it.** `_mmfdb_units` declares
   28 codes with their symbols and SI factors, `chisurf/core/units.py` reads it,
   and a `.mmfdb.pto` column carries its unit. Everything else in the tree is
   unchanged. Start where a wrong unit is most expensive, which is not the GUI:
   it is `FittingParameter`, because a fitted number leaves the program.

   **2026-08-10 — the rule that reads the vocabulary had three holes**, all
   found by making a *second* writer implement it (the compiled `tttr sm`, from
   the tttrlib repository, writing into the same containers). Two writers is
   what turns "what should this column's unit be?" from a matter of taste into
   a question with one answer, and the exercise is worth repeating for the next
   boundary rather than trusting a single implementation:

   - **A detector qualifier cost a column its unit.** `BURST_COLUMN_UNITS` keys
     on the exact name, so `Number of Photons` was `photons` and
     `Number of Photons (green)`, *in the same row of the same table*, was
     unitless. `units_for` now drops a trailing non-unit qualifier and asks
     again — which also stops the table needing one row per detector name it
     has never heard of, and makes the hand-listed `Tau (green)` / `Tau (red)` /
     `Tau (yellow)` rows redundant.
   - **A label carrying both conventions at once found neither.** A burst
     table's window rate is `S prompt green (kHz) | 0-2048`: the bar separates a
     micro-time *range*, and the unit is in the bracket to its left. The bar
     branch gave up when `0-2048` was not a unit, and the suffix regex is
     anchored at the end, so a column that plainly says kHz carried no unit.
     `split_label` now falls through to the bracket on the bar's left.
   - **`FRET 2CDE` / `ALEX 2CDE` had no entry.** A 2CDE value is a score on a
     fixed scale (≈10 for a static burst), so it is `dimensionless` — which is a
     different claim from the unit being unknown, and the distinction is the
     whole point of leaving a column unitless.

   Pinned by `test/fio/test_burst_container.py` (the rule) and
   `test/fio/test_container_cross_writer.py` (the two writers agreeing column
   for column — 40/40 on a four-detector burst table, 30/30 with PIE windows).
   The C++ port cannot read the mmCIF dictionary, so it carries the subset a
   burst table needs; that test is what stops the two drifting.
2. **The four conventions are the inventory.** Grep for them before writing
   anything: `"Name (unit)"` suffixes, `"Name | unit"` headers
   (`chisurf/core/expressions.py`), `_TIME_UNIT_US`
   (`core/experiments/deer/csv_loader.py`), `DARK_RATE_UNITS`
   (`core/fluorescence/fcs/saturation.py`). Each is a small table that disagrees
   with the others about spelling.
3. **One duplicate is still there.** `_flr_chisurf_parameter.R0` and
   `.r0` are the same parameter declared twice — same description, both bound to
   the SQL column `r0`. Both now carry `angstroms`, but removing one is a
   vocabulary *removal* and needs the alias mechanism
   (MMFDB REQUIREMENTS 2.3, "write canonical, read both"), so it belongs with
   the `flr_chisurf_parameter` → `flr_fit_parameter` rename rather than on its
   own.
4. **Do not add conversion to the fitting engine.** The engine's numbers are
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

> **One fixed internal unit per quantity, declared and never checked. Units as
> metadata at every boundary.** The arrays a model computes on and the numbers a
> solver moves are plain floats in a unit this document fixes, and stay that
> way. Nothing multiplies, wraps, validates or dispatches on a unit at runtime.
> Everything a *person* or a *file* sees carries what it is in, as metadata
> alongside the number.

# Cost, and what is deliberately not done

**Unit awareness must be free.** A fit evaluates a model tens of thousands of
times; a correlation curve is built from millions of photons. Anything that
touches a number on that path is not worth what it buys, and the things that
would touch it are exactly the things a units library sells:

| Not done | Why |
| --- | --- |
| A unit-aware numeric type (`pint`, a `float` wrapper, a unit-carrying dtype) | every kernel and every C++ boundary would unwrap it, and the ones that forgot would be the ones that mattered |
| Runtime dimension checking | the check would run per evaluation to catch a mistake that is made once, in source |
| Conversion inside a model or a solver | a conversion on the hot path is a multiply per element for a constant known at authoring time |
| Deriving that a rate is one-over-a-time | nothing composes units; the table says what each thing is |

**So the internal units are a convention, not a mechanism.** They are fixed
below, stated in each model's docstring and parameter declaration, and checked by
review — the same way array shapes and dtypes are. The runtime cost of the whole
scheme is: a string stored beside a column when a file is written, and a string
read back when one is opened. Zero on the compute path, by construction.

`convert()` exists for **boundaries** — a reader that finds microseconds in a
file when the interior wants milliseconds. It is called once per read, not once
per evaluation, and it raises on a cross-quantity conversion because a boundary
is exactly where that mistake is worth catching.

# The internal units

One unit per quantity, everywhere inside ChiSurf. These are not new: they are
what the tree already does, written down so that "already does" becomes a rule
instead of a pattern somebody has to notice.

| Quantity | Internal unit | Where this is already true |
| --- | --- | --- |
| Fluorescence lifetime, decay time axis | **nanoseconds** | `core/models/tcspc/lifetime.py` — starting values, bounds and prose are all ns |
| FCS correlation time, diffusion time τ_D | **milliseconds** | `core/models/fcs/` — `τ_D[ms]`, `t_d,min[ms]`, bunching `b_t[ms]` |
| Rotational correlation time ρ | **nanoseconds** | `core/models/tcspc/anisotropy.py` — shares the decay's ns axis, and is *not* the FCS correlation time |
| Burst duration, macro time | **milliseconds** | burst tables: `Duration (ms)`, `Mean Macro Time (ms)` |
| TAC / micro time resolution | **picoseconds** | `_mmfdb_setup.micro_time_resolution` |
| Macro time resolution | **nanoseconds** | `_mmfdb_setup.macro_time_resolution` |
| Count rate | **kilohertz** | burst tables: `Count Rate (KHz)` |
| FRET distances — R_DA, R₀, and every distance distribution | **ångströms** | `core/fluorescence/fret/calibration.py` (`R_0` = 52.0, bounds 1–200), `species_decay.py` (`# R0 (Å)`), `forster.py` returns `R0_angstrom` |
| Atomic coordinates in memory | **ångströms** | mmCIF `_atom_site.Cartn_x` declares `angstroms`, and so do PDB, DCD and the AV code |
| Radius of gyration, structural distances a user reads | **ångströms** | `core/structure/structure.py` reports R_g in Å |
| Concentration | **nanomolar** | to confirm in stage 6; a reader currently decides |
| Wavelength | **nanometres** | spectra are nm throughout |

Two of these disagree with each other on purpose and it is worth being explicit
about why:

* **Coordinates are nm inside and Å at the boundary.** `trajectory_data.py`
  already does exactly this — `xyz * 10.0  # nm here, Angstrom in a PDB` — and
  it is the pattern this whole concept generalises: the interior picks one unit,
  the boundary states another, and the conversion happens once, visibly, at the
  edge.
* **Lifetimes are ns and correlation times are ms.** Both are times, and a naive
  "one time unit" rule would force one of the two communities to work in numbers
  with six leading zeros. The unit is per *quantity*, not per dimension.
* **Lengths are all ångströms, and that is now true rather than aspirational.**
  Coordinates were nanometres in memory, which was mdtraj's convention and
  nothing else's — mmCIF, PDB, DCD, the AV code and every FRET distance are
  ångströms. With mdtraj retired ([PRD-80](prd-80.md)) nothing wanted nm at all,
  and the seventeen `× 10` / `÷ 10` conversions that bridged the two were deleted
  rather than moved. **XTC is the one format that is genuinely nanometres**
  (GROMACS writes them), so it is the only scale left in the whole reader.

A quantity not in this table has no fixed internal unit yet, and adding one is a
change to this table first.

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
* **Found while writing this.** `_flr_fret_forster_radius.forster_radius`
  carried a default of `5.0` and no unit — upstream flrCIF declares none — in a
  field every ChiSurf consumer reads as ångströms, where a Förster radius is
  40–70. It was a nanometre number in an ångström field, and nothing could have
  noticed. Declared `angstroms` and corrected to `50.0`, the same physical
  quantity.
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

1. A `FittingParameter` *records* its unit, as metadata. Reading it costs an
   attribute access; nothing consults it during a fit.
2. Every `DataCurve` axis knows its unit; a plot axis label is *derived*, never
   typed.
3. Every reader records the unit it read, and every writer records the unit it
   wrote.
4. A model declares the unit each of its parameters is in, in its `view.json`
   rather than in prose.
5. One vocabulary — `_mmfdb_units` — and one seam, `chisurf/core/units.py`.
   Nothing else holds a unit table, a symbol, or a conversion factor.
6. Converting between incompatible quantities raises — at a **boundary**, where
   conversion happens once per file. Silently returning the value is how a
   millisecond becomes a nanosecond.
7. Nothing on the compute path reads, checks or converts a unit.

# Non-goals

- **A unit-aware numeric type.** No `pint`, no wrapper around `float`, no dtype
  carrying a unit. Arrays stay `numpy` arrays. The dependency cost is the
  smaller objection; the real one is that every model, every kernel and every
  C++ boundary would have to unwrap it, and the ones that forgot would be the
  ones that mattered.
- **Runtime unit checking, anywhere on the compute path.** Not in a model, not
  in a solver, not on parameter assignment. The internal units are fixed by the
  table above and held by review, exactly as array shapes are. A check that runs
  per evaluation to catch a mistake made once in source is the wrong trade.
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
7. The fitting engine stays unitless, and so does every model interior: the
   unit is fixed by the internal-units table, not carried with the number.
8. No unit operation runs per evaluation. Conversions happen at boundaries,
   once per file or once per user action.

# Verification

* A guardrail test that no module outside `chisurf/core/units.py` defines a unit
  symbol table or a conversion factor — the shrinking-allowlist pattern, seeded
  with the four that exist.
* A benchmark asserting the compute path is untouched: fitting the same model
  before and after, with the unit metadata populated, within noise. The claim is
  zero cost, so it is measured rather than asserted.
* A test that every model's declared parameter units agree with the
  internal-units table — read from the declarations, not from the running fit,
  so it costs nothing at runtime.
* A round trip: read a file with units, fit, write a container, read it back,
  and assert the unit survived every hop.
* A GUI screenshot per touched tool: an axis label that used to be typed is now
  derived, and the two must agree where the typed one was right.
