"""A QA run must not write the user's real preferences.

Every widget that remembers something does it through ``QSettings(org, app)``,
and the main window saves its dock layout on ``closeEvent`` — which a test
fixture and a headless screenshot both trigger. Before
:func:`chisurf.gui.gui_tweaks.isolate_qsettings_for_qa` that landed in the
developer's own preferences: a suite run in a small offscreen window replaced
their dock layout with the collapsed two-column arrangement that window had, and
the next real start restored it.

These tests pin the redirection, not any one saver, because there are dozens of
savers and only one seam.
"""

import pathlib

import pytest
from qtpy import QtCore

from chisurf.gui import gui_tweaks


def _unpatched_user_preferences_root() -> pathlib.Path:
    """Where the *native* backend would put ``QSettings("ChiSurf", …)``.

    Asked of the patched class this returns the scratch directory — the
    redirection covers the native form too — so the question has to go to the
    Qt class the subclass replaced.
    """
    native = (
        QtCore.QSettings.__mro__[1]
        if hasattr(QtCore.QSettings, "_chisurf_qa_root")
        else QtCore.QSettings
    )
    return pathlib.Path(
        native(
            native.NativeFormat,
            native.UserScope,
            "ChiSurf",
            "MainWindow",
        ).fileName()
    ).parent


def test_pytest_alone_makes_this_a_qa_run():
    assert gui_tweaks.qa_run_reason() is not None


def test_the_escape_hatch_gives_the_real_preferences_back(monkeypatch):
    monkeypatch.setenv(gui_tweaks._ALLOW_REAL_QSETTINGS_VAR, "1")
    assert gui_tweaks.qa_run_reason() is None


@pytest.mark.parametrize("platform", ["offscreen", "minimal", "offscreen:size=1280x800"])
def test_a_headless_screenshot_is_a_qa_run_without_pytest(monkeypatch, platform):
    """The screenshot scripts the GUI rule asks for run outside pytest."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "pytest", None)
    monkeypatch.setenv("QT_QPA_PLATFORM", platform)
    assert gui_tweaks.qa_run_reason() == f"QT_QPA_PLATFORM={platform.split(':')[0]}"


def test_the_two_argument_constructor_writes_to_scratch_not_to_the_user():
    """``QSettings("ChiSurf", "MainWindow")`` is what every saver in the app builds.

    ``gui_tweaks`` redirected it at import, so this holds for the whole suite —
    which is the only reason closing a fixture window is safe.
    """
    written = pathlib.Path(QtCore.QSettings("ChiSurf", "MainWindow").fileName())
    assert written.parent != _unpatched_user_preferences_root()
    assert not written.is_relative_to(pathlib.Path.home() / "Library" / "Preferences")
    assert written.is_relative_to(QtCore.QSettings._chisurf_qa_root)


def test_the_redirection_survives_setdefaultformat_not_working():
    """``setDefaultFormat`` is documented to bind ``QSettings(org, app)`` — and does not.

    On the Qt build here, setting it to ``IniFormat`` leaves the two-argument
    constructor building ``NativeFormat`` objects that still write the plist.
    The instance is therefore what this asserts: the class swap is what makes
    the redirection real, and asserting ``defaultFormat()`` would pass while the
    user's preferences were being overwritten.
    """
    settings = QtCore.QSettings("ChiSurf", "MainWindow")
    assert settings.format() == QtCore.QSettings.IniFormat


def test_a_call_that_names_its_own_file_is_left_alone(tmp_path):
    """Those were already isolated; rewriting them would move a tool's settings."""
    ini = tmp_path / "tool.ini"
    settings = QtCore.QSettings(str(ini), QtCore.QSettings.IniFormat)
    assert pathlib.Path(settings.fileName()) == ini
