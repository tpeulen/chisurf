"""The menus are config, not code -- and the config cannot silently rot.

``gui/menus.json`` is the single source of the bar and the toolbar. The
guardrails live in ``test_menu_bar`` (PyMOL's order, every command
registered, every setting real); this file pins the config-loading contract
that those guardrails ride on:

* the JSON exists, parses, and defines every menu the bar names;
* a broken file **fails loudly** at import -- a viewer that silently starts
  without menus sends whoever hit it hunting a code bug;
* the splicing forms behave: ``include`` splices one menu into another's
  children (Build and Wizard under Tools, complete and single-sourced), and
  ``generate`` splices a section built from data that lives somewhere better
  (demos, presets, tours);
* editing the bar is editing the config: an entry added to the JSON appears
  in ``MENU_BAR`` without any code change.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import chimol.chrome.menus as menus
from chimol.chrome.object_menus import MenuEntry

MENUS_JSON = pathlib.Path(menus.__file__).resolve().parent / "data" / "menus.json"


def _config() -> dict:
    return json.loads(MENUS_JSON.read_text(encoding="utf-8"))


def test_the_config_exists_and_names_every_menu_on_the_bar():
    config = _config()
    defined = set(config["menus"])
    for name in config["menu_bar"]:
        assert name in defined, f"the bar lists {name!r} but the config does not define it"
    # ... and the two folded menus are defined too -- they are complete
    # menus that live one level down, not dead entries.
    assert {"Build", "Wizard"} <= defined


def test_the_bar_is_the_configs_bar():
    assert [title for title, _ in menus.MENU_BAR] == _config()["menu_bar"]


def test_the_toolbar_is_the_configs_toolbar():
    rows = _config()["toolbar"]
    assert menus.TOOLBAR == tuple(
        (row["label"], row["command"], row.get("note", "")) for row in rows
    )


def test_an_added_entry_needs_no_code_change():
    """The point of the migration: JSON in, menu entry out."""
    config = _config()
    entry = {
        "label": "Probe entry",
        "command": "orient",
        "note": "added by a test, read by the loader",
    }
    config["menus"]["Edit"].append(entry)
    built = menus._menu("Edit", config["menus"])
    assert built[-1].label == "Probe entry"
    assert built[-1].command == "orient"
    assert built[-1].note == entry["note"]


def test_include_splices_the_referenced_menu_completely():
    """Tools' Build and Wizard are the whole menus, one level down.

    An include that wrapped instead of splicing drew a submenu one level
    deeper than the config reads -- the failure this pins.
    """
    tools = {e.label: e for e in menus.TOOLS_MENU if not e.is_separator}
    assert "Build" in tools and "Wizard" in tools
    assert tools["Wizard"].children == menus.WIZARD_MENU
    assert tools["Build"].children == menus.BUILD_MENU
    # Single-sourced: editing the Wizard menu is editing both places.
    assert menus.WIZARD_MENU[-1].label == "Done"


def test_generate_splices_the_data_driven_sections():
    demo_labels = [e.label for e in menus.DEMO_MENU if not e.is_separator]
    assert len(demo_labels) > 5, "the demo section did not generate"
    assert any("labelling" in label.lower() for label in demo_labels)
    # The tours generate as Help's submenu.
    tour_menus = [e for e in menus.HELP_MENU if e.label == "Tours"]
    assert tour_menus and tour_menus[0].children, "the tours section did not generate"


def test_a_broken_config_fails_loudly(tmp_path, monkeypatch):
    """A missing or unparseable menu file is a broken build, not a degraded mode."""
    monkeypatch.setattr(menus, "MENUS_JSON", tmp_path / "not-here.json")
    with pytest.raises(RuntimeError, match="cannot read"):
        menus._load_config()

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(menus, "MENUS_JSON", bad)
    with pytest.raises(RuntimeError, match="not valid JSON"):
        menus._load_config()

    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(menus, "MENUS_JSON", empty)
    with pytest.raises(RuntimeError, match="no 'menus'"):
        menus._load_config()


def test_an_unknown_include_or_generator_is_named(tmp_path, monkeypatch):
    """The error says which row and what it asked for."""
    config = _config()
    config["menus"]["Edit"] = [{"include": "Nope"}]
    with pytest.raises(RuntimeError, match="Nope"):
        menus._menu("Edit", config["menus"])
    config["menus"]["Edit"] = [{"generate": "nope"}]
    with pytest.raises(RuntimeError, match="nope"):
        menus._menu("Edit", config["menus"])


def test_the_dye_labelling_wizard_is_reachable_from_the_tools_menu():
    """The entry that prompted the config move: Tools > Wizard."""
    tools = {e.label: e for e in menus.TOOLS_MENU if not e.is_separator}
    wizard = tools["Wizard"].children
    dye = [e for e in wizard if e.label == "Dye Labelling"]
    assert dye and dye[0].command == "wizard labelling"
    measure = tools["Measure"].children
    assert any(
        e.command == "wizard labelling" for e in measure
    ), "Measure also offers the dye wizard"


def test_every_config_row_shape_is_understood():
    """Walk the whole config: any row the loader cannot read is an error now,
    not a silent skip."""
    config = _config()
    for name, rows in config["menus"].items():
        menus._menu(name, config["menus"])  # raises on anything unknown
    assert all(isinstance(e, MenuEntry) for _, entries in menus.MENU_BAR for e in entries)
