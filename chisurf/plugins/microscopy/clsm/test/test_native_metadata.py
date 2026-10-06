"""Physical timing and photon conservation for native reconstruction."""

import numpy as np

from chisurf.core.fluorescence.imaging.simulate import (
    clsm_from_scan,
    simulate_molecule_mixture,
    write_mixture_ptu,
)
from chisurf.plugins.microscopy.clsm.core.imaging import decay_of_selection, representation


def test_simulated_ptu_preserves_timing_and_photons(tmp_path):
    import tttrlib

    sim = simulate_molecule_mixture(
        [{"ix": 2, "iy": 2, "tau": 2.5}], n_pixel=4, n_micro=128, dt=0.064, dwell=0.12, seed=3
    )
    path = write_mixture_ptu(sim, tmp_path / "scan.ptu")
    data = tttrlib.TTTR(path, "PTU")
    import json

    tags = json.loads(data.header.json)["tags"]
    actual = [t for t in tags if t["name"] == "MeasDesc_NumberMicrotimes" and t["idx"] == -1]
    assert len(actual) == 1 and actual[0]["value"] == 128
    assert data.header.number_of_micro_time_channels == 128
    assert np.isclose(data.header.micro_time_resolution, 0.064e-9)
    assert np.isclose(data.header.macro_time_resolution, 0.01)
    np.testing.assert_array_equal(data.micro_times, sim.tttr.micro_times)
    image = clsm_from_scan(data, n_pixel=4, channels=[0, 1])
    counts = representation(image, data)
    _, decay, _ = decay_of_selection(image, data, np.ones((4, 4)), trim_trailing_zeros=False)
    assert counts.sum() > 0
    assert decay.sum() == counts.sum()


def test_intensity_uses_wide_counter():
    class Image:
        intensity = np.array([[[1]]], dtype=np.uint16)

        def get_intensity_u32(self):
            return np.array([[[65537]]], dtype=np.uint32)

    assert representation(Image(), None).item() == 65537


def test_populated_factories_forbid_qt():
    import os
    import subprocess
    import sys

    code = """
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}: raise ImportError('Qt forbidden '+fullname)
sys.meta_path.insert(0,BlockQt())
import numpy as np
from emtk.testing import RecordingPainter
from chisurf.plugins.microscopy.clsm.gui.app import make_app as clsm
from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app as browser
c=clsm();c.model.current_image=np.arange(48*48).reshape(48,48);c.model.selection_mask=np.zeros((48,48));c.model.current_decay={'time_ns':np.arange(10),'counts':np.arange(10)+1,'noise':np.ones(10)}
b=browser();b.page=1;b.pending_page=1;b.model.current_file='/tmp/scan.ptu';b.model._mosaic_cache[b.model.current_file]={'mosaic':np.arange(48*48,dtype=np.uint8).reshape(48,48),'labels':['Image'],'cols':1,'rows':1}
for app in [c,b]:
    for size in [(900,650),(1200,800)]:
        p=RecordingPainter();app.draw(p,0,0,*size)
        assert p.strings
assert 'qtpy' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", code], env=os.environ.copy(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_clsm_and_browser_real_scan_workflows(tmp_path):
    import json

    from chisurf.plugins.microscopy.clsm.gui.view_model import ClsmViewModel
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import (
        ImageBrowserModel as NativeBrowserModel,
    )

    sim = simulate_molecule_mixture([{"ix": 2, "iy": 2, "tau": 2.5}], n_pixel=4, seed=3)
    path = tmp_path / "sample.ptu"
    write_mixture_ptu(sim, path)
    path.with_suffix(".json").write_text(
        json.dumps({"scan_layout": {"kind": "chisurf-simulated-raster", "n_pixel_per_line": 4}})
    )
    model = ClsmViewModel()
    model.load_tttr(str(path))
    model.setup.channels_text = "0,1"
    model.add_clsm()
    model.add_representation()
    assert model.current_image.shape == (4, 4)
    model.selection_mask[:] = 1
    assert model.recompute_decay()["counts"].sum() == model.current_image.sum()
    model.add_decay_curve("all photons")
    assert len(model.curves) == 1
    model.clear_selection()
    assert model.current_decay is None
    model.load_tttr(str(path))
    assert not model.representations and not model.curves
    browser = NativeBrowserModel()
    browser.open_folder(str(tmp_path))
    browser.select_file(str(path))
    browser.load_current()  # the app loads on a worker; headless use loads now
    assert browser.current_image().shape == (4, 4)
    browser.set_rating(str(path), 3)
    browser.set_note(str(path), "calibration bead")
    reloaded = NativeBrowserModel()
    reloaded.open_folder(str(tmp_path))
    assert reloaded.rating_of(str(path)) == 3
    assert reloaded.note_of(str(path)) == "calibration bead"
    browser.do_copy_files(str(tmp_path / "copies"))
    assert (tmp_path / "copies" / path.name).read_bytes() == path.read_bytes()
    browser.do_export_tiff(str(tmp_path / "tiffs"))
    assert list((tmp_path / "tiffs").rglob("*.tif")) or list((tmp_path / "tiffs").rglob("*.tiff"))
    browser.do_export_docx(str(tmp_path / "report.docx"))
    assert (tmp_path / "report.docx").stat().st_size > 1000
    from xml.etree.ElementTree import fromstring
    from zipfile import ZipFile

    with ZipFile(tmp_path / "report.docx") as archive:
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                fromstring(archive.read(name))
        assert "word/media/image1.png" in archive.namelist()


def test_native_pointer_brush_selects_pixels():
    from emtk.app import LEFT_BUTTON
    from emtk.testing import RecordingPainter

    from chisurf.plugins.microscopy.clsm.gui.app import make_app

    app = make_app()
    app.model.current_image = np.ones((48, 48))
    app.model.selection_mask = np.zeros((48, 48))
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    x, y = app.canvas.pick_pixels(20, 20)
    app.pointer_press(x, y, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    app.pointer_release(x, y, LEFT_BUTTON)
    assert app.model.selection_mask[20, 20] > 0
    assert app.selection_version > 0
    app.close()
