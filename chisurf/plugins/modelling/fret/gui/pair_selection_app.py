"""The native pair selection window: which FRET pairs to measure to tell the conformations of a trajectory apart.

The native counterpart of the Qt ``FRETPairSelectionWindow``. The run is :func:`..core.pair_run.run_pair_selection`, the
function the Qt window calls too; this file is the session around it (a worker thread, the rows of the table) and the
window: the fields of the Qt window declared in ``pair_selection.view.json``, three file rows, a results table
(``data_table``) and a decay plot. The shell (dialogs, Help, guided tour) is the one the Structure Tools cards share.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.plugins.emtk_layout import LabelColumn, labelled, layout_spec
from chisurf.plugins.modelling.structure_tools.cards.shell import CardShell

from ..core.pair_run import PairParams, PairResult, run_pair_selection

HERE = Path(__file__).resolve().parent
RES = HERE / "resources" / "pair_selection"
SPEC = HERE / "pair_selection.view.json"
TRAJ_FILTER = "Trajectories (*.dcd *.xtc *.trr *.h5 *.nc *.pdb);;All files (*)"
TOP_FILTER = "PDB files (*.pdb);;All files (*)"
FPS_FILTER = "JSON-Files (*.fps.json *.json);;All files (*)"
EXPORT_FILTER = "Text files (*.txt);;All files (*)"
TOPOLOGY_SUFFIXES = (".pdb", ".ent", ".cif")

#: ``(key, caption, attr, dialog title, filters, tooltip, browse tooltip, placeholder)`` of the file rows, in order.
PATH_ROWS = (
    ("trajectory", "Trajectory", "trajectory", "Open Trajectory", TRAJ_FILTER,
     "The trajectory to select pairs from. Choose it with ... or drop it on the window.",
     "Choose the trajectory file.", "Drop a trajectory here or browse..."),
    ("topology", "Topology (optional)", "topology", "Open Topology", TOP_FILTER,
     "The PDB that names the atoms; a DCD stores coordinates only, so it needs one.",
     "Choose the topology PDB.", "PDB naming the atoms (needed for a DCD)"),
    ("fps_json", "FPS JSON (optional)", "fps_json", "Open FPS JSON", FPS_FILTER,
     "Labelling positions and distances: when given they are the candidate sites and pairs "
     "(the residue fields are then not used).",
     "Choose the FPS JSON file.", "Candidate pairs from an fps.json (optional)"),
)

RESULT_TABLE = {"sections": [{
    "type": "custom", "key": "data_table",
    "description": "The chosen pairs in the order they were added, with the mean RMSD after each.",
    "options": {"source": "result_rows", "height": 190, "row_key": "number",
                "columns": [{"key": "number", "title": "#", "width": 50, "description": "Order in which the pair was added."},
                            {"key": "pair", "title": "Pair", "description": "The two residues: chain:name+number - chain:name+number."},
                            {"key": "rmsd", "title": "<<RMSD>> (A)", "width": 120, "format": "%.2f",
                             "description": "Mean RMSD between the conformations the pairs chosen so far cannot distinguish."}]}}]}


@dataclass
class PairSession(PairParams):
    """The fields of the window (a form reads and writes them by name) and the run behind the Run button."""

    def __post_init__(self) -> None:
        self.result: PairResult | None = None
        self.rows: list[dict] = []
        self.running = False
        self.status = ""
        self.status_error = False
        self._queue: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self.on_change = lambda: None
        self.on_message = lambda title, text: None

    # form hooks
    def enabled(self, name: str) -> bool:
        if self.running:
            return False
        has_fps = bool(self.fps_json.strip()) and os.path.isfile(self.fps_json.strip())
        if name in ("chain", "residues", "atom"):
            return not has_fps
        if name == "use_av":
            return has_fps
        if name in ("av_samples", "av_max_points"):
            return has_fps and self.use_av
        return True

    def params(self) -> PairParams:
        return PairParams(**{k: getattr(self, k) for k in asdict(PairParams())})

    def say(self, text: str, error: bool = False) -> None:
        self.status, self.status_error = text, error
        self.on_change()

    # run
    def start(self) -> bool:
        """Run the selection on a worker (the table is emptied first, as the Qt window does)."""
        if self.running:
            return False
        self.result, self.rows = None, []
        self.running = True
        self.say("Running the pair selection...")
        params = self.params()
        self._thread = threading.Thread(target=self._work, args=(params,), daemon=True, name="pair-selection")
        self._thread.start()
        return True

    def _work(self, params: PairParams) -> None:
        try:
            result = run_pair_selection(params)
        except Exception as exc:  # noqa: BLE001 - shown in the window, as the Qt tool's error box
            self._queue.put(("error", str(exc)))
        else:
            self._queue.put(("done", result))
        self.on_change()

    def poll(self) -> bool:
        """Take the finished run, if any; True when the window must be redrawn."""
        changed = False
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                return changed
            changed = True
            self.running = False
            if kind == "error":
                self.say(f"FRET pair selection failed: {payload}", True)
                self.on_message("FRET pair selection failed", payload)
            else:
                self.result = payload
                self.rows = [{"number": n, "pair": pair, "rmsd": rmsd} for n, pair, rmsd in payload.rows()]
                self.say(f"{len(self.rows)} pairs chosen.")
                for text in payload.warnings:
                    self.on_message("AV backend unavailable", text)

    def wait(self, timeout: float = 120.0) -> bool:
        """Block until the run is over (tests); False on a timeout."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self.poll()
        return not self.running

    def export(self, path: str) -> bool:
        if self.result is None:
            self.say("Nothing to export: run the selection first.", True)
            return False
        self.result.export(path)
        self.say(f"Exported {len(self.rows)} pairs to {path}")
        return True

    def export_settings(self) -> dict:
        return asdict(self.params())

    def restore_settings(self, settings: dict) -> None:
        for key, default in asdict(PairParams()).items():
            if key in settings and isinstance(settings[key], type(default)):
                setattr(self, key, settings[key])


class _View:
    """What the results table reads."""

    def __init__(self, session: PairSession) -> None:
        self.session = session

    @property
    def result_rows(self):
        from chisurf.plugins.modelling.structure_tools.cards.fps_model import Rows

        rows = Rows(self.session.rows)
        rows.revision = id(self.session.result)
        return rows

    def enabled(self, name: str) -> bool:
        return True


class PairSelectionCard(CardShell):
    """The pair selection window."""

    def __init__(self, session: PairSession | None = None) -> None:
        self.session = session or PairSession()
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
        _spin(spec["sections"])
        self.spec = layout_spec(spec)
        self.labels = LabelColumn()
        super().__init__("Optimal FRET Pair Selection", RES, "pairs")
        self.view = _View(self.session)
        self.form = FormState(on_used=self.used)
        self.form.custom["pair_paths"] = self._draw_paths
        self.result_form = FormState(on_used=self.used)
        self.session.on_change = self.request_frame
        self.session.on_message = self.notify

    def build_docks(self) -> DockManager:
        docks = DockManager(Split("h", 0.52, Region("inputs"), Region("results")))
        docks.add_window("inputs", "Selection", self._draw_inputs, dock="inputs", closable=False)
        docks.add_window("results", "Results", self._draw_results, dock="results", closable=False)
        return docks

    # -- actions --------------------------------------------------------------------------------------------- #
    def browse(self, row: tuple) -> None:
        key, _caption, attr, title, filters = row[:5]
        current = getattr(self.session, attr)
        self.open_file(title, filters, lambda path: self.set_path(attr, path), current=current)

    def set_path(self, attr: str, path: str) -> None:
        setattr(self.session, attr, str(path))
        self.used(attr)
        self.used(f"{attr}_browse")                  # the tour's await steps name the button
        # The first tour card is naturally placed beside the trajectory row.  In
        # this two-dock layout that puts its navigation buttons over the results
        # table, whose input wins the click.  Once the awaited browse action is
        # complete, move the card to unused input-pane space so Next remains a
        # real, clickable tour control.
        if attr == "trajectory" and self.tour.active and self.tour.step_idx == 1:
            self.tour.card_offset = (-520.0, 320.0)
        self.session.say("")

    def run(self) -> None:
        if self.session.start():
            self.used("run")
            # Starting the calculation completes the guide's only remaining
            # action step.  The result step can be read while the worker runs.
            if self.tour.active and self.tour.step_idx == 4:
                self.tour.next()

    def export(self) -> None:
        if self.session.result is None:
            self.session.say("Nothing to export: run the selection first.", True)
            return
        directory = os.path.dirname(self.session.trajectory) if self.session.trajectory else ""
        self.save_file("Export pair selection", EXPORT_FILTER, self._export, filename="pair_selection.txt",
                       directory=directory)

    def _export(self, path: str) -> None:
        self.session.export(str(path))
        self.used("export")

    def take_drop(self, paths: list[str]) -> bool:
        """A PDB goes to Topology, a .json to FPS JSON, any other file to Trajectory."""
        taken = False
        for path in paths:
            if not os.path.isfile(path):
                continue
            low = path.lower()
            attr = "topology" if low.endswith(TOPOLOGY_SUFFIXES) else "fps_json" if low.endswith(".json") else "trajectory"
            setattr(self.session, attr, path)
            taken = True
        self.session.say("Dropped files taken." if taken else "No file among the dropped paths.", not taken)
        return taken

    # -- frame ----------------------------------------------------------------------------------------------- #
    def before_frame(self) -> None:
        if self.session.poll():
            self.status, self.status_error = self.session.status, self.session.status_error
        self.status, self.status_error = self.session.status, self.session.status_error

    def animating(self) -> bool:
        return super().animating() or self.session.running

    def next_frame_in(self):
        return 0.1 if self.session.running else super().next_frame_in()

    def label_column(self) -> float:
        if not self.labels.ready:
            captions = [r[1] for r in PATH_ROWS] + [s["label"] for s in labelled(self.spec["sections"])]
            self.labels.measure(captions)
            self.labels.pad(self.spec["sections"])
        return self.labels.x

    def _draw_paths(self, section, model, state, width) -> None:
        label_w = self.label_column()
        button_w = im.get_frame_height() + 6.0
        for row in PATH_ROWS:
            key, caption, attr, _title, _filters, tip, browse_tip, hint = row
            im.text(caption)
            im.same_line(label_w)
            im.set_next_item_width(max(80.0, width - label_w - button_w - 8.0))
            im.input_text(f"##{key}", getattr(self.session, attr) or "", hint=hint,
                          flags=im.InputTextFlags.READ_ONLY, elide_start=True)
            im.set_item_tooltip(tip)
            self.remember(key)
            im.same_line()
            if im.button(f"...##{key}.browse", (button_w, 0)) and not self.session.running:
                self.browse(row)
            im.set_item_tooltip(browse_tip)
            self.remember(f"{key}_browse")

    def _draw_inputs(self, box) -> None:
        s = self.session
        pressed = self.toolbar([
            {"label": "Run selection", "key": "run", "enabled": not s.running,
             "tip": "Compute the efficiencies and choose the most informative pairs."},
            {"label": "Export", "key": "export", "enabled": s.result is not None and not s.running,
             "tip": "Write the chosen pairs and their <<RMSD>> to a text file."},
            *self.help_buttons(),
        ])
        {None: lambda: None, "run": self.run, "export": self.export, "guide": self.start_guide,
         "help": self.show_help}[pressed]()
        if s.running:
            im.text_disabled("Working...")
            self.remember("working")
        self.status_line()
        im.separator()
        self.form.rects.clear()
        self.label_column()
        draw_form(self.spec, s, self.form)
        self.item_rects.update(self.form.rects)

    def _draw_results(self, box) -> None:
        s = self.session
        self.result_form.rects.clear()
        if not s.rows:
            im.text_wrapped("No result yet: choose a trajectory and press Run selection.")
            self.remember("empty_results")
        draw_form(RESULT_TABLE, self.view, self.result_form)
        self.item_rects.update(self.result_form.rects)
        if s.result is not None and implot.begin_plot("##pairdecay", (-1, -1)):
            implot.setup_axes("Pairs added", "<<RMSD>> (A)")
            decay = np.asarray(s.result.decay, dtype=float)
            implot.set_next_line_style((31, 119, 180, 255), 2.0)
            implot.plot_line("<<RMSD>>", np.arange(1, len(decay) + 1, dtype=float), decay)
            implot.end_plot()
            im.set_item_tooltip("The mean RMSD against the number of pairs chosen: how fast the conformations become distinguishable.")
            self.remember("decay_plot")

    def export_settings(self) -> dict:
        return self.session.export_settings()

    def restore_settings(self, settings: dict) -> None:
        if isinstance(settings, dict):
            self.session.restore_settings(settings)


def _spin(sections) -> None:
    for section in sections:
        if section.get("type") == "value" and section.get("kind") in ("int", "float") and not section.get("read_only"):
            section["style"] = "spin"
            section.setdefault("step", 1)
        _spin(section.get("sections", []))


def make_app(session: PairSession | None = None) -> PairSelectionCard:
    """The pair selection window."""
    from chisurf.emtk.i18n import install

    install()
    return PairSelectionCard(session)


__all__ = ["PairSelectionCard", "PairSession", "make_app"]
