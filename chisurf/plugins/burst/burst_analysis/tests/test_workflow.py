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
    # IRF & Background feeds the MLE fit, so it comes before MLE-Lifetime rather
    # than dangling at the very bottom.
    assert labels == [
        "📂 1. Data Selection",
        "🔢 2. Channels",
        "🔎 3. Burst Selection",
        "📊 4. BVA",
        "✨ 5. IRF & Background",
        "🎯 6. MLE-Lifetime",
        "🔀 7. H2MM",
        "📋 8. Browser",
        "────────",
        "🌙 Background",
    ]
    assert BURST_PANELS[8]["separator"] is True


def test_h2mm_panel_is_flagged_experimental() -> None:
    """The H2MM step carries the experimental flag so the nav shows ⚠ + banner."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BURST_PANELS

    h2mm = next(p for p in BURST_PANELS if p.get("role") == "h2mm")
    assert h2mm.get("experimental") is True
    assert h2mm.get("experimental_message")


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
                "dock_layout": '{"tabs": []}',
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

    assert widget.paths() == [spc.resolve()]
    assert [call[0] for call in calls] == ["mmfdb.objects.put", "raw_data.register"]
    payload = widget.mmfdb_payload()
    assert payload["imports"][str(spc.resolve())]["object_result"]["object"]["object_uuid"] == "obj-1"
    assert payload["imports"][str(spc.resolve())]["raw_data_result"]["raw_data"]["raw_data_id"] == "raw-1"
    widget.close()
    app.processEvents()


def test_data_selection_resolves_mmfdb_dataset_path() -> None:
    """MMFDB data selection resolves artifact IDs through mmfdb.datasets.open."""
    from qtpy import QtWidgets

    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstDataSelectionWidget

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    calls: list[tuple[str, dict]] = []

    class Client:
        def call(self, method, params=None):
            calls.append((method, params or {}))
            return {"local_path": "/tmp/from-mmfdb.spc"}

    widget = BurstDataSelectionWidget()
    widget._mmfdb_client = Client()
    assert widget._open_mmfdb_dataset("artifact-1") == "/tmp/from-mmfdb.spc"
    assert calls == [("mmfdb.datasets.open", {"artifact_id": "artifact-1"})]
    widget.close()
    app.processEvents()
