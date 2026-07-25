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

__all__ = [
    "background_series",
    "burst_log_likelihood",
    "burst_log_likelihood_reference",
    "collapse_bursts",
    "log_background_correction",
    "log_multinomial_pmf",
]
