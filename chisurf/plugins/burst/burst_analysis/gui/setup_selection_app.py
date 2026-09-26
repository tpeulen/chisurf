"""EMTK immediate-mode UI for Setup Selection (Step 0) in Burst Analysis."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split

from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.gui.widgets.wizard.tttr_channeldefinition.setup_client import (
    DetectorSetupClient,
)
from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_detector_setups import (
    load_detector_setups,
)

if TYPE_CHECKING:
    from .tool import BurstSetupSelectionWidget

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)

# Standard template setups provided as fallbacks if the database has no entries
_DEFAULT_FALLBACK_SETUPS: dict[str, dict[str, Any]] = {
    "PIE-MFD": {
        "setup_name": "PIE-MFD",
        "detectors": {
            "green_parallel": {
                "chs": [0],
                "micro_time_ranges": [[500, 3500]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "green_perpendicular": {
                "chs": [1],
                "micro_time_ranges": [[500, 3500]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "red_parallel": {
                "chs": [2],
                "micro_time_ranges": [[500, 3500]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "red_perpendicular": {
                "chs": [3],
                "micro_time_ranges": [[500, 3500]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "yellow": {
                "chs": [2, 3],
                "micro_time_ranges": [[4200, 7500]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
        },
        "windows": {"prompt": [500, 3500], "delayed": [4200, 7500]},
        "tttr_reading": {"excitation_period": 8000, "micro_time_binning": 1, "file_type": "PTO"},
    },
    "ALEX Suite (auto)": {
        "setup_name": "ALEX Suite (auto)",
        "detectors": {
            "green": {
                "chs": [1],
                "micro_time_ranges": [[616, 3784]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "red": {
                "chs": [0],
                "micro_time_ranges": [[616, 3784]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "yellow": {
                "chs": [0],
                "micro_time_ranges": [[4278, 7762]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
        },
        "windows": {"prompt": [616, 3784], "delayed": [4278, 7762]},
        "tttr_reading": {"excitation_period": 8000, "micro_time_binning": 1, "file_type": "PTO"},
    },
    "smFRET (2-Color)": {
        "setup_name": "smFRET (2-Color)",
        "detectors": {
            "donor": {
                "chs": [0],
                "micro_time_ranges": [[0, 4095]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
            "acceptor": {
                "chs": [1],
                "micro_time_ranges": [[0, 4095]],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            },
        },
        "windows": {"all": [0, 4095]},
        "tttr_reading": {"excitation_period": 4096, "micro_time_binning": 1, "file_type": "PTO"},
    },
}


class BurstSetupSelectionGui:
    """EMTK GUI providing responsive, dockable windows for TTTR detector setup selection."""

    def __init__(
        self,
        widget: BurstSetupSelectionWidget,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.widget = widget
        self.on_guide = on_guide
        self.on_help = on_help

        self.setup_client = DetectorSetupClient()
        self.available_setups: dict[str, dict[str, Any]] = {}
        self.setup_names: list[str] = []
        self.selected_setup_name: str = ""
        self.selected_setup_data: dict[str, Any] = {}

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        # Load available setups from client & store
        self.refresh_setups()

        layout = Split(
            "h",
            0.62,
            Region("setup"),
            Split("v", 0.52, Region("details"), Region("summary")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "setup",
            "⚙️ Detector Setup & Channel Routing",
            self._draw_setup,
            dock="setup",
            closable=False,
        )
        self.docks.add_window(
            "details",
            "ℹ️ Setup Guide & Channel Mapping",
            self._draw_details,
            dock="details",
            closable=False,
        )
        self.docks.add_window(
            "summary",
            "✓ Status & Pipeline Handoff",
            self._draw_summary,
            dock="summary",
            closable=False,
        )

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Setup Selection — Help & Reference",
            resource=help_resource,
            owner=self.widget,
            on_start_guide=self.start_guide,
            size=(720.0, 540.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.widget,
        )

    def refresh_setups(self) -> None:
        """Reload setups from the canonical database, RPC service, and fallbacks."""
        setups: dict[str, dict[str, Any]] = {}
        last_used = ""

        try:
            loaded = load_detector_setups()
            if isinstance(loaded, dict):
                setups.update(loaded.get("setups", {}))
                last_used = loaded.get("last_used", "") or last_used
        except Exception as exc:
            logger.debug(f"load_detector_setups failed: {exc}")

        try:
            client_list = self.setup_client.list_setups()
            if isinstance(client_list, dict):
                last_used = client_list.get("last_used") or last_used
                for name in client_list.get("setups", []):
                    if name not in setups:
                        s_data = self.setup_client.get_setup(name)
                        if s_data:
                            setups[name] = s_data
        except Exception as exc:
            logger.debug(f"client.list_setups failed: {exc}")

        # Seed with fallback templates if still empty
        for name, data in _DEFAULT_FALLBACK_SETUPS.items():
            if name not in setups:
                setups[name] = data

        self.available_setups = setups
        self.setup_names = sorted(list(setups.keys()))

        # Determine currently selected setup
        current = ""
        tool = getattr(self.widget, "tool", None)
        if tool is not None and getattr(tool, "workflow_context", None):
            current = tool.workflow_context.setup_name

        if not current:
            current = (
                last_used
                if last_used in setups
                else (self.setup_names[0] if self.setup_names else "")
            )

        if current and current in setups:
            self.select_setup(current, sync=False)
        elif self.setup_names:
            self.select_setup(self.setup_names[0], sync=False)

    def select_setup(self, name: str, sync: bool = True) -> None:
        """Select a setup by name and update shared workflow context."""
        if not name or name not in self.available_setups:
            return
        self.selected_setup_name = name
        self.selected_setup_data = dict(self.available_setups[name])

        if sync:
            self.sync_to_tool()

    def sync_to_tool(self) -> None:
        """Propagate current setup to BurstAnalysisTool workflow context."""
        tool = getattr(self.widget, "tool", None)
        if tool is None:
            return

        if hasattr(tool, "workflow_context"):
            tool.workflow_context.setup_name = self.selected_setup_name
            tool.workflow_context.channel_settings = self.selected_setup_data

        try:
            self.setup_client.set_current(self.selected_setup_data)
        except Exception as exc:
            logger.debug(f"setup_client.set_current failed: {exc}")

        if hasattr(tool, "_apply_context_to_downstream"):
            tool._apply_context_to_downstream()

        if hasattr(tool, "host"):
            tool.host.update()

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        """Store the item's screen rectangle for tour targeting."""
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        """Render the 3 dock windows, help window, and tour overlay."""
        vp = im.get_main_viewport()
        vw, vh = vp.size
        width = float(w or vw or 800.0)
        height = float(h or vh or 600.0)

        self.docks.draw((0.0, 0.0, width, height))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        if self.tour.active:
            self.tour.draw(width, height)

    def update(self) -> None:
        self.draw()

    def _draw_setup(self, box: tuple[float, float, float, float]) -> None:
        """Draw setup selection controls, detector table, and microtime windows."""
        # Top Action Bar
        im.align_text_to_frame_padding()
        im.text("Setup Preset:")
        im.same_line()

        idx = (
            self.setup_names.index(self.selected_setup_name)
            if self.selected_setup_name in self.setup_names
            else 0
        )
        im.set_next_item_width(max(140.0, box[2] - 270.0))
        changed, new_idx = im.combo("##SetupSelectorCombo", idx, self.setup_names)
        if changed and 0 <= new_idx < len(self.setup_names):
            self.select_setup(self.setup_names[new_idx], sync=True)

        im.same_line()
        if im.button("🔄 Refresh"):
            self.refresh_setups()
            self.sync_to_tool()

        im.same_line()
        if im.button("🛠️ Wizard"):
            self._open_channel_wizard()

        im.spacing()
        im.separator()
        im.spacing()

        # Overview Pills
        detectors = self.selected_setup_data.get("detectors", {})
        windows = self.selected_setup_data.get("windows", {})
        reading = self.selected_setup_data.get("tttr_reading", {})

        im.text_colored(f"Active Setup: {self.selected_setup_name}", (0.35, 0.75, 1.0, 1.0))
        im.same_line()
        im.text_disabled(f"({len(detectors)} detectors, {len(windows)} excitation windows)")

        im.spacing()

        # ── Detectors Table ─────────────────────────────────────────────────
        im.text_colored("Physical Detectors & Channel Routing", (0.9, 0.9, 0.9, 1.0))
        table_flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.RESIZABLE
            | im.TableFlags.SIZING_FIXED_FIT
        )
        det_table_h = min(160.0, max(85.0, len(detectors) * 26.0 + 30.0))
        if im.begin_table("detectors_table", 7, table_flags, (0, det_table_h)):
            im.table_setup_column("#", im.TableColumnFlags.WIDTH_FIXED, 28.0)
            im.table_setup_column("Detector", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Routing Chs", im.TableColumnFlags.WIDTH_FIXED, 95.0)
            im.table_setup_column("Microtime Range", im.TableColumnFlags.WIDTH_FIXED, 130.0)
            im.table_setup_column("G-Factor", im.TableColumnFlags.WIDTH_FIXED, 70.0)
            im.table_setup_column("l1", im.TableColumnFlags.WIDTH_FIXED, 50.0)
            im.table_setup_column("l2", im.TableColumnFlags.WIDTH_FIXED, 50.0)
            im.table_headers_row()

            for i, (det_name, det_info) in enumerate(detectors.items()):
                im.table_next_row()

                # Column 0: Index
                im.table_set_column_index(0)
                im.text(f"{i + 1}")

                # Column 1: Detector name
                im.table_set_column_index(1)
                col = (
                    (0.4, 0.85, 0.5, 1.0)
                    if "green" in det_name.lower() or "donor" in det_name.lower()
                    else (
                        (0.95, 0.45, 0.45, 1.0)
                        if "red" in det_name.lower() or "acceptor" in det_name.lower()
                        else (
                            (0.95, 0.85, 0.3, 1.0)
                            if "yellow" in det_name.lower()
                            else (0.85, 0.85, 0.85, 1.0)
                        )
                    )
                )
                im.text_colored(det_name, col)

                # Column 2: Routing channels
                im.table_set_column_index(2)
                chs = det_info.get("chs", [])
                im.text(str(chs))

                # Column 3: Microtime ranges
                im.table_set_column_index(3)
                ranges = det_info.get("micro_time_ranges", [])
                if ranges and len(ranges) == 1:
                    im.text(f"[{ranges[0][0]}, {ranges[0][1]}]")
                elif ranges:
                    im.text(str(ranges))
                else:
                    im.text("—")

                # Column 4: G-Factor
                im.table_set_column_index(4)
                g = det_info.get("g_factor", 1.0)
                im.text(f"{g:.3f}")

                # Column 5: l1
                im.table_set_column_index(5)
                l1 = det_info.get("l1", 0.0)
                im.text(f"{l1:.2f}")

                # Column 6: l2
                im.table_set_column_index(6)
                l2 = det_info.get("l2", 0.0)
                im.text(f"{l2:.2f}")

            im.end_table()

        im.spacing()

        # ── Microtime Windows Table ─────────────────────────────────────────
        im.text_colored("Excitation / PIE Microtime Windows", (0.9, 0.9, 0.9, 1.0))
        win_table_h = min(120.0, max(75.0, len(windows) * 26.0 + 30.0))
        if im.begin_table("windows_table", 4, table_flags, (0, win_table_h)):
            im.table_setup_column("Window", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Start Ch", im.TableColumnFlags.WIDTH_FIXED, 90.0)
            im.table_setup_column("Stop Ch", im.TableColumnFlags.WIDTH_FIXED, 90.0)
            im.table_setup_column("Width (Chs)", im.TableColumnFlags.WIDTH_FIXED, 95.0)
            im.table_headers_row()

            for win_name, win_bounds in windows.items():
                im.table_next_row()
                im.table_set_column_index(0)
                im.text_colored(win_name, (0.35, 0.75, 1.0, 1.0))

                start = win_bounds[0] if len(win_bounds) > 0 else 0
                stop = win_bounds[1] if len(win_bounds) > 1 else 0
                width_chs = max(0, stop - start)

                im.table_set_column_index(1)
                im.text(f"{start}")

                im.table_set_column_index(2)
                im.text(f"{stop}")

                im.table_set_column_index(3)
                im.text(f"{width_chs}")

            im.end_table()

        im.spacing()

        # ── Timing & Acquisition Parameters ─────────────────────────────────
        im.text_colored("TTTR Reading & Laser Timing", (0.9, 0.9, 0.9, 1.0))
        im.align_text_to_frame_padding()

        col_x = 180.0
        im.text("Excitation Period:")
        im.same_line(col_x)
        period = reading.get("excitation_period", 8000)
        im.text_colored(f"{period} channels", (0.85, 0.85, 0.85, 1.0))

        im.text("Microtime Binning:")
        im.same_line(col_x)
        binning = reading.get("micro_time_binning", 1)
        im.text_colored(f"{binning}", (0.85, 0.85, 0.85, 1.0))

        im.text("File Format:")
        im.same_line(col_x)
        ftype = reading.get("file_type", "PTO / TTTR")
        im.text_colored(f"{ftype}", (0.85, 0.85, 0.85, 1.0))

    def _draw_details(self, box: tuple[float, float, float, float]) -> None:
        """Draw educational guidance explaining why step 0 is the foundation."""
        im.text_colored("Why Step 0: Setup Selection?", (0.35, 0.75, 1.0, 1.0))
        im.spacing()

        im.text_wrapped(
            "Single-molecule burst analysis depends fundamentally on how the physical "
            "detectors (SPADs / APDs) and excitation laser pulses are routed to TTTR channels."
        )
        im.spacing()

        im.text_colored("Channel Mapping Overview:", (0.9, 0.9, 0.9, 1.0))
        im.text_wrapped("• Hardware Routing: Assigns photon channel numbers to detectors.")
        im.text_wrapped(
            "• PIE / ALEX Windows: Separates prompt and delayed laser excitation pulses."
        )
        im.text_wrapped(
            "• G-Factor & Corrections: Per-detector polarization & detection efficiency."
        )

        im.spacing()
        im.separator()
        im.spacing()

        im.text_colored("Downstream Pipeline Propagation:", (0.4, 0.85, 0.5, 1.0))
        im.text_wrapped("• 1. Data Selection: Validates raw TTTR files against channel bounds.")
        im.text_wrapped("• 2. Burst Selection: Directs dual-channel burst search and thresholding.")
        im.text_wrapped("• 4. BVA: Measures donor-acceptor variance per channel.")
        im.text_wrapped("• 6/8. Burst MLE: Fits donor and acceptor fluorescence lifetimes.")
        im.text_wrapped("• IRF & Background: Deconvolves instrument response per detector.")

    def _draw_summary(self, box: tuple[float, float, float, float]) -> None:
        """Draw status confirmation and pipeline advance button."""
        detectors = self.selected_setup_data.get("detectors", {})
        windows = self.selected_setup_data.get("windows", {})

        im.text_colored("Configuration Status:", (0.4, 0.9, 0.4, 1.0))
        im.bullet_text(f"Selected Setup: {self.selected_setup_name}")
        im.bullet_text(f"Detectors Configured: {len(detectors)}")
        im.bullet_text(f"PIE Windows Defined: {len(windows)}")

        im.spacing()
        im.separator()
        im.spacing()

        if self.selected_setup_name and detectors:
            im.text_colored("✓ Setup ready for pipeline execution", (0.35, 0.85, 0.45, 1.0))
            im.spacing()
            if im.button("Proceed to 1. Data Selection ➔", (box[2] - 20.0, 32.0)):
                tool = getattr(self.widget, "tool", None)
                if tool is not None and hasattr(tool, "show_panel_by_role"):
                    self.sync_to_tool()
                    tool.show_panel_by_role("data")
        else:
            im.text_colored(
                "Please select a valid detector setup to continue.", (0.9, 0.4, 0.4, 1.0)
            )

    def _open_channel_wizard(self) -> None:
        """Open the DetectorWizard dialog to allow full custom channel definition."""
        try:
            from chisurf.gui.widgets.wizard.tttr_channeldefinition.tttr_channel_definition import (
                DetectorWizard,
            )

            wiz = DetectorWizard(parent=self.widget)
            wiz.exec_()
            self.refresh_setups()
            self.sync_to_tool()
        except Exception as exc:
            logger.warning(f"Could not open DetectorWizard: {exc}")


class BurstSetupSelectionApp(ImApp):
    """The EMTK ImApp for TTTR Detector Setup Selection."""

    def __init__(self, widget: BurstSetupSelectionWidget) -> None:
        self.widget = widget
        self.setup_gui = BurstSetupSelectionGui(
            widget=widget,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.setup_gui.item_rects

    @property
    def on_used(self) -> Callable[[str], None] | None:
        return self.setup_gui.on_used

    @on_used.setter
    def on_used(self, cb: Callable[[str], None] | None) -> None:
        self.setup_gui.on_used = cb

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.setup_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.setup_gui.show_help()

    def _render(self) -> None:
        self.setup_gui.draw()
