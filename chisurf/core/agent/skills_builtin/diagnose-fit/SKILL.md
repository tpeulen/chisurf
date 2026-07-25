---
name: diagnose-fit
description: >-
  Work out why a fit is bad and fix it, in the order that pays off. Use when
  the reduced chi-square is far from 1, the residuals look structured, a
  parameter is stuck or at a bound, or the user asks whether a fit is any
  good.
triggers:
  - chi2
  - chi-square
  - chi squared
  - bad fit
  - poor fit
  - does not converge
  - doesn't converge
  - residuals
  - stuck
  - why is
  - is this fit
  - improve the fit
  - not converging
tools:
  - fit_report
  - plot_fit
  - get_fit
  - set_fit_range
  - set_parameter
  - set_irf
  - set_components
  - run_fit
---

# Diagnosing a fit

A reduced chi-square far from 1 is a symptom, not a diagnosis. Work through
the causes in this order — it is roughly the order of how often each is to
blame, and each check is cheap.

## 1. Is the model even set up?

`fit_report` tells you whether an instrument response is attached and how many
components the model has. For a decay, a missing IRF is the single most common
cause and nothing else is worth checking until it is attached.

## 2. Look at the residuals

`plot_fit` writes the fit and its weighted residuals. Read the *shape*:

* **Structure at the rising edge** — scattered light, or an IRF that is
  shifted relative to the data. Narrow the range or let the shift float.
* **A systematic arc across the whole range** — the model is missing a
  component.
* **Structure only in the tail** — the background level is wrong, or the tail
  is empty and dominated by counting noise; shorten the range.
* **Random residuals but chi-square still high** — the uncertainties are
  underestimated, not the model wrong. Check how the weights were derived.

Durbin-Watson quantifies exactly this: near 2 is random, well below 2 is
correlated.

## 3. Look at the parameters

`get_fit` shows values, bounds and uncertainties.

* A parameter **sitting exactly on a bound** is not a fitted value. Either the
  bound is wrong, or the model wants something unphysical — which usually
  means the model is wrong.
* An **enormous relative uncertainty** (tens of per cent or more) means the
  data does not constrain that parameter. Fix it, or remove the component it
  belongs to.
* Two parameters that are strongly redundant will both have huge
  uncertainties. Fixing one is the fix.

## 4. Only then, change the model

Add a component, change the model, or reconsider the experiment. Each addition
must earn its place: a few per cent of chi-square is noise, and every extra
component costs a degree of freedom and makes the others less certain.

## What not to do

Do not keep adding components until chi-square drops. Do not narrow the fit
range until the disagreement is outside it. Both make the number look better
and the answer worse. If the data cannot support the question, say so — that
is a useful result, and the user can measure again.
