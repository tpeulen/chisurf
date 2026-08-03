"""Fitting kinetic models to two-dimensional multiparameter-fluorescence histograms.

The plots that define multiparameter fluorescence detection — FRET efficiency
against donor lifetime, and anisotropy against lifetime — are ordinarily *read*:
a static line is drawn on top and the deviation from it discussed. This package
makes them **fitted**, by forward-modelling the raw per-burst observables over an
empirical nuisance measure taken from the bursts themselves.

The design is [PRD-71](../../../okf/prds/prd-71.md); the groundwork underneath it
is [PRD-72](../../../okf/prds/prd-72.md). Four ideas carry it:

1. **The burst statistics come from the experiment**, photon-distribution-analysis
   style: the nuisance measure is the *empirical* joint distribution of the burst
   signal and the per-channel observation spans (:mod:`~.prepare`), so no
   brightness law is assumed and no optical nuisance parameter enters.
2. **The lifetime axis is the mean micro time**, whose conditional distribution is
   analytic, rather than a per-burst lifetime fit, which is biased at the 50–500
   photons a burst has (:mod:`~.moments`).
3. **Everything is fitted in raw observable space**, with the corrections and the
   background living in the forward model, so the data histogram is built once and
   a freed correction factor cannot move the fit's own target.
4. **Three composable scoring sources over one model core** — individual bursts,
   marginalized 2D histograms, and pooled per-bin decays.

Qt-free throughout: the GUI, the CLI and the experiment reader are surfaces over
this package, never the other way round.
"""

from chisurf.core.fluorescence.mfd.prepare import (
    BurstPreparation,
    NuisanceMeasure,
    PhotonIndexConvention,
    SourceResolution,
    UnresolvedPhotonSource,
    nuisance_measure,
    photon_bursts,
    prepare_burst_folder,
    resolve_sources,
)

__all__ = [
    "BurstPreparation",
    "NuisanceMeasure",
    "PhotonIndexConvention",
    "SourceResolution",
    "UnresolvedPhotonSource",
    "nuisance_measure",
    "photon_bursts",
    "prepare_burst_folder",
    "resolve_sources",
]
