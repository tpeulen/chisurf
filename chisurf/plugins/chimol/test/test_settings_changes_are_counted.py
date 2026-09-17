"""A change to the display configuration is counted, however it is written.

The scene cache keeps each object's geometry against a fingerprint of what it
was built from, and a *setting* is a global input to every builder -- stick
radius, cartoon quality, ambient occlusion -- so a setting changing is the one
thing that has to invalidate every object at once. That is what
``settings_revision()`` is for.

Only ``set_setting`` bumped it. A great deal of code reaches into the
configuration and writes it directly::

    cfg = _DISPLAY_CONFIG.setdefault("occlusion", {})
    cfg["enabled"] = False

and those writes bumped nothing, so the viewer kept the geometry it had already
built and the setting appeared to be ignored -- occlusion could be switched off
and the shading stayed. Counting now happens in the configuration itself, which
is where the data is; the same fix as the object state one layer down.
"""

from __future__ import annotations

import pytest
from chimol.core.settings.config import _DISPLAY_CONFIG
from chimol.core.settings.registry import set_setting, settings_revision


@pytest.fixture
def occlusion():
    section = _DISPLAY_CONFIG.setdefault("occlusion", {})
    previous = dict(section)
    yield section
    section.clear()
    section.update(previous)


def test_a_write_through_the_settings_command_counts():
    before = settings_revision()
    set_setting("stick_radius", 0.27)
    assert settings_revision() > before


def test_a_write_straight_into_a_section_counts(occlusion):
    """The form every panel, plugin and test actually uses."""
    before = settings_revision()
    occlusion["enabled"] = not occlusion.get("enabled", True)
    assert settings_revision() > before


def test_a_section_created_on_the_fly_is_watched_too():
    before = settings_revision()
    section = _DISPLAY_CONFIG.setdefault("_a_section_that_did_not_exist", {})
    section["value"] = 1
    try:
        assert settings_revision() > before
        deeper = section.setdefault("nested", {})
        mark = settings_revision()
        deeper["value"] = 2
        assert settings_revision() > mark, "a write two levels down is not counted"
    finally:
        _DISPLAY_CONFIG.pop("_a_section_that_did_not_exist", None)


def test_setting_a_new_path_still_lands_in_the_configuration():
    """The configuration wraps what goes into it, so a writer that keeps the
    dict it just inserted would write into an orphan.
    """
    from chimol.core.settings.config import _DISPLAY_CONFIG as cfg
    from chimol.core.settings.config import _plant

    try:
        assert _plant(cfg, ("_planted", "deep", "leaf"), 7)
        assert cfg["_planted"]["deep"]["leaf"] == 7
    finally:
        cfg.pop("_planted", None)


def test_removing_a_setting_counts(occlusion):
    occlusion["_scratch"] = 1
    before = settings_revision()
    del occlusion["_scratch"]
    assert settings_revision() > before
