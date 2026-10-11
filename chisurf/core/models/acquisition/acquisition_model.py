"""A model with nothing to fit: its fit window shows an acquisition as it runs.

The acquisition plugin streams photons through its pipeline and registers the
result as a dataset (:class:`chisurf.plugins.core.acq.dataset.AcquisitionDataset`).
Opening a fit on it with this model gives the usual fit window; the five pages
named in ``acquisition.view.json`` (decay, correlation, MCS, macro-time trace)
read the dataset's latest pipeline snapshot. The model has no parameters; its
curve is the data's, so the decay page overlays nothing and the fit-level pages
stay inert.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.fitting
from chisurf.core.data import DataGroup
from chisurf.core.models.model import ModelCurve


def acquisition_dataset(fit):
    """Return the acquisition dataset behind *fit*, or ``None``.

    The dataset is the curve that carries a pipeline ``snapshot``; the fit's data
    may be that curve, a group holding it, or a fit group's selected member.

    Parameters
    ----------
    fit : Fit or FitGroup
        The fit a page shows.
    """
    seen = set()
    stack = [fit]
    while stack:
        item = stack.pop()
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        if hasattr(item, "pipeline_snapshot"):
            return item
        stack.append(getattr(item, "selected_fit", None))
        stack.append(getattr(item, "data", None))
        if isinstance(item, DataGroup):
            stack.extend(list(item))
    return None


class AcquisitionModel(ModelCurve):
    """Live acquisition display; no parameters, the curve follows the data."""

    name = "Acquisition"
    view_spec_file = "acquisition.view.json"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, *args, **kwargs) -> None:
        """Create the parameterless model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            Fit this model belongs to.
        """
        super().__init__(fit, *args, **kwargs)
        self.find_parameters()

    def _update_model(self, **kwargs) -> None:
        """Follow the data: the model curve is the data curve."""
        fit = getattr(self.fit, "selected_fit", self.fit)
        data = getattr(fit, "data", None)
        x = np.asarray(getattr(data, "x", np.zeros(0)), dtype=float)
        y = np.asarray(getattr(data, "y", np.zeros_like(x)), dtype=float)
        self.x = x
        self.y = y
