"""Tests for the integrated burst workflow shell."""

from __future__ import annotations

from pathlib import Path


def test_mle_panel_embeds_central_widget_not_mainwindow(qapp) -> None:
    """The MLE panel is embedded as a plain QWidget, not the QMainWindow.

    On native macOS an embedded QMainWindow swallowed clicks over the panel;
    the factory now hosts the wizard's central widget instead. The wizard must
    still be reachable (it owns the fit logic) via the ``_mle_wizard`` back-ref.
    """
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_analysis.gui import tool as tool_mod
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    host = QtWidgets.QWidget()  # stand-in parent (no workflow binding)
    embedded = tool_mod._burst_mle(host)
    QtWidgets.QApplication.processEvents()

    assert not isinstance(embedded, QtWidgets.QMainWindow)
    wizard = getattr(embedded, "_mle_wizard", None)
    assert isinstance(wizard, MLELifetimeAnalysisWizard)
    assert hasattr(wizard, "burst_files_list")


def test_mle_wizard_shares_lifetime_with_embedded_widget(qapp) -> None:
    """The wizard and its embedded content must live and die as one unit.

    Regression: the wizard (a QMainWindow) used to hang off the workflow in a
    separate branch from ``central`` (its extracted content, holding every fit
    button wired to a wizard slot). A window/child cleanup could then destroy the
    wizard while ``central`` — and its buttons — survived, so a later click fired
    a slot on a deleted C++ object ("wrapped C/C++ object ... has been deleted").
    The wizard must therefore be a descendant of the embedded widget, never a
    stray child of the workflow, and must not render over the panel.
    """
    from qtpy import QtWidgets

    try:
        from qtpy import sip
    except ImportError:  # pragma: no cover - PySide path
        import sip

    from chisurf.plugins.burst.burst_analysis.gui import tool as tool_mod

    host = QtWidgets.QWidget()
    host.show()
    embedded = tool_mod._burst_mle(host)
    # Host the embedded widget the way the navigation shell does.
    layout = QtWidgets.QVBoxLayout(host)
    layout.addWidget(embedded)
    QtWidgets.QApplication.processEvents()

    wizard = embedded._mle_wizard

    # The wizard shares the embedded widget's branch (one lifetime)...
    def _is_descendant(child, ancestor):
        parent = child.parent()
        while parent is not None:
            if parent is ancestor:
                return True
            parent = parent.parent()
        return False

    assert _is_descendant(wizard, embedded), "wizard is not under the embedded widget"
    assert wizard.parent() is not host, "wizard is a stray child of the workflow"
    # ...and never renders over the panel (the click-swallow this design avoids)
    # and is not a top-level window (a Qt.Window reparent left an empty little
    # traffic-light window floating over the panel, whose close deletes the
    # wizard and re-triggers the crash).
    assert not wizard.isVisible()
    assert not wizard.isWindow(), "wizard is a floating window, not a hidden child"
    assert wizard not in QtWidgets.QApplication.topLevelWidgets()

    # Deleting the embedded content takes the wizard (and its buttons) with it, so
    # no live button can outlive the wizard and fire a slot on a dead object.
    button = wizard.toolButton_hyper_opt
    sip.delete(embedded)
    assert sip.isdeleted(wizard), "wizard outlived its embedded content"
    assert sip.isdeleted(button), "a fit button outlived the wizard"


def test_send_to_mle_survives_detector_switch() -> None:
    """IRF/background patterns must persist in the per-detector state cache.

    Regression: 'Send to MLE' wrote only the transient irf_np/bg_np, so the first
    detector switch (which restores those from channel_settings[det]) overwrote
    them with empty arrays and the fit saw nothing.
    """
    import numpy as np

    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    class _FakeMle:
        def __init__(self):
            self.irf_np = {}
            self.bg_np = {}
            self.channel_settings = {}
            self.current_detector = "green"

        def _ensure_channel_state(self, det):
            self.channel_settings.setdefault(det, {}).setdefault("irf", np.array([]))
            self.channel_settings[det].setdefault("bg", np.array([]))

        # Mirrors the wizard's _apply_ui_state: restore live arrays from the cache.
        def restore_detector(self, det):
            self.current_detector = det
            self.irf_np[det] = np.array(self.channel_settings[det]["irf"])
            self.bg_np[det] = np.array(self.channel_settings[det]["bg"])

    mle = _FakeMle()
    patterns = {
        "green": {"irf": np.array([1.0, 2.0, 3.0]), "bg": np.array([0.1, 0.1, 0.1])},
        "red": {"irf": np.array([4.0, 5.0]), "bg": np.array([0.2, 0.2])},
    }

    count = BurstAnalysisTool._apply_irf_bg_to_mle_widget(mle, patterns)
    assert count == 2

    # The state cache carries the patterns (not just irf_np)...
    assert np.array_equal(mle.channel_settings["green"]["irf"], [1.0, 2.0, 3.0])
    assert np.array_equal(mle.channel_settings["red"]["bg"], [0.2, 0.2])

    # ...so a detector switch that restores from the cache keeps them.
    mle.restore_detector("red")
    assert np.array_equal(mle.irf_np["red"], [4.0, 5.0])
    mle.restore_detector("green")
    assert np.array_equal(mle.irf_np["green"], [1.0, 2.0, 3.0])


def test_burst_workflow_panel_order() -> None:
    """Meta burst workflow exposes requested ordered steps."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BURST_PANELS

    labels = [f"{panel.get('icon', '')} {panel['name']}".strip() for panel in BURST_PANELS]
    # No standalone Channels step (channels come from the Burst Selection setup);
    # the numbered pipeline (Data → H2MM) is the main flow, with the unnumbered
    # steps below the separator: first what you do *with* the bursts (Browser,
    # Accurate FRET, Burst FCS, Kinetics), then the two that feed the pipeline
    # from the raw files (Background, IRF & Background).
    assert labels == [
        "📂 1. Data Selection",
        "🔍 2. Burst Selection",
        "📊 3. BVA",
        "📊 4. 2CDE",
        "🎯 5. MLE-Lifetime",
        "🔀 6. H2MM",
        "────────",
        "📋 Browser",
        "🎯 Accurate FRET",
        "📊 Burst FCS",
        "🔀 Kinetics (GS)",
        "🌙 Background",
        "✨ IRF & Background",
    ]
    # The separator sits after the six numbered steps.
    assert BURST_PANELS[6]["separator"] is True
    assert "channels" not in {p.get("role") for p in BURST_PANELS}


def test_h2mm_panel_is_not_flagged_experimental() -> None:
    """The H2MM step no longer carries the experimental flag (no ⚠️ / banner)."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BURST_PANELS

    h2mm = next(p for p in BURST_PANELS if p.get("role") == "h2mm")
    assert not h2mm.get("experimental")
    assert not h2mm.get("experimental_message")


def test_workflow_context_payload_is_json_ready(tmp_path: Path) -> None:
    """Workflow context serializes paths and MMFDB artifact handoff data."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstWorkflowContext

    context = BurstWorkflowContext(
        raw_files=[tmp_path / "a.spc"],
        burst_folder=tmp_path / "burstwise",
        bur_files=[tmp_path / "burstwise" / "bi4_bur" / "a.bur"],
        mmfdb_artifacts={"sidecar_artifacts": {"output_folder": "artifact-1"}},
        raw_mmfdb_artifacts={"imports": {"a.spc": {"object_result": {"ok": True}}}},
    )
    payload = context.to_payload()
    assert payload["raw_files"] == [str(tmp_path / "a.spc")]
    assert payload["burst_folder"] == str(tmp_path / "burstwise")
    assert payload["bur_files"] == [str(tmp_path / "burstwise" / "bi4_bur" / "a.bur")]
    assert payload["mmfdb_artifacts"]["sidecar_artifacts"]["output_folder"] == "artifact-1"
    assert payload["raw_mmfdb_artifacts"]["imports"]["a.spc"]["object_result"]["ok"] is True


def test_bva_factory_hides_internal_channel_tab(monkeypatch) -> None:
    """Embedded BVA keeps detector_page but hides its channel-definition dock."""
    from chisurf.plugins.burst.burst_analysis.gui import tool as meta_tool

    class FakeDockArea:
        def __init__(self) -> None:
            self._all_widgets = [object(), object()]
            self.hidden: list[int] = []

        def tabText(self, index: int) -> str:
            return ["BVA Settings", "Channel Definitions"][index]

        def hideTab(self, index: int) -> None:
            self.hidden.append(index)

    class FakeBVA:
        def __init__(self, parent=None, *, embedded: bool = False) -> None:
            self.parent = parent
            self.embedded = embedded
            self.detector_page = object()
            self.dock_area = FakeDockArea()

    monkeypatch.setattr(
        "chisurf.plugins.burst.burst_bva.gui.tool.BVATool",
        FakeBVA,
    )

    widget = meta_tool._burst_bva(parent=None)
    assert widget.detector_page is not None
    assert widget.embedded is True
    assert widget.dock_area.hidden == [1]


def test_navigation_embeds_main_window_pages_as_child_widgets() -> None:
    """Embedded legacy main windows stay child widgets inside the navigation shell."""
    from qtpy import QtCore, QtWidgets

    from chisurf.gui.widgets.navigation import NavigationPanelTool

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    loaded: list[QtWidgets.QMainWindow] = []

    def factory(parent):
        widget = QtWidgets.QMainWindow(parent)
        loaded.append(widget)
        return widget

    tool = NavigationPanelTool(
        title="Navigation Test",
        panels=[{"name": "Panel", "factory": factory}],
        minimum_size=(200, 120),
        initial_size=(220, 140),
        navigation_width=100,
    )
    app.processEvents()

    assert loaded
    assert not loaded[0].isWindow()
    assert loaded[0].windowType() == QtCore.Qt.Widget
    assert loaded[0].testAttribute(QtCore.Qt.WA_DontCreateNativeAncestors)
    assert not loaded[0].testAttribute(QtCore.Qt.WA_QuitOnClose)
    tool.close()
    app.processEvents()


def test_bva_embedded_mode_does_not_restore_top_level_geometry(monkeypatch) -> None:
    """Embedded BVA reuses dock layout without restoring standalone window state."""
    import chisurf.plugins.burst.burst_bva.gui.tool as bva_tool

    class Settings:
        def __init__(self, *args) -> None:
            self.values = {
                "dock_layout_v2": '{"tabs": []}',
                "window_geometry": b"geometry",
                "window_state": b"state",
            }

        def value(self, key):
            return self.values.get(key)

    class DockArea:
        def __init__(self) -> None:
            self.applied = None

        def set_layout_state(self, layout_state, emit_change=False) -> None:
            self.applied = (layout_state, emit_change)

    tool = bva_tool.BVATool.__new__(bva_tool.BVATool)
    tool._embedded = True
    tool.dock_area = DockArea()
    restore_calls: list[str] = []
    tool.restoreGeometry = lambda geometry: restore_calls.append("geometry")
    tool.restoreState = lambda state: restore_calls.append("state")
    monkeypatch.setattr(bva_tool, "QSettings", Settings)

    tool._restore_dock_layout()

    assert restore_calls == []
    assert tool.dock_area.applied == ({"tabs": []}, False)


def test_data_selection_imports_local_files_to_mmfdb(tmp_path: Path) -> None:
    """Adding local TTTR data imports it through MMFDB RPC."""
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstDataSelectionWidget

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    spc = tmp_path / "a.spc"
    spc.write_bytes(b"raw")
    calls: list[tuple[str, dict]] = []

    class Client:
        def call(self, method, params=None):
            calls.append((method, params or {}))
            if method == "mmfdb.objects.put":
                return {"ok": True, "object": {"object_uuid": "obj-1"}}
            if method == "raw_data.register":
                return {"ok": True, "raw_data": {"raw_data_id": "raw-1"}}
            return {}

    widget = BurstDataSelectionWidget()
    widget._mmfdb_client = Client()
    widget.add_paths([spc])
    app.processEvents()

    assert widget.paths() == [spc.resolve()]
    assert [call[0] for call in calls] == ["mmfdb.objects.put", "raw_data.register"]
    payload = widget.mmfdb_payload()
    assert payload["imports"][str(spc.resolve())]["object_result"]["object"]["object_uuid"] == "obj-1"
    assert payload["imports"][str(spc.resolve())]["raw_data_result"]["raw_data"]["raw_data_id"] == "raw-1"
    widget.close()
    app.processEvents()


def test_mle_burst_file_list_exposes_paths_not_count(qapp) -> None:
    """The burst-MLE file list is queried via ``paths()``, never ``count()``.

    Regression: ``burst_files_list`` migrated from a ``QListWidget`` to the shared
    ``PathListWidget``-backed factory, which has no ``count()``. Applying workflow
    context to the MLE panel crashed with ``'PathListWidget' object has no
    attribute 'count'``. The compat widget must expose ``paths()`` (and keep
    ``add_file``), and must NOT expose ``count`` — otherwise the caller regresses.
    """
    from chisurf.plugins.burst.burst_mle_analysis.utils import FileListWidget

    widget = FileListWidget()
    assert hasattr(widget, "paths")
    assert callable(widget.paths)
    assert widget.paths() == []
    assert hasattr(widget, "add_file")
    assert not hasattr(widget, "count")


def test_apply_context_to_mle_prepopulates_via_paths(tmp_path: Path) -> None:
    """MLE context uses ``len(paths())``/``add_file`` (no ``count()``)."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    added: list[str] = []

    class FakeList:
        def __init__(self) -> None:
            self._paths: list[str] = []

        def paths(self) -> list[str]:
            return list(self._paths)

        def add_file(self, path: str) -> None:
            self._paths.append(str(path))
            added.append(str(path))

    class FakeMle:
        def __init__(self) -> None:
            self.burst_files_list = FakeList()
            self.channel_definer = None

        def load_burst_data(self) -> None:  # noqa: D401 - stub
            pass

        def update_burst_files(self) -> None:  # noqa: D401 - stub
            pass

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    bur = tmp_path / "bi4_bur" / "a.bur"
    tool.workflow_context = BurstWorkflowContext(bur_files=[bur])

    mle = FakeMle()
    BurstAnalysisTool._apply_context_to_mle(tool, mle)
    assert added == [str(bur)]


def test_apply_context_to_2cde_sets_folder(tmp_path: Path) -> None:
    """2CDE adopts the upstream burst analysis folder (like BVA)."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    seen: list[str] = []

    class Fake2cde:
        def set_folder(self, folder: str) -> None:
            seen.append(str(folder))

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    folder = tmp_path / "burstwise"
    tool.workflow_context = BurstWorkflowContext(burst_folder=folder)

    BurstAnalysisTool._apply_context_to_2cde(tool, Fake2cde())
    assert seen == [str(folder)]


def test_mle_action_toolbar_is_pinned_above_the_dock_area(qapp) -> None:
    """MLE's action toolbar sits above the tab/dock area, not inside one dock.

    The Run/Save actions are built inside the Burst-MLE page; left there they hide
    inside a single tab/dock. They are lifted into the top-level layout so they
    stay visible whichever dock is on top — and survive the AutoForm dock-shell
    conversion (toolbar at index 0, dock form below it).
    """
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    w = MLELifetimeAnalysisWizard()
    try:
        assert w.verticalLayout.indexOf(w.toolBar_mle) == 0
        assert w.verticalLayout.indexOf(w.tabWidget) > 0
        w._convert_tabs_to_dock_shell()
        qapp.processEvents()
        assert w.verticalLayout.indexOf(w.toolBar_mle) == 0
        form = getattr(w, "_dock_form", None)
        if form is not None:
            assert w.verticalLayout.indexOf(form) > 0
    finally:
        w.close()
        qapp.processEvents()


def test_run_button_is_identical_across_plugins(qapp) -> None:
    """The primary 'run/process' action is the same button in every plugin.

    Same function → same object name → same 🚀 icon → same accent, so the Burst
    Analysis workflow reads as one app. This also lets the shell's Next button find
    and trigger each step's 'process all loaded files' action generically.
    """
    from qtpy import QtWidgets

    from chisurf.gui.glyphs import Glyphs
    from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool
    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tools = [BVATool(embedded=True), BurstTwoCdeTool(embedded=True), H2mmTool(embedded=True)]
    try:
        for tool in tools:
            run = tool.findChild(QtWidgets.QToolButton, "toolAction_run")
            assert run is not None, f"{type(tool).__name__} has no canonical Run button"
            assert run.text() == Glyphs.ROCKET
    finally:
        for tool in tools:
            tool.close()
        QtWidgets.QApplication.processEvents()


def test_h2mm_role_wired_into_downstream_propagation() -> None:
    """H2MM inherits the upstream folder on step change, like BVA/2CDE.

    Regression: ``h2mm`` was missing from ``_apply_context_to_downstream``'s role
    tuple, so the H2MM panel only picked up the folder on (re)bind, not when the
    upstream selection changed.
    """
    import inspect

    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    src = inspect.getsource(BurstAnalysisTool._apply_context_to_downstream)
    assert '"h2mm"' in src


def test_h2mm_adopts_folder_via_downstream(tmp_path: Path) -> None:
    """Applying context to a bound H2MM panel sets its analysis folder."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    seen: list[str] = []

    class FakeH2mm:
        detector_page = None

        def _set_folder(self, folder: str) -> None:
            seen.append(str(folder))

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    folder = tmp_path / "burstwise"
    tool.workflow_context = BurstWorkflowContext(burst_folder=folder)
    tool._workflow_panels = {"h2mm": FakeH2mm()}

    tool._apply_context_to_downstream()
    assert seen == [str(folder)]


def test_bva_progress_routes_to_shell_status_bar_when_embedded(qapp) -> None:
    """Embedded BVA's progress renders in the shell status bar, not a popup."""
    from chisurf.gui.widgets.navigation import _StatusTask
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    tool = BurstAnalysisTool()
    try:
        assert tool.show_panel_by_role("bva")
        bva = tool._workflow_panels.get("bva")
        assert bva is not None
        # Embedded: the shell is the nearest progress host, so ChiSurfProgress
        # renders in its status bar instead of a modal dialog.
        from chisurf.gui.progress import ChiSurfProgress, find_progress_host

        assert find_progress_host(bva) is tool
        prog = ChiSurfProgress(bva, text="Reading burst data...", maximum=0)
        assert isinstance(prog.backend, _StatusTask)
        assert tool._status_message.text() == "Reading burst data..."
        # A logged status message reaches the shell bar.
        bva._status("Done – 7 bursts")
        prog.close()
        assert tool._status_message.text() == "Done – 7 bursts"
    finally:
        tool.close()
        from qtpy import QtWidgets

        QtWidgets.QApplication.processEvents()


def test_bva_param_changes_coalesce_into_one_recompute(qapp) -> None:
    """Several rapid param changes trigger a single BVA recompute, not many.

    Regression: applying workflow context loaded the detector table, refreshed the
    donor/acceptor combos and set the folder in one turn, each firing a synchronous
    full read/compute/plot. The tool now coalesces them via a zero-delay timer and
    a ``suspend_recompute`` batch guard.
    """
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_bva.gui.tool import BVATool

    tool = BVATool(embedded=True)
    tool._burst_df = object()  # non-None so _flush_recompute takes the compute path
    calls: list[int] = []
    tool._start_analysis = lambda *a, **k: calls.append(1)
    tool._auto_update_cb.setChecked(True)

    # Batch of programmatic changes inside a suspend guard => one coalesced compute.
    with tool.suspend_recompute():
        for _ in range(5):
            tool._on_param_changed()
        assert calls == []  # nothing computed while suspended
    QtWidgets.QApplication.processEvents()
    assert calls == [1]

    # A fresh burst of changes outside the guard also collapses to one compute.
    calls.clear()
    for _ in range(4):
        tool._on_param_changed()
    QtWidgets.QApplication.processEvents()
    assert calls == [1]

    tool.close()
    QtWidgets.QApplication.processEvents()


def test_data_selection_uses_the_shared_path_list_widget() -> None:
    """Data Selection hosts the unified AutoForm path_list, not a custom list.

    The bespoke Import files / folder / MMFDB / Clear buttons were replaced by the
    shared ``PathListWidget`` (drag-drop + ➕ Files / 📁 Folder / 🗄️ Database /
    ➖ Remove / 🗑️ Clear); MMFDB dataset resolution now lives in that widget's
    shared picker, not in a per-panel ``_open_mmfdb_dataset``.
    """
    from qtpy import QtWidgets

    from chisurf.gui.autoform.sections.path_list_section import PathListWidget
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstDataSelectionWidget

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = BurstDataSelectionWidget()
    assert isinstance(widget.file_list, PathListWidget)
    assert not hasattr(widget, "_open_mmfdb_dataset")
    assert not hasattr(widget, "add_files_button")
    widget.close()
    app.processEvents()


def test_burst_fcs_adopts_the_upstream_burst_folder(tmp_path: Path) -> None:
    """Burst-wise FCS is handed the analysis folder, not a snapshot of its files.

    Its list expands a folder itself, so the folder keeps the panel pointing at
    the analysis rather than at whichever files existed at hand-off time.
    """
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    added: list[list[str]] = []

    class FakeList:
        def checked_paths(self):
            return []

        def add_paths(self, paths):
            added.append([str(p) for p in paths])

    class FakeFcs:
        file_list = FakeList()

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    folder = tmp_path / "burstwise"
    tool.workflow_context = BurstWorkflowContext(burst_folder=folder)

    BurstAnalysisTool._apply_context_to_burst_fcs(tool, FakeFcs())
    assert added == [[str(folder)]]


def test_burst_fcs_keeps_a_selection_the_user_made(tmp_path: Path) -> None:
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    added: list[list[str]] = []

    class FakeList:
        def checked_paths(self):
            return ["/somewhere/else.bur"]

        def add_paths(self, paths):
            added.append(list(paths))

    class FakeFcs:
        file_list = FakeList()

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    tool.workflow_context = BurstWorkflowContext(burst_folder=tmp_path / "burstwise")
    BurstAnalysisTool._apply_context_to_burst_fcs(tool, FakeFcs())
    assert added == [], "the workflow must not overwrite files the user chose"


def test_kinetics_receives_the_bur_files(tmp_path: Path) -> None:
    """Photon-by-photon kinetics reads .bur tables — hand it the ones upstream made."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    events: list[str] = []

    class FakeModel:
        bur_files: list = []

        def notify(self, event):
            events.append(event)

    class FakeGs:
        model = FakeModel()

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    files = [tmp_path / "m000.bur", tmp_path / "m001.bur"]
    tool.workflow_context = BurstWorkflowContext(bur_files=files)

    gs = FakeGs()
    BurstAnalysisTool._apply_context_to_burst_gs(tool, gs)
    assert gs.model.bur_files == [str(p) for p in files]
    assert events == ["changed"], "the view has to be told, or the list looks empty"

    # A second application must not append the same files again.
    BurstAnalysisTool._apply_context_to_burst_gs(tool, gs)
    assert gs.model.bur_files == [str(p) for p in files]


def test_accurate_fret_receives_one_burst_table(tmp_path: Path) -> None:
    """The calibration reads a burst table, and a .bur is one."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BurstAnalysisTool,
        BurstWorkflowContext,
    )

    loaded: list[str] = []

    class FakeModel:
        filename = ""

        def set_filename(self, path):
            loaded.append(str(path))
            self.filename = str(path)

    class FakeAccurateFret:
        model = FakeModel()

    tool = BurstAnalysisTool.__new__(BurstAnalysisTool)
    files = [tmp_path / "m000.bur", tmp_path / "m001.bur"]
    tool.workflow_context = BurstWorkflowContext(bur_files=files)

    panel = FakeAccurateFret()
    BurstAnalysisTool._apply_context_to_accurate_fret(tool, panel)
    assert loaded == [str(files[0])]

    BurstAnalysisTool._apply_context_to_accurate_fret(tool, panel)
    assert loaded == [str(files[0])], "a table already loaded here is not replaced"


def test_new_panels_are_wired_into_downstream_propagation() -> None:
    """A panel that is not in the role tuple only ever sees stale context."""
    import inspect

    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    src = inspect.getsource(BurstAnalysisTool._apply_context_to_downstream)
    for role in ('"burst_fcs"', '"burst_gs"', '"accurate_fret"'):
        assert role in src, f"{role} misses upstream changes"


def test_every_panel_role_has_an_applier() -> None:
    """Adding a panel without a hand-off leaves the user re-picking files by hand."""
    import inspect

    from chisurf.plugins.burst.burst_analysis.gui.tool import (
        BURST_PANELS,
        BurstAnalysisTool,
    )

    src = inspect.getsource(BurstAnalysisTool._apply_context_to_panel)
    for panel in BURST_PANELS:
        role = panel.get("role") or ""
        if not role or role in {"separator", "data"}:
            continue
        assert f'"{role}"' in src, f"panel {panel['name']!r} gets no workflow context"
