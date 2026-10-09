"""Worker publications must not leave stale detector definitions in the editor."""

from __future__ import annotations

import copy
import json
from concurrent.futures import Future

import pytest

from chisurf.plugins.burst.burst_fusion.gui.controller import FusionController
from chisurf.plugins.burst.burst_fusion.gui.view_model import FusionViewModel

MEASURED = {
    "detectors": {
        "green": {"chs": [8, 0, 3], "micro_time_ranges": [[0, 2048]]},
        "red": {"chs": [9, 1, 2], "micro_time_ranges": [[2048, 4095]]},
    },
    "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
}


@pytest.fixture
def controller():
    """A real model/controller seeded with an applied measured definition."""
    model = FusionViewModel()
    model.detectors = copy.deepcopy(MEASURED["detectors"])
    model.windows = copy.deepcopy(MEASURED["windows"])
    controller = FusionController(model)
    yield controller
    controller.close()


def _publish(controller, action, definition=None, error=None):
    """Exercise the real publication path independently of fitting or writing."""
    snapshot = copy.copy(controller.model)
    if definition is not None:
        snapshot.detectors = copy.deepcopy(definition["detectors"])
        snapshot.windows = copy.deepcopy(definition["windows"])
    snapshot._observers = []
    snapshot._written = "written-folder" if action == "fuse" else ""
    future = Future()
    if error is None:
        future.set_result(snapshot)
    else:
        future.set_exception(error)
    controller._future = future
    controller._action = action
    controller.running = True
    controller.poll()


def test_actual_demo_worker_replaces_measured_definition_and_apply_uses_demo(controller):
    """The shipped demo changes authoritative routing and its editable draft together."""
    controller.demo()
    controller._future.result(timeout=60)
    controller.poll()
    definition = {"detectors": controller.model.detectors, "windows": controller.model.windows}
    assert definition["detectors"]["green"]["chs"] == [0]
    assert definition["detectors"]["red"]["chs"] == [1]
    assert definition["windows"] == {}
    assert json.loads(controller.channel_text) == definition
    controller.apply_channels(controller.channel_text)
    assert controller.model.detectors == definition["detectors"]
    assert controller.model.windows == definition["windows"]


@pytest.mark.parametrize("action", ["estimate", "fuse"])
def test_successful_publication_refreshes_replaced_definition_before_notification(
    controller, action
):
    """Routing unchanged but new microtime gates/windows still replace the draft."""
    replacement = copy.deepcopy(MEASURED)
    replacement["detectors"]["green"]["micro_time_ranges"] = [[100, 400]]
    replacement["windows"] = {"prompt": [100, 400]}
    observed = []
    controller.model.add_observer(
        lambda event: observed.append(json.loads(controller.channel_text))
    )
    _publish(controller, action, replacement)
    assert json.loads(controller.channel_text) == replacement
    assert observed == [replacement]


@pytest.mark.parametrize("action", ["estimate", "fuse"])
def test_unchanged_publication_preserves_deliberate_unapplied_draft(controller, action):
    """Ordinary result delivery must not erase an edit that has not been applied."""
    draft = copy.deepcopy(MEASURED)
    draft["detectors"]["green"]["chs"] = [7]
    controller.channel_text = json.dumps(draft)
    _publish(controller, action, MEASURED)
    assert json.loads(controller.channel_text) == draft
    assert controller.model.detectors == MEASURED["detectors"]


def test_failed_publication_keeps_model_and_unapplied_draft(controller):
    """A failed worker cannot publish or rewrite detector edits."""
    controller.channel_text = "unfinished draft"
    _publish(controller, "demo", error=RuntimeError("worker failed"))
    assert controller.channel_text == "unfinished draft"
    assert controller.model.detectors == MEASURED["detectors"]
    assert controller.model.windows == MEASURED["windows"]
    assert controller.status == "Error: worker failed"


def test_cancelled_publication_keeps_model_and_unapplied_draft(controller):
    """Cancellation before publication leaves the existing definitions intact."""
    controller.channel_text = "unfinished draft"
    controller._cancel.set()
    _publish(controller, "demo", {"detectors": {"green": {"chs": [0]}}, "windows": {}})
    assert controller.channel_text == "unfinished draft"
    assert controller.model.detectors == MEASURED["detectors"]


def test_explicit_load_and_apply_remain_authoritative(controller, tmp_path):
    """Loading settings and pressing Apply adopt the exact entered definition."""
    data = controller.model.settings.to_dict()
    data.update(detectors={"green": {"chs": [4]}}, windows={"new": [10, 20]})
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data))
    controller.channel_text = "unapplied older draft"
    controller.load_settings(path)
    assert controller.model.detectors == data["detectors"]
    assert controller.model.windows == data["windows"]
    assert json.loads(controller.channel_text) == data
    applied = {"detectors": {"red": {"chs": [6]}}, "windows": {}}
    controller.apply_channels(json.dumps(applied))
    assert controller.model.detectors == applied["detectors"]
    assert json.loads(controller.channel_text) == applied


def test_rejected_apply_keeps_authoritative_model_and_draft(controller):
    """Invalid routing cannot partially replace a working definition."""
    invalid = json.dumps({"detectors": {"green": {"chs": [-1]}}, "windows": {}})
    controller.channel_text = invalid
    with pytest.raises(ValueError):
        controller.apply_channels(controller.channel_text)
    assert controller.model.detectors == MEASURED["detectors"]
    assert controller.channel_text == invalid
