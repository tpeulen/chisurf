"""Every stored setup is selectable in the pipeline's 0. Setup Selection, whatever the hub handed in.

The hub restores a session or hands a working definition to the step before its first frame. That used to
switch off the first frame's read of the store as well as "open the last used setup", so the Setup choice
listed nothing but "Unsaved" and a saved setup (RVZMT150) could not be picked.
"""

import time

import pytest

from chisurf.core.setup_channel_definition import ChannelDefinition

STORED = {
    "RVZMT150": {"detectors": {"G|G": {"chs": [0, 3]}, "R|G": {"chs": [1, 2]}}},
    "TP_20261031 DNA PIE": {"detectors": {"G|G": {"chs": [3, 0]}, "R|G": {"chs": [2, 1]}}},
}
WORKING = {
    "detectors": {f"ch{i}": {"chs": [i]} for i in range(4)},
    "windows": {"prompt": [11, 31], "delayed": [31, 503]},
}


@pytest.fixture
def store(monkeypatch):
    """A store of two setups, RVZMT150 the last used one; nothing on disk or in the MMFDB."""

    def read_setups_payload(self):
        return {"setups": {name: dict(data) for name, data in STORED.items()}, "last_used": "RVZMT150"}

    def refresh_setups(self):
        return self.apply_setups_payload(read_setups_payload(self))

    monkeypatch.setattr(ChannelDefinition, "read_setups_payload", read_setups_payload)
    monkeypatch.setattr(ChannelDefinition, "refresh_setups", refresh_setups)


def _listed(prepare):
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_analysis.gui.setup_selection_app import (
        BurstSetupSelectionApp,
    )

    app = BurstSetupSelectionApp(settings=None)
    prepare(app)
    driver = Driver(app, size=(1100, 800))
    for _ in range(40):
        driver.draw(1)
        if not app.page.toolbar.loading and app.page.toolbar.names:
            break
        time.sleep(0.05)
    return app


def test_a_fresh_step_lists_the_store_and_opens_the_last_used(store):
    app = _listed(lambda app: None)
    assert app.page.toolbar.names == sorted(STORED)
    assert app.selected_setup_name() == "RVZMT150"


@pytest.mark.parametrize(
    "prepare",
    [
        lambda app: app.restore_settings({"channel_definition": WORKING}),
        lambda app: app.load_data_into_tables(WORKING),
    ],
    ids=["restored-session", "hub-definition"],
)
def test_a_handed_in_definition_keeps_every_stored_setup_selectable(store, prepare):
    app = _listed(prepare)
    assert app.page.toolbar.names == sorted(STORED)
    # the handed-in definition stays on the page: it is not replaced by the last used setup
    assert app.selected_setup_name() == ""
    assert sorted(app.model.data["detectors"]) == ["ch0", "ch1", "ch2", "ch3"]
    assert app.select_setup("RVZMT150") and app.selected_setup_name() == "RVZMT150"


def test_photons_handed_to_the_hub_take_the_last_used_setup_not_a_proposal(store, monkeypatch):
    """"Open in… Burst Analysis" opens the Data step before step 0 ever drew: the file's photons must
    still get the library's last used setup (RVZMT150), not detectors proposed from its header."""
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    def no_proposal(*args, **kwargs):
        raise AssertionError("a setup was proposed from the file although the library has one")

    monkeypatch.setattr(ChannelDefinition, "open_tttr", no_proposal)
    hub = create_app()
    hub.context.raw_files = ["DNA13bp_3.ptu"]
    hub._propose_setup_from_first_file()
    assert hub.setup_model.current_name == "RVZMT150"
    assert hub.context.setup_name == "RVZMT150"
    assert sorted(hub.context.channel_settings["detectors"]) == ["G|G", "R|G"]


def test_without_a_stored_setup_the_hub_proposes_one_from_the_file(monkeypatch):
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    monkeypatch.setattr(
        ChannelDefinition, "read_setups_payload", lambda self: {"setups": {}, "last_used": ""}
    )
    proposed = []
    monkeypatch.setattr(
        ChannelDefinition, "open_tttr", lambda self, *a, **k: proposed.append(a) or 1 / 0
    )
    hub = create_app()
    hub.context.raw_files = ["DNA13bp_3.ptu"]
    hub._propose_setup_from_first_file()
    assert proposed  # the file was asked (and its failure reported, not raised)
    assert hub.setup_model.current_name in ("", None)


def test_a_restored_unsaved_setup_yields_to_the_last_used_one(store):
    """A session saved with an unsaved definition (ch0..ch3 proposed from a PTU) used to come back on
    every start and hide the library: the hub now opens the last used setup instead."""
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    hub.restore_settings(
        {
            "selected": "setup",
            "setup": dict(WORKING, setup_name=""),
            "children": {"setup": {"setup_name": "", "channel_definition": WORKING, "page": {}}},
            "workflow": {"channel_settings": dict(WORKING), "setup_name": ""},
        }
    )
    setup = hub.children["setup"]
    assert "ch0" not in (hub.setup_model.data.get("detectors") or {})
    assert setup.open_last_used and setup.autoload  # step 0 lists the store and opens RVZMT150


def test_a_restored_named_setup_is_kept(store):
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    named = dict(STORED["TP_20261031 DNA PIE"], setup_name="TP_20261031 DNA PIE")
    hub.restore_settings({"selected": "setup", "setup": named, "children": {"setup": {"page": {}}}})
    setup = hub.children["setup"]
    assert hub.setup_model.current_name == "TP_20261031 DNA PIE"
    assert not setup.open_last_used and setup.autoload  # kept, and the store is still listed


def test_a_restored_named_setup_comes_back_as_the_library_holds_it(store):
    """A session saved RVZMT150 with detected windows taken in but never saved (prompt 10-31, the
    green decay cut away); every start restored that copy under the name. The library's wins."""
    from chisurf.plugins.burst.burst_analysis.gui.native import create_app

    hub = create_app()
    stale = {
        "setup_name": "RVZMT150",
        "detectors": {"G|G": {"chs": [0, 3], "micro_time_ranges": [[10, 31]]}},
        "windows": {"prompt": [10, 31], "delayed": [31, 503]},
    }
    hub.restore_settings({"selected": "setup", "setup": stale, "children": {"setup": {"page": {}}}})
    assert hub.setup_model.current_name == "RVZMT150"
    assert hub.setup_model.data["detectors"]["R|G"]["chs"] == [1, 2]  # the library's detectors
    assert "micro_time_ranges" not in hub.setup_model.data["detectors"]["G|G"]
