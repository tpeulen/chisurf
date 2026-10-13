"""QuEst's domain: the simulation and everything it needs, Qt-free and host-free.

Relocated from the old in-tree ``quest/lib`` toolkit, which mixed the PET
workflow with a general-purpose structure library shadowing imp-tricks and
ChiSurf (okf/specs/imp-tricks-dedup.md).

============================  ====================================================
module                        owns
============================  ====================================================
:mod:`~quest.core.simulation`  the pipeline: ``simulate_project`` and the analysis
:mod:`~quest.core.dye_diffusion`  ``SimulateDiffusion``, ``DonorDecay``, PET chemistry
:mod:`~quest.core.photon`      photon-trace and decay kernels
:mod:`~quest.core.av`          accessible volumes, grids, FRET rate traces
:mod:`~quest.core.structure`   the ``Structure`` object
:mod:`~quest.core.structure.reader`         structure reading, through IMP.bff
:mod:`~quest.core.fps_json`    fps.json labeling files
:mod:`~quest.core.io`          point-cloud output
============================  ====================================================
"""

from chisurf.plugins.quenching_estimator.core.simulation import (  # noqa: F401
    DecaySimulationResult,
    aa_residence_from_model,
    autocorr,
    autocorr_to_tau_window,
    build_donor_from_project,
    calculate_aa_quenching,
    calculate_aa_residence,
    diffusion_coefficient_grid,
    load_project,
    sampled_density_grid,
    simulate_project,
    top_quenchers,
    write_mrc,
)

__all__ = [
    "DecaySimulationResult",
    "aa_residence_from_model",
    "autocorr",
    "autocorr_to_tau_window",
    "build_donor_from_project",
    "calculate_aa_quenching",
    "calculate_aa_residence",
    "diffusion_coefficient_grid",
    "load_project",
    "sampled_density_grid",
    "simulate_project",
    "top_quenchers",
    "write_mrc",
]
