Introduction
############

ChiSurf is an interactive platform for the **global analysis** of fluorescence
data: time-correlated single-photon counting (TCSPC) decays, fluorescence
correlation spectroscopy (FCS) curves, and single-molecule FRET measurements.
"Global" is the point of it — several data sets are fitted at once against
models whose parameters are *linked*, so a quantity that is physically shared
(a g-factor, a diffusion time, a donor lifetime) is determined once from
everything that constrains it rather than separately from each curve.

This part of the documentation covers the **fitting interface itself** and the
**worked examples**. Read it in the order it is listed:

* *The fitting interface* — importing data, choosing a model, creating a fit,
  the analysis dock, parameters and linking, scoring, optimisation, sampling and
  plots. This is the machinery every analysis in ChiSurf goes through.
* *Fluorescence decay models* — the model families for time-resolved data, from
  a plain multi-exponential decay to FRET distance distributions.
* *Correlator plugin* and *Parameter dependency graphs* — the two tools that sit
  beside the fitting window most often.
* *Worked examples* — calibrating an FCS setup, live-cell FCS/FCCS, simulated
  data, and a joint anisotropy analysis that determines the g-factor and the
  depolarisation factors. Each is a complete analysis with screenshots.

The other two layers of the documentation answer different questions.
:doc:`Concepts </concepts/index>` explain the *theory* — what a correlation
curve is (:ref:`concept-fcs-correlation`), what a lifetime measures
(:ref:`concept-tcspc-lifetime`), what anisotropy reports
(:ref:`concept-anisotropy`) — and the :doc:`Guides </guides/index>` are
task-focused walkthroughs of the single-molecule analyses. Where a page here
explains *which control*, the concept page explains *why*.

.. note::

   This manual was written alongside an earlier version of the interface. Where
   a screenshot and the running application disagree, the application is right;
   the workflows themselves have not changed. Pages are checked and signed off
   one at a time — the *Authoring* toolbar in the documentation browser shows
   which of them have been.
