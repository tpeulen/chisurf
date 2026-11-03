"""The emtk package manager: tables, filter, and the command line each button's call hands the solver.

SAFETY: ``PackageManager._popen`` is a fake (``fakes.py``); every command line is recorded and asserted, none is run. The
expected rows are the fakes' own inputs (``INSTALLED``, ``ENVS``, ``CHANNELS``); the expected command lines are written
out here with the solver path the fakes install and this environment's ``sys.prefix``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from .fakes import CHANNELS, ENVS, INSTALLED

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SOLVER = "/fake/bin/micromamba"


def ops(fakes):
    """The solver calls that change something (the refreshes that follow every operation are read-only)."""
    return [c for c in fakes.solver_commands if c in fakes.mutating_solver_commands]


@pytest.fixture
def model(fakes):
    from chisurf.plugins.core.updater.gui.package_model import PackageManagerModel

    m = PackageManagerModel()
    m.refresh_all()
    fakes.solver_commands.clear()
    return m


def pick(model, kind, **match):
    rows = {
        "installed": model.installed_rows,
        "search": model.search_rows,
        "env": model.env_rows,
        "channel": model.channel_rows,
    }[kind]
    record = next(r for r in rows if all(r[k] == v for k, v in match.items()))
    getattr(
        model,
        "select_"
        + {"installed": "installed", "search": "search", "env": "env", "channel": "channel"}[kind],
    )(record)


def confirm(model, kind, accept=True, text=""):
    assert model.dialog == kind, (model.dialog, kind)
    if text:
        model.dialog_input = text
    (model.dialog_ok if accept else model.dialog_cancel)()


# ------------------------------------------------------------------------------------------------ what is loaded
def test_the_lists_loaded_on_opening_are_what_the_solver_listed(fakes):
    from chisurf.plugins.core.updater.gui.package_model import TABS, PackageManagerModel

    m = PackageManagerModel()
    m.refresh_all()
    assert [[r["name"], r["version"], r["channel"]] for r in m.installed_rows] == [
        [p["name"], p["version"], p["channel"]] for p in INSTALLED
    ]
    assert [r["env"] for r in m.env_rows] == ENVS
    assert [r["channel"] for r in m.channel_rows] == CHANNELS
    assert m.current_env == sys.prefix
    assert list(TABS) == ["Installed Packages", "Search & Install", "Environments", "Channels"]
    assert sorted(map(tuple, fakes.solver_commands)) == sorted(
        [
            (SOLVER, "list", "--json", "-p", sys.prefix),
            (SOLVER, "config", "--show", "--json"),
            (SOLVER, "env", "list", "--json"),
        ]
    )
    assert [line.split("] ", 1)[1] for line in m.log] == [
        "Refreshing installed packages...",
        "Loaded 5 packages.",
    ]
    assert ops(fakes) == []


def test_the_filter_keeps_the_names_containing_the_text_in_any_case(model):
    model.installed_filter = "NUM"
    model.apply_filter()
    assert [[r["name"], r["version"], r["channel"]] for r in model.installed_rows] == [
        [p["name"], p["version"], p["channel"]] for p in INSTALLED if "num" in p["name"].lower()
    ]
    model.installed_filter = ""
    model.apply_filter()
    assert len(model.installed_rows) == 5


def test_search_lists_the_rows_conda_and_micromamba_print(model, fakes):
    from .fakes import SEARCH_CONDA, SEARCH_MICROMAMBA

    for payload in (SEARCH_CONDA, SEARCH_MICROMAMBA):
        fakes.search_payload = payload
        model.search_query = " numpy "
        model.search_packages()
        assert [(r["name"], r["version"], r["channel"]) for r in model.search_rows] == [
            ("numpy", "2.0.1", "conda-forge"),
            ("numpy", "1.26.4", "conda-forge"),
            ("numpy", "1.26.3", "conda-forge"),
        ]
        assert fakes.solver_commands[-1] == ["/fake/bin/micromamba", "search", "numpy", "--json"]
        assert model.log[-1].endswith("Found 3 results.")
    fakes.search_payload = [
        {"name": "numpy", "version": "2.0.1", "channel": "conda-forge"},
        {"name": "numpy-base", "version": "1.26.4", "channel": "defaults"},
    ]
    model.search_packages()
    assert [[r["name"], r["version"], r["channel"]] for r in model.search_rows] == [
        [r["name"], r["version"], r["channel"]] for r in fakes.search_payload
    ]


def test_an_empty_query_searches_nothing(model, fakes):
    model.search_query = "   "
    model.search_packages()
    assert fakes.solver_commands == [] and not model.enabled("search_packages")


# ------------------------------------------------------------------------------------------------ one test per button
def test_install_selected_asks_and_runs_the_install_line(model, fakes):
    model.search_query = "numpy"
    model.search_packages()
    pick(model, "search", version="2.0.1")
    fakes.solver_commands.clear()
    model.ask_install_selected()
    assert (
        model.dialog_title == "Confirm Installation"
        and model.dialog_text == "Are you sure you want to install:\nnumpy?"
    )
    confirm(model, "install", accept=False)
    assert ops(fakes) == []  # declined: nothing runs
    model.ask_install_selected()
    confirm(model, "install")
    assert ops(fakes) == [
        ["/fake/bin/micromamba", "install", "-y", "--update-deps", "-p", sys.prefix, "numpy"]
    ]
    assert model.log[-1].endswith(
        "Loaded 5 packages."
    ) and "Operation completed successfully." in " ".join(model.log)


def test_update_selected_runs_the_update_line_without_a_question(model, fakes):
    pick(model, "installed", name="scipy")
    model.ask_update_selected()
    assert model.dialog == "" and ops(fakes) == [
        ["/fake/bin/micromamba", "update", "-y", "-p", sys.prefix, "scipy"]
    ]


def test_update_all_asks_and_runs_the_update_all_line(model, fakes):
    model.ask_update_all()
    assert model.dialog_text == "Update all packages in the current environment?"
    confirm(model, "update_all", accept=False)
    assert ops(fakes) == []
    model.ask_update_all()
    confirm(model, "update_all")
    assert ops(fakes) == [["/fake/bin/micromamba", "update", "-y", "-p", sys.prefix, "--all"]]


def test_remove_selected_asks_and_runs_the_remove_line_only_when_confirmed(model, fakes):
    pick(model, "installed", name="scipy")
    model.ask_remove_selected()
    assert (model.dialog_title, model.dialog_text) == (
        "Confirm Removal",
        "Are you sure you want to remove:\nscipy?",
    )
    confirm(model, "remove", accept=False)
    assert ops(fakes) == []
    model.ask_remove_selected()
    confirm(model, "remove")
    assert ops(fakes) == [["/fake/bin/micromamba", "remove", "-y", "-p", sys.prefix, "scipy"]]


def test_create_new_asks_for_a_name_and_runs_the_create_line(model, fakes):
    model.ask_create_env()
    assert model.dialog_text == "Enter environment name:" and not model.dialog_input_hidden == "yes"
    confirm(model, "create_env", text="")
    assert ops(fakes) == []  # no name, nothing
    model.ask_create_env()
    confirm(model, "create_env", text="scratch")
    assert ops(fakes) == [["/fake/bin/micromamba", "create", "-y", "-n", "scratch"]]


def test_clone_selected_asks_for_the_new_name_and_runs_the_clone_line(model, fakes):
    pick(model, "env", env="/fake/mambaforge/envs/analysis")
    model.ask_clone_env()
    assert model.dialog_text == "Enter new name for clone of '/fake/mambaforge/envs/analysis':"
    confirm(model, "clone_env", text="analysis-copy")
    assert ops(fakes) == [
        [SOLVER, "create", "-y", "-n", "analysis-copy", "--clone", "/fake/mambaforge/envs/analysis"]
    ]
    fakes.solver_commands.clear()
    model.env_rows = [{"env": "named"}]
    pick(model, "env", env="named")
    model.ask_clone_env()
    confirm(model, "clone_env", text="copy2")  # a name (no path separator) is cloned by name
    assert ops(fakes) == [
        ["/fake/bin/micromamba", "create", "-y", "-n", "copy2", "--clone", "named"]
    ]


def test_remove_environment_asks_and_runs_the_env_remove_line(model, fakes):
    pick(model, "env", env="/fake/mambaforge/envs/arm64")
    model.ask_remove_env()
    assert model.dialog_text == "Remove environment '/fake/mambaforge/envs/arm64'?"
    confirm(model, "remove_env", accept=False)
    assert ops(fakes) == []
    model.ask_remove_env()
    confirm(model, "remove_env")
    assert ops(fakes) == [[SOLVER, "env", "remove", "-y", "-p", "/fake/mambaforge/envs/arm64"]]
    fakes.solver_commands.clear()
    model.env_rows = [{"env": "named"}]
    pick(model, "env", env="named")
    model.ask_remove_env()
    confirm(model, "remove_env")
    assert ops(fakes) == [["/fake/bin/micromamba", "env", "remove", "-y", "-n", "named"]]


def test_export_writes_the_yaml_the_solver_printed_for_the_selected_environment(
    model, fakes, tmp_path
):
    pick(model, "env", env="/fake/mambaforge/envs/analysis")
    target = tmp_path / "exported.yaml"
    model.request_export()
    assert model.request == "export"
    model.export_to(str(target))
    assert fakes.solver_commands == [[SOLVER, "env", "export", "-p", "/fake/mambaforge/envs/analysis"]]
    assert target.read_text() == fakes.popen(None, [SOLVER, "env", "export"])[1]
    fakes.solver_commands.clear()
    model.sel_env = None  # nothing selected: the current environment
    model.export_to(str(target))
    assert fakes.solver_commands == [["/fake/bin/micromamba", "env", "export", "-p", sys.prefix]]


def test_export_to_an_unwritable_place_is_logged_not_raised(model, tmp_path):
    model.export_to(str(tmp_path / "no" / "such" / "dir" / "x.yaml"))
    assert "Failed to write file" in model.log[-1]


def test_import_asks_for_an_optional_name_and_runs_the_env_create_line(model, fakes, tmp_path):
    path = str(tmp_path / "env.yaml")
    model.import_from(path)
    assert model.dialog_text == "Enter name for new environment (optional):"
    confirm(model, "import_env", text="imported")
    assert ops(fakes) == [["/fake/bin/micromamba", "env", "create", "-f", path, "-n", "imported"]]
    fakes.solver_commands.clear()
    model.import_from(path)
    confirm(model, "import_env", text="")
    assert ops(fakes) == [["/fake/bin/micromamba", "env", "create", "-f", path]]


def test_add_and_remove_channel_run_the_config_lines(model, fakes):
    model.ask_add_channel()
    assert model.dialog_text == "Enter channel name or URL:"
    confirm(model, "add_channel", text="bioconda")
    assert ops(fakes) == [[SOLVER, "config", "--add", "channels", "bioconda"]]
    fakes.solver_commands.clear()
    pick(model, "channel", channel="conda-forge")
    model.remove_channel()
    assert ops(fakes) == [[SOLVER, "config", "--remove", "channels", "conda-forge"]]


def test_refresh_buttons_only_read(model, fakes):
    model.refresh_installed()
    assert fakes.solver_commands == [["/fake/bin/micromamba", "list", "--json", "-p", sys.prefix]]
    fakes.solver_commands.clear()
    model.refresh_all()
    assert len(fakes.solver_commands) == 3 and ops(fakes) == []


def test_a_failing_operation_says_why(model, fakes):
    fakes.solver_fails = True
    pick(model, "installed", name="numpy")
    model.ask_remove_selected()
    confirm(model, "remove")
    assert model.dialog == "notice" and model.dialog_title == "Error"
    assert model.dialog_text == "The operation failed:\nfake solver: the operation is refused"
    assert model.log[-1].endswith("Operation failed: fake solver: the operation is refused")
    model.dialog_ok()
    assert model.dialog == ""


def test_buttons_that_need_a_selection_are_greyed_without_one(model):
    for name in (
        "ask_update_selected",
        "ask_remove_selected",
        "ask_install_selected",
        "ask_clone_env",
        "ask_remove_env",
        "remove_channel",
        "search_packages",
    ):
        assert not model.enabled(name), name
    for name in (
        "refresh_installed",
        "ask_update_all",
        "ask_create_env",
        "request_export",
        "request_import",
        "ask_add_channel",
        "refresh_all",
    ):
        assert model.enabled(name), name


def test_every_destructive_action_asks_and_nothing_runs_on_no(model, fakes):
    pick(model, "installed", name="numpy")
    pick(model, "env", env="/fake/mambaforge")
    for ask, kind in (
        (model.ask_remove_selected, "remove"),
        (model.ask_remove_env, "remove_env"),
        (model.ask_update_all, "update_all"),
    ):
        ask()
        assert model.dialog == kind
        model.dialog_cancel()
    assert ops(fakes) == []


def test_settings_round_trip_and_spec_keys(model):
    model.restore_settings({"tab": 2, "installed_filter": "py"})
    assert model.export_settings() == {"tab": 2, "installed_filter": "py"} and [
        r["name"] for r in model.installed_rows
    ] == ["numpy", "scipy", "python"]
    spec = json.loads((GUI / "packages.view.json").read_text())

    def walk(sections):
        for s in sections:
            yield s
            yield from walk(s.get("sections", []))

    for s in walk(spec["sections"]):
        for key in ("attr", "source", "options_source"):
            if s.get(key):
                assert hasattr(model, s[key]), s[key]
        for key in ("call",):
            if s.get(key):
                assert callable(getattr(model, s[key]))
        opts = s.get("options", {})
        for key in ("source", "selected_call"):
            if opts.get(key):
                assert hasattr(model, opts[key]), opts[key]
        for b in s.get("buttons", []):
            assert callable(getattr(model, b["action"])), b["action"]
            assert b.get("description")
        for c in opts.get("columns", []):
            assert c.get("tooltip")
        if s.get("type") in ("value", "choice", "toggle", "custom", "panel"):
            assert s.get("description"), s


def test_the_app_draws_at_both_sizes_and_is_qt_free(fakes, monkeypatch):
    import subprocess

    from chisurf.plugins.core.updater.gui.package_app import PackageApp
    from test.gui.emtk_port_parity import qt_free

    from .fakes import REAL_POPEN, REAL_RUN

    for size in ((1200, 800), (800, 600)):
        app = PackageApp()
        for _ in range(3):
            painter = RecordingPainter()
            app.draw(painter, 0, 0, *size)
        assert "Installed Packages" in painter.strings and "Operation Log" in painter.strings
        app.close()
    monkeypatch.setattr(subprocess, "Popen", REAL_POPEN)
    monkeypatch.setattr(subprocess, "run", REAL_RUN)
    assert qt_free("updater", "chisurf.plugins.core.updater.gui.package_app:make_package_app")["ok"]
