"""Tests for the PyMOL-compatible settings layer and its commands.

The point of the layer is that a PyMOL script's ``set``/``get``/``unset`` lines
reach the code that actually draws, so these tests check the mapping as much as
the parsing: every registered setting must name a real config entry, and a
change must land where the renderer reads it.
"""

from __future__ import annotations

import pytest

from chimol import settings
from chimol.cmd.command import Cmd
from chimol.config import _DISPLAY_CONFIG
from chimol.testing.mock_viewer import MockViewer, MockWindow


@pytest.fixture
def cmd_and_viewer():
    viewer = MockViewer()
    window = MockWindow(viewer)
    cmd = Cmd(window)
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, viewer, messages, errors


@pytest.fixture(autouse=True)
def restore_settings():
    """Undo every setting the test touched, so tests stay order-independent."""
    before = {s.name: settings.get_setting(s.name) for s in settings.iter_settings()}
    yield
    for name, value in before.items():
        settings.set_setting(name, value)


# --------------------------------------------------------------------------- #
# The table itself
# --------------------------------------------------------------------------- #
def test_every_setting_points_at_a_real_config_entry():
    """No setting may name a path the display config does not have.

    A missing path is a setting that silently does nothing: ``set`` reports
    success and the renderer never sees the value.
    """
    missing = []
    for spec in settings.iter_settings():
        node = _DISPLAY_CONFIG
        for part in spec.path:
            if not isinstance(node, dict) or part not in node:
                missing.append(f"{spec.name} -> {'.'.join(spec.path)}")
                break
            node = node[part]
    assert missing == []


def test_declared_kinds_match_the_stored_values():
    """A float setting must not be sitting on a string in the config."""
    kind_types = {
        "bool": bool,
        "int": int,
        "float": (int, float),
        "str": str,
        "vector": (list, tuple),
        "color": (str, list, tuple),
        # PyMOL's `cColorDefault` (-1): no per-representation override, so the
        # representation takes its own colour. Stored as None, hence the extra
        # member -- this kind arrived with the unit-cell work and the table was
        # not extended with it, so every run since raised KeyError here rather
        # than checking anything.
        "color_or_default": (str, list, tuple, type(None)),
    }
    for spec in settings.iter_settings():
        value = settings.get_setting(spec.name)
        assert spec.kind in kind_types, (
            f"{spec.name!r} declares kind {spec.kind!r}, which this test does not "
            f"know how to check; add it to kind_types rather than leaving the "
            f"suite to raise KeyError"
        )
        expected = kind_types[spec.kind]
        # bool is a subclass of int, so check it first and exclude it elsewhere.
        if spec.kind != "bool" and isinstance(value, bool):
            pytest.fail(f"{spec.name} holds a bool but is declared {spec.kind}")
        assert isinstance(value, expected), f"{spec.name} = {value!r}"


def test_the_dead_flat_namespace_is_gone():
    """The old copies of PyMOL names at config top level must not come back.

    They shadowed nothing and were read by nothing, so having them around only
    made it look like ``set cartoon_loop_radius`` had somewhere to land.
    """
    for name in ("cartoon_loop_radius", "ray_shadow", "field_of_view", "bg_rgb"):
        assert name not in _DISPLAY_CONFIG


# --------------------------------------------------------------------------- #
# Name resolution
# --------------------------------------------------------------------------- #
def test_exact_and_prefix_resolution():
    assert settings.resolve("cartoon_loop_radius").name == "cartoon_loop_radius"
    assert settings.resolve("cartoon_oval_w").name == "cartoon_oval_width"


def test_ambiguous_prefix_is_rejected_with_the_candidates():
    with pytest.raises(settings.UnknownSettingError) as exc:
        settings.resolve("cartoon_oval")
    message = str(exc.value)
    assert "cartoon_oval_width" in message
    assert "cartoon_oval_length" in message


def test_unknown_name_raises():
    with pytest.raises(settings.UnknownSettingError):
        settings.resolve("no_such_setting")


def test_dotted_path_reaches_config_entries_without_a_pymol_name():
    """``metaball.alpha`` has no PyMOL equivalent but must stay reachable."""
    spec, value = settings.set_setting("metaball.alpha", "0.5")
    assert spec.path == ("metaball", "alpha")
    assert value == pytest.approx(0.5)
    assert _DISPLAY_CONFIG["metaball"]["alpha"] == pytest.approx(0.5)
    settings.set_setting("metaball.alpha", 1.0)


def test_dotted_path_to_a_nonexistent_entry_raises():
    with pytest.raises(settings.UnknownSettingError):
        settings.resolve("metaball.no_such_key")


# --------------------------------------------------------------------------- #
# Value coercion
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("token", ["on", "yes", "true", "1", "T"])
def test_bool_true_spellings(token):
    assert settings.coerce(token, "bool") is True


@pytest.mark.parametrize("token", ["off", "no", "false", "0", "F"])
def test_bool_false_spellings(token):
    assert settings.coerce(token, "bool") is False


def test_bool_rejects_nonsense():
    with pytest.raises(settings.SettingValueError):
        settings.coerce("maybe", "bool")


@pytest.mark.parametrize("token", ["[1, 2, 3]", "1 2 3", "1,2,3", "(1,2,3)"])
def test_vector_spellings(token):
    assert settings.coerce(token, "vector") == [1.0, 2.0, 3.0]


def test_int_rounds_rather_than_truncating():
    assert settings.coerce("6.7", "int") == 7


def test_number_rejects_nonsense():
    with pytest.raises(settings.SettingValueError):
        settings.coerce("wide", "float")


def test_color_keeps_a_name_but_parses_a_triplet():
    assert settings.coerce("white", "color") == "white"
    assert settings.coerce("[1, 1, 1]", "color") == [1.0, 1.0, 1.0]


# --------------------------------------------------------------------------- #
# The commands
# --------------------------------------------------------------------------- #
def test_set_writes_through_to_the_config(cmd_and_viewer):
    cmd, _, messages, errors = cmd_and_viewer
    cmd.do("set cartoon_loop_radius, 0.35")
    assert errors == []
    assert _DISPLAY_CONFIG["cartoon"]["loop_radius"] == pytest.approx(0.35)
    assert "cartoon_loop_radius set to 0.35" in messages[-1]


def test_set_accepts_a_prefix(cmd_and_viewer):
    cmd, _, _, errors = cmd_and_viewer
    cmd.do("set cartoon_rect_l, 1.9")
    assert errors == []
    assert _DISPLAY_CONFIG["cartoon"]["rect_length"] == pytest.approx(1.9)


def test_set_bool_uses_pymol_spelling(cmd_and_viewer):
    cmd, _, messages, errors = cmd_and_viewer
    cmd.do("set ray_shadow, off")
    assert errors == []
    assert _DISPLAY_CONFIG["ray"]["shadow"] is False
    assert messages[-1].endswith("off")


def test_get_reports_the_current_value(cmd_and_viewer):
    cmd, _, messages, errors = cmd_and_viewer
    cmd.do("set cartoon_loop_radius, 0.42")
    cmd.do("get cartoon_loop_radius")
    assert errors == []
    assert messages[-1] == "cartoon_loop_radius = 0.42"


def test_unset_restores_the_default(cmd_and_viewer):
    cmd, _, _, errors = cmd_and_viewer
    cmd.do("set cartoon_loop_radius, 0.99")
    cmd.do("unset cartoon_loop_radius")
    assert errors == []
    assert _DISPLAY_CONFIG["cartoon"]["loop_radius"] == pytest.approx(
        settings.SETTINGS["cartoon_loop_radius"].default
    )


def test_toggle_flips_a_boolean(cmd_and_viewer):
    cmd, _, _, errors = cmd_and_viewer
    before = bool(settings.get_setting("ray_shadow"))
    cmd.do("toggle ray_shadow")
    assert errors == []
    assert bool(settings.get_setting("ray_shadow")) is (not before)


def test_toggle_refuses_a_non_boolean(cmd_and_viewer):
    cmd, _, _, errors = cmd_and_viewer
    cmd.do("toggle cartoon_loop_radius")
    assert errors and "not a boolean" in errors[-1]


def test_unknown_setting_is_reported(cmd_and_viewer):
    cmd, _, _, errors = cmd_and_viewer
    cmd.do("set no_such_setting, 1")
    assert errors and "Unknown setting" in errors[-1]


def test_bad_value_is_reported_and_nothing_is_written(cmd_and_viewer):
    cmd, _, _, errors = cmd_and_viewer
    before = settings.get_setting("cartoon_loop_radius")
    cmd.do("set cartoon_loop_radius, thick")
    assert errors and "number" in errors[-1]
    assert settings.get_setting("cartoon_loop_radius") == before


def test_field_of_view_reaches_the_viewer(cmd_and_viewer):
    """The camera is renderer state, so `set` must push it, not just store it."""
    cmd, viewer, _, errors = cmd_and_viewer
    cmd.do("set field_of_view, 35")
    assert errors == []
    assert viewer._field_of_view == pytest.approx(35.0)


def test_bg_rgb_reaches_the_viewer(cmd_and_viewer):
    cmd, viewer, _, errors = cmd_and_viewer
    cmd.do("set bg_rgb, white")
    assert errors == []
    assert viewer._background_color == "white"


def test_max_fps_reaches_the_viewer(cmd_and_viewer):
    """The frame-rate ceiling is renderer state, held by rendercanvas: a
    changed value must re-throttle the already-open window, not just sit in
    the config until the next restart."""
    cmd, viewer, _, errors = cmd_and_viewer
    cmd.do("set max_fps, 30")
    assert errors == []
    assert viewer._max_fps == pytest.approx(30.0)


def test_nerd_tick_writes_through_to_the_config(cmd_and_viewer):
    """Unlike `max_fps`, the nerd tick is read live from the config -- it has
    no renderer state to push, so `set` only needs to land in the config."""
    from chimol.config import _DISPLAY_CONFIG

    cmd, _viewer, _, errors = cmd_and_viewer
    cmd.do("set nerd_tick, 0.2")
    assert errors == []
    assert _DISPLAY_CONFIG["nerd"]["tick_interval"] == pytest.approx(0.2)


def test_representation_toggle_spelling_still_works(cmd_and_viewer):
    """Chimol scripts have long written `set cartoon, off`; keep honouring it."""
    cmd, viewer, _, errors = cmd_and_viewer
    cmd.do("set cartoon, off")
    assert errors == []
    assert viewer._reps["cartoon"] is False


def test_help_setting_describes_where_a_value_lands(cmd_and_viewer):
    cmd, _, messages, _ = cmd_and_viewer
    cmd.do("help_setting cartoon_rect_width")
    text = messages[-1]
    assert "cartoon.rect_width" in text
    assert "float" in text
