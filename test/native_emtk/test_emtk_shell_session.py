"""The emtk shell's session menus (W9 S3): project files, undo/redo, the close guard, the fit window's ×.

The shell gets a real in-process server on private ports with a fresh session state (as in
``test_emtk_shell_fits.py``); the recent-projects list and the working folder are redirected to
``tmp_path``. Questions are answered as a user answers them -- by pressing their buttons through
:class:`emtk.testing.Driver` -- or, where a test is about what happens *after* the answer, by
:func:`emtk.message_dialog.auto_answer`.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from emtk.events import CONTROL_MODIFIER, SHIFT_MODIFIER
from emtk.message_dialog import auto_answer
from emtk.testing import Driver

from chisurf.emtk.fit_docks import DATASETS_KEY, READ_KEY
from chisurf.emtk.main_app import EmtkShellApp, parse_shortcut

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
BEFORE = json.loads((Path(__file__).with_name("shell_s3_qt_inventory.json")).read_text("utf-8"))

#: Qt session controls the emtk shell does not have yet; each is an open item of the ledger
#: (``okf/subsystems/qt-retirement.md``, slice S3). This list only shrinks.
KNOWN_GAPS: dict[str, str] = {}
#: Qt controls present under another spelling, or replaced on purpose.
RENAMED = {
    "exportproject...": "Export Project… (the ellipsis character)",
    "openproject...": "Open Project…",
    "importproject...": "Import Project…",
    "fretrdaaxis...": "FRET RDA axis…",
    "dataloading...": "Data loading…",
    "cascadefitwindows": "View ▸ Workspace ▸ Cascade Windows: cascades every workspace window, fits included",
    "dataset": "the Docks toggle is called Read data, the dock's own title",
    "fit": "the Docks toggle is called Analysis, the dock's own title",
    "plot-options": "the Docks toggle is called Plot settings, the dock's own title",
    "typehere": "Qt Designer's empty placeholder submenu, never had an item",
    "1": "the Qt box's form-row numbering, not a control",
    "2": "the Qt box's form-row numbering, not a control",
}
#: Qt shortcuts the emtk shell does not bind, and why.
SHORTCUT_GAPS = {
    "Load result in current fit": "Ctrl+L: a Qt-shell action with no handler and in no menu; not carried over",
    "Close": "Ctrl+F4: Qt's MDI sub-window system menu; a fit window's × asks and removes the fit",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text).replace("&", "")).lower()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Recent projects and the working folder in ``tmp_path``: the tests never touch real settings."""
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    return tmp_path


@pytest.fixture
def shell(isolated):
    """A shell with no plugins and its own session (server on free ports, fresh state)."""
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    yield app
    app.close()
    session.close()


def _idle(shell) -> bool:
    project = shell.project
    return (
        not shell.data.busy
        and not shell.data._dirty
        and not project.busy
        and not project._record_topic
        and not project._removing_fit
    )


def _settle(driver: Driver, predicate, what: str, timeout: float = 120.0) -> None:
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, (
            f"timed out waiting for {what}: {driver.app.data.status} / {driver.app.project.status}"
        )
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _demo_fit(driver: Driver, shell) -> str:
    """Read the FCS demo curve and add the demo's model as a fit; the fit's uid."""
    data = shell.data
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    driver.click("read.use_demo")
    driver.frame(2)
    driver.click("read.load")
    _settle(
        driver,
        lambda: _idle(shell) and any(r["name"] == "fcs_demo" for r in data.datasets.datasets),
        "the demo dataset",
    )
    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    driver.click("datasets.add_fit")
    _settle(
        driver,
        lambda: (
            _idle(shell) and data.windows and data.analysis.info and shell.project.history_ready
        ),
        "the fit window",
    )
    return data.current_uid


def _value(shell, name: str) -> float:
    return float(
        shell.data.session.api.get_parameter(name, fit_uid=shell.data.current_uid)["value"]
    )


def _row(shell, name: str) -> dict:
    return next(row for row in shell.data.analysis.parameters if row["name"] == name)


def _click_answer(driver: Driver, shell, key: str) -> None:
    """Press the open question's button *key*."""
    question = shell.project.dialogs.current
    assert question is not None, "no question is open"
    driver.frame(1)
    driver.click(question.rects[f"button.{key}"])
    driver.frame(1)


# ── menus and shortcuts ───────────────────────────────────────────────────────


def _qt_items(rows, out: list[str]) -> list[str]:
    for row in rows:
        if row.get("separator"):
            continue
        out.append(row["text"])
        _qt_items(row.get("menu", []), out)
    return out


def test_the_session_menus_bind_the_qt_shortcuts(shell):
    """Every shortcut of the Qt main window is bound to the same item, or is an explained gap."""
    by_label = {}
    for _menu, actions in shell.session_menus():
        for action in actions:
            if action.shortcut:
                by_label[action.key] = action.shortcut
    labels = {
        action.label: action.shortcut for _m, actions in shell.session_menus() for action in actions
    }
    for qt_label, keys in BEFORE["shortcuts"].items():
        if qt_label in SHORTCUT_GAPS:
            continue
        mine = labels.get(qt_label) or labels.get(qt_label.replace("...", "…"))
        assert mine == keys, f"{qt_label}: Qt binds {keys}, the emtk shell {mine!r}"
    table = shell.shortcuts()
    assert parse_shortcut("Ctrl+Shift+S") in table and parse_shortcut("Ctrl+S") in table
    assert table[parse_shortcut("Ctrl+Shift+S")].key == "export_project"
    assert len(table) == len(by_label), "two items share a shortcut"


def test_parity_with_the_qt_session_menus(shell):
    """Every item of the Qt File / View / Macro / Settings menus is drawn in the emtk menus."""
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    drawn: set[str] = set()
    for title, actions in shell.session_menus():
        driver.click(f"menu.{title}")
        driver.frame(2)
        strings = set(driver.painter.strings)
        drawn |= {_norm(s) for s in strings}
        for action in actions:
            assert action.label in strings, f"{title} ▸ {action.label} is not drawn"
            if action.group:
                assert action.group in strings, f"{title} ▸ {action.group} caption is not drawn"
        output = SHOTS
        output.mkdir(parents=True, exist_ok=True)
        driver.screenshot(output / f"emtk_shell_menu_{_norm(title)}.png")
        driver.escape()
        driver.frame(2)
    before = set()
    for menu, rows in BEFORE["menus"].items():
        before.add(_norm(menu))
        before |= {_norm(text) for text in _qt_items(rows, [])}
    lost = before - drawn - set(RENAMED)
    unexplained = lost - set(KNOWN_GAPS)
    assert not unexplained, f"Qt menu items missing in the emtk shell: {sorted(unexplained)}"
    closed = set(KNOWN_GAPS) & drawn
    assert not closed, f"these gaps are closed now; strike them from KNOWN_GAPS: {sorted(closed)}"


def test_parity_with_the_qt_project_dialogs(shell, monkeypatch):
    """The database save form, the collision question and the three guard questions offer Qt's controls."""
    from emtk.view_form import FormState  # noqa: F401 - the form is drawn by the shell

    from chisurf.core.project import storage

    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    output = SHOTS
    output.mkdir(parents=True, exist_ok=True)

    def controls(strings) -> set[str]:
        return {_norm(s) for s in strings}

    # The database Save Project form (a configured MMFDB deployment).
    monkeypatch.setattr(storage, "select_backend", lambda *a, **k: "mmfdb")
    shell.project.save()
    driver.frame(3)
    form = controls(driver.painter.strings)
    # A choice's other options are in its drop-down (reachable), as the Qt inventory counts combo items.
    for section in shell.project.form.spec["sections"]:
        form |= {_norm(label) for _value, label in section.get("options", [])}
    driver.screenshot(output / "emtk_shell_save_project_form.png")
    qt = {_norm(c) for c in BEFORE["dialogs"]["SaveProjectDialog"]["controls"]} - set(RENAMED)
    assert qt - form == set(), f"Save Project form lacks {sorted(qt - form)}"
    driver.click(shell.project.form.rects["cancel"])
    driver.frame(2)
    assert shell.project.form is None

    # The collision question of an import.
    monkeypatch.setattr(storage, "database_client", lambda *a, **k: object())
    monkeypatch.setattr(
        storage,
        "import_preview",
        lambda path, client=None: {
            "collisions": {"datasets": ["ds-1", "ds-2"], "fits": ["fit-1"]},
            "origin": {"project_id": "proj_x", "version_number": 3},
        },
    )
    shell.project.import_project()
    shell.project.choose_file("/tmp/x.cs.pto")
    _settle(driver, lambda: shell.project.dialogs.modal, "the collision question")
    strings = controls(driver.painter.strings)
    driver.screenshot(output / "emtk_shell_import_collisions.png")
    qt = {_norm(c) for c in BEFORE["dialogs"]["CollisionDialog"]["controls"] if len(c) < 40}
    assert qt - strings == set(), f"collision question lacks {sorted(qt - strings)}"
    assert "ds-1" in " ".join(driver.painter.strings), "the colliding ids are listed"
    _click_answer(driver, shell, "cancel")
    assert not shell.project.dialogs.modal

    # The unsaved-changes guard: Save / Don't Save / Cancel.
    shell.project.dialogs.choice(
        "Unsaved Project",
        "Save changes to the current project before continuing?",
        [("save", "Save"), ("discard", "Don't Save"), ("cancel", "Cancel")],
        None,
        default="cancel",
    )
    driver.frame(2)
    qt = {_norm(c) for c in BEFORE["dialogs"]["close_guard"]["controls"]}
    assert qt - controls(driver.painter.strings) == set()
    shell.project.dialogs.answer(None)
    for name in ("fit_close", "quit"):
        qt = {_norm(c) for c in BEFORE["dialogs"][name]["controls"] if c.startswith("&")}
        shell.project.dialogs.confirm("q", "?", None)
        driver.frame(2)
        assert qt - controls(driver.painter.strings) == set(), name
        shell.project.dialogs.answer(False)


# ── save, reopen, undo ──────────────────────────────────────────────────────────


def test_save_then_reopen_restores_datasets_fits_and_parameters(shell, isolated):
    driver = Driver(shell, size=(1500, 950))
    driver.frame(2)
    data, project = shell.data, shell.project
    uid = _demo_fit(driver, shell)
    data.analysis.edit_parameter(_row(shell, "N"), "value", 3.25)
    _settle(driver, lambda: _idle(shell) and _value(shell, "N") == 3.25, "N = 3.25")
    model = next(r["model"] for r in data.datasets.fits if r["uid"] == uid)

    # Ctrl+S on an unsaved project asks for a file; the choice is written and becomes the document.
    driver.press(ord("s"), CONTROL_MODIFIER)
    driver.frame(2)
    assert project.file_dialog is not None and project.file_dialog.mode == "save"
    target = isolated / "demo_project.cs.pto"
    project.choose_file(target)
    _settle(driver, lambda: _idle(shell) and project.document.path is not None, "the save")
    assert target.is_file()
    assert Path(project.document.path) == target
    assert project.recent[0] == str(target)

    # Close Project: saved work closes without a question and leaves an empty session.
    project.close_project()
    _settle(driver, lambda: _idle(shell) and not data.datasets.fits, "the empty session")
    assert not project.dialogs.modal, "saved work closes without asking"
    assert [r["name"] for r in data.datasets.datasets] in ([], ["Global Dataset"])

    # The recent entry reopens it: the dataset, the fit, its model and N come back.
    project.open_recent(str(target))
    _settle(
        driver, lambda: _idle(shell) and data.datasets.fits and data.windows, "the reopened project"
    )
    assert "fcs_demo" in [r["name"] for r in data.datasets.datasets]
    assert [r["model"] for r in data.datasets.fits] == [model]
    assert _value(shell, "N") == pytest.approx(3.25)
    assert project.document.path == target
    driver.screenshot(SHOTS / "emtk_shell_reopened.png")


def test_undo_and_redo_of_a_parameter_edit(shell):
    driver = Driver(shell, size=(1500, 950))
    driver.frame(2)
    data, project = shell.data, shell.project
    _demo_fit(driver, shell)
    before = _value(shell, "N")
    data.analysis.edit_parameter(_row(shell, "N"), "value", before + 1.5)
    _settle(driver, lambda: _idle(shell) and _value(shell, "N") == before + 1.5, "the edit")
    assert project.can_undo()
    driver.press(ord("z"), CONTROL_MODIFIER)
    _settle(
        driver, lambda: _idle(shell) and _value(shell, "N") == pytest.approx(before), "the undo"
    )
    assert _row(shell, "N")["value"] == pytest.approx(before), (
        "the Analysis dock shows the undone value"
    )
    assert project.can_redo()
    driver.press(ord("y"), CONTROL_MODIFIER)
    _settle(
        driver,
        lambda: _idle(shell) and _value(shell, "N") == pytest.approx(before + 1.5),
        "the redo",
    )
    assert not project.can_redo()
    assert data.windows, "the fit window is open over the restored fit"


# ── the close guard and the fit window's × ────────────────────────────────────


def test_the_close_guard_asks_once(shell, isolated):
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    project = shell.project
    _settle(driver, lambda: _idle(shell) and project.history_ready, "the session")

    # An empty session: one "Quit ChiSurf?" (gui.confirm_close_program), No keeps the window.
    assert shell.close_request() is False
    _settle(driver, lambda: project.dialogs.modal, "the quit question")
    assert len(project.dialogs.pending) == 1
    assert shell.close_request() is False, "a second close while asking does not ask again"
    driver.frame(2)
    assert len(project.dialogs.pending) == 1
    driver.screenshot(SHOTS / "emtk_shell_quit_question.png")
    _click_answer(driver, shell, "no")
    assert not shell.close_requested

    # Unsaved work: exactly one Save / Don't Save / Cancel; Cancel keeps everything.
    _demo_fit(driver, shell)
    assert shell.close_request() is False
    _settle(driver, lambda: project.dialogs.modal, "the unsaved-changes question")
    assert [q.kind for q in project.dialogs.pending] == ["choice"]
    driver.screenshot(SHOTS / "emtk_shell_close_guard.png")
    _click_answer(driver, shell, "cancel")
    driver.frame(3)
    assert not project.dialogs.modal and not shell.close_requested

    # Don't Save closes, with no second question.
    shell.close_request()
    _settle(driver, lambda: project.dialogs.modal, "the question again")
    _click_answer(driver, shell, "discard")
    driver.frame(2)
    assert shell.close_requested and not project.dialogs.modal
    assert shell.close_request() is True, "after the answer the window closes"


def test_a_saved_session_quits_without_a_question(shell, isolated):
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    project = shell.project
    _demo_fit(driver, shell)
    with auto_answer(defaults=True):
        project.save()
    project.choose_file(isolated / "saved.cs.pto")
    _settle(driver, lambda: _idle(shell) and project.document.path is not None, "the save")
    driver.press(ord("q"), CONTROL_MODIFIER)
    _settle(driver, lambda: shell.close_requested or project.dialogs.modal, "the quit")
    assert shell.close_requested and not project.dialogs.modal


def test_the_fit_window_close_asks_then_removes_the_fit(shell):
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    data, project = shell.data, shell.project
    uid = _demo_fit(driver, shell)
    key = data.windows[uid].key

    shell.docks.hide(key)  # the window's ×
    driver.frame(2)
    assert project.dialogs.modal and shell.docks.is_visible(key), "it asks before anything closes"
    driver.screenshot(SHOTS / "emtk_shell_fit_close.png")
    _click_answer(driver, shell, "no")
    _settle(driver, lambda: _idle(shell), "the declined close")
    assert uid in data.windows and shell.docks.is_visible(key), "No keeps the fit and its window"

    shell.docks.hide(key)
    driver.frame(2)
    _click_answer(driver, shell, "yes")
    _settle(driver, lambda: _idle(shell) and not data.datasets.fits, "the fit removed")
    assert uid not in data.windows
    assert data.session.api.list_fits() == []


def test_autosave_writes_a_silent_copy(shell, isolated):
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    project = shell.project
    _demo_fit(driver, shell)
    project.autosave_now()
    target = isolated / "autosave" / "untitled.autosave.cs.pto"
    _settle(driver, lambda: _idle(shell) and target.is_file(), "the autosave copy")
    assert not project.dialogs.modal, "autosave never asks"
    assert project.document.path is None, "autosave is not a save"
    mtime = target.stat().st_mtime_ns
    project.autosave_now()
    _settle(driver, lambda: _idle(shell), "the second tick")
    assert target.stat().st_mtime_ns == mtime, "an unchanged session is not written again"


def test_shortcut_parsing():
    assert parse_shortcut("Ctrl+Shift+S") == (ord("s"), CONTROL_MODIFIER | SHIFT_MODIFIER)
    assert parse_shortcut("") is None


def test_import_remaps_through_one_client(shell, monkeypatch):
    """Import on a database: preview, the collision question, then import -- one client, Import Complete."""
    from chisurf.core.project import storage

    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    client = object()
    seen = []
    monkeypatch.setattr(storage, "select_backend", lambda *a, **k: "mmfdb")
    monkeypatch.setattr(storage, "database_client", lambda *a, **k: client)
    monkeypatch.setattr(
        storage,
        "import_preview",
        lambda path, client=None: (
            seen.append(client)
            or {
                "collisions": {"fits": ["fit-1"]},
                "origin": {"project_id": "proj_x", "version_number": 2},
            }
        ),
    )

    def imported(path, resolve_collisions, client=None):
        seen.append((client, resolve_collisions))
        return {"project_id": "proj_y", "version_id": "v", "version_number": 1}

    monkeypatch.setattr(storage, "import_database", imported)
    shell.project.import_project()
    assert shell.project.file_dialog is not None
    shell.project.choose_file("/tmp/archive.cs.pto")
    _settle(driver, lambda: shell.project.dialogs.modal, "the collision question")
    _click_answer(driver, shell, "import")
    _settle(driver, lambda: shell.project.dialogs.modal, "the completion message")
    assert seen == [client, (client, True)]
    assert "proj_y" in shell.project.dialogs.current.message
    _click_answer(driver, shell, "ok")


def test_recent_list_and_history_steps(isolated):
    from chisurf.core.project import recent
    from chisurf.history.core import OperationHistory

    names = [str(isolated / f"p{i}.cs.pto") for i in range(12)]
    listed: list[str] = []
    for name in names:
        listed = recent.added(listed, name)
    assert listed[0] == names[-1] and len(listed) == recent.LIMIT
    assert recent.added(listed, names[-3])[0] == names[-3], "reopening moves it to the top"
    assert names[-1] not in recent.removed(listed, names[-1])
    recent.store(listed)
    assert recent.load() == listed

    history = OperationHistory()
    assert history.step_target(-1) is None and history.step_target(+1) is None


def test_the_settings_forms_draw_their_controls(shell):
    """Settings ▸ FRET RDA axis… and Data loading… open their forms; Close closes them."""
    driver = Driver(shell, size=(1400, 900))
    driver.frame(2)
    project = shell.project
    for run, wanted, name in (
        (project.rda_axis, {"R_DA min", "R_DA max", "N points", "Scale", "Save axis"}, "rda_axis"),
        (
            project.data_loading,
            {"Enable staging", "Slow below", "Max points per plot"},
            "data_loading",
        ),
    ):
        run()
        driver.frame(3)
        assert wanted <= set(driver.painter.strings), (
            f"{name}: {wanted - set(driver.painter.strings)}"
        )
        driver.screenshot(SHOTS / f"emtk_shell_settings_{name}.png")
        driver.click(project.form.rects["close"])
        driver.frame(2)
        assert project.form is None
