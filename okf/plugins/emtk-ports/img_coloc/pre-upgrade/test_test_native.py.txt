"""Scientific and lifecycle parity for native colocalization."""
import json
import threading
import time

import numpy as np
import pytest

from chisurf.core.fio.image import imwrite
from chisurf.core.roi import EllipseROI
from chisurf.plugins.microscopy.img_coloc.gui.app import make_app
from chisurf.plugins.microscopy.img_coloc.gui.view_model import ColocViewModel


@pytest.fixture
def image_file(tmp_path):
    y, x = np.mgrid[:64, :64]
    a = 100 * np.exp(-((x-20)**2+(y-25)**2)/25) + 80 * np.exp(-((x-45)**2+(y-42)**2)/25)
    b = np.roll(a, (1, 2), axis=(0,1)) * .7 + 2
    path = tmp_path / "two.tif"
    imwrite(str(path), np.stack([a,b]).astype(np.float32), axes="CYX")
    return path


def wait(app):
    deadline = time.monotonic()+20
    while app.busy and time.monotonic() < deadline:
        app.poll()
        time.sleep(.01)
    assert not app.busy
    assert not app.error


def test_native_matches_qt_model_for_every_result(image_file, tmp_path):
    model = ColocViewModel()
    model.set_filename(str(image_file))
    model.object_analysis = True
    model.costes_test = True
    model.costes_randomizations = 12
    model.ccf_max_shift = 5
    model.gate_enabled = True
    model.gates.add(EllipseROI(40,30,40,30,name="population"))
    model.roi_mask = np.zeros((64,64))
    model.roi_mask[5:60,5:60] = 1
    reference = ColocViewModel()
    reference.__dict__.update(model.__dict__)
    assert reference.compute()
    app = make_app(model=model)
    assert app.start()
    wait(app)
    for key, value in reference._metrics.items():
        if isinstance(value, float):
            assert app.model._metrics[key] == pytest.approx(value, nan_ok=True)
        else:
            assert app.model._metrics[key] == value
    for method in ("image_a", "image_b", "coloc_mask_image", "histogram_image", "ccf_map_image", "object_map_image"):
        np.testing.assert_array_equal(getattr(reference,method)(),getattr(app.model,method)())
    assert app.model.profile_series() and app.model.ccf_series() and app.model.object_distance_series()
    csv = tmp_path / "result.csv"
    app.handle_path("csv", str(csv))
    assert "costes_p_value" in csv.read_text()
    settings = json.loads(json.dumps(app.export_settings()))
    restored = make_app()
    restored.restore_settings(settings)
    wait(restored)
    assert restored.model.gates.to_dict() == model.gates.to_dict()
    np.testing.assert_array_equal(restored.model.roi_mask, model.roi_mask)
    assert restored.model._metrics["pearson"] == pytest.approx(model._metrics["pearson"])
    app.close()
    restored.close()


def test_cancel_discards_late_worker_and_isolates_masks(image_file, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = ColocViewModel.compute
    def blocked(self, *args, **kwargs):
        entered.set()
        release.wait(5)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(ColocViewModel,"compute",blocked)
    app = make_app()
    app.model.set_filename(str(image_file))
    app.model.roi_mask = np.ones((64,64))
    assert app.start()
    assert entered.wait(2)
    app.model.roi_mask[:] = 0
    app.cancel()
    release.set()
    app._thread.join(5)
    app.poll()
    assert app.model._result is None
    assert not app.busy
    assert not app.model.roi_mask.any()


def test_gate_shapes_use_intensity_coordinates(image_file):
    app = make_app()
    app.open_paths([str(image_file)])
    wait(app)
    a0,a1,b0,b1 = app.model.gate_extent()
    for kind in ("rectangle", "ellipse", "polygon"):
        name = app.gate_controls.add_shape(kind)
        wait(app)
        bounds = app.model.gates.roi(name).bounds()
        assert a0 <= bounds[0] < bounds[2] <= a1
        assert b0 <= bounds[1] < bounds[3] <= b1
    assert app.model.gate_enabled
    assert app.model._metrics["n_pixels_gated"] > 0


def test_populated_views_render_without_errors(image_file, caplog):
    from emtk.testing import RecordingPainter
    app = make_app()
    app.model.ccf_max_shift = 5
    app.model.object_analysis = True
    app.open_paths([str(image_file)])
    wait(app)
    for width,height in ((1200,800),(800,600)):
        for key in ("coefficients","channels","scatter","mask","ccf","ccf2d","profiles","objects","distances"):
            app.docks.focus(key)
            painter = RecordingPainter()
            app.draw(painter,0,0,width,height)
            assert painter.strings
    assert not [record for record in caplog.records if record.levelno >= 40]


def test_painted_roi_and_gate_drive_coefficients(image_file):
    from emtk.testing import RecordingPainter
    app = make_app()
    app.open_paths([str(image_file)])
    wait(app)
    app.paint("roi_mask", (0,25,20))
    app.draw(RecordingPainter(),0,0,1200,800)
    wait(app)
    assert app.model._metrics["n_pixels_total"] == app.model.brush_size**2
    app.paint_gate = True
    app.paint("gate_paint", (0,32,32))
    app.draw(RecordingPainter(),0,0,1200,800)
    wait(app)
    assert app.model.gates.get("painted") is not None
    assert app.model.gate_enabled
    assert app.model._metrics["n_pixels_gated"] <= app.model._metrics["n_pixels_total"]


def test_existing_catalogs_translate_all_six_locales(image_file):
    from emtk import i18n
    from emtk.testing import RecordingPainter

    from chisurf.emtk.i18n import SUPPORTED_LOCALES
    app = make_app()
    app.open_paths([str(image_file)])
    wait(app)
    old = i18n.get_locale()
    try:
        for locale in SUPPORTED_LOCALES:
            i18n.set_locale(locale)
            painter = RecordingPainter()
            app.draw(painter,0,0,1200,800)
            assert painter.strings
            if locale != "en":
                assert i18n.tr("Channel A") != "Channel A"
    finally:
        i18n.set_locale(old)


def test_native_authored_labels_and_tooltips_have_catalogs_for_every_locale():
    from emtk import i18n

    from chisurf.plugins.microscopy.img_coloc.gui.native_i18n import ROWS
    app = make_app()
    old = i18n.get_locale()
    try:
        for locale in ("de", "fr", "es", "pt", "ru"):
            i18n.set_locale(locale)
            for row in ROWS:
                assert i18n.tr(row[0]) != row[0], (locale,row[0])
    finally:
        i18n.set_locale(old)
        app.close()
