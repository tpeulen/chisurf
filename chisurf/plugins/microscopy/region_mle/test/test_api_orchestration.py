"""Headless tests for the molecule-wise MLE API orchestration.

Exercises ``analyze_request`` — the per-file loop, per-file TSV writing and the
joint merge — without tttrlib by stubbing the Qt-free core fit.  The science
itself is covered by :mod:`test.test_region_mle_core`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from chisurf.plugins.microscopy.region_mle.api.models import (
    RegionMleRequest,
    RegionMleSettings,
)


def _fake_result(n_molecules: int):
    from chisurf.plugins.microscopy.region_mle.core.region_mle import RegionMleResult

    df = pd.DataFrame(
        {
            "label": np.arange(1, n_molecules + 1),
            "tau": np.linspace(1.0, 3.0, n_molecules),
            "n_photons_total": np.full(n_molecules, 500),
        }
    )
    return RegionMleResult(
        dataframe=df,
        intensity_image=np.zeros((4, 4)),
        label_image=np.zeros((4, 4), dtype=int),
        centroids=np.zeros((n_molecules, 2)),
    )


def test_analyze_request_writes_per_file_and_joint_tsv(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.region_mle.api import region_mle as api

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

    monkeypatch.setattr(api, "fit_regions_from_files", fake_fit)

    request = RegionMleRequest(
        files=[str(f1), str(f2)],
        irf_file=str(irf),
        output_dir=str(tmp_path),
        settings=RegionMleSettings(),
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
    from chisurf.plugins.microscopy.region_mle.api import region_mle as api

    good = tmp_path / "good.ptu"
    bad = tmp_path / "bad.ptu"
    good.write_bytes(b"")
    bad.write_bytes(b"")

    def fake_fit(ptu_path, irf_path, settings, **kwargs):
        from pathlib import Path

        if Path(ptu_path).name == "bad.ptu":
            raise RuntimeError("boom")
        return _fake_result(2)

    monkeypatch.setattr(api, "fit_regions_from_files", fake_fit)

    request = RegionMleRequest(
        files=[str(good), str(bad)],
        irf_file=str(tmp_path / "irf.ptu"),
        output_dir=str(tmp_path),
    )
    result = api.analyze_request(request)

    assert result.processed_files == [str(good)]
    assert result.n_molecules == 2
    assert any("boom" in w for w in result.warnings)


# --- the CLI's analysis region ----------------------------------------------
def test_cli_roi_option_reaches_the_settings(tmp_path, monkeypatch):
    """``--roi FILE`` loads the region and hands it to the analysis.

    The region only mattered from Python before: the setting existed, shaped
    the analysis, and no command line could set it. The option accepts every
    form ``load_region`` does, and several regions in one file arrive as their
    union — so a saved segmentation works as an analysis mask.
    """
    from click.testing import CliRunner

    from chisurf.core.roi import RectangleROI, save_rois
    from chisurf.plugins.microscopy.region_mle.api import region_mle as api
    from chisurf.plugins.microscopy.region_mle.cli.main import cli

    roi_file = tmp_path / "patch.json"
    save_rois(
        [RectangleROI(0, 0, 16, 16, name="left"),
         RectangleROI(32, 32, 48, 48, name="right")],
        str(roi_file),
    )
    image = tmp_path / "img.ptu"
    irf = tmp_path / "irf.ptu"
    image.write_bytes(b"")
    irf.write_bytes(b"")

    seen = {}

    def fake_fit(ptu_path, irf_path, settings, **kwargs):
        seen['roi'] = settings.analysis_roi()
        return _fake_result(1)

    monkeypatch.setattr(api, "fit_regions_from_files", fake_fit)

    result = CliRunner().invoke(
        cli,
        ["analyze", "-i", str(irf), "-o", str(tmp_path),
         "--roi", str(roi_file), str(image)],
    )
    assert result.exit_code == 0, result.output

    roi = seen['roi']
    assert roi is not None
    # The union covers both rectangles and nothing between them.
    inside = roi.contains(np.array([[8.0, 8.0], [40.0, 40.0], [24.0, 24.0]]))
    assert inside.tolist() == [True, True, False]


def test_cli_without_roi_leaves_the_whole_frame(tmp_path, monkeypatch):
    """Omitting the option must not smuggle in an empty region."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.region_mle.api import region_mle as api
    from chisurf.plugins.microscopy.region_mle.cli.main import cli

    image = tmp_path / "img.ptu"
    irf = tmp_path / "irf.ptu"
    image.write_bytes(b"")
    irf.write_bytes(b"")

    seen = {}

    def fake_fit(ptu_path, irf_path, settings, **kwargs):
        seen['roi'] = settings.analysis_roi()
        return _fake_result(1)

    monkeypatch.setattr(api, "fit_regions_from_files", fake_fit)

    result = CliRunner().invoke(
        cli, ["analyze", "-i", str(irf), "-o", str(tmp_path), str(image)]
    )
    assert result.exit_code == 0, result.output
    assert seen['roi'] is None
