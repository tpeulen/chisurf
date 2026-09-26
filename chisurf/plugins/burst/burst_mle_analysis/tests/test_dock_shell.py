"""The MLE wizard replaces its QTabWidget with an AutoForm dock area.

Regression: the BurstMLE tab could become unclickable in the QTabWidget. The
tabs are now draggable ChiSurf dock panels driven by AutoForm, mirroring
whichever tabs remain (the embedded workflow drops 'Detector Definition').
"""

from __future__ import annotations


def _make_wizard(qapp):
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    w = MLELifetimeAnalysisWizard()
    # Fire the deferred singleShot(0) conversion.
    QtWidgets.QApplication.processEvents()
    QtWidgets.QApplication.processEvents()
    return w


def test_dock_shell_replaces_tabwidget(qapp):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.widgets.dock_area import DockArea

    w = _make_wizard(qapp)
    assert getattr(w, "_dock_shell_built", False) is True
    assert w.findChildren(AutoForm)
    # Draggable ChiSurf docks (safe now the workflow embeds the central widget,
    # not the QMainWindow).
    assert w.findChildren(DockArea)
    # The old tab bar is hidden and detached from the layout. (An emptied source
    # tab such as tab_files may still be parented to it; that's harmless since the
    # tab widget itself is gone.)
    assert not w.tabWidget.isVisible()
    assert w.tabWidget.parent() is None
    # The hosted pages are reparented out of the tab widget into the dock area,
    # which owns visibility from then on (see the explicit-hide test below).
    assert w.groupBox_burst_files.parent() is not w.tab_files
    assert w.tab_parameters.parent() is not w.tabWidget


def test_hosted_pages_are_not_left_explicitly_hidden(qapp):
    """No page may carry the QTabWidget's explicit hide into its dock.

    A QTabWidget hides every page that is not current, and an explicit hide
    survives reparenting. The dock stack then shows its content wrapper while the
    page inside stays hidden, so the dock renders as an empty shell — which is
    how the whole Burst-MLE workspace (and, in the embedded workflow where the
    file docks are dropped, the entire panel) came up blank.
    """
    w = _make_wizard(qapp)
    blank = [attr for attr, _title in w._dock_pages if getattr(w, attr).isHidden()]
    assert not blank, f"pages handed to the dock area still explicitly hidden: {blank}"


def test_embedded_panel_shows_the_fit_workspace(qapp):
    """The workflow panel must render the fit controls, not just a dock title."""
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_analysis.gui import tool as tool_mod

    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    embedded = tool_mod._burst_mle(host)
    layout.addWidget(embedded)
    host.resize(1200, 800)
    host.show()
    try:
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()
        if hasattr(embedded, "_app"):
            assert embedded.isVisible(), "the EMTK host is not visible"
            assert embedded._app is not None
            return
        wizard = getattr(embedded, "_mle_wizard", embedded)
        tau = wizard.doubleSpinBox_tau
        assert embedded.isAncestorOf(tau), "the fit controls are not in the panel"
        assert tau.isVisible(), "the Burst-MLE workspace renders as an empty dock"
    finally:
        host.close()


def test_wizard_builds_without_ui_file(qapp):
    # The wizard is now built entirely in code; wizard.ui is gone. Every widget
    # the old .ui defined (and the code references) must exist as an attribute.
    import pathlib

    import chisurf.plugins.burst.burst_mle_analysis.wizard as wizard_mod

    assert not (pathlib.Path(wizard_mod.__file__).parent / "wizard.ui").exists()

    w = _make_wizard(qapp)
    for name in (
        "tabWidget",
        "tab_files",
        "tab_parameters",
        "groupBox_burst_files",
        "groupBox_irf_files",
        "groupBox_bg_files",
        "groupBox_model_params",
        "groupBox_2",
        "groupBox_fit_params",
        "doubleSpinBox_tau",
        "doubleSpinBox_gamma",
        "doubleSpinBox_r0",
        "doubleSpinBox_rho",
        "checkBox_fix_tau",
        "spinBox_min_photons",
        "comboBox_window",
        "lineEdit_current_filename",
        "pushButton_process_bursts",
        "verticalLayout_plots",
        "verticalLayout_burst_files",
        "verticalLayout_irf_files",
        "verticalLayout_bg_files",
    ):
        assert hasattr(w, name), f"missing programmatic widget: {name}"
    # A couple of the .ui defaults must survive.
    assert w.doubleSpinBox_tau.value() == 4.0
    assert w.doubleSpinBox_r0.value() == 0.38
    assert w.checkBox_irf_one_for_all.isChecked()


def test_standalone_keeps_detector_panel(qapp):
    w = _make_wizard(qapp)
    titles = [title for _attr, title in w._dock_pages]
    # The Files tab fans out into three separate file-drop foldables, kept
    # distinct from the Burst-MLE fit panel.
    assert titles == [
        "Detector Definition",
        "Burst Files",
        "IRF Files",
        "Background Files",
        "Burst-MLE",
    ]


def test_file_drops_are_separate_docks(qapp):
    from qtpy import QtWidgets

    from chisurf.gui.widgets.dock_area import DockArea

    w = _make_wizard(qapp)
    area = w.findChildren(DockArea)[0]
    tab_names = {
        tw.tabText(i) for tw in area.findChildren(QtWidgets.QTabWidget) for i in range(tw.count())
    }
    # Each file input and the Burst-MLE workspace is its own draggable dock.
    assert {"Burst Files", "IRF Files", "Background Files", "Burst-MLE"} <= tab_names
    # Each file group box was reparented out of the (removed) Files tab into the
    # dock area.
    for attr in ("groupBox_burst_files", "groupBox_irf_files", "groupBox_bg_files"):
        box = getattr(w, attr)
        assert box.parent() is not w.tab_files
        assert area.isAncestorOf(box)


def test_embedded_hides_duplicate_file_docks(qapp):
    # In the burst-analysis workflow the file inputs are supplied upstream, so the
    # MLE panel hides its Burst/IRF/Background file docks and shows only the fit.
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_analysis.gui import tool as tool_mod

    host = QtWidgets.QWidget()
    embedded = tool_mod._burst_mle(host)  # sets _embedded=True
    QtWidgets.QApplication.processEvents()
    wizard = getattr(embedded, "_mle_wizard", embedded)
    titles = [title for _attr, title in wizard._dock_pages]
    assert titles == ["Burst-MLE"]
    # The burst list widget still exists so upstream files can be loaded into it.
    assert hasattr(wizard, "burst_files_list")


def test_embedded_drops_detector_panel(qapp):
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_analysis.gui.tool import _remove_tab_by_name
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    w = MLELifetimeAnalysisWizard()
    # The workflow removes this tab synchronously before the deferred conversion.
    _remove_tab_by_name(w, "Detector Definition")
    QtWidgets.QApplication.processEvents()
    QtWidgets.QApplication.processEvents()

    titles = [title for _attr, title in w._dock_pages]
    assert titles == ["Burst Files", "IRF Files", "Background Files", "Burst-MLE"]
    assert w.tab_parameters.parent() is not w.tabWidget
