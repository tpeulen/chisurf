"""Hub detector definitions propagate once while children retain their own state."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

SETUP = {
    "detectors": {"green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0}},
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
    "future_metadata": {"tag": "preserved"},
}


@pytest.fixture(autouse=True)
def private_settings(tmp_path, monkeypatch):
    """All GUI persistence stays in the test's scratch settings."""
    for name, suffix in [
        ("CHISURF_SETTINGS_DIR", "settings"),
        ("MMFDB_SETTINGS_DIR", "mmfdb"),
        ("MMFDB_DATABASE_PATH", "mmfdb.sqlite"),
    ]:
        monkeypatch.setenv(name, str(tmp_path / suffix))


def child_factory(nested=False):
    """Create a genuine detector editor in a minimal emtk child, with an observable callback."""
    from emtk.app import ImApp

    from chisurf.emtk.channel_definition import ChannelDefinitionWidget

    class Child(ImApp):
        def __init__(self):
            self.delivered = []
            editor = ChannelDefinitionWidget(on_changed=self.delivered.append)
            self.tool = SimpleNamespace(channel_editor=editor) if nested else None
            if not nested:
                self.editor = editor
            super().__init__(lambda: editor.draw())

        def restore_settings(self, state):
            from chisurf.core.setup_channel_definition import ChannelDefinition

            editor = self.tool.channel_editor if nested else self.editor
            editor.model = ChannelDefinition(state)
            editor.model.on_changed = self.delivered.append

        def close(self):
            (self.tool.channel_editor if nested else self.editor).close()

    return Child


def test_setup_first_lazy_children_and_once_per_revision():
    """A late-created child gets the current definition; unchanged deliveries do not refire."""
    from chisurf.emtk.tool_hub import ToolHubApp

    hub = ToolHubApp(
        "Test",
        [
            {"role": name, "name": name, "uses_setup": True, "factory": child_factory()}
            for name in ("a", "b", "c")
        ],
    )
    try:
        assert hub.tools[0]["role"] == "setup"
        hub.setup_model.data = deepcopy(SETUP)
        hub.setup_model.changed()
        a = hub.ensure_child("a")
        b = hub.ensure_child("b")
        assert a.editor.model is hub.setup_model is b.editor.model
        assert len(a.delivered) == len(b.delivered) == 1
        hub._shared_setup_changed(hub.setup_model.get_settings())
        assert len(a.delivered) == 1
        hub.setup_model.data["detectors"]["green"]["g_factor"] = 1.25
        hub.setup_model.changed()
        c = hub.ensure_child("c")
        assert len(a.delivered) == len(b.delivered) == 2
        assert len(c.delivered) == 1
        assert c.delivered[0]["detectors"]["green"]["g_factor"] == 1.25
        a.delivered[-1]["future_metadata"]["tag"] = "mutated"
        assert b.delivered[-1]["future_metadata"]["tag"] == "preserved"
        assert hub.setup_model.data["future_metadata"]["tag"] == "preserved"
    finally:
        hub.close()


def test_nested_controller_and_restore_reattach_authoritative_model():
    """A controller-owned editor may replace its model on restore; shared state still wins."""
    from chisurf.emtk.tool_hub import ToolHubApp

    hub = ToolHubApp(
        "Test",
        [
            {
                "role": "nested",
                "name": "nested",
                "uses_setup": True,
                "factory": child_factory(nested=True),
            }
        ],
    )
    try:
        hub.setup_model.data = deepcopy(SETUP)
        child = hub.ensure_child("nested")
        assert child.tool.channel_editor.hosted
        hub.restore_settings(
            {"setup": SETUP, "children": {"nested": {"detectors": {}}}, "selected": "nested"}
        )
        assert child.tool.channel_editor.model is hub.setup_model
        before = len(child.delivered)
        hub.setup_model.data["future_metadata"]["tag"] = "new"
        hub.setup_model.changed()
        assert len(child.delivered) == before + 1
        assert child.delivered[-1]["future_metadata"]["tag"] == "new"
        assert hub.export_settings()["setup"]["future_metadata"]["tag"] == "new"
    finally:
        hub.close()


def test_hosted_render_has_edit_link_and_no_duplicate_detector_table():
    """The actual pointer action returns to the only full setup page."""
    from emtk.testing import Driver

    from chisurf.emtk.tool_hub import ToolHubApp

    hub = ToolHubApp(
        "Test", [{"role": "a", "name": "a", "uses_setup": True, "factory": child_factory()}]
    )
    driver = Driver(hub, (1100, 720))
    try:
        hub.setup_model.data = deepcopy(SETUP)
        hub.select("a")
        driver.frame(3)
        assert driver.rect("Edit setup…")
        assert not any(text[5] == "Detectors" for text in driver.painter.texts)
        driver.click("Edit setup…")
        driver.frame(3)
        assert hub.selected == "setup"
        assert hub.children["setup"].page.model is hub.setup_model
    finally:
        hub.close()


def test_hub_without_setup_declaration_is_unchanged():
    """A pure utility hub has no added setup step or hosted editor."""
    from chisurf.emtk.tool_hub import ToolHubApp

    hub = ToolHubApp("Test", [{"role": "a", "name": "a", "factory": child_factory()}])
    try:
        assert [p["role"] for p in hub.tools] == ["a"]
        assert not hub.ensure_child("a").editor.hosted
    finally:
        hub.close()


def test_read_only_child_defers_latest_definition_and_keeps_shared_callback():
    """Busy child inputs are delivered once after unlock; hosting never steals hub notifications."""
    from chisurf.emtk.tool_hub import ToolHubApp

    hub = ToolHubApp(
        "Test", [{"role": "a", "name": "a", "uses_setup": True, "factory": child_factory()}]
    )
    try:
        hub.setup_model.data = deepcopy(SETUP)
        child = hub.ensure_child("a")
        callback = hub.setup_model.on_changed
        child.editor.read_only = True
        for value in (1.1, 1.2):
            hub.setup_model.data["detectors"]["green"]["g_factor"] = value
            hub.setup_model.changed()
        assert len(child.delivered) == 1
        child.editor.poll()
        assert len(child.delivered) == 1
        child.editor.read_only = False
        child.editor.poll()
        child.editor.poll()
        assert len(child.delivered) == 2
        assert child.delivered[-1]["detectors"]["green"]["g_factor"] == 1.2
        assert hub.setup_model.on_changed is callback
        assert not child.editor.files_dropped(["wrong-step.json"])
    finally:
        hub.close()


def test_complete_array_metadata_change_is_a_new_revision():
    """A change hidden by NumPy's truncated repr must still reach every child."""
    import numpy as np

    from chisurf.emtk.tool_hub import ToolHubApp

    hub = ToolHubApp(
        "Test", [{"role": "a", "name": "a", "uses_setup": True, "factory": child_factory()}]
    )
    try:
        hub.setup_model.data = deepcopy(SETUP)
        hub.setup_model.data["future_metadata"]["values"] = np.zeros(4096)
        child = hub.ensure_child("a")
        before_repr = str(hub.setup_model.data["future_metadata"]["values"])
        hub.setup_model.data["future_metadata"]["values"][2048] = 1.0
        assert str(hub.setup_model.data["future_metadata"]["values"]) == before_repr
        hub.setup_model.changed()
        assert len(child.delivered) == 2
        assert child.delivered[-1]["future_metadata"]["values"][2048] == 1.0
        assert hub.export_settings()["setup"]["future_metadata"]["values"][2048] == 1.0
    finally:
        hub.close()


def test_actual_snapshot_job_defers_setup_before_read_only_frame(monkeypatch):
    """A job locks inputs immediately, before the child's next frame updates read_only."""
    import threading
    import time

    from chisurf.emtk.tool_hub import ToolHubApp
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app

    started, release = threading.Event(), threading.Event()
    snapshots = []

    def hold(snapshot):
        snapshots.append(snapshot.session.definition_payload())
        started.set()
        assert release.wait(5.0)

    monkeypatch.setattr(MleViewModel, "hold_for_setup_test", hold, raising=False)
    hub = ToolHubApp(
        "Test", [{"role": "mle", "name": "mle", "uses_setup": True, "factory": create_app}]
    )
    try:
        hub.setup_model.data = deepcopy(SETUP)
        child = hub.ensure_child("mle")
        assert child.job.start("hold_for_setup_test")
        assert started.wait(5.0)
        assert child.job.busy and not child.editor.read_only
        hub.setup_model.data["detectors"]["green"]["g_factor"] = 1.5
        hub.setup_model.changed()
        assert snapshots[0]["detectors"]["green"]["g_factor"] == 1.0
        assert child.model.session.detectors["green"]["g_factor"] == 1.0
        release.set()
        deadline = time.monotonic() + 5.0
        while child.job.busy:
            assert time.monotonic() < deadline
            child.job.poll()
            time.sleep(0.01)
        child.editor.poll()
        assert child.model.session.detectors["green"]["g_factor"] == 1.5
    finally:
        release.set()
        hub.close()
