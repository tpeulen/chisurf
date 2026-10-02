"""Every control of the PSF calculator operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the text
a list entry or a button drew) reach the window; the assertions read the visible outcome (the model, the summary, the status line,
the dialogs, the exported files). The control -> test list is in ``okf/plugins/emtk-ports/psf_calculator/REPORT.md``. The Qt tool
had no file drops, so there is no drop test.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.calculator.psf_calculator.core import PSFModel
from chisurf.plugins.calculator.psf_calculator.gui.app import make_app

from .driving import BIG, SMALL, PSFDriver, hermetic_env


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def drv():
    app = make_app()
    app.model.nxy, app.model.nz = 24, 7  # a small grid keeps every recomputation short
    d = PSFDriver(app, BIG)
    d.settle()
    yield d
    app.close()
    app._executor.shutdown(wait=True)


def model(drv):
    return drv.app.model


def stepper(drv, name, direction):
    x, y, w, h = drv.rect(f"{name}.stepper")
    drv.click_at(x + w / 2, y + h * (0.25 if direction > 0 else 0.75))


def reference(**params):
    """The volume the model gives for *params* (nxy 24, nz 7 unless said otherwise), computed directly."""
    m = PSFModel()
    m.nxy, m.nz = 24, 7
    for k, v in params.items():
        setattr(m, k, v)
    m.compute()
    return m.volume


def pick(drv, field, label):
    drv.click(field)
    drv.click_text(label, last=True)


# -- the number fields --------------------------------------------------------------------------------------- #

FIELDS = {"na": (0.05, 1.7, 1.40, 0.05), "n_immersion": (1.0, 2.0, 1.518, 0.01), "wavelength_nm": (300.0, 1200.0, 520.0, 10.0),
          "angle_deg": (0.0, 180.0, 0.0, 5.0), "nxy": (16, 192, 24, 8), "nz": (3, 81, 7, 2), "pixel_size_nm": (1.0, 200.0, 30.0, 5.0),
          "z_step_nm": (5.0, 1000.0, 100.0, 25.0), "threshold": (0.0, 0.9, 0.02, 0.01), "gamma": (0.1, 3.0, 0.6, 0.1)}


@pytest.mark.parametrize("name", list(FIELDS))
def test_each_number_field_is_typed_clamped_and_stepped_by_its_arrows(drv, name):
    lo, hi, start, step = FIELDS[name]
    if name == "angle_deg":
        pick(drv, "polarization", "Linear at angle")  # the angle field only takes input for a linear state
    assert getattr(model(drv), name) == pytest.approx(start)
    stepper(drv, name, +1)
    assert getattr(model(drv), name) == pytest.approx(start + step)
    stepper(drv, name, -1)
    stepper(drv, name, -1)
    assert getattr(model(drv), name) == pytest.approx(max(start - step, lo))
    drv.type_into(name, str(hi * 10))
    assert getattr(model(drv), name) == pytest.approx(hi)  # the Qt maximum
    drv.type_into(name, "-5")
    assert getattr(model(drv), name) == pytest.approx(lo)  # the Qt minimum
    drv.type_into(name, "abc")
    assert getattr(model(drv), name) == pytest.approx(lo)  # garbage is ignored


def test_a_typed_value_recomputes_after_the_debounce_with_the_volume_the_model_gives(drv, monkeypatch):
    import time

    from chisurf.plugins.calculator.psf_calculator.gui import app as app_module

    monkeypatch.setattr(app_module, "DEBOUNCE", 30.0)  # a quiet period no slow frame can outlast
    drv.type_into("na", "1.2")
    drv.draw(3)
    assert model(drv).is_stale and model(drv).na == 1.2
    assert not drv.app.busy  # nothing has run: the edit waits for its quiet period
    drv.app.deadline = time.monotonic()  # the quiet period is over
    drv.settle()
    assert not model(drv).is_stale
    assert np.array_equal(model(drv).volume, reference(na=1.2))
    assert any("lateral FWHM" in s for s in drv.draw(2).strings)


def test_the_summary_follows_the_volume(drv):
    before = drv.app.panel.summary_lines()
    drv.type_into("wavelength_nm", "640")
    drv.settle()
    after = drv.app.panel.summary_lines()
    assert after != before and after in "\n".join(drv.draw(2).strings) or all(line in drv.draw(2).strings for line in after.splitlines())


# -- the choices, the radio and the toggle --------------------------------------------------------------------- #


def test_choosing_the_airy_model_greys_the_polarization_and_the_volume_is_the_airy_one(drv):
    assert drv.app.panel.enabled("polarization") and drv.app.panel.enabled("show_polarization")
    pick(drv, "model", "Airy (scalar, 2-D)")
    assert model(drv).model == "airy"
    assert not drv.app.panel.enabled("polarization") and not drv.app.panel.enabled("show_polarization")
    drv.click("polarization")  # greyed: the list does not open
    assert "Linear x" not in drv.draw(2).strings
    drv.settle()
    assert np.array_equal(model(drv).volume, reference(model="airy"))


def test_the_gaussian_model_and_back(drv):
    pick(drv, "model", "Gaussian")
    drv.settle()
    assert np.array_equal(model(drv).volume, reference(model="gaussian"))
    pick(drv, "model", "Vectorial (Richards-Wolf)")
    drv.settle()
    assert np.array_equal(model(drv).volume, reference())


def test_every_polarization_is_listed_and_a_linear_angle_enables_the_angle(drv):
    drv.click("polarization")
    shown = drv.draw(2).strings
    for label in ("Circular", "Linear x", "Linear y", "Linear at angle", "Left circular", "Unpolarized", "Radial", "Azimuthal"):
        assert label in shown, label
    drv.click_text("Linear at angle", last=True)
    assert model(drv).polarization == "linear" and drv.app.panel.enabled("angle_deg")
    drv.type_into("angle_deg", "45")
    drv.settle()
    assert np.array_equal(model(drv).volume, reference(polarization="linear", angle_deg=45.0))
    assert not np.array_equal(model(drv).volume, reference(polarization="linear", angle_deg=0.0))


def test_the_angle_field_is_greyed_unless_the_polarization_is_linear_at_an_angle(drv):
    assert not drv.app.panel.enabled("angle_deg")
    drv.click("angle_deg", fx=0.3)  # a greyed field takes neither the click nor the keys
    assert not drv.app.io.want_capture_keyboard
    drv.type_text("30")
    drv.enter()
    assert model(drv).angle_deg == 0.0
    pick(drv, "polarization", "Radial")
    assert not drv.app.panel.enabled("angle_deg")


def test_the_quality_choice_switches_to_full_and_back(drv):
    pick(drv, "quality", "Full")
    assert model(drv).quality == "full" and "Full" in drv.draw(2).strings
    drv.settle()
    assert np.array_equal(model(drv).volume, reference(quality="full"))
    pick(drv, "quality", "Preview (fast)")
    assert model(drv).quality == "preview"


def test_colormap_threshold_and_gamma_redraw_without_recomputing(drv):
    volume = model(drv).volume
    pick(drv, "colormap", "viridis")
    assert model(drv).colormap == "viridis" and not model(drv).is_stale
    drv.type_into("threshold", "0.3")
    drv.type_into("gamma", "1.5")
    assert not model(drv).is_stale and model(drv).volume is volume and not drv.app.busy


def test_the_polarization_vectors_toggle(drv):
    assert model(drv).show_polarization
    drv.click("show_polarization")
    assert not model(drv).show_polarization and not model(drv).is_stale
    drv.click("show_polarization")
    assert model(drv).show_polarization


def test_the_slice_choice_changes_the_section_shown(drv):
    assert "x [nm]" in drv.draw(2).strings and "y [nm]" in drv.painter.strings
    pick(drv, "slice_plane", "XZ")
    assert drv.app.slice_plane == "XZ" and "z [nm]" in drv.draw(2).strings
    assert "XZ" in drv.painter.strings  # the choice shows what is shown
    pick(drv, "slice_plane", "YZ")
    shown = drv.draw(2).strings
    assert drv.app.slice_plane == "YZ" and "z [nm]" in shown


# -- computing and its failures ------------------------------------------------------------------------------- #


def test_the_window_says_it_is_computing_while_the_volume_is_not_in(drv, monkeypatch):
    gate = threading.Event()
    real = PSFModel.compute

    def slow(self):
        gate.wait(20)
        return real(self)

    monkeypatch.setattr(PSFModel, "compute", slow)
    drv.type_into("na", "1.1")
    for _ in range(60):
        if "Computing the volume ..." in drv.draw(1).strings:
            break
    assert "Computing the volume ..." in drv.draw(2).strings and drv.app.busy
    gate.set()
    drv.settle()
    assert "Computing the volume ..." not in drv.draw(2).strings


def test_a_failing_computation_is_reported_once_and_the_next_edit_tries_again(drv, monkeypatch):
    real = PSFModel.compute
    calls = []

    def failing(self):
        calls.append(1)
        raise RuntimeError("no optics today")

    monkeypatch.setattr(PSFModel, "compute", failing)
    drv.type_into("na", "1.3")
    drv.settle()
    assert drv.app.error == "Error: no optics today" and "Error: no optics today" in drv.draw(2).strings
    n = len(calls)
    drv.draw(5)
    assert len(calls) == n  # not retried every frame
    monkeypatch.setattr(PSFModel, "compute", real)
    drv.type_into("na", "1.35")
    drv.settle()
    assert drv.app.error == "" and not model(drv).is_stale


def test_a_stale_edit_made_while_computing_is_computed_next(drv, monkeypatch):
    gate = threading.Event()
    real = PSFModel.compute

    def slow(self):
        gate.wait(20)
        return real(self)

    monkeypatch.setattr(PSFModel, "compute", slow)
    drv.type_into("na", "1.1")
    for _ in range(60):
        drv.draw(1)
        if drv.app.busy:
            break
    drv.type_into("na", "1.25")  # edited while the first volume is in flight
    gate.set()
    drv.settle()
    assert np.array_equal(model(drv).volume, reference(na=1.25))


# -- export ------------------------------------------------------------------------------------------------------ #


def test_export_is_greyed_until_a_volume_exists_and_a_click_then_opens_nothing():
    app = make_app()
    try:
        app.model.nxy, app.model.nz = 24, 7
        d = PSFDriver(app, BIG)
        d.draw(2)
        assert not app.panel.enabled("export_npy")
        d.click("export_npy")
        assert app.dialog is None
    finally:
        app.close()
        app._executor.shutdown(wait=True)


def test_export_npy_opens_the_dialog_with_the_descriptive_name_and_writes_the_typed_one(drv, tmp_path):
    drv.click("export_npy")
    assert drv.app.dialog is not None and drv.app.file_window.title == "Export PSF as .npy"
    assert "psf_vectorial_NA1.4_n1.518_520nm_circular.npy" in drv.draw(2).strings  # the name that records the optics
    drv.click_text("psf_vectorial_NA1.4_n1.518_520nm_circular.npy")
    drv.select_all()
    drv.type_text("my_psf")
    drv.click_text("Save", last=True)
    written = tmp_path / "my_psf.npy"
    assert written.is_file() and np.array_equal(np.load(written), model(drv).volume)
    assert drv.app.status == f"Exported to {written}" and drv.app.dialog is None
    assert f"Exported to {written}" in drv.draw(2).strings or any(s.startswith("Exported to") for s in drv.painter.strings)


def test_export_tif_writes_an_imagej_stack_with_the_voxel_size(drv, tmp_path):
    tifffile = pytest.importorskip("tifffile")
    drv.click("export_tif")
    assert drv.app.file_window.title == "Export PSF as .tif"
    drv.click_text("psf_vectorial_NA1.4_n1.518_520nm_circular.tif")
    drv.select_all()
    drv.type_text("stack.tif")
    drv.click_text("Save", last=True)
    written = tmp_path / "stack.tif"
    assert written.is_file()
    with tifffile.TiffFile(written) as tif:
        assert tif.is_imagej and tif.imagej_metadata["spacing"] == pytest.approx(0.1) and tif.imagej_metadata["unit"] == "um"
        assert np.allclose(tif.asarray(), model(drv).volume.astype(np.float32))


def test_a_name_without_a_suffix_gets_the_format_suffix(drv, tmp_path):
    drv.click("export_tif")
    drv.click_text("psf_vectorial_NA1.4_n1.518_520nm_circular.tif")
    drv.select_all()
    drv.type_text("bare")
    drv.click_text("Save", last=True)
    assert (tmp_path / "bare.tif").is_file() and not (tmp_path / "bare").exists()


def test_export_cancel_and_the_close_button_write_nothing(drv, tmp_path):
    drv.click("export_npy")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and not list(tmp_path.glob("*.np*"))
    drv.click("export_npy")
    x, y, w, h = drv.app.file_window.box
    drv.click_at(x + w - 12, y + 12)  # the header's close button
    assert drv.app.dialog is None and not list(tmp_path.glob("*.np*"))


def test_export_to_an_unwritable_place_reports_instead_of_raising(drv, tmp_path):
    drv.click("export_npy")
    drv.click_text("psf_vectorial_NA1.4_n1.518_520nm_circular.npy")
    drv.select_all()
    drv.type_text("no_such_folder/psf")
    drv.click_text("Save", last=True)
    assert drv.app.error.startswith("Error: Export failed:") and any(t.startswith("Error: Export failed:") for t in drv.draw(2).strings)


# -- the 3-D view ------------------------------------------------------------------------------------------------ #


def view_texts(drv):
    """Every text drawn inside the 3-D window (axis titles and ticks) with its position: they move when the box rotates."""
    x, y, w, h = drv.rect("volume")
    return sorted((t[5], round(t[0]), round(t[1])) for t in drv.draw(2).texts if x <= t[0] <= x + w and y <= t[1] <= y + h)


def test_dragging_in_the_3d_view_rotates_it(drv):
    x, y, w, h = drv.rect("volume")
    before = view_texts(drv)
    assert len(before) > 10
    drv.drag((x + w / 2, y + h / 2), (x + w / 2 + 200, y + h / 2 - 60), steps=12)
    after = view_texts(drv)
    assert sum(1 for a, b in zip(before, after) if a != b) > 10


# -- guide and help ------------------------------------------------------------------------------------------------ #


def test_guide_walks_the_first_steps_with_the_real_fields(drv):
    drv.click("guide")
    tour = drv.app.tour
    assert tour.active and tour.step_idx == 0
    drv.click_text("Next ►")  # the first card is centred: its buttons work
    assert tour.step_idx == 1 and tour.awaiting  # NA
    drv.click_text("Next ►")
    assert tour.step_idx == 1
    drv.type_into("na", "1.3")  # a value equal to the current one is no edit
    assert not tour.awaiting
    tour.next()  # (the card's Next button lies over the 3-D view here: see the xfail below)
    assert tour.step_idx == 2 and tour.awaiting  # immersion
    drv.type_into("n_immersion", "1.333")
    assert not tour.awaiting


@pytest.mark.xfail(strict=True, reason="emtk gap: the tour card does not block what is under it, so its Next button is dead over the 3-D plot")
def test_the_tour_next_button_works_where_the_card_lies_over_the_3d_view(drv):
    drv.click("guide")
    drv.click_text("Next ►")
    drv.type_into("na", "1.3")
    drv.click_text("Next ►")
    assert drv.app.tour.step_idx == 2


def test_every_guide_target_is_a_drawn_control(drv):
    for step in drv.app.tour.steps:
        key = drv.app.tour._target_key(step.get("target"))
        if key:
            assert key in drv.app.item_rects, key


def test_escape_ends_the_tour_and_help_opens_and_closes(drv):
    drv.click("guide")
    drv.escape()
    assert not drv.app.tour.active
    drv.click("help")
    assert drv.app.help_window.open and any("PSF calculator" in s for s in drv.draw(2).strings)
    drv.escape()
    assert not drv.app.help_window.open


def test_the_small_window_works_too(drv):
    drv.size = SMALL
    drv.type_into("na", "1.3")
    drv.settle()
    assert model(drv).na == 1.3 and np.array_equal(model(drv).volume, reference(na=1.3))
