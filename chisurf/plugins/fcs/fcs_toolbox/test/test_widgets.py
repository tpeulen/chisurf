"""Tests for the unified FCS window (the native hub)."""

from emtk.testing import RecordingPainter


def _show(app, role):
    """Open a panel the way the rail does and draw a frame; True when it is the selected one."""
    app.select(role)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    return app.selected == role


def test_fcs_tool_merges_correlator_and_tools():
    from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app

    app = make_app()
    try:
        assert app.selected == "files"
        assert [p["role"] for p in app.tools] == [
            "channel_def", "files", "filter", "correlator", "merger",
            "flc_2d", "lfcs_sim", "burst_fcs", "diffusion_calc", "filter_calc",
        ]  # fmt: skip
        assert "diffusion_calc" not in app.children
        assert _show(app, "diffusion_calc")
        assert app.children["diffusion_calc"] is not None
    finally:
        app.close()


def test_included_plugins_are_menu_hidden():
    import importlib

    for mod in (
        "chisurf.plugins.fcs.fcs_correlator",
        "chisurf.plugins.fcs.flc_2d",
        "chisurf.plugins.fcs.fcs_calculator",
        "chisurf.plugins.fcs.fcs_filter_calculator",
        "chisurf.plugins.fcs.fcs_merger",
        "chisurf.plugins.burst.burst_fcs_correlator",
    ):
        m = importlib.import_module(mod)
        assert getattr(m, "menu_hidden", False) is True, mod


def test_selecting_the_filter_calculator_opens_it():
    from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app

    app = make_app()
    try:
        assert app.selected == "files"
        assert _show(app, "filter_calc") is True
        assert "filter_calc" in app.children
        try:
            app.select("does_not_exist")
        except ValueError:
            pass
        else:
            raise AssertionError("an unknown role must be refused")
    finally:
        app.close()
