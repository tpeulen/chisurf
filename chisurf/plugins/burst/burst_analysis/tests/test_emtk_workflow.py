"""Unit tests for the 100% native EMTK Burst Analysis workflow."""

from __future__ import annotations

from pathlib import Path

from emtk.qt_painter import QtPainter
from qtpy import QtGui, QtWidgets

from chisurf.plugins.burst.burst_analysis.gui.app import BurstAnalysisApp, BurstAnalysisGui
from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool, BurstWorkflowContext


def draw_app(app: BurstAnalysisApp, width: float = 1000.0, height: float = 700.0) -> None:
    """Helper to execute one paint pass with a real QtPainter."""
    pixmap = QtGui.QPixmap(int(width), int(height))
    pixmap.fill(QtGui.QColor(30, 32, 38))
    qp = QtGui.QPainter(pixmap)
    try:
        surface = QtPainter(qp, font_pt=10.0)
        app.draw(surface, 0.0, 0.0, width, height)
    finally:
        qp.end()


def test_burst_analysis_tool_emtk_host_initialized(qapp) -> None:
    """BurstAnalysisTool instantiates BurstAnalysisApp and hosts it in ControlHost."""
    tool = BurstAnalysisTool()
    try:
        assert isinstance(tool.app, BurstAnalysisApp)
        assert tool.centralWidget() is tool.host
        assert tool.app.selected_role == "setup"
        assert "setup" in tool._workflow_panels
    finally:
        tool.close()
        QtWidgets.QApplication.processEvents()


def test_burst_analysis_emtk_draw(qapp) -> None:
    """BurstAnalysisApp renders successfully without errors in EMTK."""
    tool = BurstAnalysisTool()
    try:
        # Draw frame at 1000x700
        draw_app(tool.app, 1000.0, 700.0)

        # Check layout calculations
        nav_w, top_h, status_h, main_w, main_h = tool.app.analysis_gui.get_layout(1000.0, 700.0)
        assert nav_w == 272.0
        assert top_h == 44.0
        assert status_h == 28.0
        assert main_w == 1000.0 - 272.0
        assert main_h == 700.0 - 44.0 - 28.0

        # Collapsed sidebar layout
        tool.app.analysis_gui.sidebar_collapsed = True
        nav_w_c, _, _, main_w_c, _ = tool.app.analysis_gui.get_layout(1000.0, 700.0)
        assert nav_w_c == 44.0
        assert main_w_c == 1000.0 - 44.0
    finally:
        tool.close()
        QtWidgets.QApplication.processEvents()


def test_burst_analysis_stepper_and_navigation(qapp) -> None:
    """Stepper buttons and show_panel_by_role walk the workflow in EMTK."""
    tool = BurstAnalysisTool()
    try:
        # Initial step is 0. Setup Selection
        assert tool.app.selected_role == "setup"

        # Advance to step 1 (data)
        assert tool.goto_next_step() is True
        assert tool.app.selected_role == "data"
        assert "data" in tool._workflow_panels

        # Advance to step 2 (selection)
        assert tool.goto_next_step() is True
        assert tool.app.selected_role == "selection"
        assert "selection" in tool._workflow_panels

        # Draw frame on step 2
        draw_app(tool.app, 1000.0, 700.0)

        # Direct navigation to BVA
        assert tool.show_panel_by_role("bva") is True
        assert tool.app.selected_role == "bva"
        assert "bva" in tool._workflow_panels

        # Step back to fusion
        assert tool.goto_prev_step() is True
        assert tool.app.selected_role == "fusion"

        # Navigate to a side tool
        assert tool.goto_workflow_role("accurate_fret") is True
        assert tool.app.selected_role == "accurate_fret"
        assert "accurate_fret" in tool._workflow_panels
    finally:
        tool.close()
        QtWidgets.QApplication.processEvents()


def test_burst_analysis_in_emtk_help_and_tour(qapp) -> None:
    """In-EMTK Help Window and Guided Tour open, step, and close with 0 hangs."""
    tool = BurstAnalysisTool()
    try:
        gui = tool.app.analysis_gui
        assert not gui.help_window.open
        assert not gui.tour.active

        # Open Help Window
        gui.show_help()
        assert gui.help_window.open is True

        # Render with Help Window open
        draw_app(tool.app, 1000.0, 700.0)

        # Close Help Window
        gui.help_window.close()
        assert gui.help_window.open is False

        # Open and step Guided Tour
        gui.start_guide()
        assert gui.tour.active is True
        assert gui.tour.step_idx == 0

        # Step next
        gui.tour.next_step()
        assert gui.tour.step_idx == 1

        # Stop Tour
        gui.tour.stop()
        assert gui.tour.active is False
    finally:
        tool.close()
        QtWidgets.QApplication.processEvents()


def test_burst_analysis_pointer_event_routing(qapp) -> None:
    """Pointer and key events route properly between shell chrome and active panel."""
    from emtk.events import LEFT_BUTTON

    tool = BurstAnalysisTool()
    try:
        draw_app(tool.app, 1000.0, 700.0)

        # Event in sidebar chrome (x < 272)
        tool.app.pointer_move(100.0, 100.0)
        tool.app.pointer_press(100.0, 100.0, LEFT_BUTTON)
        tool.app.pointer_release(100.0, 100.0, LEFT_BUTTON)

        # Event in central main area (x > 272, 44 < y < 672)
        active_app = tool.get_active_app()
        assert active_app is not None

        tool.app.pointer_move(500.0, 300.0)
        tool.app.pointer_press(500.0, 300.0, LEFT_BUTTON)
        tool.app.pointer_release(500.0, 300.0, LEFT_BUTTON)
        tool.app.wheel(500.0, 300.0, 1.0)
        tool.app.key(32, " ")

        # Draw frame after interaction
        draw_app(tool.app, 1000.0, 700.0)
    finally:
        tool.close()
        QtWidgets.QApplication.processEvents()


def test_burst_analysis_status_and_progress_in_emtk(qapp) -> None:
    """Status messages and background task progress reflect in the EMTK status bar."""
    tool = BurstAnalysisTool()
    try:
        assert tool._status_text == "Ready"
        assert tool._status_message.text() == "Ready"

        # Begin a progress task
        task = tool.begin_task("Analyzing TTTR data...", maximum=100)
        assert tool._status_text == "Analyzing TTTR data..."
        assert tool._status_progress_maximum == 100
        assert tool._status_progress_visible is True

        # Update progress
        task.set_value(45)
        assert tool._status_progress_value == 45

        # Render with progress active
        draw_app(tool.app, 1000.0, 700.0)

        # Complete task
        task.close()
        assert tool._active_task is None
        assert tool._status_progress_visible is False
    finally:
        tool.close()
        QtWidgets.QApplication.processEvents()
