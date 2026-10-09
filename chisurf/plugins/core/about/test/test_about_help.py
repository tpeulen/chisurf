"""About's declared actions preserve identity and await real user input."""

import json
import shutil

import pytest
from chisurf.plugins.core.about.gui.translations import LOCALES, tr
from emtk import clipboard, i18n
from emtk.keys import KEY_ESCAPE
from emtk.testing import Driver

from chisurf.core.dataspec.schema import validate_guide, validate_view_spec
from chisurf.core.info import __version__
from chisurf.plugins.core.about.gui import app as owner


@pytest.fixture
def copied(monkeypatch):
    """Intercept the system clipboard's host hook without touching user clipboard data."""
    values = []
    monkeypatch.setattr(clipboard, "_hook", values.append)
    monkeypatch.setattr(clipboard, "_last", clipboard.last_copied())
    return values


def click(app, driver, action):
    """Press the actual AutoForm action rectangle."""
    driver.click(app.form.rects[action])


def test_declared_actions_schema_and_authored_size(tmp_path, monkeypatch):
    """The primary declaration drives the real factory and every guide target exists."""
    assert not validate_view_spec(json.loads((owner.HERE / "about.view.json").read_text()))
    guide = json.loads((owner.HERE / "guide.json").read_text())
    assert not validate_guide(guide)
    assert [step["target"]["name"] for step in guide["steps"]] == ["open_help", "copy_details", "close_about"]
    directory = tmp_path / "gui"
    shutil.copytree(owner.HERE, directory)
    path = directory / "about.view.json"
    spec = json.loads(path.read_text())
    spec["window"] = {"width": 440, "height": 460}
    path.write_text(json.dumps(spec))
    monkeypatch.setattr(owner, "HERE", directory)
    app = owner.make_app()
    assert app.window_size == (440, 460)
    assert app.logo is not None


@pytest.mark.parametrize("locale", ("en", *LOCALES))
@pytest.mark.parametrize("size", [(380, 420), (320, 420)])
def test_actual_locales_keep_actions_tooltips_and_identity(size, locale):
    """Actual translated captions and painted help fit at both accepted dimensions."""
    previous = i18n.get_locale()
    i18n.set_locale(locale)
    try:
        app = owner.make_app()
        app.io.wall_clock = False
        driver = Driver(app, size)
        painter = driver.draw(2)
        assert app.logo is not None and app.window_size == (380, 420)
        assert app.window_title == tr("About ChiSurf")
        assert tr("Version: {version}").format(version=__version__) in painter.strings
        assert "thomas.peulen@tu-dortmund.de" in painter.strings
        assert set(app.form.rects) == {"open_help", "copy_details", "start_guide", "close_about"}
        assert len({rect[1] for rect in app.form.rects.values()}) == 1
        for button in app.spec["sections"][0]["buttons"]:
            assert tr(button["label"]) in painter.strings
            rect = app.form.rects[button["action"]]
            assert rect[0] >= 0 and rect[0] + rect[2] <= size[0]
            assert rect[1] + rect[3] <= size[1]
            driver.hover(rect)
            app.io.now += 1.0
            tooltip = driver.draw(2)
            assert tr(button["description"]) in " ".join(tooltip.strings)
    finally:
        i18n.set_locale(previous)


def test_copy_details_has_only_displayed_identity_and_reports_success(copied):
    """A real click uses the host-aware clipboard without collecting user data."""
    app = owner.make_app()
    driver = Driver(app, app.window_size)
    driver.draw(2)
    click(app, driver, "copy_details")
    assert copied == [app.details_text()]
    assert __version__ in copied[0]
    assert "Thomas-Otavio Peulen" in copied[0]
    assert "thomas.peulen@tu-dortmund.de" in copied[0]
    assert "github.com/fluorescence-tools/chisurf" in copied[0]
    assert len(copied[0].splitlines()) == 6
    assert tr("Application details copied.") in driver.draw(1).strings


def test_guide_awaits_help_copy_and_terminal_close(copied):
    """The last real Close acknowledges the tour before closing the About host."""
    app = owner.make_app()
    driver = Driver(app, (320, 420))
    driver.draw(2)
    click(app, driver, "start_guide")
    assert app.tour.active and app.tour.awaiting and not copied
    assert not app.help_window.open and not app.close_requested
    click(app, driver, "copy_details")
    assert not copied
    click(app, driver, "open_help")
    assert app.help_window.open and not app.tour.awaiting
    click(app, driver, "close_about")
    assert not app.close_requested
    driver.press(KEY_ESCAPE)
    assert app.tour.active and not app.help_window.open
    driver.click("Next ►")
    assert app.tour.step_idx == 1 and app.tour.awaiting
    click(app, driver, "copy_details")
    assert len(copied) == 1 and not app.tour.awaiting
    driver.click("Next ►")
    assert app.tour.step_idx == 2 and app.tour.awaiting
    click(app, driver, "close_about")
    assert app.close_requested and not app.tour.active and not app.help_window.open


def test_failed_clipboard_does_not_complete_copy_await(monkeypatch):
    """A rejected clipboard write leaves the action retryable and reports failure."""
    monkeypatch.setattr(clipboard, "copy", lambda text: False)
    app = owner.make_app()
    driver = Driver(app, app.window_size)
    driver.draw(2)
    app.io.wall_clock = False
    app.tour.start(1)
    driver.draw(2)
    click(app, driver, "copy_details")
    assert app.tour.awaiting and app.tour.step_idx == 1
    assert app.copy_status.startswith("Clipboard unavailable")
    assert app.tour.steps[1]["text"] == app.copy_status
    assert tr(app.copy_status) in " ".join(driver.draw(2).strings)
    assert not app.close_requested


def test_closed_about_cannot_reopen_or_copy(copied):
    """Late callbacks retain the closed host's clipboard and overlay boundary."""
    app = owner.make_app()
    driver = Driver(app, app.window_size)
    driver.draw(2)
    click(app, driver, "close_about")
    assert app.close_requested
    app.open_help()
    app.start_guide()
    app.copy_details()
    assert not copied and not app.help_window.open and not app.tour.active
    assert not app.copy_status
