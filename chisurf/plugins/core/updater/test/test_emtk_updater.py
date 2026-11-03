"""The emtk updater tab: statuses, version list, changelog, settings, update command lines, no Qt.

SAFETY: every system action is a fake (``fakes.py``): no update, install, removal or environment change, no network. The
expected values come from the fakes' own inputs: the listed releases (``RELEASES``), the commit list the fake GitHub
answers with (``COMMITS``) and the command lines written out in ``Fakes.expected_*``.
"""

from __future__ import annotations

import html
import json
import time
from pathlib import Path

import pytest
import yaml
from emtk.testing import RecordingPainter

from .fakes import COMMITS, RELEASES

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
COMMITS_URL = "https://github.com/Fluorescence-Tools/chisurf/commits"
LABELS = [f"Version {r['version']}" for r in RELEASES]


def changes():
    """The changelog lines of the fake commits: merges skipped, first message line, date and author."""
    return [
        f"{c['commit']['author']['date'][:10]} {c['commit']['message'].splitlines()[0]} "
        f"(by {c['commit']['author']['name']})"
        for c in COMMITS
        if not c["commit"]["message"].startswith("Merge")
    ]


def changelog_html(old: str, new: str) -> str:
    """The changelog HTML for the fake commits between *old* and *new*: bold header, escaped items, the link."""
    items = "".join(f"  <li>{html.escape(line, quote=False)}</li>\n" for line in changes())
    return (
        f"<b>Changes between {old} and {new}:</b>\n<ul>\n{items}</ul>\n"
        f'<p>More details: <a href="{COMMITS_URL}">{COMMITS_URL}</a></p>'
    )


def model_checked(**kwargs):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel(**kwargs)
    model.do_check()
    return model


# ---------------------------------------------------------------------------------------------- 1. status, versions, changelog
def test_a_check_lists_the_releases_and_the_changelog_of_the_newest(fakes):
    model = model_checked()
    assert model.status == f"Update available: version {RELEASES[0]['version']}"
    assert model.version_labels == LABELS
    assert model.version_index == 0
    assert model.changelog_html == changelog_html(RELEASES[1]["version"], RELEASES[0]["version"])
    assert (
        model.update_enabled and model.enabled("ask_update") and model.enabled("selected_version")
    )


def test_every_version_shows_the_changelog_since_the_version_before_it(fakes):
    """The changelog of a release runs from the next older listed release (the installed one for the oldest)."""
    model = model_checked()
    versions = [r["version"] for r in RELEASES] + [model.current_version]
    for index in range(len(model.version_labels)):
        model.selected_version = model.version_labels[index]
        model.update_changelog_for_selected()
        assert model.changelog_html == changelog_html(versions[index + 1], versions[index]), index


def test_the_changelog_range_follows_the_previous_listed_version_and_the_installed_one_for_the_oldest(
    fakes,
):
    """The GitHub query the changelog sends: since the previous listed version (the installed one for the oldest) to the day after."""
    model = model_checked()
    ranges = {}
    for index in range(3):
        fakes.http_requests.clear()
        model.version_index = index
        model.update_changelog_for_selected()
        (url,) = fakes.http_requests
        ranges[index] = (
            url.split("since=")[1].split("&")[0][:10],
            url.split("until=")[1].split("&")[0][:10],
            url.split("sha=")[1],
        )
    assert ranges[0] == ("2026-09-20", "2026-10-03", "development")  # 26.09.20 -> 26.10.02
    assert ranges[1] == ("2026-08-01", "2026-09-21", "development")  # 26.08.01 -> 26.09.20
    assert ranges[2][1:] == (
        "2026-08-02",
        "development",
    )  # oldest: from the installed version (no date: 14 days back)
    assert ranges[2][0] == "2026-07-18"


def test_the_start_up_check_lists_the_releases_and_gives_a_notice(fakes):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel()
    model.auto_check()
    assert model.status == "Update available: version 26.10.02"
    assert model.version_labels == LABELS
    assert (model.dialog, model.dialog_title, model.dialog_text) == (
        "notice",
        "Update Available",
        "A new version of ChiSurf (26.10.02) is available.",
    )
    drawn = [f"{b[1]}: {b[2]}" if b[0] == "link" else b[1] for b in model.changelog_blocks]
    assert [d.strip() for d in drawn] == [
        f"Changes between {model.current_version} and 26.10.02:",
        *changes(),
        f"More details: {COMMITS_URL}",
    ]  # the start-up changelog runs from the installed version
    assert model.update_enabled and not model.suppress_initial_notification


def test_a_quiet_start_up_check_shows_no_notice(fakes):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel(suppress_initial_notification=True)
    model.auto_check()
    assert model.status == "Update available: version 26.10.02" and model.dialog == ""


def test_start_up_check_is_skipped_by_the_switches_only_when_opened_by_start_up(fakes):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel, save_startup_settings

    save_startup_settings(True, True)
    quiet = UpdaterModel(suppress_initial_notification=True)
    quiet.auto_check()
    assert quiet.status == "Startup update check is disabled by user settings."
    assert (
        fakes.remote_listings == 0 and fakes.http_requests == []
    )  # nothing was asked of the network
    save_startup_settings(False, False)
    assert UpdaterModel(suppress_initial_notification=True).check_on_startup is False
    off = UpdaterModel(suppress_initial_notification=True)
    off.auto_check()
    assert off.status == "Startup update check is disabled by user settings."
    opened_by_user = UpdaterModel(suppress_initial_notification=False)
    opened_by_user.auto_check()
    assert (
        opened_by_user.status == "Update available: version 26.10.02" and fakes.remote_listings > 0
    )


def test_no_versions_listed_says_the_installed_version_is_up_to_date(fakes):
    fakes.releases.clear()
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel()
    model.auto_check()
    assert model.status == f"ChiSurf is up to date (version {model.current_version})."
    assert (
        model.version_labels == [] and not model.update_enabled and not model.enabled("ask_update")
    )
    model.do_check()
    assert model.status == "Error checking for updates: No update information available"


def test_the_changelog_formatting_of_a_sample():
    """Header bold, ``- `` lines a list, other lines paragraphs, the details line a link, everything escaped."""
    from chisurf.plugins.core.updater.gui.model import format_changelog_html

    sample = (
        "Changes between 26.09.20 and 26.10.02:\n- 2026-10-01 Add <the> updater (by Ada)\n"
        f"plain line & more\n\nMore details: {COMMITS_URL}"
    )
    assert format_changelog_html(sample) == (
        "<b>Changes between 26.09.20 and 26.10.02:</b>\n<ul>\n"
        "  <li>2026-10-01 Add &lt;the&gt; updater (by Ada)</li>\n</ul>\n"
        "<p>plain line &amp; more</p>\n"
        f'<p>More details: <a href="{COMMITS_URL}">{COMMITS_URL}</a></p>'
    )
    assert format_changelog_html("  ") == "<i>No changelog available.</i>"
    assert format_changelog_html(None) == "<i>No changelog available.</i>"


def test_the_blocks_the_window_draws_show_the_text_as_written():
    """Characters a Markdown renderer would eat (``<b>``, ``_``, ``*``) are shown as written, in the changelog's order."""
    from chisurf.plugins.core.updater.gui.model import changelog_blocks

    text = (
        "Changes between 1 and 2:\n- 2026-10-01 fix snake_case_name and *star* <b>x</b> (by Ada)\n- second\nplain & line\n"
        "More details: https://github.com/o/my_repo_x/commits"
    )
    blocks = changelog_blocks(text)
    assert [b[0] for b in blocks] == ["header", "item", "item", "paragraph", "link"]
    # the lines of the text, list markers dropped
    lines = [
        "Changes between 1 and 2:",
        "2026-10-01 fix snake_case_name and *star* <b>x</b> (by Ada)",
        "second",
        "plain & line",
        "More details: https://github.com/o/my_repo_x/commits",
    ]
    drawn = [blocks[0][1]] + [b[1] for b in blocks[1:4]] + [f"{blocks[4][1]}: {blocks[4][2]}"]
    assert [ln.strip() for ln in lines] == [d.strip() for d in drawn]
    assert blocks[4] == ("link", "More details", "https://github.com/o/my_repo_x/commits")
    assert changelog_blocks("") == [("empty", "No changelog available.", None)]


# ---------------------------------------------------------------------------------------------- 2. startup settings
def test_the_startup_switches_are_saved_under_plugins_updater(tmp_path):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    settings_file = tmp_path / "settings" / "settings_chisurf.yaml"
    model = UpdaterModel()
    model.check_on_startup = False
    model.ignore_updates_on_startup = True
    assert yaml.safe_load(settings_file.read_text()) == {
        "plugins": {"updater": {"ignore_updates_on_startup": True, "check_on_startup": False}}
    }
    again = UpdaterModel()  # read back at the next start
    assert (again.check_on_startup, again.ignore_updates_on_startup) == (False, True)


def test_the_startup_switch_defaults_are_check_on_and_ignore_off():
    from chisurf.plugins.core.updater.gui.model import UpdaterModel, load_startup_settings

    model = UpdaterModel()
    assert (model.check_on_startup, model.ignore_updates_on_startup) == (True, False)
    assert load_startup_settings({}) == (False, True)
    assert load_startup_settings({"plugins": {"updater": {"check_on_startup": False}}}) == (
        False,
        False,
    )


def test_settings_round_trip_through_the_host_hooks():
    from chisurf.plugins.core.updater.gui.app import make_app

    app = make_app()
    app.auto_check = False
    app.restore_settings({"check_on_startup": False, "ignore_updates": True})
    assert app.export_settings() == {"check_on_startup": False, "ignore_updates": True}
    app.close()


# ---------------------------------------------------------------------------------------------- 3. the update command line
def run_update(model, fakes, accept=True):
    model.ask_update()
    assert model.dialog == "confirm_update"
    (model.dialog_ok if accept else model.dialog_cancel)()


def test_update_now_downloads_a_remote_package_and_installs_it(fakes):
    model = model_checked()
    run_update(model, fakes)
    ((url, local),) = fakes.downloads
    assert url == RELEASES[0]["file_path"]
    assert Path(local).name == "chisurf-macos-26.10.02.tar.bz2" and Path(
        local
    ).parent.name.startswith("chisurf_update_")
    assert fakes.update_commands == [("separate_process", fakes.expected_update_commands(local))]
    assert (
        model.status
        == "The update was started in a separate window; restart ChiSurf when it has finished."
    )
    assert not model.updating and model.update_message == ""


def test_update_now_for_a_conda_package_uses_the_same_install_line(fakes):
    model = model_checked()
    model.selected_version = "Version 26.08.01"
    run_update(model, fakes)
    ((url, local),) = fakes.downloads
    assert url == RELEASES[2]["file_path"] and local.endswith("chisurf-macos-26.08.01.conda")
    assert fakes.update_commands == [("separate_process", fakes.expected_update_commands(local))]


def test_update_now_without_a_listed_version_runs_the_standard_install_line(fakes):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel()
    model.update_enabled = True  # as after a check that listed nothing but found a newer one
    run_update(model, fakes)
    assert fakes.update_commands == [("separate_process", fakes.expected_latest_command())]
    assert fakes.downloads == []


@pytest.mark.parametrize("development, branch", [(True, "development"), (False, "master")])
def test_the_channel_chooses_the_changelog_branch_not_the_install_line(fakes, development, branch):
    """Stable (the box unchecked) and development differ only in the branch the changelog is read from."""
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel()
    model.development = development
    assert model.updater.channel == branch and model.branch_text == f"branch: {branch}"
    model.do_check()
    assert fakes.http_requests and all(f"sha={branch}" in url for url in fakes.http_requests[:2])
    run_update(model, fakes)
    ((_, local),) = fakes.downloads
    assert fakes.update_commands == [("separate_process", fakes.expected_update_commands(local))]


def test_declining_the_question_runs_nothing_and_says_so(fakes):
    model = model_checked()
    model.ask_update()
    assert (model.dialog_title, model.dialog_text) == (
        "Update Warning",
        "The update process will close all ChiSurf windows and continue in a separate window.\n\n"
        "All unsaved work will be lost. After the update completes, you will need to restart ChiSurf manually.\n\n"
        "Do you want to continue?",
    )
    model.dialog_cancel()
    assert model.status == "Update cancelled by user."
    assert fakes.update_commands == [] and fakes.downloads == []


def test_a_failed_download_is_reported_and_runs_nothing(fakes, monkeypatch):
    import urllib.request

    def refuse(url, filename=None, reporthook=None, *a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlretrieve", refuse)
    model = model_checked()
    run_update(model, fakes)
    assert model.status == "Update failed: Failed to download update file: connection refused"
    assert fakes.update_commands == []


def test_an_update_script_that_ends_the_process_asks_the_app_to_exit(fakes, monkeypatch):
    """The real runner calls ``sys.exit`` after starting the script: the model catches it, the app ends ChiSurf."""
    from chisurf.plugins.core.updater import updater as up
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    def runner(updater, cmd, callback=None):
        fakes.update_commands.append(("separate_process", list(cmd)))
        raise SystemExit(0)

    monkeypatch.setattr(up.ChiSurfUpdater, "_run_update_in_separate_process", runner)
    exits = []
    app = UpdaterApp(UpdaterModel(), auto_check=False, exit_hook=lambda: exits.append(1))
    model = app.model
    model.do_check()
    run_update(model, fakes)  # the app runs it in the background: draw until it has finished
    for _ in range(400):
        app.draw(RecordingPainter(), 0, 0, 800, 600)
        if exits:
            break
        time.sleep(0.01)
    assert model.exit_requested and "continues in a separate window" in model.status
    assert exits == [1] and app.close_requested
    app.draw(RecordingPainter(), 0, 0, 800, 600)
    assert exits == [1]  # once
    app.close()


def test_the_package_manager_button_is_available(fakes):
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel()
    assert model.package_manager_available and model.enabled("open_package_manager")


# ---------------------------------------------------------------------------------------------- 4. spec and model agree
def spec():
    return json.loads((GUI / "updater.view.json").read_text(encoding="utf-8"))


def walk(sections):
    for section in sections:
        yield section
        yield from walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    model = UpdaterModel()
    for s in walk(spec()["sections"]):
        for key in ("attr", "source", "options_source", "text_source"):
            if s.get(key):
                assert hasattr(model, s[key]), (key, s[key])
        if s.get("call"):
            assert callable(getattr(model, s["call"])), s["call"]
        for button in s.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
            for key in ("label_source",):
                if button.get(key):
                    assert callable(getattr(model, button[key])) or hasattr(model, button[key])
        hidden = s.get("hidden_when", {}).get("attr")
        if hidden:
            assert hasattr(model, hidden)


def test_the_model_imports_no_qt(monkeypatch):
    """A child Python imports and draws the app three times with Qt imports forbidden (it reaches for no network: the
    start-up check waits for a moment of real running, and the child draws for a few milliseconds)."""
    import subprocess

    from test.gui.emtk_port_parity import qt_free

    from .fakes import REAL_POPEN, REAL_RUN

    monkeypatch.setattr(subprocess, "Popen", REAL_POPEN)
    monkeypatch.setattr(subprocess, "run", REAL_RUN)

    result = qt_free("updater", "chisurf.plugins.core.updater.gui.app:make_app")
    assert result["ok"], result["output"]


# ---------------------------------------------------------------------------------------------- 5. tooltips, drawing
def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("updater", "chisurf.plugins.core.updater.gui.app:make_app")
    inventory = emtk_inventory(app)
    app.close()
    assert inventory["controls_without_tooltip"] == []

    def check(sections):
        for s in sections:
            if s.get("type") in (
                "value",
                "choice",
                "toggle",
                "table",
                "data_table",
                "custom",
                "info",
                "panel",
            ):
                assert s.get("description"), s.get("attr") or s.get("title") or s
            for b in s.get("buttons", []):
                assert b.get("description"), b
            check(s.get("sections", []))

    check(spec()["sections"])


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_the_app_draws_empty_and_after_a_check_at_both_sizes(size):
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    app = UpdaterApp(UpdaterModel(), auto_check=False)
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert (
        "Check for Updates" in painter.strings
        and "Changelog will appear here after checking for updates..." in painter.strings
    )
    app.model.do_check()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert (
        "Version 26.10.02" in painter.strings
        and "Update available: version 26.10.02" in painter.strings
    )
    app.close()
