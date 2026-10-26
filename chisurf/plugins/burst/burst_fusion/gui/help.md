# Burst Fusion

A molecule crossing the confocal spot does not always leave one burst. It
wanders out and back, or dims for a few hundred microseconds, and the burst
search — which sees only a count rate — cuts one passage into two or three
bursts. Every fragment is then counted as its own molecule: the photon-count
distribution grows a short tail, each fragment's proximity ratio is noisier than
the passage as a whole, and a dynamics analysis can read the gap as a
transition.

This step merges those fragments back together and writes the result as a **new
burst run** of the same measurement, which every later step (BVA, 2CDE, MLE, H2MM,
the browser) reads exactly like the original one. The run you started from is not
modified.

## Where the bursts come from

The **Input** section lists the burst runs in the Datasets workspace — every burst
search of your photon data, shown under its photon stream. Pick one there, or use
*Open in…* on a run in the Datasets view. Nothing in this tool opens a file: data
enters ChiSurf by dropping it on the window, and the runs live in the project's
analysis container of each photon dataset.

## If you have not brought data

Press **🧪 Load example**. It simulates a measurement in which a *declared* number
of molecules (300) crossed the focus and about 60 % of those crossings were
interrupted — the molecule dimming for a fraction of a millisecond and coming
back — then runs the ordinary burst search over it and puts the result into the
workspace: the photons a dataset, the search a burst run of it, which is picked. The
search turns those 300 molecules into 419 bursts, and the status block
keeps the 300 on screen so every number below can be checked against it.

It is a real measurement: a photon file with macro times, micro times and
channels and a real burst search. The simulation is
deliberately thin — one FRET population, no photophysics, no diffusion model —
because it exists to demonstrate *the fusion decision*, and anything measured on
it is a statement about the code rather than about a molecule.

## How it decides

The question "did these two bursts come from the same molecule?" is answered by
the recurrence analysis of Hoffmann *et al.*: the autocorrelation `G(τ)` of the
burst arrival times gives

    P_same(τ) = 1 − 1/G(τ)

the probability that a burst arriving a lag `τ` after another one is the *same*
molecule recurring rather than a different molecule arriving by chance. For an
uncorrelated (Poisson) burst stream `G = 1` and `P_same = 0`.

You set the threshold. The curve is inverted into the longest lag at which
`P_same` still meets it, and every run of consecutive bursts closer together
than that lag becomes one burst. The plot shows the curve, your threshold
(dashed) and the lag actually fused up to (dotted), so the choice is visible
rather than implied.

The lag is the difference of burst **mean macro times** — the same quantity the
curve is built from, so a threshold means on a pair of bursts exactly what the
plot says it means.

## The gap ceiling, and why it is not optional

A burst on disk is one `(first photon, last photon)` interval. A fused burst is
therefore the *span* across its fragments and **contains the photons between
them** — which are mostly background.

At low concentration `P_same` legitimately stays above 0.5 out to tens of
milliseconds: the molecule really is the same one, because there is hardly
anyone else in the sample. Fusing on that is correct about the molecule and
ruinous for the burst — at a few kHz of background a 70 ms gap adds hundreds of
background photons to a burst that had a few hundred real ones.

So the probability answers *"same molecule?"* and the **gap ceiling** answers
*"at what cost?"*. The default of 10 ms admits the case this step exists for — a
single passage the search cut in two, gaps of microseconds to a few
milliseconds — and stops there. Set it to 0 only if you know why.

The fused run records the price per burst: `Fused Gap Photons` in its
`assembly` table is the number of photons the bridged gaps brought in.

## Preview versus written

*Estimate* is cheap and repeatable: it reads the burst tables only, so the fused
side of the histograms is the fragments' own photons, summed. *Run (Fuse)*
(which writes the fused run) reopens the photon streams and re-derives every column over the real
span; the plots then switch to the written bursts (the legend says which is on
screen). The two differ by exactly the background the gaps brought in.

## What is written

A new run of the same container (in a project: the photon dataset's analysis
container), named after the source run and the threshold:

    <source run> fused p0.50/
      bursts        the fused bursts, regenerated from the photons
      assembly      per fused burst: fragments merged, background gained
      membership    which source burst went into which fused burst

The fused bursts are stored as a burst selection — found by fusing a search, which
their algorithm (`recurrence_probability`), their settings and their parent edge to
the source search record — so every reader takes them as a run. The **source** run
gains an optional `fusion groups` table giving each original burst its fused-burst
number, so the grouping can be inspected or gated on where the original bursts
live. (A legacy burst-analysis folder handed to the headless `csc fusion` command
is still fused into a new folder beside it.)

## Where it sits

It is an optional step directly after burst selection. Walking the pipeline past
it only estimates the probability — it never redirects the analysis on its own.
Writing the fused run is what points the later steps at the fused bursts.
Results computed on the source run (BVA, 2CDE, MLE, …) are **not** copied: they
have one row per *original* burst. Recompute them on the fused run — which is why
fusion belongs before them.

## The original method

The same-molecule probability this step decides on is not ours. It comes from
**recurrence analysis of single particles (RASP)**:

> Hoffmann, A., Nettels, D., Clark, J., Borgia, A., Radford, S. E., Clarke, J.
> & Schuler, B. (2011). *Quantifying heterogeneity and conformational dynamics
> from single molecule FRET of diffusing molecules: recurrence analysis of
> single particles (RASP).* **Physical Chemistry Chemical Physics** 13(5),
> 1857–1871. [10.1039/c0cp01911a](https://doi.org/10.1039/c0cp01911a)

That paper introduces `G(τ)` of the burst arrival times and
`P_same(τ) = 1 − 1/G(τ)`, and uses them for what they were meant for: choosing a
*recurrence window* in which a returning burst can be correlated with the one
before it, to read out dynamics slower than a single transit. ChiSurf does that
too — see [Recurrence analysis (RASP)](docs/concepts/recurrence.md) and its
[guide](docs/guides/02_recurrence_rasp.md).

**This step reads the same curve for a different purpose**, and the difference
is worth stating plainly: RASP *correlates* a recurring burst with its
predecessor and keeps them separate; fusion *merges* them into one burst. Where
the recurrence is a genuine return of a molecule that left, RASP is the right
reading and fusing would destroy the very dynamics it measures. Where the "two
bursts" are one uninterrupted passage the count-rate search cut in half, fusion
is the right reading. The gap ceiling is what keeps this step on the second
case: at sub-millisecond gaps a molecule has not gone anywhere, while the
tens-of-milliseconds recurrences RASP is built on are excluded by default. If
your interest is the slow dynamics rather than the split bursts, use recurrence
analysis and leave fusion alone.

If you publish results from this step, cite the paper above for the method, and
say which threshold and gap ceiling you used — both are recorded with the fused
run's burst table (its settings).

## Further reading

* [Burst fusion](docs/concepts/burst_fusion.md) — the theory and the assumptions.
* [Recurrence analysis (RASP)](docs/concepts/recurrence.md) — where `P_same` comes from.
* [Fusing recurring bursts](docs/guides/58_burst_fusion.md) — the worked workflow.
* [Photon bursts in smFRET](docs/concepts/smfret_bursts.md) — the burst folder and
  its companions.
* {cite}`nir2006`
