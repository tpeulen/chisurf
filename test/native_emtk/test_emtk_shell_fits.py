"""The emtk shell's data and fit docks (W9 S2): load, fit, edit, run -- through ChiSurfAPI and server events.

The shell gets a real in-process server on private ports (:func:`chisurf.emtk.session.start_session`) with a
fresh session state, so nothing here touches ``chisurf.fits`` or a running ChiSurf. Every action is a click on the
declared controls (``item_rects``) or the callback a table cell edit calls; every check reads what the shell shows
or what the server answers.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY, PLOT_KEY, READ_KEY, load_view
from chisurf.emtk.main_app import EmtkShellApp

REPO = Path(__file__).resolve().parents[2]
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
MODEL = "FCS (general: diffusion + bunching/anticorr)"
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))

#: Controls of the Qt docks the emtk docks do not have yet. Each is an open item of the ledger
#: (``okf/subsystems/qt-retirement.md``, slice S2); this list only shrinks -- a control that appears is struck.
#: Empty since the model editor, the fit controller's actions, the Code face and the global dataset landed.
KNOWN_GAPS: set[str] = set()
#: Qt controls that are present under another spelling or chrome the dock manager replaces.
RENAMED = {
    "dropfileshere.": "the File field's placeholder",
    "fcs(general:diffusi...-kristine_with_error": "the fit window's tab title, not elided",
    "−": "MDI minimise: dock windows float, tab and close instead",
    "□": "MDI maximise: dock windows float, tab and close instead",
    "true": "a ticked Fixed / Bounds cell: drawn as a check box, not as text",
    "false": "an unticked Fixed / Bounds cell: drawn as a check box, not as text",
    "nan": "a parameter without an error estimate: the table writes N/A",
}
_NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$")


@pytest.fixture
def shell():
    """A shell with no plugins and its own session (server on free ports, fresh state)."""
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    yield app
    app.close()


def _settle(driver: Driver, predicate, what: str, timeout: float = 120.0) -> None:
    """Draw until *predicate* holds (a worker call landed, an event arrived)."""
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}: {driver.app.data.status}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _idle(shell) -> bool:
    return not shell.data.busy and not shell.data._dirty


def _load(driver: Driver, shell, path: Path, experiment="FCS", setup="Seidel Kristine") -> None:
    data = shell.data
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    data.read.experiment = experiment
    data.read.experiment_changed(experiment)
    data.read.setup = setup
    data.read.path = str(path)
    driver.click("read.load")
    stem = Path(path).stem
    _settle(
        driver,
        lambda: _idle(shell) and any(r["name"] == stem for r in data.datasets.datasets),
        "the dataset",
    )


def _add_fit(driver: Driver, shell, model: str = MODEL) -> str:
    data = shell.data
    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    data.datasets.model = model
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and data.windows and data.analysis.info, "the fit window")
    return data.current_uid


def _row(shell, name: str) -> dict:
    return next(row for row in shell.data.analysis.parameters if row["name"] == name)


def test_load_fit_edit_and_run_through_the_api(shell):
    """Demo → + Data → + Analysis → edit N → Fit: the window shows the fit and χ²ᵣ drops."""
    from chisurf.core.experiments.fcs.demo import DEMO

    driver = Driver(shell, size=(1500, 950))
    driver.frame(2)
    data = shell.data
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    driver.click("read.use_demo")
    driver.frame(2)
    assert Path(data.read.path).is_file()
    assert (data.read.experiment, data.read.setup) == (DEMO["experiment"], DEMO["reader"])
    driver.click("read.load")
    _settle(
        driver,
        lambda: _idle(shell) and any(r["name"] == "fcs_demo" for r in data.datasets.datasets),
        "the demo dataset",
    )
    assert [row["name"] for row in data.datasets.datasets] == ["Global Dataset", "fcs_demo"]
    output = SHOTS
    output.mkdir(parents=True, exist_ok=True)
    driver.screenshot(output / "emtk_shell_read_data.png")

    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    assert data.datasets.model == DEMO["model"], "the demo chose its model"
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and data.windows and data.analysis.info, "the fit window")
    uid = data.current_uid
    window = data.windows[uid]
    assert shell.docks.window(window.key) is not None
    assert {"Fit", "Data table", "Residuals"} <= set(window.names)
    assert data.analysis.info.get("fit_range") == [0, 159]
    chi2_start = data.analysis.info["chi2r_current"]
    assert chi2_start is not None and chi2_start > 1.5, "a fresh fit starts away from the data"

    # A cell edit of the parameter table, as the table calls it: N = 3 goes to the server.
    data.analysis.edit_parameter(_row(shell, "N"), "value", 3.0)
    _settle(driver, lambda: _idle(shell) and _row(shell, "N")["value"] == 3.0, "N = 3 read back")
    assert data.analysis.info["chi2r_current"] != chi2_start, "the edit changed the model"
    assert shell.data.session.api.get_parameter("N", fit_uid=uid)["value"] == 3.0

    received = data.session.events.received
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(2)
    chi2_before = data.analysis.info["chi2r_current"]
    driver.click("analysis.run_fit")
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("chi2r_current") != chi2_before,
        "χ² after the fit",
    )
    chi2_after = data.analysis.info["chi2r_current"]
    assert chi2_after < chi2_before
    assert data.session.events.received > received, "the fit's completion arrived as an event"
    # The demo was made with N = 2 and the noise its errors state: the fit finds both.
    assert _row(shell, "N")["value"] == pytest.approx(DEMO["n"], rel=0.05)
    assert chi2_after == pytest.approx(1.0, abs=0.3)
    assert f"χ²ᵣ {chi2_after:.4g}" in " ".join(driver.painter.strings)
    driver.frame(3)
    driver.screenshot(output / "emtk_shell_fit.png")
    # The Plot settings dock shows the current page's settings form.
    shell.docks.focus(PLOT_KEY)
    driver.frame(3)
    page = window.current_page()
    assert page is not None and page.has_settings()
    assert "No plot selected." not in driver.painter.strings
    driver.screenshot(output / "emtk_shell_plot_settings.png")


def test_a_fit_made_elsewhere_opens_its_window_from_the_event(shell):
    """``fit.created`` from another caller of the server opens the window: the event stream drives the shell."""
    driver = Driver(shell, size=(1200, 800))
    _load(driver, shell, KRISTINE)
    api = shell.data.session.api
    result = api.add_fit([0], model_name=MODEL)
    assert result.get("uid")
    _settle(driver, lambda: result["uid"] in shell.data.windows, "the window from fit.created")
    assert shell.data.current_uid == result["uid"]
    api.remove_fits(fit_uids=[result["uid"]])
    _settle(driver, lambda: not shell.data.windows, "the window closed by fit.removed")


def test_a_file_dropped_on_the_shell_is_read(shell):
    driver = Driver(shell, size=(1200, 800))
    driver.frame(2)
    data = shell.data
    data.read.experiment = "FCS"
    data.read.experiment_changed("FCS")
    data.read.setup = "Seidel Kristine"
    assert shell.on_files_dropped([str(KRISTINE)])
    _settle(driver, lambda: _idle(shell) and len(data.datasets.datasets) == 2, "the dropped file")
    assert data.datasets.datasets[-1]["name"] == "Kristine_with_error"


def test_closing_a_fit_window_keeps_the_fit(shell):
    driver = Driver(shell, size=(1200, 800))
    _load(driver, shell, KRISTINE)
    uid = _add_fit(driver, shell)
    shell.docks.hide(shell.data.windows[uid].key)
    driver.frame(2)
    assert uid not in shell.data.windows
    assert [f["uid"] for f in shell.data.session.api.list_fits()] == [uid]
    shell.data.datasets.select_fit({"uid": uid})
    driver.frame(2)
    assert uid in shell.data.windows, "selecting the fit reopens its window"


def _emtk_inventory(driver: Driver, shell) -> set[str]:
    """Normalised text of every dock in the S2 state, plus the options its choices offer."""
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from migration_parity import _normalize_control_text

    data = shell.data
    found: set[str] = set()
    # Open the reader's folded Columns panel, as the Qt inventory counts hidden rows too.
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    reader_app = next(iter(data._reader_apps.values()))
    _key, _app, box = shell._drawn[f"reader.{id(reader_app)}"]
    fx, fy, fw, fh = reader_app.form.rects["Columns (CSV only).fold"]
    driver.click((box[0] + fx + fw / 2, box[1] + fy + fh / 2))
    driver.frame(2)
    for key in (READ_KEY, DATASETS_KEY, ANALYSIS_KEY, PLOT_KEY):
        shell.docks.focus(key)
        driver.frame(3)
        found |= {_normalize_control_text(text) for text in driver.painter.strings}
    reader = data.read.reader()
    options = [
        *data.read.experiment_names(),
        *data.read.setup_names(),
        *data.datasets.model_names(),
    ]
    noise = next(
        s
        for panel in load_reader_view(reader)["sections"]
        for s in panel.get("sections", [])
        if s.get("type") == "choice"
    )
    options += list(noise.get("labels") or [])
    options += [load_view("read_data")["sections"][2]["placeholder"]]
    # The model editor's hidden panels (the inactive diffusion presets) and the controller's
    # 2-D range pair (hidden for 1-D data): present, as the Qt inventory counts hidden widgets.
    options += sorted(data.editor.inventory())
    options += _labels(load_view("analysis"))
    options += [data.analysis.dataset_options()[0][1]]
    found |= {_normalize_control_text(text) for text in options}
    return found - {""}


def _labels(spec: dict) -> list[str]:
    """Every label and title of a view spec, hidden sections included."""
    found = []

    def walk(section: dict) -> None:
        for key in ("label", "title"):
            if section.get(key):
                found.append(section[key])
        for button in section.get("buttons") or []:
            found.append(button.get("label", ""))
        for child in section.get("sections") or []:
            walk(child)

    walk(spec)
    return found


def load_reader_view(reader) -> dict:
    from chisurf.emtk.reader_settings import native_reader_spec

    return native_reader_spec(reader.view_spec())


def test_parity_with_the_qt_docks(shell):
    """Control inventory of the Qt Read data / Datasets / Analysis / Plot docks and fit window, against the emtk docks.

    The before-half is ``shell_s2_qt_inventory.json`` (``capture_shell_s2_qt_before.py``). Numbers are values,
    not controls. A Qt control missing here must be a known gap (an open ledger item) or a rename.
    """
    before = json.loads((Path(__file__).with_name("shell_s2_qt_inventory.json")).read_text("utf-8"))
    driver = Driver(shell, size=(1500, 950))
    _load(driver, shell, KRISTINE)
    _add_fit(driver, shell)
    after = _emtk_inventory(driver, shell)
    qt = set().union(*(set(dock["controls"]) for dock in before["docks"].values()))
    lost = {c for c in qt - after if not _NUMBER.match(c)}
    unexplained = lost - KNOWN_GAPS - set(RENAMED)
    assert not unexplained, f"Qt controls missing from the emtk docks: {sorted(unexplained)}"
    closed = KNOWN_GAPS & after
    assert not closed, f"these gaps are closed now; strike them from KNOWN_GAPS: {sorted(closed)}"


# ── the model editor, the fit controller and the global fit (S2 continued) ─────


@pytest.fixture
def settings_sandbox(monkeypatch):
    """Keep the user's settings out of reach: the file is never written, the session dict is restored.

    Returns the list of what would have been written (``set_optimization_settings`` keyword dicts).
    """
    import copy

    from chisurf.core import settings
    from chisurf.core.settings import settings_utils

    written: list[dict] = []
    monkeypatch.setattr(
        settings_utils, "set_optimization_settings", lambda **kw: written.append(kw) or True
    )
    monkeypatch.setitem(
        settings.cs_settings,
        "optimization",
        copy.deepcopy(settings.cs_settings.get("optimization", {})),
    )
    return written


def _row_named(rows: list, name: str) -> dict:
    return next(row for row in rows if row["name"] == name)


def _show_analysis(shell, driver) -> None:
    """Bring the Analysis dock to the front."""
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(3)


def test_the_model_editor_is_the_models_view_json_written_through_the_api(shell):
    """Type radio, a cell of one preset's table, add / del of a component: each is an RPC, read back."""
    driver = Driver(shell, size=(1500, 1400))
    _load(driver, shell, KRISTINE)
    uid = _add_fit(driver, shell)
    data, editor = shell.data, shell.data.editor
    api = data.session.api
    _show_analysis(shell, driver)
    assert editor.editor is not None, "the model's editor was read from the server"
    assert data.analysis.has_editor, "and replaces the flat parameter table"
    labels = [row["label"] for row in editor.rows("gauss")]
    assert {"N", "D[µm²/s]", "w_{r}[nm]", "w_{z}[nm]", "d_{foci}[nm]", "BG[kHz]"} <= set(labels)
    assert "3D Gaussian (single-focus)" in editor.visible_titles()
    assert "MDF (Gauss-Lorentz)" not in editor.visible_titles()
    painted = " ".join(driver.painter.strings)
    assert "w_{r}" not in painted, "the labels draw their subscripts, not the markup"

    # The Diffusion type, as the radio's click sends it: model.state.set, then the editor re-read.
    attr = editor.control_for("diffusion_mode")
    assert attr
    driver.click(f"editor.{attr}.0")
    _settle(
        driver,
        lambda: _idle(shell) and (editor.editor or {}).get("state", {}).get("diffusion_mode") == "mdf",
        "the MDF mode",
    )
    assert api.model_state_get(fit_uid=uid)["state"]["diffusion_mode"] == "mdf"
    assert "MDF (Gauss-Lorentz)" in editor.visible_titles()
    assert "3D Gaussian (single-focus)" not in editor.visible_titles()
    driver.frame(3)
    driver.screenshot(SHOTS / "emtk_shell_editor_mdf.png")

    # Each preset has its own N; a cell edit addresses the parameter by its uid.
    row = _row_named(editor.rows("mdf_physical"), "N")
    editor.edit_cell(row, "value", 4.0)
    _settle(
        driver,
        lambda: _idle(shell) and _row_named(editor.rows("mdf_physical"), "N")["value"] == 4.0,
        "the MDF N",
    )
    assert _row_named(editor.rows("gauss"), "N")["value"] == 1.0, "the Gauss preset's N is its own"
    editor.edit_cell(_row_named(editor.rows("mdf_physical"), "b"), "fixed", True)
    _settle(
        driver,
        lambda: _idle(shell) and _row_named(editor.rows("mdf_physical"), "b")["fixed"],
        "b fixed",
    )

    # Back to Gauss, then a bunching term: add, read back, del.
    driver.click(f"editor.{attr}.1")
    _settle(
        driver,
        lambda: _idle(shell) and editor.editor["state"]["diffusion_mode"] == "gauss",
        "the Gauss mode",
    )
    driver.click("editor.Bunching terms.fold")
    driver.frame(2)
    add = editor.action_for("add", "bunching")
    driver.click(f"editor.{add}")
    _settle(driver, lambda: _idle(shell) and len(editor.rows("bunching")) == 2, "a bunching term")
    assert [row["label"] for row in editor.rows("bunching")] == ["a_{b1}", "τ_{b1}[ms]"]
    assert "b1" in (editor.editor["sections"][1]["sections"][0]["text"]), "the equation follows"
    driver.frame(3)
    driver.screenshot(SHOTS / "emtk_shell_editor_bunching.png")
    remove = editor.action_for("remove", "bunching")
    driver.click(f"editor.{remove}")
    _settle(driver, lambda: _idle(shell) and not editor.rows("bunching"), "the term removed")

    # Code: the window turns over to the model's source and its view.json (model.code.files).
    window = data.windows[uid]
    driver.click(f"{window.key}.code")
    _settle(driver, lambda: _idle(shell) and window.code_shown(), "the Code face")
    names = [doc.name for doc in window.code_face.documents]
    assert names[:2] == ["general.view.json", "general.py"], names
    applied = []
    data.session.api.model_code_apply = lambda path, code, fit_uid=None: applied.append(
        (path, fit_uid)
    ) or {"ok": True, "message": "Saved (test)"}
    window.code_face.apply()
    _settle(driver, lambda: _idle(shell) and applied, "the apply call")
    assert applied[0][0].endswith("general.py") and applied[0][1] == uid
    _settle(driver, lambda: window.code_face.status == "Saved (test)", "the apply's status")
    driver.frame(3)
    driver.screenshot(SHOTS / "emtk_shell_fit_code.png")
    driver.click(f"{window.key}.code")
    driver.frame(2)
    assert not window.code_shown(), "Plots turns it back"


def test_the_fit_controllers_actions_go_through_the_api(shell, settings_sandbox, tmp_path):
    """auto, Result, ⚙, …, MCTS, Sample and Search fit settings, each driven from its control."""
    from chisurf.core import settings
    from chisurf.core.experiments.fcs.demo import DEMO, make_demo

    driver = Driver(shell, size=(1500, 1400))
    _load(driver, shell, KRISTINE)
    uid = _add_fit(driver, shell)
    data = shell.data
    api = data.session.api
    _show_analysis(shell, driver)

    # auto: the reader's own range for the data (fit.range.auto), shown in First / Last.
    driver.click("analysis.auto_range")
    _settle(driver, lambda: _idle(shell), "the auto range")
    fit_range = api.get_fit_info(fit_uid=uid)["fit_range"]
    assert fit_range == [data.analysis.xmin, data.analysis.xmax]

    # Two runs store two results; the Result field shows the first one again.
    for _ in range(2):
        driver.click("analysis.run_fit")
        _settle(driver, lambda: _idle(shell), "a fit")
    assert data.analysis.info["n_results"] >= 2
    assert data.analysis.enabled("result_index")
    data.analysis.result_index = 1
    data.analysis.result_changed(1)
    _settle(driver, lambda: _idle(shell) and data.analysis.info["result_idx"] == 0, "result 1")

    # ⚙: the settings dialog over the shell; OK writes the user settings (sandboxed here).
    driver.click("analysis.settings")
    driver.frame(3)
    dialog = data.settings_dialog
    assert dialog is not None and "Sampler" in " ".join(driver.painter.strings)
    driver.screenshot(SHOTS / "emtk_shell_fit_settings.png")
    driver.click(dialog.rects["ok"])
    driver.frame(2)
    assert data.settings_dialog is None
    assert settings_sandbox and "sampling" in settings_sandbox[-1]

    # Search fit settings is kept in the user settings when it is ticked.
    driver.click("analysis.search_fit_settings")
    driver.frame(2)
    assert data.analysis.search_fit_settings is True
    assert {"mcts": {"search_fit_settings": True}} in settings_sandbox

    # MCTS: the structure search runs on the server and reports its outcome.
    assert data.analysis.model_search, "BFF can search the general FCS model"
    data.analysis.search_fit_settings = False
    settings.cs_settings["optimization"].setdefault("mcts", {})["n_simulations"] = 3
    driver.click("analysis.mcts")
    _settle(driver, lambda: _idle(shell), "the model search", timeout=600.0)
    assert "Model search" in data.status, data.status

    # …: attach another dataset to this fit.
    _load(driver, shell, make_demo(), DEMO["experiment"], DEMO["reader"])
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(2)
    data.show_fit(uid)
    _settle(driver, lambda: _idle(shell) and data.current_uid == uid, "the fit again")
    driver.click("analysis.select_dataset")
    driver.frame(2)
    picker = data.dataset_picker
    assert picker is not None
    names = [row["name"] for row in picker.rows]
    assert "Global Dataset" not in names and "fcs_demo" in names
    picker.pick(names.index("fcs_demo"))
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("dataset_name") == "fcs_demo",
        "the demo attached",
    )

    # Sample: a folder is asked for, then the server samples into it and the verdict arrives.
    sampling = settings.cs_settings["optimization"].setdefault("sampling", {})
    sampling.update(steps=40, n_runs=2, method="slice")
    driver.click("analysis.sample")
    driver.frame(2)
    assert data.file_dialog is not None and data.file_dialog.mode == "folder"
    done, data.file_dialog = data._file_done, None
    done(str(tmp_path))
    _settle(driver, lambda: _idle(shell) and data.sampling_job, "the sampling job")
    _settle(driver, lambda: not data.sampling_job, "the sampling verdict", timeout=600.0)
    assert data.status.startswith("Sampling done"), data.status
    assert any(tmp_path.iterdir()), "the chains went to the folder"


def test_a_global_fit_is_made_and_run_in_the_emtk_session(shell):
    """The session holds the Global Dataset; a global fit takes the local fits and runs (Local first)."""
    from chisurf.core.experiments.fcs.demo import DEMO, make_demo

    driver = Driver(shell, size=(1500, 1400))
    data = shell.data
    driver.frame(2)
    assert [(r["name"], r["experiment"]) for r in data.datasets.datasets] == [
        ("Global Dataset", "Global")
    ]
    _load(driver, shell, KRISTINE)
    first = _add_fit(driver, shell)
    _load(driver, shell, make_demo(), DEMO["experiment"], DEMO["reader"])
    second = _add_fit(driver, shell)
    api = data.session.api
    names = {f["uid"]: f["name"] for f in api.list_fits()}

    data.datasets.select_dataset(data.datasets.datasets[0])
    assert "Global fit" in data.datasets.model_names()
    global_uid = _add_fit(driver, shell, model="Global fit")
    assert global_uid not in (first, second)
    editor = data.editor
    _show_analysis(shell, driver)
    assert "Local fits" in editor.visible_titles()
    candidate = editor.control_for("selected_candidate_fit")
    add = editor.action_for("press", "add_selected_fit")
    for uid in (first, second):
        setattr(editor, candidate, names[uid])
        _settle(driver, lambda: _idle(shell), "the candidate")
        driver.click(f"editor.{add}")
        _settle(driver, lambda: _idle(shell), "the fit added")
    local = [r["name"] for r in data.editor._sources[next(
        k for k in data.editor._sources if k.startswith("records_"))]]
    assert local == [names[first], names[second]]
    driver.frame(3)
    driver.screenshot(SHOTS / "emtk_shell_global_fit.png")

    chi2 = data.analysis.info.get("chi2r_current")
    driver.click("analysis.run_fit")
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("chi2r_current") != chi2,
        "the global fit",
        timeout=600.0,
    )

    # A fit over a group of two curves has two members; the Dataset combo picks which one is shown.
    grouped = api.group_datasets([1, 2])
    assert grouped["member_count"] == 2
    result = api.add_fit([1], model_name=MODEL)
    _settle(driver, lambda: result["uid"] in data.windows and _idle(shell), "the group fit")
    data.show_fit(result["uid"])
    _settle(driver, lambda: _idle(shell) and len(data.analysis.dataset_options()) == 2, "members")
    data.analysis.dataset_index = 1
    data.analysis.dataset_changed(1)
    _settle(
        driver,
        lambda: _idle(shell)
        and next(m for m in data.analysis.info["members"] if m["selected"])["local_idx"] == 1,
        "the second member",
    )


def test_a_dataset_dragged_onto_a_fit_window_is_attached_to_that_fit(shell):
    """Press a Datasets row, drag it over the fit window, let go: ``fit.set_dataset`` for that fit."""
    from emtk.events import LEFT_BUTTON

    from chisurf.core.experiments.fcs.demo import DEMO, make_demo

    driver = Driver(shell, size=(1500, 1100))
    data = shell.data
    _load(driver, shell, KRISTINE)
    uid = _add_fit(driver, shell)
    _load(driver, shell, make_demo(), DEMO["experiment"], DEMO["reader"])
    shell.docks.focus(DATASETS_KEY)
    driver.frame(3)
    binding = data.forms["datasets"].tables["dataset_rows"]
    control = binding.control
    position = [row["name"] for row in data.datasets.datasets].index("fcs_demo")
    bx, by, bw, _bh = control._body_box
    start = (bx + bw / 3, by + control._row_h * (position + 0.5))
    window = data.windows[uid]
    wx, wy, ww, wh = window.box
    end = (wx + ww / 2, wy + wh / 2)
    surface = driver.surface
    surface.on_pointer_move(*start, 0, 0)
    driver.frame()
    surface.on_pointer_press(*start, LEFT_BUTTON, 0)
    driver.frame()
    for step in range(1, 9):
        point = (start[0] + (end[0] - start[0]) * step / 8, start[1] + (end[1] - start[1]) * step / 8)
        surface.on_pointer_move(*point, LEFT_BUTTON, 0)
        driver.frame()
    assert data.dragged is not None and data.window_at(*end) == uid
    assert "fcs_demo → " in " ".join(driver.painter.strings), "the drop target is named"
    driver.screenshot(SHOTS / "emtk_shell_dataset_drag.png")
    surface.on_pointer_release(*end, LEFT_BUTTON, 0)
    driver.frame()
    _settle(
        driver,
        lambda: _idle(shell) and data.analysis.info.get("dataset_name") == "fcs_demo",
        "the dropped dataset attached",
    )
    assert data.current_uid == uid and data.dragged is None
