"""Image-correlation models (RICS, STICS, TICS, iMSD), as a view on BFF.

One catalogue, ``models.yaml`` beside this module, holds the carpet equations
over the coordinates the ICS reader records with the data: the pixel lag
``xi``, the line lag ``psi`` and the lag time ``tau``. BFF builds each equation
as a competing structure, so the 3D and membrane geometries are compared on
BIC like any other model family; which lag times a fit constrains is set by the
carpet (one frame lag is RICS, several are STICS/TICS), and releasing ``alpha``
is iMSD.

ChiSurf lists the two models it always listed, each with its own editor:
``ImageCorrelationModel`` (transport, imaging, blinking, immobile fraction,
flow) and ``IcsGaussian2DModel`` (the anisotropic Gaussian that sizes
structures). The scan timing is the reader's -- it turned the carpet lags into
the lag times the equations read -- and the imaging panel shows it.
"""

from __future__ import annotations

import pathlib

from chisurf.core.models.description import for_catalogue

_HERE = pathlib.Path(__file__).parent

#: The editor's symbols and units, as the classic ICS models labelled them.
LABELS = {
    "N": "N",
    "D": "D[µm²/s]",
    "alpha": "&alpha;",
    "offset": "G<sub>0</sub>",
    "pxl_size": "a[nm]",
    "w_r": "w<sub>r</sub>[µm]",
    "w_z": "w<sub>z</sub>[µm]",
    "tauT": "&tau;<sub>T</sub>[ms]",
    "aT": "a<sub>T</sub>",
    "N_imm": "N<sub>imm</sub>",
    "w_imm": "w<sub>imm</sub>[µm]",
    "sx": "s<sub>x</sub>[nm]",
    "sy": "s<sub>y</sub>[nm]",
    "v_x": "v<sub>x</sub>[µm/s]",
    "v_y": "v<sub>y</sub>[µm/s]",
    "A0": "A<sub>0</sub>",
    "sigma1": "&sigma;<sub>1</sub>[nm]",
    "sigma2": "&sigma;<sub>2</sub>[nm]",
    "angle": "&theta;[rad]",
    "x_off": "x<sub>0</sub>[nm]",
    "y_off": "y<sub>0</sub>[nm]",
}

#: The panel order of the classic editor's groups, by parameter.
_ORDER = {
    "transport": ("N", "D", "alpha", "offset"),
    "imaging": ("pxl_size", "w_r", "w_z"),
    "blinking": ("tauT", "aT"),
    "immobile": ("N_imm", "w_imm", "sx", "sy"),
    "flow": ("v_x", "v_y"),
    "structure": ("A0", "sigma1", "sigma2", "angle", "x_off", "y_off", "offset"),
}


class _Panel:
    """One classic ICS panel: the catalogue group's parameters in their old order."""

    def __init__(self, view, key: str):
        self._view = view
        self.key = key
        self.name = key
        self._timing_rows = None

    def _group_parameters(self) -> list:
        group = next((g for g in self._view._groups.values() if g.key == self.key), None)
        if group is None:
            return []
        by_id = {p.canonical_id: p for p in group.visible_parameters()}
        return [by_id[i] for i in _ORDER.get(self.key, ()) if i in by_id]

    def _timing(self) -> list:
        """The reader's scan timing, which made the carpet's lag times: shown, not fitted."""
        from chisurf.core.experiments.ics import IcsTiming
        from chisurf.core.models.tcspc.classic_editor import ScalarRow

        if self._timing_rows is None:

            def read(attribute):
                meta = (
                    getattr(getattr(self._view.fit, "data", None), "meta_data", None) or {}
                ).get("ics", {})
                return getattr(IcsTiming.from_meta(meta or {}), attribute)

            self._timing_rows = [
                ScalarRow(name, lambda a=attribute: read(a), lambda _v: None, label_text=label)
                for name, attribute, label in (
                    ("pxl_dur", "pixel_duration_us", "t<sub>pix</sub>[µs]"),
                    ("line_dur", "line_duration_ms", "t<sub>line</sub>[ms]"),
                    ("frame_dur", "frame_duration_ms", "t<sub>frame</sub>[ms]"),
                )
            ]
        return list(self._timing_rows)

    @property
    def parameters_all(self) -> list:
        rows = self._group_parameters()
        return self._timing() + rows if self.key == "imaging" else rows

    def visible_parameters(self) -> list:
        return self.parameters_all


class IcsEditor:
    """The groups the classic ICS editors address, over the catalogue's parameters."""

    def _panel(self, key: str) -> _Panel:
        panels = self.__dict__.setdefault("_ics_panels", {})
        if key not in panels:
            panels[key] = _Panel(self, key)
        return panels[key]

    transport = property(lambda self: self._panel("transport"))
    imaging = property(lambda self: self._panel("imaging"))
    blinking = property(lambda self: self._panel("blinking"))
    immobile = property(lambda self: self._panel("immobile"))
    flow = property(lambda self: self._panel("flow"))
    # "gaussian", as the classic editor named it: ``structure`` is the model's topology.
    gaussian = property(lambda self: self._panel("structure"))


ImageCorrelationModel = for_catalogue(
    _HERE / "models.yaml",
    name="Image correlation (RICS/STICS/TICS/iMSD)",
    module=__name__,
    view=_HERE / "image_correlation.view.json",
    entries=("Image correlation (3D)", "Image correlation (2D membrane)"),
    labels=LABELS,
    mixins=(IcsEditor,),
)

IcsGaussian2DModel = for_catalogue(
    _HERE / "models.yaml",
    name="ICS 2D Gaussian (2 sigma + angle)",
    module=__name__,
    view=_HERE / "ics_gaussian2d.view.json",
    entries=("2D Gaussian (2 sigma + angle)",),
    labels={**LABELS, "offset": "I<sub>0</sub>"},
    mixins=(IcsEditor,),
)

__all__ = ["ImageCorrelationModel", "IcsGaussian2DModel"]
