"""Qt-free image-correlation fitting models (PRD-38 model/view-spec split).

One model fits the whole spatiotemporal correlation carpet
:math:`G(\\xi, \\psi, \\Delta)`. RICS, STICS, TICS and iMSD are not separate
models here -- they are what you get from :class:`ImageCorrelationModel`
depending on how many frame lags the data carries and which terms are released
from their neutral values:

* a carpet with one frame lag is a RICS fit;
* a carpet with several frame lags is simultaneously a STICS and a TICS fit;
* releasing ``alpha`` turns it into an anomalous/iMSD fit, since the model's
  Gaussian width is :math:`w_r^2 + \\mathrm{MSD}(\\tau)` by construction.

Compute lives in :mod:`chisurf.core.models.ics.models`; these classes wrap it as
pure ``ModelCurve`` subclasses with :class:`FittingParameterGroup` parameter
groups and a declarative ``*.view.json`` editor.

Note on parameter registry ids: these keep the historical ``rics.*`` prefix.
They are stable vocabulary keys tied to the metadata dictionaries, not module
paths, so they are deliberately not renamed along with the module.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.experiments.ics.data import IcsTiming, lag_time
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.ics.models import ics_gaussian_2d, image_correlation


def _ics_meta(fit_group) -> tuple[dict, object]:
    """Return ``(ics_meta_dict, data)`` for a fit group or plain fit.

    Parameters
    ----------
    fit_group : object
        A ``FitGroup`` (with ``selected_fit``) or a plain ``Fit``.

    Returns
    -------
    tuple
        The ``meta_data['ics']`` dictionary (empty when absent) and the data
        object it came from.
    """
    fit = getattr(fit_group, "selected_fit", fit_group)
    data = getattr(fit, "data", None)
    meta = getattr(data, "meta_data", {}) or {}
    return (meta.get("ics", {}) or {}), data


def _lag_grids(meta: dict):
    """Return the ``(pixel_shift, line_shift, frame_lags)`` grids from metadata.

    Parameters
    ----------
    meta : dict
        The ICS metadata dictionary.

    Returns
    -------
    tuple of numpy.ndarray or None
        The two spatial lag grids of shape ``(ny, nx)`` and the frame lags of
        shape ``(n_lags,)``, or ``(None, None, None)`` when the metadata does
        not describe a usable carpet.
    """
    try:
        xi = np.asarray(meta.get("pixel_shift"), dtype=float)
        psi = np.asarray(meta.get("line_shift"), dtype=float)
    except Exception:
        return None, None, None
    if xi.ndim != 2 or psi.ndim != 2 or xi.shape != psi.shape:
        return None, None, None
    lags = meta.get("frame_lags")
    if lags is None:
        frame_lags = np.zeros(1, dtype=float)
    else:
        frame_lags = np.atleast_1d(np.asarray(lags, dtype=float))
    return xi, psi, frame_lags


def _data_carpet(meta: dict) -> np.ndarray | None:
    """Return the measured carpet ``(n_lags, ny, nx)`` from metadata.

    Parameters
    ----------
    meta : dict
        The ICS metadata dictionary.

    Returns
    -------
    numpy.ndarray or None
        The correlation carpet, promoted to three dimensions, or ``None``.
    """
    arr = meta.get("correlation")
    if arr is None:
        arr = meta.get("ics_mean")
    if arr is None:
        return None
    out = np.asarray(arr, dtype=float)
    if out.ndim == 2:
        out = out[None, ...]
    return out if out.ndim == 3 else None


# --- image accessors (Qt-free; referenced from view.json) ------------------
def get_ics_n_lags(fit_group) -> int:
    """Return the number of frame lags in the data carpet.

    Used by the 2D plot to size its lag slider.

    Parameters
    ----------
    fit_group : object
        The fit or fit group being plotted.

    Returns
    -------
    int
        Number of frame lags, or ``0`` when there is no carpet.
    """
    meta, _ = _ics_meta(fit_group)
    carpet = _data_carpet(meta)
    return 0 if carpet is None else int(carpet.shape[0])


def get_ics_data_image(fit_group, lag_index: int = 0):
    """Return one measured carpet slice as ``(image, x, y)``.

    Parameters
    ----------
    fit_group : object
        The fit or fit group being plotted.
    lag_index : int
        Index along the frame-lag axis. ``0`` is the RICS map.

    Returns
    -------
    tuple
        ``(image, x_axis, y_axis)``, or ``(None, None, None)``.
    """
    meta, _ = _ics_meta(fit_group)
    carpet = _data_carpet(meta)
    if carpet is None:
        return None, None, None
    img = carpet[int(np.clip(lag_index, 0, carpet.shape[0] - 1))]
    return img, np.arange(img.shape[1], dtype=float), np.arange(img.shape[0], dtype=float)


def get_ics_model_image(fit_group, lag_index: int = 0):
    """Return one model carpet slice as ``(image, x, y)``.

    Parameters
    ----------
    fit_group : object
        The fit or fit group being plotted.
    lag_index : int
        Index along the frame-lag axis.

    Returns
    -------
    tuple
        ``(image, x_axis, y_axis)``, or ``(None, None, None)``.
    """
    fit = getattr(fit_group, "selected_fit", fit_group)
    carpet = getattr(getattr(fit, "model", None), "model_carpet", None)
    if carpet is None:
        return None, None, None
    carpet = np.asarray(carpet, dtype=float)
    if carpet.ndim == 2:
        carpet = carpet[None, ...]
    if carpet.ndim != 3:
        return None, None, None
    img = carpet[int(np.clip(lag_index, 0, carpet.shape[0] - 1))]
    return img, np.arange(img.shape[1], dtype=float), np.arange(img.shape[0], dtype=float)


def get_ics_residual_image(fit_group, weighted: bool = True, lag_index: int = 0):
    """Return one residual carpet slice as ``(image, x, y)``.

    Parameters
    ----------
    fit_group : object
        The fit or fit group being plotted.
    weighted : bool
        Divide the residual by the Poisson error of the data.
    lag_index : int
        Index along the frame-lag axis.

    Returns
    -------
    tuple
        ``(image, x_axis, y_axis)``, or ``(None, None, None)``.
    """
    data_img, x, y = get_ics_data_image(fit_group, lag_index=lag_index)
    model_img, _, _ = get_ics_model_image(fit_group, lag_index=lag_index)
    if data_img is None or model_img is None:
        return None, None, None
    n0 = min(data_img.shape[0], model_img.shape[0])
    n1 = min(data_img.shape[1], model_img.shape[1])
    d, m = data_img[:n0, :n1], model_img[:n0, :n1]
    img = (d - m) / np.sqrt(np.maximum(d, 1.0)) if weighted else d - m
    return img, np.arange(n1, dtype=float), np.arange(n0, dtype=float)


# --- parameter groups ------------------------------------------------------
class IcsImaging(FittingParameterGroup):
    """Fixed acquisition parameters (scan timing, PSF, pixel size).

    These set the lag-time identity :math:`\\tau = |\\xi\\tau_p + \\psi\\tau_l +
    \\Delta\\tau_f|`, i.e. they decide what "time" each part of the carpet means.
    """

    def __init__(self, name: str = "ics_imaging", **kwargs):
        """Initialize the imaging/acquisition parameter group."""
        super().__init__(name=name, **kwargs)
        self._pixel_duration = FittingParameter(
            value=11.1, name="pxl_dur", lb=0.01, ub=1e3, bounds_on=False, fixed=True,
            label_text="t<sub>pix</sub>[µs]", registry_id="rics.pxl_dur")
        self._line_duration = FittingParameter(
            value=3.33, name="line_dur", lb=0.001, ub=1e4, bounds_on=False, fixed=True,
            label_text="t<sub>line</sub>[ms]", registry_id="rics.line_dur")
        self._frame_duration = FittingParameter(
            value=0.0, name="frame_dur", lb=0.0, ub=1e6, bounds_on=False, fixed=True,
            label_text="t<sub>frame</sub>[ms]", registry_id="rics.frame_dur")
        self._pixel_size = FittingParameter(
            value=40.0, name="pxl_size", lb=1.0, ub=1e4, bounds_on=False, fixed=True,
            label_text="a[nm]", registry_id="rics.pxl_size")
        self._w_r = FittingParameter(
            value=0.2, name="w_r", lb=1e-3, ub=1e2, bounds_on=False, fixed=True,
            label_text="w<sub>r</sub>[µm]", registry_id="rics.w_r")
        self._w_z = FittingParameter(
            value=1.0, name="w_z", lb=1e-3, ub=1e3, bounds_on=False, fixed=True,
            label_text="w<sub>z</sub>[µm]", registry_id="rics.w_z")

    pixel_duration = property(lambda s: float(s._pixel_duration.value))
    line_duration = property(lambda s: float(s._line_duration.value))
    frame_duration = property(lambda s: float(s._frame_duration.value))
    pixel_size = property(lambda s: float(s._pixel_size.value))
    w_r = property(lambda s: float(s._w_r.value))
    w_z = property(lambda s: float(s._w_z.value))


class IcsTransport(FittingParameterGroup):
    """Transport parameters: particle number, transport coefficient, anomaly.

    ``alpha`` is fixed at 1 (normal diffusion) by default; releasing it turns
    the fit into the anomalous/iMSD case, because the model's Gaussian width is
    :math:`w_r^2 + 4D\\tau^{\\alpha}`.
    """

    def __init__(self, name: str = "ics_transport", **kwargs):
        """Initialize the transport parameter group."""
        super().__init__(name=name, **kwargs)
        self._n = FittingParameter(
            value=1.0, name="N", lb=1e-6, ub=1e9, bounds_on=True, fixed=False,
            label_text="N", registry_id="rics.n")
        self._D = FittingParameter(
            value=2.0, name="D", lb=1e-6, ub=1e3, bounds_on=True, fixed=False,
            label_text="D[µm²/s]", registry_id="rics.D")
        self._alpha = FittingParameter(
            value=1.0, name="alpha", lb=0.05, ub=2.0, bounds_on=True, fixed=True,
            label_text="&alpha;", registry_id="ics.alpha")
        self._offset = FittingParameter(
            value=0.0, name="offset", lb=-1e3, ub=1e3, bounds_on=True, fixed=False,
            label_text="G<sub>0</sub>", registry_id="rics.offset")

    n = property(lambda s: float(s._n.value))
    D = property(lambda s: float(s._D.value))
    alpha = property(lambda s: float(s._alpha.value))
    offset = property(lambda s: float(s._offset.value))


class IcsBlinking(FittingParameterGroup):
    """Triplet/blinking parameters. Amplitude zero switches the term off."""

    def __init__(self, name: str = "ics_blinking", **kwargs):
        """Initialize the blinking parameter group."""
        super().__init__(name=name, **kwargs)
        self._tauT = FittingParameter(
            value=0.002, name="tauT", lb=1e-6, ub=1.0, bounds_on=True, fixed=True,
            label_text="&tau;<sub>T</sub>[ms]", registry_id="rics.tauT")
        self._aT = FittingParameter(
            value=0.0, name="aT", lb=0.0, ub=0.99, bounds_on=True, fixed=True,
            label_text="a<sub>T</sub>", registry_id="rics.aT")

    tau_triplet = property(lambda s: float(s._tauT.value))
    a_triplet = property(lambda s: float(s._aT.value))


class IcsImmobile(FittingParameterGroup):
    """Immobile component with its own width and a lateral (ccRICS) shift.

    ``N_imm = 0`` removes the static term entirely.
    """

    def __init__(self, name: str = "ics_immobile", **kwargs):
        """Initialize the immobile-component parameter group."""
        super().__init__(name=name, **kwargs)
        self._n_imm = FittingParameter(
            value=0.0, name="N_imm", lb=0.0, ub=1e9, bounds_on=True, fixed=True,
            label_text="N<sub>imm</sub>", registry_id="rics.n_imm")
        self._w_imm = FittingParameter(
            value=0.2, name="w_imm", lb=1e-3, ub=1e2, bounds_on=True, fixed=True,
            label_text="w<sub>imm</sub>[µm]", registry_id="rics.w_imm")
        self._sx = FittingParameter(
            value=0.0, name="sx", lb=-1e4, ub=1e4, bounds_on=True, fixed=True,
            label_text="s<sub>x</sub>[nm]", registry_id="rics.sx")
        self._sy = FittingParameter(
            value=0.0, name="sy", lb=-1e4, ub=1e4, bounds_on=True, fixed=True,
            label_text="s<sub>y</sub>[nm]", registry_id="rics.sy")

    n_immobile = property(lambda s: float(s._n_imm.value))
    w_immobile = property(lambda s: float(s._w_imm.value))
    shift_x = property(lambda s: float(s._sx.value))
    shift_y = property(lambda s: float(s._sy.value))


class IcsFlow(FittingParameterGroup):
    """Uniform-flow velocities along the fast/slow scan axes."""

    def __init__(self, name: str = "ics_flow", **kwargs):
        """Initialize the flow parameter group."""
        super().__init__(name=name, **kwargs)
        self._vx = FittingParameter(
            value=0.0, name="v_x", lb=-1e4, ub=1e4, bounds_on=True, fixed=True,
            label_text="v<sub>x</sub>[µm/s]", registry_id="rics.v_x")
        self._vy = FittingParameter(
            value=0.0, name="v_y", lb=-1e4, ub=1e4, bounds_on=True, fixed=True,
            label_text="v<sub>y</sub>[µm/s]", registry_id="rics.v_y")

    v_x = property(lambda s: float(s._vx.value))
    v_y = property(lambda s: float(s._vy.value))


class IcsGaussian2D(FittingParameterGroup):
    """Anisotropic 2D-Gaussian structure parameters (two widths + angle)."""

    def __init__(self, name: str = "ics_gaussian2d", **kwargs):
        """Initialize the anisotropic-Gaussian parameter group."""
        super().__init__(name=name, **kwargs)
        self._a0 = FittingParameter(
            value=1.0, name="A0", lb=0.0, ub=1e9, bounds_on=True, fixed=False,
            label_text="A<sub>0</sub>", registry_id="ics.a0")
        self._s1 = FittingParameter(
            value=200.0, name="sigma1", lb=1.0, ub=1e5, bounds_on=True, fixed=False,
            label_text="&sigma;<sub>1</sub>[nm]", registry_id="ics.sigma1")
        self._s2 = FittingParameter(
            value=200.0, name="sigma2", lb=1.0, ub=1e5, bounds_on=True, fixed=False,
            label_text="&sigma;<sub>2</sub>[nm]", registry_id="ics.sigma2")
        self._angle = FittingParameter(
            value=0.0, name="angle", lb=0.0, ub=6.3, bounds_on=True, fixed=False,
            label_text="&theta;[rad]", registry_id="ics.angle")
        self._xo = FittingParameter(
            value=0.0, name="x_off", lb=-1e5, ub=1e5, bounds_on=True, fixed=True,
            label_text="x<sub>0</sub>[nm]", registry_id="ics.x_off")
        self._yo = FittingParameter(
            value=0.0, name="y_off", lb=-1e5, ub=1e5, bounds_on=True, fixed=True,
            label_text="y<sub>0</sub>[nm]", registry_id="ics.y_off")
        self._offset = FittingParameter(
            value=0.0, name="offset", lb=-1e3, ub=1e3, bounds_on=True, fixed=False,
            label_text="I<sub>0</sub>", registry_id="ics.offset")

    amplitude = property(lambda s: float(s._a0.value))
    sigma_1 = property(lambda s: float(s._s1.value))
    sigma_2 = property(lambda s: float(s._s2.value))
    angle = property(lambda s: float(s._angle.value))
    x_offset = property(lambda s: float(s._xo.value))
    y_offset = property(lambda s: float(s._yo.value))
    offset = property(lambda s: float(s._offset.value))


# --- base model ------------------------------------------------------------
class _IcsModelBase(ModelCurve):
    """Shared plumbing: read the carpet lag grids, compute, store 3D and 1D."""

    def __init__(self, fit: cs.core.fitting.fit.Fit, **kwargs) -> None:
        """Initialize the common imaging group and seed timing from metadata."""
        super().__init__(fit, **kwargs)
        self.imaging = IcsImaging(name="ics_imaging", fit=fit)
        #: Model evaluated on the full carpet, shape ``(n_lags, ny, nx)``.
        self.model_carpet: np.ndarray | None = None
        self._seed_timing_from_meta()

    def _seed_timing_from_meta(self) -> None:
        """Initialize the fixed scan timing and pixel size from ICS metadata."""
        meta, _ = _ics_meta(self.fit)
        if not meta:
            return
        timing = IcsTiming.from_meta(meta)
        self.imaging._pixel_duration.value = timing.pixel_duration_us
        self.imaging._line_duration.value = timing.line_duration_ms
        self.imaging._pixel_size.value = timing.pixel_size_nm
        if timing.frame_duration_ms > 0.0:
            self.imaging._frame_duration.value = timing.frame_duration_ms

    def _compute(self, xi: np.ndarray, psi: np.ndarray, delta: np.ndarray) -> np.ndarray:
        """Return the model carpet on the lag grids. Implemented by subclasses.

        Parameters
        ----------
        xi, psi : numpy.ndarray
            Spatial lag grids of shape ``(n_lags, ny, nx)``.
        delta : numpy.ndarray
            Frame-lag grid of shape ``(n_lags, 1, 1)``.

        Returns
        -------
        numpy.ndarray
            Model carpet of shape ``(n_lags, ny, nx)``.
        """
        raise NotImplementedError

    def _carpet_grids(self):
        """Return the broadcast ``(xi3, psi3, delta3)`` lag grids, or ``None``.

        Reads the carpet metadata, refreshes the fixed timing from it, and
        broadcasts the spatial lag grids over the frame-lag axis so the model
        can be evaluated on the whole carpet in one call.

        Returns
        -------
        tuple or None
            ``(xi3, psi3, delta3)`` with the spatial grids of shape
            ``(n_lags, ny, nx)`` and the frame-lag grid of shape
            ``(n_lags, 1, 1)``, or ``None`` when the data carry no carpet.
        """
        meta, _ = _ics_meta(self.fit)
        xi, psi, frame_lags = _lag_grids(meta)
        if xi is None:
            return None
        self._seed_timing_from_meta()
        xi3 = np.broadcast_to(xi[None, ...], (frame_lags.size,) + xi.shape)
        psi3 = np.broadcast_to(psi[None, ...], (frame_lags.size,) + psi.shape)
        delta3 = frame_lags[:, None, None]
        return xi3, psi3, delta3

    def update_model(self, **kwargs) -> None:
        """Evaluate the model over the whole carpet and store 3D and 1D forms."""
        _, data = _ics_meta(self.fit)
        grids = self._carpet_grids()

        if grids is None:
            self.model_carpet = None
            self.y = np.zeros_like(getattr(data, "y", np.zeros(0)), dtype=float)
            return

        xi3, psi3, delta3 = grids
        carpet = np.asarray(self._compute(xi3, psi3, delta3), dtype=float)
        carpet = np.broadcast_to(carpet, xi3.shape) if carpet.shape != xi3.shape else carpet
        self.model_carpet = carpet
        y_model = carpet.ravel()

        x_data = getattr(data, "x", None)
        if x_data is not None and getattr(x_data, "size", 0) == y_model.size:
            self.x = np.asarray(x_data, dtype=float)
        else:
            self.x = np.arange(y_model.size, dtype=float)
        self.y = y_model


# --- concrete models -------------------------------------------------------
class ImageCorrelationModel(_IcsModelBase):
    """The image-correlation model: RICS, STICS, TICS and iMSD in one fit.

    Every optional term starts at its neutral value and is fixed, so the model
    opens as plain one-component diffusion. Release ``alpha`` for anomalous
    transport (iMSD), ``a_T`` for blinking, ``N_imm`` for an immobile fraction,
    ``v_x``/``v_y`` for flow, or ``s_x``/``s_y`` for a cross-correlation shift.
    Which lag times the fit actually sees is set by the data: a carpet with one
    frame lag constrains µs-to-ms motion (RICS), a carpet with many frame lags
    additionally constrains seconds (STICS/TICS).
    """

    name = "Image correlation (RICS/STICS/TICS/iMSD)"
    view_spec_file = "image_correlation.view.json"

    def __init__(self, fit, **kwargs):
        """Initialize the transport, blinking, immobile and flow groups."""
        super().__init__(fit, **kwargs)
        self.transport = IcsTransport(name="ics_transport", fit=fit)
        self.blinking = IcsBlinking(name="ics_blinking", fit=fit)
        self.immobile = IcsImmobile(name="ics_immobile", fit=fit)
        self.flow = IcsFlow(name="ics_flow", fit=fit)
        #: Membrane/2D geometry toggle (drop the axial term).
        self.two_d = False

    def _compute(self, xi, psi, delta):
        """Compute the correlation carpet from the current parameters."""
        t, im, b, imm, fl = (
            self.transport, self.imaging, self.blinking, self.immobile, self.flow
        )
        return image_correlation(
            xi, psi, delta,
            n=t.n, diffusion_coefficient=t.D, alpha=t.alpha, offset=t.offset,
            pixel_duration=im.pixel_duration, line_duration=im.line_duration,
            frame_duration=im.frame_duration, pixel_size=im.pixel_size,
            w_r=im.w_r, w_z=im.w_z,
            tau_triplet=b.tau_triplet, a_triplet=b.a_triplet,
            n_immobile=imm.n_immobile, w_immobile=imm.w_immobile,
            v_x=fl.v_x, v_y=fl.v_y,
            shift_x=imm.shift_x, shift_y=imm.shift_y,
            two_d=bool(self.two_d),
        )

    # --- the graph route: the same model as one compiled expression --------
    #
    # `image_correlation` transcribed into the expression the fitting graph
    # compiles (`Expression -> ChiSquared`), over three precomputed axes
    # (`graph_axes`). Every optional term is written unconditionally because
    # each is *exactly* neutral at its default -- `a_T = 0` makes the triplet
    # factor exactly 1, and at `N_imm = 0` the two amplitude spellings are
    # algebraically identical -- so only the geometry toggle changes the
    # string. The scan timing is folded into the tau axis and must stay
    # fixed; a freed timing parameter has no port and refuses the graph,
    # which is the correct fallback.

    @property
    def func(self) -> str:
        """The carpet equation over the ``xi``/``psi``/``tau`` axes."""
        n_m = "max(abs(N), 1e-12)"
        n_i = "abs(N_imm)"
        wr2 = "max(abs(w_r), 0.001)**2"
        msd = "(4.0*abs(D)*tau**alpha)"
        dx = "(pxl_size*xi*0.001 - v_x*tau - sx*0.001)"
        dy = "(pxl_size*psi*0.001 - v_y*tau - sy*0.001)"
        decay = f"(1.0/(1.0 + {msd}/{wr2}))"
        if not self.two_d:
            decay += f"/sqrt(1.0 + {msd}/max(abs(w_z), 0.001)**2)"
        triplet = ("(1.0 + (aT/max(1.0 - aT, 1e-12))"
                   "*exp(-tau/(max(abs(tauT), 1e-9)*0.001)))")
        spatial = f"exp(-({dx}**2 + {dy}**2)/({wr2} + {msd}))"
        mobile = f"({triplet}*{decay}*{spatial})"
        immobile = ("exp(-((pxl_size*xi*0.001 - sx*0.001)**2"
                    " + (pxl_size*psi*0.001 - sy*0.001)**2)"
                    "/max(abs(w_imm), 0.001)**2)")
        gamma = "0.5" if self.two_d else "0.35355339059327373"
        return (f"offset + {gamma}/max({n_m} + {n_i}, 1e-12)**2"
                f"*({n_m}*{mobile} + {n_i}*{immobile})")

    @property
    def _expression(self):
        """Non-``None`` marks the model as graph-compilable (see ``func``)."""
        return self.func

    @property
    def _parameters_equation(self):
        """The parameters behind the equation's variables, ports at build."""
        return [
            self.transport._n, self.transport._D, self.transport._alpha,
            self.transport._offset,
            self.imaging._pixel_size, self.imaging._w_r, self.imaging._w_z,
            self.blinking._tauT, self.blinking._aT,
            self.immobile._n_imm, self.immobile._w_imm,
            self.immobile._sx, self.immobile._sy,
            self.flow._vx, self.flow._vy,
        ]

    def graph_axes(self):
        """Return the flattened ``xi``/``psi``/``tau`` axes, or ``None``.

        The same grids `update_model` evaluates on, in the same ravel order,
        with the lag time computed from the *fixed* scan timing exactly as
        :func:`~chisurf.core.models.ics.models.image_correlation` does.

        Returns
        -------
        dict or None
            ``{"xi": ..., "psi": ..., "tau": ...}`` as flat float arrays, or
            ``None`` when the data carry no carpet metadata.
        """
        grids = self._carpet_grids()
        if grids is None:
            return None
        xi3, psi3, delta3 = grids
        im = self.imaging
        tau = lag_time(
            xi3, psi3, delta3,
            pixel_duration_us=im.pixel_duration,
            line_duration_ms=im.line_duration,
            frame_duration_ms=im.frame_duration,
        )
        tau = np.broadcast_to(np.asarray(tau, dtype=float), xi3.shape)
        return {
            "xi": np.ascontiguousarray(xi3, dtype=np.float64).ravel(),
            "psi": np.ascontiguousarray(psi3, dtype=np.float64).ravel(),
            "tau": np.ascontiguousarray(tau, dtype=np.float64).ravel(),
        }


class IcsGaussian2DModel(_IcsModelBase):
    """Anisotropic 2D-Gaussian spatial-correlation model (structure sizing).

    The one member of the family that ignores the time axis: it sizes
    structures from the shape of the spatial correlation alone.
    """

    name = "ICS 2D Gaussian (2 sigma + angle)"
    view_spec_file = "ics_gaussian2d.view.json"

    def __init__(self, fit, **kwargs):
        """Initialize with the anisotropic-Gaussian parameter group."""
        super().__init__(fit, **kwargs)
        self.gaussian = IcsGaussian2D(name="ics_gaussian2d", fit=fit)

    def _compute(self, xi, psi, delta):
        """Compute the anisotropic 2D-Gaussian surface (frame lag ignored)."""
        gp, im = self.gaussian, self.imaging
        return ics_gaussian_2d(
            xi, psi, amplitude=gp.amplitude, pixel_size=im.pixel_size,
            sigma_1=gp.sigma_1, sigma_2=gp.sigma_2, angle=gp.angle,
            x_offset=gp.x_offset, y_offset=gp.y_offset, offset=gp.offset)

    # --- the graph route (see ImageCorrelationModel for the pattern) --------

    @property
    def func(self) -> str:
        """`ics_gaussian_2d` transcribed for the graph, over ``xi``/``psi``."""
        xr = "(xi*pxl_size - x_off)"
        yr = "(psi*pxl_size - y_off)"
        u = f"(({xr}*cos(angle) + {yr}*sin(angle))/max(abs(sigma1), 1.0))"
        v = f"((-{xr}*sin(angle) + {yr}*cos(angle))/max(abs(sigma2), 1.0))"
        return f"offset + abs(A0)*exp(-{u}**2 - {v}**2)"

    @property
    def _expression(self):
        """Non-``None`` marks the model as graph-compilable (see ``func``)."""
        return self.func

    @property
    def _parameters_equation(self):
        """The parameters behind the equation's variables, ports at build."""
        gp = self.gaussian
        return [gp._a0, gp._s1, gp._s2, gp._angle, gp._xo, gp._yo,
                gp._offset, self.imaging._pixel_size]

    def graph_axes(self):
        """Return the flattened ``xi``/``psi`` lag axes, or ``None``.

        Returns
        -------
        dict or None
            ``{"xi": ..., "psi": ...}`` as flat float arrays in the carpet's
            ravel order, or ``None`` when the data carry no carpet metadata.
        """
        grids = self._carpet_grids()
        if grids is None:
            return None
        xi3, psi3, _ = grids
        return {
            "xi": np.ascontiguousarray(xi3, dtype=np.float64).ravel(),
            "psi": np.ascontiguousarray(psi3, dtype=np.float64).ravel(),
        }
