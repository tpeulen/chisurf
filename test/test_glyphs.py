"""Tests for the canonical glyph registry (:mod:`chisurf.gui.glyphs`).

The registry is a Qt-free source of truth for the pictographic "emoticon"
icons used across ChiSurf widgets, so it can be tested headlessly without a
display or the Qt stack.
"""

import importlib.util
import pathlib

import pytest

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "chisurf" / "gui" / "glyphs.py"


def _load_glyphs():
    """Import ``chisurf.gui.glyphs`` directly, bypassing the Qt-heavy package."""
    spec = importlib.util.spec_from_file_location("_chisurf_glyphs", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


glyphs = _load_glyphs()
Glyphs = glyphs.Glyphs
normalize = glyphs.normalize


@pytest.mark.parametrize(
    "src, expected",
    [
        ("🔎 Details", "🔍 Details"),  # zoom synonym -> search
        ("✎ Edit", Glyphs.EDIT + " Edit"),  # light pencil -> edit
        ("✖ Unload", Glyphs.CLOSE + " Unload"),  # heavy multiply -> close
        ("🗑 Delete", Glyphs.DELETE + " Delete"),  # missing VS16 completed
        ("⚙ Settings", Glyphs.SETTINGS + " Settings"),
    ],
)
def test_normalize_rewrites_variants(src, expected):
    assert normalize(src) == expected


@pytest.mark.parametrize(
    "text",
    ["A → B nav", "▶ Run tree", "", "no glyphs here", Glyphs.DELETE + " Delete"],
)
def test_normalize_leaves_canonical_and_prose_untouched(text):
    assert normalize(text) == text


def test_normalize_is_idempotent():
    for src in ["🗑 x", "⚙ y", "🔎 z", "✎ w", "🗑️ already", "⚙️ ok"]:
        once = normalize(src)
        assert normalize(once) == once


def test_vs16_completion_does_not_duplicate_selector():
    # A glyph that already carries the selector must not gain a second one.
    assert normalize(Glyphs.DELETE) == Glyphs.DELETE
    assert Glyphs.DELETE.count(glyphs.VS16) == 1


def test_delete_and_settings_are_colour_emoji():
    # Text-default symbols carry an explicit variation selector.
    assert Glyphs.SETTINGS.endswith(glyphs.VS16)
    assert Glyphs.DELETE.endswith(glyphs.VS16)
