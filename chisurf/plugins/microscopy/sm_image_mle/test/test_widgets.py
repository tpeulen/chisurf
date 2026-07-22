"""Smoke tests for the molecule-wise MLE AutoForm GUI."""

import pytest


def test_view_model_is_qt_free_and_binds_settings():
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    vm = MoleculeMleViewModel()
    # Scalar bindings proxy the core settings.
    vm.tau = 3.0
    assert vm.settings.tau == 3.0
    vm.detector_chs_text = "2 0"
    assert vm.settings.detector_chs == [2, 0]
    vm.mtr_start, vm.mtr_stop = 5, 200
    assert vm.settings.micro_time_range == (5, 200)
    # No results yet → empty accessors.
    assert vm.segmentation_image() is None
    assert vm.molecule_entries() == []
    assert vm.current_molecule_marker() == []
    assert vm.current_molecule_decay() == []
    ok, reason = vm.can_run()
    assert not ok and reason


def test_apply_setup_settings_carries_polarisation_corrections():
    # Regression: g_factor/l1/l2 from the shared detector setup used to be
    # dropped, and g_factor was later overwritten by the IRF-tail estimate.
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    vm = MoleculeMleViewModel()
    vm.apply_setup_settings(
        {
            "detectors": {
                "green": {
                    "chs": [0, 1],
                    "mtr": [(5, 200)],
                    "g_factor": 1.2,
                    "l1": 0.03,
                    "l2": 0.05,
                }
            }
        }
    )
    assert vm.settings.detector_chs == [0, 1]
    assert vm.settings.micro_time_range == (5, 200)
    assert vm.settings.g_factor == pytest.approx(1.2)
    assert vm.settings.l1 == pytest.approx(0.03)
    assert vm.settings.l2 == pytest.approx(0.05)
    # The setup value is authoritative: the IRF-tail auto-estimate is disabled.
    assert vm.settings.auto_g_factor is False


def test_view_spec_loads():
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    spec = MoleculeMleViewModel().view_spec()
    assert spec is not None
    assert spec.sections


def test_load_analysis_from_disk(tmp_path):
    import numpy as np
    import pandas as pd

    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    analysis = tmp_path / "cell_analysis"
    analysis.mkdir()
    pd.DataFrame({
        "source_ptu": [str(tmp_path / "cell.ptu")] * 2,
        "label": [1, 2],
        "centroid_row": [8.0, 23.0],
        "centroid_col": [8.0, 23.0],
        "n_photons_total": [220, 300],
        "tau": [1.02, 3.48],
        "gamma": [0.0, 0.0],
        "rho": [1.0, 1.0],
        "2I*": [0.4, 0.6],
    }).to_csv(analysis / "molecule_data.tsv", sep="\t", index=False)
    np.save(analysis / "intensity.npy", np.arange(16.0).reshape(4, 4))

    vm = MoleculeMleViewModel()
    vm.results_tsv = str(analysis / "molecule_data.tsv")

    assert len(vm.results) == 1
    assert vm.results[0].n_molecules == 2
    assert vm.segmentation_image().shape == (4, 4)
    assert vm.current_molecule_marker() == [(0, 8.0, 8.0)]
    entries = vm.molecule_entries()
    assert [e["badge"] for e in entries] == ["τ=1.02 ns", "τ=3.48 ns"]
    # No curves persisted → decay is empty for a reopened analysis.
    assert vm.current_molecule_decay() == []


def test_preview_without_files_reports_status():
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    vm = MoleculeMleViewModel()
    vm.preview_segmentation()
    assert "no imaging files" in vm.status_text.lower()


def test_unfitted_molecules_show_area_badge():
    import numpy as np
    import pandas as pd

    from chisurf.plugins.microscopy.sm_image_mle.core.molecule_mle import MoleculeMleResult
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    vm = MoleculeMleViewModel()
    vm.results = [MoleculeMleResult(
        dataframe=pd.DataFrame({"label": [1, 2], "area": [7, 12], "tau": [np.nan, np.nan],
                                "centroid_row": [1.0, 2.0], "centroid_col": [1.0, 2.0]}),
        intensity_image=np.zeros((4, 4)),
        label_image=np.zeros((4, 4), dtype=int),
        centroids=np.array([[1.0, 1.0], [2.0, 2.0]]),
    )]
    assert [e["badge"] for e in vm.molecule_entries()] == ["7 px", "12 px"]


def test_pipeline_and_calibration_hooks():
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    vm = MoleculeMleViewModel()
    vm.apply_pipeline_context({"source": "/data/cell.ptu"})
    assert vm.files == ["/data/cell.ptu"]
    # Idempotent — the same source is not added twice.
    vm.apply_pipeline_context({"source": "/data/cell.ptu"})
    assert vm.files == ["/data/cell.ptu"]

    vm.apply_calibration({"green": {"irf": ["/data/irf.ptu"], "conv_start": 10, "conv_stop": 200}})
    assert vm.irf_files == ["/data/irf.ptu"]
    assert vm.settings.micro_time_range == (10, 200)


def test_export_results_writes_combined_table(tmp_path):
    import numpy as np
    import pandas as pd

    from chisurf.plugins.microscopy.sm_image_mle.core.molecule_mle import MoleculeMleResult
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    def _res(labels, taus):
        return MoleculeMleResult(
            dataframe=pd.DataFrame({"label": labels, "tau": taus}),
            intensity_image=np.zeros((2, 2)),
            label_image=np.zeros((2, 2), dtype=int),
            centroids=np.zeros((len(labels), 2)),
        )

    vm = MoleculeMleViewModel()
    assert not vm.has_results()
    vm.results = [_res([1, 2], [1.0, 2.0]), _res([1], [3.0])]
    assert vm.has_results()

    out = tmp_path / "molecules.tsv"
    written = vm.export_results(str(out))
    assert written == str(out)
    df = pd.read_csv(out, sep="\t")
    assert len(df) == 3
    assert set(df["tau"]) == {1.0, 2.0, 3.0}


def test_tool_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.microscopy.sm_image_mle.gui.tool import SmImageMleTool

    widget = SmImageMleTool()
    qtbot.addWidget(widget)
    assert widget.windowTitle() == "Molecule-wise MLE"
    assert hasattr(widget, "auto_form")
    assert hasattr(widget, "model")
