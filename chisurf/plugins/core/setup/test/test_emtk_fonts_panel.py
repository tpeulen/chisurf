"""Settings ▸ Fonts, operated the way a person does: typed sizes, the magnification, Reset.

What is checked is what the window then does and what was written: emtk's font configuration
in force, the measured width of each preview line, the box the panel is laid out in under a
magnification, and the ``gui.fonts`` block in the (temporary) settings file. Hermetic: the
settings folder is a temporary one (``conftest.hermetic_settings``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from emtk import fonts, keys
from emtk.events import CONTROL_MODIFIER
from emtk.testing_realistic import RealisticDriver

from chisurf.plugins.core.setup.gui.fonts_app import VIEW_JSON, FontSettingsApp
from chisurf.plugins.core.setup.gui.fonts_model import FontSettingsModel


@pytest.fixture(autouse=True)
def _default_fonts():
    fonts.reset()
    yield
    fonts.reset()


def _sections(sections):
    for section in sections:
        yield section
        yield from _sections(section.get("sections") or [])


def _stored() -> dict:
    path = Path(__import__("os").environ["CHISURF_SETTINGS_DIR"]) / "settings_chisurf.yaml"
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {})["gui"]["fonts"]


def _driver(size=(900, 760)) -> tuple[FontSettingsApp, RealisticDriver]:
    app = FontSettingsApp()
    drv = RealisticDriver(app, size=size)  # the real device painter: it measures the fonts
    drv.frame(3)
    return app, drv


def _type_value(drv: RealisticDriver, name: str, text: str) -> None:
    drv.click(name)
    drv.key(keys.KEY_A, modifiers=CONTROL_MODIFIER)
    drv.release_key()
    drv.type(text)
    drv.press(keys.KEY_RETURN)
    drv.frame(2)


def test_every_control_is_described_and_bound():
    spec = json.loads(VIEW_JSON.read_text(encoding="utf-8"))
    model = FontSettingsModel(persist=False)
    for section in _sections(spec["sections"]):
        kind = section["type"]
        if kind in {"value", "choice", "toggle", "panel", "custom", "info"}:
            assert section.get("description"), section
        if section.get("attr"):
            assert isinstance(getattr(type(model), section["attr"]), property), section["attr"]
        if section.get("options_source"):
            assert callable(getattr(model, section["options_source"]))
            assert getattr(model, section["options_source"])()
        if kind == "custom":
            assert section["key"] == "font_preview"
            assert section["source"] in fonts.ROLES
        for button in section.get("buttons") or []:
            assert button.get("description") and callable(getattr(model, button["action"]))


def test_defaults_are_the_shipped_look():
    """The packaged ``gui.fonts`` block is emtk's defaults: today's look, nothing changed."""
    import chisurf.core.settings as package

    packaged = Path(package.__file__).with_name("settings_chisurf.yaml")
    block = yaml.safe_load(packaged.read_text(encoding="utf-8"))["gui"]["fonts"]
    assert fonts.FontConfig.from_dict(block) == fonts.config()
    assert fonts.config().ui.size == 8.0 and fonts.config().zoom == 1.0


def test_typing_the_interface_size_redraws_every_role_and_saves_it():
    app, drv = _driver()
    ui, prose = app.previews["ui"][1], app.previews["prose"][1]
    _type_value(drv, "ui_size", "10")
    assert fonts.config().ui.size == 10.0
    assert app.previews["ui"][1] == pytest.approx(ui * 10.0 / 8.0, rel=0.02)
    assert app.previews["prose"][1] == pytest.approx(prose * 10.0 / 8.0, rel=0.02)
    assert _stored()["ui"]["size"] == 10.0
    assert "saved" in app.model.status


def test_a_documentation_size_changes_only_the_documentation():
    app, drv = _driver()
    ui, prose = app.previews["ui"][1], app.previews["prose"][1]
    _type_value(drv, "prose_size", "12")
    assert fonts.config().prose.size == 12.0
    assert app.previews["ui"][1] == pytest.approx(ui)
    assert app.previews["prose"][1] == pytest.approx(prose * 12.0 / 8.0, rel=0.02)
    assert _stored()["prose"]["size"] == 12.0


def test_magnification_shrinks_the_layout_and_clicks_still_land():
    app, drv = _driver()
    _type_value(drv, "zoom", "1.25")
    assert fonts.config().zoom == 1.25
    assert drv.surface._box()[2:] == pytest.approx((720.0, 608.0))
    _type_value(drv, "prose_size", "11")  # a click on a control laid out under the zoom
    assert fonts.config().prose.size == 11.0
    drv.click("reset_defaults")
    drv.frame(2)
    assert fonts.config() == fonts.FontConfig.from_dict({"ui": {"size": 8.0}})
    assert _stored()["zoom"] == 1.0 and _stored()["prose"]["size"] == 0.0


def test_the_code_face_picker_lists_only_monospaced_families():
    model = FontSettingsModel(persist=False)
    mono = model.mono_families()
    assert mono[0] == "monospace" and "prose" not in mono
    assert set(mono) <= set(model.families())
    assert model.math_families()[0] == "auto"


def test_stored_settings_are_applied_at_startup(monkeypatch):
    import chisurf.core.settings as settings
    from chisurf.core.settings.fonts import apply_stored

    gui = dict(settings.cs_settings.get("gui") or {})
    gui["fonts"] = {"zoom": 1.5, "ui": {"size": 9.0}, "code": {"family": "No Such Mono 123"}}
    monkeypatch.setitem(settings.cs_settings, "gui", gui)
    applied = apply_stored()
    assert applied.zoom == 1.5 and applied.ui.size == 9.0
    # A face that is not installed never stops a window drawing: the role's default is drawn.
    from emtk.type_scale import text_font

    assert text_font("code")["family"] == "monospace"


def test_the_code_editor_follows_the_editor_face_unless_it_has_its_own():
    from emtk.type_scale import text_font

    from chisurf.plugins.core.code_editor.gui.editor_app import EditorModel

    model = EditorModel.__new__(EditorModel)
    model.font_family, model.font_size = "monospace", 0
    fonts.update(code={"size": 11.0})
    assert model.editor_font() == text_font("code")
    model.font_family, model.font_size = "Menlo", 12
    assert model.editor_font() == {"family": "Menlo", "size": 12}


def test_the_qt_console_takes_a_named_editor_face(monkeypatch):
    import chisurf.core.settings as settings
    from chisurf.core.console.settings import console_settings

    monkeypatch.setitem(settings.gui, "fonts", {"code": {"family": "Menlo, monospace"}})
    monkeypatch.setitem(settings.gui, "console", {})
    assert console_settings()["font_family"] == "Menlo"
    monkeypatch.setitem(settings.gui, "fonts", {"code": {"family": "monospace"}})
    assert console_settings()["font_family"] == ""


def test_every_guide_step_points_at_a_drawn_control():
    from chisurf.plugins.core.setup.gui.fonts_app import HERE

    app, _drv = _driver()
    drawn = set(app.form.rects) | set(app.item_rects)
    steps = json.loads((HERE / "fonts_guide.json").read_text(encoding="utf-8"))["steps"]
    assert steps
    for step in steps:
        assert step["target"]["name"] in drawn, step["title"]
        assert step["text"] and step["title"]
