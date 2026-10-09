"""Real-input acceptance coverage for every native FRET Docking card control.

The assertions deliberately drive the rendered rectangles through :class:`Ui`.
Fixture data only provides local files and already-existing result rows; it never
substitutes a direct call to a control's action for its pointer or keyboard event.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.modelling.fret.api.project import save_docking_project
from chisurf.plugins.modelling.structure_tools.cards.docking import make_app
from chisurf.plugins.modelling.structure_tools.cards.docking_model import DockingSession
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

REPO = next(path for path in Path(__file__).parents if (path / "pyproject.toml").exists())
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"
CANVAS = (1600, 1200)
INPUT_TOOLBAR = frozenset({"project", "save", "fps_pick", "out_pick", "run", "stop", "clear", "guide", "help"})
RIGID_BODY_TOOLBAR = frozenset({"add_pdb", "database_pdb", "remove_pdb", "clear_pdb"})
FORM_CONTROLS = frozenset({
    "fps_json", "output_dir", "operation", "method", "score_set", "n_repeats", "n_frames", "ev_weight",
    "refine_av_cycles", "fixed_body", "sigma_da", "av_backend", "save_distributions", "save_trajectory",
    "continue_from_poses", "mc_steps", "n_best", "simulated_annealing",
})
RESULT_TABS = frozenset({"tab_Results", "tab_Score", "tab_Structure"})
RESULT_HEADERS = frozenset({"trial", "type", "score", "distances", "best_pdb"})


@pytest.fixture(autouse=True)
def hermetic_settings(tmp_path, monkeypatch):
    """Keep application and MMFDB settings entirely inside the test directory."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


@pytest.fixture()
def inputs(tmp_path):
    """Local PDBs, two restraint files, folders, and a portable docking project."""
    pdbs = []
    for source, name in (("protein_1R0A.pdb", "protein.pdb"), ("dna.pdb", "dna.pdb"),
                         ("protein_1R0A.pdb", "extra.pdb"), ("dna.pdb", "database.pdb")):
        target = tmp_path / name
        shutil.copy(EXAMPLE / source, target)
        pdbs.append(target)
    payload = json.loads((EXAMPLE / "hiv_rt.fps.json").read_text())
    for position in payload["Positions"].values():
        position["pdb_path"] = str(pdbs[1] if position["chain_identifier"] == "P" else pdbs[0])
    payload["χ²"] = {"all": {"distances": list(payload["Distances"])}}
    fps_a, fps_b = tmp_path / "a.fps.json", tmp_path / "b.fps.json"
    fps_a.write_text(json.dumps(payload))
    fps_b.write_text(json.dumps(payload))
    output_a, output_b = tmp_path / "output_a", tmp_path / "output_b"
    output_a.mkdir()
    output_b.mkdir()
    project = tmp_path / "load-me.json"
    save_docking_project(
        str(project), pdb_paths=[str(pdbs[0]), str(pdbs[1])], fps_json=str(fps_a),
        output_dir=str(tmp_path), params={"n_frames": 5},
    )
    return {"pdbs": pdbs, "fps_a": fps_a, "fps_b": fps_b, "output_a": output_a,
            "output_b": output_b, "project": project}


class OfflineStructureClient:
    """The Database picker client used here; it records calls and never opens a network connection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "mmfdb.datasets.browse":
            return {"total": 1, "datasets": [
                {"artifact_id": "local-pdb", "artifact_kind": "structure", "data_format": "pdb",
                 "original_filename": self.path.name},
            ]}
        if method == "mmfdb.datasets.open":
            return {"local_path": str(self.path)}
        raise AssertionError(method)


def _wait_for(ui: Ui, predicate, timeout: float = 5.0) -> None:
    """Advance rendered frames until an asynchronous picker operation is visible."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ui.draw(2)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the rendered UI state")


def _select_choice(ui: Ui, attr: str, value: str) -> None:
    """Choose one form-combo value through its click-opened overlay."""
    ui.click(attr)
    ui.press_text(value)
    assert getattr(ui.app.session, attr) == value


def _click_first_table_row(ui: Ui, table) -> None:
    """Deliver a pointer event to the first rendered data row, below its header."""
    x, y, width, height = table._body_box
    ui.click_at(x + width * 0.5, y + min(table._row_h * 0.5, height * 0.5))


def _declared_form_controls() -> set[str]:
    """Return every interactive attr the shared fret_dock view spec declares."""
    spec = json.loads((REPO / "chisurf/plugins/modelling/fret/gui/fret_dock.view.json").read_text())

    def walk(sections):
        for section in sections:
            if section.get("type") in {"value", "choice", "toggle"}:
                yield section["attr"]
            yield from walk(section.get("sections", ()))

    return set(walk(spec["sections"]))


@pytest.mark.parametrize("canvas", [(800, 600), (1200, 800)])
def test_docking_tour_next_caption_click_advances_at_supported_viewport_sizes(canvas):
    """A real pointer click on the drawn first-step Next caption advances the tour."""
    app = make_app()
    ui = Ui(app, canvas)
    try:
        ui.click("guide")
        assert app.tour.active and app.tour.step_idx == 0 and not app.tour.awaiting
        ui.press_text("Next ►")
        assert app.tour.step_idx == 1
    finally:
        app.close()


def test_input_toolbar_and_rigid_body_controls_click_through_real_ui(inputs):
    """Project/file/modal, run/stop, guide/help and rigid-body toolbar events reach the card."""
    client = OfflineStructureClient(inputs["pdbs"][3])
    session = DockingSession()
    session.fps_json = str(inputs["fps_a"])
    app = make_app(session=session, mmfdb_client=client)
    ui = Ui(app, CANVAS)
    try:
        rendered = set(app.item_rects)
        assert INPUT_TOOLBAR <= rendered and RIGID_BODY_TOOLBAR <= rendered
        ui.click("project")
        assert (ui.dialog_open and ui.shown("Load docking project")
                and app.dialog.directory == str(inputs["project"].parent))
        ui.dialog_pick(inputs["project"].name)
        assert session.pdb_files == [str(inputs["pdbs"][0]), str(inputs["pdbs"][1])]

        saved = inputs["project"].parent / "saved-from-toolbar.json"
        ui.click("save")
        assert (ui.dialog_open and ui.shown("Save docking project")
                and app.dialog.directory == str(inputs["project"].parent))
        ui.save_dialog_type_name(str(saved))
        ui.press_text("Save")
        assert saved.exists() and session.status == f"saved {saved.name}"

        ui.click("fps_pick")
        assert (ui.dialog_open and ui.shown("Select fps.json or FPS LPs .txt")
                and app.dialog.directory == str(inputs["fps_b"].parent))
        ui.dialog_pick(inputs["fps_b"].name)
        assert session.fps_json == str(inputs["fps_b"])

        ui.click("out_pick")
        assert (ui.dialog_open and ui.shown("Output directory")
                and app.dialog.directory == str(inputs["output_b"].parent))
        ui.dialog_pick(f"[{inputs['output_b'].name}]", action="Choose")
        assert session.output_dir == str(inputs["output_b"])

        ui.click("run")
        assert session.running
        ui.click("stop")
        assert session.stop_event.is_set() and session.progress_text == "stopping..."
        _wait_for(ui, lambda: not session.running, timeout=15)
        assert not session.running and session.status == "stopped"

        ui.click("add_pdb")
        assert (ui.dialog_open and ui.shown("Add PDB file")
                and app.dialog.directory == str(inputs["pdbs"][2].parent))
        ui.dialog_pick(inputs["pdbs"][2].name)
        assert str(inputs["pdbs"][2]) in session.pdb_files

        ui.click("database_pdb")
        _wait_for(
            ui,
            lambda: app.pickers and app.pickers[0]._pending is None
            and ui.shown(f"{inputs['pdbs'][3].name} [structure] (pdb)"),
        )
        ui.press_text(f"{inputs['pdbs'][3].name} [structure] (pdb)")
        assert app.pickers[0].selection is not None
        ui.press_text("Open selected")
        _wait_for(ui, lambda: not app.pickers)
        assert session.pdb_files == [str(path) for path in inputs["pdbs"]]
        assert [call[0] for call in client.calls] == ["mmfdb.datasets.browse", "mmfdb.datasets.open"]

        pdb_table = app.pdb_form.tables["pdb_rows"].control
        _click_first_table_row(ui, pdb_table)
        assert app.view.pdb_selected == 0
        ui.key(keys.KEY_DELETE)
        assert session.pdb_files == [str(inputs["pdbs"][1]), str(inputs["pdbs"][2]), str(inputs["pdbs"][3])]
        assert app.view.pdb_selected == -1

        ui.draw(2)
        _click_first_table_row(ui, app.pdb_form.tables["pdb_rows"].control)
        assert app.view.pdb_selected == 0
        ui.click("remove_pdb")
        assert session.pdb_files == [str(inputs["pdbs"][2]), str(inputs["pdbs"][3])]
        assert app.view.pdb_selected == -1

        ui.click("clear_pdb")
        assert not session.pdb_files and app.view.pdb_selected == -1

        ui.click("help")
        assert app.help_window.open and ui.shown("Close Help")
        ui.press_text("Close Help")
        assert not app.help_window.open
        ui.click("guide")
        steps = len(app.tour.steps)
        assert app.tour.active and app.tour.step_idx == 0 and not app.tour.awaiting
        assert ui.shown(f"Step 1 of {steps}")
        ui.press_text("Next ►")
        assert app.tour.step_idx == 1 and ui.shown(f"Step 2 of {steps}")
        assert app.tour.awaiting
        ui.press_text("Next ►")
        assert app.tour.step_idx == 1 and app.tour.awaiting
        ui.click("project")
        assert ui.dialog_open and ui.shown("Load docking project")
        ui.dialog_pick("load-me.json", action="Open")
        assert not app.tour.awaiting
        ui.press_text("Next ►")
        assert app.tour.step_idx == 2 and ui.shown(f"Step 3 of {steps}")
        ui.press_text("◄ Prev")
        assert app.tour.step_idx == 1 and ui.shown(f"Step 2 of {steps}")
        ui.press_text("Close Tour")
        assert not app.tour.active and not ui.shown("Step 2 of")
    finally:
        app.close()


def test_every_fret_dock_form_control_changes_session_after_real_input(inputs):
    """Every value, combo, number spinner, and toggle in fret_dock.view.json is driven by input."""
    app = make_app()
    ui = Ui(app, CANVAS)
    session = app.session
    try:
        assert _declared_form_controls() == FORM_CONTROLS
        assert FORM_CONTROLS <= set(app.item_rects)
        ui.type_into("fps_json", str(inputs["fps_a"]))
        assert session.fps_json == str(inputs["fps_a"])
        ui.type_into("output_dir", str(inputs["output_a"]))
        assert session.output_dir == str(inputs["output_a"])
        _select_choice(ui, "operation", "screen")
        _select_choice(ui, "method", "mc")
        ui.type_into("score_set", "all")
        assert session.score_set == "all"

        for attr, text, expected in (
            ("n_repeats", "2", 2), ("n_frames", "100000", 100000), ("ev_weight", "2.5", 2.5),
            ("refine_av_cycles", "1", 1), ("fixed_body", "1", 1), ("sigma_da", "4.5", 4.5),
        ):
            ui.type_into(attr, text)
            assert getattr(session, attr) == pytest.approx(expected)

        _select_choice(ui, "av_backend", "imp-bff")
        for attr in ("save_distributions", "save_trajectory", "continue_from_poses"):
            before = getattr(session, attr)
            ui.click(attr)
            assert getattr(session, attr) is not before

        for attr, text, expected in (("mc_steps", "8", 8), ("n_best", "4", 4)):
            ui.type_into(attr, text)
            assert getattr(session, attr) == expected
        before = session.simulated_annealing
        ui.click("simulated_annealing")
        assert session.simulated_annealing is not before
    finally:
        app.close()


def test_results_controls_click_tabs_headers_rows_preview_and_clear(inputs):
    """Result navigation and all sortable table headers answer actual pointer input."""
    app = make_app()
    ui = Ui(app, CANVAS)
    session = app.session
    try:
        assert RESULT_TABS <= set(app.item_rects)
        session.add_rows([
            (0, 3.0, 4, str(inputs["pdbs"][0])),
            (1, 1.0, 4, str(inputs["pdbs"][1])),
        ], "dock")
        session.curves = {"trace.csv": ([0, 1], [3.0, 1.0])}
        ui.draw(3)

        ui.click("tab_Results")
        assert app.tab == "Results"
        table = app.result_form.tables["result_rows"].control
        assert {column.key for column in table._shown} == RESULT_HEADERS
        for index, column in enumerate(table._shown):
            x, y, _width, height = table._header_box
            left = x + sum(table._widths[:index])
            ui.click_at(left + table._widths[index] * 0.5, y + height * 0.5)
            assert table.sort_key_name == column.key

        _click_first_table_row(ui, table)
        assert session.selected_row in (0, 1) and session.preview == [session.rows[session.selected_row]["path"]]

        ui.click("tab_Score")
        assert app.tab == "Score" and ui.shown("Step") and ui.shown("Total score")

        session.preview = [str(inputs["pdbs"][0]), str(inputs["pdbs"][1])]
        session.preview_index = 1
        ui.click("tab_Structure")
        assert app.tab == "Structure" and ui.shown("Model 2 of 2")
        ui.click("preview_prev")
        assert session.preview_index == 0
        ui.click("preview_next")
        assert session.preview_index == 1

        ui.click("clear")
        assert not session.rows and not session.curves and not session.preview
    finally:
        app.close()
