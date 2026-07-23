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


def _param_value_attrs(spec):
    """Return the ``attr`` of every value row inside the injected fit-parameter panel."""
    attrs = []

    def walk(sections):
        for s in sections:
            if getattr(s, "title", "") and str(s.title).startswith("Fit parameters"):
                for row in getattr(s, "sections", []) or []:
                    a = getattr(row, "attr", "")
                    if getattr(row, "type", "") == "value" or a.endswith("_value"):
                        attrs.append(a)
            walk(getattr(s, "sections", []) or [])

    walk(spec.sections)
    return attrs


def test_fit_model_selector_rebuilds_parameter_rows():
    # The registry-driven selector: switching the fit model re-emits the
    # parameter editor with exactly that model's free parameters, and editing a
    # slot writes into the active model's start vector.
    from chisurf.core.fluorescence.mle.fit2x import PARAMETER_NAMES, Fit2xModel
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import (
        PixelMleViewModel,
    )

    vm = PixelMleViewModel()
    events: list[str] = []
    vm.add_observer(events.append)

    # default fit23 → four parameter rows (tau, gamma, r0, rho)
    assert vm.fit_model == "fit23"
    assert len(_param_value_attrs(vm.view_spec())) == len(PARAMETER_NAMES[Fit2xModel.FIT23])

    # selecting fit25 asks the host to rebuild and re-emits five rows
    vm.set_fit_model("fit25")
    assert "rebuild" in events
    assert vm.fit_model == "fit25"
    assert len(_param_value_attrs(vm.view_spec())) == len(PARAMETER_NAMES[Fit2xModel.FIT25])

    # editing slot 3 (tau4) writes into the fit25 start vector, and each model
    # keeps its own edits independently
    vm.p3_value = 6.5
    x0_25, _ = vm._ensure_model_params("fit25")
    assert x0_25[3] == 6.5
    vm.set_fit_model("fit24")
    vm.p3_value = 0.7  # fit24 slot 3 is A2
    x0_24, _ = vm._ensure_model_params("fit24")
    assert x0_24[3] == 0.7
    assert vm._ensure_model_params("fit25")[0][3] == 6.5  # fit25 untouched


def test_run_settings_carry_the_selected_model(monkeypatch):
    # The run path must forward the chosen model + its start vector/fixed mask to
    # the core (not the legacy fit23 tau/gamma/r0/rho fields).
    from chisurf.plugins.microscopy.img_pixel_mle.gui import view_model as vm_mod
    from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import (
        PixelMleViewModel,
    )

    captured = {}

    def fake_fit(path, core_settings, progress=None):
        captured["settings"] = core_settings
        raise RuntimeError("stop after capture")  # skip the real (file-less) fit

    monkeypatch.setattr(vm_mod, "_VIEW_JSON", vm_mod._VIEW_JSON)  # no-op, keep import
    vm = PixelMleViewModel()
    vm.files = ["/does/not/matter.ptu"]
    vm.irf_files = ["/does/not/matter.ptu"]
    vm.settings.detector_chs_p = [0]
    vm.settings.detector_chs_s = [1]
    vm.settings.micro_time_start, vm.settings.micro_time_stop = 0, 32
    vm.set_fit_model("fit24")
    vm.p0_value = 3.14  # tau1 initial

    import numpy as np

    # Stub IRF prep + core fit so run() reaches the settings assembly without a file.
    monkeypatch.setattr(
        "chisurf.plugins.microscopy.img_pixel_mle.backend.services._build_irf_vv_vh",
        lambda *a, **k: np.zeros(2 * 32),
    )
    monkeypatch.setattr(
        "chisurf.plugins.microscopy.img_pixel_mle.core.fit_pixel_lifetimes_from_file",
        fake_fit,
    )
    monkeypatch.setattr(PixelMleViewModel, "_period_ns", staticmethod(lambda *a, **k: 40.0))

    vm.run()
    s = captured["settings"]
    assert s.fit_model == "fit24"
    assert list(s.initial_values)[0] == 3.14
    assert len(s.initial_values) == 5 and len(s.fixed_flags) == 5


def test_tool_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.microscopy.img_pixel_mle.gui.tool import ImgPixelMleTool

    widget = ImgPixelMleTool()
    qtbot.addWidget(widget)
    assert widget.windowTitle() == "Pixel-wise MLE"
    assert hasattr(widget, "auto_form")
    assert hasattr(widget, "model")
