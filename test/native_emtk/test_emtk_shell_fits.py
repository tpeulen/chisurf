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
KNOWN_GAPS = {
    # The model's own editor (its view.json: structure choices, equation, grouped labelled
    # parameters with units, components, MDF outputs) has no native renderer yet.
    "3dgaussian(single-focus)",
    "3dgaussian(two-focus)",
    "add",
    "addcomponent",
    "anticorrterms",
    "bg[khz]",
    "bunchingterms",
    "c[nm]",
    "d1[µm²/s]",
    "d2[µm²/s]",
    "d[µm²/s]",
    "del",
    "dfoci[nm]",
    "diffusion",
    "diffusionspecies(sumofcomponents)",
    "equation",
    "gauss",
    "mag",
    "mdf",
    "mdf(gauss-lorentz)",
    "outputs(mdfmode)",
    "pinhole[µm]",
    "species_diffusion",
    "two-focus",
    "type",
    "veff[fl]",
    "w0[nm]",
    "wem[nm]",
    "wr[nm]",
    "wz[nm]",
    "x1",
    "x2",
    "ε[khz]",
    "λem[nm]",
    "λex[nm]",
    "τd[ms]",
    "true",
    "false",
    "nan",
    "first(2)",
    "last(2)",
    # The fitting controller's other actions.
    "mcts",
    "sample",
    "⚙",
    "…",
    "localfirst",
    "searchfitsettings",
    "dataset",
    "result",
    # The fit window's Code face.
    "code",
    # The Qt session always holds the global-fit pseudo-dataset.
    "global",
    "globaldataset",
}
#: Qt controls that are present under another spelling or chrome the dock manager replaces.
RENAMED = {
    "dropfileshere.": "the File field's placeholder",
    "fcs(general:diffusi...-kristine_with_error": "the fit window's tab title, not elided",
    "−": "MDI minimise: dock windows float, tab and close instead",
    "□": "MDI maximise: dock windows float, tab and close instead",
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
    _settle(driver, lambda: _idle(shell) and data.datasets.datasets, "the dataset")


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
    _settle(driver, lambda: _idle(shell) and data.datasets.datasets, "the demo dataset")
    assert [row["name"] for row in data.datasets.datasets] == ["fcs_demo"]
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
    _settle(driver, lambda: _idle(shell) and data.datasets.datasets, "the dropped file")
    assert data.datasets.datasets[0]["name"] == "Kristine_with_error"


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
    found |= {_normalize_control_text(text) for text in options}
    return found - {""}


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
