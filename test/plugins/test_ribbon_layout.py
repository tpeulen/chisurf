"""The ribbon as shipped: which tab, which group, which button.

The ribbon has no layout file — a plugin's manifest ``display_name`` is its
address, so moving one tool is a one-line manifest edit that nothing reviews as
a layout change. This pins the result, computed with the shipped default
settings through :func:`chisurf.gui.widgets.ribbon.layout.plugin_layout`, the
function the ribbon itself builds from. A deliberate move updates ``EXPECTED``
in the same change; an accidental one fails here.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

import chisurf.plugins
from chisurf.gui.widgets.ribbon.layout import (
    TAB_ORDER,
    group_records,
    ordered_tabs,
    plugin_layout,
    split_address,
)

SETTINGS = pathlib.Path(chisurf.__file__).parent / "core" / "settings" / "settings_chisurf.yaml"

#: tab → group → button labels, in ribbon order.
EXPECTED = {
    "File": {
        "Data": ["File tools"],
        "Setup": ["Menu Switch", "Settings", "Switch User"],
    },
    "Main": {
        "Help": ["About ChiSurf", "Documentation"],
    },
    "Spectroscopy": {
        "Correlation": ["FCS", "PCH"],
        "Decay": ["Decay Analysis"],
        "Kinetics": ["Hidden Markov model"],
        "Single-Molecule": [
            "ALEX Suite",
            "Burst Analysis",
            "Intensity trace",
            "Trace Browser",
            "ebFRET",
        ],
    },
    "Imaging": {
        "Imaging": ["Image Tools"],
    },
    "Structure": {
        "Modelling": ["ChiMOL", "Structure Tools"],
    },
    "Tools": {
        "Calculators": ["Calculators", "Light Path Simulator", "Spectra Downloader", "Wizards"],
        "Photon data": ["TTTR Tools"],
        "System": ["Code Editor", "Games", "MMFDB Admin", "Screenshot"],
        "Views": ["Acquisition", "Global View", "ndX"],
    },
}


def shipped_layout() -> dict[str, dict[str, list[str]]]:
    """The layout of the built-in plugins under the shipped default settings."""
    settings = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    built_in = [i for i in chisurf.plugins.iter_plugins() if i.get("source") == "built-in"]
    layout = plugin_layout(built_in, settings.get("plugins", {}), experimental=False)
    return {
        tab: {group: [split_address(r["plugin_name"])[2] for r in records] for group, records in groups.items()}
        for tab, groups in layout.items()
    }


def test_the_shipped_ribbon_is_the_reviewed_one():
    assert shipped_layout() == EXPECTED


def test_tabs_appear_in_the_declared_order():
    assert list(shipped_layout()) == [t for t in TAB_ORDER if t in EXPECTED]


@pytest.mark.parametrize(
    "address, expected",
    [
        ("Tab:Name", ("Tab", "Tab", "Name")),
        ("Tab:Group:Name", ("Tab", "Group", "Name")),
        # Four and more segments used to be dropped by the ribbon without a word.
        ("Tab:A:B:Name", ("Tab", "A › B", "Name")),
        ("Tab:A:B:C:Name", ("Tab", "A › B › C", "Name")),
        ("Name", ("Main", "Main", "Name")),
    ],
)
def test_an_address_of_any_depth_has_a_tab_a_group_and_a_label(address, expected):
    assert split_address(address) == expected


def test_setup_and_help_land_in_the_tabs_the_ribbon_builds():
    layout = group_records(
        [{"plugin_name": "Setup:Settings"}, {"plugin_name": "Help:Docs"}, {"plugin_name": "Zeta:X"}]
    )
    assert list(layout) == ["File", "Main", "Zeta"]
    assert list(layout["File"]) == ["Setup"] and list(layout["Main"]) == ["Help"]


def test_unknown_tabs_follow_the_domain_tabs_and_dev_is_last():
    assert ordered_tabs(["Dev", "Zeta", "Tools", "Alpha", "File"]) == [
        "File",
        "Tools",
        "Alpha",
        "Zeta",
        "Dev",
    ]


def test_the_group_named_after_its_tab_comes_first():
    layout = group_records([{"plugin_name": "T:A:x"}, {"plugin_name": "T:y"}])
    assert list(layout["T"]) == ["T", "A"]


def test_hidden_disabled_and_cli_only_plugins_have_no_button():
    infos = [
        {"plugin_name": "T:Shown"},
        {"plugin_name": "T:Hidden", "menu_hidden": True},
        {"plugin_name": "T:Broken"},
        {"plugin_name": "T:Cli", "cli_only": True},
    ]
    settings = {"disabled_plugins": ["T:Broken"], "hide_disabled_plugins": False}
    shown = lambda exp: [  # noqa: E731
        split_address(r["plugin_name"])[2]
        for r in plugin_layout(infos, settings, experimental=exp)["T"]["T"]
    ]
    assert shown(False) == ["Shown"]
    assert shown(True) == ["Broken", "Cli", "Shown"]
