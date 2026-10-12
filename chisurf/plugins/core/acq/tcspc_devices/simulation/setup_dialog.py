"""AutoForm setup dialog for the tttrlib acquisition photon simulator."""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass, field
from typing import Any

from qtpy import QtWidgets

from chisurf.core import dataspec as ds
from chisurf.gui import dialogs
from chisurf.gui.autoform import AutoForm, register_section
from chisurf.gui.glyphs import Glyphs

from .settings_model import (  # noqa: F401
    SimulationSettingsModel as _SettingsBase,
)
from .settings_model import (
    _expand_species_q,
    _flatten,
    _help,
    _list_get,
    _schema_help,
    _sized_matrix,
    load_channel_settings,
)


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


@dataclass
class SimulationSettingsModel(_SettingsBase):
    """Qt AutoForm view of :class:`.settings_model.SimulationSettingsModel`."""

    def species_columns(self) -> list:
        """Return the per-species columns for the ``state_table`` section.

        Molecules and diffusion, then the parallel/perpendicular brightness of
        every enabled colour. ``species_q`` keeps six slots per species
        (three colours x two polarisations) whatever is enabled, so switching a
        colour on does not renumber the ones already set — the column simply
        addresses its slot.
        """
        columns = [
            {
                "attr": "species_M",
                "label": "M",
                "default": 50.0,
                "description": "Molecules (mean number in the box) for this species.",
            },
            {
                "attr": "species_D",
                "label": "D",
                "default": 3.0,
                "description": "Diffusion coefficient (\u00b5m\u00b2/ms) for this species.",
            },
        ]
        for color in self.enabled_colors():
            base = self._CHANNEL_COLORS.index(color) * 2
            for polarisation, mark in ((0, "\u2225"), (1, "\u22a5")):
                columns.append(
                    {
                        "attr": "species_q",
                        "stride": 6,
                        "slot": base + polarisation,
                        "label": f"{self._CHANNEL_ABBR[color]} {mark}",
                        "maximum": 1e6,
                        "description": f"{color.capitalize()} {'parallel' if polarisation == 0 else 'perpendicular'} brightness q.",
                    }
                )
        # The decay is a whole spectrum, not a number, so the row opens an
        # editor rather than holding a cell. Having it on the row removes the
        # "which species am I editing" selector the dialog used to carry.
        columns.append(
            {
                "action": "open_decay_dialog",
                "label": "Decay",
                "text": "\u2026",
                "description": "Edit this species' lifetime spectrum, decay pattern and IRF.",
            }
        )
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
                        ds.ValueSection(
                            attr="output_path",
                            label="Output folder",
                            kind="str",
                            description="Folder where SPC/photon-stream files are written.",
                        ),
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
                            options={
                                "size_attr": "n_species",
                                "columns_source": "species_columns",
                                "trailing_rows_source": "species_trailing_rows",
                            },
                        ),
                    ),
                ),
                ds.PanelSection(
                    title="Kinetics",
                    collapsed=True,
                    description="Species-interconversion transition rates (radiative and non-radiative). Each button opens an N×N grid that tracks the species count and says how many transitions are set.",
                    sections=(
                        ds.CustomSection(
                            key="rate_matrix",
                            target="k_rad",
                            options={
                                "size_attr": "n_species",
                                "minimum": 0.0,
                                "decimals": 4,
                                "unit": "1/ms",
                                "popup": True,
                                "title": "Radiative (k_rad)",
                            },
                        ),
                        ds.CustomSection(
                            key="rate_matrix",
                            target="k_nrad",
                            options={
                                "size_attr": "n_species",
                                "minimum": 0.0,
                                "decimals": 4,
                                "unit": "1/ms",
                                "popup": True,
                                "title": "Non-radiative (k_nrad)",
                            },
                        ),
                    ),
                ),
                ds.PanelSection(
                    title="Geometry",
                    n_col=2,
                    sections=(
                        self._float_field(
                            "box_xy",
                            "Box XY",
                            minimum=0.001,
                            decimals=4,
                            description=_help("box_xy"),
                        ),
                        self._float_field(
                            "box_z", "Box Z", minimum=0.001, decimals=4, description=_help("box_z")
                        ),
                        self._float_field(
                            "focus_w0",
                            "Focus w0",
                            minimum=0.001,
                            decimals=4,
                            description=_help("focus_param"),
                        ),
                        self._float_field(
                            "focus_z0",
                            "Focus z0",
                            minimum=0.001,
                            decimals=4,
                            description=_help("focus_param"),
                        ),
                        self._float_field(
                            "dt", "Step", minimum=0.000001, decimals=6, description=_help("dt")
                        ),
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
                        self._float_field(
                            "tac_dt",
                            "TAC dt",
                            minimum=0.000001,
                            decimals=6,
                            description=_help("tac_dt"),
                        ),
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
                            attr="per_molecule_skip",
                            label="Coasting",
                            description=_help("per_molecule_skip"),
                        ),
                        ds.ToggleSection(
                            attr="fast_grid_bbox",
                            label="Two-step field lookup",
                            description=_help("fast_grid_bbox"),
                        ),
                        ds.ToggleSection(
                            attr="independent_molecules",
                            label="Independent molecules",
                            description=_help("independent_molecules"),
                        ),
                        ds.ToggleSection(
                            attr="analytic_excitation",
                            label="Analytic Gaussian focus",
                            description=_help("analytic_excitation"),
                        ),
                        ds.ChoiceSection(
                            attr="psf_type",
                            label="PSF / focus model",
                            options=(
                                "gaussian3d",
                                "analytic_gaussian3d",
                                "gaussian_lorentzian",
                                "radial",
                            ),
                            labels=(
                                "Gaussian 3D",
                                "Analytic Gaussian",
                                "Gaussian-Lorentzian",
                                "Numeric (radial)",
                            ),
                            description=_help("psf_type"),
                        ),
                        self._float_field(
                            "psf_zR",
                            "Rayleigh range zR (µm)",
                            minimum=0.0,
                            decimals=3,
                            description=_help("psf_zR"),
                        ),
                        ds.ValueSection(
                            attr="psf_file",
                            label="PSF file (radial)",
                            kind="string",
                            description=_help("psf_file"),
                        ),
                        self._float_field(
                            "psf_r_step",
                            "PSF r step (µm)",
                            minimum=0.0,
                            decimals=4,
                            description=_help("psf_r_step"),
                        ),
                        self._float_field(
                            "psf_z_step",
                            "PSF z step (µm)",
                            minimum=0.0,
                            decimals=4,
                            description=_help("psf_z_step"),
                        ),
                        self._float_field(
                            "active_margin",
                            "Active margin (µm)",
                            minimum=0.0,
                            decimals=3,
                            description=_help("active_margin"),
                        ),
                        ds.ValueSection(
                            attr="max_windows",
                            label="Max windows",
                            kind="int",
                            minimum=0,
                            maximum=2_000_000_000,
                            description=_help("max_windows"),
                        ),
                        self._float_field(
                            "coast_safety",
                            "Coast safety",
                            minimum=1.0,
                            decimals=2,
                            description=_help("coast_safety"),
                        ),
                        ds.ValueSection(
                            attr="min_coast_windows",
                            label="Min coast windows",
                            kind="int",
                            minimum=1,
                            maximum=1_000_000,
                            description=_help("min_coast_windows"),
                        ),
                        self._float_field(
                            "focus_threshold",
                            "Focus threshold",
                            minimum=0.0,
                            decimals=6,
                            description=_help("focus_threshold"),
                        ),
                    ),
                ),
                ds.ButtonRowSection(
                    menu=f"{Glyphs.TOOLS} Tools",
                    buttons=(
                        {
                            "label": f"{Glyphs.DNA} Decay…",
                            "action": "open_decay_dialog",
                            "description": "Define the per-species fluorescence decay "
                            "(lifetimes / IRF) or load an existing decay pattern.",
                        },
                        {
                            "label": f"{Glyphs.OPEN} Load JSON",
                            "action": "load_json",
                            "description": "Load simulation parameters from a JSON file.",
                        },
                        {
                            "label": f"{Glyphs.SAVE} Save JSON",
                            "action": "save_json",
                            "description": "Save the current simulation parameters to a JSON file.",
                        },
                        {
                            "label": "🧾 View JSON",
                            "action": "view_json",
                            "description": "Show the current simulation parameters as JSON.",
                        },
                    ),
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
            for e in spec or []:
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
            self._lifetimes[idx] = [[float(r["amplitude"]), float(r["lifetime"])] for r in rows]
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
