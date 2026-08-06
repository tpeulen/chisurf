(concept-colocalization)=
# Colocalization: what the coefficients actually measure

Two colours, one image, one question: *do these two species occupy the same
structures?* The literature answers it with half a dozen coefficients, and they
are usually presented as a menu to choose from. They are not interchangeable —
each answers a **different** version of the question, and two of them are not
even about colocalization until you have fixed a threshold.

This page explains what each coefficient measures, why background and thresholds
dominate the numbers, and why a coefficient alone is never evidence. For the
step-by-step workflow in ChiSurf, see the {doc}`guide </guides/38_colocalization>`;
for runnable code, `examples/notebooks/Colocalization.ipynb` walks through every
section below on data whose answer is known by construction.

## The two questions hiding inside "colocalization"

Write the two channels as pixel intensities $G_i$ and $R_i$ over the same $N$
pixels. There are two genuinely different things one can ask:

1. **Co-occurrence** — is signal *present* in both channels at the same pixels?
2. **Correlation** — do the two intensities *rise and fall together*?

Two proteins can co-occur everywhere and correlate not at all (both fill the
cytosol, but their local amounts are unrelated), and they can correlate strongly
while occupying a tiny fraction of the image. Coefficients that subtract the mean
answer question 2; coefficients that do not answer question 1.

## Pearson's correlation coefficient (PCC)

$$
\rho = \frac{\sum_i (G_i-\bar G)(R_i-\bar R)}
            {\sqrt{\sum_i (G_i-\bar G)^2 \; \sum_i (R_i-\bar R)^2}}
$$

with $\bar G = \frac1N\sum_i G_i$. It runs from $-1$ (perfectly anti-correlated)
through $0$ (unrelated) to $+1$ (perfectly correlated), and it is **invariant to
gain**: doubling one detector's amplification does not change it. That invariance
is exactly why it is the default.

Two properties matter in practice:

- It is *not* invariant to an **offset**. A background pedestal compresses the
  dynamic range of both channels and drags $\rho$ toward the value of whatever
  correlation the background itself has.
- A single number cannot express asymmetry. If protein A is entirely inside
  compartment B, but B extends far beyond A, $\rho$ reports one intermediate
  value and hides the asymmetry completely.

## Manders' coefficients

Manders' **overlap coefficient** (MOC) drops the mean subtraction:

$$
\mathrm{MOC} = \frac{\sum_i G_i R_i}
                    {\sqrt{\sum_i G_i^2 \; \sum_i R_i^2}}
$$

For non-negative data it lies in $[0,1]$ and reports co-occurrence — question 1.
Because nothing is centred, *every* background photon contributes to both the
numerator and the denominator, which is why MOC on background-laden images is
almost always reassuringly high and almost always meaningless.

The **split coefficients** are the ones worth reporting:

$$
M_1 = \frac{\sum_{i \,:\, R_i > t_R} G_i}{\sum_i G_i},
\qquad
M_2 = \frac{\sum_{i \,:\, G_i > t_G} R_i}{\sum_i R_i}
$$

$M_1$ is the fraction of channel-G intensity that sits in pixels where channel R
is present, and $M_2$ is the mirror. They answer the asymmetric question directly:
"90 % of the protein is on the marker, but only 10 % of the marker carries
protein" is $M_1 = 0.9$, $M_2 = 0.1$ — a statement no single correlation
coefficient can make.

Note the thresholds $t_G, t_R$ in the definitions. **$M_1$ and $M_2$ are not
defined without a threshold**, which is why the next section is not optional.

## Thresholds, and why Costes' method exists

"Present" is a decision, not a measurement. Choosing $t_G$ and $t_R$ by eye
changes $M_1$ and $M_2$ at will, and it is the single largest reason published
colocalization numbers cannot be compared between papers.

Costes' method derives them from the data. Fit the channel pair with an
**orthogonal** (total-least-squares) regression — neither channel is an
error-free predictor of the other, so ordinary least squares is the wrong fit:

$$
R = a\,G + b, \qquad
a = \frac{\sigma_R^2-\sigma_G^2+\sqrt{(\sigma_R^2-\sigma_G^2)^2+4\sigma_{GR}^2}}
         {2\,\sigma_{GR}}, \qquad
b = \bar R - a\,\bar G
$$

Now walk a threshold $T$ down that line and, at each step, compute Pearson's
coefficient **restricted to the pixels below it** ($G_i \le T$ and
$R_i \le aT+b$). Where that below-threshold correlation first reaches zero, the
remaining pixels are statistically indistinguishable from uncorrelated
background. That crossing defines

$$
t_G = T^\ast, \qquad t_R = a\,T^\ast + b .
$$

The thresholds are then a property of the image, not of the operator.

## Li's ICQ and Spearman's coefficient

Li's **intensity correlation quotient** counts the *sign* of the covariance
product instead of its magnitude:

$$
\mathrm{ICQ} = \frac{\#\{\, i : (G_i-\bar G)(R_i-\bar R) > 0 \,\}}{N} - \frac12
$$

It lies in $[-0.5, +0.5]$: $+0.5$ is fully dependent staining, $0$ random,
negative segregated. Being a count, it is insensitive to a few very bright
outliers that can dominate $\rho$.

**Spearman's** coefficient is Pearson's applied to the *ranks*. It stays near $1$
for any monotonic relation, so it separates "the relation is non-linear" (high
Spearman, mediocre Pearson — e.g. detector saturation or a non-linear dye
response) from "there is no relation" (both low).

## A high coefficient is not evidence

Two dense stainings correlate because both fill the cell. Distinguishing real
colocalization from that baseline needs a null model, and the standard one is
**Costes' randomization test**:

1. Scramble one channel in blocks the size of the PSF. Block-wise scrambling
   preserves the intensity distribution *and* the local texture — the correlation
   that exists merely because fluorescence is spatially smooth — while destroying
   any genuine spatial relation between the channels.
2. Recompute $\rho$. Repeat a few hundred times to obtain a null distribution.
3. Report $p = \Pr(\rho_\text{random} < \rho_\text{measured})$. Colocalization is
   conventionally called significant at $p > 0.95$.

The block size is the one parameter that matters: blocks much smaller than the
PSF destroy the image's own smoothness and make nearly everything look
significant.

## Before any of it: are the channels registered?

Chromatic aberration and detector misalignment shift one channel by a fraction of
a micrometre — enough to destroy a real colocalization or, with periodic
structures, to fabricate one. **Van Steensel's** cross-correlation function
diagnoses it by shifting one channel and recomputing $\rho$ at each offset:

$$
\mathrm{CCF}(\delta) = \rho\bigl(G(x),\,R(x+\delta)\bigr)
$$

- Peak at $\delta = 0$, falling off symmetrically → registered; the coefficients
  mean what they say.
- Peak away from $0$ → a registration offset. Fix it before interpreting anything.
- Flat → no spatial relation at any offset.

## Where does the correlation live? Intensity-resolved PCC

One coefficient is an average over every pixel, so it cannot say *where* the
correlation comes from. Binning the pixels along an intensity axis and computing
PCC inside each bin can:

$$
\rho(I) = \rho\bigl(\{G_i, R_i : I \le d_i < I + \Delta I\}\bigr),
\qquad d_i \in \{G_i,\; R_i,\; G_i/R_i\}
$$

Each bin carries the standard error $(1-\rho^2)/\sqrt{n-3}$, so a noisy tail is
visibly noisy rather than silently wrong. Three readings are common:

- correlation that **rises with intensity** — real structures on an uncorrelated
  background (the usual, healthy case);
- correlation that **collapses at high intensity** — detector saturation or
  bleaching in one channel;
- correlation that depends on the **ratio** $G/R$ — a mixture of populations with
  different stoichiometries rather than one uniform species.

## Registration in two dimensions

Van Steensel's profile shifts one channel horizontally. A microscope, however, is
free to misregister in *any* direction, and a purely vertical offset leaves the
horizontal profile peaking at zero — it looks perfectly registered while the
channels are half a micrometre apart. The honest version is the full plane,

$$
\mathrm{CCF}(\Delta x, \Delta y)
  = \rho\bigl(G(x, y),\, R(x + \Delta x,\, y + \Delta y)\bigr),
$$

computed for every displacement at once by FFT and normalised the same way
(mean-subtracted product over the two standard deviations). The peak's position
*is* the registration offset; its width reports the size of the structures the
correlation comes from. The 1-D profile is the central row of this plane.

## The scatter plot is the raw data

All of the above are single numbers extracted from one 2-D object: the joint
histogram of $G_i$ against $R_i$. Colocalized structures form a tilted cloud
through the origin; segregated ones form two lobes along the axes; a saturated
detector bends the cloud; a background pedestal shifts the whole cloud away from
the origin.

Reading it first, and gating a region of it to interrogate a subpopulation, tells
you more than any coefficient — the coefficients are summaries of this picture,
and a summary is only trustworthy once you have seen what it summarises.

## When pixels are the wrong unit: object-based colocalization

Everything above treats each pixel as a sample of two intensities. For **punctate**
signal — vesicles, granules, foci — that is the wrong unit. Sparse spots sit
mostly on empty background, so a correlation coefficient is dominated by the
co-occurrence of *nothing*: it can be near zero for perfectly coincident puncta
(few pixels carry any signal at all) and respectably high for spots that merely
share a crowded region.

The object-based approach segments each channel into discrete objects and asks
countable questions instead:

- **How far is each object from the nearest object of the other channel?** The
  distribution of nearest-neighbour distances is the raw result — a peak at short
  distance is coincidence, a broad distribution centred on the mean inter-object
  spacing is chance.
- **What fraction have a partner within a tolerance $d$?** This is the headline
  number, and $d$ is the one honest parameter: two objects cannot be localised
  better than the PSF, so "coincident" means "closer than the resolution", never
  "identical centroid".
- **What fraction of centres fall *inside* an object of the other channel?** A
  stricter, tolerance-free variant (Bolte & Cordelières' second object measure).
- **How much of each object's area is covered by the other channel?** The
  object-level analogue of Manders' fractions.

All four are asymmetric, so — like $M_1$/$M_2$ — they are reported in both
directions. Segmentation itself has the usual knobs (threshold, minimum size,
optional smoothing, optional watershed splitting of touching objects), and the
threshold should be the same one the pixel-wise coefficients use, so both regimes
agree on what "present" means.

Object- and pixel-based results are complements, not alternatives: report the
coefficients for continuous distributions, the object statistics for puncta, and
be suspicious when a dataset gives a confident answer in the regime it does not
belong to.

## Restricting the analysis: regions of interest

Coefficients computed over a whole field of view mix everything in it — cells and
empty medium, healthy cells and debris. Restricting the analysis to a drawn
region is therefore not cosmetic: the background estimate, the Costes threshold
search, the randomization null model and the coefficients must all see the *same*
pixels, or the region changes the numbers twice over. Report the region alongside
the coefficients, exactly like the thresholds.

## What to report

A defensible colocalization result is not one number but a small set:

| Report | Because |
| --- | --- |
| PCC | the standard correlation measure |
| $M_1$ and $M_2$ | the asymmetry PCC cannot express |
| The thresholds, and how they were chosen (ideally Costes) | $M_1$/$M_2$ are meaningless without them |
| Costes $p$-value with its block size | separates real colocalization from dense-staining chance |
| van Steensel peak shift (or the 2-D CCF peak) | shows the channels were registered |
| The region analysed, if not the whole image | the coefficients depend on it |
| For puncta: object counts, the coincident fraction **and** the tolerance | correlation coefficients do not describe sparse spots |

## References

- {cite}`dunn2011` — the practical guide: which coefficient answers which question.
- {cite}`manders1993` — the overlap coefficients M1/M2 and what they do and do not measure.
- {cite}`costes2004` — the automatic threshold and the randomisation test for significance.
- {cite}`li2004` — the intensity-correlation-quotient, an alternative to a single coefficient.
- {cite}`bolte2006` — a tour of the pitfalls: bleed-through, sampling and object-based analysis.
- {cite}`vansteensel1996` — the cross-correlation-versus-shift test that separates real overlap from chance.

