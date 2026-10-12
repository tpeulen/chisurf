"""The Burst Variance Analysis (BVA) tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstBvaApp`) over
:class:`~.view_model.BvaViewModel`:
- Left pane: folder input, actions (Run, Restart, Stop, Folder), tabbed settings
  (BVA Settings and Channel Definitions), and status.
- Right pane: BVA 2D plot with static line, scatter bursts, and profile mean ± std error.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

import json
from pathlib import Path
from typing import Any, Callable

from emtk import im, implot
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.im_core import Col, ItemFlags, get_current_context

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import (
    action_caption,
    action_tooltip,
    button_row,
    icon_label,
    window_size,
)

from .view_model import BvaViewModel

__all__ = ["BurstBvaApp", "BurstBvaGui", "WINDOW_BG"]

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)


class BurstBvaGui:
    """The immediate-mode GUI logic and rendering for BVA."""

    INVALID_RANGES = "Invalid microtime range; use increasing start:end pairs."

    def __init__(
        self,
        model: BvaViewModel | None = None,
        on_run: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_save_settings: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else BvaViewModel()
        self.on_run = on_run
        self.on_restart = on_restart
        self.on_stop = on_stop
        self.on_browse = on_browse
        self.on_clear = on_clear
        self.on_save = on_save
        self.on_save_settings = on_save_settings
        self.on_guide = on_guide
        self.on_help = on_help

        self.region_rect: list[float] = [0.2, 0.05, 0.8, 0.35]
        self.selected_settings_tab = "BVA Settings"
        self._folder_text: str | None = None
        self._microtime_text: dict[str, str] = {}
        #: The shared detector editor (``chisurf.emtk.channel_definition``) and the detectors picked from it.
        self.editor: Any = None
        self.donor_detector = ""
        self.acceptor_detector = ""
        self._syncing = False
        self._seen_editor: tuple | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None
        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst Variance Analysis (BVA) — Help & Reference",
            resource=help_resource,
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.model,
            wait_for_controls=True,
        )
        self.on_used = self.tour.notify_used  # the Folder and Run steps wait for their control
        self.model.add_observer(self._on_model_event)

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def _on_model_event(self, event: str) -> None:
        if event == "detector_settings" and self.editor is not None and not self._syncing:
            self._syncing = True  # a workflow hand-off: the editor shows what the model now holds
            try:
                self.editor.load_definition(self._editor_settings())
            finally:
                self._syncing = False
            self._sync_pair(self.editor.model.get_settings(), assign=False)

    # ── the shared detector editor and the FRET pair picked from it ──────
    def _editor_settings(self) -> dict:
        """The definition the editor starts from: the model's donor and acceptor detectors and file type."""
        detectors = {}
        for role in ("donor", "acceptor"):
            detectors[role] = {
                "chs": list(getattr(self.model, f"{role}_channels")),
                "micro_time_ranges": [
                    list(r) for r in getattr(self.model, f"{role}_micro_time_ranges")
                ],
                "g_factor": 1.0,
                "l1": 0.0,
                "l2": 0.0,
            }
        return {
            "windows": {},
            "detectors": detectors,
            "tttr_reading": {
                "file_type": self.model.file_type,
                "macro_time_resolution": 0.0,
                "micro_time_resolution": 0.0,
                "micro_time_binning": 1,
            },
        }

    def attach_editor(self, host_app: Any) -> None:
        """Create the shared detector editor (the Qt tool's Channels tab) and list the saved setups."""
        from chisurf.core.setup_channel_definition import ChannelDefinition
        from chisurf.emtk.channel_definition import ChannelDefinitionWidget

        self.editor = ChannelDefinitionWidget(
            model=ChannelDefinition(self._editor_settings()),
            on_changed=self._editor_changed,
            host_app=host_app,
        )
        self.editor.on_used = self.track
        self.editor.toolbar.reload(open_last=False)
        settings = self.editor.model.get_settings()
        self._seen_editor = (
            json.dumps(settings.get("detectors"), sort_keys=True, default=str),
            (settings.get("tttr_reading") or {}).get("file_type"),
        )
        self.donor_detector, self.acceptor_detector = self._default_pair(
            list(settings["detectors"])
        )

    @staticmethod
    def _default_pair(names: list[str]) -> tuple[str, str]:
        """The donor and acceptor among *names*: by green/red naming, else the first two."""
        donor = next((n for n in names if "green" in n.lower() or "donor" in n.lower()), "")
        acceptor = next((n for n in names if "red" in n.lower() or "acceptor" in n.lower()), "")
        donor = donor or (names[0] if names else "")
        acceptor = acceptor or next((n for n in names if n != donor), donor)
        return donor, acceptor

    def _editor_changed(self, settings: dict) -> None:
        """A detector, window or setup of the editor changed: refresh the pair choices and the model."""
        if self._syncing:
            return
        # An event that carries no change of detectors or file type must not overwrite routing typed by hand.
        seen = (
            json.dumps((settings or {}).get("detectors"), sort_keys=True, default=str),
            ((settings or {}).get("tttr_reading") or {}).get("file_type"),
        )
        changed, self._seen_editor = seen != self._seen_editor, seen
        self._sync_pair(settings, assign=changed)

    def _sync_pair(self, settings: dict, assign: bool) -> None:
        """Keep the chosen donor/acceptor detectors valid for *settings*; push them into the model when *assign*."""
        names = list((settings or {}).get("detectors") or {})
        default_donor, default_acceptor = self._default_pair(names)
        if self.donor_detector not in names:
            self.donor_detector = default_donor
        if self.acceptor_detector not in names:
            self.acceptor_detector = default_acceptor
        if assign:
            self._assign_pair(settings)

    def _assign_pair(self, settings: dict) -> None:
        """Take the picked detectors' channels and micro-time gates, and the file type, into the model."""
        detectors = (settings or {}).get("detectors") or {}
        for role, name in (("donor", self.donor_detector), ("acceptor", self.acceptor_detector)):
            det = detectors.get(name)
            if det is None:
                continue
            chs = ",".join(str(c) for c in det.get("chs", []))
            ranges = [tuple(r) for r in (det.get("micro_time_ranges") or [])] or [(0, 32768)]
            setattr(self.model, f"{role}_channels_text", chs)
            setattr(self.model, f"{role}_micro_time_ranges", ranges)
            self._microtime_text.pop(role, None)
        file_type = ((settings or {}).get("tttr_reading") or {}).get("file_type")
        if file_type and file_type != "auto" and file_type != self.model.file_type:
            self.model.set_file_type(file_type)
        self.model.notify("channel")

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        """Draw the BVA GUI into (w, h) display pixels."""
        im.dock_space_over_viewport(1)

        vp = im.get_main_viewport()
        vw, vh = vp.size
        width = float(w or vw or 800.0)
        height = float(h or vh or 600.0)

        left_w = min(max(340.0, width * 0.34), 440.0)
        right_w = max(width - left_w - 12.0, 200.0)

        # ── Left pane: Controls & Settings (Dockable) ───────────────────
        im.set_next_window_pos((4.0, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((left_w, height - 8.0), im.Cond.ALWAYS)
        if im.begin("BVA Controls"):
            self._draw_action_buttons()
            im.spacing()
            self._draw_folder_input(left_w - 16.0)
            im.spacing()

            # The settings tabs scroll inside the pane: an emtk window has no scrollbar, and the channel
            # and detector editors are taller than the window.
            im.begin_child("bva_settings_body")
            if im.begin_tab_bar("bva_settings_tabs"):
                opened = im.begin_tab_item("BVA Settings")
                im.set_item_tooltip(
                    tr("Adjust analysis and display parameters.")
                )  # selected or not
                if opened:
                    self.selected_settings_tab = "BVA Settings"
                    self.remember("BVA Settings")
                    self._draw_bva_parameters()
                    im.end_tab_item()
                else:
                    self.remember("BVA Settings")

                opened = im.begin_tab_item("Channel Definitions")
                im.set_item_tooltip(tr("Set detector routing and microtime gates."))
                if opened:
                    self.selected_settings_tab = "Channel Definitions"
                    self.remember("Channel Definitions")
                    self._draw_channel_definitions()
                    im.end_tab_item()
                else:
                    self.remember("Channel Definitions")

                opened = im.begin_tab_item("Detectors")
                im.set_item_tooltip(
                    tr(
                        "The shared detector editor: setups, reading routine, PIE windows and detectors."
                    )
                )
                if opened:
                    self.selected_settings_tab = "Detectors"
                    self.remember("Detectors")
                    if self.editor is not None:
                        self.editor.draw()
                        self.item_rects.update(
                            {f"detectors.{k}": v for k, v in self.editor.item_rects.items()}
                        )
                    im.end_tab_item()
                else:
                    self.remember("Detectors")
                im.end_tab_bar()

            im.spacing()
            self._draw_status()
            im.end_child()
            self.remember("controls", (4.0, 4.0, left_w, height - 8.0))

        im.end()

        # ── Right pane: Plot (Dockable) ──────────────────────────────────
        plots_x = left_w + 8.0
        im.set_next_window_pos((plots_x, 4.0), im.Cond.ALWAYS)
        im.set_next_window_size((right_w, height - 8.0), im.Cond.ALWAYS)
        if im.begin("BVA Plot Window"):
            if im.begin_tab_bar("bva_plot_tabs"):
                opened = im.begin_tab_item("Plot")
                im.set_item_tooltip(
                    tr(
                        "Std of the proximity ratio per burst against its mean, with the static line."
                    )
                )
                if opened:
                    self.remember("Plot")
                    avail_w, avail_h = im.get_content_region_avail()
                    avail_h = max(avail_h, 250.0)
                    self._draw_plot(avail_w, avail_h)
                    im.end_tab_item()
                else:
                    self.remember("Plot")
                im.end_tab_bar()
            self.remember("PlotWindow", (plots_x, 4.0, right_w, h - 8.0))

        im.end()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        if self.tour.active:
            self.tour.draw(width, height)

    def _draw_action_buttons(self) -> None:
        """The actions in three wrapped rows: the run controls, the saves, then guide and help."""
        running = bool(self.model.is_running)
        attention = bool(
            getattr(self.model, "restart_attention", False)
        )  # the Qt tool's flag_attention
        pressed = button_row(
            [
                {
                    "label": action_caption("run"),
                    "key": "run",
                    "keys": ("toolAction_run",),
                    "enabled": not running,
                    "colours": (ACCENT_GREEN, (56, 180, 77, 255), (36, 140, 57, 255)),
                    "tip": "Compute the per-burst standard deviation of the proximity ratio (BVA) for the loaded bursts.",
                },
                {
                    "label": action_caption("restart"),
                    "key": "restart",
                    "keys": ("toolAction_restart",),
                    "enabled": not running,
                    "colours": ((200, 120, 20, 255), (220, 140, 40, 255), (180, 100, 10, 255))
                    if attention
                    else None,
                    "tip": "Reset the analysis state and recompute from scratch.",
                },
                {
                    "label": icon_label("⏹", "Stop"),
                    "key": "stop",
                    "keys": ("toolAction_stop",),
                    "enabled": running,
                    "colours": (ACCENT_RED, (234, 59, 60, 255), (180, 20, 20, 255))
                    if running
                    else None,
                    "tip": "Stop the running BVA computation."
                    if running
                    else "Nothing is running; a BVA computation in progress can be stopped here.",
                },
                {
                    "label": icon_label("📁", "Folder"),
                    "key": "folder",
                    "tip": "Browse for the folder containing the burst analysis files.",
                },
            ],
            remember=self.remember,
        )
        if pressed == "run":
            self.track("toolAction_run")
            self.track("run")
            if callable(self.on_run):
                self.on_run()
        elif pressed == "restart":
            self.track("toolAction_restart")
            self.track("restart")
            if callable(self.on_restart):
                self.on_restart()
        elif pressed == "stop":
            self.track("toolAction_stop")
            self.track("stop")
            if callable(self.on_stop):
                self.on_stop()
        elif pressed == "folder":
            self.track("folder")
            if callable(self.on_browse):
                self.on_browse()

        # These actions previously lived only in the hidden Qt toolbar.
        pressed = button_row(
            [
                {
                    "label": icon_label("🗑", "Clear"),
                    "key": "clear",
                    "tip": "Clear the plotted BVA results and invalidate the cached analysis.",
                },
                {
                    "label": icon_label("💾", "Save plot"),
                    "key": "save_plot",
                    "tip": "Save the displayed BVA plot as a PNG image.",
                },
                {
                    "label": icon_label("⚙", "Save defaults"),
                    "key": "save_defaults",
                    "tip": "Save the current analysis and display settings as defaults.",
                },
            ],
            remember=self.remember,
        )
        actions = {
            "clear": self.on_clear,
            "save_plot": self.on_save,
            "save_defaults": self.on_save_settings,
        }
        action = actions.get(pressed)
        if callable(action):
            action()
        pressed = button_row(
            [
                {
                    "label": action_caption("guide"),
                    "key": "guide",
                    "tip": action_tooltip("guide"),
                },
                {
                    "label": action_caption("help"),
                    "key": "help",
                    "tip": action_tooltip("help"),
                },
            ],
            remember=self.remember,
        )
        if pressed == "guide":
            self.track("guide")
            self.start_guide()
        elif pressed == "help":
            self.track("help")
            self.show_help()

    def _draw_folder_input(self, width: float) -> None:
        """Folder path input."""
        im.text(tr("Burst folder:"))
        current = str(self.model.analysis_folder or "")
        # What is typed is kept as typed: the model holds a ``Path``, which drops a trailing "/" and so ate every
        # separator the moment it was typed. The model's value wins as soon as it differs from what was typed
        # (a dialog, a drop, a restored default).
        typed = self._folder_text
        if typed is None or (str(Path(typed)) if typed.strip() else "") != current:
            typed = self._folder_text = current
        changed, text = im.input_text("##folder_path", typed, hint=tr("Burst analysis folder …"))
        im.set_item_tooltip(
            tr("Path to the burst analysis folder; type a path or use Folder to browse.")
        )
        self.remember("folder_path")
        if changed:
            self._folder_text = text
            self.model.set_folder(text)

    def _draw_bva_parameters(self) -> None:
        """Draw BVA parameter controls."""
        # A drag reports every step (``LIVE_EDIT_ON_INPUT``): without the flag emtk reports a drag only on release,
        # with the value the model already had, so dragging a field changed nothing.
        im.push_item_flag(ItemFlags.LIVE_EDIT_ON_INPUT, True)
        try:
            self._draw_bva_parameter_fields()
        finally:
            im.pop_item_flag()

    def _draw_bva_parameter_fields(self) -> None:
        im.spacing()
        im.text_colored((200, 210, 230, 255), "Analysis Parameters")

        # Window length
        col_x = 175.0
        im.align_text_to_frame_padding()
        im.text(tr("Min window length (s):"))
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, wl = im.drag_float(
            "##window_length", self.model.window_length, 0.001, 0.0001, 10.0, "%.4f s"
        )
        im.set_item_tooltip(
            tr("Minimum window length in seconds used to slice bursts into photon subsets.")
        )
        self.remember("window_length")
        if changed:
            self.model.window_length = max(0.0001, float(wl))
            self.model.notify("param")

        # Photons per slice
        im.align_text_to_frame_padding()
        im.text(tr("Photons per slice:"))
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, pps = im.drag_float(
            "##photons_per_slice", float(self.model.photons_per_slice), 1.0, 1.0, 500.0, "%.0f"
        )
        im.set_item_tooltip(
            tr("Number of photons per slice when splitting bursts for the variance analysis.")
        )
        self.remember("photons_per_slice")
        if changed:
            self.model.photons_per_slice = max(1, int(round(pps)))
            self.model.notify("param")

        im.spacing()
        im.text_colored((200, 210, 230, 255), "Display Options")

        # Bins
        im.align_text_to_frame_padding()
        im.text(tr("Bins X:"))
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, bx = im.drag_float("##bins_x", float(self.model.bins_x), 1.0, 10.0, 500.0, "%.0f")
        im.set_item_tooltip(tr("Number of histogram bins along the mean proximity-ratio axis."))
        self.remember("bins_x")
        if changed:
            self.model.bins_x = max(10, int(round(bx)))
            self.model.notify("bins")

        im.align_text_to_frame_padding()
        im.text(tr("Bins Y:"))
        im.same_line(col_x)
        im.set_next_item_width(120)
        changed, by = im.drag_float("##bins_y", float(self.model.bins_y), 1.0, 10.0, 500.0, "%.0f")
        im.set_item_tooltip(tr("Number of histogram bins along the standard-deviation axis."))
        self.remember("bins_y")
        if changed:
            self.model.bins_y = max(10, int(round(by)))
            self.model.notify("bins")

        # Toggles
        if im.checkbox(tr("Show static line"), self.model.show_static_line)[0]:
            self.model.show_static_line = not self.model.show_static_line
            self.model.notify("display")
        im.set_item_tooltip(tr("Overlay the shot-noise limited static line on the BVA plot."))
        self.remember("show_static_line")

        if im.checkbox(tr("Auto update"), self.model.auto_update)[0]:
            self.model.auto_update = not self.model.auto_update
            self.model.notify("display")
        im.set_item_tooltip(tr("Recompute the BVA automatically whenever a parameter changes."))
        self.remember("auto_update")

    @staticmethod
    def _parse_ranges(text: str) -> list[tuple[int, int]] | None:
        """``"10:20, 30:40"`` as ``[(10, 20), (30, 40)]``; ``None`` unless every pair is increasing start:end."""
        try:
            parsed = [tuple(int(v.strip()) for v in part.split(":")) for part in text.split(",")]
        except ValueError:
            return None
        if not parsed or any(len(p) != 2 or p[0] < 0 or p[1] <= p[0] for p in parsed):
            return None
        return [(pair[0], pair[1]) for pair in parsed]

    def _draw_pair_assignment(self) -> None:
        """Setup, donor detector and acceptor detector: choose them, do not type routing numbers."""
        if self.editor is None:
            return
        from chisurf.emtk.channel_setup_bar import UNSAVED

        im.text_colored((200, 210, 230, 255), tr("FRET Pair Assignment"))
        bar = self.editor.toolbar
        setups = [UNSAVED, *bar.names]
        index = setups.index(bar.selected) if bar.selected in setups else 0
        im.text(tr("Setup:"))
        changed, picked = im.combo("##bva_setup", index, [tr(setups[0]), *setups[1:]])
        im.set_item_tooltip(
            tr(
                "Choose a saved detector setup; its detectors become the donor and acceptor choices."
            )
        )
        self.remember("bva_setup")
        if changed:
            bar.select("" if picked == 0 else setups[picked])
            self._sync_pair(self.editor.model.get_settings(), assign=True)
            self.track("bva_setup")
        names = list(self.editor.model.get_settings().get("detectors") or {})
        for role, label, tip in (
            (
                "donor",
                "Donor detector:",
                "The detector whose photons are the donor channel (I_DD, I_DA).",
            ),
            (
                "acceptor",
                "Acceptor detector:",
                "The detector whose photons are the acceptor channel.",
            ),
        ):
            current = getattr(self, f"{role}_detector")
            im.text(tr(label))
            changed, picked = im.combo(
                f"##bva_{role}_detector", names.index(current) if current in names else 0, names
            )
            im.set_item_tooltip(tr(tip))
            self.remember(f"{role}_detector")
            if changed and names:
                setattr(self, f"{role}_detector", names[picked])
                self._assign_pair(self.editor.model.get_settings())
                self.track(f"{role}_detector")

    def _draw_channel_definitions(self) -> None:
        """Draw detector channel controls."""
        im.spacing()
        self._draw_pair_assignment()
        im.spacing()
        opened = im.collapsing_header(tr("Manual routing"), im.TreeNodeFlags.DEFAULT_OPEN)
        im.set_item_tooltip(
            tr(
                "Type the donor and acceptor routing channels by hand instead of picking a detector pair."
            )
        )
        self.remember("manual_routing")
        if not opened:
            return
        im.text_colored((200, 210, 230, 255), "Detector Routing")

        im.text(tr("Donor routing channels:"))
        changed, donor = im.input_text("##donor_ch", self.model.donor_channels_text, hint="0,8")
        im.set_item_tooltip(
            tr("Comma-separated TTTR routing channels assigned to the donor (e.g. 0,8).")
        )
        self.remember("donor_channels")
        if changed:
            self.model.donor_channels_text = donor
            self.model.notify("channel")

        im.text(tr("Acceptor routing channels:"))
        changed, acc = im.input_text("##acceptor_ch", self.model.acceptor_channels_text, hint="1,9")
        im.set_item_tooltip(
            tr("Comma-separated TTTR routing channels assigned to the acceptor (e.g. 1,9).")
        )
        self.remember("acceptor_channels")
        if changed:
            self.model.acceptor_channels_text = acc
            self.model.notify("channel")

        for name, label in (
            ("donor", "Donor microtime ranges:"),
            ("acceptor", "Acceptor microtime ranges:"),
        ):
            im.text(label)
            ranges = getattr(self.model, f"{name}_micro_time_ranges")
            # What is typed is kept as typed until the model differs from it: re-formatting the model's ranges
            # every frame reverted each half-typed (invalid) state, so no range could be typed at all.
            typed = self._microtime_text.get(name)
            if typed is None or self._parse_ranges(typed) not in (ranges, None):
                typed = self._microtime_text[name] = ", ".join(f"{lo}:{hi}" for lo, hi in ranges)
            changed, text = im.input_text(f"##{name}_microtime", typed, hint="0:32768")
            im.set_item_tooltip(
                tr(
                    "Microtime gates in channel bins, written as start:end pairs separated by commas."
                )
            )
            self.remember(f"{name}_microtime")
            if changed:
                self._microtime_text[name] = text
                parsed = self._parse_ranges(text)
                if parsed is None:
                    self.model.status_text = self.INVALID_RANGES
                else:
                    if self.model.status_text == self.INVALID_RANGES:
                        self.model.status_text = (
                            "Ready"  # the message was about the half-typed value
                        )
                    setattr(self.model, f"{name}_micro_time_ranges", parsed)
                    self.model.notify("channel")

        im.text(tr("File type:"))
        changed, ft = im.input_text("##file_type", self.model.file_type, hint=tr("SPC-130"))
        im.set_item_tooltip(tr("TTTR file type of the source measurements (e.g. SPC-130)."))
        self.remember("file_type")
        if changed:
            self.model.set_file_type(ft)

    def _draw_status(self) -> None:
        """Status readout."""
        if self.model.status_text:
            im.separator()
            im.text_wrapped(self.model.status_text)

    def _draw_plot(self, w: float, h: float) -> None:
        """Plot the computed BVA results."""
        origin = im.get_cursor_screen_pos()
        plot_data = self.model.get_plot_data() or {}

        if implot.begin_plot("Burst Variance Analysis##bva_plot", (w, h)):
            implot.setup_axes("Mean Proximity Ratio", "Std Proximity Ratio")
            implot.setup_axis_limits(implot.AXIS_X1, -0.05, 1.05)
            implot.setup_axis_limits(implot.AXIS_Y1, -0.01, 0.44)

            # Static line
            if self.model.show_static_line and "static_x" in plot_data:
                implot.set_next_line_style((255, 107, 107, 255), 2.5)
                implot.plot_line("Static line", plot_data["static_x"], plot_data["static_y"])

            # Data
            if plot_data.get("has_data"):
                # Scatter of bursts
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 3.0, fill=(31, 119, 180, 110))
                implot.plot_scatter("Bursts", plot_data["scatter_x"], plot_data["scatter_y"])

                # Profile mean
                prof_x = plot_data.get("profile_x")
                prof_y = plot_data.get("profile_mean")
                prof_sd = plot_data.get("profile_sd")
                if prof_x is not None and len(prof_x) > 0:
                    implot.set_next_line_style((0, 255, 255, 255), 2.0)
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, fill=(0, 255, 255, 220))
                    implot.plot_line("Profile mean", prof_x, prof_y)

                    if prof_sd is not None and len(prof_sd) > 0:
                        implot.set_next_error_bar_style((0, 255, 255, 160))
                        implot.plot_error_bars("##profile_err", prof_x, prof_y, prof_sd)

            # Interactive draggable region
            r_res = implot.drag_rect(
                0,
                float(self.region_rect[0]),
                float(self.region_rect[1]),
                float(self.region_rect[2]),
                float(self.region_rect[3]),
                col=(46, 117, 182, 60),
            )
            if r_res.modified:
                self.region_rect = [
                    min(r_res.x_min, r_res.x_max),
                    min(r_res.y_min, r_res.y_max),
                    max(r_res.x_min, r_res.x_max),
                    max(r_res.y_min, r_res.y_max),
                ]
            implot.tag_x(self.region_rect[0], (90, 160, 240, 255), f"E: {self.region_rect[0]:.2f}")
            implot.tag_x(self.region_rect[2], (90, 160, 240, 255), f"E: {self.region_rect[2]:.2f}")
            implot.tag_y(
                self.region_rect[3], (90, 160, 240, 255), f"Std: {self.region_rect[3]:.2f}"
            )

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                    if "min" in data and "max" in data:
                        self.region_rect[0] = float(data["min"])
                        self.region_rect[2] = float(data["max"])
                except Exception:
                    pass
            im.end_drag_drop_target()

        self.remember("bva_plot", (origin[0], origin[1], w, h))


class BurstBvaApp(ImApp):
    """The EMTK App for Burst Variance Analysis (BVA)."""

    def __init__(
        self,
        model: BvaViewModel | None = None,
        on_run: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_save_settings: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        primary = json.loads(
            Path(__file__).with_name("window.view.json").read_text(encoding="utf-8")
        )
        self.window_size = window_size(primary, (1100, 720))
        self.controller = None
        if all(callback is None for callback in (on_run, on_restart, on_stop, on_browse, on_clear)):
            from .controller import BvaController

            model = model if model is not None else BvaViewModel()
            self.controller = BvaController(model)
            on_run, on_restart = self.controller.run, self.controller.restart
            on_stop, on_browse = self.controller.stop, self.controller.browse
            on_clear = self.controller.clear
            on_save, on_save_settings = self.controller.save_plot, self.controller.save_settings
        self.bva_gui = BurstBvaGui(
            model=model,
            on_run=on_run,
            on_restart=on_restart,
            on_stop=on_stop,
            on_browse=on_browse,
            on_clear=on_clear,
            on_save=on_save,
            on_save_settings=on_save_settings,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.bva_gui.model
        self.item_rects = self.bva_gui.item_rects
        self._size = (1200, 800)
        super().__init__(gui=self._render)
        self.bva_gui.attach_editor(self)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.bva_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.bva_gui.show_help()

    def close(self) -> None:
        """Cancel pending work and release the analysis executor."""
        if self.controller is not None:
            self.controller.close()
        if self.bva_gui.editor is not None:
            self.bva_gui.editor.close()

    def draw(self, painter, x, y, w, h) -> None:
        super().draw(painter, x, y, w, h)
        self._size = (max(1, int(w)), max(1, int(h)))
        controller = self.controller
        if controller is not None and controller.pending_export is not None:
            # Outside the frame: the picture of the window, as the Qt tool's host grab.
            path = controller.pending_export
            controller.pending_export = None
            controller.write_window_png(self, path, self._size)

    def files_dropped(self, paths) -> bool:
        """A dropped burst folder or container becomes the input; anything else is reported."""
        if self.controller is None:
            return False
        self.controller.on_paths_dropped(list(paths))
        return bool(paths)

    def _render(self) -> None:
        if self.controller is not None:
            self.controller.poll()
            if self.controller.running:  # look again in 0.1 s while BVA runs
                ctx = get_current_context()
                ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        if self.bva_gui.editor is not None:
            self.bva_gui.editor.poll()
        self.bva_gui.draw(float(w), float(h))
        if self.bva_gui.editor is not None:
            self.bva_gui.editor.draw_dialogs((0.0, 0.0, float(w), float(h)))
        if self.controller is not None:
            self.controller.draw_dialog((0.0, 0.0, float(w), float(h)))


def create_app(**kwargs):
    """Create the toolkit-free plugin control."""
    return BurstBvaApp(**kwargs)
