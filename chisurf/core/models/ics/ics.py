"""Image-correlation models (RICS, STICS, TICS, iMSD), as a view on BFF.

One catalogue, ``models.yaml`` beside this module, holds the carpet equations
over the coordinates the ICS reader records with the data: the pixel lag
``xi``, the line lag ``psi`` and the lag time ``tau``. BFF builds each equation
as a competing structure, so the 3D and membrane geometries and the 2D
Gaussian are compared on BIC like any other model family; which lag times a
fit constrains is set by the carpet (one frame lag is RICS, several are
STICS/TICS), and releasing ``alpha`` is iMSD.

``IcsGaussian2DModel`` names the same model: the 2D Gaussian is an entry of the
catalogue, not a model of its own.
"""

from __future__ import annotations

import pathlib

from chisurf.core.models.description import for_catalogue

ImageCorrelationModel = for_catalogue(
    pathlib.Path(__file__).parent / "models.yaml",
    name="Image correlation (RICS/STICS/TICS/iMSD)",
    module=__name__,
)
IcsGaussian2DModel = ImageCorrelationModel

__all__ = ["ImageCorrelationModel", "IcsGaussian2DModel"]
