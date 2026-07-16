from __future__ import annotations

import chisurf.core.models.parse as parse_module


class ParsePCFModel(parse_module.ParseModel):
    """Parse model for pair-correlation-function (PCF) distribution fits.

    Extends the generic :class:`~chisurf.core.models.parse.ParseModel` for the
    PCF experiment type; the catalogue of distribution equations lives in the
    sibling ``models.yaml``.
    """

    def __init__(self, fit, **kwargs):
        """Initialize the PCF parse model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            Fit object this model belongs to.
        **kwargs
            Additional keyword arguments forwarded to the base class.
        """
        super().__init__(fit, **kwargs)

    def update_model(self, **kwargs):
        """Update the PCF distribution model."""
        super().update_model(**kwargs)
