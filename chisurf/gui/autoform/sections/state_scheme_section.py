"""AutoForm custom section for clean HMM state scheme diagram visualization."""
from __future__ import annotations

import math
import numpy as np
from qtpy import QtWidgets, QtCore, QtGui

from .registry import register_section
from .rate_matrix_section import _resolve


#: Node fills, by state index. Cycled rather than exhausted: the palette used to
#: run out after four states and every state past the third came out the same
#: orange, which is a real limitation for a scheme with five.
_NODE_COLOURS = (
    ("#42a5f5", "#1565c0"),
    ("#66bb6a", "#2e7d32"),
    ("#ab47bc", "#6a1b9a"),
    ("#ffa726", "#e65100"),
    ("#26c6da", "#00838f"),
    ("#ec407a", "#ad1457"),
)


class SchemeCanvasWidget(QtWidgets.QWidget):
    """Drawing canvas for photophysical HMM state scheme diagram."""

    def __init__(self, parent_scheme_widget: StateSchemeWidget):
        super().__init__(parent_scheme_widget)
        self.scheme = parent_scheme_widget
        self.setMinimumSize(360, 240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        self.scheme._on_canvas_mouse_press(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        self.scheme._on_canvas_mouse_move(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        self.scheme._on_canvas_mouse_release(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        self.scheme._on_canvas_mouse_double_click(event)

    def wheelEvent(self, event: QtGui.QWheelEvent):
        self.scheme._on_canvas_wheel(event)

    def paintEvent(self, event: QtGui.QPaintEvent):
        self.scheme._on_canvas_paint(self, event)


class _RateMatrixScheme:
    """Adapt a plain rate-matrix group to the shape this canvas draws.

    The canvas was written against the FCS saturation model, which nests its
    generator under ``.dark`` and names its own states. Every *other* scheme in
    the tree is a bare
    :class:`~chisurf.core.fitting.kinetics.RateMatrixParameters` -- the shared,
    fittable kind -- so those are adapted here rather than teaching the drawing
    code two shapes. That is what lets the same diagram serve an MFD exchange
    scheme, an HMM, or anything else that grows a rate matrix.

    Parameters
    ----------
    group : RateMatrixParameters
        The scheme, exposing ``n_states`` and ``rate_matrix()``.
    labels : sequence of str, optional
        State names, in order.
    """

    def __init__(self, group, labels=None):
        self.dark = group
        self._labels = list(labels) if labels else None

    @property
    def n_states(self) -> int:
        """Return the number of states in the scheme."""
        return int(getattr(self.dark, "n_states", 0) or 0)

    @property
    def state_labels(self):
        """Return the state names, or ``None`` to let the canvas number them."""
        return self._labels

    @property
    def excitation_edge(self):
        """Return ``None``: a rate matrix has no externally pumped transition.

        Every transition in a plain scheme *is* one of its rates. Saying so
        explicitly is what stops a two-state FRET exchange being drawn with a
        phantom ``k_exc`` arrow out of a state that is not a ground state.
        """
        return None


@register_section("state_scheme")
class StateSchemeWidget(QtWidgets.QWidget):
    """Interactive HMM-style state diagram widget with photophysical node layout and curved edge routing."""

    def __init__(self, model, target: str = "", options: dict | None = None, **kwargs):
        super().__init__()
        self._model = model
        opts = dict(options) if options else {}
        opts.update(kwargs)
        self._attr = target or opts.get("target", "saturation")
        self._unit_attr = opts.get("unit_attr", "rate_unit")
        #: Where the state names come from when the scheme is a bare rate
        #: matrix, which carries rates but not names.
        self._labels_attr = opts.get("labels_attr", "state_names")
        #: The one transition driven by something other than a rate in the
        #: matrix -- a laser, in the photophysics models this canvas was first
        #: written for. It is drawn even at rate zero, because the excitation
        #: rate is not a fitted rate and would otherwise vanish from the diagram.
        #:
        #: **Declared, never assumed.** It used to be hardcoded as ``0 -> 1``,
        #: so every scheme was drawn as if state 0 were a ground state being
        #: pumped: a two-state FRET exchange came out with a phantom ``k_exc``
        #: arrow and its real backward rate missing.
        edge = opts.get("excitation_edge", None)
        self._excitation_edge = tuple(edge) if edge else None

        self.setMinimumSize(360, 280)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        # Outer Layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Header Bar: Scheme label, Presets ComboBox, 📂 Load, and 💾 Save (Single Row)
        top_bar = QtWidgets.QWidget(self)
        top_bar.setStyleSheet("QWidget { background: palette(button); border-bottom: 1px solid palette(mid); }")
        toolbar = QtWidgets.QHBoxLayout(top_bar)
        toolbar.setContentsMargins(4, 2, 4, 2)
        toolbar.setSpacing(4)

        self.combo_preset = QtWidgets.QComboBox(top_bar)
        self.combo_preset.setToolTip("Select photophysical kinetics scheme template")
        self.combo_preset.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.combo_preset.setMaximumWidth(200)

        # The scheme list belongs to the model, not to this widget: a private copy
        # here would silently disagree with the tool's own scheme selector as soon
        # as either gained an entry.
        names = None
        source = getattr(self._model, "scheme_names", None)
        if callable(source):
            try:
                names = [str(n) for n in source()]
            except Exception:
                names = None
        if not names:
            names = ["Custom"]
        for name in names:
            self.combo_preset.addItem(name)
            self.combo_preset.setItemData(
                self.combo_preset.count() - 1, name, QtCore.Qt.ToolTipRole
            )

        curr = str(getattr(self._model, "scheme_preset", ""))
        idx = self.combo_preset.findText(curr)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)

        btn_load = QtWidgets.QToolButton(top_bar)
        btn_load.setText("📂")
        btn_load.setToolTip("Load kinetics scheme from JSON file")
        btn_load.setCursor(QtCore.Qt.PointingHandCursor)
        btn_load.clicked.connect(self._on_load_scheme)

        btn_save = QtWidgets.QToolButton(top_bar)
        btn_save.setText("💾")
        btn_save.setToolTip("Save kinetics scheme to JSON file")
        btn_save.setCursor(QtCore.Qt.PointingHandCursor)
        btn_save.clicked.connect(self._on_save_scheme)

        toolbar.addWidget(self.combo_preset)
        toolbar.addStretch(1)
        toolbar.addWidget(btn_load)
        toolbar.addWidget(btn_save)

        # The bar offers preset schemes and load/save. A model that has no
        # presets has nothing to offer there: the combo reads "Custom" with
        # nothing else in it and the two buttons call methods the model does not
        # have. Shown anyway it is a strip of dead chrome above the diagram, so
        # it appears only when it does something.
        show = opts.get("show_toolbar", None)
        if show is None:
            show = len(names) > 1 or hasattr(self._model, "save_scheme_to_file")
        top_bar.setVisible(bool(show))
        main_layout.addWidget(top_bar)

        # 2. Scheme Canvas area
        self.canvas = SchemeCanvasWidget(self)
        main_layout.addWidget(self.canvas)

        self._spin = QtWidgets.QDoubleSpinBox(self.canvas)
        self._spin.setDecimals(3)
        self._spin.setRange(0.0, 1e9)
        self._spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self._spin.setAlignment(QtCore.Qt.AlignCenter)
        self._spin.setStyleSheet("QDoubleSpinBox { background: #1a1a1a; color: #ffffff; border: 2px solid #ff3333; selection-background-color: #ff3333; selection-color: #ffffff; font-size: 11px; font-weight: bold; } QLineEdit { selection-background-color: #ff3333; selection-color: #ffffff; }")
        self._spin.hide()
        self._spin.editingFinished.connect(self._on_edit_finished)
        self._editing_pair = None

        # Interactive Node, Arrow Arc & Scheme Dragging
        self._node_coords: dict[int, QtCore.QPointF] = {}
        self._arrow_offsets: dict[tuple[int, int], float] = {}
        self._dragged_node: int | None = None
        self._dragged_arrow: tuple[int, int] | None = None
        self._dragging_scheme = False
        self._drag_start_pos = QtCore.QPoint(0, 0)
        self._drag_offset = QtCore.QPointF(0, 0)
        self._last_n_states = -1
        #: View transform. Node coordinates are kept in an unscaled "scene"
        #: space so a zoom never disturbs a layout the user arranged by hand;
        #: the zoom lives here and is applied at paint time and inverted on the
        #: way back in for hit-testing.
        self._zoom = 1.0
        self._zoom_origin = QtCore.QPointF(0.0, 0.0)

    AUTOFORM_REFRESH = True
    is_form_field = False

    def _on_preset_changed(self, text: str):
        if hasattr(self._model, "scheme_preset"):
            self._model.scheme_preset = text
        self.refresh()

    def refresh(self):
        """Keep preset combobox and canvas in sync with model."""
        if hasattr(self, "combo_preset") and hasattr(self._model, "scheme_preset"):
            current = str(getattr(self._model, "scheme_preset", ""))
            if current and self.combo_preset.currentText() != current:
                idx = self.combo_preset.findText(current)
                if idx >= 0:
                    self.combo_preset.blockSignals(True)
                    self.combo_preset.setCurrentIndex(idx)
                    self.combo_preset.blockSignals(False)
        self.canvas.update()

    def _on_load_scheme(self):
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Kinetics Scheme", "", "JSON Files (*.json);;All Files (*)"
        )
        if filepath:
            if hasattr(self._model, "load_scheme_from_file"):
                self._model.load_scheme_from_file(filepath)
            self.refresh()

    def _on_save_scheme(self):
        filepath, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Kinetics Scheme", "custom_scheme.json", "JSON Files (*.json);;All Files (*)"
        )
        if filepath:
            if hasattr(self._model, "save_scheme_to_file"):
                self._model.save_scheme_to_file(filepath)
            self.refresh()

    def _get_saturation(self):
        """Return the scheme to draw, whatever shape the model keeps it in."""
        obj = getattr(self._model, "saturation", None)
        if obj is None:
            obj = getattr(self._model, self._attr, None)
        if obj is not None and not hasattr(obj, "dark") and hasattr(obj, "rate_matrix"):
            labels = getattr(self._model, self._labels_attr, None)
            if callable(labels):
                try:
                    labels = labels()
                except Exception:
                    labels = None
            obj = _RateMatrixScheme(obj, labels)
        return obj

    #: Zoom limits. Below the first the labels are unreadable; above the second
    #: a single node fills the canvas and there is nothing left to orient by.
    ZOOM_RANGE = (0.25, 6.0)

    def _transform(self) -> QtGui.QTransform:
        """Return the scene -> canvas transform."""
        t = QtGui.QTransform()
        t.translate(self._zoom_origin.x(), self._zoom_origin.y())
        t.scale(self._zoom, self._zoom)
        return t

    def _scene_pos(self, point) -> QtCore.QPointF:
        """Map a canvas position back to scene coordinates.

        Every hit test -- nodes, rate badges, the arc handles -- works in scene
        coordinates, so the inverse has to be applied on the way in or clicking
        a zoomed node would miss it by exactly the zoom factor.
        """
        inverse, ok = self._transform().inverted()
        p = QtCore.QPointF(point)
        return inverse.map(p) if ok else p

    def _on_canvas_wheel(self, event: QtGui.QWheelEvent):
        """Zoom about the pointer.

        Anchoring on the pointer rather than the widget centre is what makes
        zoom usable for inspecting one transition in a busy scheme: the thing
        under the cursor stays under the cursor.
        """
        delta = event.angleDelta().y()
        if not delta:
            return
        low, high = self.ZOOM_RANGE
        factor = 1.0015 ** float(delta)
        new_zoom = min(high, max(low, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-9:
            return
        try:
            anchor = QtCore.QPointF(event.position())
        except AttributeError:      # Qt5 spelling
            anchor = QtCore.QPointF(event.pos())
        scene = self._scene_pos(anchor)
        # Keep `scene` under `anchor`: origin' = anchor - scene * zoom'
        self._zoom = new_zoom
        self._zoom_origin = QtCore.QPointF(
            anchor.x() - scene.x() * new_zoom,
            anchor.y() - scene.y() * new_zoom,
        )
        self._spin.hide()
        self._editing_pair = None
        self.canvas.update()
        event.accept()

    def reset_view(self):
        """Return to 1:1, centred as laid out."""
        self._zoom = 1.0
        self._zoom_origin = QtCore.QPointF(0.0, 0.0)
        self.canvas.update()

    def _excitation(self):
        """Return the pumped transition ``(i, j)``, or ``None`` if there is none.

        The scheme itself wins over the view spec: a bare rate matrix knows it
        has no laser in it, whatever a spec inherited from a photophysics model
        might say.
        """
        scheme = self._get_saturation()
        edge = getattr(scheme, "excitation_edge", self._excitation_edge)
        return tuple(edge) if edge else None

    def _init_coords(self, n: int):
        w = max(360, self.canvas.width())
        h = max(240, self.canvas.height())
        if len(self._node_coords) == n and self._last_n_states == n and min(w, h) > 50:
            return

        self._last_n_states = n
        self._node_coords = {}

        if n == 3:
            # Jablonski HMM layout: S0 bottom-left, S1 top-center, T1 bottom-right
            self._node_coords[0] = QtCore.QPointF(w * 0.25, h * 0.72)
            self._node_coords[1] = QtCore.QPointF(w * 0.50, h * 0.25)
            self._node_coords[2] = QtCore.QPointF(w * 0.75, h * 0.72)
        elif n == 4:
            # Cis-Trans grid layout: S0_trans (bottom-left), S1_trans (top-left), P_cis (top-right), T1 (bottom-right)
            self._node_coords[0] = QtCore.QPointF(w * 0.25, h * 0.72)
            self._node_coords[1] = QtCore.QPointF(w * 0.25, h * 0.25)
            self._node_coords[2] = QtCore.QPointF(w * 0.75, h * 0.25)
            self._node_coords[3] = QtCore.QPointF(w * 0.75, h * 0.72)
        else:
            # Circular layout for N >= 5
            cx, cy = w / 2.0, h / 2.0
            r_layout = min(w, h) / 2.0 - 55.0
            for i in range(n):
                angle = (2.0 * math.pi * i / n) - (math.pi / 2.0)
                nx = cx + r_layout * math.cos(angle)
                ny = cy + r_layout * math.sin(angle)
                self._node_coords[i] = QtCore.QPointF(nx, ny)

    def _on_canvas_mouse_press(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            sat = self._get_saturation()
            if sat is not None and hasattr(sat, "n_states"):
                n = sat.n_states
                self._init_coords(n)
                r_node = 26.0
                pos = self._scene_pos(event.pos())
                for i in range(n):
                    pt = self._node_coords.get(i, QtCore.QPointF(0, 0))
                    if math.hypot(pos.x() - pt.x(), pos.y() - pt.y()) <= r_node:
                        self._dragged_node = i
                        self._drag_offset = QtCore.QPointF(pos.x() - pt.x(), pos.y() - pt.y())
                        self.canvas.setCursor(QtCore.Qt.ClosedHandCursor)
                        return

                # Check if an active transition arrow arc / rate badge was clicked to drag arrow curve
                dark_m = np.asarray(sat.dark.rate_matrix()).ravel()
                for (i, j), mid_pt in self._get_active_midpoints(n, dark_m).items():
                    if math.hypot(pos.x() - mid_pt.x(), pos.y() - mid_pt.y()) <= 28.0:
                        self._dragged_arrow = (i, j)
                        self.canvas.setCursor(QtCore.Qt.PointingHandCursor)
                        return

                # If canvas background clicked, start panning the ENTIRE scheme
                self._dragging_scheme = True
                self._drag_start_pos = pos
                self.canvas.setCursor(QtCore.Qt.SizeAllCursor)

    def _on_canvas_mouse_move(self, event: QtGui.QMouseEvent):
        if self._dragged_node is not None:
            pos = self._scene_pos(event.pos())
            nx = pos.x() - self._drag_offset.x()
            ny = pos.y() - self._drag_offset.y()
            self._node_coords[self._dragged_node] = QtCore.QPointF(nx, ny)
            self.canvas.update()
        elif self._dragged_arrow is not None:
            i, j = self._dragged_arrow
            p_i = self._node_coords.get(i, QtCore.QPointF(0, 0))
            p_j = self._node_coords.get(j, QtCore.QPointF(0, 0))
            dx = p_j.x() - p_i.x()
            dy = p_j.y() - p_i.y()
            dist = math.hypot(dx, dy)
            if dist > 1e-4:
                ux, uy = dx / dist, dy / dist
                px, py = -uy, ux
                pos = self._scene_pos(event.pos())
                mid_base_x = (p_i.x() + p_j.x()) / 2.0
                mid_base_y = (p_i.y() + p_j.y()) / 2.0
                new_h = (pos.x() - mid_base_x) * px + (pos.y() - mid_base_y) * py
                self._arrow_offsets[(i, j)] = float(new_h)
                self.canvas.update()
        elif getattr(self, "_dragging_scheme", False):
            pos = self._scene_pos(event.pos())
            dx = float(pos.x() - self._drag_start_pos.x())
            dy = float(pos.y() - self._drag_start_pos.y())
            self._drag_start_pos = pos
            for i in self._node_coords:
                self._node_coords[i] = QtCore.QPointF(self._node_coords[i].x() + dx, self._node_coords[i].y() + dy)
            self.canvas.update()

    def _on_canvas_mouse_release(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            self._dragged_node = None
            self._dragged_arrow = None
            self._dragging_scheme = False
            self.canvas.unsetCursor()

    def _on_canvas_mouse_double_click(self, event: QtGui.QMouseEvent):
        sat = self._get_saturation()
        if sat is None or not hasattr(sat, "dark"):
            return
        n = sat.n_states
        self._init_coords(n)
        dark_m = np.asarray(sat.dark.rate_matrix()).ravel()

        pos = self._scene_pos(event.pos())
        for (i, j), mid_pt in self._get_active_midpoints(n, dark_m).items():
            if abs(pos.x() - mid_pt.x()) <= 28 and abs(pos.y() - mid_pt.y()) <= 16:
                idx = j * n + i
                val = float(dark_m[idx]) if idx < len(dark_m) else 0.0
                self._editing_pair = (i, j)
                # A real child widget, so it is positioned in *canvas* pixels
                # even though the badge it covers was located in scene space.
                anchor = self._transform().map(mid_pt)
                self._spin.setGeometry(int(anchor.x() - 32), int(anchor.y() - 12), 64, 24)
                self._spin.blockSignals(True)
                self._spin.setValue(val)
                self._spin.blockSignals(False)
                self._spin.show()
                self._spin.setFocus()
                self._spin.selectAll()
                return

    def _on_edit_finished(self):
        if self._editing_pair is None:
            return
        i, j = self._editing_pair
        val = float(self._spin.value())
        self._spin.hide()
        self._editing_pair = None

        sat = self._get_saturation()
        if sat is None or not hasattr(sat, "dark"):
            return
        n = sat.n_states
        dark_m = list(np.asarray(sat.dark.rate_matrix()).ravel())
        idx = j * n + i
        if idx < len(dark_m):
            dark_m[idx] = val
            sat.dark.matrix = dark_m

        host_form = self._find_host_form()
        if host_form is not None:
            host_form.sync_fields()
            host_form.refresh_plots()
        self.canvas.update()

    def _find_host_form(self):
        curr = self.parentWidget()
        while curr is not None:
            if hasattr(curr, "sync_fields") and hasattr(curr, "refresh_plots"):
                return curr
            curr = curr.parentWidget()
        return None

    def _compute_edge_routing(self, p_i: QtCore.QPointF, p_j: QtCore.QPointF, is_two_way: bool, pair_key: tuple[int, int] = (0, 0)):
        r_node = 26.0
        dx = p_j.x() - p_i.x()
        dy = p_j.y() - p_i.y()
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return None, None, None, None, None

        ux, uy = dx / dist, dy / dist
        px, py = -uy, ux

        if pair_key in self._arrow_offsets:
            h = self._arrow_offsets[pair_key]
            offset_side = 7.0 if is_two_way else 0.0
        elif is_two_way:
            h = max(24.0, min(50.0, dist * 0.26))
            offset_side = 7.0
        else:
            h = max(10.0, min(22.0, dist * 0.12))
            offset_side = 0.0

        p0 = QtCore.QPointF(p_i.x() + ux * r_node + px * offset_side, p_i.y() + uy * r_node + py * offset_side)
        p3 = QtCore.QPointF(p_j.x() - ux * r_node + px * offset_side, p_j.y() - uy * r_node + py * offset_side)

        mid_x = (p0.x() + p3.x()) / 2.0 + px * h
        mid_y = (p0.y() + p3.y()) / 2.0 + py * h
        pmid = QtCore.QPointF(mid_x, mid_y)

        p1 = QtCore.QPointF(p0.x() + (pmid.x() - p0.x()) * 0.6, p0.y() + (pmid.y() - p0.y()) * 0.6)
        p2 = QtCore.QPointF(p3.x() + (pmid.x() - p3.x()) * 0.6, p3.y() + (pmid.y() - p3.y()) * 0.6)

        path = QtGui.QPainterPath()
        path.moveTo(p0)
        path.cubicTo(p1, p2, p3)
        return path, p0, p3, p2, pmid

    def _get_active_midpoints(self, n: int, dark_m: np.ndarray) -> dict[tuple[int, int], QtCore.QPointF]:
        midpoints = {}
        excitation = self._excitation()
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                idx_ij = j * n + i
                rate_ij = float(dark_m[idx_ij]) if idx_ij < len(dark_m) else 0.0
                is_excitation = excitation is not None and (i, j) == excitation

                if rate_ij > 0.0 or is_excitation:
                    idx_ji = i * n + j
                    rate_ji = float(dark_m[idx_ji]) if idx_ji < len(dark_m) else 0.0
                    is_two_way = rate_ji > 0.0 or (
                        excitation is not None and (j, i) == excitation
                    )

                    p_i = self._node_coords[i]
                    p_j = self._node_coords[j]
                    path, p0, p3, p2, pmid = self._compute_edge_routing(p_i, p_j, is_two_way, pair_key=(i, j))
                    if pmid is not None:
                        midpoints[(i, j)] = pmid
        return midpoints

    def _on_canvas_paint(self, canvas: SchemeCanvasWidget, event: QtGui.QPaintEvent):
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Fill background with dark plot color and draw grid lines
        rect = canvas.rect()
        painter.fillRect(rect, QtGui.QColor("#151515"))

        grid_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1, QtCore.Qt.DashLine)
        painter.setPen(grid_pen)
        grid_step = 35
        for x in range(grid_step, rect.width(), grid_step):
            painter.drawLine(x, 0, x, rect.height())
        for y in range(grid_step, rect.height(), grid_step):
            painter.drawLine(0, y, rect.width(), y)

        painter.setPen(QtGui.QPen(QtGui.QColor(50, 50, 50), 1))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        # The grid above is a fixed backdrop; everything below is the scheme
        # itself and moves with the zoom.
        painter.setTransform(self._transform(), True)

        sat = self._get_saturation()
        if sat is None or not hasattr(sat, "dark"):
            painter.end()
            return

        n = sat.n_states
        self._init_coords(n)
        dark_m = np.asarray(sat.dark.rate_matrix()).ravel()
        raw_labels = getattr(sat, "state_labels", None) or [f"S{i}" for i in range(n)]
        short_labels = [l.split(" ")[0] for l in raw_labels]
        r_node = 26.0
        excitation = self._excitation()

        # Directed edges with a rate, plus the pumped one when the scheme
        # declares it -- that transition carries no rate in the matrix, so it
        # would otherwise be missing from the diagram entirely.
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                idx_ij = j * n + i
                rate = float(dark_m[idx_ij]) if idx_ij < len(dark_m) else 0.0
                is_excitation = excitation is not None and (i, j) == excitation

                if rate <= 0.0 and not is_excitation:
                    continue

                idx_ji = i * n + j
                rate_ji = float(dark_m[idx_ji]) if idx_ji < len(dark_m) else 0.0
                is_two_way = rate_ji > 0.0 or (
                    excitation is not None and (j, i) == excitation
                )

                p_i = self._node_coords[i]
                p_j = self._node_coords[j]
                path, p0, p3, p2, pmid = self._compute_edge_routing(p_i, p_j, is_two_way, pair_key=(i, j))
                if path is None:
                    continue

                if is_excitation and rate <= 0.0:
                    pen_w = 2.5
                    arrow_color = QtGui.QColor("#00e5ff")
                    pen = QtGui.QPen(arrow_color, pen_w, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
                    badge_bg = QtGui.QColor(0, 140, 170, 230)
                    text_color = QtGui.QColor(255, 255, 255)
                    rate_str = "k_exc"
                else:
                    pen_w = max(1.8, 1.8 + 2.2 * math.log10(rate + 1.0))
                    # Cyan for transitions touching the pumped state, pink
                    # otherwise -- meaningful only when there *is* one. Without
                    # an excitation edge, singling out state 0 would claim a
                    # ground state the scheme never declared.
                    if excitation is None:
                        arrow_color = QtGui.QColor("#00e5ff")
                    elif j == excitation[0] or i == excitation[0]:
                        arrow_color = QtGui.QColor("#00e5ff")
                    else:
                        arrow_color = QtGui.QColor("#ff4081")
                    pen = QtGui.QPen(arrow_color, pen_w, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
                    badge_bg = QtGui.QColor(20, 20, 20, 225)
                    text_color = QtGui.QColor(255, 255, 255)
                    rate_str = f"{rate:.2f}"

                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawPath(path)

                ah_angle = math.atan2(p3.y() - p2.y(), p3.x() - p2.x())
                arrow_size = 10.0 + pen_w * 0.5
                ah_p1 = QtCore.QPointF(
                    p3.x() - arrow_size * math.cos(ah_angle - math.pi / 6),
                    p3.y() - arrow_size * math.sin(ah_angle - math.pi / 6)
                )
                ah_p2 = QtCore.QPointF(
                    p3.x() - arrow_size * math.cos(ah_angle + math.pi / 6),
                    p3.y() - arrow_size * math.sin(ah_angle + math.pi / 6)
                )
                arrow_head = QtGui.QPolygonF([p3, ah_p1, ah_p2])
                painter.setBrush(QtGui.QBrush(arrow_color))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawPolygon(arrow_head)

                fm = painter.fontMetrics()
                bw = max(40, fm.horizontalAdvance(rate_str) + 12)
                bh = 20

                painter.setBrush(QtGui.QBrush(badge_bg))
                painter.setPen(QtGui.QPen(arrow_color, 1.2))
                badge_rect = QtCore.QRectF(pmid.x() - bw / 2.0, pmid.y() - bh / 2.0, bw, bh)
                painter.drawRoundedRect(badge_rect, 6, 6)

                painter.setPen(QtGui.QPen(text_color))
                font = painter.font()
                font.setPointSize(9)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(badge_rect, QtCore.Qt.AlignCenter, rate_str)

        # Draw nodes (Photophysical State Badges)
        for i in range(n):
            pt = self._node_coords[i]
            node_rect = QtCore.QRectF(pt.x() - r_node, pt.y() - r_node, 2 * r_node, 2 * r_node)

            grad = QtGui.QRadialGradient(pt.x() - r_node * 0.3, pt.y() - r_node * 0.3, r_node * 1.5)
            light, dark = _NODE_COLOURS[i % len(_NODE_COLOURS)]
            grad.setColorAt(0, QtGui.QColor(light))
            grad.setColorAt(1, QtGui.QColor(dark))

            is_dragged = (self._dragged_node == i)
            border_color = QtGui.QColor("#ffeb3b") if is_dragged else QtGui.QColor(240, 240, 240)
            border_w = 3.0 if is_dragged else 2.0

            painter.setBrush(QtGui.QBrush(grad))
            painter.setPen(QtGui.QPen(border_color, border_w))
            painter.drawEllipse(node_rect)

            painter.setPen(QtGui.QPen(QtCore.Qt.white))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)
            lbl = short_labels[i] if i < len(short_labels) else f"S{i}"
            painter.drawText(node_rect, QtCore.Qt.AlignCenter, lbl)

        painter.end()


class StateSchemePlot(QtWidgets.QWidget):
    """Fit-window plot tab wrapper for interactive HMM State Scheme visualization."""

    name = "State Scheme"

    def __init__(self, fit=None, target: str = "saturation", unit_attr: str = "dark_unit",
                 labels_attr: str = "state_names", **options):
        super().__init__()
        self.fit = fit
        self.plot_controller = QtWidgets.QWidget()
        model = getattr(fit, "model", None) if fit is not None else None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scheme_widget = StateSchemeWidget(
            model, target=target, unit_attr=unit_attr,
            labels_attr=labels_attr, options=options,
        )
        layout.addWidget(self.scheme_widget)

    def update_plot(self, *args, **kwargs):
        """Update plot tab content on fit/model parameter change."""
        if hasattr(self, "scheme_widget"):
            self.scheme_widget.refresh()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        if hasattr(self, "scheme_widget"):
            self.scheme_widget.refresh()


from .registry import register_plot
register_plot("state_scheme", lambda: StateSchemePlot)
