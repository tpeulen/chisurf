"""emtk app for the Potential-Energy calculator: every frame of a trajectory scored by weighted potentials.

Drawn from ``calculate_potential.view.json`` (the spec the Qt widget uses) by the shared trajectory-tool app: the
trajectory and topology rows, the potential editor (a type combo, the parameters of that type, the weight and
**Add**), the stride, the table of added potentials (a double click on a row removes it), **Process** and the log.
The editor is declared as a spec of its own from the Qt-free :mod:`~.potential_specs` registry, which mirrors the
parameters the Qt ``potentialDict`` editors expose, so this module never imports Qt.

Differences from the Qt widget, on purpose: the parameters of a potential type are kept while another type is
chosen (the Qt editor was rebuilt on every change) and the table also removes the selected row on Delete.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from emtk import im
from emtk.view_form import FormState, draw_form

from chisurf.plugins.traj.emtk_tool import SaveAction, TrajToolApp, topology_field, trajectory_field

from .potential_specs import get_spec, make_potential, potential_names
from .strings import install_translations
from .view_model import PotentialEnergyViewModel

install_translations()

HERE = pathlib.Path(__file__).parent
FILE_FILTERS = [("NumPy", ["*.npy"]), ("All files", ["*"])]
ENERGY_FILTERS = [("CSV-name file", ["*.txt"]), ("All files", ["*"])]


class EditorModel:
    """The values the potential editor edits: the type, and one attribute per parameter of that type.

    The form reads and writes plain attributes (``draw_form``), so the parameters of the selected type are exposed as
    attributes and kept per type; ``add`` builds the potential with them and gives the model the weight.
    """

    def __init__(self, app: PotentialEnergyApp) -> None:
        object.__setattr__(self, "_app", app)

    # -- the type ----------------------------------------------------------------------------------------- #
    @property
    def potential_type(self) -> str:
        names = potential_names()
        index = self._app.selected_potential_index
        return names[index] if 0 <= index < len(names) else names[0]

    @potential_type.setter
    def potential_type(self, name: str) -> None:
        names = potential_names()
        if name in names:
            self._app.selected_potential_index = names.index(name)
            self._app.model.selected_potential_index = names.index(name)

    # -- the parameters of the selected type ------------------------------------------------------------ #
    def _param(self, attr: str):
        spec = get_spec(self.potential_type)
        return next((p for p in (spec.params if spec else ()) if p.attr == attr), None)

    def __getattr__(self, attr: str) -> Any:
        param = self._param(attr)
        if param is None:
            raise AttributeError(attr)
        return self._app._editor_values.setdefault(self.potential_type, {}).get(attr, param.default)

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr == "potential_type":
            type(self).potential_type.fset(self, value)
            return
        param = self._param(attr)
        if param is None:
            raise AttributeError(attr)
        self._app._editor_values.setdefault(self.potential_type, {})[attr] = value

    # -- the button --------------------------------------------------------------------------------------- #
    def add(self) -> None:
        """Add the potential with the editor's parameters and the model's weight (Qt: the **Add** button)."""
        app = self._app
        name = self.potential_type
        app.tour.notify_used("add")
        try:
            potential = make_potential(name, dict(app._editor_values.get(name, {})))
            app.model.add_potential(potential, float(app.model.potential_weight), name=name)
        except Exception as exc:  # noqa: BLE001 - shown in the window, as the Qt tool's dialog would
            app.status = f"{type(exc).__name__}: {exc}"
            return
        app.status = ""
        app._editor_values.pop(name, None)       # the added editor belongs to the universe: a fresh one, as in Qt


def editor_spec(name: str) -> dict:
    """The spec of the parameters of potential type *name*: spin fields, toggles in one row, file rows."""
    spec = get_spec(name)
    sections: list[dict] = []
    toggles: list[dict] = []
    for param in (spec.params if spec else ()):
        tip = param.tip or param.label
        if param.kind in ("float", "int"):
            section = {"type": "value", "attr": param.attr, "label": param.label, "kind": param.kind,
                       "style": "spin", "description": tip}
            if param.minimum is not None:
                section["minimum"] = param.minimum
            if param.maximum is not None:
                section["maximum"] = param.maximum
            if param.step:
                section["step"] = param.step
            if param.kind == "float":
                section["decimals"] = 3 if (param.step or 1.0) < 0.1 else 2
            sections.append(section)
        elif param.kind == "bool":
            toggles.append({"type": "toggle", "attr": param.attr, "label": param.label, "description": tip})
        else:
            sections.append({"type": "custom", "key": f"file:{param.attr}", "label": param.label,
                             "description": tip})
    if toggles:
        sections.append({"type": "panel", "title": "", "n_col": len(toggles), "sections": toggles})
    return {"sections": sections}


class PotentialEnergyApp(TrajToolApp):
    """Calculate potential-energy components across the frames of a trajectory."""

    def __init__(self, model: PotentialEnergyViewModel | None = None) -> None:
        self.selected_potential_index = 0
        #: Per potential type: the parameter values typed by the user.
        self._editor_values: dict[str, dict] = {}
        self.frames_done = 0
        self.editor = EditorModel(self)
        self.editor_form = FormState()
        process = SaveAction(
            key="process",
            label="Process",
            tooltip="Score every frame of the trajectory and write the energies to a CSV.",
            dialog_title="Save energies",
            filters=ENERGY_FILTERS,
            run=self._process,
            missing=self._missing,
            failure="Processing failed",
            cancelled="Process cancelled",
            done=lambda count: f"Processed {count} frame(s).",
        )
        super().__init__(
            model or PotentialEnergyViewModel(), HERE, "calculate_potential.view.json", "potential_energy_setup",
            "Potential energy",
            [trajectory_field(attr="trajectory_file"),
             topology_field()],
            process, action_key="potential_energy_run",
        )
        self.editor_form.on_used = self.tour.notify_used
        for section in self.spec["sections"]:
            if section.get("type") == "table":      # a double click removes a row (Qt); so does Delete
                section.setdefault("delete_call", "remove_potential_activated")
        self._weight_spec = {"sections": [{
            "type": "value", "attr": "potential_weight", "label": "Weight", "kind": "float", "style": "spin",
            "minimum": -1e6, "maximum": 1e6, "step": 1.0, "decimals": 3,
            "description": "Scaling factor applied to the next potential added.",
        }]}
        self._choice_spec = {"sections": [{
            "type": "choice", "attr": "potential_type", "label": "Potential", "options": potential_names(),
            "description": "Type of potential to configure and add.",
        }, {
            "type": "button_row", "buttons": [{
                "action": "add", "label": "Add",
                "description": "Add the configured potential to the list of used potentials.",
            }],
        }]}
        self._specs: dict[str, dict] = {}
        self._file_rows: dict[str, dict] = {}

    # -- the action ---------------------------------------------------------------------------------------- #
    def _missing(self, model) -> str | None:
        if not model.trajectory_file:
            return "Open a trajectory first."
        if not model.universe.potentials:
            return "Add at least one potential."
        return None

    def _process(self, model, path: str | None) -> int:
        self.frames_done = 0
        return model.process(path, progress_cb=self._on_progress)

    def _on_progress(self, frames_done: int) -> None:
        self.frames_done = int(frames_done)
        self.request_frame()

    def progress_text(self) -> str:
        return f" {self.frames_done} frame(s)" if self.frames_done else ""

    # -- the potential editor: the type, its parameters, the weight, Add ------------------------------- #
    def draw_extra_io(self, width: float) -> None:
        self.editor_form.rects.clear()
        name = self.editor.potential_type
        spec = self._specs.get(name)
        if spec is None:
            spec = self._specs[name] = editor_spec(name)
            self.editor_form.custom = {f"file:{p.attr}": self._draw_file_param(p)
                                       for p in (get_spec(name).params if get_spec(name) else ())
                                       if p.kind == "file"}
        draw_form(self._choice_spec, self.editor, self.editor_form)
        if spec["sections"]:
            draw_form(spec, self.editor, self.editor_form)
        draw_form(self._weight_spec, self.model, self.editor_form)
        self.item_rects.update(self.editor_form.rects)
        for key in ("potential_type", "add"):
            if key in self.editor_form.rects:
                self.item_rects[key] = self.editor_form.rects[key]

    def _draw_file_param(self, param):
        """A potential file row: the path (typed or chosen) and its ``…``."""
        def draw(section, model, state, width) -> None:
            values = self._editor_values.setdefault(self.editor.potential_type, {})
            label_w = im.calc_text_size(param.label)[0] + 8.0
            button_w = im.get_frame_height() + 6.0
            im.text(param.label)
            im.same_line(max(label_w, 110.0))
            im.set_next_item_width(max(80.0, width - max(label_w, 110.0) - button_w - 8.0))
            changed, text = im.input_text(f"##{param.attr}", str(values.get(param.attr, param.default)),
                                          elide_start=True)
            im.set_item_tooltip(param.tip or param.label)
            self.remember(param.attr)
            if changed:
                values[param.attr] = text
            im.same_line()
            if im.button(f"…##{param.attr}.browse", (button_w, 0)):
                current = str(values.get(param.attr, param.default) or "")
                from emtk.file_dialog import FileDialog

                self._open_dialog(FileDialog(f"Open {param.label}", mode="open", filters=FILE_FILTERS,
                                             directory=os.path.dirname(current) or None),
                                  lambda path, attr=param.attr: self._editor_values.setdefault(
                                      self.editor.potential_type, {}).__setitem__(attr, path))
            im.set_item_tooltip(f"Choose the {param.label.lower()} file.")
            self.remember(f"{param.attr}_browse")
        return draw

    # -- persistence ------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        settings = super().export_settings()
        settings.update({
            "potential_weight": float(self.model.potential_weight),
            "selected_potential_index": int(self.selected_potential_index),
            "editor_values": {name: dict(values) for name, values in self._editor_values.items()},
        })
        return settings

    def restore_settings(self, settings: dict) -> None:
        super().restore_settings(settings)
        if "potential_weight" in settings:
            self.model.potential_weight = float(settings["potential_weight"])
        if "selected_potential_index" in settings:
            self.selected_potential_index = int(settings["selected_potential_index"])
        for name, values in (settings.get("editor_values") or {}).items():
            self._editor_values[name] = dict(values)


def make_app(**kwargs) -> PotentialEnergyApp:
    """Construct the standalone Potential-Energy app."""
    from chisurf.emtk.i18n import install

    install()
    return PotentialEnergyApp()


__all__ = ["EditorModel", "PotentialEnergyApp", "editor_spec", "make_app"]
