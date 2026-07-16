"""Headless tests for the molecule-wise MLE API orchestration.

Exercises ``analyze_request`` — the per-file loop, per-file TSV writing and the
joint merge — without tttrlib by stubbing the Qt-free core fit.  The science
itself is covered by :mod:`test.test_molecule_mle_core`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from chisurf.plugins.microscopy.sm_image_mle.api.models import (
    MoleculeMleRequest,
    MoleculeMleSettings,
)


def _fake_result(n_molecules: int):
    from chisurf.plugins.microscopy.sm_image_mle.core.molecule_mle import MoleculeMleResult

    df = pd.DataFrame(
        {
            "label": np.arange(1, n_molecules + 1),
            "tau": np.linspace(1.0, 3.0, n_molecules),
            "n_photons_total": np.full(n_molecules, 500),
        }
    )
    return MoleculeMleResult(
        dataframe=df,
        intensity_image=np.zeros((4, 4)),
        label_image=np.zeros((4, 4), dtype=int),
        centroids=np.zeros((n_molecules, 2)),
    )


def test_analyze_request_writes_per_file_and_joint_tsv(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.sm_image_mle.api import molecule_mle as api

    f1 = tmp_path / "img1.ptu"
    f2 = tmp_path / "img2.ptu"
    f1.write_bytes(b"")
    f2.write_bytes(b"")
    irf = tmp_path / "irf.ptu"
    irf.write_bytes(b"")

    counts = {"img1.ptu": 3, "img2.ptu": 2}

    def fake_fit(ptu_path, irf_path, settings, **kwargs):
        from pathlib import Path

        return _fake_result(counts[Path(ptu_path).name])

    monkeypatch.setattr(api, "fit_molecules_from_files", fake_fit)

    request = MoleculeMleRequest(
        files=[str(f1), str(f2)],
        irf_file=str(irf),
        output_dir=str(tmp_path),
        settings=MoleculeMleSettings(),
    )
    result = api.analyze_request(request)

    assert result.processed_files == [str(f1), str(f2)]
    assert result.n_molecules == 5
    assert len(result.output_paths) == 2
    assert not result.warnings

    # Per-file TSVs exist and carry the source column.
    for out in result.output_paths:
        df = pd.read_csv(out, sep="\t")
        assert "source_ptu" in df.columns
        assert "tau" in df.columns

    # Joint TSV merges both files.
    joint = pd.read_csv(result.joint_tsv, sep="\t")
    assert len(joint) == 5
    assert set(joint["source_ptu"].unique()) == {str(f1), str(f2)}


def test_analyze_request_reports_failures_as_warnings(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.sm_image_mle.api import molecule_mle as api

    good = tmp_path / "good.ptu"
    bad = tmp_path / "bad.ptu"
    good.write_bytes(b"")
    bad.write_bytes(b"")

    def fake_fit(ptu_path, irf_path, settings, **kwargs):
        from pathlib import Path

        if Path(ptu_path).name == "bad.ptu":
            raise RuntimeError("boom")
        return _fake_result(2)

    monkeypatch.setattr(api, "fit_molecules_from_files", fake_fit)

    request = MoleculeMleRequest(
        files=[str(good), str(bad)],
        irf_file=str(tmp_path / "irf.ptu"),
        output_dir=str(tmp_path),
    )
    result = api.analyze_request(request)

    assert result.processed_files == [str(good)]
    assert result.n_molecules == 2
    assert any("boom" in w for w in result.warnings)
