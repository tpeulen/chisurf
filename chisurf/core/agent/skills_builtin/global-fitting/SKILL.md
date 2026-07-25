---
name: global-fitting
description: >-
  Analyse several measurements together by sharing parameters between their
  fits, so one value is determined by all the data. Use when the user talks
  about global or simultaneous analysis, linking or sharing parameters, or
  fitting a series with something in common.
triggers:
  - global
  - globally
  - simultaneous
  - simultaneously
  - link
  - linked
  - linking
  - share
  - shared
  - together
  - common
  - constrain
  - titration series
tools:
  - link_parameters
  - unlink_parameters
  - list_links
  - create_fit
  - run_fit
  - get_fit
  - fit_report
---

# Global analysis

Fitting measurements one at a time lets every fit invent its own value for
every parameter — including quantities that are physically the same in all of
them. Global analysis ties those together: **one value, fitted against all the
data at once**.

This is what ChiSurf is built for, and it is usually the only way to pin a
parameter that a single dataset cannot constrain on its own.

## The procedure

1. **Fit each dataset separately first.** You need to know that each model
   describes its own data before tying them together; otherwise a global fit
   just spreads one bad fit across the whole series.
2. **Decide what is genuinely shared.** Link only what physics says is
   identical across the measurements.
3. `link_parameters` with the exact names, naming the fit whose value the
   others should follow.
4. **Run every fit again.** The linked value is now determined by all of them,
   so the individual results are stale.
5. `list_links` before interpreting anything — a number means something
   different depending on what was tied to what.

## What to link, and what not to

Link a parameter when it is a property of the *system or instrument* rather
than of the individual measurement:

* donor lifetimes across a FRET series measured on the same dye,
* an instrument time-shift or colour-shift within one session,
* a background or correction factor for one detector,
* a distance or rate that the experiment is designed to hold constant.

Do **not** link what the experiment is varying — the concentration in a
titration, the efficiency you are trying to measure per sample, an amplitude
that reflects how much of each species is present. Linking those manufactures
the answer.

## Linking versus fixing

Both remove a degree of freedom, and they mean different things:

* **Fixing** (`set_parameter` with `fixed=true`) asserts a value you already
  know — from a calibration, or from a reference measurement you trust.
* **Linking** asserts only that the value is *the same everywhere*, and lets
  the data decide what it is.

When the reference measurement is itself part of the analysis, prefer
linking: fixing throws away the reference's own uncertainty.

## Reading the result

`list_links` reports the free-parameter count per fit; it must drop when a
link takes effect. Reduced chi-square usually rises slightly for the
individual datasets — that is expected and is the price of the constraint. A
*large* rise means the parameter is not actually shared, and the honest
conclusion is that the measurements disagree.

Always state which parameters were linked when reporting a global result.
