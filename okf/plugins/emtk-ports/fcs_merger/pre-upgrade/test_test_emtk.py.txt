"""Native merge selection and real Kristine output."""

import numpy as np

from chisurf.plugins.fcs.fcs_merger.gui.app import create_app


def curve(offset):
    return {
        "x": [0, 1, 2, 3],
        "y": [2, 1 + offset, 0.5 + offset, 0.25 + offset],
        "duration": 10,
        "count_rate": 20,
        "channel_a": {"counts": 200000},
        "channel_b": {"counts": 200000},
    }


def test_native_selection_and_none_checked_compatibility():
    app = create_app()
    app.set_correlations([curve(0), curve(2)])
    app.use = [True, False]
    np.testing.assert_allclose(app.mean_correlation["y"], [1, 0.5, 0.25])
    app.use = [False, False]
    np.testing.assert_allclose(app.mean_correlation["y"], [2, 1.5, 1.25])
    app.close()


def test_native_save_and_add_dataset(tmp_path):
    added = []
    app = create_app(add_dataset=added.append)
    app.set_correlations([curve(0), curve(0.2)], source_folder=tmp_path / "chunks")
    path = tmp_path / "merged.cor"
    assert app.save(path, add=True)
    app.job.future.result(timeout=5)
    app.job.poll()
    data = np.loadtxt(path)
    assert data.shape == (3, 4)
    assert data[0, 2] == 20
    assert data[1, 2] == 20
    assert added == [path]
    app.close()


def test_native_load_cor_folder(tmp_path):
    array = np.array([[0, 2, 10], [1, 1, 20], [2, 0.5, 0], [3, 0.25, 0]])
    np.savetxt(tmp_path / "first.cor", array, delimiter="\t")
    app = create_app()
    assert app.load_folder(tmp_path)
    app.job.future.result(timeout=5)
    app.job.poll()
    assert app.labels == ["first.cor"]
    assert app.mean_correlation["count_rate"] == 20
    assert len(app.mean_correlation["y"]) == 3
    app.close()


def test_native_folder_restore_keeps_selection_and_output(tmp_path):
    for i in range(2):
        np.savetxt(
            tmp_path / f"{i}.cor",
            [[0, 2, 10], [1, 1 + i, 20], [2, 0.5, 0], [3, 0.25, 0]],
            delimiter="\t",
        )
    app = create_app()
    app.restore_state(
        {
            "folder": str(tmp_path),
            "output": str(tmp_path / "saved.cor"),
            "use": [False, True],
            "selected": 1,
        }
    )
    app.job.future.result(timeout=5)
    app.job.poll()
    assert app.use == [False, True]
    assert app.selected == 1
    assert app.output == str(tmp_path / "saved.cor")
    app.close()


def test_native_rejects_different_lag_grids_before_wrong_average():
    import pytest

    app = create_app()
    other = curve(1)
    other["x"] = [0, 10, 20, 30]
    with pytest.raises(ValueError, match="lag grid"):
        app.set_correlations([curve(0), other])
    assert app.correlations == []
    app.close()
