---
type: Reference
title: What ChiSurf took from Orange3 — the adopted ideas
description: The design ideas actually harvested from the Orange3 dataflow toolkit — write-locked data, the background-task contract, and declared widget messages — where each lives in ChiSurf now, how it was translated, and where ChiSurf deliberately departs from the original.
tags: [reference, architecture, gui, provenance, attribution]
timestamp: '2026-07-27T00:00:00Z'
---

# What ChiSurf took from Orange3

Three concepts in ChiSurf were **taken from Orange3** (Bioinformatics Lab,
University of Ljubljana; GPL-3.0), a visual dataflow environment for data mining
that has solved a set of problems ChiSurf keeps running into. This concept is
the record of what was borrowed, so that "why does ChiSurf do it this way?" has
an answer, and so that the debt is stated rather than implied.

**Nothing was copied.** What crossed over is the *idea* and, in two cases, the
shape of an API; every line is written independently against ChiSurf's own
seams, which is why each of the three ends up different from its origin in ways
worth reading below. This follows the precedent set by the
[PAM port](fcs-pam-port.md) and the [QuickFit3 mining](quickfit3-mining.md):
algorithms and patterns are documented prior art, reimplemented, attributed.

Two companion concepts hold the survey rather than the outcome: the earlier
[node/workflow-toolkit lessons](orange3-lessons.md) (the data-model and
provenance pass, folded into PRD-11/16/19/21/22/25/26/27) and the
[Orange3 mining note](orange3-mining.md) (~30 areas ranked, with what remains
unharvested).

## 1. Data that cannot be written by accident

**Taken:** Orange's `Table` flags its value arrays non-writeable and requires an
explicit, scoped `unlocked()` to modify them, refusing to unlock a view into
another array (`Orange/data/table.py:489,654-700`).

**In ChiSurf:** `chisurf/core/curve.py` — `NCurve` declares the per-sample
arrays it owns in `array_attributes` and locks them in `__setattr__`;
`DataCurve` extends the tuple with `ex`/`ey`/`mask`. `unlocked(*names)` is the
escape hatch. Described in the [data model](/subsystems/data-model.md).

**Why it was worth taking.** A curve is held by a fit, a plot and any number of
plugins at once, so one of them writing into it in place changed everyone else's
result with no error and no trace. That is the invariant a dataflow graph needs
before [PRD-22](/prds/prd-22.md) and [PRD-29](/prds/prd-29.md) can be trusted.

**Where ChiSurf departs.** Orange locks what it is given and *refuses* to unlock
a non-owning array. ChiSurf **copies** such an array on the way in instead, and
keeps the refusal only as a backstop. The difference is not stylistic: the CSV
reader hands out rows of a throwaway buffer, so locking the view left the real
buffer writable — the guarantee was empty exactly where it mattered — and the
refusal made the documented escape hatch raise on every file-loaded curve. The
lock is also applied in `__setattr__` rather than at each assignment site, so a
future assignment cannot forget it.

## 2. One contract for work that runs off the GUI thread

**Taken:** Orange's `TaskState` / `ConcurrentMixin` / `ConcurrentWidgetMixin`
(`Orange/widgets/utils/concurrent.py:387,453,558`) — a worker reports through
one handle, every callback is delivered on the GUI thread, partial results
stream, starting a task cancels the previous one, and starting a task from a
completion callback is refused.

**In ChiSurf:** `chisurf/gui/task.py` — `run_in_background`, also reachable as
`ChiSurfProgress.run`. Consumers so far: the PCH histogram, the Gopich-Szabo
kinetics fit, the accurate-FRET calibration, H2MM's three run paths, BVA, and
burst selection. Described in [GUI & AutoForm](/subsystems/gui-autoform.md) and
documented for callers in `docs/development/dialogs_and_progress.md`.

**Why it was worth taking.** ChiSurf had already unified *where* progress is
displayed but not *how* work runs, so every long operation grew its own
executor, cancel flag and result delivery, and none of them agreed — two burst
tools carried byte-identical copies of the same `QRunnable` pair, each
swallowing exceptions into `logger.debug`, neither cancellable, neither guarding
against a second click.

**Where ChiSurf departs.**

* It is built **on top of** the existing `ChiSurfProgress` seam rather than
  beside it. That is what made the migration cheap: all four display backends
  (inline AutoForm section, shell status bar, modal dialog, log) kept working
  unchanged, so call sites move one at a time.
* With no `QApplication` the work runs **inline** and the callbacks fire in
  order, so a CLI or a headless test exercises the real call site instead of a
  mock. Orange always threads; ChiSurf is not canvas-only.
* A standalone tool window renders the run in **its own status bar**
  (`StatusBarProgressHost`) rather than falling through to a modal, which would
  take back exactly what moving the work off the GUI thread bought.
* `TaskHandle.set_range` exists because ChiSurf's runs have phases of genuinely
  different length (read, compute, write), and `TaskHandle.progress_window()`
  returns an adapter with the `set_value(i)` surface several Qt-free ChiSurf
  cores already accept — so a core moves into a worker unchanged, and gains a
  cancellation check on every step.

## 3. Conditions declared, not fired

**Taken:** Orange's `Msg` declarations on nested `Error` / `Warning` /
`Information` classes — a widget enumerates the conditions it can be in, raises
them by name, retracts them when the cause is fixed, and tests assert on them
directly.

**In ChiSurf:** `chisurf/gui/widgets/messages.py` — `Msg`, `MessageGroup`,
`MessagesMixin`, `MessageBar`. `ChisurfDockTool` mixes it in, so a tool opts in
by declaring a message. Described in [GUI & AutoForm](/subsystems/gui-autoform.md)
and `docs/development/dialogs_and_progress.md`.

**Why it was worth taking.** ChiSurf had unified its popups behind
`ChiSurfMessageBox`, but the *class* of message was still modal and imperative:
"load a file first" is a **state the tool is in**, not an event. A dialog says it
once, leaves nothing behind — so the tool looks ready while still being unusable
— and the only way to test it is to intercept a dialog. Declaring the condition
makes the set enumerable, the message retractable, and the test a plain
assertion.

**Where ChiSurf departs.** Message text is translated at *render* time through
[`chisurf.core.i18n`](/subsystems/i18n.md), so a language change re-renders what
is already on screen, and the ChiSurf extractor collects `Msg("…")` literals
alongside `i18n.tr("…")`. Rendering is one elided status-bar line — worst message
first, the rest counted and in the tooltip — rather than Orange's dedicated
widget message bar, because ChiSurf tools are windows and panels rather than
canvas nodes. Binding refuses a declaration that would shadow the group's own
API (`clear = Msg(...)` otherwise makes `Error.clear()` raise a message instead
of retracting the group).

## What was deliberately not taken

The supervised-learning half (classification, regression, ensembles, evaluation
and the classifier visualizations) is out of scope — ChiSurf's inference is
physical-model fitting with priors. The clustering/projection wrappers add
nothing over the scikit-learn/hdbscan dependency already shipped, and the
SQL-backed table and remote embedding service are superseded by MMFDB. The
[mining note](orange3-mining.md) carries the full ranked list, including the
ideas still worth taking — the widget-contract test mixins, VizRank, the report
system, data-matched settings contexts and the safe-expression layer are the
highest-rated of those.
