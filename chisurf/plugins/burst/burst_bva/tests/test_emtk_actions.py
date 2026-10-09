"""Action parity for the EMTK controls replacing the hidden Qt toolbar."""

from unittest.mock import patch

from chisurf.plugins.burst.burst_bva.gui.app import BurstBvaGui


def test_hidden_toolbar_actions_are_available_in_emtk():
    calls = []
    gui = BurstBvaGui(
        on_clear=lambda: calls.append("clear"),
        on_save=lambda: calls.append("save"),
        on_save_settings=lambda: calls.append("settings"),
    )
    with (
        patch("chisurf.plugins.burst.burst_bva.gui.app.im") as im,
        patch("chisurf.plugins.emtk_layout.im", im),
    ):
        # the wrapped button rows (chisurf.plugins.emtk_layout.button_row) draw through the same mock
        im.get_style.return_value.item_spacing = (8.0, 4.0)
        im.get_style.return_value.frame_padding = (6.0, 3.0)
        im.get_item_rect.return_value = None
        im.get_content_region_avail.return_value = (400.0, 300.0)  # the row-wrap measures the pane
        im.calc_text_size.return_value = (60.0, 14.0)
        for label in (
            "🗑  Clear",
            "💾  Save plot",
            "⚙  Save defaults",
        ):  # one press per frame, as a pointer gives
            im.button.side_effect = lambda text, label=label: text == label
            gui._draw_action_buttons()
        assert calls == ["clear", "save", "settings"]
        tips = [call.args[0] for call in im.set_item_tooltip.call_args_list]
        assert len(tips) >= 9
        assert any("defaults" in text for text in tips)


def test_microtime_gates_reach_analysis_settings():
    gui = BurstBvaGui()

    def edit(label, value, **kwargs):
        if label == "##donor_microtime":
            return True, "10:20, 30:40"
        return False, value

    with patch("chisurf.plugins.burst.burst_bva.gui.app.im") as im:
        im.input_text.side_effect = edit
        gui._draw_channel_definitions()
    assert gui.model.bva_settings()["donor_micro_time_ranges"] == [(10, 20), (30, 40)]


def test_invalid_microtime_gates_preserve_last_valid_settings():
    gui = BurstBvaGui()

    def edit(label, value, **kwargs):
        return (True, "20:10") if label == "##acceptor_microtime" else (False, value)

    with patch("chisurf.plugins.burst.burst_bva.gui.app.im") as im:
        im.input_text.side_effect = edit
        gui._draw_channel_definitions()
    assert gui.model.acceptor_micro_time_ranges == [(0, 32768)]
    assert "Invalid microtime" in gui.model.status_text


def test_emtk_apps_construct_without_loading_qt():
    import subprocess
    import sys

    code = """
import sys
from chisurf.plugins.burst.burst_bva.gui.app import BurstBvaApp
from chisurf.plugins.burst.burst_2cde.gui.app import BurstTwoCdeApp
BurstBvaApp()
BurstTwoCdeApp()
qt = [m for m in sys.modules if m.startswith(('qtpy', 'PyQt', 'PySide'))]
assert not qt, qt
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_bva_runs_backend_and_updates_plot(tmp_path, monkeypatch):
    import pandas as pd

    from chisurf.plugins.burst.burst_bva.core import computation as core
    from chisurf.plugins.burst.burst_bva.gui.controller import BvaController
    from chisurf.plugins.burst.burst_bva.gui.view_model import BvaViewModel

    model = BvaViewModel()
    model.auto_update = False
    model.set_folder(tmp_path)
    ctrl = BvaController(model)
    table = pd.DataFrame({"Proximity Ratio Mean": [0.5], "Proximity Ratio Std": [0.1]})
    monkeypatch.setattr(core, "read_burst_analysis", lambda *a, **k: (table, {}))
    settings = []
    monkeypatch.setattr(core, "compute_bva", lambda df, tttrs, **kw: settings.append(kw) or df)
    written = []

    def write(*args, **kwargs):
        written.append(True)
        output = tmp_path / "bv4"
        output.mkdir(exist_ok=True)
        (output / "test.bv4").write_text("test")

    monkeypatch.setattr(core, "write_bv4_analysis", write)
    try:
        ctrl.run()
        ctrl._future.result(timeout=5)
        ctrl.poll()
        assert written == [True]
        assert settings[0]["number_of_photons_per_slice"] == 10
        assert model.df is table
        assert (tmp_path / "bv4" / "bva.stamp.json").exists()
        assert (tmp_path / "bv4" / "bva_settings.json").exists()
        ctrl.run()
        assert ctrl._future is None
        assert "Unchanged" in model.status_text
        assert not model.is_running
        ctrl.clear()
        assert model.df is None
    finally:
        ctrl.close()


def test_native_defaults_restore_and_png_export(tmp_path):
    from chisurf.plugins.burst.burst_bva.gui.controller import BvaController
    from chisurf.plugins.burst.burst_bva.gui.view_model import BvaViewModel

    path = tmp_path / "defaults.ini"
    model = BvaViewModel()
    model.window_length = 0.03
    ctrl = BvaController(model, settings_path=path)
    try:
        ctrl.save_settings()
        png = tmp_path / "bva.png"
        from chisurf.plugins.burst.burst_bva.gui.app import create_app

        app = create_app()
        try:
            ctrl.write_window_png(app, png, (640, 480))  # a picture of the window, as the Qt grab
        finally:
            app.close()
        assert png.read_bytes().startswith(b"\x89PNG")
        restored = BvaViewModel()
        other = BvaController(restored, settings_path=path)
        try:
            assert restored.window_length == 0.03
        finally:
            other.close()
    finally:
        ctrl.close()


def test_native_factories_return_drawable_controls():
    from chisurf.plugins.burst.burst_2cde.gui.app import create_app as cde
    from chisurf.plugins.burst.burst_bva.gui.app import create_app as bva

    for factory in (bva, cde):
        app = factory()
        try:
            assert callable(app.draw)
            assert app.controller is not None
        finally:
            app.close()
