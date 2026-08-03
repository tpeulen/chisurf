"""Photokinetic FCS model (kinetic saturation + advanced FCS).

Composable FCS model for complex photokinetic fits: an arbitrary N-state
photochemical rate scheme (dark/excitation matrices, state brightnesses)
drives a numerically integrated, power-dependent saturation shape — the
non-analytical path that GeneralFCSModel deliberately does not take (the
general model is purely operational: diffusion + relaxation terms, evaluated
analytically).

The rate-scheme parameter groups (:class:`RateMatrixRates`, :class:`DarkRates`,
:class:`ExcRates`, :class:`StateBrightness`, :class:`KineticSaturationTerms`)
live here — not in :mod:`chisurf.core.models.fcs.general` — because they are
the kinetics model's vocabulary; fcs_saturation_calc's calculator tool
reuses them directly. The numerical shape itself is shared with the calculator
via :mod:`chisurf.core.fluorescence.fcs.saturation`.

Normalization: G(0) = b + 1/N. When saturation is active the amplitude carries
the volume expansion V_0/V_eff (so G(0) drops as the power rises); P = 0
returns to the analytical Gaussian shape with G(0) = b + 1/N.
"""

from __future__ import annotations

import math

import numpy as np

import chisurf as cs
from chisurf.core.fitting.kinetics import RateMatrixMixin
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.fcs.normalization import resolve_total_mean_count_rate
from chisurf.core.fluorescence.fcs.saturation import (
    DARK_RATE_UNITS,
    compute_bunching_factor,
    excitation_rate_peak,
    gaussian_g_diff,
    relaxation_spectrum,
    saturated_curve_shape,
)
from chisurf.core.models.fcs.mdf import compute_brightness, set_output_parameter
from chisurf.core.models.model import ModelCurve


class RateMatrixRates(FittingParameterGroup, RateMatrixMixin):
    """Off-diagonal transition rates of a photokinetic scheme as fit parameters.

    One class serves both the dark (rate) and excitation (cross-section)
    matrices of the kinetic saturation scheme; only the parameter-name prefix
    and the default rate differ.
    """

    def __init__(
        self,
        name: str = "rates",
        n_states: int = 3,
        rate_prefix: str = "k",
        default_rate: float = 1.0,
        **kwargs,
    ):
        """Initialize an ``n_states`` rate group.

        Parameters
        ----------
        name : str
            Group name.
        n_states : int
            Number of states; at least two.
        rate_prefix : str
            Prefix of the generated parameter names, ``<prefix><i>_<j>``.
        default_rate : float
            Value a freshly grown transition starts at.
        **kwargs
            Forwarded to the parent constructor.
        """
        self.rate_prefix = rate_prefix
        self.default_rate = default_rate
        super().__init__(name=name, **kwargs)
        self._n_states = n_states
        self._rebuild_rates(n_states)

    @property
    def n_states(self) -> int:
        """Number of states in the rate group."""
        return self._n_states

    @n_states.setter
    def n_states(self, val: int):
        self._rebuild_rates(max(2, int(val)))

    @property
    def rates(self) -> list[float]:
        """Flat row-major list of the current rate matrix values."""
        return self.flat_rates.tolist()

    @rates.setter
    def rates(self, value: list[float]):
        from chisurf.core.fluorescence.kinetics import rate_matrix_from_rates

        self.set_rate_matrix(rate_matrix_from_rates(value, self.n_states))


class DarkRates(RateMatrixRates):
    """Dark-state transition rates (``k``-prefixed, in ``dark_unit``)."""

    def __init__(self, name="dark", n_states=3, **kwargs):
        super().__init__(name=name, n_states=n_states, rate_prefix="k", default_rate=0.0, **kwargs)


class ExcRates(RateMatrixRates):
    """Excitation cross-section matrix (``sigma``-prefixed, dimensionless)."""

    def __init__(self, name="exc", n_states=3, **kwargs):
        super().__init__(
            name=name, n_states=n_states, rate_prefix="sigma", default_rate=0.0, **kwargs
        )


class StateBrightness(FittingParameterGroup):
    """Relative fluorescence brightness Q_i of each photochemical state."""

    def __init__(self, name="brightness", n_states=3, **kwargs):
        super().__init__(name=name, **kwargs)
        self._n_states = n_states
        self._rebuild(n_states)

    def _rebuild(self, n_states: int):
        """Resize the brightness vector, keeping the values that survive.

        State 2 starts bright and every other state dark. That is not an
        assumption about triplets: it is the one thing every photochemical
        scheme has in common — state 1 is whatever the molecule sits in when it
        is not excited, and it cannot emit. Which of the remaining states emit,
        and how brightly, is the scheme's business.
        """
        target = max(2, int(n_states))
        for k in list(self.__dict__.keys()):
            if k.startswith("B_"):
                delattr(self, k)
        old = {p.name: p.value for p in getattr(self, "_brightness", [])}
        old_fixed = {p.name: p.fixed for p in getattr(self, "_brightness", [])}
        brightness = []
        for i in range(1, target + 1):
            name = f"B_{i}"
            val = old.get(name, 1.0 if i == 2 else 0.0)
            fixed = old_fixed.get(name, i != 2)
            desc_name = f"state {i}"
            p = FittingParameter(
                value=float(val),
                name=name,
                lb=0.0,
                ub=1.0,
                bounds_on=True,
                fixed=fixed,
                label_text=f"Q<sub>{i}</sub>",
                registry_id=f"fcs.saturation.b_{i}",
            )
            setattr(p, "description", f"Relative fluorescence brightness Q_{i} of {desc_name}.")
            setattr(self, name, p)
            brightness.append(p)
        self._brightness = brightness
        self._n_states = target
        self._parameters = None
        self.find_parameters()

    @property
    def n_states(self) -> int:
        """Number of brightness states."""
        return self._n_states

    @n_states.setter
    def n_states(self, val: int):
        self._rebuild(max(2, int(val)))

    @property
    def array(self) -> np.ndarray:
        """Brightness values as a length-``n_states`` float array."""
        return np.array(
            [max(0.0, float(p.value)) for p in getattr(self, "_brightness", [])], dtype=float
        )


class KineticSaturationTerms(FittingParameterGroup):
    """Photokinetic rate scheme and optics for FCS saturation.

    The scheme is an arbitrary N-state system: a dark-rate matrix ``K_dark``, an
    excitation cross-section matrix ``K_exc`` and a per-state brightness vector.
    Nothing here knows about singlets, triplets or isomers — a state is bright or
    dark because its ``Q_i`` says so, and a transition exists because its rate is
    non-zero. Two states with a fluorescence decay rate is the minimal scheme
    (and the default); a triplet, a cis isomer, a photobleached state or a FRET
    partner are all just further states.

    The model evaluates the scheme at steady state at every point of the
    excitation profile ``k_exc(r, z)``, yielding the spatial emission profile
    that is numerically integrated into the FCS autocorrelation.
    """

    #: A freshly created scheme starts as ground / excited / dark -- the triplet
    #: case, because it is what most dyes actually do and starting there saves
    #: the common setup. It is a *default*, not an assumption: nothing in this
    #: class or in the saturation core treats state 3 as special, and the scheme
    #: can be resized, relabelled or rewired into anything.
    DEFAULT_N_STATES = 3

    #: Labels a default-sized scheme starts with, index by index. A scheme that
    #: means something else says so by setting ``_custom_state_labels``; states
    #: beyond this list fall back to their number.
    DEFAULT_STATE_LABELS = ("S0", "S1", "T1")

    def __init__(self, name: str = "kinetic_saturation", **kwargs):
        """Initialize the kinetic saturation parameter group."""
        super().__init__(name=name, **kwargs)
        self._power = FittingParameter(
            value=0.0,
            name="power",
            lb=0.0,
            ub=100000.0,
            bounds_on=True,
            fixed=True,
            label_text="P",
            registry_id="fcs.saturation.power",
        )
        setattr(self._power, "description", "Laser excitation power P in mW")
        self._extinction = FittingParameter(
            value=80000.0,
            name="extinction",
            # Not floored at a "sensible" 1e3: this is epsilon *at the excitation
            # wavelength*, and exciting a dye well off its maximum legitimately
            # gives a few hundred or less. A floor here would silently substitute
            # 1000 for a value read off a real spectrum.
            lb=0.0,
            ub=1e6,
            bounds_on=True,
            fixed=True,
            label_text="&epsilon;",
            registry_id="fcs.saturation.extinction",
        )
        setattr(
            self._extinction,
            "description",
            "Molar extinction coefficient &epsilon; at the excitation wavelength, in M⁻¹cm⁻¹. "
            "Pick a dye to read it from the MMFDB spectrum.",
        )
        self._wavelength = FittingParameter(
            value=488.0,
            name="wavelength",
            lb=200.0,
            ub=1200.0,
            bounds_on=True,
            fixed=True,
            label_text="&lambda;<sub>exc</sub>",
            registry_id="fcs.saturation.wavelength",
        )
        setattr(
            self._wavelength,
            "description",
            "Excitation wavelength &lambda; in nm. It sets the photon energy, hence how many "
            "photons a given power delivers, and which &epsilon; applies.",
        )
        self._w_r = FittingParameter(
            value=200.0,
            name="w_r",
            lb=10.0,
            ub=2000.0,
            bounds_on=True,
            fixed=True,
            label_text="w<sub>r</sub>",
            registry_id="fcs.saturation.w_r",
        )
        setattr(self._w_r, "description", "Lateral 1/e² beam waist radius w_r in nm")
        self._w_z = FittingParameter(
            value=1000.0,
            name="w_z",
            lb=50.0,
            ub=10000.0,
            bounds_on=True,
            fixed=True,
            label_text="w<sub>z</sub>",
            registry_id="fcs.saturation.w_z",
        )
        setattr(self._w_z, "description", "Axial 1/e² beam waist radius w_z in nm")
        self._D = FittingParameter(
            value=400.0,
            name="D",
            lb=0.01,
            ub=10000.0,
            bounds_on=True,
            fixed=True,
            label_text="D",
            registry_id="fcs.saturation.D",
        )
        setattr(self._D, "description", "Diffusion coefficient D in µm²/s")
        self._N = FittingParameter(
            value=1.0,
            name="N",
            lb=0.001,
            ub=1000.0,
            bounds_on=True,
            fixed=True,
            label_text="N",
            registry_id="fcs.saturation.N",
        )
        setattr(self._N, "description", "Average number of molecules in detection volume N")
        self._b = FittingParameter(
            value=1.0,
            name="b",
            lb=0.0,
            ub=10.0,
            bounds_on=True,
            fixed=True,
            label_text="b",
            registry_id="fcs.saturation.b",
        )
        setattr(self._b, "description", "Baseline offset b")
        self._bg = FittingParameter(
            value=0.0,
            name="bg",
            lb=0.0,
            ub=1e9,
            bounds_on=True,
            fixed=True,
            label_text="bg",
            registry_id="fcs.saturation.bg",
        )
        setattr(self._bg, "description", "Background count rate bg in kHz")
        self._s = FittingParameter(
            value=5.0,
            name="s",
            lb=1.0,
            ub=50.0,
            fixed=True,
            label_text="s",
            registry_id="fcs.saturation.s",
        )
        self._brightness_out = FittingParameter(
            value=0.0,
            name="brightness",
            lb=0.0,
            ub=1e9,
            fixed=True,
            label_text="B",
            registry_id="fcs.saturation.brightness_out",
        )

        self._relaxation_outputs: list[FittingParameter] = []
        self._n_states = self.DEFAULT_N_STATES
        self.dark_unit = "1/us"
        self.dark = DarkRates(n_states=self._n_states)
        self.exc = ExcRates(n_states=self._n_states)
        self.brightness = StateBrightness(n_states=self._n_states)
        self._rebuild_relaxation_outputs(self._n_states)
        self._custom_state_labels: list[str] | None = None
        self._custom_state_names: list[str] | None = None
        self._dye_name: str = ""

        # A rhodamine-like triplet scheme to start from: state 1 absorbs into
        # state 2, which decays radiatively (4 ns) or crosses into the dark state
        # 3 (~1 % yield) that empties on a microsecond timescale. Rates are stored
        # in `dark_unit` (1/us), so 250 /us is a 4 ns lifetime.
        self.exc.rates_by_name()["sigma1_2"].value = 1.0
        self.dark.rates_by_name()["k2_1"].value = 250.0
        self.dark.rates_by_name()["k2_3"].value = 2.5
        self.dark.rates_by_name()["k3_1"].value = 0.5

    power = property(lambda s: float(s._power.value) * 1e-3)  # mW to W
    pwr = property(lambda s: float(s._power.value) * 1e-3)    # mW to W alias
    extinction = property(lambda s: float(s._extinction.value))
    wavelength_nm = property(lambda s: float(s._wavelength.value))
    wavelength_m = property(lambda s: float(s._wavelength.value) * 1e-9)
    w_r_nm = property(lambda s: float(s._w_r.value))
    w_z_nm = property(lambda s: float(s._w_z.value))
    D_um2s = property(lambda s: float(s._D.value))
    N = property(lambda s: float(s._N.value))
    b = property(lambda s: float(s._b.value))
    bg = property(lambda s: float(s._bg.value))

    def _rebuild_relaxation_outputs(self, n_states: int) -> None:
        """Resize the read-only relaxation-time outputs to the scheme.

        An N-state scheme relaxes with N-1 modes, whose rates are the non-zero
        eigenvalues of ``K_dark + k_exc K_exc``. Those eigenvalues are what a
        bunching fit of the data actually returns, so they belong in the table
        beside the rates the user types -- otherwise the connection between a
        scheme and the timescales it predicts has to be worked out by hand.
        """
        for parameter in getattr(self, "_relaxation_outputs", []):
            name = parameter.name
            if hasattr(self, f"_{name}"):
                delattr(self, f"_{name}")
        outputs = []
        for i in range(1, max(1, n_states)):
            name = f"tau_R{i}"
            parameter = FittingParameter(
                value=float("nan"), name=name, fixed=True, is_output=True,
                label_text=f"&tau;<sub>R{i}</sub>[µs]",
                registry_id=f"fcs.saturation.{name}",
            )
            setattr(
                parameter, "description",
                f"Relaxation time {i} of the scheme (µs): an eigenvalue of "
                f"K_dark + k_exc·K_exc at the peak excitation rate, slowest first. "
                f"This is the timescale a bunching term fitted to the data reports, "
                f"and it shortens as the power rises.",
            )
            setattr(self, f"_{name}", parameter)
            outputs.append(parameter)
        self._relaxation_outputs = outputs
        self._parameters = None

    def update_relaxation_outputs(self, fit=None) -> list[tuple[float, float]]:
        """Recompute the relaxation spectrum and write it into the outputs.

        Returns the ``(time_s, amplitude)`` modes so a caller can report them.
        """
        modes = relaxation_spectrum(
            excitation_rate_peak(self.power, self.extinction, self.w_r_nm * 1e-9,
                                 self.wavelength_m),
            self.dark_matrix_hz, self.exc.rate_matrix(), self.brightness.array,
        )
        for i, parameter in enumerate(self._relaxation_outputs):
            value = modes[i][0] * 1e6 if i < len(modes) else float("nan")
            if fit is not None:
                set_output_parameter(fit, parameter, value)
            else:
                parameter.value = value
        return modes

    @property
    def dark_matrix_hz(self) -> np.ndarray:
        """Dark transition matrix in Hz (s^-1) for the photokinetic equation."""
        factor = DARK_RATE_UNITS.get(self.dark_unit, DARK_RATE_UNITS["1/us"])
        return self.dark.rate_matrix() * factor

    @property
    def n_states(self) -> int:
        """Number of states in the photochemical scheme."""
        return self._n_states

    @n_states.setter
    def n_states(self, val: int):
        """Resize the scheme, rebuilding the rate matrices and brightness."""
        target = max(2, int(val))
        if target != self._n_states:
            self._n_states = target
            self.dark.n_states = target
            self.exc.n_states = target
            self.brightness.n_states = target
            self._rebuild_relaxation_outputs(target)
            if hasattr(self, "fit") and self.fit:
                self.fit.update()

    @property
    def state_labels(self) -> list[str]:
        """Short display label of each state.

        Defaults to the state numbers. A scheme that means something specific —
        S0/S1/T1, trans/cis, D/A — says so by setting ``_custom_state_labels``
        (that is what a scheme JSON's ``state_labels`` does); the model itself
        never assumes a photophysical meaning for a state's position.
        """
        labels = getattr(self, "_custom_state_labels", None) or self.DEFAULT_STATE_LABELS
        out = []
        for i in range(self.n_states):
            # Per index, not all-or-nothing: growing a triplet scheme to four
            # states must keep S0/S1/T1 named and only number the new one.
            raw = labels[i] if i < len(labels) else str(i + 1)
            out.append(str(raw).split(" ")[0].split("(")[0].strip() or str(i + 1))
        return out

    @property
    def parameters(self) -> list[FittingParameter]:
        """Return parameter list."""
        if self._parameters is None:
            self._parameters = self.find_parameters()
        return self._parameters

    @property
    def state_descriptions(self) -> list[str]:
        """Long display name of each state, e.g. ``'S1 (Singlet Excited State)'``.

        Like :attr:`state_labels`, the long names come from the scheme
        (``_custom_state_names``) and fall back to the state number.
        """
        labels = self.state_labels
        names = getattr(self, "_custom_state_names", None)
        result = []
        for i in range(self.n_states):
            lbl = labels[i] if i < len(labels) else str(i + 1)
            name = names[i] if names and i < len(names) and names[i] else f"State {i + 1}"
            result.append(f"{lbl} ({name})")
        return result

    def find_parameters(self):
        """Find the optics and measurement parameters this group owns directly.

        The rate matrices and the brightness vector are separate groups; the
        model collects them in :attr:`FCSKineticsModel.parameters_all`.
        """
        self._parameters = [
            self._power,
            self._wavelength,
            self._extinction,
            self._w_r,
            self._w_z,
            self._D,
            self._N,
            self._b,
            self._bg,
            *getattr(self, "_relaxation_outputs", []),
        ]
        return self._parameters

    @property
    def active(self) -> bool:
        """Whether saturation physics is engaged, i.e. the excitation power is non-zero.

        Below this the scheme cannot be populated at all — no excitation, no
        excited state, no dark state — and the model reduces to the analytical
        Gaussian shape. Note this is *not* "a scheme is configured": the number
        of states is always at least two, so that would always be true.
        """
        return self.power > 0.0

    def status_html(self) -> str:
        """One-line HTML statement of what the model is currently computing."""
        if not self.active:
            return (
                "<p><b>P = 0 mW — no saturation.</b> The shape is the analytical 3D "
                "Gaussian and the amplitude is exactly 1/N. Set the excitation power "
                "to engage the photokinetic scheme.</p>"
            )
        k0 = excitation_rate_peak(self.power, self.extinction, self.w_r_nm * 1e-9,
                                  self.wavelength_m)
        return (
            f"<p><b>Peak excitation rate k<sub>exc</sub>(0,0) = {k0 / 1e6:.3g} µs⁻¹</b> "
            f"at {self._power.value:.4g} mW, λ = {self.wavelength_nm:.0f} nm, "
            f"ε = {self.extinction:.4g} M⁻¹cm⁻¹.<br>"
            f"The amplitude carries the saturation volume expansion V<sub>0</sub>/V<sub>eff</sub>, "
            f"so G(0) drops below 1/N as the power rises.</p>"
        )

    @property
    def dye(self) -> str:
        """Name of the MMFDB dye the optics were read from (empty if typed in)."""
        return getattr(self, "_dye_name", "")

    @dye.setter
    def dye(self, name: str) -> None:
        """Read epsilon at the excitation wavelength (and the lifetime) from MMFDB."""
        self.apply_dye(name)

    def dye_names(self) -> list[str]:
        """List the dyes MMFDB can supply an extinction spectrum for."""
        from chisurf.core.fluorescence.fret.dyes import list_absorbing_dyes

        return [""] + list_absorbing_dyes()

    def apply_dye(self, name: str, lifetime_rate: str | None = None) -> dict[str, str]:
        """Fill the optics from the MMFDB entry of ``name``.

        Only what the database actually holds is written, and each written
        quantity is reported back with its provenance — a curated gap must never
        silently overwrite a number the user set.

        Parameters
        ----------
        name : str
            Chromophore name as curated in MMFDB.
        lifetime_rate : str, optional
            Name of the dark-rate parameter that *is* this dye's fluorescence
            decay (e.g. ``"k2_1"``), set to ``1/tau`` when the database knows the
            lifetime. Schemes declare this; the model cannot guess which of an
            arbitrary scheme's transitions is the radiative one.

        Returns
        -------
        dict
            Quantity name -> provenance string, for what was written.
        """
        from chisurf.core.fluorescence.fret.dyes import extinction_at

        wanted = str(name or "").strip()
        applied: dict[str, str] = {}
        if not wanted:
            self._dye_name = ""
            return applied

        epsilon = extinction_at(wanted, self.wavelength_nm)
        if epsilon is None:
            # The chooser is type-to-search, so a half-typed or mistyped name
            # arrives here routinely. Keep the dye that *is* applied rather than
            # recording a name whose epsilon was never read.
            return applied

        self._dye_name = wanted
        if epsilon > 0.0:
            self._extinction.value = float(epsilon)
            applied["extinction"] = "mmfdb:spectra"

        if lifetime_rate:
            from chisurf.core.fluorescence.fret.dyes import dye_properties

            properties = dye_properties(self._dye_name)
            tau_ns = getattr(properties, "lifetime", None) if properties else None
            if tau_ns:
                factor = DARK_RATE_UNITS.get(self.dark_unit, DARK_RATE_UNITS["1/us"])
                rates = self.dark.rates_by_name()
                if lifetime_rate in rates:
                    rates[lifetime_rate].value = 1e9 / (float(tau_ns) * factor)
                    applied[lifetime_rate] = "mmfdb:property"
        return applied


class FCSKineticsModel(ModelCurve):
    """Photokinetic FCS model: kinetic saturation scheme + 3D volume integration.

    Attributes
    ----------
    saturation_mode : {"full", "fast"}
        ``"full"`` (default) performs 3D numerical volume integration of the
        steady-state photokinetic master equation, incorporating spatial beam
        saturation and scheme relaxation dynamics. ``"fast"`` uses an implicit
        3D Gaussian approximation for fast evaluation.
    saturation : KineticSaturationTerms
        The photokinetic scheme (power, extinction, beam waist, diffusion,
        rate matrices, state brightnesses).
    """

    name = "FCS (kinetics)"
    view_spec_file = "kinetics.view.json"

    _SATURATION_MODES = ("full", "fast")

    def __init__(self, fit: cs.core.fitting.fit.Fit, **kwargs):
        """Initialize the photokinetic saturation scheme."""
        super().__init__(fit, **kwargs)
        self._saturation_mode = "full"
        self.saturation = KineticSaturationTerms(name="kinetic_saturation", fit=fit)
        self._sat_cache: tuple[tuple, np.ndarray] | None = None
        self._updating_model = False
        self.find_parameters()

    @property
    def parameters_all(self):
        """Every parameter of the model: optics, dark rates, cross sections, brightness.

        The sub-groups are asked for ``parameters_all``, not ``parameters``. The
        latter returns only the *free* ones, and a scheme's rates are fixed by
        default -- so collecting those left every rate out of
        ``parameters_all_dict``, and anything that looks a parameter up by name
        (linking it across a global fit, restoring it from a saved state) could
        not see it.
        """
        params = list(super().parameters_all)
        seen = {id(p) for p in params}
        for grp in (self.saturation.dark, self.saturation.exc, self.saturation.brightness):
            for p in getattr(grp, "parameters_all", []) or []:
                if id(p) not in seen:
                    params.append(p)
                    seen.add(id(p))
        return params

    @property
    def saturation_mode(self) -> str:
        """Active calculation mode: ``"full"`` or ``"fast"``."""
        return self._saturation_mode

    @saturation_mode.setter
    def saturation_mode(self, v: str) -> None:
        v = str(v).lower()
        if v not in self._SATURATION_MODES:
            raise ValueError(f"saturation_mode must be one of {self._SATURATION_MODES}, got {v!r}")
        self._saturation_mode = v
        self.update()

    def update_model(self, **kwargs) -> None:
        """Evaluate the photokinetic FCS model."""
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

        sat = self.saturation
        w0 = sat.w_r_nm * 1e-9
        z0 = sat.w_z_nm * 1e-9
        D_m2_s = sat.D_um2s * 1e-12
        tau_s = tau_ms * 1e-3

        s_val = sat.w_z_nm / sat.w_r_nm if sat.w_r_nm > 0 else float("nan")
        set_output_parameter(self.fit, sat._s, s_val)
        # The scheme's relaxation times are eigenvalues of K_dark + k_exc K_exc,
        # i.e. exactly what a bunching term fitted to this curve would report.
        sat.update_relaxation_outputs(self.fit)
        brightness = compute_brightness(self.fit, sat.N, sat.bg)
        if brightness is not None:
            set_output_parameter(self.fit, sat._brightness_out, brightness)

        if not sat.active:
            # No excitation, no populated scheme: the exact analytical limit.
            g = gaussian_g_diff(tau_s, w0, z0, D_m2_s)
        elif self.saturation_mode == "fast":
            g = gaussian_g_diff(tau_s, w0, z0, D_m2_s) * compute_bunching_factor(
                excitation_rate_peak(sat.power, sat.extinction, w0, sat.wavelength_m),
                sat.dark_matrix_hz,
                sat.exc.rate_matrix(),
                sat.brightness.array,
                tau_s,
            )
        else:
            key = (
                tuple(tau_ms),
                sat.power,
                sat.wavelength_nm,
                sat.extinction,
                tuple(np.asarray(sat.dark_matrix_hz).ravel()),
                tuple(np.asarray(sat.exc.rate_matrix()).ravel()),
                tuple(np.asarray(sat.brightness.array).ravel()),
                sat.w_r_nm,
                sat.w_z_nm,
                sat.D_um2s,
            )
            if self._sat_cache is not None and self._sat_cache[0] == key:
                g = self._sat_cache[1]
            else:
                g = saturated_curve_shape(
                    tau_s,
                    power_W=sat.power,
                    extinction=sat.extinction,
                    dark_matrix=sat.dark_matrix_hz,
                    exc_matrix=sat.exc.rate_matrix(),
                    brightness=sat.brightness.array,
                    w0=w0,
                    z0=z0,
                    D=D_m2_s,
                    include_bunching=True,
                    wavelength_m=sat.wavelength_m,
                )
                self._sat_cache = (key, g)

        meta = getattr(getattr(self.fit, "data", None), "meta_data", {}) or {}
        mean_cr_total = resolve_total_mean_count_rate(meta)
        if mean_cr_total is not None and mean_cr_total > 0 and sat.bg > 0:
            bg_factor = max(0.0, (mean_cr_total - sat.bg) / mean_cr_total) ** 2
        else:
            bg_factor = 1.0

        self.x = tau_ms
        self.y = sat.b + (bg_factor / sat.N) * g

    def equation_html(self) -> str:
        """Render the active fitting equation as HTML."""
        gauss = (
            "(1+4D&tau;/w<sub>r</sub>&sup2;)<sup>&minus;1</sup> &middot; "
            "(1+4D&tau;/w<sub>z</sub>&sup2;)<sup>&minus;1/2</sup>"
        )
        if not self.saturation.active:
            g, sub = gauss, "P = 0 mW — analytical Gaussian, no photokinetics"
        elif self.saturation_mode == "full":
            g = "G<sub>num</sub>(&tau;; k<sub>exc</sub>(r,z), K) &middot; X<sub>kinetics</sub>(&tau;)"
            sub = "Full — numerical volume integration, amplitude V<sub>0</sub>/V<sub>eff</sub>"
        else:
            g = f"{gauss} &middot; X<sub>kinetics</sub>(&tau;)"
            sub = "Fast — Gaussian volume, photokinetic bunching only (no V<sub>0</sub>/V<sub>eff</sub>)"
        return f"<p><b>G(&tau;) = b + (1-bg/I)&sup2; &middot; (1/N) &middot; {g}</b><br><i>({sub})</i></p>"
