---
type: Workflow
title: Reference checkouts — annotate what you have mined
description: junk/ holds ~40 reference implementations ChiSurf is built against. Reading one is expensive, so what was read is recorded in the file itself with a CHISURF-REVIEWED header, and the coverage is measurable.
resource: build_tools/dev_utils/reference_coverage.py
tags: [workflow, references, provenance, junk, transcription]
timestamp: '2026-08-06T00:00:00Z'
---

# Why

`junk/` holds the reference implementations ChiSurf is built against — around
**forty** checkouts, populated by `junk/clone.sh`: PyMOL and ChimeraX for the
viewer, FRETBursts and burstH2MM for burst analysis, the imaging-FCS tools,
LabelLib, MASH-FRET, and more. The working rule across the tree is that a
behaviour is **read from the reference and transcribed**, never inferred — every
value inferred from behaviour has turned out wrong and every value read from
source has turned out right.

Reading one of those files is the expensive part, and it was being paid twice.
Nothing recorded *which parts had already been read*, so the next session opened
the same file, reached the same conclusion, and moved on. Worse, the cheapest
finding — **"I read this and deliberately did not take it, because…"** — was
lost every time, because it leaves no trace in the code.

# The rule

**Annotate the reference file itself.** Any file in `junk/` that you read for
ChiSurf gets a header:

```c
/*
 * CHISURF-REVIEWED: 2026-08-06
 * CHISURF-TAKEN: cSetting_stick_color -> chimol/renderer/view.py::_representation_color
 * CHISURF-SKIPPED: RepValence -- chimol has no bond orders, so it would draw nothing
 * CHISURF-RECORD: okf/plugins/pymol-parity.md
 * Header added by ChiSurf; the code below is untouched.
 */
```

Python files use `#`. The keys:

| Key | Meaning |
| --- | --- |
| `CHISURF-REVIEWED` | the date it was read. Its presence is what "reviewed" means |
| `CHISURF-TAKEN` | what came across, and **where it landed** in this tree |
| `CHISURF-SKIPPED` | what was read and deliberately not taken, **and why** |
| `CHISURF-RECORD` | the OKF concept that holds the full account |

Four things make it work:

1. **Header only — never the code.** A `git diff` inside the checkout must show
   insertions and **zero deletions**. The file has to keep saying what the
   reference does; the moment it does not, it stops being a reference.
2. **`SKIPPED` matters as much as `TAKEN`.** "Read, not taken, because X" is the
   knowledge that stops the next session re-deriving X. It is also the honest
   half: a survey that records only what was taken reads as if everything else
   was never looked at.
3. **The markers are an index; OKF is the record.** `junk/` is gitignored and
   re-clonable, so a re-clone loses every marker and loses nothing else — which
   is why each one points at the concept that holds the detail, and why a fresh
   checkout honestly reports 0 %.
4. **Put it where a reader meets it.** In the header, not in a notes file
   somewhere: the person about to re-read the file is the person opening it.

# Measuring it

```bash
python -m build_tools.dev_utils.reference_coverage --all
python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source
python -m build_tools.dev_utils.reference_coverage junk/pymol-open-source --unreviewed layer2
```

`--all` prints one line per checkout, which is the answer to *"is this source
exhausted?"* for the whole shelf. A single checkout gets a per-directory table
plus everything `TAKEN` and `SKIPPED` in it.

The **denominator is chosen, not automatic**: with no preset the whole checkout
is surveyed minus the noise every repository carries (tests, examples, build
directories, vendored dependencies); `pymol` and `chimerax` have presets that
narrow to the directories genuinely worth reading. PyMOL is ~3000 files, most of
them build glue, and counting those would hold coverage near zero for ever and
tell nobody anything.

As of 2026-08-06: PyMOL **14 / 468**, ChimeraX **10 / 116**, everything else
**0**. Nowhere near exhausted, and now that is a number rather than a feeling.

# Which reference answers which question

Recorded per subsystem in the concept that owns it, because it is a real
distinction and not a preference. For the viewer
([pymol parity](/plugins/pymol-parity.md)): **PyMOL is the authority on the GUI
and the UX**, ChimeraX on **functionality** — what a viewer should be able to
do. Asking the wrong one produces a defensible answer to a question nobody had.

# See also

* [change tracking](/workflows/change-tracking.md) — where the account of a
  change goes once it lands.
* [pymol parity](/plugins/pymol-parity.md) — the worked example: what has been
  mined from PyMOL and ChimeraX, and the measured gaps.
* `junk/clone.sh` — what is on the shelf, and how to restore it.
