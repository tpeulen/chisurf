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
