"""Typed numeric fields explain their actual commit and clamping behavior."""

import pytest
from emtk import im
from emtk.app import ImApp
from emtk.events import CONTROL_MODIFIER
from emtk.keys import KEY_RETURN
from emtk.testing import Driver

from chisurf.emtk import typed_field


class FieldApp(ImApp):
    """Exercise the production field with actual pointer and text events."""

    def __init__(self, **options):
        self.options = options
        self.value = 3
        self.buffers = {}
        self.error = ""
        self.rect = None
        self.context = None
        super().__init__(self.render)
        self.io.wall_clock = False

    def render(self):
        """Keep the value until the field explicitly commits valid input."""
        self.context = im.get_current_context()
        im.begin("Typed number", self.context.box)
        committed, error = typed_field.typed_number_field(
            "count", self.value, self.buffers, **self.options
        )
        self.rect = im.get_item_rect()
        if committed is not None:
            self.value = committed
        if error:
            self.error = error
        im.button("Elsewhere")
        im.end()


def hover_help(app):
    """Wait for the normal delayed hover painter without changing the value."""
    driver = Driver(app, (520, 240))
    driver.frame(2)
    painter = driver.hover(app.rect)
    assert app.context.tooltip
    assert app.context.box_tooltip is None
    assert app.context.tooltip not in " ".join(painter.strings)
    app.io.now += 1.0
    painter = driver.frame(2)
    assert app.context.box_tooltip is not None
    assert app.context.tooltip in " ".join(painter.strings)
    assert app.value == 3 and app.buffers == {}
    return driver


@pytest.mark.parametrize("integer,kind", [(True, "whole number"), (False, "number")])
def test_intrinsic_help_explains_type_commit_and_bounds(integer, kind):
    """The fallback describes numeric semantics rather than repeating a field identifier."""
    app = FieldApp(integer=integer, minimum=0, maximum=10)
    driver = hover_help(app)
    assert f"Enter a {kind}." in app.context.tooltip
    assert "Press Enter or click elsewhere to commit." in app.context.tooltip
    assert "clamped between 0 and 10" in app.context.tooltip
    driver.hover((510, 230))
    assert app.context.tooltip is None


def test_caller_authored_help_uses_translation_and_overrides_fallback(monkeypatch):
    """Callers can provide precise domain meaning through the existing translation path."""
    original = "Detector gain in calibrated units."
    translated = "Gain du détecteur en unités étalonnées."
    monkeypatch.setattr(typed_field, "tr", lambda text: translated if text == original else text)
    app = FieldApp(description=original, minimum=0, maximum=10)
    hover_help(app)
    assert app.context.tooltip == translated


@pytest.mark.parametrize("integer,text,commit,expected", [
    (True, "12", "enter", 10),
    (False, "-2.5", "click", 0),
])
def test_hover_metadata_preserves_real_entry_and_clamp(integer, text, commit, expected):
    """Typing stays buffered until the established Enter or click-away commit."""
    app = FieldApp(integer=integer, minimum=0, maximum=10)
    driver = hover_help(app)
    driver.click(app.rect)
    driver.key(ord("A"), "a", CONTROL_MODIFIER)
    driver.type(text)
    assert app.value == 3
    if commit == "enter":
        driver.press(KEY_RETURN)
    else:
        driver.click("Elsewhere")
    assert app.value == expected and not app.error


def test_fractional_integer_remains_rejected_after_help_is_added():
    """An informative field still refuses an invalid integer without changing its value."""
    app = FieldApp(minimum=0, maximum=10)
    driver = hover_help(app)
    driver.click(app.rect)
    driver.key(ord("A"), "a", CONTROL_MODIFIER)
    driver.type("1.5")
    driver.press(KEY_RETURN)
    assert app.value == 3 and "whole number" in app.error


@pytest.mark.parametrize("options,expected", [
    ({"minimum": 2}, "Values below 2 are clamped to 2."),
    ({"maximum": 8}, "Values above 8 are clamped to 8."),
    ({}, "Enter a whole number. Press Enter or click elsewhere to commit."),
])
def test_intrinsic_help_describes_only_the_supplied_bounds(options, expected):
    """Unbounded and one-sided fields do not invent constraints."""
    app = FieldApp(**options)
    hover_help(app)
    assert expected in app.context.tooltip
    if not options:
        assert app.context.tooltip == expected


def test_intrinsic_help_translates_templates_before_formatting_bounds(monkeypatch):
    """Numeric bounds remain data inside a translated explanatory sentence."""
    translations = {
        "Enter a whole number. Press Enter or click elsewhere to commit.":
            "Saisissez un entier. Validez avec Entrée ou en cliquant ailleurs.",
        "Values are clamped between {minimum} and {maximum}.":
            "Les valeurs sont limitées entre {minimum} et {maximum}.",
    }
    monkeypatch.setattr(typed_field, "tr", lambda text: translations.get(text, text))
    app = FieldApp(minimum=0, maximum=10)
    hover_help(app)
    assert app.context.tooltip == (
        "Saisissez un entier. Validez avec Entrée ou en cliquant ailleurs. "
        "Les valeurs sont limitées entre 0 et 10."
    )
