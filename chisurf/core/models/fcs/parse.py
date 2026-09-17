"""Equation models for FCS correlation curves, as a view on BFF.

The catalogue beside this module is ChiSurf's; BFF builds each entry as a
competing structure over the measurement's coordinates and owns the fit.
"""

from __future__ import annotations

import pathlib

from chisurf.core.models.description import for_catalogue

ParseFCSModel = for_catalogue(
    pathlib.Path(__file__).parent / "models.yaml",
    name="Parse-Model",
    module=__name__,
    reference_modes=("fcs_diffusion", "fcs_molecules"),
)

__all__ = ["ParseFCSModel"]
