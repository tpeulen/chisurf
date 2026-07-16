# Consolidated test file: test_vv_vh.py


# --- FROM test_vv_vh_io_and_anisotropy.py ---
import os
import tempfile
import importlib.util
from pathlib import Path

import numpy as np


def test_vv_vh_roundtrip_split_channels():
    module_path = Path(__file__).resolve().parents[2] / "chisurf" / "core" / "fio" / "vv_vh.py"
    spec = importlib.util.spec_from_file_location("vv_vh_local", module_path)
    vv_vh = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(vv_vh)

    n_points = 256
    rng = np.random.default_rng(1)
    vv = rng.poisson(1000, n_points).astype(float)
    vh = rng.poisson(600, n_points).astype(float)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        filename = tmp.name

    try:
        vv_vh.write_vv_vh(filename, vv=vv, vh=vh, g_factor=1.0, metadata={"test": True})
        vv_read, vh_read = vv_vh.read_vv_vh(filename, split=True)
        assert np.allclose(vv_read, vv)
        assert np.allclose(vh_read, vh)
    finally:
        os.unlink(filename)


def test_vv_vh_spectrum_equals_concatenated_components():
    module_path = Path(__file__).resolve().parents[2] / "chisurf" / "core" / "fluorescence" / "anisotropy" / "decay.py"
    spec = importlib.util.spec_from_file_location("anisotropy_decay_local", module_path)
    decay = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(decay)

    lifetime_spectrum = np.array([1.0, 3.0], dtype=float)
    anisotropy_spectrum = np.array([0.2, 1.0], dtype=float)

    vv = decay.calculcate_spectrum(lifetime_spectrum, anisotropy_spectrum, "VV")
    vh = decay.calculcate_spectrum(lifetime_spectrum, anisotropy_spectrum, "VH")
    vv_vh = decay.calculcate_spectrum(lifetime_spectrum, anisotropy_spectrum, "VV/VH")

    vv_flat = np.ravel(vv)
    vh_flat = np.ravel(vh)
    vv_vh_flat = np.ravel(vv_vh)

    assert vv_vh_flat.shape[0] == vv_flat.shape[0] + vh_flat.shape[0]
    assert np.allclose(vv_vh_flat[: vv_flat.shape[0]], vv_flat)
    assert np.allclose(vv_vh_flat[vv_flat.shape[0] :], vh_flat)

# --- FROM test_vv_vh_rebin_fix.py ---
import os
import tempfile
import importlib.util
from pathlib import Path

import numpy as np


def test_vv_vh_rebin_reshape_groups_are_stable():
    module_path = Path(__file__).resolve().parents[2] / "chisurf" / "core" / "fio" / "vv_vh.py"
    spec = importlib.util.spec_from_file_location("vv_vh_local", module_path)
    vv_vh = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(vv_vh)

    n_points = 2048
    x = np.linspace(0.0, 10.0, n_points)
    vv = np.exp(-x / 3.0) * 1000.0
    vh = np.exp(-x / 3.0) * 600.0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        filename = tmp.name

    try:
        vv_vh.write_vv_vh(filename, vv=vv, vh=vh, g_factor=1.0)
        data, _meta = vv_vh.read_vv_vh(filename, split=True, return_metadata=True)

        vv_read = np.asarray(data["VV"])
        vh_read = np.asarray(data["VH"])
        y = np.vstack([vv_read, vh_read])

        assert y.shape == (2, n_points)

        for rebin_y in (1, 2, 4, 8):
            new_channels = n_points // rebin_y
            y_rebinned = y.reshape([2, new_channels, rebin_y]).sum(axis=2)
            assert y_rebinned.shape == (2, new_channels)
    finally:
        os.unlink(filename)
