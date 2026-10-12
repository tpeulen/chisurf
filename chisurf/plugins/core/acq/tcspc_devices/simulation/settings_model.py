"""Qt-free simulation settings model shared by the Qt and emtk setup dialogs.

The model is the one place that knows how the editable simulator settings map onto the
``simulation_params`` dictionary the engine consumes (:meth:`SimulationSettingsModel.to_parameters`)
and back (:meth:`SimulationSettingsModel.from_parameters`). The Qt AutoForm dialog
(:mod:`.setup_dialog`) and the emtk dialog (``chisurf.plugins.core.acq.gui.sim_setup``) both edit
this model, so they cannot disagree about what a value means.
"""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, field
from typing import Any


@functools.lru_cache(maxsize=1)
def _schema_help() -> dict:
    """Per-parameter help from the acq plugin ``manifest.json`` params_schema.

    Single source of truth for the parameter tooltips — the same text the RPC
    method (``acq.simulation.run``) and CLI document — so the GUI never
    duplicates it.
    """
    plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    try:
        with open(os.path.join(plugin_dir, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        for method in manifest.get("rpc_methods", []):
            if method.get("name") == "acq.simulation.run":
                props = method.get("params_schema", {}).get("properties", {})
                return {k: str(v.get("description", "")) for k, v in props.items()}
    except Exception:
        pass
    return {}


def _help(schema_key: str) -> str:
    """Shared tooltip text for a ``params_schema`` key (``''`` if absent)."""
    return _schema_help().get(schema_key, "")


def load_channel_settings():
    """Load detector channel conversion settings.

    Returns
    -------
    dict
        Channel conversion settings with a default six-channel mapping.
    """
    plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    settings_file = os.path.join(plugin_dir, "channel_settings.json")
    default_settings = {
        "channel_conversion": {
            "default": [8, 0, 9, 1, 10, 2, 11, 3, 12, 4, 13, 5],
            "green_p": 0,
            "green_s": 1,
            "red_p": 2,
            "red_s": 3,
            "yellow_p": 4,
            "yellow_s": 5,
        },
        "detector_channels": {
            "green_p": 8,
            "green_s": 9,
            "red_p": 10,
            "red_s": 11,
            "yellow_p": 12,
            "yellow_s": 13,
        },
    }
    try:
        if os.path.exists(settings_file):
            with open(settings_file, encoding="utf-8") as handle:
                return json.load(handle)
        with open(settings_file, "w", encoding="utf-8") as handle:
            json.dump(default_settings, handle, indent=2)
    except Exception:
        pass
    return default_settings


def _flatten(values: Any) -> list[float]:
    """Flatten nested numeric settings.

    Parameters
    ----------
    values : object
        Scalar, nested sequence, or NumPy-like value.

    Returns
    -------
    list of float
        Flat numeric list.
    """
    if values is None:
        return []
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, (list, tuple)):
        out = []
        for item in values:
            out.extend(_flatten(item))
        return out
    return [float(values)]


def _list_get(values: list[float], index: int, default: float) -> float:
    """Return a list value with a fallback.

    Parameters
    ----------
    values : list of float
        Source values.
    index : int
        Desired index.
    default : float
        Fallback value.

    Returns
    -------
    float
        Selected or fallback value.
    """
    return float(values[index]) if index < len(values) else float(default)


def _sized_matrix(values: Any, n: int) -> list[float]:
    """Return a flat ``n*n`` matrix, padding/truncating ``values``.

    Parameters
    ----------
    values : Any
        Flat row-major rate matrix as stored on the model: ``rate[i*n + j]`` is
        the i→j rate, which is what the shared rate-matrix editor writes and
        what the photon simulator reads. (A transpose used to sit here, from
        when the editor stored ``K[target, source]``; once the editor moved to
        i→j it reversed every rate.)
    n : int
        Number of states.
    """
    flat = [float(v) for v in (values or [])]
    out = [0.0] * (n * n)
    for i in range(min(len(flat), n * n)):
        out[i] = flat[i]
    return out


def _expand_species_q(
    params: dict, n_species: int, enabled: tuple[bool, bool, bool]
) -> list[float]:
    """Expand a legacy flat ``q`` (species × enabled-channels) into species×6 slots."""
    q = _flatten(params.get("q", [50.0, 50.0]))
    slots: list[int] = []
    for ci, on in enumerate(enabled):
        if on:
            slots += [ci * 2, ci * 2 + 1]
    if not slots:
        slots = [0, 1]
    n_ch = len(slots)
    out = [0.0] * (n_species * 6)
    for s in range(n_species):
        for k, slot in enumerate(slots):
            idx = s * n_ch + k
            if idx < len(q):
                out[s * 6 + slot] = float(q[idx])
    return out


@dataclass
class SimulationSettingsModel:
    """AutoForm view model for tttrlib photon simulation settings."""

    n_species: int = 1
    molecules: float = 50.0
    diffusion: float = 3.0
    excitation_mode: str = "CW"
    green_enabled: bool = True
    red_enabled: bool = False
    yellow_enabled: bool = False
    bg_green_p: float = 0.001
    bg_green_s: float = 0.001
    bg_red_p: float = 0.001
    bg_red_s: float = 0.001
    bg_yellow_p: float = 0.001
    bg_yellow_s: float = 0.001
    box_xy: float = 2.0
    box_z: float = 4.0
    focus_w0: float = 0.3
    focus_z0: float = 2.0
    dt: float = 0.01
    n_ph_max: int = 1_000_000
    n_ph_per_file: int = 100_000
    output_path: str = ""
    n_tac_channels: int = 4096
    tac_dt: float = 0.004069
    laser_period: float = 13.596
    seed_diffusion: int = 12345
    seed_emission: int = 54321
    # --- throughput / performance knobs (native tttrlib Sim* engine; see manifest) ---
    max_windows: int = 0
    analytic_excitation: bool = False
    per_molecule_skip: bool = False
    fast_grid_bbox: bool = False
    independent_molecules: bool = False
    active_margin: float = 0.0
    coast_safety: float = 3.0
    min_coast_windows: int = 8
    focus_threshold: float = 0.001
    # --- point-spread / focus model (see manifest params_schema) ---
    psf_type: str = "gaussian3d"
    psf_zR: float = 1.0
    psf_file: str = ""
    psf_r_step: float = 0.05
    psf_z_step: float = 0.05
    # --- per-species fluorescence decay (edited in the modal Decay dialog) ---
    #: One lifetime spectrum per species: a list of [amplitude, lifetime_ns] pairs.
    decay_lifetimes: list = field(default_factory=lambda: [[[1.0, 3.2]]])
    #: One measured/saved decay-pattern file path per species ("" = use lifetimes).
    decay_pattern_files: list = field(default_factory=lambda: [""])
    #: Shared Gaussian IRF FWHM (ns); 0 = no IRF convolution.
    irf_fwhm_ns: float = 0.0
    #: Flat row-major N×N radiative / non-radiative species-interconversion rates.
    k_rad: list = field(default_factory=lambda: [0.0])
    k_nrad: list = field(default_factory=lambda: [0.0])
    #: Per-species molecules / diffusion (one entry per species).
    species_M: list = field(default_factory=lambda: [50.0])
    species_D: list = field(default_factory=lambda: [3.0])
    #: Per-species brightness q, flattened species×6 (G∥,G⊥,R∥,R⊥,Y∥,Y⊥ per species).
    species_q: list = field(default_factory=lambda: [50.0, 50.0, 0.0, 0.0, 0.0, 0.0])

    #: Detection colours, in the order their brightness slots are stored.
    _CHANNEL_COLORS = ("green", "red", "yellow")
    _CHANNEL_ABBR = {"green": "G", "red": "R", "yellow": "Y"}

    def enabled_colors(self) -> list:
        """Return the enabled detection colours, green as the fallback."""
        return [c for c in self._CHANNEL_COLORS if getattr(self, f"{c}_enabled", False)] or [
            "green"
        ]

    @classmethod
    def from_parameters(cls, params: dict[str, Any] | None):
        """Create a model from legacy acquisition simulation parameters.

        Parameters
        ----------
        params : dict, optional
            Existing ``simulation_params`` dictionary.

        Returns
        -------
        SimulationSettingsModel
            Populated view model.
        """
        params = dict(params or {})
        q = _flatten(params.get("q", [50.0, 50.0]))
        q_bg = _flatten(params.get("q_bg", [0.001, 0.001]))
        focus = _flatten(params.get("focus_param", [0.3, 2.0]))
        molecules = _flatten(params.get("M", [50.0]))
        diffusion = _flatten(params.get("D", [3.0]))
        n_channels = int(params.get("N_channels", max(2, min(6, len(q) or 2))))
        red_enabled = bool(params.get("red_enabled", n_channels >= 4))
        yellow_enabled = bool(params.get("yellow_enabled", n_channels >= 6))
        green_enabled = bool(params.get("green_enabled", True))
        if not (green_enabled or red_enabled or yellow_enabled):
            green_enabled = True
        excitation_mode = params.get(
            "excitation_mode",
            "Pulsed" if params.get("pulsed_exc") else "CW",
        )
        n_ph_per_file = params.get(
            "N_ph_per_file",
            params.get("photons_per_file", 100_000),
        )
        return cls(
            n_species=max(1, int(params.get("N_species", 1))),
            molecules=_list_get(molecules, 0, 50.0),
            diffusion=_list_get(diffusion, 0, 3.0),
            excitation_mode=str(excitation_mode),
            green_enabled=green_enabled,
            red_enabled=red_enabled,
            yellow_enabled=yellow_enabled,
            bg_green_p=_list_get(q_bg, 0, 0.001),
            bg_green_s=_list_get(q_bg, 1, 0.001),
            bg_red_p=_list_get(q_bg, 2, 0.001),
            bg_red_s=_list_get(q_bg, 3, 0.001),
            bg_yellow_p=_list_get(q_bg, 4, 0.001),
            bg_yellow_s=_list_get(q_bg, 5, 0.001),
            box_xy=float(params.get("box_xy", 2.0)),
            box_z=float(params.get("box_z", 4.0)),
            focus_w0=_list_get(focus, 0, 0.3),
            focus_z0=_list_get(focus, 1, 2.0),
            dt=float(params.get("dt", params.get("tw", 0.01))),
            n_ph_max=max(1, int(params.get("N_ph_max", 1_000_000))),
            n_ph_per_file=max(1, int(n_ph_per_file)),
            output_path=str(params.get("spc_output_path", "")),
            n_tac_channels=max(1, int(params.get("N_tac_channels", 4096))),
            tac_dt=float(params.get("tac_dt", 0.004069)),
            laser_period=float(params.get("laser_period", 13.596)),
            seed_diffusion=int(params.get("rmt1seed", params.get("seed_diffusion", 12345))),
            seed_emission=int(params.get("rmt2seed", params.get("seed_emission", 54321))),
            max_windows=int(params.get("max_windows", 0)),
            analytic_excitation=bool(params.get("analytic_excitation", False)),
            per_molecule_skip=bool(params.get("per_molecule_skip", False)),
            fast_grid_bbox=bool(params.get("fast_grid_bbox", False)),
            independent_molecules=bool(params.get("independent_molecules", False)),
            active_margin=float(params.get("active_margin", 0.0)),
            coast_safety=float(params.get("coast_safety", 3.0)),
            min_coast_windows=int(params.get("min_coast_windows", 8)),
            focus_threshold=float(params.get("focus_threshold", 0.001)),
            psf_type=str(params.get("psf_type", "gaussian3d")),
            psf_zR=float(params.get("psf_zR", 1.0)),
            psf_file=str(params.get("psf_file", "")),
            psf_r_step=float(params.get("psf_r_step", 0.05)),
            psf_z_step=float(params.get("psf_z_step", 0.05)),
            decay_lifetimes=(
                [list(s) for s in params["decay_lifetimes"]]
                if params.get("decay_lifetimes")
                else [[3.2]]
            ),
            decay_pattern_files=(
                [str(p or "") for p in params["decay_pattern_files"]]
                if params.get("decay_pattern_files")
                else [""]
            ),
            irf_fwhm_ns=float(params.get("irf_fwhm_ns", 0.0)),
            k_rad=[float(v) for v in params["k_rad"]] if params.get("k_rad") else [0.0],
            k_nrad=[float(v) for v in params["k_nrad"]] if params.get("k_nrad") else [0.0],
            species_M=(
                [float(v) for v in params["species_M"]]
                if params.get("species_M")
                else [
                    _list_get(molecules, s, 50.0)
                    for s in range(max(1, int(params.get("N_species", 1))))
                ]
            ),
            species_D=(
                [float(v) for v in params["species_D"]]
                if params.get("species_D")
                else [
                    _list_get(diffusion, s, 3.0)
                    for s in range(max(1, int(params.get("N_species", 1))))
                ]
            ),
            species_q=(
                [float(v) for v in params["species_q"]]
                if params.get("species_q")
                else _expand_species_q(
                    params,
                    max(1, int(params.get("N_species", 1))),
                    (green_enabled, red_enabled, yellow_enabled),
                )
            ),
        )

    def _enabled_channel_layout(self) -> tuple[list[float], list[int]]:
        """Return the background rates and detector mapping of the enabled channels.

        Brightness is deliberately **not** returned. It is per species and lives
        in :attr:`species_q` (six slots per species); this method used to build a
        parallel ``q`` from single-species ``q_green_p``-style fields, which
        :meth:`to_parameters` then discarded. Those fields have been removed:
        setting one looked like it configured the simulation and did nothing at
        all.

        Returns
        -------
        tuple
            ``(q_bg, ch_conversion)`` for the enabled colour channels.
        """
        if not (self.green_enabled or self.red_enabled or self.yellow_enabled):
            self.green_enabled = True
        q_bg = []
        ch_conversion = []
        next_source = 0
        for enabled, bg_values, detectors in (
            (self.green_enabled, (self.bg_green_p, self.bg_green_s), (8, 9)),
            (self.red_enabled, (self.bg_red_p, self.bg_red_s), (10, 11)),
            (self.yellow_enabled, (self.bg_yellow_p, self.bg_yellow_s), (12, 13)),
        ):
            if not enabled:
                continue
            for bg_value, detector in zip(bg_values, detectors):
                q_bg.append(float(bg_value))
                ch_conversion.extend([int(detector), int(next_source)])
                next_source += 1
        return q_bg, ch_conversion

    def to_parameters(self) -> dict[str, Any]:
        """Serialize the view model to acquisition ``simulation_params``.

        Returns
        -------
        dict
            Parameters consumed by ``SimulationDevice`` and the tttrlib backend.
        """
        q_bg, ch_conversion = self._enabled_channel_layout()
        n_channels = len(q_bg)
        n_species = max(1, int(self.n_species))
        # Per-species brightness from the 6-slot store (G∥,G⊥,R∥,R⊥,Y∥,Y⊥),
        # filtered to the enabled channels.
        enabled_slots: list[int] = []
        for ci, color in enumerate(("green", "red", "yellow")):
            if getattr(self, f"{color}_enabled", False):
                enabled_slots += [ci * 2, ci * 2 + 1]
        if not enabled_slots:
            enabled_slots = [0, 1]
        q = [
            float(self.species_q[s * 6 + slot]) if s * 6 + slot < len(self.species_q) else 0.0
            for s in range(n_species)
            for slot in enabled_slots
        ]
        molecules = [
            float(self.species_M[s]) if s < len(self.species_M) else 50.0 for s in range(n_species)
        ]
        diffusion = [
            float(self.species_D[s]) if s < len(self.species_D) else 3.0 for s in range(n_species)
        ]
        # Size the per-species decay definitions to the species count.
        lifetimes = list(self.decay_lifetimes or [[[1.0, 3.2]]])
        pattern_files = list(self.decay_pattern_files or [""])
        decay_lifetimes = [list(lifetimes[i % len(lifetimes)]) for i in range(n_species)]
        decay_pattern_files = [
            str(pattern_files[i]) if i < len(pattern_files) else "" for i in range(n_species)
        ]
        return {
            "decay_lifetimes": decay_lifetimes,
            "decay_pattern_files": decay_pattern_files,
            "irf_fwhm_ns": float(self.irf_fwhm_ns),
            "species_M": molecules,
            "species_D": diffusion,
            "species_q": list(self.species_q),
            "N_species": n_species,
            "M": molecules,
            "D": diffusion,
            "N_channels": n_channels,
            "q": q,
            "q_bg": q_bg,
            "k_rad": _sized_matrix(self.k_rad, n_species),
            "k_nrad": _sized_matrix(self.k_nrad, n_species),
            "box_xy": float(self.box_xy),
            "box_z": float(self.box_z),
            "focus_type": 0,
            "focus_param": [float(self.focus_w0), float(self.focus_z0)],
            "dt": float(self.dt),
            "tw": float(self.dt),
            "N_ph_max": max(1, int(self.n_ph_max)),
            "N_ph_per_file": max(1, int(self.n_ph_per_file)),
            "spc_output_path": str(self.output_path or ""),
            "pulsed_exc": 1 if self.excitation_mode == "Pulsed" else 0,
            "excitation_mode": str(self.excitation_mode),
            "ch_conversion": ch_conversion,
            "N_tac_channels": max(1, int(self.n_tac_channels)),
            "tac_dt": float(self.tac_dt),
            "laser_period": float(self.laser_period),
            "rmt1seed": int(self.seed_diffusion),
            "rmt2seed": int(self.seed_emission),
            "green_enabled": bool(self.green_enabled),
            "red_enabled": bool(self.red_enabled),
            "yellow_enabled": bool(self.yellow_enabled),
            "max_windows": int(self.max_windows),
            "analytic_excitation": bool(self.analytic_excitation),
            "per_molecule_skip": bool(self.per_molecule_skip),
            "fast_grid_bbox": bool(self.fast_grid_bbox),
            "independent_molecules": bool(self.independent_molecules),
            "active_margin": float(self.active_margin),
            "coast_safety": float(self.coast_safety),
            "min_coast_windows": int(self.min_coast_windows),
            "focus_threshold": float(self.focus_threshold),
            "psf_type": str(self.psf_type),
            "psf_zR": float(self.psf_zR),
            "psf_file": str(self.psf_file or ""),
            "psf_r_step": float(self.psf_r_step),
            "psf_z_step": float(self.psf_z_step),
        }

    def apply_parameters(self, params: dict[str, Any]) -> None:
        """Apply a parameter dictionary to this model.

        Parameters
        ----------
        params : dict
            Parameter dictionary to load.
        """
        fresh = self.from_parameters(params)
        self.__dict__.update(fresh.__dict__)
