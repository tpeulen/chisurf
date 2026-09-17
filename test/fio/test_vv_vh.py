# Consolidated test file: test_vv_vh.py


# --- FROM test_vv_vh_io_and_anisotropy.py ---
import importlib.util
import os
import tempfile
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
    module_path = (
        Path(__file__).resolve().parents[2]
        / "chisurf"
        / "core"
        / "fluorescence"
        / "anisotropy"
        / "decay.py"
    )
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


# --- footer metadata regressions (found via the synthetic-decay aniso round trip) ---


def _load_vv_vh():
    module_path = Path(__file__).resolve().parents[2] / "chisurf" / "core" / "fio" / "vv_vh.py"
    spec = importlib.util.spec_from_file_location("vv_vh_local_footer", module_path)
    vv_vh = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(vv_vh)
    return vv_vh


def test_vv_vh_footer_metadata_readable_for_positive_only_data():
    """An all-positive VV/VH file keeps its footer metadata.

    The legacy footer detector keyed off the first line containing a negative
    number, so a decay that never goes negative lost its g_factor/l1/l2 footer
    and the calibration silently fell back to the reader's defaults.
    """
    vv_vh = _load_vv_vh()

    n_points = 64
    x = np.linspace(0.0, 10.0, n_points)
    vv = np.exp(-x / 3.0) * 1000.0  # strictly positive
    vh = np.exp(-x / 3.0) * 600.0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        filename = tmp.name

    try:
        vv_vh.write_vv_vh(
            filename,
            vv=vv,
            vh=vh,
            g_factor=1.6,
            metadata={"l1": 0.05, "l2": 0.08, "polarization": "vv/vh"},
        )
        data, meta = vv_vh.read_vv_vh(filename, split=True, return_metadata=True)
        assert meta.get("g_factor") == 1.6
        assert meta.get("l1") == 0.05
        assert meta.get("l2") == 0.08
        assert meta.get("polarization") == "vv/vh"
        assert set(data.keys()) == {"VV", "VH"}
    finally:
        os.unlink(filename)


def test_vv_vh_footer_metadata_keys_are_not_prefixed_with_comments():
    """Footer keys must survive the '# ' comment markers savetxt writes.

    _parse_footer_metadata used to keep the marker in the key ('# #g_factor'),
    so every lookup (g_factor, channels, format_version) missed even when the
    footer itself was found.
    """
    vv_vh = _load_vv_vh()

    n_points = 16
    rng = np.random.default_rng(2)
    vv = rng.poisson(500, n_points).astype(float)
    vh = rng.poisson(300, n_points).astype(float)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        filename = tmp.name

    try:
        vv_vh.write_vv_vh(filename, vv=vv, vh=vh, g_factor=1.2, metadata={"k": "v"})
        _data, meta = vv_vh.read_vv_vh(filename, split=True, return_metadata=True)
        assert "g_factor" in meta and meta["g_factor"] == 1.2
        assert "channels" in meta and meta["channels"] == "VV, VH"
        assert "format_version" in meta
        assert meta.get("k") == "v"
    finally:
        os.unlink(filename)


def test_vv_vh_negative_data_footer_detection_unchanged():
    """Files with negative values still split at the negative separator."""
    vv_vh = _load_vv_vh()

    n_points = 32
    rng = np.random.default_rng(3)
    vv = rng.poisson(500, n_points).astype(float) - 50.0  # contains negatives
    vh = rng.poisson(300, n_points).astype(float)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        filename = tmp.name

    try:
        vv_vh.write_vv_vh(filename, vv=vv, vh=vh, g_factor=0.9)
        data, meta = vv_vh.read_vv_vh(filename, split=True, return_metadata=True)
        assert meta.get("g_factor") == 0.9
        assert np.allclose(data["VV"], vv)
        assert np.allclose(data["VH"], vh)
    finally:
        os.unlink(filename)
