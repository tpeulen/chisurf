(concept-burst-fusion)=
# Burst fusion: putting one molecule's bursts back together

A burst search knows one thing about a molecule: the count rate it produces. So
when a molecule crossing the confocal spot dips below the threshold for a few
hundred microseconds — it wanders to the edge of the volume and back, the
acceptor blinks, the dye rotates into a dim orientation — the search ends one
burst and starts another. One passage becomes two bursts, or three.

Nothing downstream can tell that apart from two molecules. The consequences are
systematic rather than random:

* The **photon-count distribution** grows a tail of short, dim bursts that no
  molecule ever actually produced, and a `min_photons` floor then rejects them —
  discarding real signal.
* Each fragment carries fewer photons than the passage, so its **proximity
  ratio** is broadened by shot noise. The FRET histogram is wider than the
  sample is heterogeneous, and a fit reads that width as a distribution of
  states.
* A **dynamics analysis** sees a burst end and another begin where the molecule
  merely dimmed, which is not a transition.

**Burst fusion** merges the fragments back into one burst. The question it has
to answer first is which bursts belong together, and that question already has a
quantitative answer.

For the step-by-step workflow in ChiSurf see the guide
{doc}`/guides/58_burst_fusion`.

## The decision: the same-molecule probability

Recurrence analysis ({doc}`RASP <recurrence>`) defines the **same-molecule
probability** from the normalized autocorrelation $G(\tau)$ of the burst arrival
times:

$$
P_\text{same}(\tau) = 1 - \frac{1}{G(\tau)} .
$$

For an uncorrelated (Poisson) burst stream $G = 1$ and $P_\text{same} = 0$: a
burst arriving a lag $\tau$ after another one is a chance coincidence between
two different molecules. Where a molecule recurs, short-lag pairs are enriched
above that random background, $G > 1$, and $P_\text{same}$ rises towards 1.

Fusion inverts the curve. The user names a probability; the largest lag at which
$P_\text{same}$ still meets it is the **fusion window** $\tau_\text{max}$, and
every run of consecutive bursts separated by less than $\tau_\text{max}$ becomes
one burst. A threshold of 1 fuses nothing. Lower thresholds fuse more, and
eventually start merging genuinely different molecules — which is why ChiSurf
plots the curve, the threshold and the resulting window together rather than
reporting a number.

Three details of the estimate matter in practice:

**The lag is measured between burst mean macro times**, the same quantity the
curve is built from, so a threshold read off the plot means on a pair of bursts
exactly what the plot says it means.

**The window is read from the long end of the curve, not the short end.**
$P_\text{same}$ is *not* monotonic: at the very shortest lags it dips, because
nothing recurs faster than a burst is long and those bins hold coincidences
between different molecules and little else. Taking the last lag above the
threshold — the recurrence time as the literature states it — is robust to that
dip; scanning outward from the shortest lag would read the dip as "different
molecule" and fuse nothing at all.

**Pairs are counted within a measurement and pooled across the folder.** Two
files are separate acquisitions and a burst in one cannot recur in the other, so
lags never cross a file boundary. But counted and expected pair numbers are
*additive*, so they are summed over all measurements before dividing
($G = \sum \text{counts} / \sum \text{expected}$). Ten short files then resolve a
curve that none of them resolves alone. Averaging per-file $G$ estimates instead
would over-weight the shortest file.

## Fusion is transitive

If A fuses with B and B with C, all three become one burst — even when A and C
are further apart than $\tau_\text{max}$. That is the physically right reading:
the molecule was in the volume the whole time. It is also how a chain runs away
in a dense measurement, so the number of fragments one fused burst may contain is
capped explicitly.

## The cost: a fused burst is one interval

Here the method meets the file format, and the constraint is not cosmetic. A
burst on disk is one `(first photon, last photon)` interval. A fused burst is
therefore the **span** from the first photon of the first fragment to the last
photon of the last — and it contains the photons *between* the fragments, which
are mostly background.

This is where a correct probability produces a bad burst. At low concentration
$P_\text{same}$ legitimately stays above 0.5 out to tens of milliseconds: the
molecule really is the same one, because there is hardly anyone else in the
sample. Fusing on that is right about the molecule and ruinous for the burst —
at a few kHz of background a 70 ms gap adds hundreds of background photons to a
burst that had a few hundred real ones, and every corrected quantity computed
from it is wrong.

So fusion has two controls, answering two different questions:

| Control | Question it answers |
|---|---|
| Same-molecule threshold | Is this the same molecule? |
| Gap ceiling | What does bridging this gap cost? |

The gap ceiling caps the probability window. Its default (10 ms) admits the case
fusion exists for — a single passage the search cut in two, with gaps of
microseconds to a few milliseconds — and stops there. The number of background
photons each fused burst gained is written out per burst, so the price is
visible rather than assumed.

## What fusion should do to your data

Fusion is diagnosable, and it is worth checking rather than trusting:

* **Bursts** falls, by roughly the fraction of passages that were being split.
* **Photons per burst** rises, and the short-burst tail of the distribution
  loses weight — the fragments were the tail.
* **Proximity-ratio width** falls, while the **mean** stays put. That is the
  signature of a shot-noise artefact being removed. If the mean moves
  substantially, the threshold is merging different populations, not fragments
  of one.
* **Duration** rises, because bridged gaps are inside the bursts now. A rise of
  orders of magnitude means the gap ceiling is too generous.

## Where it sits in the pipeline

Fusion changes *what a burst is*, so it belongs before everything that measures
one: it is an optional step directly after burst selection and before BVA, 2CDE,
the per-burst MLE and H2MM. It writes a **new** burst-analysis folder and never
modifies the one it read, so a threshold can be tried, inspected and discarded.

Per-burst results already computed on the un-fused folder — BVA, 2CDE, MLE
lifetimes — are deliberately *not* carried across. They have one row per un-fused
burst, and a burst-analysis folder is
{doc}`merged column-wise by position </concepts/smfret_bursts>`: copying them
would not fail, it would silently report one burst's lifetime against another's
efficiency. They are recomputed on the fused folder instead.

## Related

* {doc}`Recurrence analysis (RASP) <recurrence>` — where $P_\text{same}$ comes from.
* {doc}`Photon bursts in smFRET <smfret_bursts>` — the burst folder and its companions.
* {doc}`Burst variance analysis <bva>` and {doc}`2CDE <burst_2cde>` — steps that
  read the folder fusion produces.

## References

- Hoffmann, A. *et al.* (2011) Quantifying heterogeneity and conformational
  dynamics from single molecule FRET of diffusing molecules: recurrence analysis
  of single particles (RASP). *Phys. Chem. Chem. Phys.* **13**, 1857–1871.
  [10.1039/c0cp01911a](https://doi.org/10.1039/c0cp01911a)
- Nir, E. *et al.* (2006) Shot-noise limited single-molecule FRET histograms:
  comparison between theory and experiments. *J. Phys. Chem. B* **110**,
  22103–22124. [10.1021/jp063483n](https://doi.org/10.1021/jp063483n)
