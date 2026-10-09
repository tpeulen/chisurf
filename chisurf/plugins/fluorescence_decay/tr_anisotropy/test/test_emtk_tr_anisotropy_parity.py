"""The native anisotropy wizard against the Qt wizard it replaces, every control operated with real input events.

Hermetic: settings, files and the HOME folder live in a temporary folder, nothing is read from the user's
``~/.chisurf`` and there is no network. The Qt wizard (``AutoForm`` over the shared ``AnisotropyViewModel``) is
built offscreen with the reader the native model uses (a stub session carrying a ``TCSPCReader``), so both
sides read the same synthetic IRFs and decays and the numbers must agree exactly.

The control -> test list is in ``okf/plugins/emtk-ports/tr_anisotropy/REPORT.md``.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.core.experiments.tcspc.reader import TCSPCReader
from chisurf.plugins.emtk_test_input import SIZE, SMALL, Driver
from chisurf.plugins.fluorescence_decay.tr_anisotropy.core import irf as core_irf
from chisurf.plugins.fluorescence_decay.tr_anisotropy.core import spectra as core_spectra
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.app import make_app
from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.model import NativeAnisotropyModel

HERE = Path(__file__).parent
PLUGIN = HERE.parent


def make_data(folder, n=256, dt=0.1, seed=3):
    """Polarised IRFs and decays with a known answer (tau 4 ns, rho 1.5 ns, r0 0.35) and a flat background."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    x = np.arange(n) * dt
    irf = np.exp(-0.5 * ((x - 2.0) / 0.25) ** 2)
    r = 0.35 * np.exp(-x / 1.5)
    out = {}
    curves = {
        "irf_vv": irf * 3000,
        "irf_vh": irf * 2500,
        "data_vv": np.convolve(irf, np.exp(-x / 4.0) * (1 + 2 * r))[:n] * 400,
        "data_vh": np.convolve(irf, np.exp(-x / 4.0) * (1 - r))[:n] * 400,
    }
    for key, y in curves.items():
        path = folder / f"{key}.txt"
        np.savetxt(
            path, np.column_stack((x, rng.poisson(y + 4.0).astype(float))), header="time_ns counts"
        )
        out[key] = str(path)
    return out


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    import chisurf
    import chisurf.core.settings as settings

    # the settings folder is resolved when chisurf is imported: point the module at this test's folder
    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings", raising=False)
    (tmp_path / "settings").mkdir(parents=True, exist_ok=True)
    (tmp_path / "settings" / "anisotropy_corrections.json").write_text(
        json.dumps({"g_factor": 1.16, "l1": 0.12, "l2": 0.44})
    )
    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "imported_datasets", [])


@pytest.fixture
def files(tmp_path):
    return make_data(tmp_path / "data")


@pytest.fixture
def ui():
    app = make_app()
    driver = Driver(app)
    driver.draw()
    return driver


def go(ui, title):
    ui.click_name(title)
    return ui.app.model


def set_files(model, files):
    for key, path in files.items():
        setattr(model, key + "_path", path)


def load(ui, files):
    m = go(ui, "Data")
    set_files(m, files)
    go(ui, "Normalize IRF")
    ui.click_text("Load / reload data")
    return m


# ───────────────────────────── numeric parity with the Qt wizard ───────────────────────────── #


@pytest.fixture
def qt_wizard(files):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    import chisurf

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841 (kept alive)
    chisurf.cs = types.SimpleNamespace(
        current_setup=None,
        current_experiment_reader=TCSPCReader(dt=1.0, rep_rate=10.0, skiprows=0),
        current_experiment=None,
        dataset_selector=None,
    )
    from chisurf.plugins.fluorescence_decay.tr_anisotropy.gui.tool import AnisotropyWizard

    wizard = AnisotropyWizard()
    set_files(wizard.model, files)
    wizard._qapp = qapp
    return wizard


def test_loading_and_the_background_correction_equal_the_qt_wizard(qt_wizard, files):
    qt = qt_wizard.model
    assert qt.load_data()
    native = NativeAnisotropyModel()
    native.first_column_is_time = True
    set_files(native, files)
    native.load_data()
    assert (native.region_lb, native.region_ub) == (qt.region_lb, qt.region_ub)
    for key in ("irf_vv", "irf_vh", "data_vv", "data_vh", "irf_vv_bg_norm", "irf_vh_bg_norm"):
        np.testing.assert_allclose(native.data[key].y, qt.data[key].y, err_msg=key)
    for lb, ub in ((50, 150), (10, 30), (0, 256), (120, 120)):
        qt.apply_region(lb, ub)
        native.apply_region(lb, ub)
        for key in ("irf_vv_bg_norm", "irf_vh_bg_norm"):
            np.testing.assert_allclose(native.data[key].y, qt.data[key].y, err_msg=(lb, ub, key))


def test_a_crossed_region_is_swapped_where_the_qt_wizard_silently_skipped_the_subtraction(
    qt_wizard, files
):
    """Deliberate difference: Qt passes (200, 100) on, an empty region, so no background is subtracted."""
    qt = qt_wizard.model
    qt.load_data()
    native = NativeAnisotropyModel()
    native.first_column_is_time = True
    set_files(native, files)
    native.load_data()
    qt.apply_region(200, 100)
    native.apply_region(200, 100)
    assert (native.region_lb, native.region_ub) == (100, 200)
    swapped, _ = core_irf.correct_irfs(native.data["irf_vv"].y, native.data["irf_vh"].y, 100, 200)
    np.testing.assert_allclose(native.data["irf_vv_bg_norm"].y, swapped)
    skipped, _ = core_irf.correct_irfs(qt.data["irf_vv"].y, qt.data["irf_vh"].y, 200, 100)
    np.testing.assert_allclose(qt.data["irf_vv_bg_norm"].y, skipped)


def test_the_qt_wizards_step_texts_and_check_marks_are_the_natives(qt_wizard, ui, files):
    wiz = qt_wizard.findChild(
        __import__("chisurf.gui.autoform.sections.wizard_section", fromlist=["x"]).WizardWidget
    )
    assert [s["title"] for s in ui.app.steps] == [
        wiz._steps[i].title for i in range(len(wiz._steps))
    ]
    for i, step in enumerate(wiz._steps):
        assert ui.app.steps[i].get("subtitle", "") == (step.subtitle or "")
    # the Qt check marks: Data waits for the files, Components for both spectra, the rest are ticked
    qt, native = qt_wizard.model, ui.app.model
    for state in ({}, files, {"data_vh": ""}):
        for model in (qt, native):
            set_files(model, {**{k: "" for k in files}, **state} if state is not files else files)
        for i in range(6):
            assert native.step_complete(i) == wiz._step_complete(i), (sorted(state), i)
    for model in (qt, native):
        model.lifetime_spectrum = []
    assert [native.step_complete(i) for i in range(6)] == [wiz._step_complete(i) for i in range(6)]
    assert native.step_complete(4) is False


def test_corrections_defaults_and_spectra_files_equal_the_qt_wizard(qt_wizard, tmp_path):
    qt = qt_wizard.model
    native = (
        make_app().model
    )  # a fresh window starts from the same stored defaults the Qt wizard reads
    assert (native.g_factor, native.l1, native.l2) == (qt.g_factor, qt.l1, qt.l2)
    assert (native.g_factor, native.l1, native.l2) == (1.16, 0.12, 0.44)
    assert native.lifetime_spectrum == qt.lifetime_spectrum
    assert native.rotation_spectrum == qt.rotation_spectrum
    qt.lifetime_spectrum = [[0.4, 1.0], [0.6, 3.0]]
    native.lifetime_spectrum = [[0.4, 1.0], [0.6, 3.0]]
    qt_file, native_file = tmp_path / "qt.spk.json", tmp_path / "native.spk.json"
    core_spectra.save_spectra(
        qt_file, qt.lifetime_spectrum, qt.rotation_spectrum, mirror_to_default=False
    )
    native.save_spectra(native_file)
    assert json.loads(qt_file.read_text()) == json.loads(native_file.read_text())
    fresh = NativeAnisotropyModel()
    fresh.load_spectra(str(qt_file))
    assert fresh.lifetime_spectrum == [[0.4, 1.0], [0.6, 3.0]]


# ───────────────────────────────── steps and navigation ───────────────────────────────── #


def test_each_step_is_reached_by_clicking_its_entry_and_shows_its_title(ui):
    for index, step in enumerate(ui.app.steps):
        ui.click_name(step["title"])
        assert ui.app.step_index == index
        assert step["title"] in [t[5] for t in ui.draw().texts]


def test_back_and_next_walk_the_steps_and_grey_out_at_the_ends(ui):
    assert ui.app.step_index == 0
    ui.click_text("Back")
    assert ui.app.step_index == 0
    for expected in range(1, 6):
        ui.click_text("Next")
        assert ui.app.step_index == expected
    ui.click_text("Next")
    assert ui.app.step_index == 5
    for expected in range(4, -1, -1):
        ui.click_text("Back")
        assert ui.app.step_index == expected


def test_the_check_marks_follow_the_files_and_the_spectra(ui, files):
    def marks():
        return {t[5][4:] for t in ui.draw().texts if t[5].startswith("[x] ")}

    assert "Data" not in marks() and "Components" in marks()
    set_files(ui.app.model, files)
    assert "Data" in marks()
    ui.app.model.lifetime_spectrum.clear()
    assert "Components" not in marks()


# ─────────────────────────────────────── Data step ─────────────────────────────────────── #


def test_each_path_field_takes_typed_text_and_says_found_or_missing(ui, files):
    m = go(ui, "Data")
    for attr in ("irf_vv_path", "irf_vh_path", "data_vv_path", "data_vh_path"):
        ui.type_into_name(attr, files[attr.replace("_path", "")])
        assert getattr(m, attr) == files[attr.replace("_path", "")]
    assert m.files_ready()
    assert [t[5] for t in ui.draw().texts].count("found") == 4
    ui.type_into_name("data_vh_path", str(Path(files["data_vh"]).with_name("nope.txt")))
    assert not m.files_ready()
    assert [t[5] for t in ui.draw().texts].count("missing") == 1


@pytest.mark.parametrize("attr", ["irf_vv_path", "irf_vh_path", "data_vv_path", "data_vh_path"])
def test_browse_opens_the_file_dialog_and_a_clicked_file_fills_the_field(ui, files, attr):
    m = go(ui, "Data")
    ui.app.last_dir = str(Path(files["irf_vv"]).parent)
    index = ["irf_vv_path", "irf_vh_path", "data_vv_path", "data_vh_path"].index(attr)
    ui.click(
        ui.text_rect(ui.draw(), "Browse", last=False)
        if index == 0
        else [t[:4] for t in ui.draw().texts if t[5] == "Browse"][index]
    )
    assert ui.app.dialog is not None
    name = Path(files[attr.replace("_path", "")]).name
    ui.click_text(name)
    ui.click_text("Open")
    assert ui.app.dialog is None
    assert getattr(m, attr) == files[attr.replace("_path", "")]


def test_the_file_dialog_cancel_and_close_leave_the_path_unchanged(ui, files):
    m = go(ui, "Data")
    ui.app.last_dir = str(Path(files["irf_vv"]).parent)
    for closer in ("Cancel", "×"):
        ui.click_text("Browse", last=False)
        assert ui.app.dialog is not None
        ui.click_text(closer)
        assert ui.app.dialog is None
    assert m.irf_vv_path == ""


def test_the_stacked_toggle_swaps_four_fields_for_two_and_the_reader_settings_follow(ui):
    m = go(ui, "Data")
    assert ui.app.model.stacked_files is False
    texts = [t[5] for t in ui.draw().texts]
    assert {"IRF VV", "IRF VH", "Data VV", "Data VH"} <= set(texts)
    ui.click_text("Two stacked VV/VH files")
    assert m.stacked_files is True
    texts = [t[5] for t in ui.draw().texts]
    assert {"IRF VV/VH", "Data VV/VH"} <= set(texts) and "IRF VH" not in texts
    assert m.enabled("first_column_is_time") is False
    ui.click_text("Two stacked VV/VH files")
    assert m.stacked_files is False


def test_first_column_and_header_toggles_are_clicked_and_bin_width_greys_with_a_time_column(ui):
    m = go(ui, "Data")
    ui.click_text("First column is time (ns)")
    assert m.first_column_is_time is True and m.enabled("bin_width") is False
    ui.click_text("First column is time (ns)")
    assert m.first_column_is_time is False and m.enabled("bin_width") is True
    assert m.use_header is True
    ui.click_text("Use file header")
    assert m.use_header is False


@pytest.mark.parametrize(
    "attr,typed,expected",
    [
        ("bin_width", "0.05", 0.05),
        ("rep_rate", "40", 40.0),
        ("skiprows", "3", 3),
        ("bin_width", "500", 100.0),
        ("rep_rate", "0", 0.001),
        ("skiprows", "-4", 0),
    ],
)
def test_reader_fields_take_typed_values_and_clamp_to_their_limits(ui, attr, typed, expected):
    m = go(ui, "Data")
    ui.type_into_name(attr, typed)
    assert getattr(m, attr) == pytest.approx(expected)


@pytest.mark.parametrize("attr,step", [("bin_width", 0.01), ("rep_rate", 1.0), ("skiprows", 1)])
def test_reader_field_arrows_step_the_value(ui, attr, step):
    m = go(ui, "Data")
    start = getattr(m, attr)
    x, y, w, h = ui.rect(f"{attr}.stepper")
    ui.click((x, y, w, h), fy=0.25)
    assert getattr(m, attr) == pytest.approx(start + step)
    ui.click((x, y, w, h), fy=0.75)
    ui.click((x, y, w, h), fy=0.75)
    assert getattr(m, attr) == pytest.approx(max(start - step, 0.0 if attr == "skiprows" else 1e-6))


def test_stacked_files_are_read_with_the_channel_and_the_header_bin_width(ui, tmp_path):
    from chisurf.core.fio.vv_vh import write_vv_vh

    n = 64
    arrays = {
        k: np.arange(n, dtype=float) * s + 3
        for k, s in (("irf_vv", 1), ("irf_vh", 2), ("data_vv", 3), ("data_vh", 4))
    }
    write_vv_vh(
        tmp_path / "irf.dat", vv=arrays["irf_vv"], vh=arrays["irf_vh"], metadata={"dt": 0.1}
    )
    write_vv_vh(
        tmp_path / "data.dat", vv=arrays["data_vv"], vh=arrays["data_vh"], metadata={"dt": 0.1}
    )
    m = go(ui, "Data")
    ui.click_text("Two stacked VV/VH files")
    ui.type_into_name("irf_vv_path", str(tmp_path / "irf.dat"))
    ui.type_into_name("data_vv_path", str(tmp_path / "data.dat"))
    go(ui, "Normalize IRF")
    ui.click_text("Load / reload data")
    for key in arrays:
        np.testing.assert_allclose(m.data[key].y, arrays[key])
    assert np.diff(m.data["data_vh"].x).mean() == pytest.approx(0.1)


def test_dropping_files_fills_the_next_empty_path_and_a_json_loads_the_spectra(ui, files, tmp_path):
    m = ui.app.model
    assert ui.drop(files["data_vv"], files["irf_vv"]) is True
    assert (m.irf_vv_path, m.irf_vh_path) == (files["data_vv"], files["irf_vv"])
    assert ui.app.step_index == 1
    ui.drop(files["irf_vh"], files["data_vh"])
    assert (m.data_vv_path, m.data_vh_path) == (files["irf_vh"], files["data_vh"])
    saved = tmp_path / "s.spk.json"
    core_spectra.save_spectra(saved, [[0.9, 2.5]], [[0.2, 7.0]], mirror_to_default=False)
    ui.drop(saved)
    assert m.lifetime_spectrum == [[0.9, 2.5]] and m.rotation_spectrum == [[0.2, 7.0]]
    assert ui.app.step_index == 4
    assert ui.drop() is False


# ───────────────────────────────── Normalize IRF step ───────────────────────────────── #


def test_load_is_greyed_without_files_and_loads_the_curves_with_them(ui, files):
    m = go(ui, "Normalize IRF")
    ui.click_text("Load / reload data")
    assert m.data["irf_vv"] is None
    assert "Load the data to see the IRFs." in [t[5] for t in ui.draw().texts]
    m = load(ui, files)
    assert (
        m.data["irf_vv"] is not None
        and len(m.data["irf_vv"].y) == 249
        or len(m.data["irf_vv"].y) == 256
    )
    assert (m.region_lb, m.region_ub) == core_irf.initial_region(len(m.data["irf_vv"].y))
    assert m.status.startswith("Loaded")


def test_a_bad_file_is_reported_in_the_status_line_and_nothing_is_loaded(ui, files, tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("not numbers\nat all\n")
    m = go(ui, "Data")
    set_files(m, {**files, "data_vh": str(bad)})
    go(ui, "Normalize IRF")
    ui.click_text("Load / reload data")
    assert m.status.startswith("Error:") or m.data["data_vh"] is None
    assert m.data["irf_vv_bg_norm"] is None
    assert m.status[:20] in [t[5] for t in ui.draw().texts] or any(
        m.status[:30] in t[5] for t in ui.draw().texts
    )


def test_typing_the_background_channels_recomputes_the_corrected_irfs(ui, files):
    m = load(ui, files)
    ui.type_into_name("region_lb", "40")
    ui.type_into_name("region_ub", "120")
    assert (m.region_lb, m.region_ub) == (40, 120)
    vv, vh = core_irf.correct_irfs(m.data["irf_vv"].y, m.data["irf_vh"].y, 40, 120)
    np.testing.assert_allclose(m.data["irf_vv_bg_norm"].y, vv)
    np.testing.assert_allclose(m.data["irf_vh_bg_norm"].y, vh)


def test_background_fields_clamp_to_the_channel_count_and_swap_when_crossed(ui, files):
    m = load(ui, files)
    n = len(m.data["irf_vv"].y)
    ui.type_into_name("region_ub", "99999")
    assert m.region_ub == n
    ui.type_into_name("region_lb", str(n))
    ui.type_into_name("region_ub", "10")
    assert m.region_lb <= m.region_ub


def test_the_background_arrows_step_one_channel(ui, files):
    m = load(ui, files)
    start = m.region_lb
    ui.click(ui.rect("region_lb.stepper"), fy=0.25)
    assert m.region_lb == start + 1
    ui.click(ui.rect("region_lb.stepper"), fy=0.75)
    assert m.region_lb == start


def test_dragging_the_green_box_edge_in_the_plot_moves_the_background_region(ui, files):
    m = load(ui, files)
    ui.draw(3)
    info = ui.app.plot_info
    (x0, y0), (x1, y1) = info["lb"], info["ub"]
    before = (m.region_lb, m.region_ub)
    ui.drag((x1, y1), (x1 - 80, y1))
    assert m.region_ub < before[1]
    assert m.region_lb == before[0]
    vv, _ = core_irf.correct_irfs(m.data["irf_vv"].y, m.data["irf_vh"].y, m.region_lb, m.region_ub)
    np.testing.assert_allclose(m.data["irf_vv_bg_norm"].y, vv)
    ui.drag((x0, y0), (x0 + 30, y0))
    assert m.region_lb > before[0]


def test_the_plot_has_axes_a_legend_and_four_curves(ui, files):
    load(ui, files)
    strings = [t[5] for t in ui.draw().texts]
    for label in (
        "Channel",
        "IRF counts",
        "VV (raw)",
        "VH (raw)",
        "VV (corrected)",
        "VH (corrected)",
    ):
        assert label in strings, label


def test_the_wheel_zooms_the_irf_plot(ui, files):
    load(ui, files)
    ui.draw(3)
    (px, py), (sx, sy) = ui.app.plot_info["pos"], ui.app.plot_info["size"]
    before = ui.draw().strings[:]
    ui.wheel(px + sx * 0.3, py + sy * 0.5, -3.0)
    assert ui.draw().strings != before


def test_export_writes_the_corrected_irfs_through_the_dialog(ui, files, tmp_path):
    from chisurf.core.fio.vv_vh import read_vv_vh

    m = go(ui, "Normalize IRF")
    ui.click_text("Export corrected IRFs")
    assert ui.app.dialog is None  # greyed: nothing to export before the data is loaded
    m = load(ui, files)
    ui.app.last_dir = str(tmp_path)
    ui.click_text("Export corrected IRFs")
    assert ui.app.dialog is not None
    ui.click_text("corrected_irfs.dat", last=False, fx=0.3)
    ui.app.key(0x41, "a", 0x04000000)
    ui.type("out")
    ui.click_text("Save")
    out = tmp_path / "out"
    written = [p for p in tmp_path.iterdir() if p.name.startswith("out")]
    assert written, sorted(p.name for p in tmp_path.iterdir())
    saved, meta = read_vv_vh(written[0], split=True, return_metadata=True)
    np.testing.assert_allclose(saved["VV"], m.data["irf_vv_bg_norm"].y, rtol=1e-9)
    np.testing.assert_allclose(saved["VH"], m.data["irf_vh_bg_norm"].y, rtol=1e-9)
    assert m.status.startswith("Exported")


# ─────────────────────────────────────── Corrections ─────────────────────────────────────── #


@pytest.mark.parametrize(
    "attr,typed,expected",
    [
        ("g_factor", "1.25", 1.25),
        ("l1", "0.03", 0.03),
        ("l2", "-0.02", -0.02),
        ("g_factor", "0", 0.001),
        ("l1", "99", 10.0),
        ("l2", "-99", -10.0),
    ],
)
def test_each_correction_takes_typed_values_clamped_to_its_range(ui, attr, typed, expected):
    m = go(ui, "Corrections")
    ui.type_into_name(attr, typed)
    assert getattr(m, attr) == pytest.approx(expected)
    assert m._corrections[{"g_factor": "g_factor", "l1": "l1", "l2": "l2"}[attr]] == pytest.approx(
        expected
    )


@pytest.mark.parametrize("attr", ["g_factor", "l1", "l2"])
def test_each_correction_arrow_steps_by_a_hundredth(ui, attr):
    m = go(ui, "Corrections")
    start = getattr(m, attr)
    ui.click(ui.rect(f"{attr}.stepper"), fy=0.25)
    assert getattr(m, attr) == pytest.approx(start + 0.01)
    ui.click(ui.rect(f"{attr}.stepper"), fy=0.75)
    assert getattr(m, attr) == pytest.approx(start)


# ─────────────────────────────────────── Components ─────────────────────────────────────── #


def edit_cell(ui, shown, typed):
    """Double-click the cell showing *shown*, replace its text (Backspace: the table's editor opens unselected), Enter."""
    ui.click(ui.text_rect(ui.draw(), shown, last=False), clicks=2)
    for _ in range(12):
        ui.app.key(keys.KEY_BACKSPACE, "")
        ui.draw(1)
    ui.type(typed)
    ui.enter()


def field(ui, form, name):
    ui.draw()
    return ui.app.forms[form].rects[name]


def test_the_tables_show_the_qt_default_spectra(ui):
    go(ui, "Components")
    strings = [t[5] for t in ui.draw().texts]
    for value in ("0.3", "1.8", "0.7", "4.1", "0.28", "0.15", "0.1", "10"):
        assert value in strings, value


def test_a_double_clicked_cell_is_edited_by_typing(ui):
    m = go(ui, "Components")
    edit_cell(ui, "1.8", "2.2")
    assert m.lifetime_spectrum[0] == [0.3, 2.2]
    edit_cell(ui, "0.15", "0.5")
    assert m.rotation_spectrum[0] == [0.28, 0.5]
    assert "2.2" in [t[5] for t in ui.draw().texts]


def test_escape_leaves_a_cell_unchanged(ui):
    m = go(ui, "Components")
    ui.click(ui.text_rect(ui.draw(), "1.8"), clicks=2)
    ui.type("9")
    ui.escape()
    assert m.lifetime_spectrum[0] == [0.3, 1.8]


def test_a_refused_edit_keeps_the_value_and_says_why(ui):
    m = go(ui, "Components")
    edit_cell(ui, "1.8", "-3")
    assert m.lifetime_spectrum[0] == [0.3, 1.8]
    assert "positive" in m.status
    assert any("positive" in t[5] for t in ui.draw().texts)


def test_add_component_appends_the_typed_pair_to_the_right_table(ui):
    m = go(ui, "Components")
    ui.type_into(field(ui, "lifetime", "new_amplitude"), "0.25")
    assert m.lifetime.new_amplitude == pytest.approx(
        0.25
    ) and m.rotation.new_amplitude == pytest.approx(0.5)
    ui.type_into(field(ui, "lifetime", "new_value"), "3.5")
    ui.click(field(ui, "lifetime", "add"))
    assert m.lifetime_spectrum[-1] == [0.25, 3.5] and len(m.lifetime_spectrum) == 3
    assert "3.5" in [t[5] for t in ui.draw().texts]
    ui.type_into(field(ui, "rotation", "new_value"), "7")
    ui.click(field(ui, "rotation", "add"))
    assert m.rotation_spectrum[-1] == [0.5, 7.0] and len(m.rotation_spectrum) == 3
    assert len(m.lifetime_spectrum) == 3


def test_remove_selected_deletes_the_clicked_row_or_the_last_one(ui):
    m = go(ui, "Components")
    ui.click(ui.text_rect(ui.draw(), "4.1"))
    ui.click(field(ui, "lifetime", "delete"))
    assert m.lifetime_spectrum == [[0.3, 1.8]]
    ui.click(field(ui, "rotation", "delete"))
    assert m.rotation_spectrum == [[0.28, 0.15]]  # none selected: the last row goes
    ui.click(field(ui, "rotation", "delete"))
    ui.click(field(ui, "rotation", "delete"))
    assert m.rotation_spectrum == []  # nothing left to remove: no error


def test_the_delete_key_removes_the_selected_row(ui):
    m = go(ui, "Components")
    ui.click(ui.text_rect(ui.draw(), "0.28"))
    ui.delete()
    assert m.rotation_spectrum == [[0.1, 10.0]]


def test_the_new_component_fields_reject_non_positive_times(ui):
    m = go(ui, "Components")
    ui.type_into(field(ui, "lifetime", "new_value"), "0")
    assert m.lifetime.new_value >= 0.001
    m.lifetime.new_amplitude = -1.0
    m.lifetime.add()
    assert len(m.lifetime_spectrum) == 2 and "nonnegative" in m.status


def test_save_spectra_asks_for_a_name_then_overwrites_silently(ui, tmp_path):
    m = go(ui, "Components")
    m.spk_path = ""  # nothing loaded or saved yet: ask where
    ui.app.last_dir = str(tmp_path)
    ui.click_text("Save spectra")
    assert ui.app.dialog is not None
    ui.click_text("anisotropy.spk.json", last=False, fx=0.3)
    ui.app.key(0x41, "a", 0x04000000)
    ui.type("mine.spk.json")
    ui.click_text("Save")
    saved = tmp_path / "mine.spk.json"
    assert saved.is_file() and m.spk_path == str(saved)
    assert json.loads(saved.read_text())["lifetime_spectrum"] == [[0.3, 1.8], [0.7, 4.1]]
    m.lifetime_spectrum[0][1] = 9.0
    ui.click_text("Save spectra")
    assert ui.app.dialog is None
    assert json.loads(saved.read_text())["lifetime_spectrum"][0] == [0.3, 9.0]
    assert "Saved spectra" in m.status


def test_a_fresh_window_saves_to_the_stored_default_file_as_the_qt_wizard_did(tmp_path):
    core_spectra.spk_json_path()  # the stored default file exists, as after the first Qt run
    ui = Driver(make_app())
    ui.draw()
    m = go(ui, "Components")
    assert m.spk_path.endswith("wizard.spk.json") and str(tmp_path) in m.spk_path
    m.lifetime_spectrum[0][1] = 2.5
    ui.click_text("Save spectra")
    assert ui.app.dialog is None
    assert json.loads(Path(m.spk_path).read_text())["lifetime_spectrum"][0] == [0.3, 2.5]


def test_load_spectra_replaces_both_tables_from_the_file(ui, tmp_path):
    m = go(ui, "Components")
    saved = tmp_path / "in.spk.json"
    core_spectra.save_spectra(
        saved, [[1.0, 2.0]], [[0.4, 5.0], [0.1, 20.0]], mirror_to_default=False
    )
    ui.app.last_dir = str(tmp_path)
    ui.click_text("Load spectra")
    ui.click_text("in.spk.json")
    ui.click_text("Open")
    assert m.lifetime_spectrum == [[1.0, 2.0]] and m.rotation_spectrum == [[0.4, 5.0], [0.1, 20.0]]
    assert m.spk_path == str(saved)
    assert "20" in [t[5] for t in ui.draw().texts]


def test_a_damaged_spectra_file_is_reported_not_raised(ui, tmp_path):
    m = go(ui, "Components")
    bad = tmp_path / "bad.spk.json"
    bad.write_text("{not json")
    ui.drop(bad)
    assert m.status.startswith("Error:")
    assert m.lifetime_spectrum == [[0.3, 1.8], [0.7, 4.1]]


# ────────────────────────────────────────── Finish ────────────────────────────────────────── #


def test_create_fits_is_greyed_before_loading_and_builds_the_linked_fits_after(ui, files):
    import chisurf

    m = go(ui, "Finish")
    ui.click_text("Create fits")
    assert m.fit_groups is None and chisurf.fits == []
    m = load(ui, files)
    m.g_factor, m.l1, m.l2 = 1.5, 0.03, 0.07
    go(ui, "Finish")
    ui.click_text("Create fits")
    assert m.fit_groups is not None, m.status
    vv, vh, global_fit = m.fit_groups
    assert len(chisurf.fits) == 3 and len(chisurf.imported_datasets) == 4
    assert global_fit.model.fits == [vv, vh]
    pars = {p.canonical_id: p for p in vv.model.parameters_all}
    assert pars["anisotropy.g"].value == pytest.approx(1.5)
    assert pars["lifetime.tau.1"].value == pytest.approx(4.1)
    assert pars["rotation.time.1"].value == pytest.approx(10.0)
    assert m.status.startswith("Created")
    assert any(t[5].startswith("Created: ") for t in ui.draw().texts)


def test_create_fits_after_changing_the_reader_demands_a_reload(ui, files):
    import chisurf

    m = load(ui, files)
    ui.type_into_name("rep_rate", "50") if go(ui, "Data") else None
    go(ui, "Finish")
    ui.click_text("Create fits")
    assert m.fit_groups is None and "reload" in m.status and chisurf.fits == []


# ───────────────────────────── help, guide, settings, small window ───────────────────────────── #


def test_help_opens_a_window_with_live_links_and_closes(ui):
    ui.click_text("Help")
    assert ui.app.help_window.open
    assert "Help" in " ".join(t[5] for t in ui.draw().texts)
    ui.click_text("Close")
    assert not ui.app.help_window.open


def test_the_help_links_point_at_pages_that_exist():
    import re

    text = (PLUGIN / "gui" / "help.md").read_text()
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", text)
    assert links
    for link in links:
        assert (repo / link).is_file(), link


def test_the_tour_is_walked_with_the_real_controls_and_waits_at_each_await(ui, files, tmp_path):
    ui.click_text("Guide")
    tour = ui.app.tour
    assert tour.active and tour.step_idx == 0
    ui.click_text("Next ►")
    assert tour.step_idx == 1 and ui.app.step_index == 1 and tour.awaiting
    ui.click_text("Next ►")  # refused while it waits
    assert tour.step_idx == 1
    ui.type_into_name("irf_vv_path", files["irf_vv"])
    ui.type_into_name("irf_vh_path", files["irf_vh"])
    ui.type_into_name("data_vv_path", files["data_vv"])
    ui.type_into_name("data_vh_path", files["data_vh"])
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 2 and ui.app.step_index == 2 and tour.awaiting
    ui.click_text("Load / reload data")
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 3 and ui.app.step_index == 3 and tour.awaiting
    ui.type_into_name("g_factor", "1.1")
    ui.click_text("Next ►")
    assert tour.step_idx == 4 and ui.app.step_index == 4 and tour.awaiting
    ui.click(ui.text_rect(ui.draw(), "Add component", last=False))
    ui.click_text("Next ►")
    assert tour.step_idx == 5 and ui.app.step_index == 5 and tour.awaiting
    ui.click_text("Create fits")
    assert not tour.awaiting
    ui.click_text("Close Tour")
    assert not tour.active


def test_every_tour_target_is_drawn_on_its_step(ui):
    for step in ui.app.tour.steps:
        key = ui.app.tour._target_key(step.get("target"))
        if not key:
            continue
        ui.app.tour.start(ui.app.tour.steps.index(step))
        ui.draw(3)
        assert ui.app.target_rect(key), key
        ui.app.tour.stop()


def test_settings_round_trip_restores_paths_corrections_spectra_and_step(ui, files):
    m = ui.app.model
    set_files(m, files)
    m.g_factor = 1.3
    m.lifetime_spectrum = [[1.0, 2.0]]
    m.stacked_files = True
    m.rep_rate = 33.0
    ui.app.select_step(3)
    ui.app.last_dir = "/somewhere"
    saved = json.loads(json.dumps(ui.app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.model.irf_vv_path == files["irf_vv"] and other.model.g_factor == 1.3
    assert other.model.lifetime_spectrum == [[1.0, 2.0]] and other.model.stacked_files is True
    assert other.model.rep_rate == 33.0 and other.step_index == 3 and other.last_dir == "/somewhere"
    other.restore_settings({"step_index": "junk"})
    assert other.step_index == 0


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_every_step_draws_populated_and_empty_at_every_size(ui, files, size):
    ui.resize(size)
    for index in range(6):
        ui.app.select_step(index)
        ui.draw(3)
    m = load(ui, files)
    ui.resize(size)
    for index in range(6):
        ui.app.select_step(index)
        ui.draw(3)


def test_no_text_is_cut_off_in_the_small_window(ui, files):
    ui.resize(SMALL)
    load(ui, files)
    for index in range(6):
        ui.app.select_step(index)
        painter = ui.draw(3)
        for x, y, w, h, *_rest in (t for t in painter.texts):
            assert x >= -1 and x + w <= SMALL[0] + 1, (index, x, w)


def test_every_control_has_a_tooltip_on_every_step(ui, files):
    from test.gui.emtk_port_parity import emtk_inventory

    load(ui, files)
    missing = set()
    for index in range(6):
        ui.app.select_step(index)
        missing |= set(emtk_inventory(ui.app, SIZE)["controls_without_tooltip"])
    assert not missing, sorted(missing)


def test_every_spec_field_and_action_exists_on_the_model_and_has_a_description():
    model = NativeAnisotropyModel()
    spec = json.loads((PLUGIN / "gui" / "anisotropy_emtk.view.json").read_text())["panels"]

    def walk(sections, owner):
        for section in sections:
            kind = section.get("type")
            if kind in ("value", "toggle"):
                assert hasattr(owner, section["attr"]), section["attr"]
                assert section.get("description"), section["attr"]
                if section.get("call"):
                    assert callable(getattr(owner, section["call"])), section["call"]
            elif kind == "button_row":
                for button in section["buttons"]:
                    assert callable(getattr(owner, button["action"])), button
                    assert button.get("description"), button
            elif kind == "custom":
                options = section["options"]
                for name in ("source", "selected_call", "edited_call", "delete_call"):
                    assert hasattr(owner, options[name]), options[name]
                for column in options["columns"]:
                    assert column.get("tooltip"), column
            if kind == "panel":
                assert section.get("description"), section.get("title")
            walk(section.get("sections", []), owner)

    for name, panel in spec.items():
        walk(panel["sections"], model.lifetime if name in ("lifetime", "rotation") else model)


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tr_anisotropy")
    assert result["ok"], result["output"]


def test_a_window_with_nothing_loaded_asks_for_the_data_instead_of_drawing_a_curve(ui):
    go(ui, "Normalize IRF")
    painter = ui.draw()
    assert "Load the data to see the IRFs." in [t[5] for t in painter.texts]
    assert "IRF normalization" not in [t[5] for t in painter.texts]
