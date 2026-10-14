"""App-wide tooltip settings and settings deep-merge."""

from __future__ import annotations


def test_settings_deep_merge_exposes_new_keys():
    from chisurf.core.settings.settings_utils import _deep_merge

    defaults = {"gui": {"tooltip": {"enabled": True, "wrap_width": 72}, "keep": 1}}
    user = {"gui": {"keep": 2}}  # older user file without the new tooltip block
    merged = _deep_merge(defaults, user)
    assert merged["gui"]["tooltip"]["wrap_width"] == 72  # new default surfaces
    assert merged["gui"]["keep"] == 2  # user override still wins


def test_tooltip_settings_present():
    from chisurf.core.settings import cs_settings

    gui = cs_settings.get("gui", {})
    assert gui.get("tooltip", {}).get("wrap_width") == 72
    assert gui.get("application_font_size") == 13
