import copy
import sys

import pytest
from emtk.app import ImApp
from emtk.testing import RecordingPainter

from chisurf.emtk.validation import BlockQt
from chisurf.plugins.microscopy.imaging_tools.gui.app import PANELS, ImagingToolsApp


class Client:
    def __init__(self):
        self.setup = {}

    def get_current(self):
        return self.setup

    def set_current(self, setup):
        self.setup = copy.deepcopy(setup)


class Child(ImApp):
    def __init__(self, coordinator=None, **kwargs):
        self.coordinator = coordinator
        self.received = {}
        self.value = 3
        super().__init__(lambda: None)

    def apply_setup_settings(self, payload):
        self.received["setup"] = payload

    def apply_pipeline_context(self, payload):
        self.received["pipeline"] = payload

    def apply_calibration(self, payload):
        self.received["calibration"] = payload

    def export_settings(self):
        return {"value": self.value}

    def restore_settings(self, data):
        self.value = data["value"]


def test_lazy_context_navigation_snapshot_and_state():
    app = ImagingToolsApp(client=Client(), factories={"pixel_intensity": Child, "pixel_nb": Child})
    app.set_setup({"detectors": {"green": {"chs": [0]}}})
    app.set_pipeline(source="image.ptu", hdf5="image.h5")
    calibration = {"green": {"bg_vv": 4}}
    app.set_calibration(calibration)
    assert not app.children
    assert app.goto_role("pixel_intensity")
    child = app.child
    assert child.coordinator is app
    assert child.received["pipeline"] == {"source": "image.ptu", "hdf5": "image.h5"}
    assert child.received["setup"] == app.setup
    calibration["green"]["bg_vv"] = 999
    assert child.received["calibration"]["green"]["bg_vv"] == 4
    child.value = 12
    app.advance_from("pixel_intensity")
    assert app.selected == "pixel_nb"
    app.previous_from("pixel_nb")
    assert app.child is child
    saved = app.export_settings()
    restored = ImagingToolsApp(
        client=Client(), factories={"pixel_intensity": Child, "pixel_nb": Child}
    )
    restored.restore_settings(saved)
    assert restored.child.value == 12
    assert restored.child.received == child.received
    assert not restored.goto_role("pixel_mle")
    assert "pending" in restored.error


@pytest.mark.parametrize("role", [row[0] for row in PANELS])
def test_all_native_children_render_without_qt(role):
    blocker = BlockQt()
    sys.meta_path.insert(0, blocker)
    app = ImagingToolsApp(client=Client())
    try:
        if app.factory(role) is None:
            assert not app.goto_role(role)
            assert "pending" in app.error
            return
        assert app.goto_role(role), app.error
        for width, height in ((1200, 800), (800, 600)):
            painter = RecordingPainter()
            for _ in range(2):
                app.draw(painter, 0, 0, width, height)
            assert painter.strings
        assert app.child._coordinator is app
        assert app.child._pipeline_role == role
    finally:
        app.close()
        sys.meta_path.remove(blocker)


@pytest.mark.parametrize(
    "role", ["pixel_intensity", "pixel_nb", "pixel_micro_time", "pixel_phasor", "calibration"]
)
def test_current_native_pipeline_receives_setup_source_hdf5_and_calibration(role, monkeypatch):
    import numpy as np

    from chisurf.core.fluorescence import imaging

    def fake_compute(filename, windows, kind, progress=None):
        return {
            "green": {
                "n_par": np.ones((4, 4)) * 10,
                "n_perp": np.ones((4, 4)),
                "durations": np.ones(4) * 0.01,
                "n_pixel": 4,
                "bg": 0.0,
                "frames": np.ones((3, 4, 4)),
            }
        }

    monkeypatch.setattr(imaging, "compute_windows", fake_compute)
    app = ImagingToolsApp(client=Client())
    try:
        assert app.goto_role(role), app.error
        child = app.child
        app.set_setup(
            {
                "detectors": {
                    "green": {
                        "chs": [0, 1],
                        "ch_p": [0],
                        "ch_s": [1],
                        "micro_time_ranges": [[0, 4095]],
                    }
                }
            }
        )
        app.set_pipeline(source="selected.ptu", hdf5="shared.imaging.h5")
        app.set_calibration({"green": {"bg_vv": 2.0, "bg_vh": 3.0}})
        job = getattr(child, "job", None)
        if job and job.thread:
            job.thread.join(5)
            job.poll()
            # Pending context updates are deliberately applied by the child render.
            child.draw(RecordingPainter(), 0, 0, 950, 650)
        assert "green" in child.model.detectors
        assert child.model.filename == "selected.ptu"
        if role != "calibration":
            assert child.model.pipeline_hdf5 == "shared.imaging.h5"
            assert child.model.pipeline_sink == app.set_pipeline
        else:
            assert child.model.publish == app.set_calibration
    finally:
        # This test uses an in-memory numerical stub, never persist it as real data.
        for child in app.children.values():
            child.model.flush_to_hdf5 = lambda: None
        app.close()


@pytest.mark.parametrize("locale", ["en", "de", "fr", "es", "pt", "ru"])
def test_existing_catalog_locales_render_native_hub(locale):
    from chisurf.emtk.i18n import install, set_locale
    from chisurf.plugins.microscopy.imaging_tools.gui.app import label

    install(locale)
    app = ImagingToolsApp(client=Client(), factories={"browser": Child})
    try:
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 800, 600)
        assert painter.strings
        assert label("Setup")
    finally:
        app.close()
        set_locale("en")
