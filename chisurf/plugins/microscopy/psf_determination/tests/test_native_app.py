"""Populated native PSF rendering, actual picks and snapshot background delivery."""

import os
import subprocess
import sys

import numpy as np
import pytest
from emtk.testing import RecordingPainter


def bead_stack():
    z, y, x = np.indices((21, 40, 40))
    return (
        5
        + 1000
        * np.exp(-0.5 * (((x - 20) / 2.0) ** 2 + ((y - 20) / 2.0) ** 2 + ((z - 10) / 3.0) ** 2))
    ).astype(np.float32)


def finish(app):
    app.job.thread.join(timeout=20)
    assert not app.job.thread.is_alive()
    app.job.poll()
    assert not app.job.busy
    assert not app.job.error, app.job.error


def test_populated_native_frame_without_qt():
    code = """
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden: '+fullname)
sys.meta_path.insert(0,BlockQt())
import numpy as np
from emtk.testing import RecordingPainter
from chisurf.plugins.microscopy.psf_determination.gui.app import make_app
app=make_app()
z,y,x=np.indices((21,40,40))
app.model.set_stack((5+1000*np.exp(-.5*(((x-20)/2)**2+((y-20)/2)**2+((z-10)/3)**2))).astype(np.float32))
app.model.selected_bead=(10,20,20)
assert app.model.fit_selected()['success']
app.canvas.z=10
for size in [(900,650),(1200,800)]:
    class ImageRecorder(RecordingPainter):
        def image(self,*args):self.calls.append(('image',args))
    painter=ImageRecorder()
    app.draw(painter,0,0,*size)
    assert any(call[0] == "image" for call in painter.calls)
    assert 'Load stack' in painter.strings
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, env=os.environ.copy()
    )
    assert result.returncode == 0, result.stderr


def test_pointer_pick_runs_fit_without_mutating_display_before_delivery():
    from emtk.app import LEFT_BUTTON

    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    app.model.set_stack(bead_stack())
    app.canvas.z = 10
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    x, y = app.canvas.pick_pixels(20, 20)
    app.pointer_press(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert app.model.selected_bead == (10, 20, 20)
    assert app.job.busy
    app.job.thread.join(timeout=20)
    assert app.model._fit_roi is None, "worker wrote to the displayed model"
    app.pointer_release(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert not app.job.busy
    assert app.model._fit_params is not None
    assert app.model.fit_circle()["r"] == pytest.approx(2.355, rel=0.03)


def test_detection_batch_profiles_export_and_settings(tmp_path):
    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    app.model.set_stack(bead_stack())
    assert app.start("detect_beads")
    finish(app)
    assert app.model.detected_beads
    assert app.start("fit_all")
    finish(app)
    assert "Batch PSF fits" in app.model.results_text
    path = tmp_path / "psf.csv"
    assert app.start("export_csv", str(path))
    finish(app)
    assert "fwhm_xy_nm" in path.read_text()
    app.model.selected_bead = (10, 20, 20)
    assert app.start("fit_selected")
    finish(app)
    assert len(app.model.x_profile_series()) == 2
    state = app.settings()
    app.model.pixel_size_nm = 999
    app.apply_settings(state)
    assert app.model.pixel_size_nm == state["pixel_size_nm"]
    assert not app.canvas.pick(-10, 5, bead_stack().shape, app.pick_bead)


def test_loader_reads_real_tiff_on_background_job(tmp_path):
    from chisurf.core.fio.image import imwrite
    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    path = tmp_path / "beads.tif"
    imwrite(path, bead_stack(), axes="ZYX")
    app = make_app()
    app.open_paths([path])
    finish(app)
    assert app.model.stack.shape == (21, 40, 40)
    assert app.model.filename == str(path)


def test_texture_orientation_matches_picking_coordinates():
    from emtk.pil_painter import PilPainter

    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    stack = np.zeros((1, 10, 10), dtype=np.float32)
    stack[0, 2, 3] = 100
    app.model.set_stack(stack)
    app.canvas.colormap = "gray"
    painter = PilPainter(900, 700)
    app.draw(painter, 0, 0, 900, 700)
    bright = app.canvas.pick_pixels(3, 2)
    mirrored = app.canvas.pick_pixels(3, 7)

    def red(point):
        return painter.frame.getpixel(tuple(round(v) for v in point))[0]

    origin = app.canvas.pick_pixels(0, 0)
    unit = app.canvas.pick_pixels(1, 1)
    assert abs(unit[0] - origin[0]) == pytest.approx(abs(unit[1] - origin[1]))
    assert red(bright) > 200
    assert red(mirrored) < 50


def test_job_delivers_original_events_on_the_ui_thread():
    import threading

    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    app.model.set_stack(bead_stack())
    events = []
    app.model.add_observer(lambda event: events.append((event, threading.get_ident())))
    app.start("detect_beads")
    finish(app)
    assert ("beads", threading.get_ident()) in events
    assert all(thread == threading.get_ident() for _, thread in events)


def test_all_profile_tabs_share_the_header_row():
    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 1200, 800)
    y_by_label = {}
    for call in painter.calls:
        if call[0] == "text" and call[6] in ("x profile", "y profile", "z profile"):
            y_by_label.setdefault(call[6], call[2])
    assert len(y_by_label) == 3
    assert len(set(y_by_label.values())) == 1


def test_native_save_settings_dialog_accepts_real_pointer_input(tmp_path):
    import json

    from emtk.app import LEFT_BUTTON

    from chisurf.plugins.microscopy.psf_determination.gui.app import make_app

    app = make_app()
    app.choose("save_settings")
    app.dialog.directory = str(tmp_path)
    app.dialog.filename = "psf-state.json"
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 1200, 800)
    save = next(call for call in reversed(painter.calls) if call[0] == "text" and call[6] == "Save")
    x, y = save[1] + save[3] / 2, save[2] + save[4] / 2
    app.pointer_press(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    app.pointer_release(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    path = tmp_path / "psf-state.json"
    assert path.exists(), app.error
    assert json.loads(path.read_text())["pixel_size_nm"] == 100
    assert app.dialog is None
