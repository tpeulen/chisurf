"""The viewport's single-key shortcuts: one table, read and written.

The point of `chimol.chrome.keybindings` is that the same information reaches three
places -- the ``keys`` overlay, the settings panel, and the key handler that
actually performs an action -- without being written down three times. These
tests hold that: a rebind has to change what the key *does*, not just what the
overlay claims, and vice versa.
"""
from __future__ import annotations

import pytest

from chimol.chrome import keybindings as kb


@pytest.fixture(autouse=True)
def _restore_bindings():
    """Put the shipped keys back, whatever a test did to them.

    The display config is process-wide, so a test that rebinds and leaves it
    rebound changes the answer for every test after it -- the exact failure
    `okf` records as "global setting test isolation".
    """
    from chimol.core.settings.config import _DISPLAY_CONFIG

    before = dict(_DISPLAY_CONFIG.get("keys") or {})
    yield
    _DISPLAY_CONFIG["keys"] = before


def _set(action: str, key: str) -> None:
    from chimol.core.settings.config import _DISPLAY_CONFIG

    _DISPLAY_CONFIG.setdefault("keys", {})[action] = key


# -- the table -------------------------------------------------------------
def test_every_action_ships_with_a_key_and_a_label():
    """A row with no label is a row the overlay prints blank."""
    for action, (key, label) in kb.ACTIONS.items():
        assert key, f"{action} has no default key"
        assert label.strip(), f"{action} has no label"


def test_the_defaults_are_the_shortcuts_that_always_shipped():
    """Muscle memory: these six were hard-coded comparisons before the table,
    and moving them into configuration must not have moved the keys."""
    assert kb.default_keys() == {
        "cartoon": "r", "ca_trace": "c", "atoms": "b",
        "dots": "d", "sidechains": "s", "close": "q",
    }


def test_the_table_and_the_shipped_config_agree():
    """The one drift this design can still have, so it is guarded.

    `ACTIONS`' defaults are spelled out a second time in `core/settings/config.py`'s
    defaults literal -- deliberately, because `test_display_config_defaults`
    `eval`s that dict as a literal and a function call inside it breaks that
    guard. Two copies need a test, and this is it: an action added to the
    table but not to the config would resolve to its fallback and never appear
    in the settings panel, which is the sort of half-working that is hard to
    notice.
    """
    from chimol.core.settings.config import _load_display_config

    shipped = (_load_display_config().get("keys") or {})
    assert shipped == kb.default_keys()


def test_labels_are_ascii_so_the_atlas_can_draw_them():
    """The overlay draws through the chrome's glyph atlas, and a character it
    has not baked paints as nothing at all rather than raising."""
    for action, (_key, label) in kb.ACTIONS.items():
        assert label.isascii(), f"{action}'s label has a non-ASCII character"


# -- resolution ------------------------------------------------------------
def test_a_bound_key_resolves_to_its_action():
    assert kb.action_for_key("r") == "cartoon"


def test_resolution_ignores_case():
    """The bindings are single letters; shift is not part of them."""
    assert kb.action_for_key("R") == kb.action_for_key("r") == "cartoon"


def test_an_unbound_key_resolves_to_nothing():
    assert kb.action_for_key("x") is None


def test_a_rebind_moves_what_the_key_does():
    _set("cartoon", "t")
    assert kb.action_for_key("t") == "cartoon"
    assert kb.action_for_key("r") is None


def test_an_empty_binding_switches_the_shortcut_off():
    """Clearing the field is a legitimate way to disable a shortcut, and must
    not turn into "fires on every keystroke that produced no text"."""
    _set("cartoon", "")
    assert kb.action_for_key("") is None
    assert kb.action_for_key("r") is None
    assert any(b.action == "cartoon" and b.key == "" for b in kb.bindings())


def test_a_missing_section_falls_back_to_the_defaults():
    """A configuration written before an action existed still resolves it."""
    from chimol.core.settings.config import _DISPLAY_CONFIG

    _DISPLAY_CONFIG.pop("keys", None)
    assert kb.action_for_key("r") == "cartoon"


def test_a_malformed_value_does_not_take_the_viewer_down():
    _set("cartoon", None)
    assert isinstance(kb.bindings(), list)


# -- what the overlay prints ----------------------------------------------
def test_bindings_lists_every_action_in_table_order():
    rows = kb.bindings()
    assert [one.action for one in rows] == list(kb.ACTIONS)


def test_bindings_report_the_live_key_not_the_default():
    _set("atoms", "n")
    assert next(one.key for one in kb.bindings() if one.action == "atoms") == "n"


# -- conflicts -------------------------------------------------------------
def test_no_conflicts_in_the_shipped_bindings():
    """Six keys, six actions -- if that stops being true, say so here rather
    than in a bug report about a shortcut doing the wrong thing."""
    assert kb.conflicts() == {}


def test_two_actions_on_one_key_are_reported():
    """The settings panel can be typed into, so this state is reachable; the
    honest thing is to name it rather than silently last-one-wins."""
    _set("cartoon", "c")          # ca_trace already holds "c"
    clash = kb.conflicts()
    assert clash == {"c": ["cartoon", "ca_trace"]}
    # Deterministic while it lasts: table order decides.
    assert kb.action_for_key("c") == "cartoon"


# -- the wiring ------------------------------------------------------------
def test_the_settings_panel_offers_every_binding_as_an_editable_field():
    """"Adjust the keyboard bindings" is this: the panel walks the display
    config, so the rows exist without a hand-written control -- but they have
    to come out editable rather than as a read-only label."""
    from chimol.chrome.panels.settings import build_model

    model = build_model(lambda *_a: None)
    rows = {s.key: s for s in model.settings if s.key.startswith("keys.")}
    assert len(rows) == len(kb.ACTIONS)
    for action in kb.ACTIONS:
        assert f"keys.{action}" in rows


def test_the_keys_command_is_registered():
    """Help -> Keyboard bindings issues this; a menu row pointing at a command
    that does not exist looks fine and does nothing."""
    from chimol.commands import cmd

    names = set(cmd.command_names())
    assert "keys" in names
    assert "keybindings" in names


def test_the_help_menu_offers_the_overlay():
    from chimol.hosts.qt.menu_bar import HELP_MENU

    labels = {getattr(e, "label", None): getattr(e, "command", None) for e in HELP_MENU}
    assert labels.get("Keyboard bindings") == "keys"
