# FRET check

A single-molecule FRET measurement checked in one pass: open a TTTR file (or a simulated example), the tool
detects the experiment (PIE or µs-ALEX, the routing channels, the excitation windows), finds the bursts,
corrects them and reports what to look at — photon trace, count rates, E/S histogram, lifetime and anisotropy
of every burst, and a QC list that names what is wrong with the measurement in plain words, with a PDF report
to download. All processing is local; nothing leaves the machine.

## How it works
1. Open a photon-stream file (PTU, HT3, PTU/ALEX .sm, PTO, SPC) or press the example button for a simulated
   measurement.
2. Check the detected experiment in **Channels and windows**: the micro-time histogram of every detector with
   the excitation windows marked. Fix a wrong guess and press Apply.
3. The **time trace** shows the count rate per stream in 1 ms bins with the bursts shaded; **E/S** shows the
   joint burst histogram with its marginals.
4. Read the QC verdict: occupancy, stoichiometry range, background fractions, mean count rate, burst density —
   each with a green/amber/red flag, and the Issues section names the cause and the fix for every red.
5. **Report** writes the A4 PDF (E/S, trace, count rates, diagnostics, checks table, issues); **ndX** holds the
   full burst table for gating and follow-up.

## Before trusting a result
The corrections (gamma, beta, background) default to neutral values — set yours before reading absolute E.
The QC flags compare the measurement against the comfort zones of a healthy confocal smFRET run; amber means
"look, this may be fine", red means "fix this before publishing".
