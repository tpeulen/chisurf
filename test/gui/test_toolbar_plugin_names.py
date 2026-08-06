"""``toolbar_plugins`` entries must survive a plugin being renamed.

The setting stores a plugin's *display* name, so every rename drops a button
from the toolbar and logs ``Could not find module for plugin`` on each start.
Three of the seven shipped entries had been dead that way — and because user
settings are copied to ``~/.chisurf`` once and never refreshed, correcting the
shipped list only reaches new installs. The resolution therefore has to be
lenient, which is what these tests pin.
"""

import pytest

import chisurf as cs
import chisurf.plugins


@pytest.fixture(scope="module")
def resolve(qapp):
    """The real lookup ``load_toolbar_plugins`` uses, over the real plugin set.

    Imported rather than reimplemented: a copy of the matcher here would keep
    passing after the one in the application changed.
    """
    from chisurf.gui.main import find_toolbar_plugin

    plugin_infos = list(cs.plugins.iter_plugins())
    return lambda name: find_toolbar_plugin(plugin_infos, name)


def test_every_shipped_entry_resolves(resolve):
    """A dead entry is a button the user paid for and never got."""
    entries = cs.core.settings.cs_settings["plugins"]["toolbar_plugins"]
    unresolved = [name for name in entries if resolve(name) is None]
    assert not unresolved, f"toolbar_plugins names nothing: {unresolved}"


@pytest.mark.parametrize(
    "legacy, module",
    [
        # Punctuation drift.
        ("Single-Molecule:Burst-Selection", "burst_selection"),
        # The display name was shortened.
        ("Single-Molecule:Burst MLE Lifetime Analysis", "burst_mle_analysis"),
        ("Tools:ndXplorer", "ndxplorer"),
        # Re-categorised, leaf unchanged.
        ("Tools:Histogram-Microtime", "microtime_histogram"),
        ("FCS:Correlator", "fcs_correlator"),
        ("Miscellaneous:F-Test", "f_test"),
    ],
)
def test_the_names_left_in_existing_user_settings_still_resolve(resolve, legacy, module):
    info = resolve(legacy)
    assert info is not None, f"{legacy} no longer resolves"
    assert info.get("module_name") == module


def test_leniency_refuses_to_guess(resolve):
    """A prefix shared by several plugins must warn, not pick one at random."""
    assert resolve("Tools:Burst") is None
    assert resolve("Nothing:At All Whatsoever") is None
