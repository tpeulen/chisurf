"""Tests for the unified FCS window (shared NavigationPanelTool shell)."""


def test_fcs_tool_merges_correlator_and_tools(qapp, qtbot):
    from chisurf.gui.widgets.navigation import NavigationPanelTool
    from chisurf.plugins.fcs.fcs_correlator.tool import CORRELATOR_PANELS
    from chisurf.plugins.fcs.fcs_toolbox.tool import (
        FCS_PANELS,
        TOOL_PANELS,
        FcsTool,
        FcsToolboxTool,
    )

    w = FcsTool()
    qtbot.addWidget(w)

    # same base / look as Burst Analysis, Decay Analysis, Imaging Tools
    assert isinstance(w, NavigationPanelTool)
    assert w.windowTitle() == "FCS"
    assert FcsToolboxTool is FcsTool  # back-compat alias

    # correlator workflow + a "Tools" separator + the optional tools,
    # each behind its own group header.
    separators = [p for p in FCS_PANELS if p.get("separator")]
    assert [s["name"] for s in separators] == ["Correlator", "Tools"]
    assert len(FCS_PANELS) == len(CORRELATOR_PANELS) + len(TOOL_PANELS) + len(separators)
    assert w.nav_list.count() == len(FCS_PANELS)

    names = [w.nav_list.item(i).text() for i in range(w.nav_list.count())]
    assert any("Correlator" in n for n in names)
    assert any("Diffusion Calc" in n for n in names)
    assert any("2D-FLCS" in n for n in names)

    # panels load lazily; opens on the correlator "Files & Steps" step.
    files_row = w._nav_row_for_role("files")
    assert w.nav_list.currentRow() == files_row

    # an optional tool loads on demand
    calc_row = w._nav_row_for_role("diffusion_calc")
    assert calc_row >= 0
    assert w.panels[calc_row].get("instance") is None
    w.nav_list.setCurrentRow(calc_row)
    assert w.panels[calc_row].get("instance") is not None


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
    calc_row = w._nav_row_for_role("filter_calc")
    assert calc_row >= 0
    assert w.nav_list.currentRow() != calc_row       # starts elsewhere
    assert w.show_panel_by_role("filter_calc") is True
    assert w.nav_list.currentRow() == calc_row       # navigated
    assert w.show_panel_by_role("does_not_exist") is False
