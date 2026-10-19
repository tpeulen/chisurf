"""Shipped ``gui`` settings: deep merge, and no key the application no longer reads."""

from __future__ import annotations

#: ``gui`` keys only the removed Qt shell read. A user's settings file may still
#: carry them (it is merged over the defaults, never rewritten), but the shipped
#: YAML must not advertise them, nor ``docs/reference/settings.md`` document them.
RETIRED_GUI_KEYS = (
    "tooltip",
    "RubberBandMove",
    "RubberBandResize",
    "console_style",
    "console_width",
    "console_height",
    "fit_window_style",
    "fit_windows_size",
    "show_console",
)


def test_settings_deep_merge_exposes_new_keys():
    """A key added to the defaults surfaces under an older user file; user values win."""
    from chisurf.core.settings.settings_utils import _deep_merge

    defaults = {"gui": {"block": {"enabled": True, "width": 72}, "keep": 1}}
    user = {"gui": {"keep": 2}}
    merged = _deep_merge(defaults, user)
    assert merged["gui"]["block"]["width"] == 72
    assert merged["gui"]["keep"] == 2


def test_shipped_gui_settings_carry_no_retired_key():
    """The shipped ``settings_chisurf.yaml`` names no key nothing reads."""
    import pathlib

    import yaml

    import chisurf.core.settings as settings

    path = pathlib.Path(settings.__file__).with_name("settings_chisurf.yaml")
    gui = yaml.safe_load(path.read_text(encoding="utf-8"))["gui"]
    assert not set(RETIRED_GUI_KEYS) & set(gui)
    assert gui.get("application_font_size") == 13


def test_settings_reference_documents_no_retired_key():
    """``docs/reference/settings.md`` does not document a retired ``gui`` key."""
    import pathlib

    page = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reference" / "settings.md"
    if not page.is_file():
        return
    text = page.read_text(encoding="utf-8")
    for key in RETIRED_GUI_KEYS:
        assert f"`{key}`" not in text and f"`gui.{key}`" not in text, key
