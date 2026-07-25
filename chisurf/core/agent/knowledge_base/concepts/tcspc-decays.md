---
type: Concept
title: Time-resolved fluorescence decays
description: >-
  What a TCSPC measurement contains, why the instrument response has to be
  deconvolved, and how many lifetime components are honest.
tags: [tcspc, decay, lifetime, irf, deconvolution]
timestamp: '2026-07-25T00:00:00Z'
---

# What is measured

A TCSPC measurement is a histogram of the delay between exciting a sample and
detecting a photon, accumulated over many excitation cycles. With enough
photons its shape is the fluorescence decay — but convolved with the
instrument's own response, and sitting on a background.

The counts are Poisson distributed, so the uncertainty of a channel is
roughly the square root of its content. That is why the tail, with few
counts, carries little weight and the rising edge carries a lot.

# The instrument response

The measured curve is the true decay convolved with the **IRF**: the response
the instrument gives to a signal with no lifetime of its own, measured on a
scattering sample. It is a separate measurement, and its file name usually
contains `irf`, `prompt` or `lamp`.

Fitting a decay without deconvolving the IRF answers the wrong question. The
fitted lifetimes come out too long, because part of what is being fitted is
the instrument. On the sample donor decay the difference is stark: without an
IRF a one-lifetime fit reaches chi2r 8.5 and looks merely poor; with the IRF
attached the same model reaches 12.8, because the fit can no longer hide its
inadequacy behind the instrument.

An IRF is only valid for the measurement it belongs to — same instrument
settings, same detector, same time calibration. A mismatched IRF will not
deconvolve, and no number of components will rescue it.

# How many components

Real samples rarely decay with a single exponential: different environments,
conformations and quenching pathways each contribute. Fitting is therefore a
sum of exponentials, and the count is a judgement.

On the sample donor decay, with the IRF attached: one lifetime gives chi2r
12.8, two give 1.37, three give 1.03. The progression stops there — a fourth
buys nothing.

Each component costs a degree of freedom and makes the others less certain,
and beyond three or four the individual lifetimes stop being separable at
all: many combinations describe the data equally well. Decide with an F-test
rather than by eye, and treat amplitudes of a component that is not clearly
justified as meaningless.

# What the parameters mean

* **Lifetimes** are properties of the fluorophore in its environment.
* **Amplitudes** (often normalised fractions) are how much of the signal each
  component contributes — related to, but not the same as, the fraction of
  molecules.
* **Scatter** and **background** absorb light that is not fluorescence. If
  either runs to an implausible value, look at the measurement rather than
  the model.
* **The time shift** between IRF and decay is a real instrumental quantity and
  usually needs to be free.

# When it will not fit

Scattered light at the rising edge, an empty tail dominated by counting
noise, a shifted or mismatched IRF, or a genuinely non-exponential decay. The
residuals say which: structure at the rise points at the IRF or scatter,
structure across the whole range at a missing component, structure only in the
tail at the background or the range.
