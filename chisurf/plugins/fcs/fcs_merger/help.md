# FCS curve merger

Averages several correlation curves into one, so a set of short acquisitions
becomes a curve worth fitting.

The averaging itself is arithmetic. The work is deciding **which curves belong
in it** — which is why this tool shows you every curve, its count rates and its
duration, and makes inclusion a per-curve tick rather than an assumption.

Press **Guide** for the walk-through.

## Why merge at all

A single short FCS acquisition is noisy, and the noise is worst exactly where
the information is: at short lag, where few photon pairs contribute. Longer
acquisitions fix that but expose the sample to more photobleaching, more drift
and more chances for an aggregate to wander through.

Many short acquisitions plus a merge gets the statistics without the exposure —
**and** gives you something a single long run cannot: the ability to look at the
repeats and throw away the ones that went wrong.

## What is averaged, and what that assumes

The curves are averaged point-by-point in lag. That is the right operation only
if every curve is a measurement of **the same thing**, because the mean of a set
of correlation curves is not generally the correlation curve of their union:

- **G(0) = 1/N.** Averaging curves taken at different concentrations gives a
  mean whose amplitude is the mean of the reciprocals, not the reciprocal of the
  mean. If the count rates differ across your repeats, the merged amplitude is
  not a concentration you can quote.
- **A drifting focus changes τ_D**, not just the amplitude, so merging across a
  realignment broadens the merged decay and reports a diffusion time nothing in
  the sample has.
- **Bleaching within a run** adds a slow component that averaging preserves
  faithfully — it does not cancel out just because several runs have it.

The count-rate and duration columns are there to make these visible before you
merge, not after.

## Which curves to leave out

**Aggregates are the main reason this tool has checkboxes.** One bright particle
crossing the focus produces a large, slow correlation contribution, and because
G is normalised by the *square* of the mean intensity, a single such event can
dominate a whole curve. On the plot it is unmistakable once you know it: an
amplitude well above the others and a shoulder at long lag.

Averaging that curve in does not dilute it — it moves the mean. Untick it.

Also exclude:

- **curves whose count rate differs markedly** from the rest (a different sample
  state, a different focus depth, or a bubble);
- **the first curve of a session**, often taken before the temperature settled;
- **anything whose shape is qualitatively different**, rather than noisier. Noise
  averages down; a different shape does not.

The rule of thumb: if you would not have believed the curve on its own, it does
not become believable by being averaged with better ones.

## Reading the two plots

**Left** — every loaded curve, with the unticked ones dashed and grey. This is
the screening view: look for one curve sitting above the family, or a shoulder
the others do not have.

**Right** — the merge of the ticked curves. It should look like the family it
came from, with less scatter. If it has a feature none of the individual curves
has, something in the set is dominating it.

Adding the result to ChiSurf writes it as an FCS dataset, ready to fit.

## Before believing the merged curve

- **Do the ticked curves agree in amplitude?** If not, they are not the same
  concentration and the merged G(0) means nothing.
- **Do they agree in shape?** Overlay is what merging assumes; scatter is what
  it fixes.
- **How many curves survived?** A mean of three is a mean of three, however
  smooth it looks. The improvement in noise goes as √n and nothing more.
- **Would the conclusion change if you unticked the most extreme curve?** If it
  would, the answer rests on that curve and not on the merge.

## Further reading

- [FCS correlation](docs/concepts/fcs_correlation.md) — what G(τ) is and why
  G(0) = 1/N.
- [Diffusion by FCS, step by step](docs/guides/09_diffusion_fcs.md)
- [FCS toolbox: correlate, merge, convert](docs/guides/75_fcs_toolbox.md) — the
  workflow this merger is step 5 of, and where its error bars come from.
- [Combining repeats](docs/guides/35_combining_repeats.md)
- [FCS confocal calculator](docs/concepts/fcs_correlation.md) — for turning the
  merged τ into D, r_h and a concentration.
