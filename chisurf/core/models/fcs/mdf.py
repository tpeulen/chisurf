"""Enderlein Gauss--Lorentz MDF FCS model (Qt-free, PRD-38/PRD-62 view-spec split).

Unlike the formula-string ``ParseFCSModel`` catalogue, this is a Python-computed
:class:`~chisurf.core.models.model.ModelCurve` that evaluates the diffusion
autocorrelation of the Enderlein molecule-detection function (MDF) by numerical
integration (see :mod:`chisurf.core.fluorescence.fcs.enderlein`). It yields an
accurate effective volume — hence an absolute concentration — without the 3-D
Gaussian approximation, and is the basis for two-focus / dual-focus calibration.

Parameters are grouped into :class:`~chisurf.core.fitting.parameter.FittingParameterGroup`
sub-objects (:class:`MdfPhysical`, :class:`MdfOptics`, :class:`MdfOutputs`) so
the editor renders them as compact tables (``mdf.view.json``); compute stays
here, the JSON is user-editable. :class:`MdfPhysical` and :class:`MdfOptics`
are also reused by the general composable FCS model
(:mod:`chisurf.core.models.fcs.general`) for its ``"mdf"`` diffusion mode.
"""

from __future__ import annotations

import math

import numpy as np

import chisurf as cs
from chisurf import typing
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.model import ModelCurve
from chisurf.core.fluorescence.fcs import enderlein
from chisurf.core.fluorescence.fcs.normalization import compute_cpm, resolve_total_mean_count_rate
from chisurf.core.models.fcs.relaxation import BunchingTerms

#: Avogadro constant for the concentration output (1/mol).
NA = 6.02214076e23

#: The equation variable the Enderlein MDF shape arrives on in the graph
#: route: a producer node writes it, so it is not a fitting parameter.
MDF_SHAPE_VARIABLE = "g_mdf"


class MdfPhysical(FittingParameterGroup):
    """Free physical parameters of the Enderlein Gauss-Lorentz MDF.

    ``w0`` is the excitation beam's lateral 1/e^2 waist; ``wem`` is the
    emission/collection-side Gauss-Lorentz waist (Enderlein's ``R0``, renamed
    to avoid colliding with the unrelated Foerster-radius ``R0`` in the
    parameter registry — see PRD-62). ``diam`` is the known inter-focus
    separation for two-focus (dual-focus) FCS; 0 means single-focus
    auto-correlation (the default). ``b`` is the correlation-curve baseline
    offset, defaulting to 1 to match the typical normalized-ACF convention
    (``G(tau) -> 1`` far from zero lag, e.g. the Kristine format) rather than a
    background-subtracted 0-baseline. ``bg`` is a background count rate (kHz,
    detector dark counts/scatter/afterpulsing) subtracted from the data file's
    total count rate before computing :attr:`MdfOutputs`'s brightness output —
    the Parse-FCS catalogue's ``Counts``/``BG`` convention
    (``models.yaml``'s "3D diffusion + background" family).
    """

    def __init__(self, name: str = "mdf_physical", **kwargs):
        """Initialize the free physical parameter group."""
        super().__init__(name=name, **kwargs)
        self._N = FittingParameter(
            value=1.0, name="N", lb=1e-6, ub=1e9, fixed=False, registry_id="fcs_mdf.N")
        self._D = FittingParameter(
            value=300.0, name="D", lb=1e-3, ub=1e5, fixed=False,
            label_text="D[µm²/s]", registry_id="fcs_mdf.D")
        self._w0 = FittingParameter(
            value=250.0, name="w0", lb=10.0, ub=5000.0, fixed=False,
            label_text="w<sub>0</sub>[nm]", registry_id="fcs_mdf.w0")
        self._wem = FittingParameter(
            value=250.0, name="wem", lb=10.0, ub=5000.0, fixed=False,
            label_text="w<sub>em</sub>[nm]", registry_id="fcs_mdf.wem")
        self._b = FittingParameter(
            value=1.0, name="b", lb=-10.0, ub=10.0, fixed=False, registry_id="fcs_mdf.b")
        self._diam = FittingParameter(
            value=0.0, name="diam", lb=0.0, ub=5000.0, fixed=True,
            label_text="d<sub>foci</sub>[nm]", registry_id="fcs_mdf.diam")
        self._bg = FittingParameter(
            value=0.0, name="bg", lb=0.0, ub=1e6, fixed=True,
            label_text="BG[kHz]", registry_id="fcs_mdf.bg")

    N = property(lambda s: float(s._N.value))
    D = property(lambda s: float(s._D.value))
    w0 = property(lambda s: float(s._w0.value))
    wem = property(lambda s: float(s._wem.value))
    b = property(lambda s: float(s._b.value))
    diam = property(lambda s: float(s._diam.value))
    bg = property(lambda s: float(s._bg.value))


class MdfOptics(FittingParameterGroup):
    """Fixed confocal optical parameters for the Enderlein MDF."""

    def __init__(self, name: str = "mdf_optics", **kwargs):
        """Initialize the fixed optical parameter group."""
        super().__init__(name=name, **kwargs)
        self._lam_ex = FittingParameter(
            value=485.0, name="lam_ex", lb=200.0, ub=1200.0, fixed=True,
            label_text="&lambda;<sub>ex</sub>[nm]", registry_id="fcs_mdf.lam_ex")
        self._lam_em = FittingParameter(
            value=520.0, name="lam_em", lb=200.0, ub=1200.0, fixed=True,
            label_text="&lambda;<sub>em</sub>[nm]", registry_id="fcs_mdf.lam_em")
        self._n = FittingParameter(
            value=1.33, name="n", lb=1.0, ub=2.0, fixed=True, registry_id="fcs_mdf.n")
        self._pinhole = FittingParameter(
            value=50.0, name="pinhole", lb=1.0, ub=1000.0, fixed=True,
            label_text="pinhole[µm]", registry_id="fcs_mdf.pinhole")
        self._mag = FittingParameter(
            value=60.0, name="mag", lb=1.0, ub=1000.0, fixed=True, registry_id="fcs_mdf.mag")

    lam_ex = property(lambda s: float(s._lam_ex.value))
    lam_em = property(lambda s: float(s._lam_em.value))
    n = property(lambda s: float(s._n.value))
    pinhole = property(lambda s: float(s._pinhole.value))
    mag = property(lambda s: float(s._mag.value))

    def as_optics(self) -> enderlein.Optics:
        """Build an :class:`~chisurf.core.fluorescence.fcs.enderlein.Optics` instance."""
        return enderlein.Optics(
            excitation_wavelength=self.lam_ex * 1e-3,   # nm -> µm
            emission_wavelength=self.lam_em * 1e-3,
            refractive_index=self.n,
            pinhole=self.pinhole,
            magnification=self.mag,
        )


class MdfOutputs(FittingParameterGroup):
    """Derived (read-only) outputs of the Enderlein MDF model."""

    def __init__(self, name: str = "mdf_outputs", **kwargs):
        """Initialize the derived-output parameter group (all NaN until fit)."""
        super().__init__(name=name, **kwargs)
        self._Veff = FittingParameter(
            value=float("nan"), name="Veff", fixed=True, is_output=True,
            label_text="V<sub>eff</sub>[fL]", registry_id="fcs_mdf.Veff")
        self._conc = FittingParameter(
            value=float("nan"), name="conc", fixed=True, is_output=True,
            label_text="c[nM]", registry_id="fcs_mdf.conc")
        self._tauD = FittingParameter(
            value=float("nan"), name="tauD", fixed=True, is_output=True,
            label_text="&tau;<sub>D</sub>[ms]", registry_id="fcs_mdf.tauD")
        self._brightness = FittingParameter(
            value=float("nan"), name="brightness", fixed=True, is_output=True,
            label_text="&epsilon;[kHz]", registry_id="fcs_mdf.brightness")


def compute_brightness(fit, N: float, bg: float = 0.0) -> typing.Optional[float]:
    """Background-corrected molecular brightness ``(CR_total - bg) / N``, in kHz.

    ``CR_total`` comes from the data file's ``mean_count_rate``(``_total``)
    metadata (e.g. the Kristine format's header); returns ``None`` when that
    metadata is absent, mirroring :func:`~chisurf.core.fluorescence.fcs.
    normalization.compute_cpm`. ``bg`` is a background count rate (kHz) to
    subtract first — see :class:`MdfPhysical`. Shared by :class:`MdfFCSModel`
    and the general composable FCS model's ``"mdf"``/``"gauss"``/
    ``"two_focus"`` modes so brightness is computed identically everywhere.
    """
    meta = getattr(getattr(fit, "data", None), "meta_data", {}) or {}
    mean_cr_total = resolve_total_mean_count_rate(meta)
    if mean_cr_total is None:
        return None
    return compute_cpm(mean_cr_total - bg, N)


def set_output_parameter(fit, param: FittingParameter, value: float) -> None:
    """Write a derived output parameter (value + keep fixed) through the API.

    Shared by :class:`MdfFCSModel` and the general composable FCS model
    (:mod:`chisurf.core.models.fcs.general`) so a derived output round-trips
    through the same path a user edit would.

    The write goes through :class:`~chisurf.core.api.ChiSurfAPI`, not through
    the GUI's fitting client: a model is compute, and reaching into
    ``chisurf.gui`` from ``chisurf.core.models`` breaks the split the whole
    layer is built on (and the headless paths, where no client exists). The
    facade forwards to the same ``parameter.set_value`` handler either way.
    """
    try:
        param.value = value
    except Exception:
        pass
    try:
        from chisurf.core.api import ChiSurfAPI

        api = ChiSurfAPI()
        fit_idx = getattr(fit, "fit_idx", None)
        kwargs = {} if fit_idx is None else {"fit_index": int(fit_idx)}
        api.set_parameter_value(parameter_name=str(param.name), value=float(value), **kwargs)
        api.set_parameter_fixed(parameter_name=str(param.name), fixed=True, **kwargs)
    except Exception:
        pass


class MdfFCSModel(ModelCurve):
    """Enderlein Gauss--Lorentz MDF diffusion FCS model.

    Fitting parameters
    ------------------
    physical.N, .D, .w0, .wem, .b, .diam, .bg : see :class:`MdfPhysical`.
    optics.lam_ex, .lam_em, .n, .pinhole, .mag : see :class:`MdfOptics`.
    bunching : zero or more extra exponential relaxation terms, see
        :class:`~chisurf.core.models.fcs.relaxation.BunchingTerms`.

    Output parameters
    -----------------
    outputs.Veff, .conc, .tauD, .brightness : see :class:`MdfOutputs`.

    The correlation lag ``data.x`` is taken in **milliseconds** (matching the
    other ChiSurf FCS models) and converted to seconds internally.
    """

    name = "FCS MDF (Gauss-Lorentz)"
    view_spec_file = "mdf.view.json"

    def __init__(self, fit: "cs.core.fitting.fit.Fit", **kwargs):
        """Initialize the physical/optics/bunching/outputs parameter groups."""
        super().__init__(fit, **kwargs)
        self.physical = MdfPhysical(name="mdf_physical", fit=fit)
        self.optics = MdfOptics(name="mdf_optics", fit=fit)
        self.bunching = BunchingTerms(name="mdf_bunching", fit=fit)
        self.outputs = MdfOutputs(name="mdf_outputs", fit=fit)
        self.find_parameters()

    def _update_model(self, **kwargs) -> None:
        """Evaluate the Enderlein-MDF diffusion autocorrelation into ``self.y``."""
        data = self.fit.data
        tau_ms = np.asarray(data.x, dtype=float).ravel()
        if tau_ms.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            return

        p = self.physical
        w0 = p.w0 * 1e-3   # nm -> µm
        wem = p.wem * 1e-3
        D = p.D            # µm²/s
        N = p.N
        b = p.b

        if not (math.isfinite(w0) and w0 > 0 and math.isfinite(wem) and wem > 0
                and math.isfinite(D) and D > 0 and math.isfinite(N) and N != 0):
            self.x = tau_ms
            self.y = np.full_like(tau_ms, float("nan"))
            return

        tau_s = tau_ms * 1e-3
        separation = p.diam * 1e-3   # nm -> µm
        optics = self.optics.as_optics()
        g = enderlein.g_diff(tau_s, w0, wem, D, optics=optics, normalize=True,
                              n_grid=121, span=30.0, separation=separation)
        g = self.bunching.apply(g, tau_ms)

        veff_um3 = enderlein.effective_volume(w0, wem, optics)
        conc_nM = (N / (veff_um3 * 1e-15 * NA)) * 1e9 if veff_um3 > 0 else float("nan")
        tauD_ms = (w0 * w0) / (4.0 * D) * 1e3
        set_output_parameter(self.fit, self.outputs._Veff, veff_um3)
        set_output_parameter(self.fit, self.outputs._conc, conc_nM)
        set_output_parameter(self.fit, self.outputs._tauD, tauD_ms)
        brightness = compute_brightness(self.fit, N, p.bg)
        if brightness is not None:
            set_output_parameter(self.fit, self.outputs._brightness, brightness)

        meta = getattr(getattr(self.fit, "data", None), "meta_data", {}) or {}
        mean_cr_total = resolve_total_mean_count_rate(meta)
        if mean_cr_total is not None and mean_cr_total > 0 and p.bg > 0:
            bg_factor = max(0.0, (mean_cr_total - p.bg) / mean_cr_total) ** 2
        else:
            bg_factor = 1.0

        self.x = tau_ms
        self.y = b + (bg_factor / N) * g

    # --- the graph route: the kernel is a node, the rest is one equation
    #
    # The Enderlein shape is a numerical kernel, so unlike a parse model this
    # equation does not contain it: `g_mdf` is a *variable* an
    # `IMP.bff.FCSMdfCurve` producer node writes, and the equation only
    # multiplies the terms that genuinely are formulas onto it (the bunching
    # factors, the amplitude, the baseline). `w0`, `wem`, `D` and `diam` are
    # that node's ports and are therefore absent from
    # :attr:`_parameters_equation`; the optics are a fixed calibration folded
    # into the node, so freeing one refuses the graph (unclaimable port).

    def _count_rate_constant(self):
        """The dataset's total mean count rate, or ``None`` when absent."""
        meta = getattr(getattr(self.fit, "data", None), "meta_data", {}) or {}
        cr = resolve_total_mean_count_rate(meta)
        return float(cr) if cr is not None and cr > 0 else None

    @property
    def func(self) -> str:
        """The compound equation over the node's shape, in bff's spelling."""
        factors = [MDF_SHAPE_VARIABLE]
        factors += [
            "(1.0 - ba%d + ba%d*exp(-x/bt%d))" % (i, i, i)
            for i in range(1, len(self.bunching) + 1)]
        cr = self._count_rate_constant()
        if cr is not None:
            amplitude = "max(0.0, (%r - bg)/%r)**2/N" % (cr, cr)
        else:
            amplitude = "1.0/N"
        return "b + (%s)*%s" % (amplitude, "*".join(factors))

    @property
    def _expression(self):
        """Non-``None`` marks the model as graph-compilable (see ``func``)."""
        return self.func

    @property
    def _parameters_equation(self):
        """The equation's own variables -- not the producer node's ports."""
        out = [self.physical._N, self.physical._b, self.physical._bg]
        out += self.bunching._ba + self.bunching._bt
        return out

    def equation_html(self) -> str:
        """Render the currently active compound fitting equation as HTML.

        Reflects the number of active bunching terms; bound to an
        ``info``/``source`` section in ``mdf.view.json`` so it stays live as
        terms are added/removed (see :meth:`chisurf.core.models.fcs.
        relaxation.BunchingTerms.equation_html`).
        """
        g = "MDF<sub>Enderlein</sub>(&tau;; w<sub>0</sub>, w<sub>em</sub>, D)"
        if self.physical.diam > 0:
            g += " &middot; exp(&minus;d<sub>foci</sub>&sup2;/(w<sub>0</sub>&sup2;+4D&tau;))"
        bunch = self.bunching.equation_html()
        if bunch:
            g += " &middot; " + bunch
        return f"<b>G(&tau;) = b + (1/N)&middot;</b>{g}"
