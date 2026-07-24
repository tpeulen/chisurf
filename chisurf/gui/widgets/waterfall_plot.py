"""
Waterfall Plot Widget

A reusable waterfall plot widget for TTTR data visualization, built on the
:mod:`chisurf.gui.chiplot` plotting API (renderer-neutral; no direct pyqtgraph
use).
"""

from __future__ import annotations

import numpy as np
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QVBoxLayout, QWidget

from chisurf.gui import chiplot as cp


class WaterfallPlotWidget(QWidget):
    """
    A widget for displaying TTTR waterfall plots with position indicator.

    Features:
    - Waterfall image display
    - Horizontal position indicator line
    - Proper axis labeling for TTTR data
    - Signal emission for user interactions
    """

    # Signals
    plot_clicked = Signal(float, float)  # x, y coordinates when plot is clicked

    def __init__(self, parent=None):
        super().__init__(parent)

        # Plot components
        self.plot = cp.Plot(self)
        self.waterfall_img: cp.handles.Image | None = None
        self.position_line: cp.handles.Marker | None = None

        # Data storage
        self.waterfall_data: np.ndarray | None = None
        self.n_macro_bins: int = 0
        self.n_micro_bins: int = 0

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Setup plot widget
        self.plot.set_title("Microtime Waterfall")
        self.plot.set_labels(left="Macrotime (s)", bottom="Microtime (bins)")

        # Create position indicator (horizontal line that moves vertically)
        self.position_line = self.plot.hline(0.0, movable=False, pen=cp.to_pen("y", width=2))
        self.position_line.visible = False

        layout.addWidget(self.plot)

    def _connect_signals(self):
        """Connect signals."""
        # chiplot emits data-coordinate (x, y) for left clicks.
        self.plot.clicked.connect(self.plot_clicked.emit)

    def set_waterfall_data(
        self,
        rgb_data: np.ndarray,
        macro_t_s: np.ndarray,
        micro_centers: np.ndarray,
        n_macro_bins: int,
        n_micro_bins: int,
    ):
        """
        Set the waterfall data and update the plot.

        Keeps RGB color mixing but uses alpha channel to represent intensity.

        Args:
            rgb_data: RGB image data (shape: n_micro, n_macro, 3)
            macro_t_s: Macrotime values for x-axis (seconds)
            micro_centers: Microtime bin centers for y-axis (bins)
            n_macro_bins: Number of macrotime bins
            n_micro_bins: Number of microtime bins
        """
        if rgb_data.ndim != 3 or rgb_data.shape[2] != 3:
            raise ValueError(
                f"rgb_data must have shape (n_micro, n_macro, 3), got {rgb_data.shape}"
            )

        self.waterfall_data = rgb_data
        self.n_macro_bins = n_macro_bins
        self.n_micro_bins = n_micro_bins

        # ---- Normalize RGB to float32 in [0, 1] for stable alpha computation ----
        if np.issubdtype(rgb_data.dtype, np.integer):
            rgb = rgb_data.astype(np.float32) / 255.0
        else:
            rgb = rgb_data.astype(np.float32, copy=False)
            # if it looks like [0..255] floats, normalize
            if np.nanmax(rgb) > 1.5:
                rgb = rgb / 255.0

        rgb = np.clip(rgb, 0.0, 1.0)

        # ---- Compute intensity proxy from RGB (luminance) ----
        # You can change weights if your channel coloring has meaning.
        intensity = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

        # ---- Map intensity -> alpha with log + robust scaling ----
        # This is the critical part that makes bursts pop.
        I = intensity

        # log1p-like compression in [0,1] domain:
        # (scale first so log has effect even for small values)
        # You can tune "log_gain" if needed.
        log_gain = 50.0
        I_log = np.log1p(log_gain * I) / np.log1p(log_gain)

        # robust quantile stretch
        finite = I_log[np.isfinite(I_log)]
        if finite.size:
            lo = float(np.quantile(finite, 0.01))
            hi = float(np.quantile(finite, 0.995))
            if hi <= lo:
                hi = lo + 1e-6
            alpha = (I_log - lo) / (hi - lo)
        else:
            alpha = I_log

        alpha = np.clip(alpha, 0.0, 1.0)

        # Optional: enforce a minimum alpha so low background is still faintly visible
        # Set to 0.0 to fully hide background.
        alpha_min = 0.02
        alpha = alpha_min + (1.0 - alpha_min) * alpha

        # Optional: gamma on alpha (gamma < 1 boosts faint signals; >1 suppresses)
        alpha_gamma = 0.7
        alpha = np.power(alpha, alpha_gamma)

        # ---- Compose RGBA (float 0..1) ----
        rgba = np.empty((rgb.shape[0], rgb.shape[1], 4), dtype=np.float32)
        rgba[..., :3] = rgb
        rgba[..., 3] = alpha

        # ---- Update image ----
        rgba_uint8 = (rgba * 255).astype(np.uint8)
        if self.waterfall_img is None:
            self.waterfall_img = self.plot.image(rgba_uint8)
            self.position_line.z = 1.0  # keep the indicator above the image
        else:
            self.waterfall_img.set_image(rgba_uint8)

        # ---- Set axis ranges (keep your convention) ----
        self.plot.set_xlim(float(macro_t_s[0]), float(macro_t_s[-1]))
        self.plot.set_ylim(float(micro_centers[0]), float(micro_centers[-1]))

    def set_position(self, position: float):
        """
        Set the position of the indicator line.

        Args:
            position: Position value (in plot coordinates)
        """
        if self.position_line is not None:
            self.position_line.set_value(position)

    def show_position_indicator(self, show: bool = True):
        """
        Show or hide the position indicator line.

        Args:
            show: True to show, False to hide
        """
        if self.position_line is not None:
            self.position_line.visible = show

    def reset_position(self):
        """Reset the position indicator to the start (bin 0)."""
        self.set_position(0)

    def get_bin_count(self) -> tuple[int, int]:
        """
        Get the number of bins in the waterfall.

        Returns:
            Tuple of (n_macro_bins, n_micro_bins)
        """
        return self.n_macro_bins, self.n_micro_bins

    def clear_plot(self):
        """Clear the waterfall plot."""
        if self.waterfall_img is not None:
            self.waterfall_img.remove()
            self.waterfall_img = None
        self.waterfall_data = None
        self.n_macro_bins = 0
        self.n_micro_bins = 0
        self.show_position_indicator(False)

    def set_title(self, title: str):
        """Set the plot title."""
        self.plot.set_title(title)

    def get_plot_widget(self) -> cp.Plot:
        """Get the underlying chiplot Plot for advanced customization."""
        return self.plot
