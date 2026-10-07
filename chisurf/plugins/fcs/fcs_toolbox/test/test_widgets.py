"""Tests for the unified FCS window (native workflow host)."""


def test_fcs_tool_merges_correlator_and_tools(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool, FcsToolboxTool

    tool = FcsTool()
    qtbot.addWidget(tool)
    assert tool.windowTitle() == "FCS"
    assert FcsToolboxTool is FcsTool
    assert tool.app.selected == "files"
    assert [p["role"] for p in tool.app.tools] == [
        "channel_def", "files", "filter", "correlator", "merger",
        "flc_2d", "lfcs_sim", "burst_fcs", "diffusion_calc", "filter_calc",
    ]
    assert "diffusion_calc" not in tool.app.children
    assert tool.show_panel_by_role("diffusion_calc")
    assert tool.app.children["diffusion_calc"] is not None
    tool.close()


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


def test_show_panel_by_role_navigates_to_filter_calc(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool

    w = FcsTool()
    qtbot.addWidget(w)
    assert w.app.selected == "files"
    assert w.show_panel_by_role("filter_calc") is True
    assert w.app.selected == "filter_calc"
    assert "filter_calc" in w.app.children
    assert w.show_panel_by_role("does_not_exist") is False
    w.close()
