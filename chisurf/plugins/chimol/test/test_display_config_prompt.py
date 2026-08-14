"""Asking before changing someone's settings, and remembering the answer.

Migration can only correct a value it *names*. A default that moved twice inside
one released version left copies holding something nobody intended and nothing
could name -- the file's version stamp already matched, so every later
correction was skipped. The only symptom was that the viewer looked wrong, in a
way the person reporting it had no way to diagnose.

Comparing against the shipped file does not depend on the stamp being right, so
it catches that. But the file is the user's, so the answer is theirs: offer the
new values, list what differs, and take "don't ask again" for an answer.
"""
from __future__ import annotations

import json

import pytest

from chimol import config as cfg_mod


@pytest.fixture(autouse=True)
def _restore_display_config():
    """Put the process-wide display config back after every test.

    `_DISPLAY_CONFIG` is one dict for the whole process and reloading now
    mutates it in place, which is the point -- ten modules hold it by name. That
    also means a test which reloads from a scratch settings directory changes
    what *every other test file* renders with, and the symptom appears somewhere
    unrelated: this file quietly broke the putty tests until it was restored.
    """
    from chimol import config as _cfg

    snapshot = json.loads(json.dumps(_cfg._DISPLAY_CONFIG))
    try:
        yield
    finally:
        _cfg._merge_in_place(_cfg._DISPLAY_CONFIG, snapshot)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Point the config helpers at a scratch settings directory.

    Through ``CHIMOL_SETTINGS_DIR``, which is the documented override and the
    seam that actually exists. Patching ``cfg_mod._cs_settings`` used to work
    and stopped: :func:`~chimol.config.get_user_display_config_path` now
    delegates to :mod:`chimol.settings_dir`, which never consults it. The
    patch then had **no effect at all**, so every test in this file read the
    developer's own configuration -- which matches the shipped file, so nine
    tests failed on "nothing differs" and the file looked broken rather than
    mis-pointed.

    A stale test seam fails loudly here only because these tests assert on a
    *difference*. One asserting on agreement would have passed against the real
    configuration and proved nothing.

    There is now exactly **one** seam to point. `_load_display_config` used to
    read ChiSurf's settings module directly, so this fixture had to patch that
    too or a reload reached past the override; it goes through
    :mod:`chimol.settings_dir` as well now, and that honours the environment
    variable above. One override covers every path into the config, which is
    the whole reason chimol resolves its own settings directory rather than
    asking ChiSurf.
    """
    monkeypatch.setenv("CHIMOL_SETTINGS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def shipped() -> dict:
    """Return the config the package ships."""
    return json.loads(
        cfg_mod.get_package_display_config_path().read_text(encoding="utf-8")
    )


def _write(settings, cfg: dict):
    path = settings / "chimol_display.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# What differs
# --------------------------------------------------------------------------- #
def test_a_copy_of_the_shipped_file_differs_in_nothing(settings, shipped):
    _write(settings, shipped)
    assert cfg_mod.diff_against_package() == {}


def test_a_changed_value_is_reported_with_both_sides(settings, shipped):
    """Both values, because the choice is only meaningful with the comparison."""
    stale = json.loads(json.dumps(shipped))
    stale["metaball"]["sigma_factor"] = 3.0
    _write(settings, stale)

    differences = cfg_mod.diff_against_package()
    assert set(differences) == {"metaball.sigma_factor"}
    yours, theirs = differences["metaball.sigma_factor"]
    assert yours == 3.0
    assert theirs == shipped["metaball"]["sigma_factor"]


def test_a_stranded_value_is_found_whatever_the_stamp_says(settings, shipped):
    """The case the version check cannot see, and the reason this exists.

    A file stamped with the *current* version is "up to date" as far as
    migration is concerned, so nothing looks at its contents ever again. If a
    default moved after that stamp was written, the difference is invisible --
    which is exactly how a value nobody intended survived two attempts to fix
    it.
    """
    stranded = json.loads(json.dumps(shipped))
    stranded["_version"] = cfg_mod.DISPLAY_CONFIG_VERSION
    stranded["metaball"]["sigma_factor"] = 3.0
    _write(settings, stranded)

    assert cfg_mod.check_for_display_config_update() is False, "the stamp looks current"
    assert "metaball.sigma_factor" in cfg_mod.diff_against_package()


def test_meta_keys_are_not_compared(settings, shipped):
    """`_version` and the prompt preference describe the file, not the picture."""
    mine = json.loads(json.dumps(shipped))
    mine["_version"] = 1
    mine[cfg_mod.UPDATE_PROMPT_KEY] = False
    _write(settings, mine)

    assert cfg_mod.diff_against_package() == {}


def test_no_user_copy_means_nothing_to_ask_about(settings):
    assert cfg_mod.diff_against_package() == {}


# --------------------------------------------------------------------------- #
# The preference
# --------------------------------------------------------------------------- #
def test_asking_is_the_default(settings, shipped):
    """Opting out has to be a decision, not the state a file happens to be in."""
    _write(settings, shipped)
    assert cfg_mod.get_update_prompt_enabled() is True


def test_opting_out_survives_a_restart(settings, shipped):
    _write(settings, shipped)
    assert cfg_mod.set_update_prompt_enabled(False) is True
    assert cfg_mod.get_update_prompt_enabled() is False

    written = json.loads((settings / "chimol_display.json").read_text())
    assert written[cfg_mod.UPDATE_PROMPT_KEY] is False


def test_opting_back_in_works(settings, shipped):
    _write(settings, shipped)
    cfg_mod.set_update_prompt_enabled(False)
    cfg_mod.set_update_prompt_enabled(True)
    assert cfg_mod.get_update_prompt_enabled() is True


def test_the_preference_does_not_reach_the_rendered_config(settings, shipped, monkeypatch):
    """It configures the *asking*; nothing should look for it while drawing."""
    mine = json.loads(json.dumps(shipped))
    mine[cfg_mod.UPDATE_PROMPT_KEY] = False
    _write(settings, mine)
    monkeypatch.delenv("CHIMOL_DISPLAY_CONFIG", raising=False)

    loaded = cfg_mod._load_display_config()
    assert cfg_mod.UPDATE_PROMPT_KEY not in loaded


# --------------------------------------------------------------------------- #
# Taking the new values
# --------------------------------------------------------------------------- #
def test_adopting_writes_only_what_was_named(settings, shipped):
    """Everything else is left alone, including other differences."""
    mine = json.loads(json.dumps(shipped))
    mine["metaball"]["sigma_factor"] = 3.0
    mine["metaball"]["alpha"] = 0.11
    _write(settings, mine)

    adopted = cfg_mod.adopt_package_values(["metaball.sigma_factor"])
    assert adopted == ["metaball.sigma_factor"]

    written = json.loads((settings / "chimol_display.json").read_text())
    assert written["metaball"]["sigma_factor"] == shipped["metaball"]["sigma_factor"]
    assert written["metaball"]["alpha"] == 0.11, "an unnamed difference was overwritten"


def test_adopting_everything_leaves_no_difference(settings, shipped):
    mine = json.loads(json.dumps(shipped))
    mine["metaball"]["sigma_factor"] = 3.0
    mine["metaball"]["iso_value"] = 0.14
    _write(settings, mine)

    cfg_mod.adopt_package_values(cfg_mod.diff_against_package())
    assert cfg_mod.diff_against_package() == {}


def test_adopting_stamps_the_file_with_the_current_version(settings, shipped):
    """Otherwise the next start re-migrates values that are already current."""
    mine = json.loads(json.dumps(shipped))
    mine["_version"] = 2
    mine["metaball"]["sigma_factor"] = 3.0
    _write(settings, mine)

    cfg_mod.adopt_package_values(["metaball.sigma_factor"])
    written = json.loads((settings / "chimol_display.json").read_text())
    assert written["_version"] == cfg_mod.DISPLAY_CONFIG_VERSION


def test_an_unknown_name_is_ignored_rather_than_invented(settings, shipped):
    _write(settings, shipped)
    assert cfg_mod.adopt_package_values(["metaball.not_a_setting", "nosuch.key"]) == []


# --------------------------------------------------------------------------- #
# The prompt itself
# --------------------------------------------------------------------------- #
@pytest.fixture
def window(settings, shipped, _qt_app, monkeypatch):
    """Return a window whose settings differ from the package in one value."""
    mine = json.loads(json.dumps(shipped))
    mine["metaball"]["sigma_factor"] = 3.0
    _write(settings, mine)

    from chimol.app.molview_main_window import MolViewPluginWindow

    win = MolViewPluginWindow()
    monkeypatch.setattr(win, "status_bar", win.statusBar())
    return win


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_choosing_the_new_values_adopts_them(window, shipped):
    from chisurf.gui import dialogs

    with dialogs.auto_answer(choice=dialogs.Answer("update", False)):
        window._offer_package_display_defaults()

    assert cfg_mod.diff_against_package() == {}


def test_keeping_yours_changes_nothing(window):
    from chisurf.gui import dialogs

    with dialogs.auto_answer(choice=dialogs.Answer("keep", False)):
        window._offer_package_display_defaults()

    assert "metaball.sigma_factor" in cfg_mod.diff_against_package()
    assert cfg_mod.get_update_prompt_enabled() is True


def test_the_tick_box_stops_the_asking_whichever_button_was_pressed(window):
    """"Don't ask again" is about the asking, not about the answer.

    Someone who keeps their settings *and* ticks the box has said two separate
    things, and both have to be honoured -- otherwise the only way to stop being
    asked is to accept values you did not want.
    """
    from chisurf.gui import dialogs

    with dialogs.auto_answer(choice=dialogs.Answer("keep", True)):
        window._offer_package_display_defaults()

    assert cfg_mod.get_update_prompt_enabled() is False
    assert "metaball.sigma_factor" in cfg_mod.diff_against_package()


def test_nothing_is_asked_once_opted_out(window, monkeypatch):
    """The whole point of remembering the answer."""
    from chisurf.gui import dialogs

    cfg_mod.set_update_prompt_enabled(False)

    asked = []
    monkeypatch.setattr(dialogs, "choice", lambda *a, **k: asked.append(a) or dialogs.Answer(None, False))
    window._offer_package_display_defaults()
    assert asked == []


def test_nothing_is_asked_when_the_settings_already_agree(settings, shipped, _qt_app, monkeypatch):
    from chisurf.gui import dialogs
    from chimol.app.molview_main_window import MolViewPluginWindow

    _write(settings, shipped)
    win = MolViewPluginWindow()

    asked = []
    monkeypatch.setattr(dialogs, "choice", lambda *a, **k: asked.append(a) or dialogs.Answer(None, False))
    win._offer_package_display_defaults()
    assert asked == []


# --------------------------------------------------------------------------- #
# Turning it back on, in the settings panel
# --------------------------------------------------------------------------- #
# The preference used to be a tick box in a modal JSON dialog. That dialog is
# gone -- no Qt chrome outside the embedding window -- so the row lives in the
# settings editor drawn inside the 3-D view, beside everything else. What has
# to keep working is only this: the preference can be read, and it can be put
# back after being turned off.
def test_the_panel_shows_the_current_preference(settings, shipped):
    from chimol.renderer import settings_window

    mine = json.loads(json.dumps(shipped))
    mine[cfg_mod.UPDATE_PROMPT_KEY] = False
    _write(settings, mine)

    model = settings_window.build_model()
    assert model.get(settings_window.PROMPT_KEY) is False


def test_an_absent_preference_reads_as_asking(settings, shipped):
    from chimol.renderer import settings_window

    _write(settings, shipped)
    assert settings_window.build_model().get(settings_window.PROMPT_KEY) is True


def test_the_panel_can_turn_it_back_on(settings, shipped):
    """A preference with no way back on is a preference that only turns off."""
    from chimol.renderer import settings_window

    mine = json.loads(json.dumps(shipped))
    mine[cfg_mod.UPDATE_PROMPT_KEY] = False
    path = _write(settings, mine)

    model = settings_window.build_model()
    row = next(one for one in model.settings
               if one.key == settings_window.PROMPT_KEY)
    model.adjust(row, 0)

    assert model.get(settings_window.PROMPT_KEY) is True
    assert json.loads(path.read_text())[cfg_mod.UPDATE_PROMPT_KEY] is True


# --------------------------------------------------------------------------- #
# Reloading has to reach the modules that draw
# --------------------------------------------------------------------------- #
def test_a_reload_reaches_a_module_that_imported_the_config_by_name(settings, shipped):
    """Ten modules hold this dict by name, including both renderers.

    `from ..config import _DISPLAY_CONFIG` binds the *object*, so rebinding the
    module global -- which is what reloading used to do -- left every one of
    them on the dict from before the reload. The config was reloaded and the
    renderer kept drawing from the old one, which is what made saving in the
    Config editor look like it did nothing.
    """
    from chimol.renderer.view import _DISPLAY_CONFIG as held_by_renderer

    mine = json.loads(json.dumps(shipped))
    mine["metaball"]["shininess"] = 12.0
    _write(settings, mine)

    cfg_mod.reload_display_config()
    try:
        assert held_by_renderer["metaball"]["shininess"] == 12.0
        assert held_by_renderer is cfg_mod._DISPLAY_CONFIG
    finally:
        _write(settings, shipped)
        cfg_mod.reload_display_config()


def test_a_section_object_survives_a_reload(settings, shipped):
    """Anything holding one section must see the new values too."""
    _write(settings, shipped)
    cfg_mod.reload_display_config()
    section = cfg_mod._DISPLAY_CONFIG["metaball"]

    mine = json.loads(json.dumps(shipped))
    mine["metaball"]["shininess"] = 7.0
    _write(settings, mine)
    cfg_mod.reload_display_config()
    try:
        assert section["shininess"] == 7.0
    finally:
        _write(settings, shipped)
        cfg_mod.reload_display_config()
