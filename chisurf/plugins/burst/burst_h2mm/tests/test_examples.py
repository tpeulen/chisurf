"""Example-data generator + end-to-end file-based analysis test."""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings, StreamSettings
from chisurf.plugins.burst.burst_h2mm.backend.services import (
    run_analysis,
    write_result_tables,
)
from chisurf.plugins.burst.burst_h2mm.examples.generate_example_data import (
    generate_example_data,
)

pytest.importorskip("tttrlib")
pytest.importorskip("tables")  # pandas HDF5 backend for the ndX output


def test_generate_and_analyze_example_dataset(tmp_path):
    """The generated .bur + Photon-HDF5 loads and fits through the real pipeline."""
    bur_path, tttr_path = generate_example_data(tmp_path, n_bursts=120, burst_len=80, seed=1)
    assert bur_path.exists() and tttr_path.exists()
    assert tttr_path.name.endswith(".photon.h5")

    settings = H2mmSettings(
        streams=[StreamSettings("donor", [0]), StreamSettings("acceptor", [1])],
        min_states=1,
        max_states=2,
        n_restarts=1,
        max_iter=200,
        min_photons=5,
        file_type="auto",  # Photon-HDF5 is auto-detected
    )
    result, bundle = run_analysis(settings, analysis_folder=str(tmp_path))

    # Two clearly-separated states were simulated → recovered.
    assert result.n_bursts > 0
    assert result.n_states == 2
    e = sorted(result.fret)
    assert e[0] < 0.4 < e[1]

    # The defined output set is written and openable.
    out_dir = tmp_path / "h2mm"
    write_result_tables(result, bundle, out_dir)
    assert (out_dir / "h2mm_result.json").exists()
    assert (out_dir / "h2mm_photons.h5").exists() or (out_dir / "h2mm_photons.csv").exists()
    assert (out_dir / "h2mm_bursts.csv").exists()
    assert pathlib.Path(result.output_paths["result_json"]).exists()


def test_packing_simulated_bursts_keeps_the_photons_it_was_given():
    """``Last Photon`` is inclusive, and the packer is where that is decided.

    Seven call sites used to write this by hand and two of the spellings
    disagreed: ``off + len(burst)`` rather than ``off + len(burst) - 1``. Because
    the reader slices to ``last + 1``, the first spelling handed every burst the
    **next** burst's first photon — one extra sample, carrying the whole
    inter-burst gap with it. Nothing failed, because the tests that used it
    asserted on fitted parameters rather than on counts, and one alien photon in
    thirty moves a rate very little.

    A dwell time is a different matter: the injected gap is the inter-burst
    separation, orders of magnitude longer than any real inter-photon time, and a
    propagator reads it as the chain relaxing to equilibrium at the end of every
    burst.
    """
    import numpy as np

    from chisurf.plugins.burst.burst_h2mm.core.photons import (
        StreamDef,
        bursts_from_dataframe,
        pack_simulated_bursts,
    )

    rng = np.random.default_rng(0)
    times = [
        np.concatenate([[0], np.cumsum(rng.poisson(4, 29) + 1)]).astype(np.int64) for _ in range(5)
    ]
    streams = [rng.integers(0, 2, t.size) for t in times]
    definitions = [StreamDef(f"s{i}", [i]) for i in range(2)]

    tttr, frame = pack_simulated_bursts(times, streams)
    photons = bursts_from_dataframe(frame, {"sim.spc": tttr}, definitions, min_photons=1)

    counts = np.diff(photons.burst_offsets)
    assert list(counts) == [int(t.size) for t in times]
    # No photon of one burst may be an inter-burst gap away from its neighbour.
    assert int(photons.unique_dt.max()) < 1000
