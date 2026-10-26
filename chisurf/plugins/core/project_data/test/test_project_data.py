"""The Project data window, driven with real pointer input on its demonstration project.

Load example writes a project whose third linked file was moved to a backup folder (a decoy of
the same name sits elsewhere); the window finds it missing, a folder search proposes the right file
first, its checksum is confirmed, the project is made self-contained and saved, and it then needs
no other file. Every tour target is a drawn control. The window is rendered for inspection.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from emtk.testing import Driver

from chisurf.core.project.link_repair import LinkRepairModel, ProjectFileSource
from chisurf.plugins.core.project_data.gui.app import ProjectDataApp, receive

HERE = Path(__file__).resolve().parents[1]
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))


def _click(driver: Driver, app: ProjectDataApp, name: str) -> None:
    driver.frame(2)
    x, y, w, h = app.form.rects[name]
    driver.click((x + w / 2, y + h / 2))
    driver.frame(2)


def _settle(driver: Driver, app: ProjectDataApp, timeout: float = 30.0) -> None:
    end = time.monotonic() + timeout
    driver.frame(1)
    while app.model.busy and time.monotonic() < end:
        time.sleep(0.02)
        driver.frame(1)
    driver.frame(2)
    assert not app.model.busy


def test_the_demo_is_located_made_self_contained_and_saved(tmp_path, monkeypatch):
    monkeypatch.setattr("chisurf.plugins.core.project_data.gui.app.session_source", lambda: None)
    app = ProjectDataApp()
    driver = Driver(app, (980, 700))
    _click(driver, app, "load_example")
    model = app.model
    assert isinstance(model.source, ProjectFileSource)
    assert [r["name"] for r in model.unresolved] == ["c"]
    assert model.selected["name"] == "c" and model.enabled("request_search")
    project = model.source.path
    backup = project.parent.parent / "backup"
    app._start({"search": lambda: model.search(backup)})  # what the folder dialog's answer does
    _settle(driver, app)
    assert model.candidates[0]["match"] == "same size" and len(model.candidates) == 2
    driver.screenshot(SHOTS / "project_data_located.png")
    _click(driver, app, "use_candidate")
    assert not model.unresolved
    _click(driver, app, "make_self_contained")
    _settle(driver, app)
    assert model.self_contained
    _click(driver, app, "save_project")
    assert not model.enabled("save_project")  # saved: nothing left to write
    for path in (project.parent / "data").iterdir():
        path.unlink()
    for path in backup.rglob("*.tif"):
        path.unlink()
    reopened = LinkRepairModel(ProjectFileSource(project))
    reopened.refresh()
    assert reopened.self_contained and not reopened.unresolved
    driver.screenshot(SHOTS / "project_data_self_contained.png")


def test_every_tour_target_is_a_drawn_control(monkeypatch):
    monkeypatch.setattr("chisurf.plugins.core.project_data.gui.app.session_source", lambda: None)
    app = ProjectDataApp()
    driver = Driver(app, (980, 700))
    driver.frame(3)
    steps = json.loads((HERE / "gui" / "guide.json").read_text(encoding="utf-8"))["steps"]
    targets = {s["target"]["name"] for s in steps if s.get("target")}
    drawn = set(app.form.rects) | set(app.item_rects)
    assert targets <= drawn, targets - drawn
    assert not app.tour.active  # the tour starts from Guide, never by itself
    x, y, w, h = app.item_rects["guide"]
    driver.click((x + w / 2, y + h / 2))
    driver.frame(2)
    assert app.tour.active


def test_a_hand_off_opens_on_the_mode_it_asks_for(monkeypatch):
    class _Source:
        def __init__(self):
            from chisurf.core.data import LinkedDataset

            self.datasets = [LinkedDataset(__file__, data_kind="image", name="here")]

        def linked_datasets(self):
            return self.datasets

        def project_path(self):
            return None

        def changed(self):
            pass

    source = _Source()
    monkeypatch.setattr("chisurf.plugins.core.project_data.gui.app.session_source", lambda: source)
    app = ProjectDataApp()
    receive(app, {"mode": "self_contained"})
    assert app.model.job == "self_contained"
    driver = Driver(app, (980, 700))
    _settle(driver, app)
    assert app.model.self_contained
