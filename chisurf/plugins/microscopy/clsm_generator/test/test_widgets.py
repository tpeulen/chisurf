"""Tests for the CLSM Generator GUI (Qt-free view-model + AutoForm tool)."""

from __future__ import annotations

import numpy as np
import pytest


def test_view_model_loads_maps_and_gates_generation(tmp_path):
    from chisurf.plugins.microscopy.clsm_generator.gui.view_model import ClsmGeneratorViewModel

    vm = ClsmGeneratorViewModel()
    ok, reason = vm.can_generate()
    assert not ok and "intensity" in reason.lower()

    inten = tmp_path / "i.npy"
    life = tmp_path / "l.npy"
    np.save(inten, np.ones((8, 8)))
    np.save(life, np.full((8, 8), 2.0))

    vm.sel_intensity = str(inten)
    vm.sel_lifetime_files = [str(life)]
    ok, reason = vm.can_generate()
    assert ok, reason

    # Views list the loaded inputs (reconstruction appears after generate).
    ids = [e["id"] for e in vm.view_entries()]
    assert ids == ["intensity_in", "lifetime_in_0"]
    assert vm.current_view_image().shape == (8, 8)


def test_shape_mismatch_is_reported(tmp_path):
    from chisurf.plugins.microscopy.clsm_generator.gui.view_model import ClsmGeneratorViewModel

    inten = tmp_path / "i.npy"
    life = tmp_path / "l.npy"
    np.save(inten, np.ones((8, 8)))
    np.save(life, np.full((6, 6), 2.0))

    vm = ClsmGeneratorViewModel()
    vm.sel_intensity = str(inten)
    vm.sel_lifetime_files = [str(life)]
    ok, reason = vm.can_generate()
    assert not ok and "match" in reason.lower()


def test_view_spec_loads():
    from chisurf.plugins.microscopy.clsm_generator.gui.view_model import ClsmGeneratorViewModel

    spec = ClsmGeneratorViewModel().view_spec()
    assert spec is not None and spec.sections


@pytest.mark.skipif(
    not __import__(
        "chisurf.core.fluorescence.imaging.simulate", fromlist=["have_simulator"]
    ).have_simulator(),
    reason="tttrlib photon simulator unavailable",
)
def test_generate_and_save_roundtrip(tmp_path):
    from chisurf.plugins.microscopy.clsm_generator.gui.view_model import ClsmGeneratorViewModel

    inten = tmp_path / "i.npy"
    life = tmp_path / "l.npy"
    np.save(inten, np.ones((16, 16)))
    np.save(life, np.full((16, 16), 2.0))

    vm = ClsmGeneratorViewModel()
    vm.n_lifetime_levels = 4
    vm.n_intensity_levels = 3
    vm.sel_intensity = str(inten)
    vm.sel_lifetime_files = [str(life)]
    vm.generate()

    assert vm.has_result()
    assert vm.current_view == "recon"
    assert vm.current_view_image().shape == (16, 16)
    assert "lifetime_in_0" in [e["id"] for e in vm.view_entries()]
    assert "recon" in [e["id"] for e in vm.view_entries()]

    out = tmp_path / "sim.npz"
    written = vm.save(str(out))
    assert written == str(out)
    assert out.exists()
    with np.load(out) as data:
        assert "macro_times" in data
        assert len(data["macro_times"]) > 0


@pytest.mark.parametrize("suffix", [".ptu", ".pto"])
def test_a_saved_scan_opens_in_the_imaging_steps_as_it_is(tmp_path, suffix):
    """Drop the generator's file on *1. Intensity*: the step must see the 16x16 scan, not ``0x0 px``."""
    import json

    from chisurf.core.fluorescence.imaging.pixel_maps import build_clsm
    from chisurf.plugins.microscopy.clsm_generator.gui.view_model import ClsmGeneratorViewModel

    inten, life = tmp_path / "i.npy", tmp_path / "l.npy"
    np.save(inten, np.ones((16, 16)))
    np.save(life, np.full((16, 16), 2.0))
    vm = ClsmGeneratorViewModel()
    vm.n_lifetime_levels, vm.n_intensity_levels = 2, 2
    vm.sel_intensity, vm.sel_lifetime_files = str(inten), [str(life)]
    vm.generate()
    out = tmp_path / f"scan{suffix}"
    assert vm.save(str(out)) == str(out)
    import tttrlib

    image = np.asarray(build_clsm(tttrlib.TTTR(str(out)), channels=(0,)).intensity).sum(axis=0)
    np.testing.assert_array_equal(image, np.asarray(vm._sim.intensity))
    layout = json.loads(out.with_suffix(".json").read_text())["scan_layout"]
    assert layout == {"kind": "chisurf-simulated-raster", "n_pixel_per_line": 16}
