"""The Qt-free view model behind the light-path window: the actions, the form fields and the result tables.

``LightPathPanel`` wraps :class:`~.controller.LightPathController` and the graph control for the specs of
``lightpath.view.json`` (drawn by ``emtk.view_form``). An action returns nothing and reports a problem on
:attr:`message`; the app shows it in a dialog and on the status line, as the Qt tool showed its error boxes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from chisurf.core.optical_configuration import extract_forster

from .node_types import optical_registry

PRESET_DIR = Path.home() / ".chisurf" / "presets" / "lightpath_optical"


def preset_dir() -> Path:
    """The optical-preset folder Easy Mode reads (resolved at call time, so a test can move HOME)."""
    return Path.home() / ".chisurf" / "presets" / "lightpath_optical"


class ResultTable:
    """One results tab as rows and columns for a ``data_table`` section."""

    def __init__(self, panel: "LightPathPanel", kind: str) -> None:
        self.panel = panel
        self.kind = kind

    def _matrix(self) -> dict:
        result = self.panel.controller.result or {}
        if self.kind == "forster":
            return extract_forster(result)
        return (result.get("crosstalk_matrices") or {}).get(self.kind) or {}

    def columns(self) -> list[dict]:
        matrix = self._matrix()
        cols = [{"key": "row", "title": "", "description": "The row of the matrix."}]
        for i, name in enumerate(matrix.get("columns") or []):
            cols.append({"key": f"c{i}", "title": str(name), "format": "%.4e", "description": f"Column {name} of the {self.kind} matrix."})
        return cols

    def rows(self) -> list[dict]:
        if self.kind == "signals":
            return [
                {"laser": str(r.get("laser", "")), "detector": str(r.get("detector", "")), "dye": str(r.get("dye", "")),
                 "intensity": float(r.get("intensity", 0.0))}
                for r in (self.panel.controller.result or {}).get("detector_signals", [])
            ]
        matrix = self._matrix()
        out = []
        for label, values in zip(matrix.get("rows") or [], matrix.get("values") or []):
            rec = {"row": str(label)}
            for i, value in enumerate(values):
                rec[f"c{i}"] = float(value)
            out.append(rec)
        return out


class LightPathPanel:
    """What the specs of ``lightpath.view.json`` read and call."""

    TABS = ("Signals", "Excitation", "Emission", "Detected", "Förster radius")

    def __init__(self, controller, graph_control, *, browse: Callable[[str], None], ask_name: Callable[..., None],
                 show_help: Callable[[], None], start_guide: Callable[[], None], focus_graph: Callable[[], None] | None = None) -> None:
        self.controller = controller
        self.graph_control = graph_control
        self._browse, self._ask_name = browse, ask_name
        self._help, self._guide = show_help, start_guide
        self.message: tuple[str, str] | None = None
        self.selected_type = ""
        self.selected_saved = ""
        self.source_node = self.target_node = ""
        self.source_port = self.target_port = 0
        self.selected_link = None
        self.want_list = False
        self.signals = ResultTable(self, "signals")
        self.excitation = ResultTable(self, "excitation")
        self.emission = ResultTable(self, "emission")
        self.detected = ResultTable(self, "detected")
        self.forster = ResultTable(self, "forster")

    # -- fields -------------------------------------------------------------------------------------------- #
    running = property(lambda self: bool(self.controller.running))
    remote = property(lambda s: s.controller.remote, lambda s, v: setattr(s.controller, "remote", bool(v)))
    auto_update = property(lambda s: s.controller.auto_update, lambda s, v: setattr(s.controller, "auto_update", bool(v)))
    operation_name = property(lambda s: s.controller.operation_name, lambda s, v: setattr(s.controller, "operation_name", str(v)))
    show_minimap = property(lambda s: s.graph_control.show_minimap, lambda s, v: setattr(s.graph_control, "show_minimap", bool(v)))

    @property
    def db_path(self) -> str:
        return self.controller.db_path or ""

    @db_path.setter
    def db_path(self, value: str) -> None:
        self.controller.db_path = str(value).strip() or None

    # -- state the specs ask for ------------------------------------------------------------------------- #
    def has_selection(self) -> bool:
        from emtk import nodes

        editor = self.graph_control.editor
        return bool(nodes.get_selected_nodes(editor) or nodes.get_selected_links(editor))

    def has_instrument(self) -> bool:
        return bool((self.controller.result or {}).get("instrument_setting"))

    def enabled(self, name: str) -> bool:
        busy = self.running
        if name == "stop":
            return busy
        if name in ("guide", "help"):
            return True
        if name == "export_instrument":
            return self.has_instrument()
        if name == "delete_selection":
            return not busy and self.has_selection()
        if name == "add_selected":
            return not busy and bool(self.selected_type)
        if name == "fit":
            return True
        if name == "remove_link":
            return not busy and self.selected_link is not None
        if name in ("db_path", "remote", "auto_update", "show_minimap", "operation_name"):
            return True
        return not busy

    def palette_rows(self) -> list[dict]:
        return [{"id": d.id, "title": d.title} for d in optical_registry.all_types().values()]

    def saved_rows(self) -> list[dict]:
        return [{"name": str(r.get("name") or r.get("operation_id")), "operation_id": str(r["operation_id"])}
                for r in self.controller.saved]

    # -- the connection form -------------------------------------------------------------------------------- #
    def node_options(self) -> list:
        """``[(node id, label), ...]`` of the graph, for the From and To choices."""
        nodes = self.controller.document.nodes
        ids = [n.id for n in nodes]
        if self.source_node not in ids:
            self.source_node = ids[0] if ids else ""
        if self.target_node not in ids:
            self.target_node = ids[-1] if ids else ""
        return [(n.id, f"{n.title} [{n.id[:6]}]") for n in nodes]

    def link_rows(self) -> list[dict]:
        doc = self.controller.document
        out = []
        for e in doc.edges:
            s, t = doc.node(e.source), doc.node(e.target)
            out.append({"source": f"{s.title if s else e.source} : {e.source_port}", "target": f"{t.title if t else e.target} : {e.target_port}",
                        "_edge": e})
        return out

    def select_link(self, record: Any) -> None:
        self.selected_link = (record or {}).get("_edge") if isinstance(record, dict) else None

    def connect_ports(self) -> None:
        self._try("Connect Failed", self.controller.connect, self.source_node, self.source_port, self.target_node, self.target_port)

    def remove_link(self) -> None:
        if self.selected_link is not None:
            self.controller.remove_edge(self.selected_link)
            self.selected_link = None

    def delete_link(self, record: Any = None) -> None:
        """The Delete key on the links list: remove the selected row."""
        self.remove_link()

    # -- actions ------------------------------------------------------------------------------------------- #
    def _try(self, title: str, function: Callable, *args) -> Any:
        try:
            return function(*args)
        except Exception as exc:  # noqa: BLE001 - reported, as the Qt tool's error box
            self.controller.status = f"Error: {exc}"
            self.message = (title, str(exc))
            return None

    def save_graph(self) -> None:
        self._browse("save")

    def load_graph(self) -> None:
        self._browse("load")

    def export_instrument(self) -> None:
        if not self.has_instrument():
            self.message = ("Export Warning", "No instrument setting has been simulated yet.")
            return
        self._browse("instrument")

    def save_preset(self) -> None:
        self._ask_name("Save Optical Path Preset", "Preset name:", "", self._write_preset)

    def _write_preset(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        folder = preset_dir()

        def write():
            folder.mkdir(parents=True, exist_ok=True)
            self.controller.save_preset(folder / f"{name}.json")
            self.controller.status = f"Optical preset saved: {folder / (name + '.json')}"

        self._try("Save Failed", write)

    def save_mmfdb(self) -> None:
        self._ask_name("Save Simulation to MMFDB", "Name:", self.controller.operation_name or "Light path simulation", self._save_named)

    def _save_named(self, name: str) -> None:
        self.controller.operation_name = name.strip() or "Light path simulation"
        self.controller.start("save")

    def load_mmfdb(self) -> None:
        self.want_list = True
        self.controller.start("list")

    def select_saved(self, record: Any) -> None:
        self.selected_saved = str((record or {}).get("operation_id", "")) if isinstance(record, dict) else ""

    def activate_saved(self, record: Any) -> None:
        self.select_saved(record)
        self.load_saved()

    def load_saved(self) -> None:
        if self.selected_saved:
            self.controller.start("get", self.selected_saved)
            self.want_list = False

    def select_palette(self, record: Any) -> None:
        self.selected_type = str((record or {}).get("id", "")) if isinstance(record, dict) else ""

    def activate_palette(self, record: Any) -> None:
        self.select_palette(record)
        self.add_selected()

    def add_selected(self) -> None:
        if not self.selected_type:
            return
        x, y, w, h = self.graph_control._box
        position = self.graph_control.editor.canvas.to_grid((x + w / 2, y + h / 2))
        self._try("Add Failed", self.controller.add_node, self.selected_type, position)

    def reset(self) -> None:
        self._try("Reset Failed", self.controller.reset)

    def calculate(self) -> None:
        self.controller.start()

    def stop(self) -> None:
        self.controller.stop()

    def arrange(self) -> None:
        self._try("Arrange Failed", self.controller.arrange)

    def fit(self) -> None:
        self.graph_control.fit()

    def delete_selection(self) -> None:
        self.graph_control.delete_selection()

    def load_catalogue(self) -> None:
        self.controller.start("catalogue")

    def guide(self) -> None:
        self._guide()

    def help(self) -> None:
        self._help()
