"""The Acquisition destination of the Settings hub, native emtk (Qt-free).

Parity target: the Qt ``AcquisitionSettingsWidget`` of the hub -- the standard output folder, the chunk size, the
real-time pacing switch, the active device type and, for the simulator, its parameters. Every edit is stored at once
under ``gui.acquisition`` (as the Qt panel does on each change) through
:func:`chisurf.core.settings.settings_utils.set_acquisition_settings`. The form is the spec
``acq_settings_emtk.view.json`` drawn by :func:`emtk.view_form.draw_sections`.

What stays in the Qt Acquisition tool: the simulator's per-species table, the kinetics matrices, the decay editor and the
channel switches (Qt-only AutoForm sections) and the vendor card dialogs. Their stored values are kept untouched here.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

HERE = Path(__file__).parent
DEVICE_TYPES = ["Simulation", "Becker-Hickl", "PicoQuant", "BrickMic"]
CHUNK_RANGE = (1000, 65536)

#: Simulator attribute -> (parameter key, caster, companion keys written with it).
_SIM = {
    "excitation_mode": ("excitation_mode", str),
    "N_ph_max": ("N_ph_max", int),
    "N_ph_per_file": ("N_ph_per_file", int),
    "spc_output_path": ("spc_output_path", str),
    "rmt1seed": ("rmt1seed", int),
    "rmt2seed": ("rmt2seed", int),
    "box_xy": ("box_xy", float),
    "box_z": ("box_z", float),
    "dt": ("dt", float),
    "N_tac_channels": ("N_tac_channels", int),
    "tac_dt": ("tac_dt", float),
    "laser_period": ("laser_period", float),
    "per_molecule_skip": ("per_molecule_skip", bool),
    "fast_grid_bbox": ("fast_grid_bbox", bool),
    "independent_molecules": ("independent_molecules", bool),
    "analytic_excitation": ("analytic_excitation", bool),
    "psf_type": ("psf_type", str),
    "psf_zR": ("psf_zR", float),
    "psf_file": ("psf_file", str),
    "psf_r_step": ("psf_r_step", float),
    "psf_z_step": ("psf_z_step", float),
}
_FOCUS = {"focus_w0": 0, "focus_z0": 1}


def simulation_defaults() -> dict[str, Any]:
    """The parameters the Qt simulator dialog writes for a fresh form (a data file, checked against Qt by a test)."""
    return json.loads((HERE / "acq_sim_defaults.json").read_text(encoding="utf-8"))


class AcquisitionSettingsModel:
    """State of the Acquisition destination; every change is persisted like the Qt panel does."""

    def __init__(self, config: dict | None = None, persist=None) -> None:
        if config is None:
            from chisurf.settings import gui as gui_settings

            config = gui_settings.setdefault("acquisition", {})
        self.config = config
        self._persist = persist or self._persist_to_disk
        self.request = ""
        self.status = ""
        self.device_types = list(DEVICE_TYPES)
        self.config.setdefault("device_type", "Simulation")

    # -- plain fields ------------------------------------------------------------------------------------------- #
    @property
    def output_path(self) -> str:
        configured = str(self.config.get("output_path", "") or "").strip()
        if configured:
            return configured
        try:
            import chisurf as cs

            working = getattr(cs, "working_path", "") or ""
        except Exception:  # noqa: BLE001
            working = ""
        if working:
            return str(Path(working) / "acquisition")
        return str(Path.home() / "chisurf" / "acquisition")

    @output_path.setter
    def output_path(self, value: str) -> None:
        text = str(value).strip()
        self.config["output_path"] = str(Path(text).expanduser()) if text else ""
        self.save()

    @property
    def chunk_size(self) -> int:
        return int(self.config.get("chunk_size", 16384))

    @chunk_size.setter
    def chunk_size(self, value: int) -> None:
        self.config["chunk_size"] = max(CHUNK_RANGE[0], min(CHUNK_RANGE[1], int(value)))
        self.save()

    @property
    def real_time_sim(self) -> bool:
        return bool(self.config.get("real_time_sim", False))

    @real_time_sim.setter
    def real_time_sim(self, value: bool) -> None:
        self.config["real_time_sim"] = bool(value)
        self.save()

    @property
    def device_type(self) -> str:
        return str(self.config.get("device_type", "Simulation"))

    @device_type.setter
    def device_type(self, value: str) -> None:
        if value in self.device_types:
            self.config["device_type"] = value
            self.save()

    def browse_output(self) -> None:
        """Ask the app for the folder chooser (the Qt ``...`` button)."""
        self.request = "output"

    # -- simulator parameters ------------------------------------------------------------------------------------ #
    def _params(self) -> dict[str, Any]:
        params = self.config.get("simulation_params")
        return params if isinstance(params, dict) else {}

    def _write_param(self, key: str, value: Any) -> None:
        params = self.config.get("simulation_params")
        if not isinstance(params, dict):
            params = simulation_defaults()
            self.config["simulation_params"] = params
        params[key] = value
        if key == "excitation_mode":
            params["pulsed_exc"] = 1 if value == "Pulsed" else 0
        if key == "dt":
            params["tw"] = value
        self.save()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("sim_"):
            key = name[4:]
            params = self._params() or simulation_defaults()
            if key in _FOCUS:
                return float(params.get("focus_param", [0.3, 2.0])[_FOCUS[key]])
            if key in _SIM:
                return _SIM[key][1](params.get(key, simulation_defaults()[key]))
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("sim_"):
            key = name[4:]
            if key in _FOCUS:
                params = self._params() or simulation_defaults()
                focus = list(params.get("focus_param", [0.3, 2.0]))
                focus[_FOCUS[key]] = float(value)
                self._write_param("focus_param", focus)
                return
            if key in _SIM:
                self._write_param(_SIM[key][0], _SIM[key][1](value))
                return
        object.__setattr__(self, name, value)

    @property
    def sample_summary(self) -> str:
        params = self._params() or simulation_defaults()
        colours = [c.capitalize() for c in ("green", "red", "yellow") if params.get(f"{c}_enabled")]
        return (
            f"Species: {int(params.get('N_species', 1))}    Channels: {', '.join(colours) or 'Green'}\n"
            "The per-species table (M, D, brightness), kinetics matrices and decay spectra are edited in the "
            "Qt Acquisition tool; their stored values are kept as they are."
        )

    # -- persistence --------------------------------------------------------------------------------------------- #
    def save(self) -> None:
        self._persist(copy.deepcopy(self.config))

    @staticmethod
    def _persist_to_disk(config: dict) -> bool:
        from chisurf.core.settings.settings_utils import set_acquisition_settings

        return bool(set_acquisition_settings(config))


class AcquisitionSettingsApp(ImApp):
    """Edit the acquisition settings."""

    def __init__(self, model: AcquisitionSettingsModel | None = None) -> None:
        self.model = model or AcquisitionSettingsModel()
        spec = json.loads((HERE / "acq_settings_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.dialog: FileDialog | None = None
        self.dialog_window = DialogWindow("Select acquisition output folder", size=(700, 540), key="acq_output_dialog")
        self.help_window = EmTkHelpWindow(
            title="Acquisition - Help",
            text=(
                "# Acquisition settings\n\nThe standard output folder, the chunk size, the active device type and "
                "the simulator parameters of the Acquisition tool. Every change is stored at once.\n\n"
                "## Simulator\n\nThe scalar parameters are edited here. The per-species table, kinetics and decay "
                "spectra stay in the Acquisition tool and keep their stored values."
            ),
            owner=self,
        )
        self.tour = EmTkGuidedTour(
            steps=[
                {"title": "Output folder", "text": "New measurements are written here. Press Browse to pick a folder.",
                 "target": "browse_output", "await": {"hint": "Press Browse..."}},
                {"title": "Device type", "text": "Choose the simulator or the hardware family.", "target": "device_type"},
            ],
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(self.render)

    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        im.set_next_window_pos(vp.pos, im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("Acquisition settings", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            if im.button("Help"):
                self.help_window.show()
            im.set_item_tooltip("Explain the output folder, the chunk size, the device type and the simulator parameters.")
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if im.button("Guide"):
                self.tour.start()
            im.set_item_tooltip("Walk through choosing the output folder and the device type.")
            self.item_rects["guide"] = im.get_item_rect()
            draw_sections(self.panels["settings"]["sections"], self.model, self.form, titles=False)
        im.end()
        self._requests(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _requests(self, box: Any) -> None:
        request, self.model.request = self.model.request, ""
        if request == "output" and self.dialog is None:
            self.dialog = FileDialog(
                "Select acquisition output folder", mode="folder", directory=self.model.output_path
            )
            self.dialog_window.show()
        if self.dialog is None:
            return
        pressed = self.dialog_window.begin(box)
        result = self.dialog.draw()
        if result:
            self.model.output_path = result[0]
            self.dialog = None
            self.dialog_window.hide()
        elif result is False or pressed == "close":
            self.dialog = None
            self.dialog_window.hide()
        self.dialog_window.end()

    def export_settings(self) -> dict:
        return {"folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        folds = settings.get("folds", {})
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})

    def close(self) -> None:
        self.dialog = None


def make_app() -> AcquisitionSettingsApp:
    """Build the Acquisition settings app (the hub's destination factory)."""
    return AcquisitionSettingsApp()
