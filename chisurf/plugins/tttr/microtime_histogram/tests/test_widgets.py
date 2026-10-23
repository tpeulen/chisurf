"""Native file expansion, polarization and measured TAC-linearization guards."""

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.tttr.microtime_histogram.gui.model import HistogramModel


def _write_burst_container(raw: Path, first=1, last=5) -> Path:
    """A measurement with one burst run: the .pto provenance of a search."""
    import pandas as pd

    from chisurf.plugins.burst.burst_selection.api.io import write_container

    df = pd.DataFrame({"first photon": [first], "last photon": [last]})
    return Path(write_container(raw, df, parameters={"demo": 1}, run="demo search"))


def test_a_folder_expands_to_its_burst_containers(tmp_path):
    """Recursive folder input finds the .pto containers a search wrote."""
    (tmp_path / "burstwise").mkdir()
    (tmp_path / "burstwise" / "m000.pt3").write_bytes(b"x")
    _write_burst_container(tmp_path / "burstwise" / "m000.pt3")
    model = HistogramModel()
    model.add_paths([tmp_path], bursts=True)
    assert {Path(path).name for path in model.burst_files} == {"m000.pto"}


def test_a_folder_without_containers_stays_empty(tmp_path):
    """Unrelated inputs cannot become selected burst gates."""
    (tmp_path / "unrelated.txt").write_bytes(b"x")
    model = HistogramModel()
    model.add_paths([tmp_path], bursts=True)
    assert model.burst_files == []


_SPC = Path(__file__).resolve().parents[5] / "test/data/tttr/BH/132/BH_SPC132.spc"


@pytest.mark.skipif(not _SPC.is_file(), reason="sample SPC not available")
def test_setup_lut_linearizes_the_real_histogram_only_when_enabled():
    """Saved TAC LUTs affect the actual compute path; disabling the gate restores raw counts."""
    from chisurf.plugins.tttr.tttr_lut_tools.api import compute

    lut = np.asarray(
        compute.compute_lut_from_files([str(_SPC)], channel=0, linear_start=1500, linear_stop=3000)[
            "NTAC_fract"
        ]
    )
    model = HistogramModel()
    model.auto_save = False
    setup = {
        "detectors": {"green": {"chs": [0]}},
        "tttr_reading": {"file_type": "SPC-130"},
        "channel_luts": {"0": lut.tolist()},
        "apply_lut": False,
    }
    model.set_setup(setup)
    model.add_paths([_SPC])
    model.compute()
    raw = model.cumulative_parallel.copy()
    setup["apply_lut"] = True
    model.set_setup(setup)
    model.compute()
    assert not np.array_equal(raw, model.cumulative_parallel)
    setup["apply_lut"] = False
    model.set_setup(setup)
    model.compute()
    np.testing.assert_array_equal(raw, model.cumulative_parallel)


def test_polarization_resolved_gates_parallel_and_perpendicular():
    """Routing order alternates VV/VH when resolved and becomes one stream otherwise."""
    model = HistogramModel()
    setup = {"detectors": {"green": {"chs": [8, 0, 3, 9, 1, 2]}}, "polarization_resolved": True}
    model.set_setup(setup)
    assert model.parallel == [8, 3, 1]
    assert model.perpendicular == [0, 9, 2]
    setup["polarization_resolved"] = False
    model.set_setup(setup)
    assert model.parallel == [8, 0, 3, 9, 1, 2]
    assert model.perpendicular == []


@pytest.mark.skipif(not _SPC.is_file(), reason="sample SPC not available")
def test_unpolarized_export_contains_one_selected_stream_without_duplicate_photons(tmp_path):
    """An empty VH selection means no VH photons, rather than the provider's all-channel default."""
    import tttrlib

    model = HistogramModel()
    model.auto_save = False
    model.set_setup(
        {
            "polarization_resolved": False,
            "detectors": {"green": {"chs": [8, 0, 3]}},
            "tttr_reading": {"file_type": "SPC-130"},
        }
    )
    model.add_paths([_SPC])
    model.compute()
    stream = tttrlib.TTTR(str(_SPC), "SPC-130")
    raw, _ = stream.get_microtime_histogram(1, [8, 0, 3])
    np.testing.assert_array_equal(model.cumulative_parallel[: len(raw)], raw)
    assert np.count_nonzero(model.cumulative_parallel[len(raw) :]) == 0
    assert model.cumulative_perpendicular.sum() == 0
    selected = np.count_nonzero(np.isin(stream.routing_channels, [8, 0, 3]))
    assert model.cumulative_ps.sum() == selected == 135967
    np.testing.assert_array_equal(model.cumulative_ps, model.cumulative_parallel)
    output = tmp_path / "unpolarized.dat"
    model.save(output)
    np.testing.assert_array_equal(np.loadtxt(output), model.cumulative_ps)
