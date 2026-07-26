# Photon-by-photon kinetics (Gopich–Szabo)

This tool fits a kinetic scheme directly to the **arrival time and colour of
every photon**. It never bins, so it resolves exchange faster than any bin you
could have chosen — down to the mean interphoton time.

## What it answers

Given bursts of donor and acceptor photons, it returns

* the **rate constants** between states, in s⁻¹;
* the **FRET efficiency** of each state;
* the equilibrium **population** of each state, implied by the rates;
* optionally, an upper bound (or a measurement) of how long a **transition
  itself** takes.

## When to use it rather than a histogram

A burst-wise FRET histogram shows a molecule that switches faster than the burst
duration as a single broadened peak, or a smear between two peaks. It cannot say
how fast. This method can, because the evidence it uses is the *pattern* of
colours in time, not their sum.

The practical range is set by two limits you cannot argue with:

* **Fastest:** exchange faster than the interphoton time is invisible. At
  50 kHz detected photons that is roughly 20 µs.
* **Slowest:** exchange slower than a burst leaves no transition inside a burst
  to see. A static mixture is the right model there, and it will fit better.

Between them, the method is the sharpest tool available.

## How to run it

1. Drop the `.bur` burst tables, point **TTTR folder** at the raw files, and
   check the donor and acceptor **channel** lists.
2. Check the **macro-time tick**. Zero reads it from the file header. Every
   fitted rate is proportional to it, so a wrong value rescales the entire
   answer without any other symptom.
3. Choose the number of **states** and press **▶ Fit**.

If you have no data to hand, tick **Simulate**: it generates photons from a
molecule with known rates, which is the only way to find out what your photon
budget can actually resolve.

## Reading the result

**Rates and 1/k.** The waiting time `1/k` is usually the more intuitive number.
Compare it with the burst duration: if `1/k` is much longer than a burst, most
bursts contain no transition and the rate is poorly determined however confident
the fit looks.

**Relaxation time.** The observable combination. For two states it is
`1/(k₁₂ + k₂₁)` — the timescale a perturbed population returns to equilibrium,
and the one a correlation measurement would report.

**BIC.** Add a state only when the BIC clearly falls. An extra state always fits
a little better, because it always has more parameters.

**Cross-check with H2MM.** Fits the same photons with the discrete-time H2MM
engine. The two share no code and parameterise time differently — H2MM fits a
per-tick transition *probability*, this fits a *rate* — so agreement is real
evidence. Disagreement beyond a few per cent is worth chasing before believing
either.

## The transition-time scan

A two-state model assumes switching is instantaneous. It is not: crossing a
barrier takes a finite time, and for protein folding that transition-path time is
a quantity people want.

The scan inserts an explicit intermediate the molecule must pass through and
plots the log-likelihood against how long crossing takes, relative to the
instantaneous model.

**Expect an upper bound, not a measurement.** A crossing much faster than the
photon rate leaves no trace at all, so the curve is flat at zero for short
durations and falls for long ones. That flat region is the honest answer: the
crossing is faster than the point where the curve starts to fall. Only a clear
positive peak is a measurement, and it deserves a likelihood-ratio test before
you report it.

The intermediate's efficiency defaults to the mean of the two end states. That
is an assumption, not a derivation — a real transition path need not sit halfway.

## The state path

**Decode state path** computes the most likely state of every photon (Viterbi).
It is an illustration of the fitted model, not a measurement: it assigns a
definite state to every photon, including in bursts that contain no evidence for
any transition at all. Use it to look at examples; never to count transitions.

## Caveats worth taking seriously

* **Efficiencies here are apparent**, not corrected for leakage, direct
  excitation or detection efficiency. Calibrate with the Accurate FRET tool and
  interpret the state efficiencies in the same frame.
* **Photons in neither channel list are dropped.** For ALEX data that correctly
  removes acceptor-excitation photons; check the counts in the report.
* **Two states closer together than the shot-noise width cannot be separated.**
  The fit will still return two, and they will still look precise.
* **Background photons are not modelled.** They act as an extra colour source
  with no state dependence and bias the efficiencies toward each other.
