"""Scientific parity and native factory checks for the anisotropy port."""

import csv
import subprocess
import sys

import numpy as np
import pytest

from chisurf.plugins.vv_vh_anisotropy.gui.model import AnisotropyModel


def sample(tmp_path, name="decay.dat"):
    t = np.arange(40, dtype=float)
    vv = 400 * np.exp(-t / 17) + 8
    vh = 180 * np.exp(-t / 17) + 4
    path = tmp_path / name
    np.savetxt(path, np.r_[vv, vh])
    return path, vv, vh


def test_computation_shift_flip_background_region(tmp_path):
    path, vv, vh = sample(tmp_path)
    model = AnisotropyModel()
    model.load(path)
    assert model.region_bounds == [28.0, 36.0]
    assert model.r_t == pytest.approx((vv - vh) / (vv + 2 * vh))
    model.g_factor = 1.2
    model.bg_vv = 8
    model.bg_vh = 4
    model.shift = .5
    model.region_bounds = [10, 20]
    model.compute()
    shifted = model.shifted(vh - 4, .5)
    expected = (vv - 8 - 1.2 * shifted) / (vv - 8 + 2.4 * shifted)
    assert model.r_t[1:] == pytest.approx(expected[1:])
    assert np.isnan(model.r_t[0])
    assert model.r_infty == pytest.approx(np.mean(expected[10:20]))
    model.flip = True
    model.compute()
    assert model.r_t[5] != pytest.approx(expected[5])


def test_exports_batch_errors_and_restored_state(tmp_path):
    path, _, _ = sample(tmp_path)
    model = AnisotropyModel()
    model.load(path)
    model.bg_vv = 3
    model.compute()
    decay, trace, info = model.save(tmp_path / "result.txt")
    assert decay.exists() and trace.exists() and info.exists()
    assert np.loadtxt(trace, skiprows=1).shape == (40, 3)
    with info.open() as stream:
        assert next(csv.DictReader(stream))["filename"] == path.name
    model.batch_files = [str(path), str(tmp_path / "missing.dat")]
    saved_trace = model.r_t.copy()
    rows = model.run_batch()
    assert np.isfinite(rows[0][1]) and np.isnan(rows[1][1]) and rows[1][-1]
    assert model.loaded_file == str(path)
    assert model.r_t == pytest.approx(saved_trace)
    model.save_batch(tmp_path / "batch.csv")
    assert len((tmp_path / "batch.csv").read_text().splitlines()) == 3
    restored = AnisotropyModel()
    restored.restore_settings(model.export_settings())
    assert restored.loaded_file == str(path)
    assert restored.bg_vv == 3
    assert restored.r_t == pytest.approx(model.r_t)


def test_native_factory_with_qt_import_blocked():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('qtpy', 'PyQt', 'PySide')):
        raise AssertionError('Qt import forbidden: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from chisurf.plugins.vv_vh_anisotropy.gui.app import create_app
assert create_app().model.__class__.__name__ == 'AnisotropyModel'
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                            text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_six_locale_labels_and_tooltips():
    from emtk import i18n

    from chisurf.plugins.vv_vh_anisotropy.gui.strings import LANGUAGES, TRANSLATIONS, tr

    original = i18n.get_locale()
    try:
        assert len(LANGUAGES) == 6
        for locale in LANGUAGES:
            i18n.set_locale(locale)
            assert tr("Load VV/VH file…") == TRANSLATIONS["Load VV/VH file…"][locale]
            assert tr("Shift VH by a fractional channel using interpolation.")
            assert tr("Drag the green lines to choose the r∞ region.")
    finally:
        i18n.set_locale(original)
