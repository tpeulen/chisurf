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

This model is purely operational (analytical diffusion + relaxation terms).
The photokinetic *saturation* path — arbitrary N-state rate schemes and the
numerical, power-dependent autocorrelation — lives in :mod:`.kinetics`
(:class:`FCSKineticsModel`), together with the rate-matrix parameter groups
it needs.
"""

from __future__ import annotations

import math

import numpy as np

import chisurf as cs
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.fcs import enderlein
from chisurf.core.models.fcs.mdf import (
    NA,
    MdfOptics,
    MdfOutputs,
    MdfPhysical,
    compute_brightness,
    set_output_parameter,
)
from chisurf.core.models.fcs.relaxation import AnticorrTerms, BunchingTerms
from chisurf.core.models.model import ModelCurve

#: The equation variable the Enderlein MDF shape arrives on in the graph
#: route. It is written by a producer node, so it is deliberately not a
#: fitting parameter; the objective builder binds it to that node's port.
_MDF_SHAPE_VARIABLE = "g_mdf"


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
            value=1.0, name="N", lb=1e-6, ub=1e9, bounds_on=True, fixed=False, registry_id="fcs_gauss.N",
            description='Average number of fluorescent particles in the observation volume.'
        )
        self._D = FittingParameter(
            value=300.0,
            name="D",
            lb=1e-3,
            ub=1e5,
            bounds_on=True,
            fixed=False,
            label_text="D[µm²/s]",
            registry_id="fcs_gauss.D",
            description='Translational diffusion coefficient of the fluorophore (µm²/s).'
        )
        self._w_r = FittingParameter(
            value=250.0,
            name="w_r",
            lb=10.0,
            ub=5000.0,
            bounds_on=True,
            fixed=False,
            label_text="w<sub>r</sub>[nm]",
            registry_id="fcs_gauss.w_r",
            description='Radial waist (1/e²) of the detection PSF (nm).'
        )
        self._w_z = FittingParameter(
            value=1000.0,
            name="w_z",
            lb=10.0,
            ub=20000.0,
            bounds_on=True,
            fixed=False,
            label_text="w<sub>z</sub>[nm]",
            registry_id="fcs_gauss.w_z",
            description='Axial waist (1/e²) of the detection PSF (nm).'
        )
        self._b = FittingParameter(
            value=1.0, name="b", lb=-10.0, ub=10.0, fixed=False, registry_id="fcs_gauss.b",
            description='Additive baseline/offset of the correlation function.'
        )
        self._diam = FittingParameter(
            value=0.0,
            name="diam",
            lb=0.0,
            ub=5000.0,
            fixed=True,
            label_text="d<sub>foci</sub>[nm]",
            registry_id="fcs_gauss.diam",
            description='Lateral distance between the two foci in a dual-focus FCS setup (nm).'
        )
        self._bg = FittingParameter(
            value=0.0,
            name="bg",
            lb=0.0,
            ub=1e6,
            fixed=True,
            label_text="BG[kHz]",
            registry_id="fcs_gauss.bg",
            description='Background count rate (kHz).'
        )
        self._s = FittingParameter(
            value=float("nan"),
            name="s",
            fixed=True,
            is_output=True,
            label_text="s",
            registry_id="fcs_gauss.s",
            description='Output: structure parameter s = z0/w0 (axial-to-radial extent of the detection volume).'
        )
        self._brightness = FittingParameter(
            value=float("nan"),
            name="brightness",
            fixed=True,
            is_output=True,
            label_text="&epsilon;[kHz]",
            registry_id="fcs_gauss.brightness",
            description='Output: molecular brightness (counts per molecule per second, kHz).'
        )

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
        w_r = self.w_r * 1e-3  # nm -> µm
        w_z = self.w_z * 1e-3
        diam = self.diam * 1e-3
        tau_s = np.asarray(tau_ms, dtype=float) * 1e-3
        lateral = 1.0 / (1.0 + 4.0 * D * tau_s / w_r**2)
        axial = 1.0 / np.sqrt(1.0 + 4.0 * D * tau_s / w_z**2)
        g = lateral * axial
        if diam > 0:
            g = g * np.exp(-(diam**2) / (w_r**2 + 4.0 * D * tau_s))
        return g


class DiffusionSpecies(GaussDiffusion):
    """Several 3-D-Gaussian diffusion components sharing one focus.

    ``G_diff(tau) = sum_i x_i * (1 + 4 D_i tau/w_r^2)^-1 (1 + 4 D_i tau/w_z^2)^-1/2``
    with the amplitudes ``x_i`` normalised to one.

    Diffusion terms *add*; bunching terms multiply. Everything else in this
    module is the multiplying kind, so a curve needing two transit times could
    not be expressed at all -- which is exactly what an optically saturated
    measurement needs. Flattening the emission profile turns its autocorrelation
    into a broader mixture of decay rates than one Gaussian component can
    produce, and the established analysis is a global triplet term (a bunching
    term here) times *two* diffusion times (Widengren & Rigler, Bioimaging 4
    (1996) 149). Two components is therefore the default.

    The components share ``w_r``/``w_z``: they are one molecule in one distorted
    focus, so what differs between them is the transit time, not the optics. The
    inherited single ``D`` is unused -- ``D_1`` replaces it.
    """

    def __init__(self, name: str = "species_diffusion", n_species: int = 2, **kwargs):
        """Initialize with ``n_species`` diffusion components."""
        super().__init__(name=name, **kwargs)
        self._species: list = []
        self._rebuild_species(max(1, int(n_species)))

    def _rebuild_species(self, n_species: int) -> None:
        """Resize the component list, keeping the values that survive."""
        old = {p.name: (p.value, p.fixed) for p in self._species}
        for key in [k for k in self.__dict__ if k.startswith(("_x_", "_D_"))]:
            delattr(self, key)
        self._species = []
        for i in range(1, n_species + 1):
            for prefix, default, label, bounds in (
                ("x", 1.0 / n_species, f"x<sub>{i}</sub>", (0.0, 1.0)),
                ("D", 300.0, f"D<sub>{i}</sub>[µm²/s]", (1e-3, 1e5)),
            ):
                pname = f"{prefix}_{i}"
                value, fixed = old.get(pname, (default, False))
                parameter = FittingParameter(
                    value=float(value), name=pname, lb=bounds[0], ub=bounds[1],
                    bounds_on=True, fixed=bool(fixed), label_text=label,
                    registry_id=f"fcs_species.{pname}",
                )
                setattr(self, f"_{pname}", parameter)
                self._species.append(parameter)
        self._n_species = n_species
        self._parameters = None
        self.find_parameters()

    @property
    def n_species(self) -> int:
        """Number of diffusion components."""
        return getattr(self, "_n_species", 1)

    def __len__(self) -> int:
        """Number of diffusion components.

        A parameter group counts its *parameters*, but ``append`` and ``pop``
        here add and remove a component, and anything that treats this as a
        list of components -- the agent's ``set_components``, for one -- reads
        the length to decide how many to add. Counting parameters would make it
        ask for two components and be told there are already ten.
        """
        return self.n_species

    def append(self) -> None:
        """Add a diffusion component."""
        self._rebuild_species(self.n_species + 1)

    def pop(self) -> None:
        """Remove the last diffusion component, never going below one."""
        if self.n_species > 1:
            self._rebuild_species(self.n_species - 1)

    @property
    def fractions(self) -> np.ndarray:
        """Component amplitudes, normalised to sum to one."""
        raw = np.array(
            [max(0.0, float(getattr(self, f"_x_{i}").value)) for i in range(1, self.n_species + 1)]
        )
        total = raw.sum()
        return raw / total if total > 0 else np.full(self.n_species, 1.0 / self.n_species)

    @property
    def diffusion_coefficients(self) -> np.ndarray:
        """Component diffusion coefficients (um^2/s)."""
        return np.array(
            [float(getattr(self, f"_D_{i}").value) for i in range(1, self.n_species + 1)]
        )

    def find_parameters(self):
        """Expose the optics and the per-component parameters, not the unused D."""
        self._parameters = [
            self._N, self._w_r, self._w_z, self._b, self._diam, self._bg, *self._species
        ]
        return self._parameters

    @property
    def parameters(self):
        """Return the parameter list, discovering it on first access."""
        if getattr(self, "_parameters", None) is None:
            self.find_parameters()
        return self._parameters

    def g_diff(self, tau_ms: np.ndarray) -> np.ndarray:
        """Amplitude-weighted sum of the components' diffusion shapes."""
        tau_s = np.asarray(tau_ms, dtype=float) * 1e-3
        w_r = self.w_r * 1e-3
        w_z = self.w_z * 1e-3
        diam = self.diam * 1e-3
        out = np.zeros_like(tau_s, dtype=float)
        for fraction, D in zip(self.fractions, self.diffusion_coefficients):
            lateral = 1.0 / (1.0 + 4.0 * D * tau_s / w_r**2)
            axial = 1.0 / np.sqrt(1.0 + 4.0 * D * tau_s / w_z**2)
            component = lateral * axial
            if diam > 0:
                component = component * np.exp(-(diam**2) / (w_r**2 + 4.0 * D * tau_s))
            out += fraction * component
        return out


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

    _DIFFUSION_MODES = ("mdf", "gauss", "species", "two_focus")

    def __init__(self, fit: cs.core.fitting.fit.Fit, **kwargs):
        """Initialize every diffusion-mode parameter group plus relaxation terms."""
        super().__init__(fit, **kwargs)
        self._diffusion_mode = "gauss"
        self.mdf_physical = MdfPhysical(name="mdf_physical", fit=fit)
        self.mdf_optics = MdfOptics(name="mdf_optics", fit=fit)
        self.mdf_outputs = MdfOutputs(name="mdf_outputs", fit=fit)
        self.gauss = GaussDiffusion(name="gauss_diffusion", fit=fit)
        self.two_focus = GaussDiffusion(name="two_focus_diffusion", fit=fit)
        self.species = DiffusionSpecies(name="species_diffusion", fit=fit)
        self.two_focus._diam.value = 400.0
        self.two_focus._diam.fixed = True  # a known, fixed geometric constant
        self.bunching = BunchingTerms(name="bunching", fit=fit)
        self.anticorr = AnticorrTerms(name="anticorr", fit=fit)
        #: Re-entrancy guard: writing a derived output parameter
        #: (:func:`set_output_parameter`) round-trips through the API, which
        #: calls ``update_model`` again; without this guard that cycle recursed
        #: ~200 deep on every update.
        self._updating_model = False
        self.find_parameters()

    @property
    def diffusion_mode(self) -> str:
        """Active diffusion type: ``"mdf"``, ``"gauss"``, ``"species"`` or ``"two_focus"``."""
        return self._diffusion_mode

    @diffusion_mode.setter
    def diffusion_mode(self, v: str) -> None:
        """Set the active diffusion type; must be one of :attr:`_DIFFUSION_MODES`."""
        v = str(v).lower()
        if v not in self._DIFFUSION_MODES:
            raise ValueError(f"diffusion_mode must be one of {self._DIFFUSION_MODES}, got {v!r}")
        self._diffusion_mode = v
        self.update()

    def _inactive_diffusion_groups(self) -> list:
        """Return the diffusion parameter groups the active mode does not use."""
        mdf = [self.mdf_physical, self.mdf_optics, self.mdf_outputs]
        others = {"mdf": [self.gauss, self.two_focus, self.species],
                  "two_focus": mdf + [self.gauss, self.species],
                  "species": mdf + [self.gauss, self.two_focus]}
        return others.get(self.diffusion_mode, mdf + [self.two_focus, self.species])

    @property
    def parameters_all(self):
        """Return the parameters of the *active* diffusion mode only.

        All three diffusion presets are instantiated so the user can switch
        between them, but :meth:`update_model` computes with exactly one. If
        the inactive ones stay in the parameter list, the optimiser varies
        numbers the model never reads — the fit becomes rank-deficient, and
        ``parameters_all_dict`` (which is keyed by name) can hand back the
        *inactive* ``N`` or ``D``, still sitting at its default, as if it were
        the fitted value.

        Returns
        -------
        list of FittingParameter
            Every parameter except those belonging to an inactive diffusion
            preset.
        """
        excluded: set[int] = set()
        for group in self._inactive_diffusion_groups():
            for parameter in getattr(group, "_parameters", None) or []:
                excluded.add(id(parameter))
        return [p for p in super().parameters_all if id(p) not in excluded]

    def _mdf_shape(self, tau_ms: np.ndarray):
        """Return ``(g, N, b)`` for the MDF diffusion mode, or ``None`` if invalid."""
        p = self.mdf_physical
        w0 = p.w0 * 1e-3  # nm -> µm
        wem = p.wem * 1e-3
        D = p.D
        N = p.N
        if not (
            math.isfinite(w0)
            and w0 > 0
            and math.isfinite(wem)
            and wem > 0
            and math.isfinite(D)
            and D > 0
            and math.isfinite(N)
            and N != 0
        ):
            return None
        tau_s = np.asarray(tau_ms, dtype=float) * 1e-3
        separation = p.diam * 1e-3
        optics = self.mdf_optics.as_optics()
        g = enderlein.g_diff(
            tau_s,
            w0,
            wem,
            D,
            optics=optics,
            normalize=True,
            n_grid=121,
            span=30.0,
            separation=separation,
        )

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

    def _update_model(self, **kwargs) -> None:
        """Evaluate the selected diffusion term, apply relaxation terms, into ``self.y``."""
        # Writing a derived output parameter (s, brightness) round-trips through
        # the API, which calls update_model again. Skip that nested recompute —
        # the enclosing call is computing with the same parameters and has
        # already written the output value (set_output_parameter sets it first).
        if self._updating_model:
            return
        self._updating_model = True
        try:
            self._update_model_inner(**kwargs)
        finally:
            self._updating_model = False

    def _update_model_inner(self, **kwargs) -> None:
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
        elif self.diffusion_mode == "species":
            shape = self._gauss_shape(self.species, tau_ms)
        else:
            shape = self._gauss_shape(self.gauss, tau_ms)
        if shape is None:
            self.x = tau_ms
            self.y = np.full_like(tau_ms, float("nan"))
            return
        g, N, b = shape

        g = self.bunching.apply(g, tau_ms)
        g = self.anticorr.apply(g, tau_ms)

        meta = getattr(getattr(self.fit, "data", None), "meta_data", {}) or {}
        from chisurf.core.fluorescence.fcs.normalization import resolve_total_mean_count_rate
        mean_cr_total = resolve_total_mean_count_rate(meta)
        diff_obj = getattr(self, self.diffusion_mode, None)
        bg_val = float(getattr(diff_obj, "bg", 0.0)) if diff_obj is not None else 0.0
        if mean_cr_total is not None and mean_cr_total > 0 and bg_val > 0:
            bg_factor = max(0.0, (mean_cr_total - bg_val) / mean_cr_total) ** 2
        else:
            bg_factor = 1.0

        self.x = tau_ms
        self.y = b + (bg_factor / N) * g

    # --- the graph route: the active composition as one compiled expression
    #
    # The model's curve genuinely *is* an equation (`equation_html` has
    # always written it), so the graph route regenerates the same equation
    # in the engine's spelling: the active diffusion mode, the current
    # bunching/anticorrelation term count and the dataset's count-rate
    # constant are all *structural* -- any change regenerates the string,
    # and `_graph_cache_key` carries it, so a stale graph cannot serve a
    # reconfigured model. Every optional factor is exactly neutral at its
    # default (`diam = 0` and `bg = 0` both make their factor exactly 1),
    # so nothing branches inside one configuration. The `"mdf"` mode is a
    # numerical kernel (`enderlein.g_diff`, bff's FcsMdf), not a formula, so
    # its shape arrives on a variable an `FcsMdfCurve` producer node writes
    # rather than as algebra; everything downstream of the shape is the same
    # equation as in the closed-form modes.

    def _count_rate_constant(self):
        """The dataset's total mean count rate, or ``None`` when absent."""
        meta = getattr(getattr(self.fit, "data", None), "meta_data", {}) or {}
        from chisurf.core.fluorescence.fcs.normalization import (
            resolve_total_mean_count_rate)
        cr = resolve_total_mean_count_rate(meta)
        return float(cr) if cr is not None and cr > 0 else None

    def _diffusion_expression(self):
        """The active diffusion shape over ``x`` (tau, ms), or ``None``.

        Every mode but ``"mdf"`` is a closed form and returns its algebra.
        ``"mdf"`` returns the *variable* the Enderlein shape arrives on: it
        is a numerical kernel, so a producer node computes it and the
        equation only multiplies the terms that are formulas onto it. The
        variable is bound to that node's output port by the objective
        builder, which is why it is not among :attr:`_parameters_equation`.
        """
        mode = self.diffusion_mode
        if mode == "mdf":
            return _MDF_SHAPE_VARIABLE
        lat = "1.0/(1.0 + 4.0*{D}*(x*0.001)/(w_r*0.001)**2)"
        axi = "1.0/sqrt(1.0 + 4.0*{D}*(x*0.001)/(w_z*0.001)**2)"
        two = "exp(-(diam*0.001)**2/((w_r*0.001)**2 + 4.0*{D}*(x*0.001)))"
        component = f"{lat}*{axi}*{two}"
        if mode == "species":
            n = self.species.n_species
            parts = [
                "max(x_%d, 0.0)*(%s)" % (i, component.format(D="D_%d" % i))
                for i in range(1, n + 1)]
            total = " + ".join("max(x_%d, 0.0)" % i for i in range(1, n + 1))
            return "(%s)/max(%s, 1e-30)" % (" + ".join(parts), total)
        return "(%s)" % component.format(D="D")

    @property
    def func(self) -> str | None:
        """The full compound equation for the graph, or ``None``.

        Identical in every diffusion mode: the shape, times each relaxation
        factor, scaled and offset. Only the *shape* differs -- algebra in the
        closed-form modes, the producer variable in ``"mdf"``.
        """
        g = self._diffusion_expression()
        if g is None:
            return None
        factors = [g]
        factors += [
            "(1.0 - ba%d + ba%d*exp(-x/bt%d))" % (i, i, i)
            for i in range(1, len(self.bunching) + 1)]
        factors += [
            "(1.0 - aca%d*exp(-x/(act%d*1e-6)))" % (i, i)
            for i in range(1, len(self.anticorr) + 1)]
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
        """The active mode's parameters plus the relaxation terms' own."""
        mode = self.diffusion_mode
        if mode == "mdf":
            # The waists, D and the two-focus separation are the *node's*
            # ports, not the equation's variables; the objective builder
            # carries them. What is left is what the equation multiplies the
            # node's shape by.
            p = self.mdf_physical
            out = [p._N, p._b, p._bg]
            out += self.bunching._ba + self.bunching._bt
            out += self.anticorr._aca + self.anticorr._act
            return out
        group = {"two_focus": self.two_focus,
                 "species": self.species}.get(mode, self.gauss)
        out = [group._N, group._w_r, group._w_z, group._b, group._diam,
               group._bg]
        if mode == "species":
            out += list(group._species)
        else:
            out.append(group._D)
        out += self.bunching._ba + self.bunching._bt
        out += self.anticorr._aca + self.anticorr._act
        return out

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
