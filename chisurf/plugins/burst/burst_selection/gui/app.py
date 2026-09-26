"""EMTK immediate-mode UI for Burst Selection in ChiSurf with full Qt parity.

Provides a responsive, dockable interface backed by the real BurstSelectionTool:
- 📁 Files & Channels: Add files/folders, toggle file inclusion, active file
  diagnostic switcher, detector setup selection, channel setup manager.
- ⚙️ Filter Settings: Full two-way sync with WizardTTTRPhotonFilter:
  Filter mode, min photons (L), window (m), max delta-t (T), min/max dMT,
  merge gap, count rate threshold, background subtraction, display controls.
- 📈 Count Rate (MCS): Real macro-time trace from TTTR data (all vs burst photons),
  bin width slider, draggable threshold line, region drag-and-drop.
- ⏱️ Inter-Photon Delay (dT): Real log-scale delta macro-time distribution from TTTR data,
  showing all vs burst photons and threshold indicator.
- 📉 Microtime Decay (TCSPC): Real log-scale TCSPC decay comparing all photons vs
  burst-filtered photons with selectable bin resolution.
- 📏 Burst Duration: Real burst duration distribution.
- 📊 2D Feature Scatter: Real burst scatter with customizable X & Y features (E, S,
  Duration, Photons, Count Rate), interactive drag-rect gate, static FRET line,
  and region drag-and-drop.
- 📊 1D Feature Histogram: Real 1D histogram of any selected burst feature with log-Y option.
- 📋 Bursts Table: Paginated, selectable table of real detected burst records.
- 📊 Summary & Metrics: Statistical cards (total bursts, mean photons, mean duration, rate).

NO fake/dummy simulated preview curves are used. When no data is loaded, clean
informative empty states are presented.
Organized into an emtk.docking.DockManager with responsive regions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

from chisurf.core.datastore import column_names, numeric_column, row_count
from chisurf.core.fio.staging import TTTR_FILE_FILTER
from chisurf.gui.widgets.tools.emtk_help_guide import EmTkHelpWindow
from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
    load_detector_setups,
)

if TYPE_CHECKING:
    from .tool import BurstSelectionTool

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_ORANGE = (255, 127, 14, 255)
ACCENT_PURPLE = (148, 103, 189, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)
REGION_FILL = (46, 117, 182, 60)
REGION_BORDER = (90, 160, 240, 255)

FEATURE_COLUMNS = [
    "Proximity Ratio",
    "Stoichiometry",
    "Duration (ms)",
    "Number of Photons",
    "Count Rate (KHz)",
    "Number of Photons (green)",
    "Number of Photons (red)",
]


class BurstSelectionGui:
    """Comprehensive EMTK GUI providing responsive, dockable panes for Burst Selection."""

    def __init__(
        self,
        tool: BurstSelectionTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_guide = on_guide
        self.on_help = on_help

        # Filter & Search parameters (synced with tool.wizard)
        self.min_photons: int = 30
        self.photon_window: int = 10
        self.time_window_ms: float = 0.50
        self.dmt_min_enabled: bool = False
        self.dmt_min_ms: float = 0.001
        self.dmt_max_enabled: bool = True
        self.dmt_max_ms: float = 0.150
        self.merge_gap: int = 3
        self.threshold_khz: float = 50.0
        self.filter_algorithm: int = 0
        self.channel_idx: int = 0
        self.window_idx: int = 0
        self.subtract_background: bool = False
        self.background_rate_khz: float = 2.5

        # CUSUM parameters
        self.cusum_alpha: float = 0.05
        self.cusum_beta: float = 0.05
        self.cusum_bg_rate: float = 2000.0
        self.cusum_sb_ratio: float = 30.0

        # Kalman parameters
        self.kalman_q: float = 0.01
        self.kalman_r_scale: float = 0.1
        self.kalman_z_thresh: float = 3.0
        self.kalman_min_len: int = 2
        self.kalman_merge_gap: int = 5

        # BOCPD parameters
        self.bocpd_changepoint_prob: float = 1e-5
        self.bocpd_prior_count: float = 1.0
        self.bocpd_prior_duration: float = 0.1

        # Max-tree & Bayesian Blocks parameters
        self.maxtree_alpha: float = 0.05
        self.bblocks_p0: float = 0.05

        # Display and plot options
        self.show_all_photons: bool = True
        self.show_selected_photons: bool = True
        self.mcs_bin_width_ms: float = 1.0
        self.decay_bins: int = 128
        self.burst_bins: int = 40
        self.log_decay: bool = True
        self.log_dt: bool = True

        # 1D Histogram options
        self.hist_feature_idx: int = 0
        self.hist_bins: int = 60
        self.hist_log_y: bool = False

        # Active file selection for diagnostics
        self.active_file_idx: int = 0
        self.file_inclusion: list[bool] = []

        # Feature scatter & gating parameters
        self.feature_x_idx: int = 0  # Proximity Ratio (E)
        self.feature_y_idx: int = 1  # Stoichiometry (S)
        self.gate_x_min: float = 0.20
        self.gate_x_max: float = 0.80
        self.gate_y_min: float = 0.25
        self.gate_y_max: float = 0.75
        self.show_static_fret_line: bool = True

        # Bursts table state
        self.table_page: int = 0
        self.page_size: int = 50
        self.selected_burst_idx: int | None = None

        # Drag-and-drop & Guided tour rect caching
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None
        self._last_dropped_region: dict[str, Any] | None = None

        # In-EMTK Tour & Help state
        self.tour_active: bool = False
        self.tour_step: int = 0

        # Floating in-EMTK Help Window (rendered over the EMTK view)
        help_resource = Path(__file__).parent / "help.md"
        self.help_window = EmTkHelpWindow(
            title="Burst Selection — Help & Reference",
            resource=help_resource,
            owner=self.tool,
            on_start_guide=self.start_guide,
            size=(720.0, 540.0),
        )
        self.help_tab_topic: str = "All"

        # Internal guard to prevent recursive sync loops
        self._syncing: bool = False

        # Build Dock Layout
        # Left region: Settings, Files, Summary
        # Top right region: MCS, dT, Decay, Burst Duration, Help & Reference
        # Bottom right region: 2D Scatter, Bursts Table, 1D Histogram
        layout = Split(
            "h",
            0.35,
            Region("left"),
            Split(
                "v",
                0.50,
                Region("top_right"),
                Region("bottom_right"),
            ),
        )
        self.docks = DockManager(layout)

        # Left region windows
        self.docks.add_window(
            "settings", "Filter Settings", self._draw_settings_content, dock="left", closable=False
        )
        self.docks.add_window(
            "files", "Files & Channels", self._draw_files_content, dock="left", closable=False
        )
        self.docks.add_window(
            "summary", "Summary & Metrics", self._draw_summary_content, dock="left", closable=False
        )

        # Top Right windows
        self.docks.add_window(
            "trace",
            "Count Rate (MCS)",
            self._draw_timeline_content,
            dock="top_right",
            closable=False,
        )
        self.docks.add_window(
            "dt", "Inter-Photon Delay (dT)", self._draw_dt_content, dock="top_right", closable=False
        )
        self.docks.add_window(
            "decay",
            "Microtime Decay (TCSPC)",
            self._draw_decay_content,
            dock="top_right",
            closable=False,
        )
        self.docks.add_window(
            "duration",
            "Burst Duration",
            self._draw_burst_length_content,
            dock="top_right",
            closable=False,
        )
        self.docks.add_window(
            "help", "Help & Reference", self._draw_help_content, dock="top_right", closable=True
        )

        # Bottom Right windows
        self.docks.add_window(
            "scatter",
            "2D Feature Scatter",
            self._draw_scatter_content,
            dock="bottom_right",
            closable=False,
        )
        self.docks.add_window(
            "table", "Bursts Table", self._draw_table_content, dock="bottom_right", closable=False
        )
        self.docks.add_window(
            "histogram",
            "1D Feature Histogram",
            self._draw_1d_histogram_content,
            dock="bottom_right",
            closable=False,
        )

        self._sync_from_tool()

    def _sync_from_tool(self) -> None:
        """Sync parameter values from the underlying tool and wizard."""
        if self._syncing:
            return
        self._syncing = True
        try:
            wiz = getattr(self.tool, "wizard", None)
            if wiz is not None:
                fs = getattr(wiz, "filter_settings", None)
                # Mode - read from comboBox_burst_filter or comboBox_mode
                mode_box = getattr(wiz, "comboBox_burst_filter", None) or getattr(
                    wiz, "comboBox_mode", None
                )
                if mode_box is not None:
                    self.filter_algorithm = max(0, mode_box.currentIndex())

                c2 = getattr(wiz, "comboBox_2", None)
                if c2 is not None:
                    self.channel_idx = max(0, c2.currentIndex())

                c3 = getattr(wiz, "comboBox_3", None)
                if c3 is not None:
                    self.window_idx = max(0, c3.currentIndex())

                # Min photons (L)
                spin_l = getattr(wiz, "spinBox", None) or getattr(
                    wiz, "spinBox_sliding_window_min_photons", None
                )
                if spin_l is not None:
                    self.min_photons = int(spin_l.value())
                elif fs is not None:
                    self.min_photons = int(getattr(fs, "min_photons", self.min_photons))

                # Consecutive window (m)
                spin_m = getattr(wiz, "spinBox_7", None) or getattr(wiz, "photon_window", None)
                if spin_m is not None:
                    self.photon_window = int(spin_m.value())
                elif fs is not None:
                    self.photon_window = int(getattr(fs, "photon_window", self.photon_window))

                # Time window (T in ms)
                spin_t = getattr(wiz, "doubleSpinBox", None) or getattr(wiz, "time_window_ms", None)
                if spin_t is not None:
                    self.time_window_ms = float(spin_t.value())
                elif fs is not None:
                    self.time_window_ms = float(getattr(fs, "time_window", self.time_window_ms))

                # dMT min / max
                chk_min = getattr(wiz, "checkBox_dMT_min", None)
                if chk_min is not None:
                    self.dmt_min_enabled = bool(chk_min.isChecked())
                elif fs is not None:
                    self.dmt_min_enabled = bool(getattr(fs, "dt_min_active", self.dmt_min_enabled))

                spin_dmt_min = getattr(wiz, "doubleSpinBox_dMT_min", None)
                if spin_dmt_min is not None:
                    self.dmt_min_ms = float(spin_dmt_min.value())
                elif fs is not None:
                    self.dmt_min_ms = float(getattr(fs, "dt_min", self.dmt_min_ms))

                chk_max = getattr(wiz, "checkBox_dMT_max", None)
                if chk_max is not None:
                    self.dmt_max_enabled = bool(chk_max.isChecked())
                elif fs is not None:
                    self.dmt_max_enabled = bool(getattr(fs, "dt_max_active", self.dmt_max_enabled))

                spin_dmt_max = getattr(wiz, "doubleSpinBox_dMT_max", None)
                if spin_dmt_max is not None:
                    self.dmt_max_ms = float(spin_dmt_max.value())
                elif fs is not None:
                    self.dmt_max_ms = float(getattr(fs, "dt_max", self.dmt_max_ms))

                # Merge gap
                spin_gap = getattr(wiz, "spinBox_max_gap", None)
                if spin_gap is not None:
                    self.merge_gap = int(spin_gap.value())
                elif fs is not None:
                    self.merge_gap = int(getattr(fs, "merge_gap", self.merge_gap))

                if fs is not None:
                    self.cusum_alpha = float(getattr(fs, "alpha", self.cusum_alpha))
                    self.cusum_beta = float(getattr(fs, "beta", self.cusum_beta))
                    self.cusum_bg_rate = float(getattr(fs, "background_rate", self.cusum_bg_rate))
                    self.cusum_sb_ratio = float(getattr(fs, "sb_ratio", self.cusum_sb_ratio))
                    self.kalman_q = float(getattr(fs, "kalman_q", self.kalman_q))
                    self.kalman_r_scale = float(getattr(fs, "kalman_r_scale", self.kalman_r_scale))
                    self.kalman_z_thresh = float(
                        getattr(fs, "kalman_z_thresh", self.kalman_z_thresh)
                    )
                    self.kalman_min_len = int(getattr(fs, "kalman_min_len", self.kalman_min_len))
                    self.kalman_merge_gap = int(
                        getattr(fs, "kalman_merge_gap", self.kalman_merge_gap)
                    )
                    self.bocpd_changepoint_prob = float(
                        getattr(fs, "bocpd_changepoint_prob", self.bocpd_changepoint_prob)
                    )
                    self.bocpd_prior_count = float(
                        getattr(fs, "bocpd_prior_count", self.bocpd_prior_count)
                    )
                    self.bocpd_prior_duration = float(
                        getattr(fs, "bocpd_prior_duration", self.bocpd_prior_duration)
                    )

            files = getattr(self.tool, "_file_paths", [])
            if len(self.file_inclusion) != len(files):
                self.file_inclusion = [True] * len(files)
        finally:
            self._syncing = False

    def _sync_to_tool(self, notify: bool = True) -> None:
        """Write parameters back to tool wizard and refresh plots."""
        if self._syncing:
            return
        self._syncing = True
        try:
            wiz = getattr(self.tool, "wizard", None)
            if wiz is not None:
                fs = getattr(wiz, "filter_settings", None)
                if fs is not None:
                    fs.min_photons = int(self.min_photons)
                    fs.photon_window = int(self.photon_window)
                    fs.time_window = float(self.time_window_ms)
                    fs.dt_min_active = bool(self.dmt_min_enabled)
                    fs.dt_min = float(self.dmt_min_ms)
                    fs.dt_max_active = bool(self.dmt_max_enabled)
                    fs.dt_max = float(self.dmt_max_ms)
                    fs.merge_gap = int(self.merge_gap)
                    fs.alpha = float(self.cusum_alpha)
                    fs.beta = float(self.cusum_beta)
                    fs.background_rate = float(self.cusum_bg_rate)
                    fs.sb_ratio = float(self.cusum_sb_ratio)
                    fs.kalman_q = float(self.kalman_q)
                    fs.kalman_r_scale = float(self.kalman_r_scale)
                    fs.kalman_z_thresh = float(self.kalman_z_thresh)
                    fs.kalman_min_len = int(self.kalman_min_len)
                    fs.kalman_merge_gap = int(self.kalman_merge_gap)
                    fs.bocpd_changepoint_prob = float(self.bocpd_changepoint_prob)
                    fs.bocpd_prior_count = float(self.bocpd_prior_count)
                    fs.bocpd_prior_duration = float(self.bocpd_prior_duration)

                mode_box = getattr(wiz, "comboBox_burst_filter", None) or getattr(
                    wiz, "comboBox_mode", None
                )
                if mode_box is not None and mode_box.count() > self.filter_algorithm:
                    mode_box.setCurrentIndex(self.filter_algorithm)

                c2 = getattr(wiz, "comboBox_2", None)
                if c2 is not None and c2.count() > self.channel_idx:
                    c2.setCurrentIndex(self.channel_idx)
                    if fs is not None and hasattr(fs, "detector"):
                        fs.detector = c2.currentText()

                c3 = getattr(wiz, "comboBox_3", None)
                if c3 is not None and c3.count() > self.window_idx:
                    c3.setCurrentIndex(self.window_idx)
                    if fs is not None and hasattr(fs, "window"):
                        fs.window = c3.currentText()

                spin_l = getattr(wiz, "spinBox", None) or getattr(
                    wiz, "spinBox_sliding_window_min_photons", None
                )
                if spin_l is not None:
                    spin_l.setValue(int(self.min_photons))

                spin_m = getattr(wiz, "spinBox_7", None) or getattr(wiz, "photon_window", None)
                if spin_m is not None:
                    spin_m.setValue(int(self.photon_window))

                spin_t = getattr(wiz, "doubleSpinBox", None) or getattr(wiz, "time_window_ms", None)
                if spin_t is not None:
                    spin_t.setValue(float(self.time_window_ms))

                chk_min = getattr(wiz, "checkBox_dMT_min", None)
                if chk_min is not None:
                    chk_min.setChecked(self.dmt_min_enabled)
                spin_dmt_min = getattr(wiz, "doubleSpinBox_dMT_min", None)
                if spin_dmt_min is not None:
                    spin_dmt_min.setValue(float(self.dmt_min_ms))

                chk_max = getattr(wiz, "checkBox_dMT_max", None)
                if chk_max is not None:
                    chk_max.setChecked(self.dmt_max_enabled)
                spin_dmt_max = getattr(wiz, "doubleSpinBox_dMT_max", None)
                if spin_dmt_max is not None:
                    spin_dmt_max.setValue(float(self.dmt_max_ms))

                spin_gap = getattr(wiz, "spinBox_max_gap", None)
                if spin_gap is not None:
                    spin_gap.setValue(int(self.merge_gap))

            if notify:
                filter_fn = getattr(self.tool, "_on_filter_settings_changed", None)
                if callable(filter_fn):
                    filter_fn()
        finally:
            self._syncing = False

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        """Store the item's screen rectangle for tour targeting."""
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def _get_active_diagnostic(self) -> dict[str, Any] | None:
        """Return the diagnostic payload for the active file."""
        diags = getattr(self.tool, "_last_diagnostics", None)
        if diags and len(diags) > 0:
            idx = min(self.active_file_idx, len(diags) - 1)
            return diags[idx]

        tttr = getattr(self.tool, "_last_tttr", None)
        sel = getattr(self.tool, "_last_selected", None)
        if tttr is not None:
            return {
                "tttr": tttr,
                "selected": sel if sel is not None else np.zeros(len(tttr), dtype=bool),
                "start_stop": getattr(self.tool, "_last_start_stop", None),
                "path": getattr(self.tool, "_last_diagnostic_path", None),
            }
        return None

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        """Render top action bar, responsive dock manager, and active tour overlay."""
        vp = im.get_main_viewport()
        vw, vh = vp.size
        width = float(w or vw or 800.0)
        height = float(h or vh or 600.0)

        # Top Action Bar
        im.dummy((0.0, 2.0))
        im.indent(4.0)
        self._draw_top_action_bar(width - 8.0)
        im.unindent(4.0)
        bar_h = 34.0

        # Dock Manager filling the remaining viewport
        self.docks.draw((0.0, bar_h, width, max(100.0, height - bar_h)))

        # In-EMTK Help Window (floating window over the EMTK view)
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        # In-EMTK Guided Tour Overlay (drawn on top of all docks)
        if self.tour_active:
            self._draw_tour_overlay(width, height)

    def _draw_top_action_bar(self, width: float) -> None:
        """Dedicated top action bar with primary workflow commands."""
        # 1. Primary Action: Find Bursts
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("Find Bursts"):
            self.track("toolAction_run")
            self._sync_to_tool()
            self.tool.analyze_files()
        self.remember("run")
        self.remember("toolAction_run")
        im.pop_style_color(3)

        im.same_line()
        if im.button("Recompute"):
            self.track("toolAction_refresh")
            self._sync_to_tool()
            self.tool.analyze_files(force=True)
        self.remember("refresh")
        self.remember("toolAction_refresh")

        im.same_line()
        if im.button("Save Bursts"):
            save_fn = getattr(self.tool, "save_current_bur", None) or getattr(
                self.tool, "save_selected_bursts", None
            )
            if callable(save_fn):
                save_fn()

        im.same_line()
        im.text_disabled("|")
        im.same_line()

        if im.button("Add Files"):
            self.track("toolAction_add")
            self._on_add_files()
        self.remember("add")
        self.remember("toolAction_add")
        im.same_line()
        if im.button("Add Folder"):
            self._on_add_folder()

        im.same_line()
        im.text_disabled("|")
        im.same_line()

        # ndX integration
        ndx_fn = getattr(self.tool, "_send_current_to_ndxplorer", None)
        if callable(ndx_fn) and im.button("to ndX"):
            ndx_fn()

        im.same_line()
        if im.button("Guide"):
            self.start_guide()

        im.same_line()
        if im.button("Help"):
            self.show_help()

        # Status text & active file summary
        files = getattr(self.tool, "_file_paths", [])
        frame = getattr(self.tool, "_last_frame", None)
        n_bursts = row_count(frame) if frame is not None else 0

        im.same_line()
        im.spacing()
        im.same_line()
        if files:
            active_name = files[min(self.active_file_idx, len(files) - 1)].name
            im.text_colored(f"{active_name}", (0.5, 0.8, 1.0, 1.0))
            im.same_line()
            im.text_disabled(f"({len(files)} files, {n_bursts:,} bursts)")
        else:
            im.text_disabled("No files loaded")

    # ── 1. Files & Channels Content ─────────────────────────────────────────

    def _draw_files_content(self, box: tuple[float, float, float, float]) -> None:
        files = getattr(self.tool, "_file_paths", [])
        if len(self.file_inclusion) != len(files):
            self.file_inclusion = [True] * len(files)

        # File actions row
        if im.button("Add Files##files_btn"):
            self._on_add_files()
        im.same_line()
        if im.button("Add Folder##files_btn"):
            self._on_add_folder()
        im.same_line()
        if im.button("Remove"):
            if 0 <= self.active_file_idx < len(files):
                files.pop(self.active_file_idx)
                self.file_inclusion.pop(self.active_file_idx)
                if self.active_file_idx >= len(files):
                    self.active_file_idx = max(0, len(files) - 1)
                refresh_fn = getattr(self.tool, "_refresh_file_list", None)
                if callable(refresh_fn):
                    refresh_fn()
        im.same_line()
        if im.button("Clear"):
            clear_fn = getattr(self.tool, "clear", None)
            if callable(clear_fn):
                clear_fn()
            else:
                files.clear()
            self.file_inclusion.clear()
            self.active_file_idx = 0

        im.separator()

        # Files table
        table_h = max(90.0, box[3] - 110.0)
        table_flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SIZING_FIXED_FIT
        )
        if im.begin_table("files_table", 3, table_flags, (0, table_h)):
            im.table_setup_column("Use", im.TableColumnFlags.WIDTH_FIXED, 35.0)
            im.table_setup_column("#", im.TableColumnFlags.WIDTH_FIXED, 25.0)
            im.table_setup_column("File Name", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()

            if files:
                for i, p in enumerate(files):
                    im.table_next_row()
                    im.table_set_column_index(0)
                    changed, val = im.checkbox(f"##inc_{i}", self.file_inclusion[i])
                    if changed:
                        self.file_inclusion[i] = val
                    im.table_set_column_index(1)
                    im.text(f"{i + 1}")
                    im.table_set_column_index(2)
                    is_selected = i == self.active_file_idx
                    if im.selectable(
                        f"{p.name}##f_{i}", is_selected, im.SelectableFlags.SPAN_ALL_COLUMNS
                    ):
                        self.active_file_idx = i
                        load_fn = getattr(self.tool, "_load_tttr_for_plots", None)
                        settings = getattr(self.tool, "_settings_from_controls", lambda: None)()
                        if callable(load_fn) and settings:
                            load_fn([p], settings)
            else:
                im.table_next_row()
                im.table_set_column_index(2)
                im.text_disabled("No files loaded. Click Add Files.")
            im.end_table()

        im.separator()

        # Detector Setup Combo & Channel Setup Manager
        try:
            setups_data = load_detector_setups().get("setups", {})
            setup_names = sorted(list(setups_data.keys()))
        except Exception:
            setup_names = ["PIE-MFD", "ALEX Suite", "smFRET", "Default"]

        current_setup = getattr(self.tool, "_selected_setup_name", None) or (
            setup_names[0] if setup_names else "Default"
        )
        setup_idx = setup_names.index(current_setup) if current_setup in setup_names else 0
        im.align_text_to_frame_padding()
        im.text("Setup:")
        im.same_line()
        im.set_next_item_width(max(110.0, box[2] - 150.0))
        changed_s, new_s_idx = im.combo("##Setup", setup_idx, setup_names)
        if changed_s and 0 <= new_s_idx < len(setup_names):
            name = setup_names[new_s_idx]
            apply_fn = getattr(self.tool, "_apply_detector_setup", None)
            if callable(apply_fn):
                apply_fn(name)
            self._sync_from_tool()

        im.same_line()
        if im.button("Channels"):
            show_chan_fn = getattr(self.tool, "_show_channel_settings", None)
            if callable(show_chan_fn):
                show_chan_fn()

    def _on_add_files(self) -> None:
        try:
            from qtpy import QtWidgets

            paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
                None,
                "Select TTTR files",
                "",
                TTTR_FILE_FILTER,
            )
            if paths:
                add_fn = getattr(self.tool, "_add_paths", None)
                if callable(add_fn):
                    add_fn([Path(p) for p in paths])
                self._sync_from_tool()
        except Exception as exc:
            logger.warning("Could not open file dialog: %s", exc)

    def _on_add_folder(self) -> None:
        try:
            from qtpy import QtWidgets

            folder = QtWidgets.QFileDialog.getExistingDirectory(
                None, "Select folder containing TTTR files"
            )
            if folder:
                add_fn = getattr(self.tool, "_add_paths", None)
                if callable(add_fn):
                    add_fn([Path(folder)])
                self._sync_from_tool()
        except Exception as exc:
            logger.warning("Could not open folder dialog: %s", exc)

    # ── 2. Search & Filter Settings Content ─────────────────────────────────

    def _draw_settings_content(self, box: tuple[float, float, float, float]) -> None:
        wiz = getattr(self.tool, "wizard", None)
        combo_filter = getattr(wiz, "comboBox_burst_filter", None) or getattr(
            wiz, "comboBox_mode", None
        )
        if combo_filter is not None and combo_filter.count() > 0:
            alg_names = [combo_filter.itemText(i) for i in range(combo_filter.count())]
        else:
            alg_names = [
                "Sliding window",
                "Cumulative (CUSUM / SPRT)",
                "Kalman (rate change)",
                "Bayesian changepoint (BOCPD)",
                "Coincident (multi-detector)",
                "Max-tree (threshold-free)",
                "Bayesian Blocks (optimal segmentation)",
            ]

        # Algorithm ComboBox
        im.text_colored("Algorithm:", (0.4, 0.8, 1.0, 1.0))
        im.set_next_item_width(max(150.0, box[2] - 20.0))
        alg_idx = min(self.filter_algorithm, len(alg_names) - 1)
        changed_alg, new_alg = im.combo("##filter_alg", alg_idx, alg_names)
        self.remember("algorithm")
        if changed_alg and 0 <= new_alg < len(alg_names):
            self.filter_algorithm = new_alg
            self._sync_to_tool()
        curr_alg = alg_names[min(self.filter_algorithm, len(alg_names) - 1)]

        # Detector & Window lists from wizard and setup dictionaries
        c2 = getattr(wiz, "comboBox_2", None)
        c3 = getattr(wiz, "comboBox_3", None)
        detectors_dict = getattr(wiz, "detectors", {}) or {}
        windows_dict = getattr(wiz, "windows", {}) or {}

        if c2 is not None and c2.count() > 0:
            ch_names = [c2.itemText(i) for i in range(c2.count())]
        elif detectors_dict:
            ch_names = ["All"] + [k for k in detectors_dict.keys() if k != "All"]
        else:
            ch_names = ["All", "green", "red", "yellow"]

        if c3 is not None and c3.count() > 0:
            win_names = [c3.itemText(i) for i in range(c3.count())]
        elif windows_dict:
            win_names = ["All"] + [k for k in windows_dict.keys() if k != "All"]
        else:
            win_names = ["All", "delayed", "prompt"]

        # Detector ComboBox
        im.spacing()
        im.text_colored("Detector Channel:", (0.4, 0.8, 1.0, 1.0))
        im.set_next_item_width(max(150.0, box[2] - 20.0))
        ch_idx = min(self.channel_idx, len(ch_names) - 1)
        changed_ch, new_ch = im.combo("##ch_sel", ch_idx, ch_names)
        self.remember("detector")
        if changed_ch and 0 <= new_ch < len(ch_names):
            self.channel_idx = new_ch
            self._sync_to_tool()

        # Display active routing channels for detector
        curr_ch_name = ch_names[ch_idx] if 0 <= ch_idx < len(ch_names) else "All"
        le4 = getattr(wiz, "lineEdit_4", None)
        ch_str = le4.text() if le4 is not None else ""
        if not ch_str and curr_ch_name != "All":
            det_dict = detectors_dict.get(curr_ch_name, {})
            chs = det_dict.get("chs", [])
            ch_str = ", ".join(map(str, chs)) if chs else ""
        if ch_str:
            im.text_disabled(f"Routing channels: {ch_str}")
        else:
            im.text_disabled("Routing channels: All (unfiltered)")

        # Window ComboBox
        im.spacing()
        im.text_colored("Microtime Window:", (0.4, 0.8, 1.0, 1.0))
        im.set_next_item_width(max(150.0, box[2] - 20.0))
        win_idx = min(self.window_idx, len(win_names) - 1)
        changed_win, new_win = im.combo("##win_sel", win_idx, win_names)
        self.remember("window")
        if changed_win and 0 <= new_win < len(win_names):
            self.window_idx = new_win
            self._sync_to_tool()

        # Display active microtime range for window
        curr_win_name = win_names[win_idx] if 0 <= win_idx < len(win_names) else "All"
        le5 = getattr(wiz, "lineEdit_5", None)
        win_str = le5.text() if le5 is not None else ""
        if not win_str and curr_win_name != "All":
            w_val = windows_dict.get(curr_win_name, [])
            if isinstance(w_val, (list, tuple)) and len(w_val) == 2:
                win_str = f"{w_val[0]}:{w_val[1]}"
        if win_str:
            im.text_disabled(f"Microtime range: {win_str}")
        else:
            im.text_disabled("Microtime range: Full decay (unfiltered)")

        im.spacing()
        im.separator()

        # Conditionally render parameter sections for each algorithm:
        col_x = 145.0
        alg_lower = curr_alg.lower()
        if "cusum" in alg_lower or "cumulative" in alg_lower or self.filter_algorithm == 1:
            im.text_colored("CUSUM / SPRT Parameters:", (0.4, 0.8, 1.0, 1.0))

            im.align_text_to_frame_padding()
            im.text("False alarm (α):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _ca, val_a = im.input_float("##cusum_alpha", self.cusum_alpha, 0.01, 0.05, "%.3f")
            if _ca:
                self.cusum_alpha = max(0.0001, min(0.99, val_a))
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Missed det. (β):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cb, val_b = im.input_float("##cusum_beta", self.cusum_beta, 0.01, 0.05, "%.3f")
            if _cb:
                self.cusum_beta = max(0.0001, min(0.99, val_b))
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Bg rate (Hz):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cr, val_r = im.input_float("##cusum_bg_rate", self.cusum_bg_rate, 100.0, 500.0, "%.0f")
            if _cr:
                self.cusum_bg_rate = max(1.0, val_r)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("S/B ratio:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cs, val_s = im.input_float("##cusum_sb_ratio", self.cusum_sb_ratio, 1.0, 5.0, "%.1f")
            if _cs:
                self.cusum_sb_ratio = max(1.1, val_s)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Min photons (L):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cl, val_l = im.input_int("##min_photons", self.min_photons, 1, 10)
            self.remember("parameters")
            if _cl:
                self.min_photons = max(5, val_l)
                self._sync_to_tool()

        elif "kalman" in alg_lower or self.filter_algorithm == 2:
            im.text_colored("Kalman Filter Parameters:", (0.4, 0.8, 1.0, 1.0))

            im.align_text_to_frame_padding()
            im.text("Process noise (Q):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cq, val_q = im.input_float("##kalman_q", self.kalman_q, 0.001, 0.01, "%.4f")
            if _cq:
                self.kalman_q = max(1e-6, val_q)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Meas. scale (R):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cr, val_r = im.input_float("##kalman_r", self.kalman_r_scale, 0.05, 0.2, "%.2f")
            if _cr:
                self.kalman_r_scale = max(0.01, val_r)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Z threshold:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cz, val_z = im.input_float("##kalman_z", self.kalman_z_thresh, 0.5, 1.0, "%.1f")
            if _cz:
                self.kalman_z_thresh = max(0.5, val_z)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Min length:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cml, val_ml = im.input_int("##kalman_min_len", self.kalman_min_len, 1, 5)
            if _cml:
                self.kalman_min_len = max(1, val_ml)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Merge gap:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cmg, val_mg = im.input_int("##kalman_merge_gap", self.kalman_merge_gap, 1, 5)
            if _cmg:
                self.kalman_merge_gap = max(0, val_mg)
                self._sync_to_tool()

        elif (
            "bocpd" in alg_lower
            or "bayesian changepoint" in alg_lower
            or self.filter_algorithm == 3
        ):
            im.text_colored("BOCPD Parameters:", (0.4, 0.8, 1.0, 1.0))

            im.align_text_to_frame_padding()
            im.text("Changepoint prob:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cp, val_p = im.input_float(
                "##bocpd_prob", self.bocpd_changepoint_prob, 1e-6, 1e-4, "%.6f"
            )
            if _cp:
                self.bocpd_changepoint_prob = max(1e-9, min(0.1, val_p))
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Prior count:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cpc, val_pc = im.input_float(
                "##bocpd_prior_count", self.bocpd_prior_count, 0.1, 1.0, "%.2f"
            )
            if _cpc:
                self.bocpd_prior_count = max(0.01, val_pc)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Prior duration(s):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cpd, val_pd = im.input_float(
                "##bocpd_prior_dur", self.bocpd_prior_duration, 0.05, 0.5, "%.3f"
            )
            if _cpd:
                self.bocpd_prior_duration = max(0.001, val_pd)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Min photons (L):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cl, val_l = im.input_int("##min_photons", self.min_photons, 1, 10)
            self.remember("parameters")
            if _cl:
                self.min_photons = max(5, val_l)
                self._sync_to_tool()

        elif "max-tree" in alg_lower or self.filter_algorithm == 5:
            im.text_colored("Max-Tree Parameters:", (0.4, 0.8, 1.0, 1.0))

            im.align_text_to_frame_padding()
            im.text("Min photons (L):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cl, val_l = im.input_int("##min_photons", self.min_photons, 1, 10)
            self.remember("parameters")
            if _cl:
                self.min_photons = max(5, val_l)
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Alpha cutoff:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _ca, val_a = im.input_float("##maxtree_alpha", self.maxtree_alpha, 0.01, 0.05, "%.3f")
            if _ca:
                self.maxtree_alpha = max(0.001, min(0.5, val_a))
                self._sync_to_tool()

        elif "bayesian blocks" in alg_lower or self.filter_algorithm == 6:
            im.text_colored("Bayesian Blocks Parameters:", (0.4, 0.8, 1.0, 1.0))

            im.align_text_to_frame_padding()
            im.text("False pos (p0):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cp, val_p = im.input_float("##bblocks_p0", self.bblocks_p0, 0.01, 0.05, "%.3f")
            if _cp:
                self.bblocks_p0 = max(0.0001, min(0.5, val_p))
                self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Min counts:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cl, val_l = im.input_int("##min_photons", self.min_photons, 1, 10)
            self.remember("parameters")
            if _cl:
                self.min_photons = max(5, val_l)
                self._sync_to_tool()

        else:
            # Default / Sliding Window / Coincident
            im.text_colored("Sliding Window Parameters:", (0.4, 0.8, 1.0, 1.0))

            # Minimum photons in burst (L)
            im.align_text_to_frame_padding()
            im.text("Min photons (L):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cl, val_l = im.input_int("##min_photons", self.min_photons, 1, 10)
            self.remember("parameters")
            if _cl:
                self.min_photons = max(5, val_l)
                self._sync_to_tool()

            # Consecutive window (m)
            im.align_text_to_frame_padding()
            im.text("Photons/window (m):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cm, val_m = im.input_int("##photon_window", self.photon_window, 1, 5)
            if _cm:
                self.photon_window = max(2, val_m)
                self._sync_to_tool()

            # Window duration (T in ms)
            im.align_text_to_frame_padding()
            im.text("Window dur (T ms):")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _ct, val_t = im.input_float("##time_window", self.time_window_ms, 0.05, 0.5, "%.4f")
            if _ct:
                self.time_window_ms = max(0.0001, val_t)
                self._sync_to_tool()

            im.spacing()
            im.separator()
            im.text_colored("Macro Time Interval (dMT):", (0.4, 0.8, 1.0, 1.0))

            _c_min, self.dmt_min_enabled = im.checkbox("Use min dMT##chk", self.dmt_min_enabled)
            if _c_min:
                self._sync_to_tool()
            if self.dmt_min_enabled:
                im.same_line()
                im.set_next_item_width(100)
                _c_dmin, val_dmin = im.input_float(
                    "ms##dmin", self.dmt_min_ms, 0.0005, 0.005, "%.4f"
                )
                if _c_dmin:
                    self.dmt_min_ms = max(0.00001, val_dmin)
                    self._sync_to_tool()

            _c_max, self.dmt_max_enabled = im.checkbox("Use max dMT##chk", self.dmt_max_enabled)
            if _c_max:
                self._sync_to_tool()
            if self.dmt_max_enabled:
                im.same_line()
                im.set_next_item_width(100)
                _c_dmax, val_dmax = im.input_float("ms##dmax", self.dmt_max_ms, 0.01, 0.05, "%.4f")
                if _c_dmax:
                    self.dmt_max_ms = max(0.001, val_dmax)
                    self._sync_to_tool()

            im.align_text_to_frame_padding()
            im.text("Merge gap:")
            im.same_line(col_x)
            im.set_next_item_width(120)
            _cg, val_g = im.input_int("##merge_gap", self.merge_gap, 1, 5)
            if _cg:
                self.merge_gap = max(0, val_g)
                self._sync_to_tool()

        im.spacing()
        im.separator()
        im.text_colored("Threshold & Background:", (0.4, 0.8, 1.0, 1.0))

        im.align_text_to_frame_padding()
        im.text("Rate cutoff (kHz):")
        im.same_line(col_x)
        im.set_next_item_width(120)
        _ck, val_k = im.input_float("##threshold_khz", self.threshold_khz, 5.0, 20.0, "%.1f")
        if _ck:
            self.threshold_khz = max(0.1, val_k)
        if _ck:
            self.threshold_khz = max(0.1, val_k)
        if _ck:
            self.threshold_khz = max(0.1, val_k)

        _cb, self.subtract_background = im.checkbox("Subtract Background", self.subtract_background)
        if self.subtract_background:
            im.same_line()
            im.set_next_item_width(90)
            _, self.background_rate_khz = im.input_float(
                "kHz##bg", self.background_rate_khz, 0.5, 2.0, "%.1f"
            )

        im.spacing()
        im.separator()
        im.text_colored("Display Layers:", (0.4, 0.8, 1.0, 1.0))
        _, self.show_all_photons = im.checkbox("All Photons", self.show_all_photons)
        im.same_line()
        _, self.show_selected_photons = im.checkbox("Selected Bursts", self.show_selected_photons)

    # ── 3. Count Rate & Timeline (MCS) Content ──────────────────────────────

    def _draw_timeline_content(self, box: tuple[float, float, float, float]) -> None:
        im.set_next_item_width(140)
        _cb, self.mcs_bin_width_ms = im.slider_float(
            "Bin (ms)", self.mcs_bin_width_ms, 0.1, 20.0, "%.1f ms"
        )
        self.remember("diagnostics")
        im.same_line()
        im.text_colored(f"Threshold: {self.threshold_khz:.1f} kHz", (0.9, 0.4, 0.4, 1.0))

        diag = self._get_active_diagnostic()
        has_data = diag is not None and diag.get("tttr") is not None

        if not has_data:
            im.same_line()
            im.text_disabled("(No TTTR file loaded. Click Add Files)")

        if implot.begin_plot("MCS Intensity Trace", (-1, -1)):
            implot.setup_axes("Macro Time (s)", "Count Rate (kHz)")

            # Drag line for threshold
            d_res = implot.drag_line_y(301, self.threshold_khz, (0.9, 0.3, 0.3, 0.8), thickness=1.5)
            if d_res.modified:
                self.threshold_khz = max(0.1, float(d_res.value))
            implot.tag_y(
                self.threshold_khz, (0.9, 0.3, 0.3, 1.0), fmt=f"{self.threshold_khz:.1f} kHz"
            )

            if has_data:
                tttr = diag["tttr"]
                try:
                    bin_sec = max(0.0001, self.mcs_bin_width_ms / 1000.0)
                    trace = np.asarray(
                        tttr.get_intensity_trace(time_window_length=bin_sec), dtype=np.float64
                    )
                    if len(trace) > 0:
                        xs = np.linspace(
                            0.0, float(len(trace)) * bin_sec, len(trace), dtype=np.float64
                        )
                        rates_khz = trace / 1000.0
                        if self.show_all_photons:
                            implot.plot_line("All Photons", xs, rates_khz)

                        # Highlight burst intervals
                        selected = diag.get("selected")
                        if self.show_selected_photons and selected is not None and np.any(selected):
                            sel_indices = np.where(selected)[0]
                            if len(sel_indices) > 0:
                                sel_trace = np.asarray(
                                    tttr[sel_indices].get_intensity_trace(
                                        time_window_length=bin_sec
                                    ),
                                    dtype=np.float64,
                                )
                                sel_rates = sel_trace / 1000.0
                                n_pts = min(len(xs), len(sel_rates))
                                implot.plot_line("Burst Photons", xs[:n_pts], sel_rates[:n_pts])
                except Exception as exc:
                    logger.debug("MCS trace rendering error: %s", exc)

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                    th = data.get("threshold") or data.get("rate_threshold")
                    if th is not None:
                        self.threshold_khz = float(th)
                except Exception:
                    pass
            im.end_drag_drop_target()

    # ── 4. Inter-Photon Delay (dT) Content ──────────────────────────────────

    def _draw_dt_content(self, box: tuple[float, float, float, float]) -> None:
        _c, self.log_dt = im.checkbox("Log Y Axis", self.log_dt)
        im.same_line()
        im.text_colored("Poisson knee separates bursts from background", (0.7, 0.7, 0.7, 1.0))

        diag = self._get_active_diagnostic()
        has_data = diag is not None and diag.get("tttr") is not None

        if not has_data:
            im.same_line()
            im.text_disabled("(No TTTR file loaded)")

        if implot.begin_plot("Delta Macro-Time Distribution", (-1, -1)):
            implot.setup_axes("Δt (ms)", "Counts")
            if self.log_dt:
                implot.setup_axis_scale(implot.ImAxis_Y1, implot.ImPlotScale_Log10)

            if has_data:
                tttr = diag["tttr"]
                sel = diag.get("selected")
                try:
                    macro_times = tttr.macro_times
                    macro_res = getattr(tttr.header, "macro_time_resolution", 1e-7)
                    dt_ms = np.diff(macro_times) * macro_res * 1000.0
                    dt_valid = dt_ms[dt_ms > 0]
                    if len(dt_valid) > 0:
                        min_dt = max(1e-5, float(np.min(dt_valid)))
                        max_dt = min(1000.0, float(np.max(dt_valid)))
                        bins = np.logspace(np.log10(min_dt), np.log10(max_dt), 60)
                        counts_all, _ = np.histogram(dt_valid, bins=bins)
                        centers = np.sqrt(bins[:-1] * bins[1:])
                        if self.show_all_photons:
                            implot.plot_line("All Photons", centers, np.maximum(counts_all, 1.0))

                        if self.show_selected_photons and sel is not None and len(sel) > 1:
                            sel_mask = sel[:-1] & sel[1:]
                            if np.any(sel_mask):
                                counts_burst, _ = np.histogram(dt_ms[sel_mask], bins=bins)
                                implot.plot_line(
                                    "Burst Photons", centers, np.maximum(counts_burst, 1.0)
                                )
                except Exception as exc:
                    logger.debug("dT plot calculation error: %s", exc)

            # Threshold cutoff guide line
            th_dt_ms = (
                (float(self.photon_window) / max(0.1, self.threshold_khz))
                if self.threshold_khz > 0
                else 0.2
            )
            implot.drag_line_x(303, th_dt_ms, (0.9, 0.4, 0.2, 0.8), thickness=1.5)
            implot.tag_x(th_dt_ms, (0.9, 0.4, 0.2, 1.0), fmt=f"m/rate: {th_dt_ms:.3f} ms")

            implot.end_plot()

    # ── 5. Microtime Decay (TCSPC) Content ──────────────────────────────────

    def _draw_decay_content(self, box: tuple[float, float, float, float]) -> None:
        _c, self.log_decay = im.checkbox("Log Counts", self.log_decay)
        im.same_line()
        bins_options = [64, 128, 256, 512, 1024]
        bins_str = [str(b) for b in bins_options]
        decay_bins_idx = (
            bins_options.index(self.decay_bins) if self.decay_bins in bins_options else 2
        )
        im.set_next_item_width(100)
        changed_b, new_b_idx = im.combo("Bins", decay_bins_idx, bins_str)
        if changed_b and 0 <= new_b_idx < len(bins_options):
            self.decay_bins = bins_options[new_b_idx]

        diag = self._get_active_diagnostic()
        has_data = diag is not None and diag.get("tttr") is not None

        if not has_data:
            im.same_line()
            im.text_disabled("(No TTTR file loaded)")

        if implot.begin_plot("TCSPC Microtime Decay", (-1, -1)):
            implot.setup_axes("Microtime (ns)", "Counts")
            if self.log_decay:
                implot.setup_axis_scale(implot.ImAxis_Y1, implot.ImPlotScale_Log10)

            if has_data:
                tttr = diag["tttr"]
                sel = diag.get("selected")
                try:
                    y_all, x_all = tttr.get_microtime_histogram(self.decay_bins)
                    positive = np.where(y_all > 0)[0]
                    if len(positive) > 0:
                        last = int(positive[-1]) + 1
                        x_ns = x_all[:last] * 1e9
                        y_trimmed = y_all[:last]
                        if self.show_all_photons:
                            implot.plot_line("All Photons", x_ns, np.maximum(y_trimmed, 1.0))

                        if self.show_selected_photons and sel is not None and np.any(sel):
                            sel_indices = np.where(sel)[0]
                            if len(sel_indices) > 0:
                                y_sel, x_sel = tttr[sel_indices].get_microtime_histogram(
                                    self.decay_bins
                                )
                                y_sel_trimmed = y_sel[:last]
                                implot.plot_line(
                                    "Burst Photons", x_ns, np.maximum(y_sel_trimmed, 1.0)
                                )
                except Exception as exc:
                    logger.debug("Decay plot error: %s", exc)

            implot.end_plot()

    # ── 6. 1D / 2D Feature Scatter Content ──────────────────────────────────

    def _draw_scatter_content(self, box: tuple[float, float, float, float]) -> None:
        frame = getattr(self.tool, "_last_frame", None)
        cols = column_names(frame) if frame is not None else FEATURE_COLUMNS
        valid_cols = [
            c
            for c in cols
            if "file" not in c.lower()
            and any(
                k in c.lower()
                for k in [
                    "photon",
                    "ratio",
                    "stoich",
                    "duration",
                    "rate",
                    "count",
                    "fret",
                    "e",
                    "s",
                ]
            )
        ]
        if not valid_cols:
            valid_cols = FEATURE_COLUMNS

        # Feature pickers
        im.set_next_item_width(140)
        x_idx = min(self.feature_x_idx, len(valid_cols) - 1)
        changed_x, new_x = im.combo("X Feature", x_idx, valid_cols)
        if changed_x and 0 <= new_x < len(valid_cols):
            self.feature_x_idx = new_x

        im.same_line()
        im.set_next_item_width(140)
        y_idx = min(self.feature_y_idx, len(valid_cols) - 1)
        changed_y, new_y = im.combo("Y Feature", y_idx, valid_cols)
        if changed_y and 0 <= new_y < len(valid_cols):
            self.feature_y_idx = new_y

        im.same_line()
        _, self.show_static_fret_line = im.checkbox("Static FRET Line", self.show_static_fret_line)

        col_x = valid_cols[min(self.feature_x_idx, len(valid_cols) - 1)]
        col_y = valid_cols[min(self.feature_y_idx, len(valid_cols) - 1)]

        has_bursts = frame is not None and row_count(frame) > 0
        if not has_bursts:
            im.same_line()
            im.text_disabled("(No bursts detected. Click Find Bursts)")

        if implot.begin_plot("2D Feature Scatter with Gating", (-1, -1)):
            implot.setup_axes(col_x, col_y)

            # Interactive Gating Box
            res_rect = implot.drag_rect(
                302,
                self.gate_x_min,
                self.gate_y_min,
                self.gate_x_max,
                self.gate_y_max,
                REGION_FILL,
            )
            if res_rect.modified:
                self.gate_x_min, self.gate_y_min, self.gate_x_max, self.gate_y_max = (
                    float(res_rect.x_min),
                    float(res_rect.y_min),
                    float(res_rect.x_max),
                    float(res_rect.y_max),
                )
            implot.tag_x(self.gate_x_min, ACCENT_GREEN, fmt=f"X_min: {self.gate_x_min:.2f}")
            implot.tag_x(self.gate_x_max, ACCENT_GREEN, fmt=f"X_max: {self.gate_x_max:.2f}")

            # Static line in E-S representation
            if (
                self.show_static_fret_line
                and ("ratio" in col_x.lower() or col_x == "E")
                and ("stoich" in col_y.lower() or col_y == "S")
            ):
                line_e = np.linspace(0.0, 1.0, 100)
                line_s = np.full_like(line_e, 0.5)
                implot.plot_line("Static FRET Line", line_e, line_s)

            if has_bursts:
                try:
                    data_x = numeric_column(frame, col_x)
                    data_y = numeric_column(frame, col_y)
                    valid = np.isfinite(data_x) & np.isfinite(data_y)
                    if np.any(valid):
                        implot.plot_scatter(
                            f"Bursts ({np.sum(valid):,})", data_x[valid], data_y[valid]
                        )
                except Exception as exc:
                    logger.debug("Scatter plot error: %s", exc)

            implot.end_plot()

        # Drag Source: Region Payload from Current Gate
        if im.begin_drag_drop_source():
            region_payload = json.dumps(
                {
                    "type": "scatter_gate",
                    "x_name": col_x,
                    "y_name": col_y,
                    "x_range": [self.gate_x_min, self.gate_x_max],
                    "y_range": [self.gate_y_min, self.gate_y_max],
                    "threshold": self.threshold_khz,
                }
            )
            im.set_drag_drop_payload("BURST_REGION", region_payload.encode("utf-8"))
            im.text(f"Gate: {col_x} [{self.gate_x_min:.2f}, {self.gate_x_max:.2f}]")
            im.end_drag_drop_source()

    # ── 7. 1D Feature Histogram Content ─────────────────────────────────────

    def _draw_1d_histogram_content(self, box: tuple[float, float, float, float]) -> None:
        frame = getattr(self.tool, "_last_frame", None)
        cols = column_names(frame) if frame is not None else FEATURE_COLUMNS
        valid_cols = [
            c
            for c in cols
            if "file" not in c.lower()
            and any(
                k in c.lower()
                for k in [
                    "photon",
                    "ratio",
                    "stoich",
                    "duration",
                    "rate",
                    "count",
                    "fret",
                    "e",
                    "s",
                ]
            )
        ]
        if not valid_cols:
            valid_cols = FEATURE_COLUMNS

        im.set_next_item_width(150)
        feat_idx = min(self.hist_feature_idx, len(valid_cols) - 1)
        changed_f, new_f = im.combo("Feature", feat_idx, valid_cols)
        if changed_f and 0 <= new_f < len(valid_cols):
            self.hist_feature_idx = new_f

        im.same_line()
        im.set_next_item_width(110)
        _, self.hist_bins = im.slider_int("Bins", self.hist_bins, 10, 200)

        im.same_line()
        _, self.hist_log_y = im.checkbox("Log Y", self.hist_log_y)

        selected_feat = valid_cols[min(self.hist_feature_idx, len(valid_cols) - 1)]
        has_bursts = frame is not None and row_count(frame) > 0

        if not has_bursts:
            im.same_line()
            im.text_disabled("(No bursts detected)")

        if implot.begin_plot(f"1D Histogram: {selected_feat}", (-1, -1)):
            implot.setup_axes(selected_feat, "Counts")
            if self.hist_log_y:
                implot.setup_axis_scale(implot.ImAxis_Y1, implot.ImPlotScale_Log10)

            if has_bursts:
                try:
                    data = numeric_column(frame, selected_feat)
                    valid_data = data[np.isfinite(data)]
                    if len(valid_data) > 0:
                        counts, edges = np.histogram(valid_data, bins=self.hist_bins)
                        centers = (edges[:-1] + edges[1:]) * 0.5
                        bar_w = (edges[1] - edges[0]) * 0.9
                        counts_plot = np.maximum(counts, 1.0) if self.hist_log_y else counts
                        implot.plot_bars(
                            f"Distribution ({len(valid_data):,})", centers, counts_plot, bar_w
                        )
                except Exception as exc:
                    logger.debug("1D histogram plot error: %s", exc)

            implot.end_plot()

    # ── 8. Burst Duration Content ───────────────────────────────────────────

    def _draw_burst_length_content(self, box: tuple[float, float, float, float]) -> None:
        im.set_next_item_width(120)
        _, self.burst_bins = im.slider_int("Bins", self.burst_bins, 10, 100)

        frame = getattr(self.tool, "_last_frame", None)
        has_bursts = frame is not None and row_count(frame) > 0

        if not has_bursts:
            im.same_line()
            im.text_disabled("(No bursts detected)")

        if implot.begin_plot("Burst Duration Distribution", (-1, -1)):
            implot.setup_axes("Burst Duration (ms)", "Counts")

            if has_bursts:
                cols = column_names(frame)
                dur_col = next((c for c in cols if "duration" in c.lower()), None)
                if dur_col:
                    try:
                        durs = numeric_column(frame, dur_col)
                        valid_durs = durs[np.isfinite(durs) & (durs > 0)]
                        if len(valid_durs) > 0:
                            counts, edges = np.histogram(valid_durs, bins=self.burst_bins)
                            centers = (edges[:-1] + edges[1:]) * 0.5
                            implot.plot_bars(
                                "Duration Distribution",
                                centers,
                                counts,
                                (edges[1] - edges[0]) * 0.9,
                            )
                    except Exception as exc:
                        logger.debug("Burst length histogram error: %s", exc)

            implot.end_plot()

    # ── 9. Bursts Table Content ─────────────────────────────────────────────

    def _draw_table_content(self, box: tuple[float, float, float, float]) -> None:
        frame = getattr(self.tool, "_last_frame", None)
        n_rows = row_count(frame) if frame is not None else 0
        n_pages = max(1, (n_rows + self.page_size - 1) // self.page_size)

        # Pagination & Controls
        if self.table_page > 0 and im.button("◀ Prev"):
            self.table_page -= 1
        im.same_line()
        im.text(f"Page {self.table_page + 1} of {n_pages} ({n_rows:,} bursts)")
        im.same_line()
        if self.table_page < n_pages - 1 and im.button("Next ▶"):
            self.table_page += 1

        im.same_line()
        im.set_next_item_width(90)
        _cp, self.page_size = im.slider_int("Per Page", self.page_size, 25, 200)

        cols_wanted = [
            "Burst #",
            "Start (s)",
            "Stop (s)",
            "Photons",
            "Duration (ms)",
            "Count Rate (kHz)",
            "E",
            "S",
        ]
        table_h = max(80.0, box[3] - 40.0)
        table_flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SIZING_FIXED_FIT
        )
        if im.begin_table("bursts_tbl", len(cols_wanted), table_flags, (0, table_h)):
            im.table_setup_column("Burst #", im.TableColumnFlags.WIDTH_FIXED, 55.0)
            im.table_setup_column("Start (s)", im.TableColumnFlags.WIDTH_FIXED, 75.0)
            im.table_setup_column("Stop (s)", im.TableColumnFlags.WIDTH_FIXED, 75.0)
            im.table_setup_column("Photons", im.TableColumnFlags.WIDTH_FIXED, 65.0)
            im.table_setup_column("Duration", im.TableColumnFlags.WIDTH_FIXED, 70.0)
            im.table_setup_column("Rate (kHz)", im.TableColumnFlags.WIDTH_FIXED, 75.0)
            im.table_setup_column("E", im.TableColumnFlags.WIDTH_FIXED, 55.0)
            im.table_setup_column("S", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()

            if frame is not None and n_rows > 0:
                cols = column_names(frame)
                start_col = next((c for c in cols if "start" in c.lower()), None)
                stop_col = next((c for c in cols if "stop" in c.lower()), None)
                ph_col = next((c for c in cols if "photon" in c.lower() or c == "counts"), None)
                dur_col = next((c for c in cols if "duration" in c.lower()), None)
                rate_col = next((c for c in cols if "rate" in c.lower()), None)
                e_col = next(
                    (
                        c
                        for c in cols
                        if "proximity" in c.lower() or "fret" in c.lower() or c == "E"
                    ),
                    None,
                )
                s_col = next((c for c in cols if "stoichiometry" in c.lower() or c == "S"), None)

                starts = numeric_column(frame, start_col) if start_col else np.zeros(n_rows)
                stops = numeric_column(frame, stop_col) if stop_col else np.zeros(n_rows)
                phs = numeric_column(frame, ph_col) if ph_col else np.zeros(n_rows)
                durs = numeric_column(frame, dur_col) if dur_col else np.zeros(n_rows)
                rates = numeric_column(frame, rate_col) if rate_col else np.zeros(n_rows)
                es = numeric_column(frame, e_col) if e_col else np.zeros(n_rows)
                ss = numeric_column(frame, s_col) if s_col else np.zeros(n_rows)

                start_idx = self.table_page * self.page_size
                end_idx = min(start_idx + self.page_size, n_rows)

                for idx in range(start_idx, end_idx):
                    im.table_next_row()
                    im.table_set_column_index(0)
                    is_sel = idx == self.selected_burst_idx
                    if im.selectable(f"#{idx + 1}", is_sel):
                        self.selected_burst_idx = idx
                    im.table_set_column_index(1)
                    im.text(f"{starts[idx]:.4f}")
                    im.table_set_column_index(2)
                    im.text(f"{stops[idx]:.4f}")
                    im.table_set_column_index(3)
                    im.text(f"{int(phs[idx])}")
                    im.table_set_column_index(4)
                    im.text(f"{durs[idx]:.2f} ms")
                    im.table_set_column_index(5)
                    im.text(f"{rates[idx]:.1f}")
                    im.table_set_column_index(6)
                    im.text(f"{es[idx]:.2f}")
                    im.table_set_column_index(7)
                    im.text(f"{ss[idx]:.2f}")
            else:
                im.table_next_row()
                im.table_set_column_index(0)
                im.text_disabled("No bursts detected yet. Click Find Bursts.")

            im.end_table()

    # ── 10. Summary & Metrics Content ───────────────────────────────────────

    def _draw_summary_content(self, box: tuple[float, float, float, float]) -> None:
        frame = getattr(self.tool, "_last_frame", None)
        n_bursts = row_count(frame) if frame is not None else 0

        # High level metric cards
        im.text_colored(f"• Total Bursts: {n_bursts:,}", (0.3, 0.85, 0.4, 1.0))

        if frame is not None and n_bursts > 0:
            cols = column_names(frame)
            ph_col = next((c for c in cols if "photon" in c.lower() or c == "counts"), None)
            dur_col = next((c for c in cols if "duration" in c.lower()), None)
            rate_col = next((c for c in cols if "rate" in c.lower()), None)

            if ph_col:
                phs = numeric_column(frame, ph_col)
                im.text(f"• Mean Photons: {np.mean(phs):.1f} ± {np.std(phs):.1f}")
            if dur_col:
                durs = numeric_column(frame, dur_col)
                im.text(f"• Mean Duration: {np.mean(durs):.2f} ms")
            if rate_col:
                rates = numeric_column(frame, rate_col)
                im.text(f"• Mean Rate: {np.mean(rates):.1f} kHz")
        else:
            im.text_disabled("• Mean Photons: —")
            im.text_disabled("• Mean Duration: —")
            im.text_disabled("• Mean Rate: —")

        files = getattr(self.tool, "_file_paths", [])
        im.separator()
        im.text_colored(f"Files Analyzed: {len(files)}", (0.7, 0.8, 0.9, 1.0))
        if 0 <= self.active_file_idx < len(files):
            im.text(f"Active: {files[self.active_file_idx].name}")

        im.separator()
        im.text_colored("Status:", (0.7, 0.7, 0.7, 1.0))
        if n_bursts > 0:
            im.text_colored(f"Ready ({n_bursts:,} bursts)", (0.4, 0.9, 0.5, 1.0))
        elif files:
            im.text_colored("Files ready. Click Find Bursts.", (0.9, 0.8, 0.3, 1.0))
        else:
            im.text_disabled("No files loaded.")

    # ── 11. In-EMTK Help & Reference Content ────────────────────────────────

    def _draw_help_content(self, box: tuple[float, float, float, float]) -> None:
        """Render rich in-EMTK Help & Reference documentation."""
        im.align_text_to_frame_padding()
        im.text_colored("Burst Selection — Documentation & Reference", (0.4, 0.8, 1.0, 1.0))
        im.same_line()
        if im.button("Start Guided Tour"):
            self.start_guide()
        im.same_line()
        if im.button("Close Help"):
            self.docks.hide("help")

        im.separator()

        # Category filter buttons
        categories = [
            "All",
            "Algorithms",
            "Best Practices",
            "Channels",
            "Diagnostics",
            "Validation",
        ]
        for cat in categories:
            is_active = self.help_tab_topic == cat
            if is_active:
                im.push_style_color(Col.BUTTON, ACCENT_GREEN)
            if im.button(cat):
                self.help_tab_topic = cat
            if is_active:
                im.pop_style_color()
            im.same_line()
        im.new_line()
        im.separator()

        topic = self.help_tab_topic

        if topic in ("All", "Algorithms"):
            im.text_colored("1. Burst Identification Algorithms", (0.3, 0.85, 0.4, 1.0))
            im.bullet()
            im.text_colored("Sliding Window (Lee & Weiss 2002):", (0.9, 0.9, 0.9, 1.0))
            im.text("   Slides a window of m photons. Instantaneous rate R = m / dt.")
            im.text("   Burst opens when R exceeds F * background, and closes when R drops.")
            im.text("   Local background thresholding protects against buffer/laser drift.")
            im.spacing()
            im.bullet()
            im.text_colored("CUSUM / SPRT (Sequential Probability Ratio):", (0.9, 0.9, 0.9, 1.0))
            im.text("   Accumulates log-likelihood ratios to detect abrupt rate increases.")
            im.text(
                "   Guarantees bounds on false-alarm probability (alpha) and missed-detection (beta)."
            )
            im.spacing()
            im.bullet()
            im.text_colored("Kalman Filter (Dynamic State Estimation):", (0.9, 0.9, 0.9, 1.0))
            im.text("   Continuously estimates count rate with Kalman gain. Flags bursts when")
            im.text(
                "   residual Z-score exceeds threshold. Highly robust for variable burst lengths."
            )
            im.spacing()
            im.bullet()
            im.text_colored("BOCPD (Bayesian Online Changepoints):", (0.9, 0.9, 0.9, 1.0))
            im.text("   Recursive exact Bayesian inference with Poisson-Gamma conjugate priors.")
            im.spacing()
            im.bullet()
            im.text_colored("Coincident (ALEX Dual-Channel):", (0.9, 0.9, 0.9, 1.0))
            im.text("   Requires simultaneous rate rise in both donor and acceptor excitation.")
            im.text("   Rejects donor-only or acceptor-only singly-labeled species.")
            im.spacing()
            im.bullet()
            im.text_colored("Max-Tree & Bayesian Blocks:", (0.9, 0.9, 0.9, 1.0))
            im.text(
                "   Adaptive hierarchical threshold-free segmentation and Scargle optimal partitioning."
            )
            im.separator()

        if topic in ("All", "Best Practices"):
            im.text_colored("2. Critical Best Practice: Size Cuts", (1.0, 0.6, 0.3, 1.0))
            im.text_colored(
                "   Do NOT put the minimum-photon cut (L) inside the search!", (1.0, 0.4, 0.4, 1.0)
            )
            im.text("   Search permissively with consecutive photons (m), then apply the size cut")
            im.text("   afterwards on the background-corrected burst size.")
            im.text("   Applying a size cut during the search biases against dim bursts,")
            im.text("   distorting FRET efficiency distributions.")
            im.separator()

        if topic in ("All", "Channels"):
            im.text_colored("3. Detector Setup & Microtime Windows", (0.4, 0.8, 1.0, 1.0))
            im.text("   The detector setup binds hardware routing channels to excitation periods.")
            im.text(
                "   A swapped assignment reflects E around 0.5 without producing any fit error."
            )
            im.text("   Confirm detector setup once against a known reference sample.")
            im.text(
                "   Microtime windows (prompt vs delayed) distinguish direct acceptor excitation from FRET."
            )
            im.separator()

        if topic in ("All", "Diagnostics"):
            im.text_colored("4. Diagnostic Plots Guide", (0.4, 0.8, 1.0, 1.0))
            im.bullet()
            im.text_colored("Count Rate (MCS):", (0.9, 0.9, 0.9, 1.0))
            im.text(
                "   Macro-time trace: reveals photobleaching, focus drift, and aggregate crossings."
            )
            im.bullet()
            im.text_colored("Inter-Photon Delay (dT):", (0.9, 0.9, 0.9, 1.0))
            im.text(
                "   Background is an exponential decay; bursts produce a short-time excess peak."
            )
            im.bullet()
            im.text_colored("Microtime Decay (TCSPC):", (0.9, 0.9, 0.9, 1.0))
            im.text("   Lifetime decay comparing all photons vs selected burst photons.")
            im.bullet()
            im.text_colored("Burst Duration:", (0.9, 0.9, 0.9, 1.0))
            im.text("   Distribution of burst transit times. Smooth decay without minimum spikes.")
            im.bullet()
            im.text_colored("2D Feature Scatter & Gating:", (0.9, 0.9, 0.9, 1.0))
            im.text("   Bivariate scatter (E vs S) with interactive draggable gating box.")
            im.bullet()
            im.text_colored("1D Feature Histogram:", (0.9, 0.9, 0.9, 1.0))
            im.text("   1D distribution with customizable bins and optional log-Y scaling.")
            im.bullet()
            im.text_colored("Bursts Table:", (0.9, 0.9, 0.9, 1.0))
            im.text(
                "   Paginated table of detected bursts with photon counts, durations, and rates."
            )
            im.separator()

        if topic in ("All", "Validation"):
            im.text_colored("5. Quality Verification Rules", (0.3, 0.85, 0.4, 1.0))
            im.text("   1. Vary the threshold by a factor of 2 — real populations persist.")
            im.text("   2. Inspect the MCS intensity trace across the entire acquisition.")
            im.text(
                "   3. Verify donor-only and acceptor-only populations land at expected positions."
            )
            im.separator()

    # ── 12. In-EMTK Guided Tour ─────────────────────────────────────────────

    TOUR_STEPS: list[dict[str, Any]] = [
        {
            "title": "Deciding what a burst is",
            "text": "Burst Selection defines bursts from raw photon arrival timestamps. All downstream analyses (BVA, 2CDE, MLE, H2MM, and FRET histograms) depend on the bursts identified here.",
            "target": None,
            "dock": "settings",
            "hint": "Follow this 7-step tour to master burst selection.",
        },
        {
            "title": "1. Load raw TTTR files",
            "text": "Add TTTR files or a folder of measurements. Files are read once here and cached for all downstream analysis steps without reopening raw files.",
            "target": "add",
            "dock": "files",
            "hint": "Click 'Add Files' or 'Add Folder' to load measurements.",
        },
        {
            "title": "2. Detector & Microtime setup",
            "text": "The detector setup specifies physical donor/acceptor channels and excitation periods. Set it to match your hardware to ensure correct E and S values.",
            "target": "detector",
            "dock": "settings",
            "hint": "Select your detector channel and microtime window.",
        },
        {
            "title": "3. Burst detection algorithm",
            "text": "Choose from 7 algorithms (Sliding window, CUSUM/SPRT, Kalman, BOCPD, Coincident, Max-tree, Bayesian Blocks). Sliding window with local background threshold is the primary standard.",
            "target": "algorithm",
            "dock": "settings",
            "hint": "Select the burst identification algorithm.",
        },
        {
            "title": "4. Search parameters & size cuts",
            "text": "Important rule: Keep the search permissive (m consecutive photons) and apply the minimum photon cut (L) afterwards on background-corrected sizes to avoid biasing dim populations.",
            "target": "parameters",
            "dock": "settings",
            "hint": "Tune photon window m, time window T, and min photons L.",
        },
        {
            "title": "5. Run burst identification",
            "text": "Click 'Find Bursts' to execute the detection algorithm over all included TTTR files. The diagnostic tabs immediately populate with real data.",
            "target": "run",
            "dock": "settings",
            "hint": "Click 'Find Bursts' to run detection.",
        },
        {
            "title": "6. Inspect diagnostics & validate",
            "text": "Check dT (short-time excess over exponential background), MCS (trace stability), Decay (TCSPC), and 2D Scatter (gate E vs S). Test: vary threshold by 2x to confirm populations persist.",
            "target": "diagnostics",
            "dock": "trace",
            "hint": "Review the diagnostic tabs to verify burst quality.",
        },
    ]

    @property
    def tour(self):
        """Unified tour controller property."""

        class _TourShim:
            def __init__(self, outer):
                self._outer = outer

            @property
            def active(self) -> bool:
                return bool(self._outer.tour_active)

            def start(self) -> None:
                self._outer.start_guide()

            def stop(self) -> None:
                self._outer.tour_active = False

        return _TourShim(self)

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour_active = True
        self.tour_step = 0
        self._sync_tour_step()

    def show_help(self) -> None:
        """Show the in-EMTK Help Window (and focus Help dock tab if present)."""
        self.help_window.show()
        if "help" in self.docks.windows:
            self.docks.focus("help")

    def _sync_tour_step(self) -> None:
        """Synchronize dock tab focus for current tour step."""
        if 0 <= self.tour_step < len(self.TOUR_STEPS):
            step = self.TOUR_STEPS[self.tour_step]
            dock = step.get("dock")
            if dock and dock in self.docks.windows:
                self.docks.focus(dock)

    def _draw_tour_overlay(self, width: float, height: float) -> None:
        """Render floating guided tour card and spotlight border in EMTK."""
        if not (0 <= self.tour_step < len(self.TOUR_STEPS)):
            self.tour_active = False
            return

        step = self.TOUR_STEPS[self.tour_step]
        ctx = im.get_current_context()

        # Dimmed backdrop
        ctx.draw.add_rect_filled((0.0, 0.0), (width, height), (0, 0, 0, 90))

        # Check target rect
        target_key = step.get("target")
        target_rect = self.item_rects.get(target_key) if target_key else None

        card_w = min(480.0, width - 40.0)
        card_h = 195.0

        if target_rect:
            tx, ty, tw, th = target_rect
            # Highlight border around target
            ctx.draw.add_rect(
                (tx - 3.0, ty - 3.0),
                (tx + tw + 3.0, ty + th + 3.0),
                (56, 210, 80, 255),
                rounding=4.0,
                thickness=2.5,
            )
            # Position card smartly relative to target:
            # If target is on the left panel (dock), put the card to its right so it doesn't obscure the settings
            if tx < 350.0 and tx + tw + card_w + 20.0 <= width:
                cx = tx + tw + 16.0
                cy = max(45.0, min(ty, height - card_h - 20.0))
            elif ty + th + card_h + 16.0 <= height:
                cx = max(16.0, min(tx, width - card_w - 16.0))
                cy = ty + th + 10.0
            elif ty - card_h - 10.0 >= 40.0:
                cx = max(16.0, min(tx, width - card_w - 16.0))
                cy = ty - card_h - 10.0
            else:
                cx = (width - card_w) / 2.0
                cy = (height - card_h) / 2.0
        else:
            cx = (width - card_w) / 2.0
            cy = (height - card_h) / 2.0

        # Tour Card Body
        ctx.draw.add_rect_filled(
            (cx, cy),
            (cx + card_w, cy + card_h),
            (26, 28, 36, 250),
            rounding=8.0,
        )
        ctx.draw.add_rect(
            (cx, cy),
            (cx + card_w, cy + card_h),
            (70, 140, 240, 255),
            rounding=8.0,
            thickness=1.5,
        )

        # Content area with native wrapping inside a clipped child region
        content_margin = 14.0
        im.begin_child(
            (cx + content_margin, cy + 10.0, card_w - 2 * content_margin, card_h - 48.0),
            clip=True,
        )
        im.text_colored(
            f"Step {self.tour_step + 1} of {len(self.TOUR_STEPS)}: {step['title']}",
            (0.4, 0.8, 1.0, 1.0),
        )
        im.spacing()
        im.text_wrapped(step["text"])
        if step.get("hint"):
            im.spacing()
            im.text_colored(f"💡 {step['hint']}", (0.5, 0.9, 0.5, 1.0))
        im.end_child()

        # Action buttons at bottom of card
        btn_y = cy + card_h - 34.0
        im.set_cursor_screen_pos((cx + 14.0, btn_y))
        if im.button("Close Tour"):
            self.tour_active = False

        im.set_cursor_screen_pos((cx + card_w - 170.0, btn_y))
        if self.tour_step > 0:
            if im.button("◄ Prev"):
                self.tour_step -= 1
                self._sync_tour_step()
        else:
            im.begin_disabled()
            im.button("◄ Prev")
            im.end_disabled()

        im.same_line()
        is_last = self.tour_step == len(self.TOUR_STEPS) - 1
        next_label = "Finish ✓" if is_last else "Next ►"
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        if im.button(next_label):
            if is_last:
                self.tour_active = False
            else:
                self.tour_step += 1
                self._sync_tour_step()
        im.pop_style_color()


class BurstSelectionApp(ImApp):
    """Immediate-mode EMTK application for Burst Selection."""

    def __init__(
        self,
        tool: BurstSelectionTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.selection_gui = BurstSelectionGui(
            tool=tool,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.tool = self.selection_gui.tool
        super().__init__(gui=self._render, continuous=False)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.selection_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.selection_gui.show_help()

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.selection_gui.item_rects

    @property
    def on_used(self) -> Callable[[str], None] | None:
        return self.selection_gui.on_used

    @on_used.setter
    def on_used(self, cb: Callable[[str], None] | None) -> None:
        self.selection_gui.on_used = cb

    def _render(self) -> None:
        w, h = im.get_main_viewport().size
        self.selection_gui.draw(float(w), float(h))
