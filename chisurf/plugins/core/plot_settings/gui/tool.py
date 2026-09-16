"""Plot settings plugin — configure plot appearance, colors, and backend.

Uses ``CollapsibleBox`` sections (the same folding panels AutoForm uses)
for a clean, progressive-disclosure layout.  Each section groups related
controls: backend selection, colors, appearance, and an advanced
pyqtgraph section.  A live chiplot preview at the bottom shows the effect
of the current settings.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

import chisurf.core.settings as css
from chisurf.gui import dialogs
from chisurf.gui.chiplot import available_backends
from chisurf.gui.widgets.collapsible_box import CollapsibleBox

try:
    from chisurf.gui.misc_helpers import persist_plugin_state
except ImportError:
    def persist_plugin_state(name):  # type: ignore[misc]
        def decorator(cls):
            return cls
        return decorator


# ---------------------------------------------------------------------------
# ColorButton — a clickable swatch that opens QColorDialog
# ---------------------------------------------------------------------------

class ColorButton(QtWidgets.QPushButton):
    """A push button showing a color swatch; click opens ``QColorDialog``.

    Parameters
    ----------
    color : str
        Initial color (hex ``#RRGGBB`` or color name).
    parent : QWidget, optional
    """

    color_changed = QtCore.Signal(str)

    def __init__(self, color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(80)
        self.setFixedHeight(26)
        self._update_swatches()
        self.clicked.connect(self._pick)

    def _update_swatches(self):
        self.setStyleSheet(
            f"background-color: {self._color};"
            f"border: 2px solid #555;"
            f"border-radius: 4px;"
        )
        self.setToolTip(self._color)

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(self._color), self, "Select Color")
        if c.isValid():
            self._color = c.name()
            self._update_swatches()
            self.color_changed.emit(self._color)

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str) -> None:
        self._color = value
        self._update_swatches()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hbox(*widgets, spacing=6) -> QtWidgets.QHBoxLayout:
    lay = QtWidgets.QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for w in widgets:
        lay.addWidget(w)
    return lay


def _color_row(label: str, key: str, btn: ColorButton) -> QtWidgets.QWidget:
    """A row: [label | swatch | hex-edit], all on one line."""
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lab = QtWidgets.QLabel(label)
    lab.setMinimumWidth(140)
    hex_label = QtWidgets.QLabel(btn.color)
    hex_label.setStyleSheet("color: #888; font-family: monospace; font-size: 10px;")
    btn.color_changed.connect(lambda c, l=hex_label: l.setText(c))
    lay.addWidget(lab)
    lay.addWidget(btn)
    lay.addWidget(hex_label)
    lay.addStretch()
    return w


def _labelled_row(label: str, widget: QtWidgets.QWidget,
                  stretch: bool = True) -> QtWidgets.QWidget:
    """Return a row pairing a fixed-width label with a control."""
    row = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    lab = QtWidgets.QLabel(label)
    lab.setMinimumWidth(140)
    layout.addWidget(lab)
    layout.addWidget(widget, 0 if stretch else 1)
    if stretch:
        layout.addStretch()
    return row


def _spin_row(label: str, spin: QtWidgets.QAbstractSpinBox) -> QtWidgets.QWidget:
    """Return a labelled row for a spin box."""
    return _labelled_row(label, spin)


def _slider_row(label: str, slider: QtWidgets.QSlider) -> QtWidgets.QWidget:
    """Return a labelled row for a slider, with a live value readout."""
    readout = QtWidgets.QLabel(str(slider.value()))
    readout.setMinimumWidth(34)
    readout.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    slider.valueChanged.connect(lambda v: readout.setText(str(v)))
    holder = QtWidgets.QWidget()
    inner = QtWidgets.QHBoxLayout(holder)
    inner.setContentsMargins(0, 0, 0, 0)
    inner.setSpacing(6)
    inner.addWidget(slider, 1)
    inner.addWidget(readout)
    return _labelled_row(label, holder, stretch=False)


def _check_row(label: str, cb: QtWidgets.QCheckBox) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lab = QtWidgets.QLabel(label)
    lab.setMinimumWidth(140)
    lay.addWidget(lab)
    lay.addWidget(cb)
    lay.addStretch()
    return w


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

@persist_plugin_state("plot_settings")
class PlotSettingsWidget(QtWidgets.QWidget):
    """Settings panel for all plot-related configuration.

    Uses ``CollapsibleBox`` sections so the user expands only the area
    they want to change.  Changes apply live to the in-memory settings
    dict and preview; *Save* persists to ``settings_chisurf.yaml``.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot Settings")
        self._color_buttons: dict[str, ColorButton] = {}
        self._preview_plot = None
        self._loading = False
        self._build_ui()
        self._load_settings()

    # -- UI construction ------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_content = QtWidgets.QWidget()
        self._scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(4, 4, 4, 4)
        self._scroll_layout.setSpacing(6)

        self._build_backend_section()
        self._build_colors_section()
        self._build_appearance_section()
        self._build_pyqtgraph_section()
        self._build_preview_section()

        self._scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # --- Bottom buttons ---
        btn_bar = QtWidgets.QHBoxLayout()
        self.apply_btn = QtWidgets.QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_settings)
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.clicked.connect(self._save_settings)
        self.reset_btn = QtWidgets.QPushButton("Reset")
        self.reset_btn.clicked.connect(self._load_settings)
        btn_bar.addWidget(self.apply_btn)
        btn_bar.addWidget(self.save_btn)
        btn_bar.addStretch()
        btn_bar.addWidget(self.reset_btn)
        root.addLayout(btn_bar)

    def _build_backend_section(self):
        box = CollapsibleBox("Rendering Backend", expanded=True)

        row = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lab = QtWidgets.QLabel("Active backend")
        lab.setMinimumWidth(140)
        self.backend_combo = QtWidgets.QComboBox()
        for name in available_backends():
            self.backend_combo.addItem(name)
        self.backend_combo.currentTextChanged.connect(self._on_changed)
        lay.addWidget(lab)
        lay.addWidget(self.backend_combo, 1)
        box.add_widget(row)

        hint = QtWidgets.QLabel(
            "Changes apply on next application start or when a new plot is created.")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        hint.setWordWrap(True)
        box.add_widget(hint)
        self._scroll_layout.addWidget(box)

    def _build_colors_section(self):
        box = CollapsibleBox("Colors", expanded=True)
        color_keys = [
            ("data", "Data curve"),
            ("model", "Model curve"),
            ("irf", "Instrument response"),
            ("residuals", "Residuals"),
            ("auto_corr", "Autocorrelation"),
            ("region_selector", "Region selector"),
        ]
        for key, label in color_keys:
            btn = ColorButton("#ffffff")
            btn.color_changed.connect(self._on_changed)
            self._color_buttons[key] = btn
            box.add_widget(_color_row(label, key, btn))

        # Alpha slider
        self.alpha_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.alpha_slider.setRange(0, 255)
        self.alpha_slider.valueChanged.connect(self._on_changed)
        self._alpha_label = QtWidgets.QLabel("100")
        self._alpha_label.setFixedWidth(36)
        self._alpha_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.alpha_slider.valueChanged.connect(
            lambda v: self._alpha_label.setText(str(v)))
        alpha_row = QtWidgets.QWidget()
        al = QtWidgets.QHBoxLayout(alpha_row)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(8)
        lab = QtWidgets.QLabel("Region alpha")
        lab.setMinimumWidth(140)
        al.addWidget(lab)
        al.addWidget(self.alpha_slider, 1)
        al.addWidget(self._alpha_label)
        box.add_widget(alpha_row)

        # Transparencies
        self.active_transparency = QtWidgets.QDoubleSpinBox()
        self.active_transparency.setRange(0.0, 1.0)
        self.active_transparency.setSingleStep(0.05)
        self.active_transparency.valueChanged.connect(self._on_changed)
        self.inactive_transparency = QtWidgets.QDoubleSpinBox()
        self.inactive_transparency.setRange(0.0, 1.0)
        self.inactive_transparency.setSingleStep(0.05)
        self.inactive_transparency.valueChanged.connect(self._on_changed)
        at_row = QtWidgets.QWidget()
        atl = QtWidgets.QHBoxLayout(at_row)
        atl.setContentsMargins(0, 0, 0, 0)
        atl.setSpacing(8)
        atl.addWidget(QtWidgets.QLabel("Active transparency"))
        atl.addWidget(self.active_transparency)
        box.add_widget(at_row)
        it_row = QtWidgets.QWidget()
        itl = QtWidgets.QHBoxLayout(it_row)
        itl.setContentsMargins(0, 0, 0, 0)
        itl.setSpacing(8)
        itl.addWidget(QtWidgets.QLabel("Inactive transparency"))
        itl.addWidget(self.inactive_transparency)
        box.add_widget(it_row)

        self._scroll_layout.addWidget(box)

    def _build_appearance_section(self):
        box = CollapsibleBox("Appearance", expanded=False)

        self.line_width = QtWidgets.QDoubleSpinBox()
        self.line_width.setRange(0.5, 10.0)
        self.line_width.setSingleStep(0.5)
        self.line_width.valueChanged.connect(self._on_changed)
        lw_row = QtWidgets.QWidget()
        lwl = QtWidgets.QHBoxLayout(lw_row)
        lwl.setContentsMargins(0, 0, 0, 0)
        lwl.setSpacing(8)
        lab = QtWidgets.QLabel("Line width")
        lab.setMinimumWidth(140)
        lwl.addWidget(lab)
        lwl.addWidget(self.line_width)
        lwl.addStretch()
        box.add_widget(lw_row)

        # Axis chrome size. 0 means "follow the application font", which is the
        # default and what keeps a plot from looking pasted into the window.
        self.font_size = QtWidgets.QSpinBox()
        self.font_size.setRange(0, 24)
        self.font_size.setSpecialValueText("auto")
        self.font_size.setToolTip(
            "Base point size for ticks, axis labels and titles. "
            "'auto' follows the application font.")
        self.font_size.valueChanged.connect(self._on_changed)
        box.add_widget(_spin_row("Axis font size", self.font_size))

        self.enable_grid = QtWidgets.QCheckBox()
        self.enable_grid.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Enable grid", self.enable_grid))

        # Grid opacity, and which panels get one. Both were settings the plots
        # already read and nothing could reach: a grid at full opacity buries
        # an eighty-pixel residual strip, and there was no way to turn it down.
        self.grid_alpha = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.grid_alpha.setRange(0, 100)
        self.grid_alpha.setToolTip("Grid line opacity, per cent.")
        self.grid_alpha.valueChanged.connect(self._on_changed)
        box.add_widget(_slider_row("Grid opacity", self.grid_alpha))

        self.show_data_grid = QtWidgets.QCheckBox()
        self.show_data_grid.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Grid on data panel", self.show_data_grid))
        self.show_residual_grid = QtWidgets.QCheckBox()
        self.show_residual_grid.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Grid on residuals", self.show_residual_grid))
        self.show_acorr_grid = QtWidgets.QCheckBox()
        self.show_acorr_grid.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Grid on autocorrelation", self.show_acorr_grid))

        self.enable_region_selector = QtWidgets.QCheckBox()
        self.enable_region_selector.setToolTip(
            "Draw the draggable fit-range band on the data panel.")
        self.enable_region_selector.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Fit-range selector", self.enable_region_selector))

        self.show_legend = QtWidgets.QCheckBox()
        self.show_legend.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Show legend by default", self.show_legend))
        self.hide_title = QtWidgets.QCheckBox()
        self.hide_title.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Hide titles", self.hide_title))
        self.label_axis = QtWidgets.QCheckBox()
        self.label_axis.setToolTip("Show the axis names (counts, t / ns, ...).")
        self.label_axis.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Label axes", self.label_axis))

        self._scroll_layout.addWidget(box)

    def _build_pyqtgraph_section(self):
        box = CollapsibleBox("Advanced: pyqtgraph Configuration", expanded=False)

        self.pg_antialias = QtWidgets.QCheckBox()
        self.pg_antialias.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Antialiasing", self.pg_antialias))

        self.pg_left_button_pan = QtWidgets.QCheckBox()
        self.pg_left_button_pan.toggled.connect(self._on_changed)
        box.add_widget(_check_row("Left button pans", self.pg_left_button_pan))

        self.pg_background = QtWidgets.QComboBox()
        self.pg_background.addItems(["k", "w", "default"])
        self.pg_background.currentTextChanged.connect(self._on_changed)
        bg_row = QtWidgets.QWidget()
        bl = QtWidgets.QHBoxLayout(bg_row)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        lab = QtWidgets.QLabel("Background")
        lab.setMinimumWidth(140)
        bl.addWidget(lab)
        bl.addWidget(self.pg_background)
        bl.addStretch()
        box.add_widget(bg_row)

        self.pg_foreground = QtWidgets.QComboBox()
        # "d" (light grey) first, deliberately. A combo whose first entry is
        # "k" reads back black whenever nothing loaded a value into it, and
        # black chrome on the black default background makes every axis, tick
        # and label invisible — the panel still reserves their space, so it
        # looks like the plot has no axes rather than like a colour setting.
        # Saved once, it stays: user settings are copied to ~/.chisurf and
        # never refreshed.
        self.pg_foreground.addItems(["d", "w", "l", "k"])
        self.pg_foreground.setToolTip(
            "Axis, tick and label colour. Keep it contrasting with the "
            "background: matching the two hides every axis.")
        self.pg_foreground.currentTextChanged.connect(self._on_changed)
        fg_row = QtWidgets.QWidget()
        fl = QtWidgets.QHBoxLayout(fg_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(8)
        lab2 = QtWidgets.QLabel("Foreground")
        lab2.setMinimumWidth(140)
        fl.addWidget(lab2)
        fl.addWidget(self.pg_foreground)
        fl.addStretch()
        box.add_widget(fg_row)

        self._scroll_layout.addWidget(box)

    def _build_preview_section(self):
        box = CollapsibleBox("Preview", expanded=True)
        container = QtWidgets.QWidget()
        cl = QtWidgets.QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        box.add_widget(container, stretch=1)
        box.setMinimumHeight(250)
        self._preview_container = container
        self._scroll_layout.addWidget(box, 1)

    # -- Load / save ----------------------------------------------------

    def _plot_settings(self) -> dict:
        return css.cs_settings.get("gui", {}).get("plot", {})

    def _load_settings(self):
        """Populate every control from the settings, without writing back.

        Each ``setChecked``/``setValue`` emits, and the handler applies the
        *whole* dialog to the settings dict — which is the same dict being read
        here, not a copy. So loading raced with applying: the first control to
        emit wrote every not-yet-loaded control's default over the real value,
        and the panel came up with everything unchecked and the sliders at
        zero. The flag makes loading one-directional.
        """
        self._loading = True
        try:
            self._load_settings_into_controls()
        finally:
            self._loading = False
        self._update_preview()

    def _load_settings_into_controls(self):
        """Set every control from the settings dict (see :meth:`_load_settings`)."""
        ps = self._plot_settings()
        colors = ps.get("colors", {})
        self.backend_combo.setCurrentText(ps.get("backend", "pyqtgraph"))
        for key, btn in self._color_buttons.items():
            btn.color = colors.get(key, "#ffffff")
        self.alpha_slider.setValue(int(colors.get("region_selector_alpha", 100)))
        self.active_transparency.setValue(float(colors.get("active_transparency", 1.0)))
        self.inactive_transparency.setValue(float(colors.get("inactive_transparency", 0.2)))
        self.line_width.setValue(float(ps.get("line_width", 2.0)))
        self.font_size.setValue(int(ps.get("font_size", 0) or 0))
        self.enable_grid.setChecked(bool(ps.get("enable_grid", True)))
        self.grid_alpha.setValue(int(round(float(ps.get("grid_alpha", 0.35)) * 100)))
        self.show_data_grid.setChecked(bool(ps.get("show_data_grid", True)))
        self.show_residual_grid.setChecked(bool(ps.get("show_residual_grid", True)))
        self.show_acorr_grid.setChecked(bool(ps.get("show_acorr_grid", True)))
        self.enable_region_selector.setChecked(
            bool(ps.get("enable_region_selector", True)))
        self.show_legend.setChecked(bool(ps.get("show_legend", False)))
        self.hide_title.setChecked(bool(ps.get("hideTitle", True)))
        self.label_axis.setChecked(bool(ps.get("label_axis", False)))
        pg = ps.get("pyqtgraph_config", {})
        self.pg_antialias.setChecked(bool(pg.get("antialias", False)))
        self.pg_left_button_pan.setChecked(bool(pg.get("leftButtonPan", True)))
        self.pg_background.setCurrentText(pg.get("background", "k"))
        self.pg_foreground.setCurrentText(pg.get("foreground", "d"))

    def _collect_settings(self) -> dict[str, Any]:
        return {
            "backend": self.backend_combo.currentText(),
            "colors": {
                "data": self._color_buttons["data"].color,
                "model": self._color_buttons["model"].color,
                "irf": self._color_buttons["irf"].color,
                "residuals": self._color_buttons["residuals"].color,
                "auto_corr": self._color_buttons["auto_corr"].color,
                "region_selector": self._color_buttons["region_selector"].color,
                "region_selector_alpha": self.alpha_slider.value(),
                "active_transparency": self.active_transparency.value(),
                "inactive_transparency": self.inactive_transparency.value(),
            },
            "line_width": self.line_width.value(),
            "font_size": self.font_size.value(),
            "enable_grid": self.enable_grid.isChecked(),
            "grid_alpha": self.grid_alpha.value() / 100.0,
            "show_data_grid": self.show_data_grid.isChecked(),
            "show_residual_grid": self.show_residual_grid.isChecked(),
            "show_acorr_grid": self.show_acorr_grid.isChecked(),
            "enable_region_selector": self.enable_region_selector.isChecked(),
            "show_legend": self.show_legend.isChecked(),
            "hideTitle": self.hide_title.isChecked(),
            "label_axis": self.label_axis.isChecked(),
            "pyqtgraph_config": {
                "antialias": self.pg_antialias.isChecked(),
                "background": self.pg_background.currentText(),
                "foreground": self.pg_foreground.currentText(),
                "leftButtonPan": self.pg_left_button_pan.isChecked(),
            },
        }

    def _apply_settings(self):
        settings = self._collect_settings()
        gui = css.cs_settings.setdefault("gui", {})
        existing = gui.get("plot", {})
        existing_colors = existing.get("colors", {})
        settings["colors"].update({
            k: v for k, v in existing_colors.items()
            if k not in settings["colors"]
        })
        existing.update(settings)
        gui["plot"] = existing
        self._update_preview()

    def _save_settings(self):
        self._apply_settings()
        import yaml
        from chisurf.core.settings.path_utils import get_path
        settings_file = get_path("settings") / "settings_chisurf.yaml"
        try:
            with open(settings_file, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                data = {}
            gui = data.setdefault("gui", {})
            gui["plot"] = css.cs_settings.get("gui", {}).get("plot", {})
            with open(settings_file, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
        except Exception as exc:
            dialogs.warning(self, "Save failed", str(exc))

    def _on_changed(self):
        """Apply the dialog to the settings, unless the dialog is being loaded."""
        if getattr(self, "_loading", False):
            return
        self._apply_settings()

    # -- Preview --------------------------------------------------------

    def _update_preview(self):
        """Render a sample decay plot as a live preview."""
        # Remove old preview
        if self._preview_plot is not None:
            try:
                self._preview_container.layout().removeWidget(self._preview_plot)
                self._preview_plot.close()
                self._preview_plot.deleteLater()
            except Exception:
                pass
            self._preview_plot = None

        try:
            from chisurf.gui import chiplot as cp
            from chisurf.gui.chiplot.canvas import Plot
            ps = self._collect_settings()
            colors = ps["colors"]
            bg = "k" if ps["pyqtgraph_config"]["background"] == "k" else "w"

            # Push the renderer options before building the preview panel, so
            # the preview shows the axis colours that were just chosen. Without
            # this it renders with whatever was configured at startup, which is
            # how a foreground matching the background — every axis invisible —
            # could be saved from a dialog that looked correct.
            cp.configure(**ps["pyqtgraph_config"])
            # The chrome font is read from the settings dict at draw time, so
            # the preview needs the pending value in place to show it.
            css.cs_settings.setdefault("gui", {}).setdefault(
                "plot", {})["font_size"] = ps["font_size"]

            plot = Plot(background=bg)
            self._preview_plot = plot

            # A constant background, because the preview is drawn on a log
            # axis: a bare Gaussian IRF reaches 1e-70 by the end of the window,
            # the axis is then asked to span seventy decades, and every curve
            # collapses onto the top edge — which tells the user nothing about
            # the colours and widths they came here to choose.
            t = np.linspace(0, 10, 256)
            background = 2.0
            data = 1000 * np.exp(-t / 3.0) + 200 * np.exp(-t / 8.0) + background
            model = 980 * np.exp(-t / 2.9) + 210 * np.exp(-t / 7.8) + background
            irf = 500 * np.exp(-((t - 1.0) ** 2) / 0.05) + background

            plot.line(t, data, pen=colors["data"], width=ps["line_width"], name="data")
            plot.line(t, model, pen=colors["model"], width=ps["line_width"],
                      style="dash", name="model")
            plot.line(t, irf, pen=colors["irf"], width=1.5, name="IRF")

            if ps["enable_grid"] and ps["show_data_grid"]:
                plot.grid(x=True, y=True, alpha=ps["grid_alpha"])
            if ps["label_axis"]:
                plot.set_labels(left="counts", bottom="t / ns")
            plot.set_log(y=True)
            if ps["show_legend"]:
                plot.legend()
            plot.set_xlim(0, 10)
            plot.autoscale()

            self._preview_container.layout().addWidget(plot)
        except Exception:
            pass
