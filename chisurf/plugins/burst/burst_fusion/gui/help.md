# Burst Fusion

A molecule crossing the confocal spot does not always leave one burst. It
wanders out and back, or dims for a few hundred microseconds, and the burst
search — which sees only a count rate — cuts one passage into two or three
bursts. Every fragment is then counted as its own molecule: the photon-count
distribution grows a short tail, each fragment's proximity ratio is noisier than
the passage as a whole, and a dynamics analysis can read the gap as a
transition.

This step merges those fragments back together and writes the result as a **new
burst folder**, which every later step (BVA, 2CDE, MLE, H2MM, the browser) reads
exactly like the original one. The folder you started from is not modified.

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

The emitted folder records the price per burst: `Fused Background Photons` in
its `fu4` companion is the number of photons the bridged gaps brought in.

## Preview versus written

*Analyze* is cheap and repeatable: it reads the burst tables only, so the fused
side of the histograms is the fragments' own photons, summed. *Write fused
folder* reopens the photon streams and re-derives every column over the real
span; the plots then switch to the written bursts (the legend says which is on
screen). The two differ by exactly the background the gaps brought in.

## What is written

    <source>_fused_p0.50/
      bi4_bur/<stem>.bur        the fused bursts, regenerated from the photons
      fu4/<stem>.fu4            per fused burst: fragments merged, background gained
      Info/analysis.json        how the raw data was read (so later steps need not guess)
      Info/fusion.json          the settings, the window, the P_same curve, the statistics

and, in the **source** folder, an optional `fg4` companion giving each original
burst its fused-burst number, so the grouping can be inspected or gated on
where the original bursts live.

## Where it sits

It is an optional step directly after burst selection. Walking the pipeline past
it only estimates the probability — it never redirects the analysis on its own.
Writing the fused folder is what points the later steps at the fused bursts.
Companions computed on the source folder (BVA, 2CDE, MLE, …) are **not** copied:
they have one row per *original* burst and would misalign. Recompute them on the
fused folder — which is why fusion belongs before them.

## Further reading

* [Burst fusion](docs/concepts/burst_fusion.md) — the theory and the assumptions.
* [Recurrence analysis (RASP)](docs/concepts/recurrence.md) — where `P_same` comes from.
* [Fusing recurring bursts](docs/guides/58_burst_fusion.md) — the worked workflow.
* Hoffmann *et al.*, *Phys. Chem. Chem. Phys.* **13**, 1857 (2011),
  [10.1039/c0cp01911a](https://doi.org/10.1039/c0cp01911a)
