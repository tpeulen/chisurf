r"""Global View: the parameter network of every open fit, and the links in it.

The window is a standard ChiSurf dock tool — a canonical toolbar over a
:class:`~chisurf.gui.widgets.dock_area.DockArea` — so its panels can be split,
tabbed, torn apart and remembered like every other tool's. The network itself is
drawn by :class:`~chisurf.plugins.core.globalview.gui.network_widget.ParameterNetworkWidget`,
on the shared node-link marks the state-scheme diagram uses.

What replaced what, and why: the graph used to be a ``pyqtgraph.GraphItem``
inside a ``GraphicsLayoutWidget``, rebuilt from scratch on every redraw and
stacked into a growing ``QVBoxLayout``; its nodes were sized in data
coordinates, so labels, arrowheads and node radii all changed size with the
layout. The controls sat in two ``QGroupBox``\ es above the plot in a grid whose
second column absorbed the whole window width, which is why a spin box for a
number between 0 and 1 was eight hundred pixels wide.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from chisurf.core import graph as cg
from qtpy import QtCore, QtWidgets

import chisurf as cs
import chisurf.core.fitting.fit
import chisurf.core.models
import chisurf.core.parameter
import chisurf.gui.widgets
from chisurf import logging
from chisurf.core.parameter import Parameter
from chisurf.gui import dialogs
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.dock_area import DockArea
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client
from chisurf.gui.widgets.tool_buttons import action_button
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool
from chisurf.plugins.core.globalview.api.graph import build_graph as api_build_graph
from chisurf.plugins.core.globalview.gui.adapter import (
    NODE_COLORS,
    compute_layout,
    graph_result_to_graph,
)
from chisurf.plugins.core.globalview.gui.network_widget import ParameterNetworkWidget

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    persist_plugin_state = lambda n: lambda c: c


GRAPH_LAYOUTS = [
    "kamada_kawai",
    "spring",
    "shell",
    "arf",
    "spectral",
]

#: How long a burst of change events is allowed to settle before the network is
#: rebuilt. A running fit emits a parameter event per iteration, and rebuilding
#: on each one means re-running a layout algorithm hundreds of times for a graph
#: whose *shape* never changed — so the events are coalesced into one wake-up.
REFRESH_DEBOUNCE_MS = 300

#: Dock titles. Named once, because the authored default layout addresses docks
#: by their tab text and a typo there silently falls back to plain tabs.
DOCK_NETWORK = "🕸️ Network"
DOCK_PARAMETERS = f"{Glyphs.GRID} Parameters"
DOCK_SELECTION = f"{Glyphs.LINK} Selection"
DOCK_VIEW = f"{Glyphs.PALETTE} View"


@persist_plugin_state("globalview")
class GraphWizard(ChisurfDockTool):
    """Dockable window showing fits, their parameters, and the links between them."""

    graph_layouts = GRAPH_LAYOUTS

    node_colors = dict(NODE_COLORS)

    tool_settings_name = "GlobalViewTool"

    def __init__(
        self,
        fit_list: Optional[List[Any]] = None,
        parent=None,
        connect_owners: bool = False,
        include_fixed: bool = False,
        *args,
        **kwargs,
    ):
        super().__init__(parent)
        if fit_list is None:
            fc = get_fitting_client()
            fit_list = fc.get_fit_objects() if fc is not None else []
        self.fit_list = fit_list

        self.G: cg.Graph = None
        self.node_objects: Dict[Any, Any] = {}
        self.node_data: Dict[str, Any] = {}
        self.connections: List[List[int]] = []

        #: Structure of the network as last drawn — node names, kinds and edges.
        #: A value changing is not a reason to re-run a layout algorithm; only a
        #: parameter appearing, disappearing, or changing what it *is* (fixed,
        #: linked, free) can move a node.
        self._signature: Optional[tuple] = None
        #: Set when a change arrived that has not been drawn — because auto
        #: refresh is off, or because the window is not on screen.
        self._stale = False
        #: Whether the window has been shown at its real size, and a dock layout
        #: is therefore worth remembering. See :meth:`_save_dock_layout`.
        self._layout_ready = False

        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._refresh_if_changed)

        self.setWindowTitle("🕸️ Global View — parameter network")
        self.resize(1150, 760)

        self._build_ui()
        self._check_connect_owners.setChecked(bool(connect_owners))
        self._check_include_fixed.setChecked(bool(include_fixed))
        self._connect_signals()

        self.recompute_graph()
        self.restore_window_geometry()
        self._connect_events()

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build the toolbar, the docks and the status bar."""
        self._build_toolbar()

        self.dock_area = DockArea(self)
        self.dock_area.setContextMenuEnabled(True)
        self.dock_area.setContextMenuMode("basic")
        self.setCentralWidget(self.dock_area)

        self.graph_widget = ParameterNetworkWidget(self)
        self.dock_area.addTab(self.graph_widget, DOCK_NETWORK, close_mode="hide")

        self.parameters_form = self._build_parameters_panel()
        self.dock_area.addTab(self.parameters_form, DOCK_PARAMETERS, close_mode="hide")

        self.dock_area.addTab(self._build_selection_panel(), DOCK_SELECTION, close_mode="hide")
        self.dock_area.addTab(self._build_view_panel(), DOCK_VIEW, close_mode="hide")

        self._restore_dock_layout()
        self.dock_area.layoutChanged.connect(self._save_dock_layout)

        self.statusBar().showMessage(
            "Drag one parameter onto another to link it — the second is the master."
        )

    def _build_toolbar(self) -> None:
        """Create the canonical toolbar: file actions, then the link actions."""
        self.toolbar = QtWidgets.QToolBar("Global View", self)
        self.toolbar.setObjectName("globalview_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QtCore.QSize(16, 16))
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.toolbar)

        self._btn_load = action_button(
            "add", tooltip="Load a parameter network from a GraphML (.gml) file",
        )
        self._btn_save = action_button(
            "save", tooltip="Save the current parameter network to a GraphML (.gml) file",
        )
        self._btn_redraw = action_button(
            "refresh",
            tooltip=(
                "Rebuild the network from the current fits and links, and lay it "
                "out again"
            ),
        )
        # Icon-only everywhere else, but this is the one button someone reaches
        # for when the picture disagrees with the fits, so it says so.
        self._btn_redraw.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._btn_redraw.setText(" Refresh")

        # Auto refresh is event-driven, coalesced and structure-checked (see
        # ``_on_change_event``), but it is still work happening behind the user's
        # back — so it is a switch, and turning it off says so in the status bar
        # rather than silently showing a stale network.
        self._check_auto = QtWidgets.QCheckBox("auto")
        self._check_auto.setChecked(True)
        self._check_auto.setToolTip(
            "Redraw when a fit or a link changes. Changes are coalesced and the "
            "layout only re-runs when the network's shape actually changed, so a "
            "running fit does not cost anything here. Untick to refresh by hand."
        )

        self.toolbar.addWidget(self._btn_load)
        self.toolbar.addWidget(self._btn_save)
        self.toolbar.addWidget(self._btn_redraw)
        self.toolbar.addWidget(self._check_auto)
        self.toolbar.addSeparator()

        self._btn_link = QtWidgets.QToolButton()
        self._btn_link.setText(f"{Glyphs.LINK} Link")
        self._btn_link.setToolTip(
            "Link the two selected parameters — the first selected (red rim) is "
            "the master the second follows"
        )
        self.toolbar.addWidget(self._btn_link)

        self._btn_clear_links = QtWidgets.QToolButton()
        self._btn_clear_links.setText(f"{Glyphs.CLEAR} Unlink")
        self._btn_clear_links.setToolTip("Remove the links of the selected parameters")
        self.toolbar.addWidget(self._btn_clear_links)

        self._check_clear_all = QtWidgets.QCheckBox("all")
        self._check_clear_all.setToolTip(
            "Unlink applies to EVERY parameter in every fit, not just the selection"
        )
        self.toolbar.addWidget(self._check_clear_all)

        self.toolbar.addSeparator()
        self._btn_reset_view = QtWidgets.QToolButton()
        self._btn_reset_view.setText("⌖")
        self._btn_reset_view.setToolTip(
            "Fit the network back into the panel — undoes zoom, pan and any "
            "nodes you dragged"
        )
        self.toolbar.addWidget(self._btn_reset_view)

        self.add_toolbar_help(
            self.toolbar, resource="help.md", title="Global View — help",
        )

    def _build_view_panel(self) -> QtWidgets.QWidget:
        """Create the layout/appearance panel."""
        panel = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(panel)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        group = QtWidgets.QGroupBox("Network")
        form = QtWidgets.QFormLayout(group)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._combo_layout = QtWidgets.QComboBox()
        self._combo_layout.addItems(self.graph_layouts)
        self._combo_layout.setToolTip(
            "Algorithm that places the nodes: kamada_kawai and spring keep linked "
            "parameters near each other, shell and spectral expose structure"
        )
        form.addRow("Layout", self._combo_layout)

        self._spin_node_size = QtWidgets.QDoubleSpinBox()
        self._spin_node_size.setRange(4.0, 40.0)
        self._spin_node_size.setSingleStep(1.0)
        self._spin_node_size.setDecimals(0)
        self._spin_node_size.setSuffix(" px")
        self._spin_node_size.setValue(13.0)
        self._spin_node_size.setToolTip("Radius of a parameter node; fits are drawn larger")
        form.addRow("Node size", self._spin_node_size)

        self._spin_graph_scale = QtWidgets.QDoubleSpinBox()
        self._spin_graph_scale.setRange(0.2, 8.0)
        self._spin_graph_scale.setSingleStep(0.1)
        self._spin_graph_scale.setValue(1.0)
        self._spin_graph_scale.setToolTip(
            "Spread the network beyond the panel (pan and zoom to read it) — how a "
            "crowded graph is pulled apart without changing its layout"
        )
        form.addRow("Spread", self._spin_graph_scale)

        self._check_connect_owners = QtWidgets.QCheckBox("Connect base")
        self._check_connect_owners.setToolTip(
            "Draw a line between every pair of owners — every fit AND every "
            "registered parameter group (ndX, a calculator), so a plugin's "
            "working model sits with the fits it can be linked to instead of "
            "floating apart. Visual only: it links nothing."
        )
        form.addRow(self._check_connect_owners)

        self._check_include_fixed = QtWidgets.QCheckBox("Include fixed")
        # Named so the guided tour can point at it: this window has no view
        # spec, so a step's ``attr`` resolves to nothing and the step would be
        # shown centred, teaching nobody where the control is.
        self._check_include_fixed.setObjectName("globalview_include_fixed")
        self._check_include_fixed.setToolTip(
            "Show parameters held fixed; they cannot be fitted but can still be linked"
        )
        form.addRow(self._check_include_fixed)

        outer.addWidget(group)
        outer.addStretch(1)
        return panel

    def _build_selection_panel(self) -> QtWidgets.QWidget:
        """Create the panel holding editors for the selected parameters."""
        panel = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(panel)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        self._selection_hint = QtWidgets.QLabel(
            "Click a parameter node to edit it here. Click a second one and press "
            f"{Glyphs.LINK} Link to make it follow the first."
        )
        self._selection_hint.setWordWrap(True)
        self._selection_hint.setStyleSheet("color: #8a8f98; font-size: 11px;")
        outer.addWidget(self._selection_hint)

        self.parameter_layout = QtWidgets.QVBoxLayout()
        self.parameter_layout.setContentsMargins(0, 0, 0, 0)
        self.parameter_layout.setSpacing(2)
        holder = QtWidgets.QWidget()
        holder.setLayout(self.parameter_layout)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        outer.addWidget(scroll, 1)
        return panel

    def _build_parameters_panel(self) -> QtWidgets.QWidget:
        """Create the AutoForm table of every parameter, in and out of fits."""
        # Every fit parameter plus every registered out-of-fit group. Graph
        # resync happens via the ``parameter.``/``fit.`` event subscriptions in
        # ``_connect_events``; the table refreshes itself on the same events.
        from chisurf.gui.autoform.auto_form import AutoForm
        from chisurf.plugins.core.globalview.parameters_model import (
            GlobalViewParametersModel,
        )

        return AutoForm(GlobalViewParametersModel())

    def _connect_signals(self) -> None:
        """Wire the toolbar, the controls and the canvas."""
        self._btn_link.clicked.connect(self.link_selection)
        self._btn_clear_links.clicked.connect(self.link_clear)
        self._btn_redraw.clicked.connect(lambda: self.recompute_graph(force=True))
        self._check_auto.toggled.connect(self._on_auto_toggled)
        self._btn_save.clicked.connect(self.write_graph)
        self._btn_load.clicked.connect(self.read_graph)
        self._btn_reset_view.clicked.connect(self.graph_widget.refit)

        # These change what is drawn or where, so they always redraw — the
        # structure check that guards the automatic refresh must not swallow a
        # redraw the user explicitly asked for.
        for control in (self._check_connect_owners, self._check_include_fixed):
            control.stateChanged.connect(lambda _=None: self.recompute_graph(force=True))
        self._combo_layout.currentIndexChanged.connect(
            lambda _=None: self.recompute_graph(force=True)
        )
        self._spin_graph_scale.valueChanged.connect(
            lambda _=None: self.recompute_graph(force=True)
        )
        # Node size is pure appearance — it does not change the layout, so it
        # repaints rather than re-running the layout algorithm.
        self._spin_node_size.valueChanged.connect(self._apply_node_size)

        self.graph_widget.selectionChanged.connect(self.callback_selection)
        self.graph_widget.linkRequested.connect(self.on_link_requested)
        self.graph_widget.linkRemovalRequested.connect(self.on_link_removal_requested)

    def _apply_node_size(self, value: float) -> None:
        """Repaint the canvas at a new node radius."""
        self.graph_widget.node_radius = float(value)
        self.graph_widget.update_graph()

    # ── dock layout persistence ───────────────────────────────────────

    def _dock_settings(self) -> QtCore.QSettings:
        return QtCore.QSettings("chisurf", self.tool_settings_name)

    def _save_dock_layout(self) -> None:
        """Persist the dock arrangement — once it is worth persisting.

        ``layoutChanged`` fires while the docks are being built, when the area
        is about a hundred pixels wide and every split reads as 48/48. Saved,
        that becomes the layout restored on the next launch, and it *wins over
        the authored default* — so the tool would come up half controls, half
        network, permanently, without anyone having dragged anything.
        """
        if not self._layout_ready or self.dock_area.width() < 200:
            return
        try:
            state = self.dock_area.get_layout_state()
            self._dock_settings().setValue("dock_layout", json.dumps(state))
        except Exception as exc:
            logging.log(0, f"globalview: could not save dock layout ({exc})")

    def _restore_dock_layout(self) -> None:
        """Restore the dock arrangement, or author the default split."""
        try:
            value = self._dock_settings().value("dock_layout")
            state = json.loads(value) if isinstance(value, str) else value
            if isinstance(state, dict) and self.dock_area.set_layout_state(
                state, emit_change=False
            ):
                return
        except Exception as exc:
            logging.log(0, f"globalview: could not restore dock layout ({exc})")

        # Default: the network (with the parameter table behind it) takes the
        # width, the two narrow panels share a column on the right. Without this
        # all four arrive as one row of tabs and the canvas is the only one ever
        # visible.
        default_layout = {
            "version": 1,
            "root": {
                "type": "splitter",
                "orientation": "horizontal",
                "sizes": [800, 330],
                "children": [
                    {
                        "type": "tab",
                        "current_index": 0,
                        "tabs": [
                            {"widget_key": t, "tab_name": t, "tab_text": t}
                            for t in (DOCK_NETWORK, DOCK_PARAMETERS)
                        ],
                    },
                    {
                        "type": "tab",
                        "current_index": 0,
                        "tabs": [
                            {"widget_key": t, "tab_name": t, "tab_text": t}
                            for t in (DOCK_SELECTION, DOCK_VIEW)
                        ],
                    },
                ],
            },
            "active_tab_widget": None,
            "current_index": 0,
        }
        try:
            self.dock_area.set_layout_state(default_layout, emit_change=False)
        except Exception as exc:
            logging.log(0, f"globalview: could not apply default dock layout ({exc})")

    # ── graph ─────────────────────────────────────────────────────────

    def recompute_graph(self, force: bool = False) -> None:
        """Rebuild the graph, lay it out, and hand it to the canvas.

        Parameters
        ----------
        force : bool, optional
            Lay the network out again even when its structure is unchanged. The
            automatic refresh leaves this ``False``, so a fit running for a
            thousand iterations redraws nothing: the *values* moved, and values
            do not decide where a node goes. Anything the user asked for —
            Refresh, a different layout, a new spread — passes ``True``.
        """
        self.node_data = self.make_graph_plot(
            fit_list=self.fit_list,
            connect_owners=self.connect_owners,
            include_fixed=self.include_fixed,
            node_size=self.node_size,
            force=force,
        )

    def make_graph_plot(
        self,
        fit_list: List[Any],
        update_callback=None,
        node_size: float = 13.0,
        connect_owners: bool = False,
        include_fixed: bool = True,
        force: bool = True,
    ) -> Dict[str, Any]:
        """Rebuild the network and draw it. Returns the node bookkeeping."""
        connections, node_data = self.make_graph(
            connect_owners, fit_list=fit_list, include_fixed=include_fixed,
        )
        edges = self._reindexed_edges(connections, node_data["ids"])
        signature = (
            tuple(node_data["names"]),
            tuple(node_data["types"]),
            tuple(sorted(tuple(e) for e in edges)),
        )
        self._stale = False
        if not force and signature == self._signature:
            # Same nodes, same kinds, same edges: the picture is already right.
            self._update_status(node_data)
            return node_data
        self._signature = signature

        pos = self.get_node_positions()
        positions = [pos[i] for i in node_data["ids"]]

        self.graph_widget.node_radius = float(node_size)
        self.graph_widget.set_graph(
            positions,
            edges,
            node_data["names"],
            node_data["types"],
            spread=self.graph_scale,
        )
        self._update_status(node_data)
        return node_data

    @staticmethod
    def _reindexed_edges(connections, node_ids) -> List[List[int]]:
        """Re-express edges as positions in `node_ids`.

        The canvas indexes nodes by their position in the arrays it is handed,
        while the graph names them by node id — and the two diverge as soon as
        ``include_fixed`` drops a node. Feeding raw ids straight through is how
        an edge ends up attached to the wrong parameter.
        """
        order = {n: i for i, n in enumerate(node_ids)}
        edges = []
        for a, b in connections:
            if a in order and b in order:
                edges.append([order[a], order[b]])
        return edges

    # ── refreshing ────────────────────────────────────────────────────

    def _on_change_event(self) -> None:
        """Handle a fit/parameter change: decide whether a redraw is needed.

        Called on the GUI thread for every ``fit.``/``parameter.`` event, which
        during a fit means once per iteration — so it must be cheap. It is: it
        either restarts a timer or sets a flag. The actual work happens once,
        after the events stop arriving, and only if the network's shape changed.
        """
        if not self._check_auto.isChecked():
            self._mark_stale()
            return
        self._refresh_timer.start()

    def _refresh_if_changed(self) -> None:
        """Redraw when the network's structure has actually changed."""
        if not self.isVisible():
            # Nothing to look at: remember, and catch up in ``showEvent``.
            self._stale = True
            return
        self.recompute_graph(force=False)

    def _mark_stale(self) -> None:
        """Say the picture no longer matches the fits."""
        self._stale = True
        self.statusBar().showMessage(
            "The fits changed — press ⟳ Refresh to redraw the network."
        )

    def _on_auto_toggled(self, enabled: bool) -> None:
        """Catch up immediately when automatic refreshing is switched back on."""
        if enabled and self._stale:
            self.recompute_graph(force=True)
        elif not enabled:
            self.statusBar().showMessage(
                "Automatic refresh off — press ⟳ Refresh after changing a fit.",
                5000,
            )

    def showEvent(self, event) -> None:                          # noqa: N802 (Qt)
        """Catch up on changes that arrived while the window was hidden."""
        super().showEvent(event)
        # Now the docks have their real geometry, so what the user does to them
        # from here is theirs to remember.
        QtCore.QTimer.singleShot(0, self._mark_layout_ready)
        if self._stale and self._check_auto.isChecked():
            self.recompute_graph(force=True)

    def _mark_layout_ready(self) -> None:
        """Start remembering dock arrangements (deferred until after layout)."""
        self._layout_ready = True

    def _update_status(self, node_data: Dict[str, Any]) -> None:
        """Report what is on screen, since an empty canvas is otherwise mute."""
        types = node_data.get("types", [])
        n_owner = sum(1 for t in types if t in (0, 4))
        n_param = len(types) - n_owner
        n_linked = sum(1 for t in types if t == 2)
        if not types:
            self.statusBar().showMessage(
                "No fits and no registered parameter groups — nothing to draw."
            )
            return
        self.statusBar().showMessage(
            f"{n_owner} owners · {n_param} parameters · {n_linked} linked. "
            "Drag one parameter onto another to link it."
        )

    def make_graph(
        self,
        connect_owners: bool = False,
        include_fixed: bool = False,
        fit_list: Optional[List[Any]] = None,
    ):
        """Build the graph and the per-node bookkeeping the GUI needs."""
        if fit_list is None:
            fc = get_fitting_client()
            fit_list = fc.get_fit_objects() if fc is not None else []
        G, node_objects, connections = self.build_graph(
            include_fixed, fit_list, connect_owners
        )

        node_names = []
        node_ids = []
        node_types = []
        for node in G.nodes:
            o = node_objects[node]
            if o is not None and isinstance(o, cs.core.parameter.Parameter):
                if o.fixed:
                    if not include_fixed:
                        continue
                    node_types.append(1)
                else:
                    node_types.append(2 if o.is_linked else 3)
            elif G.nodes.get(node, {}).get("node.type") == "group":
                node_types.append(4)
            else:
                node_types.append(0)
            node_names.append(G.nodes[node]["node.name"])
            node_ids.append(node)

        fit_indices = [G.nodes.get(k, {}).get("fit.idx") for k in node_ids]

        # Which fit or group each parameter belongs to. Two fits of the same
        # model give their parameters the same names, so "tau1" on its own does
        # not say which one is being edited — and the editor panel showed
        # exactly that: two rows both labelled ``tau1``.
        owner_of = {
            src: tgt for src, tgt in connections
            if G.nodes.get(tgt, {}).get("node.type") in ("fit", "group")
        }
        owners = [
            str(G.nodes.get(owner_of.get(k), {}).get("node.name", ""))
            for k in node_ids
        ]

        self.G = G
        return connections, {
            "ids": node_ids,
            "types": node_types,
            "names": node_names,
            "owners": owners,
            "objects": [node_objects[k] for k in node_ids],
            "fit_indices": fit_indices,
        }

    @staticmethod
    def build_graph(
        include_fixed: bool = True,
        fit_list: List[Any] = None,
        connect_owners: bool = False,
        group_list: Optional[List[Any]] = None,
        **kwargs,
    ):
        """Build the node graph and resolve every node to its live object.

        Returns
        -------
        tuple
            ``(G, node_objects, edges)``. The node graph is what the layout
            algorithms consume, but its edges are **undirected** and come back
            renumbered low-to-high — so a link's follower → master direction is
            lost the moment it enters the graph, and drawing arrows from it
            points half of them the wrong way. The directed edges are therefore
            carried out separately, straight from the graph builder.
        """
        if fit_list is None:
            fc = get_fitting_client()
            fit_list = fc.get_fit_objects() if fc is not None else []
        if group_list is None:
            from chisurf.core.registry.parameter_groups import (
                iter_registered_parameter_groups,
            )
            group_list = iter_registered_parameter_groups()
        api_result = api_build_graph(
            fit_list, include_fixed, connect_owners, group_list=group_list,
        )
        G = graph_result_to_graph(api_result)

        from chisurf.core.base import Base

        # Map each registered group by its owner_id so "group" owner nodes resolve
        # to the live group object; parameters resolve globally by their UUID.
        groups_by_owner = {str(oid): g for oid, _label, g in group_list}
        node_objects = {}
        for n in api_result.nodes:
            if n.node_type == "fit":
                node_objects[n.node_idx] = (
                    fit_list[n.fit_idx] if 0 <= n.fit_idx < len(fit_list) else None
                )
            elif n.node_type == "group":
                node_objects[n.node_idx] = groups_by_owner.get(n.owner_id)
            else:
                obj = Base.find_by_uuid(n.param_uid) if n.param_uid else None
                if obj is None and 0 <= n.fit_idx < len(fit_list):
                    try:
                        obj = getattr(
                            fit_list[n.fit_idx].model, "parameters_all_dict", {}
                        ).get(n.name)
                    except Exception:
                        obj = None
                node_objects[n.node_idx] = obj
        edges = [(e.source, e.target) for e in api_result.edges]
        return G, node_objects, edges

    def get_node_positions(
        self,
        G: cg.Graph = None,
        graph_scale: float = None,
        graph_layout: str = None,
    ):
        """Return node positions from the selected layout algorithm."""
        if G is None:
            G = self.G
        if graph_layout is None:
            graph_layout = self.graph_layout
        # The canvas fits whatever range the layout returns to the panel, so the
        # layout's own scale is arbitrary; the user's "spread" is applied there.
        return compute_layout(G, graph_layout, 1.0)

    # ── properties ────────────────────────────────────────────────────

    @property
    def clear_all(self) -> bool:
        """Whether Unlink applies to every parameter rather than the selection."""
        return self._check_clear_all.isChecked()

    @property
    def selected_nodes(self) -> List[Any]:
        """Return the live objects behind the selected nodes, oldest first."""
        objects = self.node_data.get("objects", [])
        return [
            objects[i] for i in self.graph_widget.selected_nodes_idx
            if 0 <= i < len(objects)
        ]

    @property
    def graph_layout(self) -> str:
        """Name of the selected layout algorithm."""
        return self._combo_layout.currentText()

    @property
    def include_fixed(self) -> bool:
        """Whether fixed parameters are drawn."""
        return self._check_include_fixed.isChecked()

    @property
    def connect_owners(self) -> bool:
        """Whether fit nodes are joined to each other."""
        return self._check_connect_owners.isChecked()

    @property
    def graph_scale(self) -> float:
        """Spread multiplier applied to the fitted layout."""
        return self._spin_graph_scale.value()

    @property
    def node_size(self) -> float:
        """Parameter-node radius, in pixels."""
        return self._spin_node_size.value()

    # ── selection ─────────────────────────────────────────────────────

    def callback_selection(self, *args) -> None:
        """Show an editor for every selected parameter, under its owner's name."""
        cs.gui.widgets.general.clear_layout(self.parameter_layout)
        indices = [
            i for i in self.graph_widget.selected_nodes_idx
            if 0 <= i < len(self.node_data.get("objects", []))
        ]
        owners = self.node_data.get("owners", [])
        objects = self.node_data.get("objects", [])
        shown = 0
        for rank, i in enumerate(indices):
            node = objects[i]
            if node is None:
                continue
            try:
                w = cs.gui.widgets.fitting.widgets.make_fitting_parameter_widget(node)
            except Exception:
                continue
            owner = owners[i] if i < len(owners) else ""
            role = " · master" if rank == 0 and len(indices) > 1 else ""
            caption = QtWidgets.QLabel(f"{owner}{role}" if owner else role.strip(" ·"))
            caption.setStyleSheet("color: #8a8f98; font-size: 10px;")
            self.parameter_layout.addWidget(caption)
            self.parameter_layout.addWidget(w)
            shown += 1
        self.parameter_layout.addStretch(1)
        self._selection_hint.setVisible(shown < 2)

    # ── linking ───────────────────────────────────────────────────────

    def _fit_idx_for_node(self, obj: Any) -> Optional[int]:
        try:
            idx = self.node_data.get("objects", []).index(obj)
            return self.node_data.get("fit_indices", [])[idx]
        except (ValueError, IndexError):
            return None

    def _validate_and_link(self, source, target) -> bool:
        if source is None or target is None:
            return False
        if Parameter.check_recursive_link(target, source):
            msg = (
                f"Cannot link '{source.name}' → '{target.name}': "
                "this would create a cyclic dependency between parameters."
            )
            cs.logging.log(0, "Cycle detected: " + msg)
            dialogs.warning(self, "Linking Error", msg)
            return False
        fc = get_fitting_client()
        if fc is not None:
            src_fit_idx = self._fit_idx_for_node(source)
            tgt_fit_idx = self._fit_idx_for_node(target)
            kw = dict(
                parameter_name=str(source.name),
                target_parameter_name=str(target.name),
            )
            # A fit parameter keeps the fit-addressed path; an out-of-fit (group)
            # parameter — fit_idx < 0 — is addressed by its global UUID so it joins
            # the same link graph as fits.
            if src_fit_idx is not None and src_fit_idx >= 0:
                kw["fit_index"] = src_fit_idx
            else:
                kw["parameter_uid"] = str(getattr(source, "unique_identifier", ""))
            if tgt_fit_idx is not None and tgt_fit_idx >= 0:
                kw["target_fit_index"] = tgt_fit_idx
            else:
                kw["target_parameter_uid"] = str(getattr(target, "unique_identifier", ""))
            fc.link_parameters(**kw)
        return True

    def on_link_requested(self, source_idx: int, target_idx: int) -> None:
        """Link the dragged parameter to the one it was dropped on."""
        objects = self.node_data.get("objects", [])
        if not (0 <= source_idx < len(objects) and 0 <= target_idx < len(objects)):
            return
        if self._validate_and_link(objects[source_idx], objects[target_idx]):
            self.recompute_graph()

    def on_link_removal_requested(self, source_idx: int) -> None:
        """Break the link of the parameter whose arrow was double-clicked."""
        objects = self.node_data.get("objects", [])
        if not 0 <= source_idx < len(objects):
            return
        param = objects[source_idx]
        fit_idx = self.node_data.get("fit_indices", [None])[source_idx]
        fc = get_fitting_client()
        if fc is not None and param is not None:
            fc.unlink_parameter(parameter_name=str(param.name), fit_index=fit_idx)
        self.recompute_graph()

    def link_selection(self) -> None:
        """Link the two selected parameters — the first selected is the master."""
        logging.log(0, "link_selection(self)")
        nodes = self.selected_nodes
        if len(nodes) < 2:
            self.statusBar().showMessage(
                "Select two parameter nodes first — the first one is the master.", 5000
            )
            return
        target, source = nodes[:2]
        if self._validate_and_link(source, target):
            self.recompute_graph()

    def link_clear(self) -> None:
        """Remove links from the selection, or from every parameter."""
        logging.log(0, "link_clear(self)")
        fc = get_fitting_client()
        if self.clear_all:
            for fit_idx, fit in enumerate(self.fit_list):
                for p in getattr(fit.model, "parameters_all", []):
                    if fc is not None:
                        fc.unlink_parameter(
                            parameter_name=str(p.name), fit_index=fit_idx,
                        )
        else:
            for n in self.selected_nodes:
                if n is None:
                    continue
                fit_idx = self._fit_idx_for_node(n)
                if fc is not None:
                    if fit_idx is not None and fit_idx >= 0:
                        fc.unlink_parameter(
                            parameter_name=str(n.name), fit_index=fit_idx,
                        )
                    else:
                        fc.unlink_parameter(
                            parameter_name=str(n.name),
                            parameter_uid=str(getattr(n, "unique_identifier", "")),
                        )
        self.recompute_graph()

    # ── GraphML I/O ───────────────────────────────────────────────────

    def read_graph(self, evt=None, *args, **kwargs):
        """Load a parameter network from GraphML and apply it to the fits."""
        path = kwargs.get(
            "path",
            cs.gui.widgets.get_filename(
                description="ChiSurf-GraphML",
                file_type="CS-GraphML (*.gml)",
            ),
        )
        if not path:
            return
        G = cg.read_graphml(path)
        self.link(G, **kwargs)

    def write_graph(self, evt=None, G: cg.Graph = None):
        """Save the current parameter network to GraphML."""
        if G is None:
            G = self.G
        path = cs.gui.widgets.save_file(
            description="ChiSurf-GraphML",
            file_type="CS-GraphML (*.gml)",
        )
        if not path:
            return
        cg.write_graphml(G, path, encoding="utf-8", prettyprint=True)
        self.statusBar().showMessage(f"Saved network to {path}", 5000)

    def get_fit(self, G, node):
        """Return the fit a graph node belongs to, or ``None``."""
        idx = G.nodes[node].get("fit.idx", -1)
        if idx is None or not (0 <= idx < len(self.fit_list)):
            return None
        return self.fit_list[idx]

    def get_parameters(self, G, node):
        """Return the live parameter a graph node refers to, or ``None``."""
        if G.nodes[node].get("node.type") != "parameter":
            return None
        # Resolve by global UUID first (works for out-of-fit group parameters);
        # fall back to the fit's parameter dict by name.
        uid = G.nodes[node].get("param.uid", "")
        if uid:
            from chisurf.core.base import Base
            p = Base.find_by_uuid(uid)
            if p is not None:
                return p
        fit = self.get_fit(G, node)
        if fit is None:
            return None
        return getattr(fit.model, "parameters_all_dict", {}).get(
            G.nodes[node]["node.name"]
        )

    @staticmethod
    def _node_param_address(G: cg.Graph, node: Any, param: Any) -> Dict[str, Any]:
        """Return the RPC address kwargs for a graph node's parameter.

        Fit parameters keep the fit-addressed path (``parameter_name`` +
        ``fit_index``); out-of-fit (group) parameters — ``fit.idx`` < 0 — are
        addressed by their global ``parameter_uid``.
        """
        fit_idx = G.nodes[node].get("fit.idx")
        if fit_idx is not None and fit_idx >= 0:
            return {"parameter_name": str(param.name), "fit_index": fit_idx}
        return {
            "parameter_name": str(param.name),
            "parameter_uid": str(getattr(param, "unique_identifier", "")),
        }

    def link(self, G: cg.Graph, clear_fist: bool = False, **kwargs):
        """Apply a loaded network: parameter values, fixed flags and links."""
        cs.logging.log(0, "link")
        self.G = G
        fc = get_fitting_client()

        if clear_fist:
            self.link_clear()

        for node in G.nodes:
            p = self.get_parameters(G, node)
            if p is not None and fc is not None:
                addr = self._node_param_address(G, node, p)
                fc.set_parameter_value(value=float(G.nodes[node]["value"]), **addr)
                fc.set_parameter_fixed(fixed=bool(G.nodes[node]["fixed"]), **addr)

        for edge in G.edges:
            n1, n2 = edge
            p1 = self.get_parameters(G, n1)
            p2 = self.get_parameters(G, n2)
            if p1 is not None and p2 is not None and fc is not None:
                kw = self._node_param_address(G, n2, p2)
                kw["target_parameter_name"] = str(p1.name)
                tgt_idx = G.nodes[n1].get("fit.idx")
                if tgt_idx is not None and tgt_idx >= 0:
                    kw["target_fit_index"] = tgt_idx
                else:
                    kw["target_parameter_uid"] = str(
                        getattr(p1, "unique_identifier", "")
                    )
                fc.link_parameters(**kw)

        self.recompute_graph()

    @staticmethod
    def skip_fit(fit, omitted_models: list[cs.core.models.Model] = None):
        """Return whether a fit is left out of the graph (a global fit is)."""
        if omitted_models is None:
            omitted_models = [cs.core.models.global_model.GlobalFitModel]
        return any(isinstance(fit.model, c) for c in omitted_models)

    # ── events ────────────────────────────────────────────────────────

    def _connect_events(self) -> None:
        """Subscribe to server events that require a graph rebuild."""
        fc = get_fitting_client()
        if fc is None:
            return
        self._subscription_tokens = []
        for topic in ("fit.", "parameter."):
            # The event may arrive off the GUI thread, so it is bounced through
            # the event loop before touching a widget; ``_on_change_event`` then
            # coalesces the burst.
            cb = lambda p: QtCore.QTimer.singleShot(0, self._on_change_event)
            fc.subscribe(topic, cb)
            self._subscription_tokens.append((topic, cb))

    def closeEvent(self, event):
        """Unsubscribe and remember the window geometry."""
        fc = get_fitting_client()
        if fc is not None:
            for topic, cb in getattr(self, "_subscription_tokens", []):
                try:
                    fc.unsubscribe(topic, cb)
                except Exception:
                    pass
        self.save_window_geometry()
        super().closeEvent(event)


if __name__ == "plugin":
    graph_wiz = GraphWizard()
    graph_wiz.show()

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    app.aboutToQuit.connect(app.deleteLater)
    graph_wiz = GraphWizard()
    graph_wiz.show()
    sys.exit(app.exec_())
