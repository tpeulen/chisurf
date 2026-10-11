"""The emtk shell's model editor beyond the general FCS model: curve pickers and custom sections (W9 S2).

A TCSPC fit takes its IRF and background from the session's datasets through the editor's curve
pickers (``model.curve.set`` / ``model.curve.unload``); the nine ``custom`` sections (κ² controls,
anisotropy diagnostics, L-curve, rate matrix, scalar table, file list, background run, fit mixer,
global parameter table) and a lifetime group's *Abs.* / *Norm.* / *read* / *link* are drawn
natively and write through ``model.section.call``; any parameter table opens the link menu on a
right click. Every action is a click on the declared rectangles (``editor.*`` item rects), the
callback a table calls, or a pick in the popup the click opened; every check reads what the shell
shows or what the server answers. The parity test compares the Analysis dock against the Qt model
editors captured by ``capture_shell_s2_models_qt_before.py``.
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

from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY, READ_KEY
from chisurf.emtk.main_app import EmtkShellApp

REPO = Path(__file__).resolve().parents[2]
TCSPC = REPO / "test" / "data" / "tcspc" / "decay_fit"
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
PDB = REPO / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
_NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$")

#: Qt model-editor controls the emtk editor does not have yet, by model (an open ledger item each).
#: This list only shrinks -- a control that appears is struck.
KNOWN_GAPS: dict[str, set[str]] = {}
#: Qt controls present under another spelling, or chrome of the Qt widgets.
RENAMED = {
    "true": "a ticked Fixed / Bounds cell: drawn as a check box",
    "false": "an unticked Fixed / Bounds cell: drawn as a check box",
    "nan": "a parameter without a value or error: the table writes N/A",
    "inf": "an unbounded Hi: the table writes inf only where it is set",
    "statescheme&&kinetics": "Qt's escaped '&' in a group title; the panel reads 'State Scheme & Kinetics'",
    "➕files": "the shared emtk file list's 'Add files'",
    "➖remove": "the shared emtk file list's 'Remove'",
    "📁folder": "the shared emtk file list's 'Folder'",
    "🗄️database": "the shared emtk file list's 'Database'",
    "🗑️clear": "the shared emtk file list's 'Clear'",
    "∥": "chitable's fit-columns button: the emtk table sizes its columns itself (fit_columns)",
    "☑️": "chitable's column picker button: a right click on the emtk table's header",
    "🧹": "chitable's clear-filters button: the emtk table's filter box",
}
#: Qt editor text that is data of the user's environment, not a control: the dye names of the
#: ``Dye`` list come from the MMFDB repository the session reads (an isolated test session may
#: have none), the global table's row count from the fits of the session.
ENVIRONMENT = re.compile(r"^(2-aminopurine|alexa\d+|atto\d+\w*|cy\d|\d+rows×\d+columns)$")


@pytest.fixture
def shell():
    """A shell with no plugins and its own session (server on free ports, fresh state)."""
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    state = SessionState()
    session = start_session(state=state)
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    app.state = state
    yield app
    app.close()


def _settle(driver: Driver, predicate, what: str, timeout: float = 180.0) -> None:
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}: {driver.app.data.status}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _idle(shell) -> bool:
    return not shell.data.busy and not shell.data._dirty


def _load(driver: Driver, shell, path: Path, experiment: str, setup: str) -> dict:
    data = shell.data
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    data.read.experiment = experiment
    data.read.experiment_changed(experiment)
    data.read.setup = setup
    data.read.path = str(path)
    count = len(data.datasets.datasets)
    driver.click("read.load")
    _settle(driver, lambda: _idle(shell) and len(data.datasets.datasets) > count, path.name)
    return data.datasets.datasets[-1]


def _add_pda(driver: Driver, shell) -> dict:
    """A synthetic two-colour PDA dataset in the session (the PTU reader's shape, no photon file)."""
    import chisurf
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    sys.path.insert(0, str(Path(__file__).parent))
    from capture_shell_s2_models_qt_before import make_pda_curve

    ensure_experiments_registered(allow_widgets=False)
    reader = next(r for r in chisurf.experiment["PDA"].readers if str(r.name) == "PTU/HT3/SPC")
    curve = make_pda_curve()
    curve.experiment = reader.experiment
    curve.setup = reader
    count = len(shell.data.datasets.datasets)
    shell.state.add_dataset(curve)
    shell.data._dirty |= {"datasets"}
    _settle(driver, lambda: _idle(shell) and len(shell.data.datasets.datasets) > count, "PDA data")
    return shell.data.datasets.datasets[-1]


def _add_fit(driver: Driver, shell, dataset: dict, model: str) -> str:
    data = shell.data
    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    data.datasets.select_dataset(dataset)
    data.datasets.model = model
    count = len(data.datasets.fits)
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and len(data.datasets.fits) > count, f"the {model} fit")
    return data.datasets.fits[-1]["uid"]


def _show(driver: Driver, shell, uid: str) -> None:
    """Make fit *uid* current and bring the Analysis dock (with its editor) to the front."""
    data = shell.data
    data.datasets.select_fit({"uid": uid})
    _settle(driver, lambda: _idle(shell) and data.editor.uid == uid, "the fit's editor")
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(3)


def _model(shell, uid: str):
    return next(f for f in shell.state.fits if str(f.unique_identifier) == uid).model


def _section(shell, key: str) -> dict:
    """A resolved curve picker (by its key) or custom section (by its key or address)."""
    return next(s for s in shell.data.editor.sections.data.values() if key in (s.get("key"), s.get("id")))


def _click_editor(driver: Driver, shell, name: str) -> None:
    key = f"editor.{name}"
    # The rectangles of the editor as it is drawn now: a re-read table settles its height in a frame or two.
    last = None
    for _ in range(10):
        driver.frame(1)
        rect = shell.item_rects.get(key)
        if rect is not None and rect == last:
            break
        last = rect
    assert key in shell.item_rects, f"{name} is not drawn: {sorted(shell.item_rects)}"
    driver.click(key)


def _tcspc(driver: Driver, shell) -> tuple[dict, dict]:
    prompt = _load(driver, shell, TCSPC / "Prompt.txt", "TCSPC", "TXT/CSV")
    decay = _load(driver, shell, TCSPC / "Decay_577D.txt", "TCSPC", "TXT/CSV")
    return prompt, decay


def _pick_curve(driver: Driver, shell, key: str, row: dict) -> None:
    """``…`` of a curve picker, then the dataset in the popup it opened."""
    _click_editor(driver, shell, f"curve.{key}.pick")
    picker = shell.data.dataset_picker
    assert picker is not None, "the ``…`` opened the session's datasets"
    picker.pick(next(i for i, r in enumerate(picker.rows) if r["uid"] == row["uid"]))
    _settle(driver, lambda: _idle(shell), f"{key} loaded")


def test_the_irf_and_background_pickers_load_and_unload_a_session_curve(shell, caplog):
    driver = Driver(shell, size=(1500, 2400))
    prompt, decay = _tcspc(driver, shell)
    uid = _add_fit(driver, shell, decay, "FRET: Gaussian distances")
    _show(driver, shell, uid)
    _pick_curve(driver, shell, "convolve.irf", prompt)
    model = _model(shell, uid)
    assert model.convolve.irf is not None and "Prompt" in model.convolve.irf.name
    irf = _section(shell, "convolve.irf")
    assert irf["loaded"] and "Prompt" in irf["curve_name"] and irf["fwhm"] == pytest.approx(18.0)
    assert "18.000" in driver.painter.strings, "the FWHM is shown"
    _pick_curve(driver, shell, "generic.background_curve", prompt)
    assert model.generic.background_curve is not None
    driver.frame(4)
    # The fit window's Fit page gets a line for the IRF it did not have when it was built.
    assert "updating the Fit page failed" not in caplog.text
    driver.screenshot(SHOTS / "emtk_shell_tcspc_curves.png")
    _click_editor(driver, shell, "curve.generic.background_curve.unload")
    _settle(driver, lambda: _idle(shell) and not _section(shell, "generic.background_curve")["loaded"],
            "the background unloaded")
    assert model.generic.background_curve is None
    from chisurf.core.api._client import RemoteError

    with pytest.raises(RemoteError, match="declares no curve input"):
        shell.data.session.api.model_curve_set("bogus.curve", prompt["uid"], fit_uid=uid)


def test_kappa2_controls_switch_the_regime_and_open_their_windows(shell):
    driver = Driver(shell, size=(1500, 2400))
    _prompt, decay = _tcspc(driver, shell)
    uid = _add_fit(driver, shell, decay, "FRET: Gaussian distances")
    _show(driver, shell, uid)
    model = _model(shell, uid)
    _click_editor(driver, shell, "kappa2.static")
    _settle(driver, lambda: _idle(shell) and model.orientation_parameter.mode == "slow", "static κ²")
    assert _section(shell, "kappa2_controls:")["data"]["mode"] == "slow"
    _click_editor(driver, shell, "kappa2.show")
    window = shell.data.editor.sections.dialogs[-1]
    _settle(driver, lambda: _idle(shell) and window.data, "the κ² distribution")
    assert window.data["k2"] and window.data["ratio"]
    driver.frame(2)
    driver.screenshot(SHOTS / "emtk_shell_kappa2_show.png")
    driver.click(window.rects["ok"])
    driver.frame(2)
    assert not window.open
    _click_editor(driver, shell, "kappa2.compute")
    dialog = shell.data.editor.sections.dialogs[-1]
    driver.frame(3)
    driver.screenshot(SHOTS / "emtk_shell_kappa2_compute.png")
    mean = float(dialog.model.k2_mean)
    driver.click(dialog.rects["ok"])
    _settle(driver, lambda: _idle(shell), "the κ² distribution applied")
    assert model.fret_parameters.kappa2 == pytest.approx(mean, rel=1e-6)
    assert model.orientation_parameter.orientation_spectrum is not None
    _click_editor(driver, shell, "kappa2.r0")
    forster = shell.data.editor.sections.dialogs[-1]
    assert type(forster).__name__ == "ForsterCalculatorDialog"
    forster.on_close(61.5)
    _settle(driver, lambda: _idle(shell), "R0 written")
    assert model.fret_parameters.forster_radius == pytest.approx(61.5)


def test_lifetime_amplitude_options_and_the_r_t_window(shell):
    driver = Driver(shell, size=(1500, 2400))
    _prompt, decay = _tcspc(driver, shell)
    first = _add_fit(driver, shell, decay, "Lifetime")
    uid = _add_fit(driver, shell, decay, "Lifetime")
    _show(driver, shell, uid)
    model = _model(shell, uid)
    ident = "lifetime_amplitude_options:lifetimes"
    _click_editor(driver, shell, f"amplitudes.{ident}.abs")
    _settle(driver, lambda: _idle(shell) and not model.lifetimes.absolute_amplitudes, "Abs. off")
    other = _model(shell, first)
    other.lifetimes.parameters_all[1].value = 2.5
    _click_editor(driver, shell, f"amplitudes.{ident}.read")
    driver.frame(2)
    menu = shell.data.editor.sections.dialogs[-1]
    item = next(e for e in menu.panel.entries if getattr(e, "enabled", True))
    menu.panel.open = False
    menu.calls[id(item)]()
    _settle(driver, lambda: _idle(shell), "read")
    assert model.lifetimes.parameters_all[1].value == pytest.approx(2.5)
    _click_editor(driver, shell, "anisotropy.diag")
    driver.frame(2)
    assert "This model reports no corrected VV/VH integrals." in driver.painter.strings
    _click_editor(driver, shell, "anisotropy.rt")
    window = shell.data.editor.sections.dialogs[-1]
    _settle(driver, lambda: _idle(shell) and (window.error or window.data), "r(t)")
    # One fit is not a VV/VH pair: the window says so, as the Qt one did.
    assert "VV/VH channels are not available" in window.error


def test_the_l_curve_is_swept_and_its_corner_adopted(shell):
    driver = Driver(shell, size=(1500, 2600))
    kristine = _load(driver, shell, KRISTINE, "FCS", "Seidel Kristine")
    uid = _add_fit(driver, shell, kristine, "FCS MaxEnt")
    _show(driver, shell, uid)
    form = shell.data.editor.form
    form.folds["L-curve"] = True
    driver.frame(3)
    ident = "lcurve:l_curve"
    shell.data.editor.sections.sweep[ident] = [-3.0, 1.0, 8.0]
    _click_editor(driver, shell, f"lcurve.{ident}.sweep")
    _settle(driver, lambda: _idle(shell) and _section(shell, "lcurve")["data"]["reg"], "the sweep",
            timeout=600)
    data = _section(shell, "lcurve")["data"]
    assert len(data["reg"]) == 8
    driver.screenshot(SHOTS / "emtk_shell_lcurve.png")
    if data["corner_index"] is not None:
        _click_editor(driver, shell, f"lcurve.{ident}.corner")
        _settle(driver, lambda: _idle(shell), "the corner")


def test_rate_matrix_cells_and_the_link_menu(shell):
    driver = Driver(shell, size=(1500, 2400))
    kristine = _load(driver, shell, KRISTINE, "FCS", "Seidel Kristine")
    other = _add_fit(driver, shell, kristine, "FCS (general: diffusion + bunching/anticorr)")
    uid = _add_fit(driver, shell, kristine, "FCS (kinetics)")
    _show(driver, shell, uid)
    sections = shell.data.editor.sections
    ident = "rate_matrix:saturation.dark.rate_values"
    row = next(r for name, rows in shell.data.editor._sources.items() if name.startswith("section_rows_")
               for r in rows if r.get("_section") == ident and r["_i"] == 1)
    assert sections.editable(row, "c0") and not sections.editable(row, "c1"), "the diagonal is no rate"
    shell.data.editor.section_edit_rate(row, "c2", 7.5)
    _settle(driver, lambda: _idle(shell), "the rate")
    model = _model(shell, uid)
    n = int(model.saturation.n_states)
    assert list(model.saturation.dark.rate_values)[1 * n + 2] == pytest.approx(7.5)
    driver.screenshot(SHOTS / "emtk_shell_rate_matrix.png")

    # The link menu: a right click on a parameter row, a fit, its parameter.
    table_row = next(r for name, rows in shell.data.editor._sources.items()
                     if name.startswith("rows_") for r in rows if r["name"] == "N")
    shell.data.editor.section_context(table_row, "value", (100.0, 100.0))
    _settle(driver, lambda: _idle(shell) and shell.data.editor.sections.dialogs, "the link menu")
    menu = shell.data.editor.sections.dialogs[-1]
    info = shell.data.session.api.get_fit_info(fit_uid=other) or {}
    info = info.get("fit", info)
    target = next(p for p in info["model"]["parameters_all"] if p["name"] == "N")
    call = next(c for item_id, c in menu.calls.items()
                if getattr(c, "__defaults__", None) and c.__defaults__[0] == target["uid"])
    menu.panel.open = False
    call()
    _settle(driver, lambda: _idle(shell), "the link")
    linked = next(p for p in _model(shell, uid).parameters_all if
                  str(p.unique_identifier) == table_row["uid"])
    assert str(linked.link.unique_identifier) == target["uid"]
    row = next(r for name, rows in shell.data.editor._sources.items()
               if name.startswith("rows_") for r in rows if r["uid"] == table_row["uid"])
    assert row["linked"], "the editor shows the parameter as linked"


def test_scalar_table_file_list_and_global_table(shell):
    # Tall: the structure fit's editor is long, and its file list sits at the end of it.
    driver = Driver(shell, size=(1500, 5200))
    pda = _add_pda(driver, shell)
    uid = _add_fit(driver, shell, pda, "PDA2c-discrete")
    _show(driver, shell, uid)
    table = _section(shell, "scalar_table")
    first = table["data"]["rows"][0]
    row = dict(first, _section=table["id"])
    value = 0.25 if first["kind"] == "float" else 7
    shell.data.editor.section_edit_scalar(row, "value", value)
    _settle(driver, lambda: _idle(shell), "the scalar")
    owner = _model(shell, uid)
    target = table["target"]
    if target:
        owner = getattr(owner, target)
    assert getattr(owner, first["attr"]) == pytest.approx(value)
    driver.screenshot(SHOTS / "emtk_shell_pda_scalar_table.png")

    _prompt, decay = _tcspc(driver, shell)
    structure = _add_fit(driver, shell, decay, "FRET: Structure fit")
    _show(driver, shell, structure)
    api = shell.data.session.api
    editor = shell.data.editor
    # The dyes' residues first (T4 lysozyme numbers from 1): an AV needs an atom to sit on.
    for key, residue in (("res_1", 44), ("res_2", 132)):
        setattr(editor, editor.control_for(key), residue)
        _settle(driver, lambda: _idle(shell), key)
    ident = "path_list:structure_files"
    # The list is what the section writes and shows; whether a PDB yields accessible volumes is
    # the model's (an AV on 148L samples no states today: okf/references/known-issues.md).
    model = _model(shell, structure)
    model.load_structures = lambda paths: model.__dict__.__setitem__(
        "_structure_files", [str(p) for p in paths])
    assert api.model_section_call(ident, "add", {"paths": [str(PDB)]}, fit_uid=structure)["ok"]
    shell.data.reread_current()
    _settle(driver, lambda: _idle(shell) and _section(shell, "path_list")["data"]["paths"], "the file")
    assert model.structure_files == [str(PDB)]
    driver.frame(3)
    assert "148l.pdb" in driver.painter.strings
    _click_editor(driver, shell, "structure_files.clear")
    _settle(driver, lambda: _idle(shell) and not _section(shell, "path_list")["data"]["paths"],
            "the list cleared")

    lifetime = _add_fit(driver, shell, decay, "Lifetime")
    global_row = next(r for r in shell.data.datasets.datasets if r["experiment"] == "Global")
    glob = _add_fit(driver, shell, global_row, "Global fit")
    _show(driver, shell, glob)
    editor = shell.data.editor
    names = {f["uid"]: f["name"] for f in api.list_fits()}
    setattr(editor, editor.control_for("selected_candidate_fit"), names[lifetime])
    _settle(driver, lambda: _idle(shell), "the candidate")
    _click_editor(driver, shell, editor.action_for("press", "add_selected_fit"))
    _settle(driver, lambda: _idle(shell), "the fit added")
    rows = _section(shell, "global_parameter_table")["data"]["rows"]
    assert rows and {"row", "owner", "link_row"} <= set(rows[0])
    driver.screenshot(SHOTS / "emtk_shell_global_parameter_table.png")


def _inventory(driver: Driver, shell) -> set[str]:
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from migration_parity import _normalize_control_text

    editor = shell.data.editor
    # Every panel open, as the Qt inventory counts folded widgets too.
    def walk(sections):
        for section in sections:
            if section.get("type") == "panel" and section.get("title"):
                editor.form.folds[section["title"]] = True
            walk(section.get("sections") or [])

    walk(editor.spec.get("sections", []))
    found: set[str] = set()
    for _ in range(3):
        driver.frame(2)
        found |= {_normalize_control_text(t) for t in driver.painter.strings}
    found |= {_normalize_control_text(t) for t in editor.inventory()}
    for rows in editor._sources.values():
        for row in rows:
            for key in ("label", "name", "state"):
                if row.get(key):
                    found.add(_normalize_control_text(editor.plain_label(str(row[key]))))
    from chisurf.emtk.model_editor import PARAMETER_COLUMNS

    found |= {_normalize_control_text(c["label"]) for c in PARAMETER_COLUMNS}
    return found - {""}


def test_parity_with_the_qt_model_editors(shell):
    """Control inventory of the Qt model editors (TCSPC with IRF and background, mixture, MaxEnt,
    structure, FCS kinetics, PDA, global fit, ProteinMC) against the emtk Analysis dock's editor."""
    before = json.loads(
        Path(__file__).with_name("shell_s2_models_qt_inventory.json").read_text("utf-8")
    )["models"]
    driver = Driver(shell, size=(1500, 4000))
    prompt, decay = _tcspc(driver, shell)
    fits: dict[str, str] = {}
    for key, model in (
        ("tcspc_lifetime", "Lifetime"),
        ("tcspc_fret_gaussian", "FRET: Gaussian distances"),
        ("tcspc_mixture", "Lifetime mixture"),
        ("tcspc_maxent_lifetime", "Lifetime: MaxEnt"),
        ("fret_structure", "FRET: Structure fit"),
    ):
        fits[key] = _add_fit(driver, shell, decay, model)
        if key != "fret_structure":
            _show(driver, shell, fits[key])
            for curve in ("convolve.irf", "generic.background_curve"):
                if f"editor.curve.{curve}.pick" in shell.item_rects:
                    _pick_curve(driver, shell, curve, prompt)
    kristine = _load(driver, shell, KRISTINE, "FCS", "Seidel Kristine")
    fits["fcs_kinetics"] = _add_fit(driver, shell, kristine, "FCS (kinetics)")
    pda = _add_pda(driver, shell)
    fits["pda_discrete"] = _add_fit(driver, shell, pda, "PDA2c-discrete")
    fits["pda_dynamic_n"] = _add_fit(driver, shell, pda, "PDA2c-dynamic-N-state")
    global_row = next(r for r in shell.data.datasets.datasets if r["experiment"] == "Global")
    fits["global_fit"] = _add_fit(driver, shell, global_row, "Global fit")
    structure = _load(driver, shell, PDB, "Modelling", "StructureReader")
    fits["proteinmc"] = _add_fit(driver, shell, structure, "ProteinMC")
    report = {}
    for key, uid in fits.items():
        _show(driver, shell, uid)
        after = _inventory(driver, shell)
        driver.screenshot(SHOTS / f"emtk_shell_model_{key}.png")
        qt = set(before[key]["controls"])
        lost = {
            c for c in qt - after
            if not _NUMBER.match(c) and "/users/" not in c and not ENVIRONMENT.match(c)
        }
        unexplained = lost - KNOWN_GAPS.get(key, set()) - set(RENAMED)
        closed = KNOWN_GAPS.get(key, set()) & after
        if unexplained or closed:
            report[key] = {"lost": sorted(unexplained), "closed": sorted(closed)}
    assert not report, f"Qt controls missing from the emtk editor: {json.dumps(report, indent=1)}"
