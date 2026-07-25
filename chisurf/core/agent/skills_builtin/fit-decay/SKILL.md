---
name: fit-decay
description: >-
  Fit time-resolved fluorescence decays (TCSPC): attach the instrument
  response, choose the number of lifetime components, judge the result and
  report lifetimes. Use whenever the user wants a decay, lifetime, IRF or
  TCSPC measurement fitted or interpreted.
triggers:
  - decay
  - decays
  - lifetime
  - lifetimes
  - tcspc
  - irf
  - instrument response
  - fluorescence decay
  - exponential
  - deconvolution
experiments: [TCSPC, Stopped flow]
tools:
  - load_data
  - create_fit
  - set_irf
  - set_components
  - run_fit
  - fit_report
  - plot_fit
  - auto_fit_decay
---

# Fitting a fluorescence decay

A TCSPC measurement is a histogram of photon arrival times. What you measure
is **not** the fluorescence decay itself: it is that decay convolved with the
instrument's response to a scattering sample. Fitting the raw histogram
therefore answers the wrong question, and the lifetimes come out too long.

## The procedure

1. **Find both files.** A decay measurement almost always comes with an IRF
   measured on the same instrument. Its file name usually contains `irf`,
   `prompt` or `lamp`. `list_files` labels what it finds; `load_data` flags
   datasets that look like IRFs.
2. **Create the fit on the sample**, not on the IRF. The IRF is a reference
   measurement — it is never fitted as if it were a sample.
3. **Attach the IRF** with `set_irf`.
4. **Start with one lifetime, then add components** with `set_components`,
   running the fit after each change, until the reduced chi-square stops
   improving materially.
5. **Judge the fit** with `fit_report`, and show it with `plot_fit`.

`auto_fit_decay` performs steps 3–4 in a single call and returns the trace of
chi-square against component count. Prefer it when the user simply wants the
decay fitted; drive the steps yourself when you need control over one of them.

## What the numbers mean

On a real donor-only decay from the sample data, the sequence looks like this:

| configuration | reduced chi2 |
| --- | --- |
| no IRF, one lifetime | 8.5 |
| IRF, one lifetime | 12.8 |
| IRF, two lifetimes | 1.37 |
| IRF, three lifetimes | 1.03 |

Two things are worth learning from that table. Attaching the IRF made
chi-square *worse* — because a one-exponential model cannot describe a
properly deconvolved decay, and the fit was previously hiding that behind the
instrument response. And the honest answer needed three components.

* **Reduced chi-square** near 1 means the model describes the data within
  Poisson noise. Above ~2, the model is wrong.
* **Durbin-Watson** near 2 means the residuals are random. Well below 2 means
  they are correlated — something systematic remains even if chi-square looks
  tolerable. Check it before you call a fit good.
* Stop adding components when chi-square improves by only a few per cent.
  Extra components fit noise, and their amplitudes become meaningless.

## Reporting

Give the lifetimes with their uncertainties, the reduced chi-square, and how
many components you needed. A multi-exponential decay usually means a mixture
of states or environments, so present the amplitudes too — they are the
fractions of the species. Say plainly if the fit is not good.

## When it still will not fit

* **Scattered light** at the rising edge, or an empty tail: narrow the range
  with `set_fit_range`.
* **A shifted IRF**: the `ts` parameter shifts the IRF in time; let it float.
* **A wrong IRF**: an IRF measured with different settings will not
  deconvolve. Say so rather than adding components until chi-square drops.
* Lifetimes running to zero or to the edge of their range mean the model has
  more components than the data supports — go back down.
