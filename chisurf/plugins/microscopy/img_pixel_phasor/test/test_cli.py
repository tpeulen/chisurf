"""Headless CLI smoke tests for the phasor plugin (PRD-55 acceptance).

Covers the acceptance item "derived maps are produced through the plugin's
``cli/main.py``": with a modulation frequency supplied, the CLI emits per-pixel
apparent-lifetime maps (``tau_phi`` / ``tau_m``) and persists them to HDF5. The
TTTR-reading ``compute_phasor`` is monkeypatched with synthetic phasor maps so
the test needs no imaging file, and the HDF5 writer is stubbed so no h5py I/O is
required — the derived-map math itself is covered by ``test_analysis.py``.
"""
from __future__ import annotations

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.plugins.microscopy.img_pixel_phasor import analysis, core
from chisurf.plugins.microscopy.img_pixel_phasor.cli.main import cli


def _synthetic_result() -> dict:
    """Return a compute_phasor-shaped result with finite phasor coordinates."""
    g = np.array([[0.5, 0.6], [0.7, 0.55]])
    s = np.array([[0.45, 0.40], [0.35, 0.42]])
    n = np.ones((2, 2))
    return {"maps": {"g": g, "s": s, "n_photons": n}, "shape": (2, 2)}


def test_derived_phasor_maps_adds_tau_maps() -> None:
    maps = _synthetic_result()["maps"]
    out = core.derived_phasor_maps(maps, 80.0)

    assert set(core.DERIVED_MAP_FIELDS) <= set(out)
    assert out["tau_phi"].shape == maps["g"].shape
    tau_phi, tau_m = analysis.phasor_to_apparent_lifetime(maps["g"], maps["s"], 80.0)
    np.testing.assert_allclose(out["tau_phi"], tau_phi)
    np.testing.assert_allclose(out["tau_m"], tau_m)
    assert "tau_phi" not in maps  # input not mutated


def test_derived_phasor_maps_requires_positive_frequency() -> None:
    with pytest.raises(ValueError):
        core.derived_phasor_maps({"g": np.zeros(1), "s": np.zeros(1)}, -1.0)


def test_cli_produces_and_writes_derived_maps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(core, "compute_phasor", lambda *a, **k: _synthetic_result())
    written: dict = {}
    monkeypatch.setattr(
        core, "add_maps_to_hdf5",
        lambda path, keep: written.update(keys=sorted(keep)) or sorted(keep),
    )

    infile = tmp_path / "img.ptu"
    infile.write_bytes(b"stub")
    out = tmp_path / "phasor.h5"
    res = CliRunner().invoke(cli, [str(infile), "--frequency", "80", "-o", str(out)])

    assert res.exit_code == 0, res.output
    assert "tau_phi" in res.output and "tau_m" in res.output
    assert "tau_phi" in written["keys"] and "tau_m" in written["keys"]


def test_cli_without_frequency_skips_derived_maps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(core, "compute_phasor", lambda *a, **k: _synthetic_result())
    infile = tmp_path / "img.ptu"
    infile.write_bytes(b"stub")
    res = CliRunner().invoke(cli, [str(infile)])

    assert res.exit_code == 0, res.output
    assert "tau_phi" not in res.output
    assert "--frequency" in res.output
