"""Native form for the original easy optical setup graph and simulator."""

import copy
import json
from pathlib import Path

from chisurf.core.optical_configuration import (
    _graph_to_config,
    apply_easy_graph_parameters,
    build_easy_graph,
    extract_forster,
)


class OpticalConfigurationWidget:
    def __init__(self, config=None, detector_names=None, on_changed=None, on_open_graph=None):
        self.config = copy.deepcopy(
            config
            or {
                "lasers": "488:1.0, 640:1.0",
                "dyes": {},
                "detectors": [{"name": name} for name in (detector_names or ["green", "red"])],
                "emission_splitters": [],
                "kappa2": 2 / 3,
                "n": 1.33,
            }
        )
        self.on_changed = on_changed
        self.on_open_graph = on_open_graph
        self.advanced_app = None
        self.advanced_window = None
        self.graph_override = copy.deepcopy(self.config.get("_graph"))
        self.probes = []
        self.status = ""
        self.new_detector = ""
        self.results = copy.deepcopy(self.config.get("_cached_results") or {})
        self.dialog = None
        self.action = "load"
        self.template_directory = (
            Path(__file__).resolve().parents[1]
            / "plugins"
            / "core"
            / "lightpath_simulator"
            / "templates"
        )
        self.preset_directory = Path.home() / ".chisurf" / "presets" / "lightpath_optical"
        self.templates = sorted(self.template_directory.glob("*.json")) + sorted(
            self.preset_directory.glob("*.json")
        )
        self.template_index = 0

    def changed(self):
        if self.graph_override is not None:
            self.graph_override = apply_easy_graph_parameters(self.graph_override, self.config)
            self.config["_graph"] = copy.deepcopy(self.graph_override)
        if callable(self.on_changed):
            self.on_changed(copy.deepcopy(self.config))

    def refresh_probes(self):
        from chisurf.plugins.core.lightpath_simulator.core.workflow import get_probes_info

        self.probes = get_probes_info().get("probes", [])
        self.status = f"{len(self.probes)} optical components available."

    def simulate(self):
        from chisurf.plugins.core.lightpath_simulator.core.workflow import (
            serialize_numpy,
            simulate_lightpath,
        )

        graph = self.graph_override or build_easy_graph(copy.deepcopy(self.config))
        self.results = serialize_numpy(
            simulate_lightpath(graph, db_path=self.config.get("_spectra_db_path"))
        )
        self.config["_cached_results"] = {
            "forster": extract_forster(self.results),
            "crosstalk_matrices": self.results.get("crosstalk_matrices", {}),
        }
        self.changed()
        self.status = "Optical simulation completed."
        return self.results

    def load(self, path):
        config = json.loads(Path(path).read_text())
        if "nodes" in config:
            graph = copy.deepcopy(config)
            config = _graph_to_config(config)
            config["_graph"] = graph
        elif "config" in config:
            config = config["config"]
        if not isinstance(config, dict):
            raise ValueError("Optical preset must contain an object.")
        self.config = copy.deepcopy(config)
        self.graph_override = copy.deepcopy(config.get("_graph"))
        self.results = copy.deepcopy(config.get("_cached_results") or {})
        self.changed()

    def save(self, path):
        Path(path).write_text(json.dumps(self.config, indent=2))
        self.status = "Optical configuration saved."

    def open_advanced(self):
        if callable(self.on_open_graph):
            self.on_open_graph()
            return
        from emtk.dialog_window import DialogWindow

        from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

        if self.advanced_app is not None:
            self.advanced_app.close()
        self.advanced_app = create_app(
            db_path=self.config.get("_spectra_db_path"), owner_id=f"channel-optical-{id(self)}"
        )
        self.advanced_app.controller.auto_update = False
        self.advanced_app.controller.load_document(
            self.graph_override or build_easy_graph(copy.deepcopy(self.config))
        )
        self.advanced_app.docks.name = f"advanced-optical-{id(self)}"
        self.advanced_window = DialogWindow(
            "Advanced optical graph", size=(1100, 780), key=f"advanced-optical-{id(self)}"
        )
        self.advanced_window.show()

    def apply_advanced(self):
        if self.advanced_app is None:
            raise ValueError("Open the advanced editor first.")
        graph = self.advanced_app.controller.graph()
        self.config = _graph_to_config(graph)
        self.config["_graph"] = graph
        self.config["_spectra_db_path"] = self.advanced_app.controller.db_path
        self.graph_override = copy.deepcopy(graph)
        self.results = copy.deepcopy(self.advanced_app.controller.result)
        self.config["_cached_results"] = {
            "forster": extract_forster(self.results),
            "crosstalk_matrices": self.results.get("crosstalk_matrices", {}),
        }
        self.changed()
        self.status = "Advanced optical graph applied to this setup."
        self._close_advanced()

    def _close_advanced(self):
        if self.advanced_app is not None:
            self.advanced_app.close()
            self.advanced_app = None
        if self.advanced_window is not None:
            self.advanced_window.hide()

    def close(self):
        self._close_advanced()

    def _action(self, function, *args):
        try:
            return function(*args)
        except Exception as exc:
            self.status = f"Error: {exc}"

    @staticmethod
    def _button(label, tip, callback):
        from emtk import im

        if im.button(label):
            callback()
        im.set_item_tooltip(tip)

    def _probe(self, label, current, filter_key=None):
        from emtk import im

        probes = [p for p in self.probes if filter_key is None or p.get(filter_key)]
        ids = [None] + [p["probe_id"] for p in probes]
        labels = ["None"] + [f"{p['name']} ({p['probe_id']})" for p in probes]
        if current is not None and current not in ids:
            ids.append(current)
            labels.append(f"Component {current}")
        im.text(label + ":")
        changed, index = im.combo("##" + label, ids.index(current), labels)
        im.set_item_tooltip(f"Select the measured spectrum used for {label.lower()}.")
        return changed, ids[index]

    def draw(self):
        from emtk import im

        self._button(
            "Open advanced graph editor",
            "Edit arbitrary components and optical connections; apply the full graph back to this setup.",
            self.open_advanced,
        )
        self._button(
            "Refresh optical catalogue",
            "Load available dye, transmission and detector spectra from MMFDB.",
            lambda: self._action(self.refresh_probes),
        )
        self._button(
            "Load optical preset",
            "Load an easy-mode configuration or a light-path graph.",
            lambda: self.browse("load"),
        )
        self._button(
            "Save optical preset",
            "Save the complete optical configuration including cached simulation results.",
            lambda: self.browse("save"),
        )
        if self.templates:
            im.text("Built-in template:")
            changed, index = im.combo(
                "##optical_template",
                self.template_index,
                ["Choose template"] + [p.stem for p in self.templates],
            )
            self.template_index = index
            im.set_item_tooltip("Load a packaged instrument light-path template.")
            if changed and index > 0:
                self._action(self.load, self.templates[index - 1])
        im.text("Laser lines wavelength:power:")
        changed, value = im.input_text(
            "##optical_lasers", self.config.get("lasers", "488:1.0, 640:1.0")
        )
        im.set_item_tooltip(
            "Comma-separated excitation lines in nanometers with relative powers, for example 488:1.0, 640:1.0."
        )
        if changed:
            self.config["lasers"] = value
            self.changed()
        for key, label, minimum, maximum in [
            ("kappa2", "Orientation factor κ²", 0.0, 4.0),
            ("n", "Refractive index", 1.0, 3.0),
        ]:
            im.text(label + ":")
            changed, value = im.slider_float(
                "##optical_" + key,
                float(self.config.get(key, 2 / 3 if key == "kappa2" else 1.33)),
                minimum,
                maximum,
            )
            im.set_item_tooltip(
                "Parameter used in the Förster-radius calculation for the selected fluorophores."
            )
            if changed:
                self.config[key] = value
                self.changed()
        changed, value = self._probe(
            "Excitation dichroic", self.config.get("excitation_dichroic_probe_id"), "has_trans"
        )
        if changed:
            self.config["excitation_dichroic_probe_id"] = value
            self.changed()
        changed, value = self._probe("Add fluorophore", None, "has_em")
        if changed and value is not None:
            probe = next(p for p in self.probes if p["probe_id"] == value)
            self.config.setdefault("dyes", {})[str(value)] = {
                "qy": probe.get("qy", 1.0),
                "ec": probe.get("ec", 1.0),
            }
            self.changed()
        for dye, properties in list(self.config.setdefault("dyes", {}).items()):
            im.push_id(dye)
            im.text(f"Fluorophore {dye}")
            for key, label in [("qy", "Quantum yield"), ("ec", "Extinction coefficient")]:
                changed, value = im.input_float(label, float(properties.get(key, 1.0)))
                im.set_item_tooltip(f"Optical {label.lower()} of fluorophore {dye}.")
                if changed:
                    properties[key] = max(0.0, value)
                    self.changed()
            self._button(
                "Remove fluorophore",
                "Remove this dye from the optical sample.",
                lambda key=dye: self._remove_dye(key),
            )
            im.pop_id()
        self._button(
            "Add emission splitter",
            "Add a measured dichroic or polarizer in the detection path.",
            self._add_splitter,
        )
        for index, splitter in enumerate(list(self.config.setdefault("emission_splitters", []))):
            im.push_id(f"splitter{index}")
            options = ["Dichroic", "Polarizer"]
            current = splitter.get("type", "Dichroic")
            changed, selected = im.combo(
                "Splitter type", options.index(current) if current in options else 0, options
            )
            im.set_item_tooltip("Choose a dichroic splitter or polarization splitter.")
            if changed:
                splitter["type"] = options[selected]
                self.changed()
            changed, value = self._probe("Splitter spectrum", splitter.get("probe_id"), "has_trans")
            if changed:
                splitter["probe_id"] = value
                self.changed()
            self._button(
                "Remove splitter",
                "Remove this splitter from the optical chain.",
                lambda i=index: self._remove_splitter(i),
            )
            im.pop_id()
        im.text("New optical detector name:")
        _, self.new_detector = im.input_text("##new_optical_detector", self.new_detector)
        im.set_item_tooltip("Name of the optical detector channel to add.")
        self._button(
            "Add optical detector",
            "Add a detector channel with its bandpass and quantum-efficiency spectrum.",
            self._add_detector,
        )
        for index, detector in enumerate(list(self.config.setdefault("detectors", []))):
            im.push_id(f"optical_detector{index}")
            im.text(detector.get("name", f"Detector {index + 1}"))
            for key, label, filter_key in [
                ("bandpass_probe_id", "Bandpass", "has_trans"),
                ("qe_probe_id", "Quantum efficiency", "has_qe"),
            ]:
                changed, value = self._probe(label, detector.get(key), filter_key)
                if changed:
                    detector[key] = value
                    self.changed()
            self._button(
                "Remove optical detector",
                "Remove this detector from the simulated light path.",
                lambda i=index: self._remove_detector(i),
            )
            im.pop_id()
        self._button(
            "Simulate optical setup",
            "Calculate Förster radii and excitation/emission/detection crosstalk using the original optical backend.",
            lambda: self._action(self.simulate),
        )
        if self.results:
            self._draw_matrix(
                "Förster radius", self.results.get("forster") or extract_forster(self.results)
            )
            for title, matrix in self.results.get("crosstalk_matrices", {}).items():
                self._draw_matrix(f"{title.title()} crosstalk", matrix)
        if self.status:
            im.text_wrapped(self.status)

    @staticmethod
    def _draw_matrix(title, matrix):
        from emtk import im

        if not isinstance(matrix, dict):
            return
        rows, columns, values = (
            matrix.get("rows", []),
            matrix.get("columns", []),
            matrix.get("values", []),
        )
        if not rows or not columns:
            return
        im.text(title)
        if im.begin_table(
            "##matrix_" + title, len(columns) + 1, im.TableFlags.BORDERS | im.TableFlags.ROW_BG
        ):
            im.table_setup_column("")
            for column in columns:
                im.table_setup_column(str(column))
            im.table_headers_row()
            for index, row in enumerate(rows):
                im.table_next_row()
                im.table_next_column()
                im.text(str(row))
                for value in values[index]:
                    im.table_next_column()
                    im.text(f"{float(value):.4g}")
            im.end_table()

    def _remove_dye(self, name):
        self.config["dyes"].pop(name, None)
        self.changed()

    def _add_splitter(self):
        self.config.setdefault("emission_splitters", []).append(
            {"type": "Dichroic", "probe_id": None}
        )
        self.changed()

    def _remove_splitter(self, index):
        self.config["emission_splitters"].pop(index)
        self.changed()

    def _add_detector(self):
        if self.new_detector.strip():
            self.config.setdefault("detectors", []).append({"name": self.new_detector.strip()})
            self.new_detector = ""
            self.changed()

    def _remove_detector(self, index):
        self.config["detectors"].pop(index)
        self.changed()

    def browse(self, action):
        from emtk.file_dialog import FileDialog

        self.action = action
        self.dialog = FileDialog(
            "Optical configuration",
            mode="save" if action == "save" else "open",
            filters=[("Optical JSON", ["*.json"])],
            filename="optical_setup.json" if action == "save" else None,
        )

    def draw_dialogs(self, frame):
        from emtk import im

        if self.advanced_window is not None and self.advanced_window.open:
            pressed = self.advanced_window.begin(frame)
            self._button(
                "Apply graph to setup",
                "Keep the full edited graph, including custom nodes and rewiring.",
                lambda: self._action(self.apply_advanced),
            )
            im.same_line()
            self._button(
                "Keep previous optical setup",
                "Close the graph editor without applying changes.",
                self._close_advanced,
            )
            if self.advanced_app is not None:
                self.advanced_app.controller.poll()
                self.advanced_app.io = im.get_current_context().io
                x, y = im.get_cursor_screen_pos()
                width, height = im.get_content_region_avail()
                self.advanced_app.docks.draw((x, y, max(100, width), max(120, height)))
            self.advanced_window.end()
            if pressed == "close":
                self._close_advanced()
        if self.dialog is None:
            return
        if im.begin("Optical preset chooser"):
            result = self.dialog.draw()
            if result:
                self._action(self.save if self.action == "save" else self.load, result[0])
                self.dialog = None
            elif result is False:
                self.dialog = None
        im.end()
