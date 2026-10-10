"""Build project payloads through the real v5 session writer.

The archiver indexes the validated scientific snapshot that
:func:`chisurf.core.project.capture_session` produces, so fixtures that
exercise it must come from that writer rather than from hand-rolled dicts.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project import capture_session


class TwoParameterModel(ModelCurve):
    """Small real model: ``y = amplitude * x + offset``."""

    def __init__(self, fit, **kwargs):
        super().__init__(fit, **kwargs)
        self.amplitude = FittingParameter(name="amplitude", value=1.0)
        self.offset = FittingParameter(name="offset", value=0.0)
        self.find_parameters()

    def _update_model(self, **kwargs):
        self.x = self.fit.data.x
        self.y = self.amplitude.value * self.x + self.offset.value


def make_curve(
    uid: str, offset: float = 0.0, n: int = 8, filename: str = "", **meta
) -> DataCurve:
    """Return a real curve with errors and a stable UID."""
    x = np.arange(float(n))
    curve = DataCurve(
        x=x,
        y=x + 10.0 + offset,
        ex=np.full_like(x, 0.1),
        ey=np.ones_like(x),
        name=f"curve-{uid}",
        unique_identifier=uid,
    )
    curve.filename = filename
    curve.meta_data.update(meta)
    return curve


def make_curves() -> tuple[DataCurve, DataCurve]:
    """Two distinct curves."""
    return make_curve("ds_001"), make_curve("ds_002", 5.0)


def make_global_group(first: DataCurve, second: DataCurve, uid: str = "fit_001") -> FitGroup:
    """Global fit over two curves with a cross-member parameter link."""
    group = FitGroup(DataCurveGroup([first, second], name="measurements"), model_class=TwoParameterModel)
    group.unique_identifier = uid
    source, target = group.grouped_fits
    source.model.amplitude.value = 5.0
    source.model.amplitude.bounds = (0.0, 10.0)
    source.model.amplitude.bounds_on = True
    source.model.offset.fixed = True
    target.model.amplitude.link = source.model.amplitude
    return group


def make_single_fit(curve: DataCurve, uid: str = "fit_002") -> Fit:
    """Independent single fit."""
    fit = Fit(model_class=TwoParameterModel, data=curve)
    fit.unique_identifier = uid
    return fit


def v5_payload(datasets=(), fits=(), *, name: str = "test_project", ui_state=None) -> dict:
    """Return ``capture_session(...).to_dict()`` for explicit runtime objects."""
    return capture_session(
        list(datasets), list(fits), name=name, ui_state=ui_state or {}
    ).to_dict()
