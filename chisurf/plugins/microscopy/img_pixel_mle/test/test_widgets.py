"""Smoke tests for the pixel-wise MLE AutoForm GUI."""

import pytest


def test_view_model_is_qt_free_and_binds_settings():
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel

    vm = PixelMleViewModel()
    # Scalar bindings proxy the API settings.
    vm.tau = 3.0
    assert vm.settings.tau == 3.0
    vm.channels_parallel_text = "0 4"
    vm.channels_perpendicular_text = "1, 5"
    assert vm.settings.detector_chs_p == [0, 4]
    assert vm.settings.detector_chs_s == [1, 5]
    vm.micro_time_start, vm.micro_time_stop = 5, 200
    assert vm.settings.micro_time_start == 5
    assert vm.settings.micro_time_stop == 200
    # Engine / worker bindings.
    vm.engine = "fast"
    assert vm.settings.engine == "fast"
    vm.n_workers = 0
    assert vm.settings.n_workers is None
    vm.n_workers = 4
    assert vm.settings.n_workers == 4
    # No results yet → empty accessors.
    assert vm.tau_map_image() is None
    assert vm.result_file_names() == []
    ok, reason = vm.can_run()
    assert not ok and reason


def test_can_run_guards_channels_and_window():
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel

    vm = PixelMleViewModel()
    vm.files = ["a.ptu"]
    vm.irf_files = ["irf.ptu"]
    vm.micro_time_start, vm.micro_time_stop = 100, 50  # empty window
    ok, reason = vm.can_run()
    assert not ok and "window" in reason.lower()
    vm.micro_time_start, vm.micro_time_stop = 0, 256
    ok, _ = vm.can_run()
    assert ok


def test_apply_calibration_carries_irf_and_window():
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel

    vm = PixelMleViewModel()
    vm.apply_calibration(
        {
            "Green": {
                "irf": ["irf.ptu"],
                "bg_vv": 2.0,
                "bg_vh": 1.0,
                "conv_start": 10,
                "conv_stop": 300,
            },
        }
    )
    assert vm.irf_files == ["irf.ptu"]
    assert vm.settings.use_bg is True
    assert vm.settings.bg_p == 2.0 and vm.settings.bg_s == 1.0
    assert vm.settings.micro_time_start == 10
    assert vm.settings.micro_time_stop == 300


def test_apply_setup_settings_carries_polarisation_corrections():
    # Regression: g_factor/l1/l2 from the shared detector setup used to be
    # dropped, so the fit silently ran at g=1, l1=l2=0.
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel

    vm = PixelMleViewModel()
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
    assert vm.settings.detector_chs_p == [0]
    assert vm.settings.detector_chs_s == [1]
    assert vm.settings.micro_time_start == 5 and vm.settings.micro_time_stop == 200
    assert vm.settings.g_factor == pytest.approx(1.2)
    assert vm.settings.l1 == pytest.approx(0.03)
    assert vm.settings.l2 == pytest.approx(0.05)


def test_view_spec_loads():
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel

    spec = PixelMleViewModel().view_spec()
    assert spec is not None
    assert spec.sections


def test_tool_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.microscopy.img_pixel_mle.gui.tool import ImgPixelMleTool

    widget = ImgPixelMleTool()
    qtbot.addWidget(widget)
    assert widget.windowTitle() == "Pixel-wise MLE"
    assert hasattr(widget, "auto_form")
    assert hasattr(widget, "model")
