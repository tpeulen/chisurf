"""The docking card of Structure Tools: FRET-restrained rigid-body docking, refinement and screening (IMP + IMP.bff).

The native counterpart of the Qt ``FretDockingTool``. The inputs are the Qt tool's own ``fret_dock.view.json`` spec
(read from the FRET plugin, not copied), drawn by emtk with spin fields and grouped captions; the structures are a
table (``data_table``), the results a sortable table, a score-versus-step plot and a 3D trace of the selected structure.
The state and the run live in :class:`~.docking_model.DockingSession`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from emtk import im, implot, implot3d
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.chimol_view import ChimolView
from chisurf.plugins.emtk_layout import layout_spec

from .docking_model import DockingSession
from .shell import CardShell

HERE = Path(__file__).resolve().parent
RES = HERE / "resources" / "docking"
FRET_SPEC = HERE.parent.parent / "fret" / "gui" / "fret_dock.view.json"
PDB_FILTER = "PDB (*.pdb *.ent);;All files (*)"
PROJECT_FILTER = "Docking project (*.json);;All files (*)"
FPS_FILTER = "FPS labelling (*.json *.txt);;All files (*)"
TABS = ("Results", "Score", "Structure")
#: The colour of each score curve (data colours).
CURVE_COLOURS = [(31, 119, 180, 255), (255, 127, 14, 255), (44, 160, 44, 255), (214, 39, 40, 255),
                 (148, 103, 189, 255), (140, 86, 75, 255), (227, 119, 194, 255), (127, 127, 127, 255)]

PDB_TABLE = {"sections": [{
    "type": "custom", "key": "data_table",
    "description": "The structures to dock, one per rigid body; the row number is the body id. The same file twice is a "
                   "homodimer. Delete removes the selected row.",
    "options": {"source": "pdb_rows", "height": 110, "row_key": "body", "selected_call": "select_pdb",
                "delete_call": "delete_pdb",
                "columns": [{"key": "body", "title": "Body", "width": 54, "description": "The body id of the structure."},
                            {"key": "file", "title": "Structure", "description": "File name; the full path is in the tooltip."},
                            {"key": "folder", "title": "Folder", "description": "The folder the file is in."}]}}]}

RESULT_TABLE = {"sections": [{
    "type": "custom", "key": "data_table",
    "description": "One row per result; runs accumulate until Clear. Click a header to sort (best score first); "
                   "select a row to show that structure.",
    "options": {"source": "result_rows", "expand": True, "reserve": 4, "row_key": "key", "selected_call": "select_result",
                "sort": {"key": "score", "descending": False}, "status": True,
                "columns": [{"key": "trial", "title": "Trial", "width": 60, "description": "Trial number of a repeated run."},
                            {"key": "type", "title": "Type", "width": 70, "description": "dock, mc or refine."},
                            {"key": "score", "title": "Score", "width": 90, "format": "%.2f", "description": "The restraint score; lower is better."},
                            {"key": "distances", "title": "Distances", "width": 80, "description": "Number of distance restraints scored."},
                            {"key": "best_pdb", "title": "Best PDB", "description": "The docked structure of the result."}]}}]}


class DockingView:
    """What the tables read and call."""

    def __init__(self, card: "DockingCard") -> None:
        self.card = card
        self.session = card.session
        self.pdb_selected = -1

    @property
    def pdb_rows(self):
        from .fps_model import Rows

        rows = Rows([{"body": i, "file": Path(p).name, "folder": str(Path(p).parent), "path": p}
                     for i, p in enumerate(self.session.pdb_files)])
        rows.revision = hash(tuple(self.session.pdb_files))
        return rows

    def select_pdb(self, record) -> None:
        self.pdb_selected = record["body"] if isinstance(record, dict) else -1
        if isinstance(record, dict):
            self.session.show_structures(record["path"])

    def delete_pdb(self, record) -> None:
        if isinstance(record, dict) and self.session.remove_pdb(record["body"]):
            self.pdb_selected = -1
            self.card.session.say(f"Removed body {record['body']}.")

    @property
    def result_rows(self):
        rows = self.session.rows
        for i, row in enumerate(rows):
            row.setdefault("key", f"{row['type']}-{row['trial']}-{i}")
        return rows

    def select_result(self, record) -> None:
        if isinstance(record, dict):
            index = next((i for i, r in enumerate(self.session.rows) if r is record), -1)
            self.session.select_row(index)

    def enabled(self, name: str) -> bool:
        return not (self.card.blocked or self.session.running)


class DockingCard(CardShell):
    """The docking window."""

    def __init__(self, session: DockingSession | None = None) -> None:
        self.session = session or DockingSession()
        self.tab = TABS[0]
        spec = json.loads(FRET_SPEC.read_text(encoding="utf-8"))
        _spin(spec["sections"])
        self.spec = layout_spec(spec)
        super().__init__("FRET Docking", RES, "dock")
        self.view = DockingView(self)
        self.form = FormState(on_used=self.used)
        self.pdb_form = FormState(on_used=self.used)
        self.result_form = FormState(on_used=self.used)
        self.session.on_change = self.request_frame
        self.error_shown = ""
        #: The Structure tab's molecular viewer (chimol, as the Qt docking window embeds it).
        self.chimol = ChimolView()
        self._chimol_path = ""

    def build_docks(self) -> DockManager:
        docks = DockManager(Split("h", 0.46, Region("inputs"), Region("results")))
        docks.add_window("inputs", "Inputs", self._draw_inputs, dock="inputs", closable=False)
        docks.add_window("results", "Results", self._draw_results, dock="results", closable=False)
        return docks

    # ── actions ───────────────────────────────────────────────────────────

    def sync(self) -> None:
        self.status, self.status_error = self.session.status, self.session.status_error
        self.request_frame()

    def load_project(self) -> None:
        self.open_file("Load docking project", PROJECT_FILTER, self._load_project, current=self.session.fps_json)

    def _load_project(self, path: str) -> None:
        if self.session.load_project(path):
            self.used("project")
        self.sync()

    def save_project(self) -> None:
        directory = os.path.dirname(self.session.fps_json) if self.session.fps_json else ""
        self.save_file("Save docking project", PROJECT_FILTER, self._save_project, filename="docking_project.json",
                       directory=directory)

    def _save_project(self, path: str) -> None:
        if not str(path).endswith(".json"):
            path = f"{path}.json"
        self.session.save_project(path)
        self.sync()

    def pick_fps(self) -> None:
        self.open_file("Select fps.json or FPS LPs .txt", FPS_FILTER, self._set_fps, current=self.session.fps_json)

    def _set_fps(self, path: str) -> None:
        self.session.fps_json = path
        self.used("fps_json")
        self.sync()

    def pick_output(self) -> None:
        self.open_file("Output directory", "All files (*)", self._set_output, current=self.session.output_dir, folder=True)

    def _set_output(self, path: str) -> None:
        self.session.output_dir = path
        self.used("output_dir")
        self.sync()

    def add_pdbs(self) -> None:
        self.open_file("Add PDB file", PDB_FILTER, lambda p: self._add_pdb([p]),
                       current=self.session.pdb_files[-1] if self.session.pdb_files else "")

    def _add_pdb(self, paths: list[str]) -> None:
        self.session.add_pdbs(paths)
        self.session.say(f"Added {len(paths)} structure(s): {len(self.session.pdb_files)} rigid bodies.")
        self.used("pdb")
        self.sync()

    def take_drop(self, paths: list[str]) -> bool:
        """Dropped files: a ``.pdb`` becomes the next rigid body, a ``.json`` / ``.txt`` the fps file (a docking
        project .json that has ``pdb_paths`` is loaded as a project)."""
        taken = False
        for path in paths:
            low = path.lower()
            if low.endswith((".pdb", ".ent")) and os.path.isfile(path):
                self.session.add_pdbs([path])
                taken = True
            elif low.endswith((".json", ".txt")) and os.path.isfile(path):
                if low.endswith(".json") and _is_project(path):
                    taken = self.session.load_project(path) or taken
                else:
                    self.session.fps_json = path
                    taken = True
        self.session.say("Dropped files taken." if taken else "No PDB, fps.json or project file among the dropped paths.",
                         not taken)
        self.sync()
        return taken

    def run(self) -> None:
        if self.session.start():
            self.used("run")
        self.sync()

    def clear(self) -> None:
        self.session.clear_results()
        self.session.say("Results cleared.")
        self.sync()

    # ── frame ─────────────────────────────────────────────────────────────

    def before_frame(self) -> None:
        if self.session.poll():
            self.sync()
        if self.session.running:
            self.request_frame()

    def animating(self) -> bool:
        return super().animating() or self.session.running

    def next_frame_in(self):
        return 0.05 if self.session.running else super().next_frame_in()

    def _draw_inputs(self, box) -> None:
        s = self.session
        running = s.running
        pressed = self.toolbar([
            {"label": "Project", "key": "project", "enabled": not running, "tip": "Load a docking project (.json): PDBs, fps.json and parameters."},
            {"label": "Save", "key": "save", "enabled": not running, "tip": "Save the current inputs and parameters as a docking project."},
            {"label": "fps.json", "key": "fps_pick", "enabled": not running, "tip": "Choose the labelling/distance fps.json (or FPS LPs .txt) file."},
            {"label": "Output", "key": "out_pick", "enabled": not running, "tip": "Choose the output directory."},
            {"label": "Run", "key": "run", "enabled": not running, "tip": "Run the selected operation; results are appended to the table."},
            {"label": "Stop", "key": "stop", "enabled": running, "tip": "Stop the run (a docking process is terminated)."},
            {"label": "Clear", "key": "clear", "enabled": not running, "tip": "Clear the results table and the score plot."},
            *self.help_buttons(),
        ])
        {None: lambda: None, "project": self.load_project, "save": self.save_project, "fps_pick": self.pick_fps,
         "out_pick": self.pick_output, "run": self.run, "stop": s.stop, "clear": self.clear,
         "guide": self.start_guide, "help": self.show_help}[pressed]()
        if running:
            im.progress_bar(s.progress, (-1, 0), s.progress_text or "running...")
            self.remember("progress")
        self.status_line()
        im.separator()
        im.text("PDB rigid bodies (one per body)")
        pressed = self.toolbar([
            {"label": "Add Files", "key": "add_pdb", "enabled": not running, "tip": "Add a structure file as the next rigid body (a dropped .pdb does the same)."},
            {"label": "Remove", "key": "remove_pdb", "enabled": self.view.pdb_selected >= 0 and not running, "tip": "Remove the selected rigid body."},
            {"label": "Clear List", "key": "clear_pdb", "enabled": bool(s.pdb_files) and not running, "tip": "Remove every rigid body."},
        ])
        if pressed == "add_pdb":
            self.add_pdbs()
        elif pressed == "remove_pdb":
            self.view.delete_pdb({"body": self.view.pdb_selected})
            self.sync()
        elif pressed == "clear_pdb":
            s.pdb_files.clear()
            self.view.pdb_selected = -1
            s.say("Removed every rigid body.")
            self.sync()
        self.pdb_form.rects.clear()
        draw_form(PDB_TABLE, self.view, self.pdb_form)
        self.item_rects.update(self.pdb_form.rects)
        self.form.rects.clear()
        im.begin_disabled(running)
        draw_form(self.spec, s, self.form)
        im.end_disabled()
        self.item_rects.update(self.form.rects)

    def _draw_results(self, box) -> None:
        from emtk.im_core import Col

        for i, tab in enumerate(TABS):
            if i:
                im.same_line()
            selected = tab == self.tab
            if selected:
                im.push_style_color(Col.BUTTON, im.get_style().color(Col.TAB_SELECTED))
            if im.button(tab):
                self.tab = tab
            if selected:
                im.pop_style_color(1)
            im.set_item_tooltip({"Results": "One row per docking result; click a header to sort.",
                                 "Score": "The restraint score against the step of the run, one curve per trial.",
                                 "Structure": "A 3D trace of the selected structure."}[tab])
            self.remember(f"tab_{tab}")
        im.separator()
        {"Results": self._draw_table, "Score": self._draw_score, "Structure": self._draw_structure}[self.tab]()

    def _draw_table(self) -> None:
        self.result_form.rects.clear()
        if not self.session.rows:
            im.text_wrapped("No results yet: add the structures and the fps.json, then press Run.")
            self.remember("empty_results")
        draw_form(RESULT_TABLE, self.view, self.result_form)
        self.item_rects.update(self.result_form.rects)

    def _draw_score(self) -> None:
        curves = self.session.curves
        if not curves:
            im.text_wrapped("No score trace yet: it is drawn while a docking run is going on.")
            self.remember("empty_score")
            return
        if implot.begin_plot("##dockscore", (-1, -1)):
            implot.setup_axes("Step", "Total score")
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for i, (path, (frames, scores)) in enumerate(sorted(curves.items())):
                label = Path(path).parent.name if "trial_" in path else "score"
                implot.set_next_line_style(CURVE_COLOURS[i % len(CURVE_COLOURS)], 2.0)
                implot.plot_line(label, np.asarray(frames, dtype=float), np.asarray(scores, dtype=float))
            implot.end_plot()
            im.set_item_tooltip("Total restraint score against the step of the run (CG iteration or MC frame).")
            self.remember("score_plot")

    def _draw_structure(self) -> None:
        s = self.session
        if not s.preview:
            im.text_wrapped("No structure to show: select a structure of the list or a result.")
            self.remember("empty_structure")
            return
        if len(s.preview) > 1:
            im.text(f"Model {s.preview_index + 1} of {len(s.preview)}")
            im.same_line()
            if im.button("Previous") and s.preview_index > 0:
                s.preview_index -= 1
            im.set_item_tooltip("The previous docked model.")
            self.remember("preview_prev")
            im.same_line()
            if im.button("Next") and s.preview_index < len(s.preview) - 1:
                s.preview_index += 1
            im.set_item_tooltip("The next docked model.")
            self.remember("preview_next")
        path = str(s.preview[min(s.preview_index, len(s.preview) - 1)])
        viewer = self.chimol.viewer
        if viewer is not None:
            if path != self._chimol_path:
                for obj in viewer.list_objects():
                    viewer.remove_object(obj["id"])
                self.chimol.app.load(path)
                self.chimol.sync_panel()
                self._chimol_path = path
            self.chimol.draw(enabled=not self.blocked)
            im.set_item_tooltip("The structure as cartoon; drag to rotate, wheel to zoom.")
            self.remember("structure_plot")
            return
        im.text_wrapped(f"The molecular viewer could not start ({self.chimol.error}); showing the CA / P trace.")
        back = s.backbone(path)
        if back is None:
            im.text_wrapped("The structure could not be read.")
            return
        xyz, chains = back
        if implot3d.begin_plot("##dockstruct", (-1, -1), implot3d.FLAGS_NO_LEGEND):
            implot3d.setup_axes("x [A]", "y [A]", "z [A]")
            for i, chain in enumerate(dict.fromkeys(chains)):
                pts = xyz[chains == chain]
                colour = tuple(c / 255 for c in CURVE_COLOURS[i % len(CURVE_COLOURS)])
                implot3d.plot_line(f"chain {chain}", pts[:, 0], pts[:, 1], pts[:, 2],
                                   spec=implot3d.Spec(line_color=colour))
            implot3d.end_plot()
            im.set_item_tooltip("The CA / P trace of the structure, one colour per chain; drag to rotate, wheel to zoom.")
            self.remember("structure_plot")

    # ── persistence ───────────────────────────────────────────────────────

    def export_settings(self) -> dict:
        return {**self.session.export_settings(), "tab": self.tab}

    def restore_settings(self, settings: dict) -> None:
        if not isinstance(settings, dict):
            return
        self.session.restore_settings(settings)
        if settings.get("tab") in TABS:
            self.tab = settings["tab"]

    def close(self) -> None:
        self.session.close()
        self.chimol.close()


def _spin(sections) -> None:
    for section in sections:
        if section.get("type") == "value" and section.get("kind") in ("int", "float") and not section.get("read_only"):
            section["style"] = "spin"
        _spin(section.get("sections", []))


def _is_project(path: str) -> bool:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "pdb_paths" in data


def make_app(session: DockingSession | None = None) -> DockingCard:
    """The docking card."""
    from chisurf.emtk.i18n import install

    install()
    return DockingCard(session)


__all__ = ["DockingCard", "make_app"]
