"""The pooled proximity-ratio Gaussian mixture is pinned on fixed data.

Guide 29 fits the proximity ratio of every burst of ten repeated BH SPC-130 files. Its caption once carried
numbers (PR 0.023 / 0.400) that no tool state reproduced: the retired Qt tool and the emtk app both give
0.031 / 0.428 on the same bursts (bit-identical data). These tests keep the pooled path honest: pooling is
the plain concatenation of the files' bursts, and the fit on it is the fit of a bare ``GaussianMixture``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_selection.tests.test_emtk_native_model import (  # noqa: F401
    DATA,
    SETUP,
    hermetic,
    model,
)


def _pooled_pr(model):  # noqa: F811
    model.hist_feature = "Proximity Ratio"
    model.pool_files = True
    return model.feature_data("Proximity Ratio")


def _bare_fit(pr, n):
    from chisurf.core.ml import GaussianMixture

    gm = GaussianMixture(
        n_components=n, covariance_type="full", random_state=42, max_iter=300, n_init=10, tol=1e-3,
        reg_covar=1e-6,
    ).fit(pr.reshape(-1, 1))
    order = np.argsort(gm.means_.ravel())
    return gm.means_.ravel()[order], np.sqrt(gm.covariances_.ravel())[order], gm.weights_[order]


def test_pooled_data_is_every_files_proximity_ratio_and_the_fit_is_the_bare_mixture(model):  # noqa: F811
    from chisurf.plugins.burst.burst_selection.api.features import proximity_ratio

    model.run()
    per_file = []
    for path in model.files:
        pr = proximity_ratio(model.frames_by_file[str(path)])
        per_file.append(pr[np.isfinite(pr)])
    pooled = _pooled_pr(model)
    assert pooled.size == sum(p.size for p in per_file) == 198
    np.testing.assert_allclose(pooled, np.concatenate(per_file), rtol=1e-5)

    model.gmm_components = 2
    rows = model.fit_gmm()["rows"]
    means, stds, weights = _bare_fit(pooled, 2)
    shown = sorted(rows, key=lambda r: float(r["mean"]))
    np.testing.assert_allclose([float(r["mean"]) for r in shown], means, atol=5e-4)
    np.testing.assert_allclose([float(r["std"]) for r in shown], stds, atol=5e-4)
    np.testing.assert_allclose([float(r["weight"]) for r in shown], weights, atol=5e-4)


def test_guide_29_numbers_on_the_ten_repeats(tmp_path, monkeypatch):
    """Ten files, 1130 bursts, three Gaussians: PR 0.031 (sigma 0.016, 0.35) and 0.428 (sigma 0.063, 0.47)."""
    import shutil

    from chisurf.plugins.burst.burst_selection.gui.model import BurstSelectionModel, save_setup

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "settings").mkdir()
    (tmp_path / "mmfdb").mkdir()
    folder = tmp_path / "spc"
    folder.mkdir()
    for spc in sorted(DATA.glob("m00*.spc")):
        shutil.copy(spc, folder)
    det = lambda chs: {"chs": chs, "micro_time_ranges": [[0, 4096]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}  # noqa: E731
    save_setup(
        "guide29",
        {
            "windows": {"prompt": [0, 4096]},
            "detectors": {"green": det([0, 8]), "red": det([1, 9])},
            "tttr_reading": {"file_type": "SPC-130", "micro_time_binning": 1},
        },
    )
    m = BurstSelectionModel()
    assert m.select_setup("guide29")
    m.add_paths(sorted(folder.glob("*.spc")))
    m.run()
    pooled = _pooled_pr(m)
    assert pooled.size == 1130
    m.gmm_components = 3
    rows = sorted(m.fit_gmm()["rows"], key=lambda r: float(r["mean"]))
    by_weight = sorted(rows, key=lambda r: -float(r["weight"]))
    donor_only = min(rows, key=lambda r: float(r["mean"]))
    assert float(donor_only["mean"]) == pytest.approx(0.031, abs=5e-4)
    assert float(donor_only["std"]) == pytest.approx(0.016, abs=5e-4)
    assert float(donor_only["weight"]) == pytest.approx(0.349, abs=2e-3)
    fret = by_weight[0]
    assert float(fret["mean"]) == pytest.approx(0.428, abs=5e-4)
    assert float(fret["std"]) == pytest.approx(0.063, abs=5e-4)
    assert float(fret["weight"]) == pytest.approx(0.466, abs=2e-3)
