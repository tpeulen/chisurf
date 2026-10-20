"""Every computed ``.cor`` has a settings file beside it that reproduces it from the raw photons.

Correlate two short simulated streams (one cut to time regions, the photon filter on, three pieces of which the merge
uses two), save the merge, then compute it again from nothing but ``<name>.cor.json``: the same curve.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs.merge import merge_folder, save_mean_correlation
from chisurf.core.fluorescence.fcs.provenance import read_settings, settings_path
from chisurf.plugins.fcs.fcs_correlator.correlator_model import CorrelatorSettingsModel
from chisurf.plugins.fcs.fcs_correlator.filter_model import FilterSettingsModel
from chisurf.plugins.fcs.fcs_correlator.provenance import main, reproduce
from chisurf.plugins.fcs.fcs_correlator.workflow import FcsWorkflow
from chisurf.plugins.fcs.fcs_merger.gui.model import MergerModel

from .streams import diffusion_spc


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


def _merge(tmp_path, use_filter: bool):
    a = diffusion_spc(tmp_path, "a.spc", rate_hz=20.0, duration_s=2.0, seed=1)
    b = diffusion_spc(tmp_path, "b.spc", rate_hz=20.0, duration_s=2.0, seed=2)
    wf = FcsWorkflow()
    wf.set_files([str(a), str(b)], use_filter=use_filter, use_merger=True)
    wf.regions.set(a, [(0.2, 1.4)])
    fm = FilterSettingsModel()
    fm.filter_mode, fm.invert, fm.min_ph = "burst", True, 15
    if use_filter:
        wf.load_files_into_filter(fm)
    cm = CorrelatorSettingsModel()
    wf.apply_to_correlator(cm, fm)
    cm.n_splits, cm.n_casc, cm.channel_a, cm.channel_b = 3, 18, "0", "1"
    assert "3 chunk" in cm.correlate_data()
    cm.n_casc = 25  # changed after Correlate: the record holds what was used
    merger = MergerModel()
    curves, folder = wf.merger_input(cm)
    merger.set_correlations(curves, folder, provenance=wf.merger_provenance(cm))
    merger.use = [True, False, True]
    target = merger.save(tmp_path / "out" / "merged.cor")
    return target, merger, (a, b)


@pytest.mark.parametrize("use_filter", [False, True], ids=["raw", "filtered"])
def test_the_settings_file_reproduces_the_cor_from_the_raw_photons(tmp_path, use_filter):
    target, merger, (a, b) = _merge(tmp_path, use_filter)
    record = read_settings(settings_path(target))
    assert record["source"] == "photons"
    assert [e["name"] for e in record["inputs"]] == ["a.spc", "b.spc"]
    assert record["inputs"][0]["regions"] == [[0.2, 1.4]] and record["inputs"][1]["regions"] == []
    assert all(len(e["sha256"]) == 64 for e in record["inputs"])
    assert record["correlator"]["n_casc"] == 18 and record["correlator"]["n_splits"] == 3
    assert record["merge"]["chunks"] == [0, 2]
    assert (record["photon_filter"] is not None) == use_filter
    if use_filter:
        assert record["photon_filter"]["invert"] is True and record["photon_filter"]["min_ph"] == 15
    merged, curves = reproduce(settings_path(target))
    assert len(curves) == 3
    np.testing.assert_allclose(merged["y"], merger.mean_correlation["y"], rtol=0, atol=0)
    np.testing.assert_allclose(merged["x"], merger.mean_correlation["x"])
    saved = np.loadtxt(target, delimiter="\t")
    np.testing.assert_allclose(saved[:, 1], [float(f"{v:.5g}") for v in merged["y"]])


def test_a_changed_raw_file_is_refused(tmp_path):
    target, _merger, (a, _b) = _merge(tmp_path, False)
    with open(a, "ab") as fh:
        fh.write(b"\0" * 8)
    with pytest.raises(ValueError, match="checksum differs"):
        reproduce(target)


def test_command_line_reproduces_and_writes(tmp_path, capsys):
    target, _merger, _files = _merge(tmp_path, False)
    again = tmp_path / "again.cor"
    assert main([str(settings_path(target)), "-o", str(again)]) == 0
    out = capsys.readouterr().out
    assert "max |ΔG| against merged.cor: 0" in out
    assert np.array_equal(np.loadtxt(again), np.loadtxt(target))
    assert read_settings(again)["inputs"] == read_settings(target)["inputs"]


def test_every_written_cor_has_a_settings_file(tmp_path):
    """Guard: a .cor written without a record still says so, and a folder merge names its correlation files."""
    curve = {"x": [1e-3, 1e-2], "y": [1.5, 1.1], "duration": 1.0, "count_rate": 10.0}
    bare = save_mean_correlation(curve, tmp_path / "bare.cor")
    assert json.loads(bare.read_text())["source"] == "unknown"
    target, _merger, _files = _merge(tmp_path, False)
    merged = merge_folder(target.parent, tmp_path / "remerged.cor")
    record = read_settings(tmp_path / "remerged.cor")
    assert record["source"] == "correlations" and merged["n_curves"] == 1
    assert record["inputs"][0]["name"] == "merged.cor"
    with pytest.raises(ValueError, match="not from photons"):
        reproduce(record)


def test_the_workflow_hands_its_record_to_the_merger_and_the_cor_gets_it(tmp_path):
    """Through the hub: regions drawn in Files & Steps, Correlate, the merger's save writes the settings file."""
    from .test_emtk_workflow import _hub

    a = diffusion_spc(tmp_path, "a.spc", rate_hz=20.0, duration_s=2.0, seed=1)
    hub = _hub()
    hub.nav("files")
    files = hub.child
    files.add_paths([a])
    files.add_region(0.5, 1.5, str(a))
    hub.nav("correlator")
    hub.child.model.n_splits = 2
    hub.click("correlate")
    hub.wait_correlated()
    hub.nav("merger")
    target = hub.child.model.save(tmp_path / "hub.cor")
    record = read_settings(target)
    assert record["inputs"][0]["regions"] == [[0.5, 1.5]] and record["merge"]["chunks"] == [0, 1]
    merged, _curves = reproduce(record)
    np.testing.assert_array_equal(merged["y"], hub.child.model.mean_correlation["y"])
    hub.app.close()
