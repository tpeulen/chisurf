"""Native batch detection, ROI state, Gaussian picks and hard Qt blockers."""

import os
import subprocess
import sys

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.microscopy.psf_determination.tests.test_native_app import finish


def field():
    y, x = np.indices((48, 56))
    image = np.full((48, 56), 2.0, dtype=float)
    for cy, cx in [(12, 14), (32, 39)]:
        image += 200 * np.exp(-0.5 * (((y - cy) / 1.6) ** 2 + ((x - cx) / 1.6) ** 2))
    return image


def write_field(path):
    from chisurf.core.fio.image import imwrite
    from chisurf.core.fio.pto import Measurement

    imwrite(path, field().astype(np.uint16), axes="YX")
    with Measurement.create(path, artifact_kind="image_data"):
        pass
    return str(path)


def test_populated_native_frame_without_qt():
    code = """
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden: '+fullname)
sys.meta_path.insert(0,BlockQt())
import numpy as np
from emtk.testing import RecordingPainter
from chisurf.plugins.microscopy.spot_finder.gui.app import make_app
from chisurf.plugins.microscopy.spot_finder.core.spots import detect,SpotFinderSettings
app=make_app()
y,x=np.indices((48,56))
image=2+200*np.exp(-.5*(((y-12)/1.6)**2+((x-14)/1.6)**2))
app.model.results=[detect(image,SpotFinderSettings(method='threshold',threshold=20,clear_border=False))]
app.regions.add_shape('rectangle')
for size in [(900,650),(1200,800)]:
    class ImageRecorder(RecordingPainter):
        def image(self,*args):self.calls.append(('image',args))
    painter=ImageRecorder()
    app.draw(painter,0,0,*size)
    assert any(call[0] == "image" for call in painter.calls)
    assert 'Preview' in painter.strings
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, env=os.environ.copy()
    )
    assert result.returncode == 0, result.stderr


def test_background_preview_roi_export_and_failure_rows(tmp_path):
    from chisurf.core.fio.fluorescence.region_container import list_region_sets
    from chisurf.core.roi import RectangleROI
    from chisurf.plugins.microscopy.spot_finder.gui.app import make_app

    good = write_field(tmp_path / "field.tif")
    broken = tmp_path / "broken.tif"
    broken.write_bytes(b"not a TIFF")
    app = make_app()
    app.open_paths([good, str(broken)])
    app.model.settings.method = "threshold"
    app.model.settings.threshold = 20
    app.model.settings.clear_border = False
    app.model.regions.add(RectangleROI(5, 5, 23, 22))
    app.model.apply_regions()
    assert app.start("preview")
    finish(app)
    assert app.model.results[0].n_regions == 1
    assert not list_region_sets(good), "Preview wrote detection results"
    app.model.regions.clear()
    app.model.apply_regions()
    app.model.write_results = False
    assert app.start("run")
    finish(app)
    assert len(app.model.run_rows) == 2
    assert [r.status for r in app.model.run_rows] == ["ok", "failed"]
    output = tmp_path / "regions.csv"
    assert app.start("export_results", str(output))
    finish(app)
    assert output.exists()
    assert len(output.read_text().splitlines()) == 3
    app.draw(RecordingPainter(), 0, 0, 1200, 800)


def test_real_pointer_picks_and_addition_preserve_snapshot_boundary():
    from emtk.app import LEFT_BUTTON

    from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings, detect
    from chisurf.plugins.microscopy.spot_finder.gui.app import make_app

    app = make_app()
    # A threshold that finds no pixels still provides an intensity image to inspect.
    result = detect(
        field(), SpotFinderSettings(method="threshold", threshold=1000, clear_border=False)
    )
    app.model.results = [result]
    app.draw(RecordingPainter(), 0, 0, 1200, 900)
    x, y = app.canvas.pick_pixels(14, 12)
    app.pointer_press(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 900)
    assert app.job.busy
    finish(app)
    assert len(app.model.picked) == 1
    assert app.model.picked[0].x == pytest.approx(14, abs=0.2)
    app.pointer_release(x, y, LEFT_BUTTON)
    count = result.n_regions
    app.start("add_picked_to_detection")
    app.job.thread.join(timeout=20)
    assert result.n_regions == count, "worker mutated the displayed detection object"
    app.job.poll()
    assert app.model.results[0].n_regions == 1
    assert not app.model.picked


def test_region_geometry_persistence_and_recipe_state(tmp_path):
    from chisurf.plugins.microscopy.spot_finder.gui.app import make_app

    app = make_app()
    app.regions.add_shape("ellipse")
    app.regions.duplicate()
    assert len(app.model.regions) == 2
    app.model.regions.combine = "or"
    app.model.regions[0].invert = True
    path = tmp_path / "rois.json"
    app.regions.save(path)
    app.regions.load(path)
    assert len(app.model.regions) == 4
    state = app.state_dict()
    app.model.workflow = "camera_spots"
    assert app.model.method == "log"
    app.apply_state(state)
    assert app.model.workflow == state["settings"]["workflow"]
    assert len(app.model.regions) == 4
    assert app.model.regions[0].invert
    assert app.on_files_dropped(["first.tif", "first.tif"])
    assert app.model.files == ["first.tif"]


def test_dragging_analysis_roi_does_not_pick_a_spot():
    from emtk.app import LEFT_BUTTON

    from chisurf.core.roi import RectangleROI
    from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings, detect
    from chisurf.plugins.microscopy.spot_finder.gui.app import make_app

    app = make_app()
    app.model.results = [
        detect(field(), SpotFinderSettings(method="threshold", threshold=20, clear_border=False))
    ]
    name = app.model.regions.add(RectangleROI(5, 5, 23, 23, name="Search"))
    app.model.apply_regions()
    app.draw(RecordingPainter(), 0, 0, 1200, 900)
    center = app.canvas.pick_pixels(14, 14)
    moved = app.canvas.pick_pixels(18, 16)
    app.pointer_press(*center, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 900)
    assert not app.job.busy
    app.pointer_move(*moved, buttons=LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 900)
    app.pointer_release(*moved, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 900)
    assert app.model.regions[name].roi.x0 > 5
    assert not app.model.picked


def test_real_photon_demo_and_preview_without_qt(tmp_path):
    code = """
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden: '+fullname)
sys.meta_path.insert(0,BlockQt())
from pathlib import Path
from chisurf.plugins.microscopy.spot_finder import demo
from chisurf.plugins.microscopy.spot_finder.gui.app import make_app
original=demo.create_demo
demo.create_demo=lambda:original(directory=Path(sys.argv[1]))
app=make_app()
assert app.start('load_demo')
app.job.thread.join(timeout=30)
assert not app.job.thread.is_alive(),'demo timed out'
app.job.poll()
assert not app.job.error,app.job.error
assert len(app.model.files)==1 and app.model.files[0].endswith('.ptu')
assert app.start('preview')
app.job.thread.join(timeout=30)
assert not app.job.thread.is_alive(),'preview timed out'
app.job.poll()
assert not app.job.error,app.job.error
assert app.model.results,app.model.status_text
assert app.model.results[0].n_regions==4,app.model.status_text
assert app.start('run')
app.job.thread.join(timeout=30)
assert not app.job.thread.is_alive(),'write timed out'
app.job.poll()
assert not app.job.error,app.job.error
assert app.model.run_rows[0].status=='ok',app.model.run_rows[0].reason
from chisurf.core.fio.fluorescence.region_container import read_regions,list_region_sets
assert list_region_sets(app.model.files[0])==['spots']
assert int(read_regions(app.model.files[0]).labels.max())==4
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=100,
    )
    assert result.returncode == 0, result.stderr


def test_pipeline_updates_are_not_lost_to_background_delivery():
    import threading

    from chisurf.plugins.microscopy.spot_finder.gui.app import make_app
    from chisurf.plugins.microscopy.spot_finder.gui.view_model import SpotFinderViewModel

    class SlowPreview(SpotFinderViewModel):
        def __init__(self):
            super().__init__()
            self.files = ["old.tif"]
            self.started = threading.Event()
            self.proceed = threading.Event()

        def preview(self):
            self.started.set()
            assert self.proceed.wait(5)
            self.status_text = "Preview finished."

    model = SlowPreview()
    app = make_app(model=model)
    app.start("preview")
    assert model.started.wait(5)
    app.apply_pipeline_context({"files": ["new.tif"]})
    assert model.files == ["old.tif"]
    model.proceed.set()
    finish(app)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert model.files == ["new.tif"]
