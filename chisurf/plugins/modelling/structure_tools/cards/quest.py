"""The QuEst card of Structure Tools: Brownian-dynamics simulation of dye quenching (PET) and FRET on a protein.

The native counterpart of the Qt ``QuEstTool`` / ``TransientDecayGenerator``. The science and the project model are
the ``quest`` package's (``quest.gui.form_model.ProjectFormModel`` is Qt-free: the project dict *is* the state, so what
the window saves is what the CLI and the web UI read). This file draws it: the Project panel of ``quest.view.json``
(read from the quest package, not copied), the quenching table as a ``data_table``, the three result plots, a 3D trace
of the structure with the attachment sites, and the project JSON.

QuEst needs the IMP.bff quenching tables (``IMP.bff.quenching``) to build even an empty project; where the Python
environment has none, the card says so and offers Retry, as the Qt hub's error panel does.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot, implot3d
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.plugins.emtk_layout import layout_spec

from .fps_model import Rows
from .shell import CardShell

HERE = Path(__file__).resolve().parent
RES = HERE / "resources" / "quest"
TABS = ("Plots & Dynamics", "3D Structure", "Quenching Chemistry", "Project JSON")
STRUCTURE_FILTER = "Structures (*.pdb *.ent *.cif *.pdb.gz);;All files (*)"
PROJECT_FILTER = "QuEst project (*.json);;All files (*)"
COLOURS = {"donor": (31, 119, 180, 255), "fret": (214, 39, 40, 255), "traj": (44, 160, 44, 255), "acf": (148, 103, 189, 255)}

QUENCHER_COLUMNS = [
    {"key": "residue", "title": "Residue", "width": 80, "description": "Three-letter amino-acid code."},
    {"key": "kQ", "title": "kQ (1/ns)", "width": 100, "editable": True,
     "description": "Rate at which this residue type quenches the dye while the two are in contact; overlapping contact spheres add up."},
    {"key": "quench_radius", "title": "Radius (A)", "width": 100, "editable": True,
     "description": "Distance from the dye centre to the residue's quenching centre within which quenching occurs; empty inherits the project-wide fallback contact radius."},
    {"key": "quench_atoms", "title": "Atoms", "editable": True,
     "description": "Atom names whose centroid defines the residue's quenching centre (the redox-active moiety, not CB)."},
    {"key": "slow_factor", "title": "Slow factor", "width": 90, "editable": True,
     "description": "Factor between 0 and 1 scaling the dye's diffusion near this residue type (unspecific stickiness); overlapping residues multiply."},
]
QUENCH_TABLE = {"sections": [{
    "type": "custom", "key": "data_table",
    "description": "The PET quenching chemistry of every amino acid. Double-click a cell of kQ, Radius, Atoms or Slow factor to edit.",
    "options": {"source": "quencher_rows", "editable": True, "expand": True, "reserve": 4, "row_key": "residue",
                "edited_call": "edit_quencher", "status": True, "columns": QUENCHER_COLUMNS}}]}
JSON_VIEW = {"sections": [{"type": "custom", "key": "code_editor", "target": "json_text",
                           "options": {"language": "JSON", "read_only": True, "expand": True, "height": 200}}]}


def quest_spec() -> dict:
    """The Project panel of the quest package's view spec, as emtk draws it (folds, spin fields, capped widths)."""
    import quest.gui.generate_view_spec as gvs

    path = gvs.view_spec_path()
    full = json.loads(Path(path).read_text(encoding="utf-8"))
    project = next(s for d in full["sections"] if d.get("type") == "dock_area" for s in d["sections"]
                   if s.get("title") == "Project")
    panels = []
    for panel in copy.deepcopy(project["sections"]):
        panel["sections"] = [s for s in panel["sections"] if s.get("type") != "table"]
        panel["collapsible"] = True
        for sec in panel["sections"]:
            if sec.get("attr") == "pdb":
                sec["kind"] = "str"
                sec["elide"] = "start"
            if sec.get("type") == "value" and sec.get("kind") in ("int", "float") and not sec.get("read_only"):
                sec["style"] = "spin"
        panels.append(panel)
    return layout_spec({"sections": panels})


class QuestSession:
    """The QuEst project model and the run, or the reason there is none."""

    def __init__(self, model: Any | None = None) -> None:
        self.model = model
        self.error = ""
        self.status_error = False
        self.running = False
        self.message = ""
        self.structure = None
        self.structure_path = ""
        self.json_cache = ""
        if self.model is None:
            self.build()

    def build(self) -> bool:
        """Create the project model; the failure (missing IMP.bff quenching tables, ...) is the status."""
        try:
            from quest.gui.form_model import ProjectFormModel

            self.model = ProjectFormModel(locale="en")
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.model = None
            self.error = f"{type(exc).__name__}: {exc}"
            return False
        self.error = ""
        return True

    @property
    def ready(self) -> bool:
        return self.model is not None

    # ── files ─────────────────────────────────────────────────────────────

    def load_structure(self, path: str) -> bool:
        if not self.ready:
            return False
        if not Path(path).is_file():
            self.say(f"No such file: {path}", True)
            return False
        self.model.pdb = path
        self.model.auto_attach_to_structure()
        self.structure = None
        self.say(f"Loaded {Path(path).name}")
        return True

    def load_project(self, path: str) -> bool:
        if not self.ready:
            return False
        try:
            self.model.load_project(path)
        except Exception as exc:  # noqa: BLE001
            self.say(f"Failed to load the project: {exc}", True)
            return False
        self.structure = None
        self.say(f"Loaded {Path(path).name}")
        return True

    def save_project(self, path: str) -> bool:
        if not self.ready:
            return False
        try:
            self.model.save_project(path)
        except Exception as exc:  # noqa: BLE001
            self.say(f"Failed to save the project: {exc}", True)
            return False
        self.say(f"Saved {Path(path).name}")
        return True

    def say(self, text: str, error: bool = False) -> None:
        self.message, self.status_error = text, error
        if self.ready:
            self.model.status = text

    # ── run ───────────────────────────────────────────────────────────────

    def simulate(self) -> bool:
        if not self.ready or self.running:
            return False
        problems = self.model.validate()
        if problems:
            self.say(f"Cannot simulate: {problems[0]}", True)
            return False
        self.model.start_simulation()
        self.running = True
        return True

    def cancel(self) -> bool:
        return bool(self.ready and self.model.cancel_simulation())

    def poll(self) -> bool:
        """Apply a finished run on the UI thread; True when something changed."""
        if not self.ready or not self.running:
            return False
        if self.model.simulation_running:
            return True
        self.running = False
        self.model.poll_simulation()
        self.message = self.model.status
        self.status_error = self.message.lower().startswith(("failed", "error", "simulation failed"))
        return True

    def wait(self, timeout: float = 120.0) -> bool:
        import time

        end = time.monotonic() + timeout
        while self.running and time.monotonic() < end:
            time.sleep(0.02)
            self.poll()
        return not self.running

    # ── what the tabs read ────────────────────────────────────────────────

    def quencher_rows(self) -> Rows:
        rows = Rows(self.model.quencher_rows()) if self.ready else Rows()
        rows.revision = hash(json.dumps(self.model.project.get("amino_acid_interactions", {}), sort_keys=True,
                                        default=str)) if self.ready else 0
        return rows

    def edit_quencher(self, record, key: str, value) -> None:
        if not self.ready or not isinstance(record, dict):
            return
        rows = self.model.quencher_rows()
        index = next((i for i, r in enumerate(rows) if r["residue"] == record["residue"]), -1)
        if index >= 0:
            try:
                self.model.update_quencher_cell(index, key, value)
            except ValueError:
                self.say(f"Not a number: {value}", True)

    def reset_quencher_defaults(self) -> None:
        from quest.project import template_project

        self.model.project["amino_acid_interactions"] = template_project().get("amino_acid_interactions", {})
        self.model._notify()
        self.say("Quenching chemistry reset to the defaults.")

    @property
    def json_text(self) -> str:
        return json.dumps(self.model.to_project_dict(), indent=2) if self.ready else ""

    def series(self) -> dict[str, list[dict]]:
        if not self.ready:
            return {"decay": [], "trajectory": [], "acf": []}
        return {"decay": self.model.decay_series(), "trajectory": self.model.trajectory_series(),
                "acf": self.model.autocorrelation_series()}

    def backbone(self):
        """The CA trace of the loaded structure and the attachment sites ``(donor, acceptor)``, or None."""
        pdb = str(self.model.project.get("pdb") or "") if self.ready else ""
        if not pdb or not Path(pdb).is_file():
            return None
        if self.structure is None or self.structure_path != pdb:
            try:
                import chisurf.core.structure as cs_structure

                self.structure, self.structure_path = cs_structure.Structure(pdb), pdb
            except Exception:  # noqa: BLE001
                self.structure, self.structure_path = None, pdb
                return None
        atoms = self.structure.atoms
        keep = np.isin(atoms["atom_name"], ["CA", "P"])
        trace = np.asarray(atoms["xyz"])[keep]

        def site(chain, residue, atom):
            try:
                mask = (atoms["chain"] == str(chain)) & (atoms["res_id"] == int(residue)) & (atoms["atom_name"] == str(atom))
                hit = np.asarray(atoms["xyz"])[mask]
                return hit[0] if len(hit) else None
            except (TypeError, ValueError):
                return None

        project = self.model.project
        donor = site(project.get("attachment", {}).get("chain"), project.get("attachment", {}).get("residue"),
                     project.get("attachment", {}).get("atom"))
        acceptor = None
        dyes = project.get("fret", {}).get("dyes", [])
        if project.get("fret", {}).get("enabled") and len(dyes) > 1:
            att = dyes[1].get("attachment", {})
            acceptor = site(att.get("chain"), att.get("residue"), att.get("atom"))
        return trace, donor, acceptor

    # ── persistence ───────────────────────────────────────────────────────

    def export_settings(self) -> dict:
        return {"project": self.model.to_project_dict()} if self.ready else {}

    def restore_settings(self, settings: dict) -> None:
        if self.ready and isinstance(settings, dict) and isinstance(settings.get("project"), dict):
            try:
                self.model.load_project_dict(settings["project"])
            except Exception as exc:  # noqa: BLE001
                self.say(f"The saved project could not be restored: {exc}", True)


class QuestCard(CardShell):
    """The QuEst window."""

    def __init__(self, session: QuestSession | None = None) -> None:
        self.session = session or QuestSession()
        self.tab = TABS[0]
        self.spec = quest_spec() if self.session.ready else {"sections": []}
        super().__init__("QuEst", RES, "quest")
        self.form = FormState(on_used=self.used)
        self.table_form = FormState(on_used=self.used)
        self.json_form = FormState(on_used=self.used)

    def build_docks(self) -> DockManager:
        docks = DockManager(Split("h", 0.40, Region("inputs"), Region("results")))
        docks.add_window("inputs", "Inputs", self._draw_inputs, dock="inputs", closable=False)
        docks.add_window("results", "Results", self._draw_results, dock="results", closable=False)
        return docks

    # ── actions ───────────────────────────────────────────────────────────

    def sync(self) -> None:
        self.status = self.session.message or (self.session.model.status if self.session.ready else "")
        self.status_error = self.session.status_error
        self.request_frame()

    def load_structure(self) -> None:
        self.open_file("Open a structure", STRUCTURE_FILTER, self._load_structure,
                       current=str(self.session.model.project.get("pdb") or "") if self.session.ready else "")

    def _load_structure(self, path: str) -> None:
        if self.session.load_structure(path):
            self.used("load_pdb")
        self.sync()

    def load_project(self) -> None:
        self.open_file("Load project", PROJECT_FILTER, self._load_project)

    def _load_project(self, path: str) -> None:
        if self.session.load_project(path):
            self.used("load_project")
        self.sync()

    def save_project(self) -> None:
        self.save_file("Save project", PROJECT_FILTER, self._save_project, filename="project.json")

    def _save_project(self, path: str) -> None:
        if not str(path).endswith(".json"):
            path = f"{path}.json"
        if self.session.save_project(path):
            self.used("save_project")
        self.sync()

    def simulate(self) -> None:
        if self.session.simulate():
            self.used("simulate")
        self.sync()

    def take_drop(self, paths: list[str]) -> bool:
        """A dropped ``.json`` is a project, a structure file is the structure (the first of each kind is taken)."""
        taken = False
        for path in paths:
            low = path.lower()
            if low.endswith(".json") and os.path.isfile(path):
                taken = self.session.load_project(path)
            elif low.endswith((".pdb", ".ent", ".cif", ".pdb.gz")) and os.path.isfile(path):
                taken = self.session.load_structure(path)
            if taken:
                break
        if not taken:
            self.session.say("No structure or project file among the dropped paths.", True)
        self.sync()
        return taken

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
        if not s.ready:
            self._draw_unavailable()
            return
        running = s.running
        pressed = self.toolbar([
            {"label": "Simulate", "key": "simulate", "enabled": not running, "tip": "Run the simulation: dye diffusion, PET quenching and (with FRET on) the donor decay."},
            {"label": "Cancel", "key": "cancel", "enabled": running, "tip": "Ask the run to stop; its result is discarded."},
            {"label": "Load PDB...", "key": "load_pdb", "enabled": not running, "tip": "Choose a structure; a valid attachment site is picked from it."},
            {"label": "Load project...", "key": "load_project", "enabled": not running, "tip": "Read a QuEst project JSON written by any surface."},
            {"label": "Save project...", "key": "save_project", "tip": "Write the form as project JSON, the file the CLI and the web UI read."},
            *self.help_buttons(),
        ])
        {None: lambda: None, "simulate": self.simulate, "cancel": lambda: (s.cancel(), self.sync()),
         "load_pdb": self.load_structure, "load_project": self.load_project, "save_project": self.save_project,
         "guide": self.start_guide, "help": self.show_help}[pressed]()
        im.text_wrapped(f"State: {s.model.status}")
        self.remember("state")
        im.separator()
        self.form.rects.clear()
        im.begin_disabled(running)
        draw_form(self.spec, s.model, self.form)
        im.end_disabled()
        self.item_rects.update(self.form.rects)

    def _draw_unavailable(self) -> None:
        im.text("QuEst cannot start here")
        im.separator()
        im.text_wrapped("QuEst needs the IMP.bff quenching tables (IMP.bff.quenching), which this Python environment "
                        "does not provide. The reason it reported:")
        im.text_wrapped(self.session.error)
        self.remember("unavailable")
        if im.button("Retry"):
            self.session.build()
            if self.session.ready:
                self.spec = quest_spec()
            self.sync()
        im.set_item_tooltip("Try to load QuEst again (after installing the IMP.bff quenching module).")
        self.remember("retry")
        im.same_line()
        pressed = self.toolbar(self.help_buttons())
        if pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()

    def _draw_results(self, box) -> None:
        if not self.session.ready:
            im.text_wrapped("The results appear here once QuEst can run.")
            return
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
            im.set_item_tooltip({
                "Plots & Dynamics": "The fluorescence decay, the dye trajectory and the position autocorrelation of the last run.",
                "3D Structure": "The structure with the donor and acceptor attachment sites.",
                "Quenching Chemistry": "The quenching parameters of every amino acid.",
                "Project JSON": "The project as the CLI and the web UI read it (read only).",
            }[tab])
            self.remember(f"tab_{tab}")
        im.separator()
        {"Plots & Dynamics": self._draw_plots, "3D Structure": self._draw_structure,
         "Quenching Chemistry": self._draw_quenching, "Project JSON": self._draw_json}[self.tab]()

    def _draw_plots(self) -> None:
        series = self.session.series()
        if not any(series.values()):
            im.text_wrapped("No result yet: set the structure and the dye, then press Simulate.")
            self.remember("empty_plots")
            return
        height = max(90.0, (im.get_content_region_avail()[1] - 16.0) / 3.0)
        plots = (("##decay", "Time (ns)", "Counts", "decay", "Fluorescence decay (donor and FRET)", True, False),
                 ("##traj", "Time (ns)", "|r - <r>| (A)", "trajectory", "Dye trajectory", False, False),
                 ("##acf", "Lag (ns)", "ACF", "acf", "Position autocorrelation", False, True))
        for pid, xl, yl, key, tip, log_y, log_x in plots:
            if implot.begin_plot(pid, (-1, height)):
                implot.setup_axes(xl, yl)
                if log_y:
                    implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                if log_x:
                    implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                implot.setup_legend(implot.LOCATION_NORTH_EAST)
                for j, line in enumerate(series[key]):
                    colour = COLOURS[("donor" if j == 0 else "fret") if key == "decay" else
                                     "traj" if key == "trajectory" else "acf"]
                    x = np.asarray(line["x"], dtype=float)
                    y = np.asarray(line["y"], dtype=float)
                    if log_y:
                        y = np.where(y > 0, y, np.nan)
                    implot.set_next_line_style(colour, 2.0)
                    implot.plot_line(str(line["name"]), x, y)
                implot.end_plot()
                im.set_item_tooltip(tip)
                self.remember(f"plot_{key}")

    def _draw_structure(self) -> None:
        data = self.session.backbone()
        if data is None:
            im.text_wrapped("No structure loaded: press Load PDB... (or drop a .pdb file on the window).")
            self.remember("empty_structure")
            return
        trace, donor, acceptor = data
        if implot3d.begin_plot("##questmol", (-1, -1)):
            implot3d.setup_axes("x [A]", "y [A]", "z [A]")
            implot3d.plot_line("backbone", trace[:, 0], trace[:, 1], trace[:, 2])
            if donor is not None:
                implot3d.plot_scatter("donor", [float(donor[0])], [float(donor[1])], [float(donor[2])],
                                      spec=implot3d.Spec(marker_size=7, marker_fill_color=(0.12, 0.47, 0.71, 1.0)))
            if acceptor is not None:
                implot3d.plot_scatter("acceptor", [float(acceptor[0])], [float(acceptor[1])], [float(acceptor[2])],
                                      spec=implot3d.Spec(marker_size=7, marker_fill_color=(0.84, 0.15, 0.16, 1.0)))
            implot3d.end_plot()
            im.set_item_tooltip("The CA / P trace of the structure with the donor (blue) and acceptor (red) attachment sites.")
            self.remember("structure_plot")

    def _draw_quenching(self) -> None:
        if im.button("Reset Defaults"):
            self.session.reset_quencher_defaults()
            self.sync()
        im.set_item_tooltip("Replace the table by the reference PET chemistry.")
        self.remember("reset_defaults")
        self.table_form.rects.clear()
        draw_form(QUENCH_TABLE, self.session, self.table_form)
        self.item_rects.update(self.table_form.rects)

    def _draw_json(self) -> None:
        self.json_form.rects.clear()
        draw_form(JSON_VIEW, self.session, self.json_form)
        self.item_rects.update(self.json_form.rects)

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
        if self.session.running:
            self.session.cancel()


def make_app(session: QuestSession | None = None) -> QuestCard:
    """The QuEst card."""
    from chisurf.emtk.i18n import install

    install()
    return QuestCard(session)


__all__ = ["QuestCard", "QuestSession", "make_app", "quest_spec"]
