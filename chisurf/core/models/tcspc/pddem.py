"""Energy migration between two chromophores (PDDEM) by its classic dotted path: BFF's ``tcspc_pddem``."""
from __future__ import annotations

from chisurf.core.models.description import for_family

PDDEMModel = for_family("tcspc_pddem")

__all__ = ["PDDEMModel"]
