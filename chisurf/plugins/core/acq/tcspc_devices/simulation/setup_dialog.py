"""AutoForm setup dialog for the tttrlib acquisition photon simulator."""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, field
from typing import Any

from qtpy import QtWidgets

from chisurf.core import dataspec as ds
from chisurf.gui.autoform import AutoForm, register_section
from chisurf.gui.glyphs import Glyphs
from chisurf.gui import dialogs


@register_section("acq_channels")
class _ChannelSwitches(QtWidgets.QWidget):
    """Which detection colours exist, as a row of checkboxes.

    Only the switches: the per-species grid they size is the general
    ``state_table`` section, which reads its columns back from
    :meth:`SimulationSettingsModel.species_columns`. Toggling a colour here
    therefore adds or removes two columns there without either side knowing
    about the other.
    """

    AUTOFORM_REFRESH = True
    is_form_field = False
    _COLORS = ("green", "red", "yellow")

    def __init__(self, model, target: str = "", **options):
        """Build one checkbox per detection colour."""
        super().__init__()
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Channels:"))
        self._checks: dict[str, QtWidgets.QCheckBox] = {}
        for color in self._COLORS:
            box = QtWidgets.QCheckBox(color.capitalize())
            box.setChecked(bool(getattr(self._model, f"{color}_enabled", False)))
            box.setToolTip(f"Enable the {color} detection channel (parallel + perpendicular).")
            box.toggled.connect(lambda v, c=color: self._toggle(c, v))
            self._checks[color] = box
            layout.addWidget(box)
        layout.addStretch(1)

    def _toggle(self, color: str, value: bool) -> None:
        """Enable or disable a colour and let the hosting form re-read."""
        setattr(self._model, f"{color}_enabled", bool(value))
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, "refresh_plots") and hasattr(widget, "sync_fields"):
                widget.refresh_plots()
                return
            widget = widget.parentWidget()

    def refresh(self) -> None:
        """Re-read the enabled colours from the model."""
        for color, box in self._checks.items():
            box.blockSignals(True)
            box.setChecked(bool(getattr(self._model, f"{color}_enabled", False)))
            box.blockSignals(False)


@functools.lru_cache(maxsize=1)
def _schema_help() -> dict:
    """Per-parameter help from the acq plugin ``manifest.json`` params_schema.

    Single source of truth for the parameter tooltips — the same text the RPC
    method (``acq.simulation.run``) and CLI document — so the GUI never
    duplicates it.
    """
    plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    try:
        with open(os.path.join(plugin_dir, "manifest.json"), "r", encoding="utf-8") as f:
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


def _sized_matrix(values: Any, n: int, *, transpose: bool = False) -> list[float]:
    """Return a flat ``n*n`` matrix, padding/truncating ``values``.

    Parameters
    ----------
    values : Any
        Flat rate matrix as stored on the model.
    n : int
        Number of states.
    transpose : bool
        Swap the index convention. The shared rate-matrix editor writes
        ``K[target, source]`` — chisurf's kinetics convention — while the
        photon simulator takes a **row-major i→j** matrix. Feeding one to the
        other transposes every rate: a two-state blinker keeps its two numbers
        and swaps which way they run, so the simulation is wrong in a way that
        still looks like a simulation. The transpose happens here, once, at the
        boundary between the two conventions.
    """
    flat = [float(v) for v in (values or [])]
    out = [0.0] * (n * n)
    for i in range(min(len(flat), n * n)):
        out[i] = flat[i]
    if transpose:
        out = [out[j * n + i] for i in range(n) for j in range(n)]
    return out


def _expand_species_q(params: dict, n_species: int, enabled: tuple[bool, bool, bool]) -> list[float]:
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
        return [c for c in self._CHANNEL_COLORS
                if getattr(self, f"{c}_enabled", False)] or ["green"]

    def species_columns(self) -> list:
        """Return the per-species columns for the ``state_table`` section.

        Molecules and diffusion, then the parallel/perpendicular brightness of
        every enabled colour. ``species_q`` keeps six slots per species
        (three colours x two polarisations) whatever is enabled, so switching a
        colour on does not renumber the ones already set — the column simply
        addresses its slot.
        """
        columns = [
            {"attr": "species_M", "label": "M", "default": 50.0,
             "description": "Molecules (mean number in the box) for this species."},
            {"attr": "species_D", "label": "D", "default": 3.0,
             "description": "Diffusion coefficient (\u00b5m\u00b2/ms) for this species."},
        ]
        for color in self.enabled_colors():
            base = self._CHANNEL_COLORS.index(color) * 2
            for polarisation, mark in ((0, "\u2225"), (1, "\u22a5")):
                columns.append({
                    "attr": "species_q", "stride": 6, "slot": base + polarisation,
                    "label": f"{self._CHANNEL_ABBR[color]} {mark}",
                    "maximum": 1e6,
                    "description": f"{color.capitalize()} {'parallel' if polarisation == 0 else 'perpendicular'} brightness q.",
                })
        # The decay is a whole spectrum, not a number, so the row opens an
        # editor rather than holding a cell. Having it on the row removes the
        # "which species am I editing" selector the dialog used to carry.
        columns.append({
            "action": "open_decay_dialog", "label": "Decay", "text": "\u2026",
            "description": "Edit this species' lifetime spectrum, decay pattern and IRF.",
        })
        return columns

    def species_trailing_rows(self) -> list:
        """Return the background row shown beneath the species.

        Background is not a species — it has no molecules and no diffusion, so
        those cells are blank — but it is read in the same detection channels,
        which is why it belongs in the same grid rather than in fields
        elsewhere.
        """
        cells = [None, None]
        for color in self.enabled_colors():
            for suffix in ("p", "s"):
                cells.append({"attr": f"bg_{color}_{suffix}", "decimals": 6, "maximum": 1e6})
        return [{"label": "BG", "cells": cells}]

    def species_changed(self, _value=None) -> None:
        """Re-sync the form so the kinetics matrix tracks the species count."""
        for name in ("_sync_fields", "_refresh_widgets"):
            callback = getattr(self, name, None)
            if callable(callback):
                callback()

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
                if params.get("decay_lifetimes") else [[3.2]]
            ),
            decay_pattern_files=(
                [str(p or "") for p in params["decay_pattern_files"]]
                if params.get("decay_pattern_files") else [""]
            ),
            irf_fwhm_ns=float(params.get("irf_fwhm_ns", 0.0)),
            k_rad=[float(v) for v in params["k_rad"]] if params.get("k_rad") else [0.0],
            k_nrad=[float(v) for v in params["k_nrad"]] if params.get("k_nrad") else [0.0],
            species_M=(
                [float(v) for v in params["species_M"]] if params.get("species_M")
                else [_list_get(molecules, s, 50.0)
                      for s in range(max(1, int(params.get("N_species", 1))))]
            ),
            species_D=(
                [float(v) for v in params["species_D"]] if params.get("species_D")
                else [_list_get(diffusion, s, 3.0)
                      for s in range(max(1, int(params.get("N_species", 1))))]
            ),
            species_q=(
                [float(v) for v in params["species_q"]] if params.get("species_q")
                else _expand_species_q(
                    params, max(1, int(params.get("N_species", 1))),
                    (green_enabled, red_enabled, yellow_enabled),
                )
            ),
        )

    def view_spec(self):
        """Return the declarative AutoForm layout.

        Returns
        -------
        chisurf.core.dataspec.ModelView
            AutoForm section tree.
        """
        return ds.ModelView(
            sections=(
                ds.PanelSection(
                    title="Acquisition",
                    n_col=2,
                    sections=(
                        ds.ChoiceSection(
                            attr="excitation_mode",
                            label="Mode",
                            options=("CW", "Pulsed"),
                            style="combo",
                            description="Excitation mode: CW (continuous) or Pulsed (pulsed laser; enables the micro-time / TCSPC axis).",
                        ),
                        ds.ValueSection(
                            attr="n_ph_max",
                            label="Photons",
                            kind="int",
                            minimum=1,
                            maximum=2_000_000_000,
                            description=_help("N_ph_max"),
                        ),
                        ds.ValueSection(
                            attr="n_ph_per_file",
                            label="Photons/file",
                            kind="int",
                            minimum=1,
                            maximum=2_000_000_000,
                            description="Split the streamed SPC output into files of this many photons each.",
                        ),
                        ds.ValueSection(attr="output_path", label="Output folder", kind="str",
                            description="Folder where SPC/photon-stream files are written."),
                        ds.ValueSection(
                            attr="seed_diffusion",
                            label="Diffusion seed",
                            kind="int",
                            minimum=0,
                            description=_help("rmt1seed"),
                        ),
                        ds.ValueSection(
                            attr="seed_emission",
                            label="Emission seed",
                            description=_help("rmt2seed"),
                            kind="int",
                            minimum=0,
                        ),
                    ),
                ),
                ds.PanelSection(
                    title="Sample & brightness",
                    description="One row per species (grows with Species): molecules M, diffusion D, and per-channel ∥/⊥ brightness q. The last row is per-channel background.",
                    sections=(
                        ds.ValueSection(
                            attr="n_species",
                            label="Species",
                            kind="int",
                            minimum=1,
                            maximum=999,
                            call="species_changed",
                            description=_help("N_species"),
                        ),
                        ds.CustomSection(key="acq_channels"),
                        ds.CustomSection(
                            key="state_table",
                            options={"size_attr": "n_species",
                                     "columns_source": "species_columns",
                                     "trailing_rows_source": "species_trailing_rows"},
                        ),
                    ),
                ),
                ds.PanelSection(
                    title="Kinetics",
                    collapsed=True,
                    description="Species-interconversion transition rates (radiative and non-radiative). Each button opens an N×N grid that tracks the species count and says how many transitions are set.",
                    sections=(
                        ds.CustomSection(
                            key="rate_matrix", target="k_rad",
                            options={"size_attr": "n_species", "minimum": 0.0,
                                     "decimals": 4, "unit": "1/ms", "popup": True,
                                     "title": "Radiative (k_rad)"},
                        ),
                        ds.CustomSection(
                            key="rate_matrix", target="k_nrad",
                            options={"size_attr": "n_species", "minimum": 0.0,
                                     "decimals": 4, "unit": "1/ms", "popup": True,
                                     "title": "Non-radiative (k_nrad)"},
                        ),
                    ),
                ),
                ds.PanelSection(
                    title="Geometry",
                    n_col=2,
                    sections=(
                        self._float_field("box_xy", "Box XY", minimum=0.001, decimals=4,
                            description=_help("box_xy")),
                        self._float_field("box_z", "Box Z", minimum=0.001, decimals=4,
                            description=_help("box_z")),
                        self._float_field("focus_w0", "Focus w0", minimum=0.001, decimals=4,
                            description=_help("focus_param")),
                        self._float_field("focus_z0", "Focus z0", minimum=0.001, decimals=4,
                            description=_help("focus_param")),
                        self._float_field("dt", "Step", minimum=0.000001, decimals=6,
                            description=_help("dt")),
                    ),
                ),
                ds.PanelSection(
                    title="Microtime",
                    n_col=2,
                    sections=(
                        ds.ValueSection(
                            attr="n_tac_channels",
                            label="TAC channels",
                            kind="int",
                            minimum=1,
                            maximum=1_000_000,
                            description=_help("N_tac_channels"),
                        ),
                        self._float_field("tac_dt", "TAC dt", minimum=0.000001, decimals=6,
                            description=_help("tac_dt")),
                        self._float_field(
                            "laser_period",
                            "Laser period",
                            minimum=0.000001,
                            decimals=6,
                            description=_help("laser_period"),
                        ),
                    ),
                ),
                ds.PanelSection(
                    title="Performance",
                    n_col=2,
                    description="Optional throughput knobs (native tttrlib Sim* engine). Speed/accuracy trade-offs — see each tooltip. Defaults reproduce the exact fixed-step engine.",
                    sections=(
                        ds.ToggleSection(
                            attr="per_molecule_skip", label="Coasting",
                            description=_help("per_molecule_skip"),
                        ),
                        ds.ToggleSection(
                            attr="fast_grid_bbox", label="Two-step field lookup",
                            description=_help("fast_grid_bbox"),
                        ),
                        ds.ToggleSection(
                            attr="independent_molecules", label="Independent molecules",
                            description=_help("independent_molecules"),
                        ),
                        ds.ToggleSection(
                            attr="analytic_excitation", label="Analytic Gaussian focus",
                            description=_help("analytic_excitation"),
                        ),
                        ds.ChoiceSection(
                            attr="psf_type", label="PSF / focus model",
                            options=("gaussian3d", "analytic_gaussian3d",
                                     "gaussian_lorentzian", "radial"),
                            labels=("Gaussian 3D", "Analytic Gaussian",
                                    "Gaussian-Lorentzian", "Numeric (radial)"),
                            description=_help("psf_type"),
                        ),
                        self._float_field(
                            "psf_zR", "Rayleigh range zR (µm)", minimum=0.0, decimals=3,
                            description=_help("psf_zR"),
                        ),
                        ds.ValueSection(
                            attr="psf_file", label="PSF file (radial)", kind="string",
                            description=_help("psf_file"),
                        ),
                        self._float_field(
                            "psf_r_step", "PSF r step (µm)", minimum=0.0, decimals=4,
                            description=_help("psf_r_step"),
                        ),
                        self._float_field(
                            "psf_z_step", "PSF z step (µm)", minimum=0.0, decimals=4,
                            description=_help("psf_z_step"),
                        ),
                        self._float_field(
                            "active_margin", "Active margin (µm)", minimum=0.0, decimals=3,
                            description=_help("active_margin"),
                        ),
                        ds.ValueSection(
                            attr="max_windows", label="Max windows", kind="int", minimum=0,
                            maximum=2_000_000_000,
                            description=_help("max_windows"),
                        ),
                        self._float_field(
                            "coast_safety", "Coast safety", minimum=1.0, decimals=2,
                            description=_help("coast_safety"),
                        ),
                        ds.ValueSection(
                            attr="min_coast_windows", label="Min coast windows", kind="int",
                            minimum=1, maximum=1_000_000,
                            description=_help("min_coast_windows"),
                        ),
                        self._float_field(
                            "focus_threshold", "Focus threshold", minimum=0.0, decimals=6,
                            description=_help("focus_threshold"),
                        ),
                    ),
                ),
                ds.ButtonRowSection(
                    menu=f"{Glyphs.TOOLS} Tools",
                    buttons=(
                        {"label": f"{Glyphs.DNA} Decay…", "action": "open_decay_dialog",
                         "description": "Define the per-species fluorescence decay "
                                        "(lifetimes / IRF) or load an existing decay pattern."},
                        {"label": f"{Glyphs.OPEN} Load JSON", "action": "load_json",
                         "description": "Load simulation parameters from a JSON file."},
                        {"label": f"{Glyphs.SAVE} Save JSON", "action": "save_json",
                         "description": "Save the current simulation parameters to a JSON file."},
                        {"label": "🧾 View JSON", "action": "view_json",
                         "description": "Show the current simulation parameters as JSON."},
                    )
                ),
            )
        )

    @staticmethod
    def _float_field(
        attr: str,
        label: str,
        minimum: float = 0.0,
        maximum: float = 1_000_000.0,
        decimals: int = 4,
        description: str = "",
    ) -> ds.ValueSection:
        """Create a bounded float ``ValueSection``.

        Parameters
        ----------
        attr : str
            Bound model attribute.
        label : str
            Form label.
        minimum : float, optional
            Minimum accepted value.
        maximum : float, optional
            Maximum accepted value.
        decimals : int, optional
            Number of decimal places.

        Returns
        -------
        chisurf.core.dataspec.ValueSection
            Configured float field.
        """
        return ds.ValueSection(
            attr=attr,
            label=label,
            kind="float",
            minimum=minimum,
            maximum=maximum,
            decimals=decimals,
            description=description,
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
            float(self.species_M[s]) if s < len(self.species_M) else 50.0
            for s in range(n_species)
        ]
        diffusion = [
            float(self.species_D[s]) if s < len(self.species_D) else 3.0
            for s in range(n_species)
        ]
        # Size the per-species decay definitions to the species count.
        lifetimes = list(self.decay_lifetimes or [[[1.0, 3.2]]])
        pattern_files = list(self.decay_pattern_files or [""])
        decay_lifetimes = [
            list(lifetimes[i % len(lifetimes)]) for i in range(n_species)
        ]
        decay_pattern_files = [
            str(pattern_files[i]) if i < len(pattern_files) else ""
            for i in range(n_species)
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
            # The editor stores K[target, source]; the simulator wants i→j.
            "k_rad": _sized_matrix(self.k_rad, n_species, transpose=True),
            "k_nrad": _sized_matrix(self.k_nrad, n_species, transpose=True),
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

    def open_decay_dialog(self, species: int = 0) -> None:
        """Open the modal decay editor, starting at ``species``.

        Parameters
        ----------
        species : int
            Zero-based species index the editor opens on. The per-row button in
            the species table passes its own row; the Tools entry opens at the
            first species.
        """
        dialog = DecaySettingsDialog(self, start_species=species)
        if dialog.exec_():
            sync = getattr(self, "_sync_fields", None)
            if callable(sync):
                sync()

    def load_json(self) -> None:
        """Load simulation parameters from a JSON file selected by the user."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Load simulation JSON",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        with open(path, encoding="utf-8") as handle:
            self.apply_parameters(json.load(handle))
        sync = getattr(self, "_sync_fields", None)
        if callable(sync):
            sync()

    def save_json(self) -> None:
        """Save the current simulation parameters to a JSON file."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None,
            "Save simulation JSON",
            "simulation_config.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_parameters(), handle, indent=2)

    def view_json(self) -> None:
        """Show the current serialized parameter JSON."""
        dialogs.information(
            None,
            "Simulation Parameters",
            json.dumps(self.to_parameters(), indent=2),
        )


class DecaySettingsDialog(QtWidgets.QDialog):
    """Modal per-species fluorescence-decay editor for the simulator.

    Edit each species' lifetime spectrum (τ table) and a shared Gaussian IRF, or
    load an existing decay-pattern file; a live preview shows the resulting decay
    (built through the single canonical ``synthetic_decay`` generator). On OK the
    per-species ``decay_lifetimes`` / ``decay_pattern_files`` / ``irf_fwhm_ns``
    are written back to the settings model.
    """

    def __init__(self, model, parent=None, start_species: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Decay settings")
        self.setModal(True)
        self.resize(560, 620)
        self._model = model
        n = max(1, int(model.n_species))
        base_lt = list(model.decay_lifetimes or [[[1.0, 3.2]]])
        base_pf = list(model.decay_pattern_files or [""])

        def _pairs(spec):
            out = []
            for e in (spec or []):
                if isinstance(e, (list, tuple)) and len(e) >= 2:
                    out.append([float(e[0]), float(e[1])])
                else:
                    out.append([1.0, float(e)])
            return out or [[1.0, 3.2]]

        # Per-species stores; the shared editor edits one species at a time.
        # Pad with the default rather than wrapping around: `base_lt[i % len]`
        # gave a species added later a *copy of another species'* decay, with
        # nothing on screen saying so. An unset species starts from the default.
        self._lifetimes = [
            _pairs(base_lt[i]) if i < len(base_lt) else _pairs(None) for i in range(n)
        ]
        self._patterns = [str(base_pf[i]) if i < len(base_pf) else "" for i in range(n)]
        self._fwhm = float(getattr(model, "irf_fwhm_ns", 0.0) or 0.0)
        self._cur = max(0, min(int(start_species), n - 1))

        from chisurf.gui.autoform import AutoForm
        from chisurf.gui.widgets.synthetic_decay_editor import SyntheticDecayEditorModel

        # The one shared synthetic-decay editor — identical to the FCS Filter
        # Calculator's synthetic-component editor, so the two never diverge.
        self.editor_model = SyntheticDecayEditorModel(
            n_bins=int(model.n_tac_channels),
            bin_width=float(model.tac_dt),
        )
        self._build_ui(n, AutoForm)
        self._push_editor(self._cur)

    def _build_ui(self, n: int, AutoForm) -> None:
        lay = QtWidgets.QVBoxLayout(self)
        if n > 1:
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel("Species:"))
            self.combo = QtWidgets.QComboBox()
            self.combo.addItems([str(i + 1) for i in range(n)])
            self.combo.setCurrentIndex(self._cur)
            self.combo.currentIndexChanged.connect(self._on_species)
            row.addWidget(self.combo)
            row.addStretch(1)
            lay.addLayout(row)

        self.form = AutoForm(self.editor_model, self)
        lay.addWidget(self.form, 1)

        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # -- per-species state -------------------------------------------------
    def _on_species(self, idx: int) -> None:
        self._pull_editor(self._cur)
        self._cur = int(idx)
        self._push_editor(self._cur)

    def _push_editor(self, idx: int) -> None:
        """Load species ``idx`` into the shared editor."""
        self.editor_model.spectrum_rows = [
            {"amplitude": float(a), "lifetime": float(t)} for a, t in self._lifetimes[idx]
        ]
        self.editor_model.pattern_path = self._patterns[idx]
        self.editor_model.irf_fwhm_ns = self._fwhm
        self.editor_model.name = f"Species {idx + 1}"
        self.form.sync_fields()
        self.form.refresh_plots()

    def _pull_editor(self, idx: int) -> None:
        """Save the shared editor's current state back into species ``idx``."""
        rows = self.editor_model.spectrum_rows
        if rows:
            self._lifetimes[idx] = [
                [float(r["amplitude"]), float(r["lifetime"])] for r in rows
            ]
        self._patterns[idx] = self.editor_model.pattern_path
        # The Gaussian IRF FWHM is shared across all species.
        self._fwhm = float(self.editor_model.irf_fwhm_ns)

    def _accept(self) -> None:
        self._pull_editor(self._cur)
        self._model.decay_lifetimes = [list(t) for t in self._lifetimes]
        self._model.decay_pattern_files = list(self._patterns)
        self._model.irf_fwhm_ns = float(self._fwhm)
        self.accept()


class EnhancedSimulationSetupDialog(QtWidgets.QDialog):
    """AutoForm-backed setup dialog for tttrlib simulation parameters."""

    def __init__(self, device=None, parent=None):
        """Initialize the setup dialog.

        Parameters
        ----------
        device : object, optional
            Simulation device or acquisition wrapper carrying
            ``simulation_params``.
        parent : QWidget, optional
            Parent widget.
        """
        super().__init__(parent)
        self.device = device
        self.setWindowTitle("Simulation Setup")
        self.resize(720, 720)
        self.model = SimulationSettingsModel.from_parameters(self._device_parameters())
        self.form = AutoForm(self.model)
        self.model._sync_fields = self.form.sync_fields
        self.model._refresh_widgets = self.form.refresh_plots
        self._build_ui()

    def _device_parameters(self) -> dict[str, Any]:
        """Read simulation parameters from the device-like object.

        Returns
        -------
        dict
            Existing parameters or an empty dictionary.
        """
        if self.device is None:
            return {}
        if hasattr(self.device, "simulation_params"):
            return dict(getattr(self.device, "simulation_params") or {})
        inner = getattr(self.device, "device", None)
        if inner is not None and hasattr(inner, "simulation_params"):
            return dict(getattr(inner, "simulation_params") or {})
        return {}

    def _build_ui(self) -> None:
        """Build the dialog around the AutoForm widget."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.form, 1)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _flush_editor_focus(self) -> None:
        """Commit any AutoForm editor that is waiting for focus-out."""
        focused = QtWidgets.QApplication.focusWidget()
        if focused is not None:
            focused.clearFocus()

    def get_parameters(self) -> dict[str, Any]:
        """Return current simulation parameters.

        Returns
        -------
        dict
            Parameters consumed by ``SimulationDevice``.
        """
        self._flush_editor_focus()
        return self.model.to_parameters()

    def _apply_parameters(self, params: dict[str, Any]) -> None:
        """Apply saved parameters to the form.

        Parameters
        ----------
        params : dict
            Saved simulation parameter dictionary.
        """
        self.model.apply_parameters(params)
        self.form.sync_fields()

    def accept(self) -> None:
        """Accept the dialog and update the attached device parameters."""
        params = self.get_parameters()
        target = self.device
        if target is not None and hasattr(target, "simulation_params"):
            target.simulation_params.update(params)
        inner = getattr(target, "device", None) if target is not None else None
        if inner is not None and hasattr(inner, "simulation_params"):
            inner.simulation_params.update(params)
        super().accept()

    def load_json(self) -> None:
        """Load JSON parameters into the form."""
        self.model.load_json()
        self.form.sync_fields()

    def save_json(self) -> None:
        """Save the current form parameters as JSON."""
        self.model.save_json()

    def view_json(self) -> None:
        """Show the current form parameters as JSON."""
        self.model.view_json()


SimulationSetupDialog = EnhancedSimulationSetupDialog
