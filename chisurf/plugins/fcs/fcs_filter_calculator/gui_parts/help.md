# Filtered FCS — the lifetime filter calculator

Ordinary FCS correlates the *total* intensity. When two species have the same
diffusion time, or a detector artefact rides on top of the real signal, the plain
autocorrelation cannot separate them — there is nothing in one intensity trace to
separate.

Filtered FCS uses a dimension the plain correlation throws away: every photon
carries a **nanosecond arrival time after the excitation pulse**, and different
species have different decay patterns. This tool turns those patterns into
per-photon **weights**, and correlating the weighted streams gives
species-selective curves.

Press **Guide** for the walk-through.

## What a filter actually is

Give the tool the normalised micro-time pattern *p<sub>s</sub>(t)* of each
component. A photon at micro-time *t* could have come from any of them, so it is
not assigned to one — it is given a **filter value** *F<sub>s</sub>(t)* saying how
much it counts towards component *s*.

Two consequences that surprise people:

**Filter values go negative.** They are not probabilities. A negative weight is
how the method *subtracts* a component's expected contribution from a region of
the decay it shares with another. A filter that never goes negative usually means
the patterns are not actually distinguishable.

**The filters depend only on the patterns, not on the data.** Once the component
decays are fixed, the filters follow. That is why everything on this page is
about getting the patterns right.

## Where the patterns come from

**Auto-fit** decomposes the measured mixed decay into *N* lifetime components and
offers them as species. It is a starting set, not an answer: a two-component fit
to a three-component sample gives two patterns that are each a blend.

**Measured references** are better whenever you can get them — the pure species
measured separately, under the same optics.

**Unmix** fits non-negative component intensities and computes the filters.

## The three things that decide the answer

**The patterns must be genuinely different.** Two lifetimes within about 20 % of
each other cannot be separated no matter how many photons you collect. The filter
amplitudes blow up and the "separated" curves are amplified noise that looks like
a clean result.

**The IRF and the fit range.** The patterns are compared over a micro-time range
you choose. Include the rise and you are partly fitting the IRF; start too late
and you have thrown away where the components differ most.

**Scatter and background are components too.** Scattered excitation light has its
own micro-time pattern — essentially the IRF — and if you do not give it a
component it will be absorbed into the others, distorting both.

## Before you believe a species curve

1. **Do the amplitudes look sane?** Filter values in the tens or hundreds mean an
   ill-conditioned separation, not a sensitive one.
2. **Does the reconstruction match the measured decay?** If the components cannot
   rebuild the mixed decay, they do not describe the sample.
3. **Do the species cross-correlations behave?** For species that do not
   interconvert, the cross-correlation should be flat. Structure in it is the
   most direct sign that the patterns are wrong.
4. **Change the number of components.** A real separation is stable; an
   over-specified one redistributes wildly.

## Further reading

- [Filtered FCS (fFCS / FLCS) and 2D-FLCS](docs/concepts/filtered_fcs.md)
- [FCS correlation](docs/concepts/fcs_correlation.md)
- [Filtered FCS, step by step](docs/guides/17_filtered_fcs.md)
- [Diffusion and FCS](docs/guides/09_diffusion_fcs.md)
- [FRET-FCS](docs/guides/16_fret_fcs.md)
