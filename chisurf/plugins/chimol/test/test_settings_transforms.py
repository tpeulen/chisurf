"""Settings whose PyMOL name is not what chimol stores.

``transparency`` is the case that forced this. PyMOL counts transparency, where
0 is fully opaque; the renderer reads an *alpha*, where 1 is. Storing both is
two numbers that must agree and eventually will not, so the settings table
carries the conversion and the config keeps one value.

What that has to get right is the round trip in **both** directions: a `set`
must echo what the user typed rather than what was stored, a `get` must answer
in the user's units, and `unset` must restore the default the program actually
ships -- which here is chimol's translucent surface, not PyMOL's opaque one.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol.config import _DISPLAY_CONFIG
from chisurf.plugins.chimol.chimol.settings import (
    get_setting,
    resolve,
    set_setting,
    setting_names,
    unset_setting,
)


@pytest.fixture
def restore_surface():
    """`_DISPLAY_CONFIG` is one process-wide dict, so put it back in place.

    Restored *in place* rather than replaced: a dict swapped here changes what
    every other test file sees.
    """
    section = _DISPLAY_CONFIG.setdefault("surface", {})
    keys = ("alpha", "two_sided", "grid_spacing", "probe_radius",
            "best", "normal", "poor", "miserable")
    before = {k: section.get(k) for k in keys}
    yield section
    for key, value in before.items():
        if value is None:
            section.pop(key, None)
        else:
            section[key] = value


# --------------------------------------------------------------------------- #
# transparency: the complement
# --------------------------------------------------------------------------- #
def test_transparency_stores_the_complementary_alpha(restore_surface):
    set_setting("transparency", 0.4)
    assert restore_surface["alpha"] == pytest.approx(0.6)


def test_transparency_reads_back_in_the_users_units(restore_surface):
    set_setting("transparency", 0.4)
    assert get_setting("transparency") == pytest.approx(0.4)


def test_set_reports_what_was_asked_for_not_what_was_stored(restore_surface):
    """`set transparency, 0.4` must echo 0.4, not the 0.6 alpha it became."""
    _spec, coerced = set_setting("transparency", 0.4)
    assert coerced == pytest.approx(0.4)


def test_zero_transparency_is_fully_opaque(restore_surface):
    """PyMOL's sense, and the one a preset relies on."""
    set_setting("transparency", 0.0)
    assert restore_surface["alpha"] == pytest.approx(1.0)


def test_one_transparency_is_invisible(restore_surface):
    set_setting("transparency", 1.0)
    assert restore_surface["alpha"] == pytest.approx(0.0)


def test_the_round_trip_is_stable_over_the_whole_range(restore_surface):
    for value in (0.0, 0.15, 0.25, 0.5, 0.75, 1.0):
        set_setting("transparency", value)
        assert get_setting("transparency") == pytest.approx(value), value


def test_unset_restores_the_default_this_program_ships(restore_surface):
    """Not PyMOL's opaque default: `unset` restores *the* default.

    chimol ships a slightly translucent surface (alpha 0.85). Changing that is a
    config-version migration, not something a settings entry may do quietly.
    """
    set_setting("transparency", 0.9)
    unset_setting("transparency")
    assert restore_surface["alpha"] == pytest.approx(0.85)
    assert get_setting("transparency") == pytest.approx(0.15)


def test_the_raw_config_path_is_not_transformed(restore_surface):
    """A dotted path reaches the stored value directly, complement and all.

    That is the point of having both spellings: `transparency` speaks PyMOL and
    `surface.alpha` speaks to the renderer.
    """
    set_setting("surface.alpha", 0.3)
    assert restore_surface["alpha"] == pytest.approx(0.3)
    assert get_setting("transparency") == pytest.approx(0.7)


# --------------------------------------------------------------------------- #
# two_sided_lighting
# --------------------------------------------------------------------------- #
def test_two_sided_lighting_is_registered_and_boolean(restore_surface):
    set_setting("two_sided_lighting", "on")
    assert restore_surface["two_sided"] is True
    set_setting("two_sided_lighting", "off")
    assert restore_surface["two_sided"] is False


def test_two_sided_lighting_toggles(restore_surface):
    set_setting("two_sided_lighting", "off")
    set_setting("two_sided_lighting", "toggle")
    assert get_setting("two_sided_lighting") is True


# --------------------------------------------------------------------------- #
# The rule the table exists to keep
# --------------------------------------------------------------------------- #
def test_every_transforming_spec_round_trips():
    """A one-way transform would silently corrupt the value it reports.

    Any spec that converts on the way in must convert back on the way out, or
    `get` answers in the storage's units and the next `set` compounds the error.

    Probed **on the spec's own domain**: an integer setting promises the round
    trip for integers and nothing else. ``surface_quality`` is a level selecting
    one of eight separations, so asking it to preserve 0.25 would be asking it
    to be a float, which is exactly the confusion it was registered wrongly as
    before.
    """
    probes = {
        "float": (0.0, 0.25, 0.5, 1.0),
        "int": (-3, -1, 0, 1, 2, 3, 4),
    }
    checked = 0
    for name in setting_names():
        spec = resolve(name)
        if spec.stored is None and spec.shown is None:
            continue
        assert spec.stored is not None and spec.shown is not None, name
        for probe in probes.get(spec.kind, (0.0, 1.0)):
            assert spec.from_config(spec.to_config(probe)) == pytest.approx(
                probe
            ), f"{name} does not round-trip at {probe}"
        checked += 1
    assert checked >= 2, "the transforming specs went missing"


# --------------------------------------------------------------------------- #
# surface_quality: a level, not a spacing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "level, spacing",
    [
        (4, 0.0625),   # "totally impractical"
        (3, 0.25 / 3.0),
        (2, 0.125),    # "nearly perfect"
        (1, 0.25),     # "good"
        (0, 0.5),      # normal -- PyMOL's default
        (-1, 0.85),
        (-2, 0.85 * 1.5),
        (-3, 2.0),     # "miserable"
    ],
)
def test_the_quality_levels_are_pymols(restore_surface, level, spacing):
    """Transcribed from ``RepSurfaceSetSettings``; the numbers are the meaning."""
    set_setting("surface_quality", level)
    assert restore_surface["grid_spacing"] == pytest.approx(spacing)
    assert get_setting("surface_quality") == level


def test_a_higher_level_is_a_finer_surface(restore_surface):
    """The direction is the whole point, and it is the opposite of a spacing.

    Registered as a float spacing under PyMOL's name, `surface_quality 0` asked
    for "normal" and got a spacing of zero -- not coarse, but infinitely fine.
    """
    set_setting("surface_quality", 0)
    normal = restore_surface["grid_spacing"]
    set_setting("surface_quality", 2)
    assert restore_surface["grid_spacing"] < normal
    set_setting("surface_quality", -3)
    assert restore_surface["grid_spacing"] > normal


def test_the_level_reads_the_base_separations(restore_surface):
    """The four bases are registered settings, so they have to be *read*."""
    set_setting("surface_normal", 0.6)
    try:
        set_setting("surface_quality", 0)
        assert restore_surface["grid_spacing"] == pytest.approx(0.6)
    finally:
        unset_setting("surface_normal")


def test_a_spacing_set_directly_reports_the_nearest_level(restore_surface):
    """A dotted path can set anything; `get` answers with the closest level."""
    set_setting("surface.grid_spacing", 0.51)
    assert get_setting("surface_quality") == 0


# --------------------------------------------------------------------------- #
# One name, one entry
# --------------------------------------------------------------------------- #
def test_no_setting_is_registered_twice():
    """A duplicate name silently shadows, and the shadowed one still *looks* live.

    `solvent_radius` was registered twice, onto two different config keys. The
    surface mesh read one and `get_area` read the other, so `set solvent_radius`
    moved the number the area calculation used and left the surface on screen
    untouched -- with both entries in the table, both docstrings plausible, and
    nothing failing.
    """
    from chisurf.plugins.chimol.chimol.settings import _SPECS

    seen: dict[str, str] = {}
    duplicates = []
    for spec in _SPECS:
        if spec.name in seen:
            duplicates.append(f"{spec.name}: {seen[spec.name]} and {'.'.join(spec.path)}")
        seen[spec.name] = ".".join(spec.path)
    assert not duplicates, "settings registered more than once: " + "; ".join(duplicates)


def test_no_two_settings_share_a_config_path():
    """Two names for one storage is fine; one name for two storages is not.

    The reverse -- several PyMOL names onto one config entry -- is deliberate
    (`cartoon_side_chain_helper` and `ribbon_side_chain_helper` are one setting
    here), so this only asserts the direction that bites.
    """
    from chisurf.plugins.chimol.chimol.settings import _SPECS

    by_name: dict[str, set[str]] = {}
    for spec in _SPECS:
        by_name.setdefault(spec.name, set()).add(".".join(spec.path))
    split = {n: p for n, p in by_name.items() if len(p) > 1}
    assert not split, f"one name writing several config entries: {split}"


def test_the_probe_radius_reaches_the_surface_the_user_sees(restore_surface):
    """The consumer that was left behind by the duplicate."""
    set_setting("solvent_radius", 2.5)
    assert restore_surface["probe_radius"] == pytest.approx(2.5)
    assert get_setting("solvent_radius") == pytest.approx(2.5)
