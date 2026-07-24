"""General composable FCS model (PRD-62).

Pick a diffusion type — ``"gauss"`` (a classic single-focus 3-D-Gaussian PSF,
the default), ``"mdf"`` (the Enderlein Gauss-Lorentz MDF, :mod:`.mdf`), or
``"two_focus"`` (the classic Dertinger two-focus/dual-focus technique, a
directly selectable preset rather than a parameter buried in a table) — and
add an arbitrary number of bunching and anticorrelation (photon-antibunching)
relaxation terms (:mod:`.relaxation`). Only the panel for the active diffusion
mode stays expanded — the ``diffusion_mode`` choice section re-folds its
siblings live via ``rebuild_on_change``/``collapsed_when``'s ``not_equals``.
Two-focus cross-correlation (a known inter-focus separation ``diam`` > 0, the
Dertinger convention already used by the "Two-focus 3D diffusion" entry in the
FCS parse-model catalogue, ``chisurf/core/models/fcs/models.yaml``) is
available in every mode; the ``"two_focus"`` preset just starts with it
unfixed and non-zero.

This supersedes the diffusion x bunching/anticorrelation combinatorial subset
of that catalogue (``"3D Gauss, N bunching"``, ``"... + antibunching"``,
multi-diffusion+bunching combos) for new work; the catalogue itself is
untouched and remains the path for cases this model does not cover (flow,
scanning FCS, FRET-FCCS, afterpulsing/bleaching correction terms).

Normalization: ``G(0) = b + 1/N`` at zero two-focus separation, for both
diffusion modes — matching :mod:`.mdf`; ``b`` defaults to 1 (the typical
normalized-ACF baseline), not 0. This differs from the legacy parse
catalogue's ``1/(N*sqrt(8))`` convention (a PAM-specific artifact of how those
older models define ``N``); porting a catalogue ``N`` here requires dividing
it by ``sqrt(8)``.
"""

from __future__ import annotations

import math

import numpy as np

import chisurf as cs
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.model import ModelCurve
from chisurf.core.fluorescence.fcs import enderlein
from chisurf.core.models.fcs.mdf import (
    MdfPhysical, MdfOptics, MdfOutputs, NA, compute_brightness, set_output_parameter,
)
from chisurf.core.models.fcs.relaxation import AnticorrTerms, BunchingTerms


class GaussDiffusion(FittingParameterGroup):
    """Classic 3-D-Gaussian-PSF diffusion term (absolute D), optional two-focus.

    ``G_diff(tau) = (1 + 4*D*tau/w_r^2)^-1 * (1 + 4*D*tau/w_z^2)^-1/2 * exp(-diam^2/(w_r^2+4*D*tau))``,
    the Dertinger two-focus form (PAM ``FCS_2Focus_D``); ``diam = 0`` reduces
    it to the single-focus 3-D-Gaussian diffusion term. ``b`` (baseline
    offset) defaults to 1 to match the typical normalized-ACF convention
    (``G(tau) -> 1`` far from zero lag). ``s = w_z/w_r`` (the classic
    structure/aspect-ratio parameter) and the background-corrected molecular
    brightness are derived, read-only outputs (see :meth:`GeneralFCSModel.
    _gauss_shape`) rather than independent fit parameters — this group still
    fits absolute ``w_r``/``w_z`` directly (see the module docstring), ``s``
    is reported for comparison with the legacy dimensionless parametrization.
    ``bg`` is a background count rate (kHz) subtracted before computing
    brightness, matching :class:`~chisurf.core.models.fcs.mdf.MdfPhysical`.
    """

    def __init__(self, name: str = "gauss_diffusion", **kwargs):
        """Initialize the classic 3-D-Gaussian diffusion parameter group."""
        super().__init__(name=name, **kwargs)
        self._N = FittingParameter(
            value=1.0, name="N", lb=1e-6, ub=1e9, fixed=False, registry_id="fcs_gauss.N")
        self._D = FittingParameter(
            value=300.0, name="D", lb=1e-3, ub=1e5, fixed=False,
            label_text="D[µm²/s]", registry_id="fcs_gauss.D")
        self._w_r = FittingParameter(
            value=250.0, name="w_r", lb=10.0, ub=5000.0, fixed=False,
            label_text="w<sub>r</sub>[nm]", registry_id="fcs_gauss.w_r")
        self._w_z = FittingParameter(
            value=1000.0, name="w_z", lb=10.0, ub=20000.0, fixed=False,
            label_text="w<sub>z</sub>[nm]", registry_id="fcs_gauss.w_z")
        self._b = FittingParameter(
            value=1.0, name="b", lb=-10.0, ub=10.0, fixed=False, registry_id="fcs_gauss.b")
        self._diam = FittingParameter(
            value=0.0, name="diam", lb=0.0, ub=5000.0, fixed=True,
            label_text="d<sub>foci</sub>[nm]", registry_id="fcs_gauss.diam")
        self._bg = FittingParameter(
            value=0.0, name="bg", lb=0.0, ub=1e6, fixed=True,
            label_text="BG[kHz]", registry_id="fcs_gauss.bg")
        self._s = FittingParameter(
            value=float("nan"), name="s", fixed=True, is_output=True,
            label_text="s", registry_id="fcs_gauss.s")
        self._brightness = FittingParameter(
            value=float("nan"), name="brightness", fixed=True, is_output=True,
            label_text="&epsiv;[kHz]", registry_id="fcs_gauss.brightness")

    N = property(lambda s: float(s._N.value))
    D = property(lambda s: float(s._D.value))
    w_r = property(lambda s: float(s._w_r.value))
    w_z = property(lambda s: float(s._w_z.value))
    b = property(lambda s: float(s._b.value))
    diam = property(lambda s: float(s._diam.value))
    bg = property(lambda s: float(s._bg.value))

    def g_diff(self, tau_ms: np.ndarray) -> np.ndarray:
        """3-D-Gaussian diffusion shape (``g(0) = 1`` at ``diam = 0``)."""
        D = self.D
        w_r = self.w_r * 1e-3   # nm -> µm
        w_z = self.w_z * 1e-3
        diam = self.diam * 1e-3
        tau_s = np.asarray(tau_ms, dtype=float) * 1e-3
        lateral = 1.0 / (1.0 + 4.0 * D * tau_s / w_r ** 2)
        axial = 1.0 / np.sqrt(1.0 + 4.0 * D * tau_s / w_z ** 2)
        g = lateral * axial
        if diam > 0:
            g = g * np.exp(-diam ** 2 / (w_r ** 2 + 4.0 * D * tau_s))
        return g


class GeneralFCSModel(ModelCurve):
    """General composable FCS model: choose a diffusion type + relaxation terms.

    Attributes
    ----------
    diffusion_mode : {"mdf", "gauss", "two_focus"}
        Active diffusion type, ``"gauss"`` by default (the common case; MDF's
        accurate absolute Veff/concentration needs optics parameters most
        users do not have calibrated). ``"mdf"`` uses :attr:`mdf_physical`/
        :attr:`mdf_optics` (Enderlein Gauss-Lorentz MDF); ``"gauss"`` uses
        :attr:`gauss` (classic single-focus 3-D Gaussian); ``"two_focus"``
        uses :attr:`two_focus` — the same 3-D-Gaussian term as ``"gauss"``
        (:class:`GaussDiffusion` already supports a two-focus cross-term via
        ``diam``), but as its own preset instance with ``diam`` unfixed and
        defaulted non-zero, so the classic Dertinger two-focus technique is a
        directly selectable, discoverable option rather than a parameter
        buried inside the single-focus table. ``diam`` is also available
        (fixed at 0 by default) in ``"mdf"``/``"gauss"`` for users who want
        two-focus combined with those modes without switching presets.
    bunching, anticorr : see :mod:`chisurf.core.models.fcs.relaxation`.
    """

    name = "FCS (general: diffusion + bunching/anticorr)"
    view_spec_file = "general.view.json"

    _DIFFUSION_MODES = ("mdf", "gauss", "two_focus")

    def __init__(self, fit: "cs.core.fitting.fit.Fit", **kwargs):
        """Initialize every diffusion-mode parameter group plus relaxation terms."""
        super().__init__(fit, **kwargs)
        self._diffusion_mode = "gauss"
        self.mdf_physical = MdfPhysical(name="mdf_physical", fit=fit)
        self.mdf_optics = MdfOptics(name="mdf_optics", fit=fit)
        self.mdf_outputs = MdfOutputs(name="mdf_outputs", fit=fit)
        self.gauss = GaussDiffusion(name="gauss_diffusion", fit=fit)
        self.two_focus = GaussDiffusion(name="two_focus_diffusion", fit=fit)
        self.two_focus._diam.value = 400.0
        self.two_focus._diam.fixed = True   # a known, fixed geometric constant
        self.bunching = BunchingTerms(name="bunching", fit=fit)
        self.anticorr = AnticorrTerms(name="anticorr", fit=fit)
        self.find_parameters()

    @property
    def diffusion_mode(self) -> str:
        """Active diffusion type: ``"mdf"``, ``"gauss"``, or ``"two_focus"``."""
        return self._diffusion_mode

    @diffusion_mode.setter
    def diffusion_mode(self, v: str) -> None:
        """Set the active diffusion type; must be one of :attr:`_DIFFUSION_MODES`."""
        v = str(v).lower()
        if v not in self._DIFFUSION_MODES:
            raise ValueError(f"diffusion_mode must be one of {self._DIFFUSION_MODES}, got {v!r}")
        self._diffusion_mode = v

    def _mdf_shape(self, tau_ms: np.ndarray):
        """Return ``(g, N, b)`` for the MDF diffusion mode, or ``None`` if invalid."""
        p = self.mdf_physical
        w0 = p.w0 * 1e-3   # nm -> µm
        wem = p.wem * 1e-3
        D = p.D
        N = p.N
        if not (math.isfinite(w0) and w0 > 0 and math.isfinite(wem) and wem > 0
                and math.isfinite(D) and D > 0 and math.isfinite(N) and N != 0):
            return None
        tau_s = np.asarray(tau_ms, dtype=float) * 1e-3
        separation = p.diam * 1e-3
        optics = self.mdf_optics.as_optics()
        g = enderlein.g_diff(tau_s, w0, wem, D, optics=optics, normalize=True,
                              n_grid=121, span=30.0, separation=separation)

        veff_um3 = enderlein.effective_volume(w0, wem, optics)
        conc_nM = (N / (veff_um3 * 1e-15 * NA)) * 1e9 if veff_um3 > 0 else float("nan")
        tauD_ms = (w0 * w0) / (4.0 * D) * 1e3
        set_output_parameter(self.fit, self.mdf_outputs._Veff, veff_um3)
        set_output_parameter(self.fit, self.mdf_outputs._conc, conc_nM)
        set_output_parameter(self.fit, self.mdf_outputs._tauD, tauD_ms)
        brightness = compute_brightness(self.fit, N, p.bg)
        if brightness is not None:
            set_output_parameter(self.fit, self.mdf_outputs._brightness, brightness)
        return g, N, p.b

    def _gauss_shape(self, gp: GaussDiffusion, tau_ms: np.ndarray):
        """Return ``(g, N, b)`` for a Gaussian diffusion group, or ``None`` if invalid."""
        if not (math.isfinite(gp.D) and gp.D > 0 and math.isfinite(gp.N) and gp.N != 0):
            return None
        s = gp.w_z / gp.w_r if gp.w_r > 0 else float("nan")
        set_output_parameter(self.fit, gp._s, s)
        brightness = compute_brightness(self.fit, gp.N, gp.bg)
        if brightness is not None:
            set_output_parameter(self.fit, gp._brightness, brightness)
        return gp.g_diff(tau_ms), gp.N, gp.b

    def update_model(self, **kwargs) -> None:
        """Evaluate the selected diffusion term, apply relaxation terms, into ``self.y``."""
        data = self.fit.data
        tau_ms = np.asarray(data.x, dtype=float).ravel()
        if tau_ms.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            return

        if self.diffusion_mode == "mdf":
            shape = self._mdf_shape(tau_ms)
        elif self.diffusion_mode == "two_focus":
            shape = self._gauss_shape(self.two_focus, tau_ms)
        else:
            shape = self._gauss_shape(self.gauss, tau_ms)
        if shape is None:
            self.x = tau_ms
            self.y = np.full_like(tau_ms, float("nan"))
            return
        g, N, b = shape

        g = self.bunching.apply(g, tau_ms)
        g = self.anticorr.apply(g, tau_ms)

        self.x = tau_ms
        self.y = b + g / N

    def equation_html(self) -> str:
        """Render the currently active compound fitting equation as HTML.

        Reflects the active ``diffusion_mode`` and the number of active
        bunching/anticorrelation terms; bound to an ``info``/``source``
        section in ``general.view.json`` so it stays live as the mode is
        switched or terms are added/removed.
        """
        if self.diffusion_mode == "mdf":
            g = "MDF<sub>Enderlein</sub>(&tau;; w<sub>0</sub>, w<sub>em</sub>, D)"
            diam = self.mdf_physical.diam
            w_label = "w<sub>0</sub>"
        else:
            gp = self.two_focus if self.diffusion_mode == "two_focus" else self.gauss
            g = (
                "(1+4D&tau;/w<sub>r</sub>&sup2;)<sup>&minus;1</sup>"
                " &middot; (1+4D&tau;/w<sub>z</sub>&sup2;)<sup>&minus;1/2</sup>"
            )
            diam = gp.diam
            w_label = "w<sub>r</sub>"
        if diam > 0:
            g += f" &middot; exp(&minus;d<sub>foci</sub>&sup2;/({w_label}&sup2;+4D&tau;))"
        for term_html in (self.bunching.equation_html(), self.anticorr.equation_html()):
            if term_html:
                g += " &middot; " + term_html
        return f"<b>G(&tau;) = b + (1/N)&middot;</b>{g}"
