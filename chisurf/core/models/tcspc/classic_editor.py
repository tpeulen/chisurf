"""The classic TCSPC editor over a BFF-described model.

Before the TCSPC models became views on BFF, every lifetime and FRET fit had
the same editor: *Convolution* (IRF, per/exp/full, n0, dt, rep, stop, IRF
start/stop, lb, ts, IRF shape), *Generic* (background curve, sc, bg, tBg,
tMeas and the photon counts), *Corrections* (linearization table, smoothing,
pile-up/DNL/reverse, dead time, window size), the model's own components with
add/del, and *Anisotropy*. Those editors are the ``views/<family>.view.json``
files beside :mod:`chisurf.core.models.description`, unchanged in their
structure, and they address the groups this module provides: ``convolve``,
``generic``, ``corrections``, ``lifetimes``, ``anisotropy``, ``fret_parameters``,
``gaussians``, ``fret_rates``, ``fa``/``fb``, ``pddem``.

A group here owns nothing. Every row is a BFF parameter of the model, a scalar
of its description shown as a fixed row (``dt``, ``rep``, ``tBg``, ...), or an
output computed from the model (``#Ph_B``, ``E_FRET``); every switch writes a
scalar. The fitted parameter vector is the model's own: these groups are
properties, never attributes of the model's ``__dict__``, so parameter
discovery does not see the rows they add.
"""

from __future__ import annotations

import typing

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter

#: Polarization scalar value <-> the classic editor's names.
_POLARIZATIONS = ("vm", "vv", "vh", "vv/vh")
#: Linearization window scalar value <-> ``chisurf.core.math.signal.window_function_types``.
_WINDOWS = ("flat", "hanning", "hamming", "bartlett", "blackman")
#: A description scalar this large means "no limit" (the end of the decay).
_NO_LIMIT = 1e17


class ScalarRow(FittingParameter):
    """A description scalar shown as a fixed row of a parameter table.

    Reads and writes the scalar through *get* / *set*, so the table cell, the
    scalar and the model agree; it is never free, since a scalar is not fitted.
    """

    def __init__(
        self,
        name: str,
        get: typing.Callable[[], float],
        set_: typing.Callable[[float], None],
        **kwargs,
    ):
        self.__dict__["_get"] = get
        try:
            start = float(get())
        except Exception:
            start = 0.0
        super().__init__(value=start, name=name, fixed=True, **kwargs)
        # Set after construction: the constructor writes the start value, and
        # that must not reach the scalar.
        self.__dict__["_set"] = set_

    @property
    def value(self) -> float:
        try:
            return float(self.__dict__["_get"]())
        except Exception:
            return float("nan")

    @value.setter
    def value(self, v: float) -> None:
        setter = self.__dict__.get("_set")
        if setter is not None:
            setter(float(v))

    @property
    def fixed(self) -> bool:
        return True

    @fixed.setter
    def fixed(self, v: bool) -> None:
        pass


class OutputRow(ScalarRow):
    """A quantity computed from the model, shown read-only (``#Ph_B``, ``E_FRET``)."""

    def __init__(self, name: str, get: typing.Callable[[], float], **kwargs):
        super().__init__(name, get, lambda _v: None, is_output=True, **kwargs)


class _Group:
    """Common ground of the classic groups: the view, and rows looked up by id."""

    name = ""

    def __init__(self, view, name: str = ""):
        self._view = view
        self.name = name
        self._rows: dict[str, FittingParameter] = {}

    @property
    def parameters_all_dict(self) -> dict:
        """The rows by name, as a parameter group offers them (``g``, ``l1``, ...)."""
        return {p.name: p for p in self.parameters_all}

    @property
    def parameter_dict(self) -> dict:
        return self.parameters_all_dict

    def __len__(self) -> int:
        return len(self.parameters_all)

    # -- BFF parameters -------------------------------------------------------
    def _by_id(self) -> dict[str, FittingParameter]:
        return {getattr(p, "canonical_id", None): p for p in self._view.parameters_all}

    def _parameters(self, ids: typing.Sequence[str]) -> list:
        used = set(self._view.structure_parameter_ids())
        by_id = self._by_id()
        return [by_id[i] for i in ids if i in by_id and i in used]

    # -- scalars ---------------------------------------------------------------
    def _has(self, scalar: str) -> bool:
        return scalar in self._view.scalar_names()

    def _get(self, scalar: str, default: float = 0.0) -> float:
        value = self._view.get_scalar(scalar) if self._has(scalar) else None
        return float(default if value is None else value)

    def _set(self, scalar: str, value: float) -> None:
        if self._has(scalar):
            self._view.set_scalar(scalar, float(value))

    def _row(self, key: str, factory: typing.Callable[[], FittingParameter]) -> FittingParameter:
        """One stable row object per key, so a table keeps editing the same row."""
        row = self._rows.get(key)
        if row is None:
            row = factory()
            self._rows[key] = row
        return row

    def _dt(self) -> float:
        return self._get("dt", 1.0) or 1.0

    def _n_channels(self) -> int:
        data = getattr(self._view.fit, "data", None)
        try:
            return int(len(data.x))
        except Exception:
            return 0


class Convolve(_Group):
    """Convolution: the IRF and how the model is convolved with it."""

    def __init__(self, view):
        super().__init__(view, "Convolution")
        self._full = False

    # -- the IRF ---------------------------------------------------------------
    @property
    def irf(self):
        return self._view.datasets.response

    @property
    def unnormalized_irf(self):
        return self.irf

    @property
    def _irf(self):
        return self.irf

    @_irf.setter
    def _irf(self, curve) -> None:
        if curve is None:
            self.unload_irf()
        else:
            self._view.set_dataset("response", curve)

    def unload_irf(self) -> None:
        if self._view.has_dataset("response"):
            self._view.unset_dataset("response")

    # -- switches --------------------------------------------------------------
    @property
    def mode(self) -> str:
        if self._get("periodic_excitation", 1.0):
            return "per"
        return "full" if self._full else "exp"

    @mode.setter
    def mode(self, value: str) -> None:
        # BFF convolves a single excitation or a periodic train; the classic
        # "full" (numpy's full convolution of one excitation) is the former.
        value = str(value)
        self._full = value == "full"
        self._set("periodic_excitation", 1.0 if value == "per" else 0.0)

    @property
    def do_convolution(self) -> bool:
        return bool(self._get("convolve", 1.0))

    @do_convolution.setter
    def do_convolution(self, value: bool) -> None:
        self._set("convolve", 1.0 if value else 0.0)

    # -- rows ------------------------------------------------------------------
    def _stop_ns(self, scalar: str) -> float:
        value = self._get(scalar, _NO_LIMIT * 10)
        end = self._n_channels() * self._dt()
        return end if value >= _NO_LIMIT else value

    @property
    def parameters_all(self) -> list:
        rows = []
        rows += self._parameters(["instrument.n0"])
        rows.append(
            self._row(
                "dt",
                lambda: ScalarRow(
                    "dt",
                    lambda: self._dt(),
                    lambda v: self._set("dt", v),
                    decimals=4,
                    description="Time bin width of the TCSPC histogram (ns per channel).",
                ),
            )
        )
        rows.append(
            self._row(
                "rep",
                lambda: ScalarRow(
                    "rep",
                    lambda: 1000.0 / max(self._get("period", 100.0), 1e-12),
                    lambda v: self._set("period", 1000.0 / v if v > 0 else 100.0),
                    description="Laser repetition rate of the excitation source (MHz).",
                ),
            )
        )
        if self._has("convolution_stop"):
            rows.append(
                self._row(
                    "stop",
                    lambda: ScalarRow(
                        "stop",
                        lambda: (
                            min(
                                self._get("convolution_stop", _NO_LIMIT * 10),
                                self._n_channels() or 1e18,
                            )
                            * self._dt()
                        ),
                        lambda v: self._set("convolution_stop", max(1.0, round(v / self._dt()))),
                        description="Stop time of the convolution window (ns).",
                    ),
                )
            )
        for key, scalar, label in (
            ("irf_start", "response_start", "IRF<sub>start</sub>"),
            ("irf_stop", "response_stop", "IRF<sub>stop</sub>"),
        ):
            if not self._has(scalar):
                continue
            rows.append(
                self._row(
                    key,
                    lambda scalar=scalar, key=key, label=label: ScalarRow(
                        key,
                        (lambda: self._stop_ns(scalar))
                        if key == "irf_stop"
                        else (lambda: self._get(scalar, 0.0)),
                        lambda v, scalar=scalar: self._set(scalar, v),
                        label_text=label,
                        description="Region of the IRF used for the convolution (ns).",
                    ),
                )
            )
        rows += self._parameters(
            [
                "instrument.response_background",
                "instrument.timeshift",
                "instrument.irf_width",
                "instrument.irf_shape",
                "instrument.irf_position",
            ]
        )
        return rows

    def visible_parameters(self) -> list:
        return self.parameters_all


class Generic(_Group):
    """Nuisance: scatter, background, the background curve and the photon counts."""

    def __init__(self, view):
        super().__init__(view, "Generic")

    @property
    def background_curve(self):
        return self._view.datasets.background_pattern

    @background_curve.setter
    def background_curve(self, curve) -> None:
        if curve is None:
            self.unload_background_curve()
        else:
            self._view.set_dataset("background_pattern", curve)

    def unload_background_curve(self) -> None:
        if self._view.has_dataset("background_pattern"):
            self._view.unset_dataset("background_pattern")

    @property
    def n_ph_bg(self) -> float:
        """Background photons: the background curve rescaled to the measurement, plus bg per channel."""
        n = 0.0
        curve = self.background_curve
        if curve is not None:
            a = (
                float(np.sum(curve.y))
                / max(self._get("t_background", 1.0), 1e-12)
                * self._get("t_decay", 1.0)
            )
            if np.isfinite(a):
                n += a
        background = self._parameters(["instrument.background"])
        if background:
            n += float(background[0].value) * self._n_channels()
        return n

    @property
    def n_ph_fl(self) -> float:
        data = getattr(self._view.fit, "data", None)
        total = float(np.sum(getattr(data, "y", []))) if data is not None else 0.0
        return max(total - self.n_ph_bg, 1.0)

    @property
    def parameters_all(self) -> list:
        rows = self._parameters(["instrument.scatter", "instrument.background"])
        for key, scalar, text in (
            ("tBg", "t_background", "Measurement time of the background acquisition."),
            ("tMeas", "t_decay", "Measurement time of the main TCSPC experiment."),
        ):
            if self._has(scalar):
                rows.append(
                    self._row(
                        key,
                        lambda key=key, scalar=scalar, text=text: ScalarRow(
                            key,
                            lambda: self._get(scalar, 1.0),
                            lambda v: self._set(scalar, v),
                            description=text,
                        ),
                    )
                )
        rows.append(
            self._row(
                "PhB",
                lambda: OutputRow(
                    "PhB",
                    lambda: self.n_ph_bg,
                    label_text="#Ph<sub>B</sub>",
                    decimals=0,
                    description="Estimated number of background photons in the TCSPC trace.",
                ),
            )
        )
        rows.append(
            self._row(
                "PhF",
                lambda: OutputRow(
                    "PhF",
                    lambda: self.n_ph_fl,
                    label_text="#Ph<sub>F</sub>",
                    decimals=0,
                    description="Estimated number of fluorescence photons (after background subtraction).",
                ),
            )
        )
        return rows

    def visible_parameters(self) -> list:
        return self.parameters_all


class Corrections(_Group):
    """DNL linearization and pile-up."""

    def __init__(self, view):
        super().__init__(view, "Corrections")
        self._curve = None
        self._dnl = False

    @property
    def lintable(self):
        return self._curve

    @lintable.setter
    def lintable(self, curve) -> None:
        self._curve = curve
        self._dnl = curve is not None
        self._apply()

    def unload_lintable(self) -> None:
        self._curve = None
        self._dnl = False
        self._apply()

    @property
    def correct_dnl(self) -> bool:
        return bool(self._dnl and self._curve is not None)

    @correct_dnl.setter
    def correct_dnl(self, value: bool) -> None:
        self._dnl = bool(value)
        self._apply()

    def _apply(self) -> None:
        if self.correct_dnl:
            self._view.set_dataset("linearization", self._curve)
        elif self._view.has_dataset("linearization"):
            self._view.unset_dataset("linearization")

    @property
    def window_function(self) -> str:
        index = int(self._get("lin_window", 1.0))
        return _WINDOWS[index] if 0 <= index < len(_WINDOWS) else "hanning"

    @window_function.setter
    def window_function(self, value: str) -> None:
        if str(value) in _WINDOWS:
            self._set("lin_window", float(_WINDOWS.index(str(value))))

    @property
    def correct_pile_up(self) -> bool:
        return bool(self._get("pile_up", 0.0))

    @correct_pile_up.setter
    def correct_pile_up(self, value: bool) -> None:
        self._set("pile_up", 1.0 if value else 0.0)

    @property
    def reverse(self) -> bool:
        return bool(self._get("reverse_linearization", 0.0))

    @reverse.setter
    def reverse(self, value: bool) -> None:
        self._set("reverse_linearization", 1.0 if value else 0.0)

    @property
    def parameters_all(self) -> list:
        rows = []
        if self._has("dead_time"):
            rows.append(
                self._row(
                    "tDead",
                    lambda: ScalarRow(
                        "tDead",
                        lambda: self._get("dead_time", 0.0),
                        lambda v: self._set("dead_time", v),
                        decimals=1,
                        description="Dead time of the TCSPC detector (ns), used for pile-up correction.",
                    ),
                )
            )
        if self._has("lin_window_length"):
            rows.append(
                self._row(
                    "win-size",
                    lambda: ScalarRow(
                        "win-size",
                        lambda: self._get("lin_window_length", 17.0),
                        lambda v: self._set("lin_window_length", round(v)),
                        decimals=0,
                        description="Window length of the linearization smoothing (channels).",
                    ),
                )
            )
        return rows

    def visible_parameters(self) -> list:
        return self.parameters_all


class Components(_Group):
    """A lifetime list (or any per-component group) with add/del, as the classic editor had it."""

    def __init__(self, view, key: str, name: str):
        super().__init__(view, name)
        self.key = key

    @property
    def absolute_amplitudes(self) -> bool:
        return bool(self._get("absolute_amplitudes", 1.0))

    @absolute_amplitudes.setter
    def absolute_amplitudes(self, value: bool) -> None:
        self._set("absolute_amplitudes", 1.0 if value else 0.0)

    @property
    def normalize_amplitudes(self) -> bool:
        return bool(self._get("normalize_amplitudes", 1.0))

    @normalize_amplitudes.setter
    def normalize_amplitudes(self, value: bool) -> None:
        self._set("normalize_amplitudes", 1.0 if value else 0.0)

    def _group(self):
        return next((g for g in self._view._groups.values() if g.key == self.key), None)

    def _lifetime_parameter_rows(self) -> list:
        group = self._group()
        return group.component_parameters() if group is not None else []

    _gaussian_parameter_rows = _lifetime_parameter_rows
    _distance_parameter_rows = _lifetime_parameter_rows

    @property
    def parameters_all(self) -> list:
        return self._lifetime_parameter_rows()

    def visible_parameters(self) -> list:
        return self.parameters_all

    @property
    def _amplitudes(self) -> list:
        return self._lifetime_parameter_rows()[0::2]

    @property
    def _lifetimes(self) -> list:
        return self._lifetime_parameter_rows()[1::2]

    @property
    def link(self):
        return None

    @link.setter
    def link(self, other) -> None:
        """Follow *other*'s components: the i-th amplitude and lifetime of each."""
        for mine, theirs in zip(self.parameters_all, getattr(other, "parameters_all", [])):
            mine.link = theirs

    def append(self, *args, **kwargs) -> None:
        self._view.change_components(self.key, +1)

    append_gaussian = append
    append_distance = append

    def pop(self, index: typing.Optional[int] = None) -> None:
        self._view.remove_component(self.key, index)


class Gaussians(Components):
    """Gaussian distances, and whether they are the distance between two gaussian clouds."""

    @property
    def is_distance_between_gaussians(self) -> bool:
        return bool(self._get("distance_between_gaussians", 0.0))

    @is_distance_between_gaussians.setter
    def is_distance_between_gaussians(self, value: bool) -> None:
        self._set("distance_between_gaussians", 1.0 if value else 0.0)


class Anisotropy(_Group):
    """Polarization, r0 / g / l1 / l2, and the rotational correlation times."""

    def __init__(self, view):
        super().__init__(view, "Anisotropy")

    def _groups(self):
        groups = {g.key: g for g in self._view._groups.values()}
        return groups.get("anisotropy"), groups.get("rotations")

    @property
    def polarization_type(self) -> str:
        index = int(self._get("polarization", 0.0))
        return _POLARIZATIONS[index] if 0 <= index < len(_POLARIZATIONS) else "vm"

    @polarization_type.setter
    def polarization_type(self, value: str) -> None:
        value = str(value).lower()
        if value in _POLARIZATIONS:
            self._set("polarization", float(_POLARIZATIONS.index(value)))

    def _rotation_parameters(self) -> list:
        _, rotations = self._groups()
        return rotations.component_parameters() if rotations is not None else []

    _rotation_parameter_rows = _rotation_parameters

    @property
    def parameters_all(self) -> list:
        static, _ = self._groups()
        return (
            static.visible_parameters() if static is not None else []
        ) + self._rotation_parameters()

    def visible_parameters(self) -> list:
        return self.parameters_all

    def add_rotation(self, *args, **kwargs) -> None:
        self._view.change_components("rotations", +1)

    def remove_rotation(self, index: typing.Optional[int] = None) -> None:
        self._view.remove_component("rotations", index)

    # The r(t) window: the BFF group answers it.
    def __getattr__(self, name: str):
        if name in (
            "_extract_vv_vh_raw_for_diag",
            "_extract_vv_vh_model_for_diag",
            "_shift_trace_to_reference",
            "rt_from_channels",
        ):
            static, _ = self._groups()
            if static is not None:
                return getattr(static, name)
        raise AttributeError(name)


class FRETParameters(_Group):
    """tau0, R0, kappa2, the donor-only fraction, and the FRET efficiency."""

    def __init__(self, view):
        super().__init__(view, "FRET parameters")

    def _parameter(self, canonical: str):
        found = self._parameters([canonical])
        return found[0] if found else None

    @property
    def kappa2(self) -> float:
        p = self._parameter("fret.kappa2")
        return float(p.value) if p is not None else 2.0 / 3.0

    @kappa2.setter
    def kappa2(self, value: float) -> None:
        p = self._parameter("fret.kappa2")
        if p is not None:
            p.value = float(value)

    @property
    def _kappa2(self):
        return self._parameter("fret.kappa2")

    @property
    def parameters_all(self) -> list:
        rows = self._parameters(["fret.tau0", "fret.forster_radius", "fret.kappa2", "fret.x_donly"])
        if "fret_efficiency" in self._view.presentation.get("statistics", {}):
            rows.append(
                self._row(
                    "E_FRET",
                    lambda: OutputRow(
                        "E_FRET",
                        lambda: self._view._presented_number("fret_efficiency"),
                        label_text="E<sub>FRET</sub>",
                        description="Mean FRET efficiency of the model.",
                    ),
                )
            )
        return rows

    def visible_parameters(self) -> list:
        return self.parameters_all


class OrientationParameter:
    """The kappa2 averaging regime the classic kappa2 controls switch."""

    def __init__(self, view):
        self._view = view
        self.orientation_spectrum = None

    @property
    def mode(self) -> str:
        if "static_orientation" not in self._view.scalar_names():
            return "fast"
        return "slow" if (self._view.get_scalar("static_orientation") or 0.0) else "fast"

    @mode.setter
    def mode(self, value: str) -> None:
        if "static_orientation" in self._view.scalar_names():
            self._view.set_scalar("static_orientation", 1.0 if str(value) == "slow" else 0.0)


class PDDEMGroup(_Group):
    """The per-fluorophore A/B quantities, one row per quantity."""

    _PAIRS = (
        ("pddem.f_ab", "pddem.f_ba"),
        ("pddem.pure_a", "pddem.pure_b"),
        ("pddem.excitation_a", "pddem.excitation_b"),
        ("pddem.emission_a", "pddem.emission_b"),
    )

    def __init__(self, view):
        super().__init__(view, "PDDEM")

    def _pddem_parameter_rows(self) -> list:
        rows = []
        for a, b in self._PAIRS:
            rows += self._parameters([a, b])
        reports = self._view.presentation.get("reports", {})
        for key in ("alpha_a", "alpha_b"):
            if key in reports:
                rows.append(
                    self._row(
                        key,
                        lambda key=key: OutputRow(
                            key,
                            lambda: self._view._presented_number(key),
                            description="Energy transfer efficiency of the fluorophore.",
                        ),
                    )
                )
        return rows

    @property
    def parameters_all(self) -> list:
        return self._pddem_parameter_rows()

    def visible_parameters(self) -> list:
        return self.parameters_all


class ClassicTCSPCEditor:
    """Mixed into a TCSPC family's view class: the groups the classic editor addresses."""

    def _classic(self, key: str, factory):
        groups = self.__dict__.setdefault("_classic_groups", {})
        group = groups.get(key)
        if group is None:
            group = factory()
            groups[key] = group
        return group

    def _component_key(self, *candidates: str) -> str:
        keys = [g.key for g in self.__dict__.get("_groups", {}).values()]
        document_groups = {
            entry.get("group") for entry in self._document.get("parameters", {}).values()
        }
        for candidate in candidates:
            if candidate in keys or candidate in document_groups:
                return candidate
        return candidates[0]

    @property
    def convolve(self) -> Convolve:
        return self._classic("convolve", lambda: Convolve(self))

    @property
    def generic(self) -> Generic:
        return self._classic("generic", lambda: Generic(self))

    @property
    def corrections(self) -> Corrections:
        return self._classic("corrections", lambda: Corrections(self))

    @property
    def lifetimes(self) -> Components:
        key = self._component_key("lifetimes", "donor")
        return self._classic("lifetimes", lambda: Components(self, key, "Lifetimes"))

    @property
    def fa(self) -> Components:
        return self._classic("fa", lambda: Components(self, "chromophore_a", "Fluorophore A"))

    @property
    def fb(self) -> Components:
        return self._classic("fb", lambda: Components(self, "donor", "Fluorophore B"))

    @property
    def anisotropy(self) -> Anisotropy:
        return self._classic("anisotropy", lambda: Anisotropy(self))

    @property
    def fret_parameters(self) -> FRETParameters:
        return self._classic("fret_parameters", lambda: FRETParameters(self))

    @property
    def orientation_parameter(self) -> OrientationParameter:
        return self._classic("orientation", lambda: OrientationParameter(self))

    @property
    def gaussians(self) -> Gaussians:
        return self._classic(
            "gaussians", lambda: Gaussians(self, "distances", "Gaussian distances")
        )

    @property
    def fret_rates(self) -> Components:
        return self._classic(
            "fret_rates", lambda: Components(self, "distances", "Discrete distances")
        )

    @property
    def pddem(self) -> PDDEMGroup:
        return self._classic("pddem", lambda: PDDEMGroup(self))

    @property
    def use_dye_linker(self) -> bool:
        return (
            bool(self.get_scalar("dye_linker") or 0.0)
            if "dye_linker" in self.scalar_names()
            else False
        )

    @use_dye_linker.setter
    def use_dye_linker(self, value: bool) -> None:
        if "dye_linker" in self.scalar_names():
            self.set_scalar("dye_linker", 1.0 if value else 0.0)

    # -- distributions as the classic distribution plot reads them -----------
    @property
    def distance_distribution(self) -> np.ndarray:
        """``[[[p...], [R_DA...]]]``: BFF presents the pairs interleaved."""
        flat = np.asarray(self.presented_distribution("distance_distribution"), dtype=float)
        if flat.size < 2:
            return np.zeros((1, 2, 0))
        return np.array([[flat[0::2], flat[1::2]]])

    @property
    def fret_rate_spectrum(self) -> np.ndarray:
        """Interleaved ``(p, k_FRET)``: each distance as its transfer rate."""
        distribution = self.distance_distribution
        if distribution.shape[-1] == 0:
            return np.zeros(0)
        p, r = distribution[0]
        values = {
            q.canonical_id: float(q.value)
            for q in self.parameters_all
            if hasattr(q, "canonical_id")
        }
        tau0 = values.get("fret.tau0", 4.0)
        r0 = values.get("fret.forster_radius", 52.0)
        kappa2 = values.get("fret.kappa2", 2.0 / 3.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            k = (kappa2 / (2.0 / 3.0)) * (r0 / r) ** 6 / tau0
        keep = np.isfinite(k) & (p > 0)
        spectrum = np.empty(2 * int(keep.sum()))
        spectrum[0::2], spectrum[1::2] = p[keep], k[keep]
        return spectrum

    def _chain_parameter_rows(self) -> list:
        return self._model_group_rows("chain")

    def _mem_parameter_rows(self) -> list:
        return self._model_group_rows("maxent")

    def _model_group_rows(self, key: str) -> list:
        group = next((g for g in self.__dict__.get("_groups", {}).values() if g.key == key), None)
        return group.visible_parameters() if group is not None else []
