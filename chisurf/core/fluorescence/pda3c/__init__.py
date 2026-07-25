"""Three-colour photon distribution analysis (tcPDA) — compute core.

Qt-free forward model for [PRD-65](../../../../okf/prds/prd-65.md): the
burst-wise photon-partition likelihood that three-colour PDA fits, kept separate
from the two-colour family in :mod:`chisurf.core.models.pda` because it shares
neither the engine nor the data object with it (see the PRD).
"""

from __future__ import annotations

from .likelihood import (  # noqa: F401
    background_series,
    burst_log_likelihood,
    burst_log_likelihood_reference,
    collapse_bursts,
    log_background_correction,
    log_multinomial_pmf,
)
from .model import (  # noqa: F401
    BurstCounts,
    ThreeColorSpecies,
    simulate_bursts,
    total_log_likelihood,
)
from .physics import (  # noqa: F401
    ThreeColorSetup,
    blue_channel_probabilities,
    green_channel_probabilities,
    transfer_efficiencies,
)
from .species import (  # noqa: F401
    cholesky_to_statistics,
    covariance_from_statistics,
    covariance_to_cholesky,
    gauss_hermite_grid,
    nearest_positive_definite,
)

__all__ = [
    "BurstCounts",
    "ThreeColorSetup",
    "ThreeColorSpecies",
    "background_series",
    "blue_channel_probabilities",
    "burst_log_likelihood",
    "burst_log_likelihood_reference",
    "cholesky_to_statistics",
    "collapse_bursts",
    "covariance_from_statistics",
    "covariance_to_cholesky",
    "gauss_hermite_grid",
    "green_channel_probabilities",
    "log_background_correction",
    "log_multinomial_pmf",
    "nearest_positive_definite",
    "simulate_bursts",
    "total_log_likelihood",
    "transfer_efficiencies",
]
