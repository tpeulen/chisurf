"""Decay equations convolved with a measured response, as a view on BFF.

``tcspc_model.yaml`` beside this module holds the equations of time. BFF
builds each as a competing structure, convolves it with the IRF (the generic
``Convolution`` node) and runs it through the same counting instrument a
lifetime fit meets -- scatter, pile-up, scale, background, linearisation.
"""
from __future__ import annotations

import pathlib

from chisurf.core.models.description import for_catalogue

ParseDecayModel = for_catalogue(
    pathlib.Path(__file__).parent / "tcspc_model.yaml", name="Parse-Model",
    module=__name__, frame="equations_convolved")

__all__ = ["ParseDecayModel"]
