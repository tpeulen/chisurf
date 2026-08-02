---
type: PRD
prd: "73"
title: "PRD-73: FRET wiring for the FCS kinetics model"
description: Let the FCS kinetics model be driven by FRET species — a brightness source that computes per-state brightnesses from a FRET efficiency / crosstalk / excitation picture, a button on the FCS model that imports those brightnesses, and a well-defined computation of the average brightness Q from the crosstalk and excitation matrices.
status: draft
phase: "unassigned"
resource: chisurf/core/models/fcs/
tags: [prd, fcs, fret, kinetics, brightness, wiring]
timestamp: '2026-08-02T00:00:00Z'
---

# Summary

[PRD-62](prd-62.md) consolidated the FCS models and
`FCSKineticsModel` (in `chisurf/core/models/fcs/kinetics.py`) grew the
photokinetic saturation scheme. Today the scheme's per-state brightnesses are
free fit parameters (`StateBrightness`, the `Q_i` column in the
`kinetic_saturation` panel of `kinetics.view.json`) with no physical
connection to FRET. For a user studying a FRET-labelled species by FCS, the
brightnesses the model should use are **not** arbitrary: they are dictated by
the FRET efficiency of the species, the detection crosstalk, and the
excitation/detection matrices of the instrument.

This PRD wires FRET into the FCS kinetics model. It is a **wiring** change:
one brightness source that computes per-state brightnesses from FRET + optical
parameters, one button on the FCS model that imports those values into
`StateBrightness`, and one agreed definition of how the average molecular
brightness Q follows from the crosstalk and excitation matrices. It does not
redesign the saturation physics and it does not implement the
brightness-into-amplitude propagation of species mixtures, which is
[PRD-75](prd-75.md).

# Motivation

A FRET FCS experiment reports on a *photophysical species* — donor-only,
acceptor-only, or FRET pair — each with its own fluorescence brightness in each
detection channel. The `Q_i` in the FCS saturation scheme are the *same*
relative brightnesses the FRET picture predicts from:

- the **FRET efficiency** E (how much donor emission is quenched / acceptor
  emission sensitised),
- the **crosstalk matrix** (what fraction of a photon from the donor channel is
  seen in the acceptor channel and vice versa — the detector bleed-through
  matrix `L`), and
- the **excitation matrix** (which lasers drive which dye, and how strongly —
  the `sigma` matrix already present in `KineticSaturationTerms.exc`).

Today nothing links these. The user must hand-type `Q_i` values derived from a
separate FRET calculation into the brightness table, and the model has no way
to know which state is the donor, which is the acceptor, or what the channel
layout is. The wiring described here is the precondition for [PRD-75](prd-75.md)
(brightness → amplitude for species mixtures) and for using the kinetics model
as a genuine FRET-FCS fit model.

# Design

## 1. A brightness source — extend the FRET calculator, do not invent a store

The `fret_calculator` plugin (`chisurf/plugins/calculator/fret_calculator/`,
core in `core/algorithms.py`) already converts between E, R, R0, lifetimes and
FRET rate constants. It has **no brightness concept today** — grep for
brightness/crosstalk/saturation finds nothing in the plugin. The cleanest
home for per-state brightnesses is the FRET picture, so the calculator gains a
brightness section rather than a new parallel plugin: given the species' FRET
efficiency and detection set, it emits the relative per-state brightness
vector the FCS scheme expects.

The single new computation in `fret_calculator/core/algorithms.py`:

```
Q_state(channel, state)  given  L (crosstalk/bleed-through matrix),
                              sigma (excitation matrix), E (species FRET
                              efficiency), and the donor/acceptor emission
                              weights
```

The output is the vector of relative brightnesses `Q_i` that
`StateBrightness.array` already expects — the FCS model keeps consuming the
same array, so the wiring is value-level, not API-level.

### Acceptance

- `fret_calculator/core/algorithms.py` has one pure function taking
  `(L, sigma, E, ...)` and returning a brightness vector, with a NumPy-style
  docstring.
- The calculator GUI shows the brightness section; changing E, crosstalk or
  excitation updates the vector live, like every other quantity it already
  recomputes.
- The computed vector, when copied into `StateBrightness`, reproduces a hand
  calculation for a known FRET pair (guardrail test with a fixed `L`/`sigma`/
  `E` triple).

## 2. A button on the FCS model — "import brightness from FRET calculator"

`kinetics.view.json` gains an `"action"` entry (the pattern already used by
`pda2c/dynamic.view.json`'s `run_consistency_check`) in the
`kinetic_saturation` panel, next to the brightness table:

- **label**: e.g. "⇥ Import brightness from FRET calculator"
- **action**: `import_brightness_from_fret_calculator`
- **description**: what it does — replaces the current `Q_i` values with the
  brightnesses from the FRET calculator's current session.

The model method (`FCSKineticsModel.import_brightness_from_fret_calculator`)
reads the calculator's last-computed brightness vector and writes it into
`self.saturation.brightness`, marking the values fixed so a fit does not move
imported physical brightnesses behind the user's back (the same intent as the
existing `StateBrightness._rebuild` default `fixed=...` for all but the S1
state). The write goes through the same parameter path a user edit would, so
the GUI and headless paths behave identically.

If the calculator has not been run, the action is a no-op with a clear message
rather than importing stale/zero values.

### Acceptance

- Clicking the button after running the FRET calculator replaces the `Q_i`
  column with the imported values and refits the model immediately.
- The button is discoverable and documented: `kinetics.view.json` carries a
  `description`, and the model's parameter-group docs mention it.
- Headless equivalent: a public model method callable from `csc`/macros that
  does the same import, tested without a GUI.

## 3. Average brightness Q from the crosstalk and excitation matrices

"Brightness" appears in two places with different meanings:

- `StateBrightness.array` — the **per-state relative** `Q_i` that shape the
  saturation autocorrelation (already wired, [PRD-62](prd-62.md)).
- `compute_brightness(fit, N, bg)` in `chisurf/core/models/fcs/mdf.py` — the
  **absolute molecular brightness** `(CR_total - bg)/N` in kHz, a derived
  output shown in the fit table.

This PRD pins down the missing link: how the *absolute* Q follows from the
*cross*-species picture. In practice Q must be computed from the crosstalk and
excitation matrices — the detection-weighted sum over states:

```
Q_abs  =  (weighted sum over states/channels of  sigma * Q_i * E_emission)
          / N,  scaled by the count rate
```

which is exactly what a FRET mixture measurement means. The precise formula,
its units, and where it lives (a shared helper next to `compute_brightness`,
so the FCS model and the calculator agree) are specified in the implementation;
what is fixed here is the *dependency*: Q for a FRET-labelled species is a
function of `L`, `sigma`, and `E`, not a free number.

### Acceptance

- One helper computes Q from the crosstalk + excitation matrices and the
  per-state brightnesses; the FCS model and the FRET calculator both call it
  (no duplicated formula).
- A unit test asserts Q = 0 when the species is invisible in a channel
  (zero row of `L` or `sigma`) and that a donor-only species has no acceptor
  contribution.

# Status

Draft. Nothing implemented. Registered as the precondition for
[PRD-75](prd-75.md) (brightness → amplitude for species mixtures), which is
explicitly out of scope here.

Related: [PRD-62](prd-62.md) (FCS model consolidation, the kinetics model and
`StateBrightness`), [PRD-75](prd-75.md) (brightness propagation into
amplitudes, the postponed follow-up), [PRD-58](prd-58.md) (FRET plugin),
[PRD-38](prd-38.md) (view-spec / action buttons).
