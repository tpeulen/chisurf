"""EMTK immediate-mode UI for Integrated Burst Analysis in ChiSurf.

Hosts the entire burst analysis workflow in a 100% native EMTK interface:
- Left Navigation Rail: Full pipeline (steps 1–8) and side tools with search filter,
  completion badges, description tooltips, and collapsible toggle.
- Top Action & Stepper Bar: Current step title & description, workflow breadcrumb chips
  (raw files, burst count, detector setup), pipeline navigation (Back, Next, Fast-Forward),
  and in-EMTK Help & Tour buttons.
- Bottom Status Bar: Status messages, inline progress bar for running background tasks,
  task cancel button, and pipeline progress indicator.
- Central Area: Seamless direct rendering and input routing to the active step's EMTK view.
- In-EMTK Help & Guided Tour: Embedded `EmTkHelpWindow` and `EmTkGuidedTour` with zero
  external Qt modal dialogs and zero hangs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.im_core import Col
from qtpy import QtCore

from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

if TYPE_CHECKING:
    from .tool import BurstAnalysisTool

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
HEADER_BG = (24, 26, 31, 255)
SIDEBAR_BG = (27, 29, 35, 255)
STATUS_BG = (22, 24, 28, 255)
ITEM_HOVER_BG = (48, 52, 62, 255)
ITEM_ACTIVE_BG = (35, 85, 140, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_ORANGE = (255, 127, 14, 255)
ACCENT_PURPLE = (148, 103, 189, 255)
ACCENT_GRAY = (158, 158, 158, 255)
TEXT_DIM = (160, 160, 160, 255)
TEXT_BRIGHT = (240, 240, 240, 255)


class BurstAnalysisGui:
    """The EMTK immediate-mode GUI for the Burst Analysis workflow shell."""

    def __init__(
        self,
        tool: BurstAnalysisTool,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_guide = on_guide
        self.on_help = on_help

        # Navigation state
        self.sidebar_collapsed: bool = False
        self.search_filter: str = ""
        self.selected_role: str = "setup"

        # Tour and Rect tracking
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        # Floating In-EMTK Help Window
        help_resource = Path(__file__).parent / "help.md"
        self.help_window = EmTkHelpWindow(
            title="Burst Analysis — Help & Reference",
            resource=help_resource,
            owner=self.tool,
            on_start_guide=self.start_guide,
            size=(760.0, 560.0),
        )

        # In-EMTK Guided Tour
        guide_resource = Path(__file__).parent / "guide.json"
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.tool,
        )

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

    def get_layout(self, w: float, h: float) -> tuple[float, float, float, float, float]:
        """Compute dimensions: (nav_w, top_h, status_h, main_w, main_h)."""
        nav_w = 44.0 if self.sidebar_collapsed else 272.0
        top_h = 44.0
        status_h = 28.0
        main_w = max(100.0, w - nav_w)
        main_h = max(100.0, h - top_h - status_h)
        return nav_w, top_h, status_h, main_w, main_h

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        """Draw top bar, left navigation rail, bottom status bar, and overlays."""
        vp = im.get_main_viewport()
        vw, vh = vp.size
        width = float(w or vw or 1000.0)
        height = float(h or vh or 700.0)

        nav_w, top_h, status_h, main_w, main_h = self.get_layout(width, height)

        # 1. Top Header & Action Bar
        self._draw_header(width, top_h)

        # 2. Left Navigation Rail
        self._draw_sidebar(nav_w, top_h, height - top_h - status_h)

        # 3. Bottom Status Bar
        self._draw_status_bar(width, status_h, height - status_h)

        # 4. In-EMTK Help Window Overlay
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        # 5. In-EMTK Tour Overlay
        if self.tour.active:
            self.tour.draw(width, height)

    def _draw_header(self, width: float, height: float) -> None:
        """Top bar displaying current step title, breadcrumbs, stepper, and actions."""
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)

        im.push_style_color(Col.WINDOW_BG, HEADER_BG)
        im.push_style_color(Col.BORDER, PANEL_BORDER)

        if im.begin(
            "##burst_header",
            (0.0, 0.0, width, height),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_SCROLLBAR,
        ):
            current_panel = self._get_panel_by_role(self.selected_role)
            icon = current_panel.get("icon", "📂") if current_panel else "📂"
            name = current_panel.get("name", "Workflow Step") if current_panel else "Workflow Step"
            desc = current_panel.get("description", "") if current_panel else ""

            # Left title & description
            im.set_cursor_pos_x(14.0)
            im.set_cursor_pos_y(10.0)
            im.text_colored(f"{icon} {name}", (1.0, 1.0, 1.0, 1.0))
            if desc and not self.sidebar_collapsed:
                im.same_line()
                im.text_disabled(f"— {desc[:50]}..." if len(desc) > 50 else f"— {desc}")

            # Right-aligned stepper & help buttons
            button_area_w = 360.0
            im.same_line()
            im.set_cursor_pos_x(max(im.get_cursor_pos_x() + 12.0, width - button_area_w))
            im.set_cursor_pos_y(8.0)

            # Stepper buttons
            can_prev = self._can_go_prev()
            if not can_prev:
                im.push_style_color(Col.TEXT, (0.5, 0.5, 0.5, 1.0))
            if im.button("◀ Back") and can_prev:
                self.tool.goto_prev_step()
            self.remember("back_step")
            if not can_prev:
                im.pop_style_color(1)

            im.same_line()
            can_next = self._can_go_next()
            if not can_next:
                im.push_style_color(Col.TEXT, (0.5, 0.5, 0.5, 1.0))
            else:
                im.push_style_color(Col.BUTTON, ACCENT_BLUE)
            if im.button("Next ▶") and can_next:
                self.tool.goto_next_step()
            self.remember("next_step")
            if not can_next:
                im.pop_style_color(1)
            else:
                im.pop_style_color(1)

            im.same_line()
            im.text_disabled("|")
            im.same_line()

            # Fast Forward (Run Pipeline)
            if im.button("⏩ Run"):
                self.track("fast_forward")
                self.tool.fast_forward()
            self.remember("fast_forward")

            im.same_line()
            im.text_disabled("|")
            im.same_line()

            # In-EMTK Guide & Help
            if im.button("Guide"):
                self.start_guide()
            self.remember("guide")

            im.same_line()
            if im.button("? Help"):
                self.show_help()
            self.remember("help")

            im.end()

        im.pop_style_color(2)

    def _draw_sidebar(self, width: float, y_offset: float, height: float) -> None:
        """Left navigation rail with steps 1–8, separator, and side tools."""
        im.set_next_window_pos((0.0, y_offset), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)

        im.push_style_color(Col.WINDOW_BG, SIDEBAR_BG)
        im.push_style_color(Col.BORDER, PANEL_BORDER)

        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE
        if self.sidebar_collapsed:
            flags |= im.WindowFlags.NO_SCROLLBAR

        if im.begin("##burst_sidebar", (0.0, y_offset, width, height), flags):
            # Top rail controls: collapse button & search
            if not self.sidebar_collapsed:
                im.spacing()
                im.push_item_width(width - 50.0)
                changed, new_text = im.input_text_with_hint(
                    "##nav_search", "Search steps...", self.search_filter
                )
                if changed:
                    self.search_filter = new_text
                im.pop_item_width()

                im.same_line()
                if im.button("◀##collapse", (26.0, 22.0)):
                    self.sidebar_collapsed = True
                self.remember("sidebar_toggle")

                im.spacing()
                im.text_disabled("PIPELINE STEPS")
                im.spacing()
            else:
                im.spacing()
                if im.button("▶##expand", (width - 16.0, 24.0)):
                    self.sidebar_collapsed = False
                self.remember("sidebar_toggle")
                im.spacing()
                im.separator()
                im.spacing()

            # Iterate panels
            panels = self.tool.panels

            for idx, panel in enumerate(panels):
                if panel.get("separator"):
                    if not self.sidebar_collapsed:
                        im.spacing()
                        im.separator()
                        im.spacing()
                        im.set_cursor_pos_x(12.0)
                        im.text_disabled("SIDE TOOLS")
                        im.spacing()
                    else:
                        im.spacing()
                        im.separator()
                        im.spacing()
                    continue

                role = str(panel.get("role", ""))
                name = str(panel.get("name", ""))
                icon = str(panel.get("icon", ""))
                desc = str(panel.get("description", ""))

                # Apply search filter
                if self.search_filter:
                    query = self.search_filter.lower()
                    if (
                        query not in name.lower()
                        and query not in desc.lower()
                        and query not in role.lower()
                    ):
                        continue

                is_active = role == self.selected_role

                # Determine status badge for this step
                badge = self._get_step_badge(role)

                # Render Step Item
                self._draw_step_item(
                    idx=idx,
                    role=role,
                    icon=icon,
                    name=name,
                    badge=badge,
                    desc=desc,
                    is_active=is_active,
                    collapsed=self.sidebar_collapsed,
                    width=width,
                )

            im.end()

        im.pop_style_color(2)

    def _draw_step_item(
        self,
        idx: int,
        role: str,
        icon: str,
        name: str,
        badge: str,
        desc: str,
        is_active: bool,
        collapsed: bool,
        width: float,
    ) -> None:
        """Render a single step entry in the navigation rail with strict left alignment."""
        from emtk.im_core import get_current_context

        ctx = get_current_context()

        btn_w = width - 12.0
        btn_h = 28.0
        im.set_cursor_pos_x(6.0)
        box = ctx.layout.row(height=btn_h, width=btn_w)
        label_id = f"step_{role}_{idx}"
        item_id = ctx.get_id(label_id)
        hovered, held, pressed = ctx.button_behavior(box, item_id)

        if pressed:
            self.tool.show_panel_by_role(role)

        # Background highlights
        if is_active:
            ctx.draw.add_rect_filled(
                (box[0], box[1]),
                (box[0] + box[2], box[1] + box[3]),
                (35 / 255, 85 / 255, 140 / 255, 1.0),
                4.0,
            )
            # Left accent strip
            ctx.draw.add_rect_filled(
                (box[0], box[1] + 2.0),
                (box[0] + 3.5, box[1] + box[3] - 2.0),
                (33 / 255, 150 / 255, 243 / 255, 1.0),
                1.5,
            )
        elif hovered:
            ctx.draw.add_rect_filled(
                (box[0], box[1]),
                (box[0] + box[2], box[1] + box[3]),
                (48 / 255, 52 / 255, 62 / 255, 1.0),
                4.0,
            )

        line_h = ctx.p.line_height()
        text_y = box[1] + (box[3] - line_h) * 0.5
        text_col = (
            (1.0, 1.0, 1.0, 1.0)
            if is_active
            else ((0.92, 0.92, 0.92, 1.0) if hovered else (0.82, 0.82, 0.82, 1.0))
        )

        if collapsed:
            t = icon or "•"
            tw, _ = ctx.draw.calc_text_size(t)
            ctx.draw.add_text((box[0] + (box[2] - tw) * 0.5, text_y), text_col, t)
        else:
            # 1. Left-aligned icon
            icon_x = box[0] + 10.0
            if icon:
                ctx.draw.add_text((icon_x, text_y), text_col, icon)

            # 2. Left-aligned label
            label_x = box[0] + 32.0
            disp_name = name
            max_label_w = btn_w - (75.0 if badge else 45.0)
            lw, _ = ctx.draw.calc_text_size(disp_name)
            while lw > max_label_w and len(disp_name) > 6:
                disp_name = disp_name[:-2] + "…"
                lw, _ = ctx.draw.calc_text_size(disp_name)
            ctx.draw.add_text((label_x, text_y), text_col, disp_name)

            # 3. Right-aligned badge
            if badge:
                bw, _ = ctx.draw.calc_text_size(badge)
                badge_x = box[0] + box[2] - bw - 8.0
                badge_col = (0.35, 0.75, 1.0, 1.0) if "opt" in badge else (0.5, 0.85, 0.5, 1.0)
                ctx.draw.add_text((badge_x, text_y), badge_col, badge)

        if desc and hovered:
            im.set_tooltip(f"{name}\n{desc}")

        self.remember(f"panel_{role}", box)
        self.remember(role, box)

    def _draw_status_bar(self, width: float, height: float, y_pos: float) -> None:
        """Bottom status bar with message, progress bar, cancel, and badges."""
        im.set_next_window_pos((0.0, y_pos), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)

        im.push_style_color(Col.WINDOW_BG, STATUS_BG)
        im.push_style_color(Col.BORDER, PANEL_BORDER)

        if im.begin(
            "##burst_status",
            (0.0, y_pos, width, height),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_SCROLLBAR,
        ):
            status_text = getattr(self.tool, "_status_text", "Ready")
            active_task = getattr(self.tool, "_active_task", None)

            # Left: status message
            im.text_colored(f"  {status_text}", (0.8, 0.8, 0.8, 1.0))

            # Inline Progress bar if a task is active
            if active_task is not None and getattr(self.tool, "_status_progress_visible", False):
                im.same_line()
                val = getattr(self.tool, "_status_progress_value", 0)
                max_val = getattr(self.tool, "_status_progress_maximum", 100)
                fraction = float(val) / float(max_val) if max_val > 0 else 0.0
                im.progress_bar(fraction, (180.0, 16.0), f"{int(fraction * 100)}%")

                if getattr(self.tool, "_status_cancel_visible", False):
                    im.same_line()
                    if im.button("Cancel##task_cancel"):
                        active_task.cancel()

            # Right: summary chips
            ctx = self.tool.workflow_context
            chips: list[str] = []
            if ctx.raw_files:
                chips.append(f"📁 {len(ctx.raw_files)} TTTR")
            if ctx.burst_folder:
                n_bur = len(ctx.bur_files)
                chips.append(f"🎯 {n_bur} bursts" if n_bur else "🎯 Bursts Ready")
            if ctx.setup_name:
                chips.append(f"🔬 {ctx.setup_name}")

            if chips:
                chip_str = " | ".join(chips)
                avail_w = im.get_content_region_avail()[0]
                text_w = len(chip_str) * 7.5 + 20.0
                if avail_w > text_w:
                    im.same_line()
                    im.dummy((avail_w - text_w, 1.0))
                    im.same_line()
                    im.text_disabled(f"{chip_str}  ")

            im.end()

        im.pop_style_color(2)

    def _get_panel_by_role(self, role: str) -> dict[str, Any] | None:
        """Find panel metadata dict by role."""
        for p in self.tool.panels:
            if p.get("role") == role:
                return p
        return None

    def _get_step_badge(self, role: str) -> str:
        """Return visual badge indicating status of step."""
        ctx = self.tool.workflow_context
        if role == "setup":
            return "✓" if ctx.setup_name else ""
        if role == "data":
            return f"({len(ctx.raw_files)})" if ctx.raw_files else ""
        if role == "selection":
            if ctx.bur_files:
                return f"({len(ctx.bur_files)})"
            if ctx.burst_folder:
                return "✓"
            return ""
        if role == "fusion":
            return "[opt]"
        if role in ("bva", "two_cde", "mle", "h2mm", "segment_mle"):
            # If burst folder is ready, this step is ready to analyze
            return "•" if ctx.burst_folder else ""
        return ""

    def _can_go_prev(self) -> bool:
        """Check if back stepper can be used."""
        panels = [p for p in self.tool.panels if not p.get("separator")]
        roles = [p.get("role") for p in panels]
        try:
            idx = roles.index(self.selected_role)
            return idx > 0
        except ValueError:
            return False

    def _can_go_next(self) -> bool:
        """Check if forward stepper can be used."""
        panels = [p for p in self.tool.panels if not p.get("separator")]
        roles = [p.get("role") for p in panels]
        try:
            idx = roles.index(self.selected_role)
            return idx < len(roles) - 1
        except ValueError:
            return False


class BurstAnalysisApp(ImApp):
    """The master EMTK ImApp for Integrated Burst Analysis.

    Draws the full shell (sidebar, header, status bar) and delegates central
    drawing and event handling directly to the active step's EMTK ImApp.
    """

    def __init__(self, tool: BurstAnalysisTool) -> None:
        self.tool = tool
        self.analysis_gui = BurstAnalysisGui(
            tool=tool,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render_shell, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.analysis_gui.item_rects

    @property
    def selected_role(self) -> str:
        return self.analysis_gui.selected_role

    @selected_role.setter
    def selected_role(self, role: str) -> None:
        self.analysis_gui.selected_role = role

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.analysis_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.analysis_gui.show_help()

    def _render_shell(self) -> None:
        """Render shell elements (called by ImApp.draw frame)."""
        self.analysis_gui.draw()

    def draw(self, painter: Any, x: float, y: float, w: float, h: float) -> None:
        """Draw shell and composite active step's EMTK app."""
        self._width = float(w)
        self._height = float(h)

        # 1. Draw shell frame
        super().draw(painter, x, y, w, h)

        # 2. Draw active step panel in the central area
        active_app = self.tool.get_active_app()
        if active_app is not None and not self.analysis_gui.help_window.open:
            nav_w, top_h, status_h, main_w, main_h = self.analysis_gui.get_layout(w, h)
            qp = getattr(painter, "_p", None)
            if qp is not None:
                qp.save()
                qp.setClipRect(QtCore.QRectF(x + nav_w, y + top_h, main_w, main_h))
                qp.translate(x + nav_w, y + top_h)
                try:
                    active_app.draw(painter, 0.0, 0.0, main_w, main_h)
                finally:
                    qp.restore()
            else:
                active_app.draw(painter, x + nav_w, y + top_h, main_w, main_h)

    def animating(self) -> bool:
        """Check if shell or active panel requests animation."""
        if super().animating():
            return True
        active_app = self.tool.get_active_app()
        if active_app is not None and callable(getattr(active_app, "animating", None)):
            return bool(active_app.animating())
        return False

    def next_frame_in(self) -> float | None:
        """Compute delay until next frame."""
        parent_delay = super().next_frame_in()
        active_app = self.tool.get_active_app()
        child_delay = None
        if active_app is not None and callable(getattr(active_app, "next_frame_in", None)):
            child_delay = active_app.next_frame_in()

        if parent_delay is None:
            return child_delay
        if child_delay is None:
            return parent_delay
        return min(parent_delay, child_delay)

    # ── Input Event Routing ─────────────────────────────────────────────
    def pointer_press(
        self, x: float, y: float, button: int, modifiers: int = 0, clicks: int = 1
    ) -> None:
        """Route mouse press between shell chrome and active panel."""
        if self.analysis_gui.help_window.open or self.analysis_gui.tour.active:
            super().pointer_press(x, y, button, modifiers, clicks)
            return

        w = getattr(self, "_width", 1000.0)
        h = getattr(self, "_height", 700.0)
        nav_w, top_h, status_h, main_w, main_h = self.analysis_gui.get_layout(w, h)

        # Chrome hit-test
        if x < nav_w or y < top_h or y > (h - status_h):
            super().pointer_press(x, y, button, modifiers, clicks)
        else:
            active_app = self.tool.get_active_app()
            if active_app is not None and hasattr(active_app, "pointer_press"):
                active_app.pointer_press(x - nav_w, y - top_h, button, modifiers, clicks)
            else:
                super().pointer_press(x, y, button, modifiers, clicks)

    def pointer_move(self, x: float, y: float, buttons: int = 0, modifiers: int = 0) -> None:
        """Broadcast pointer move for hover tracking across both shell and active panel."""
        super().pointer_move(x, y, buttons, modifiers)
        w = getattr(self, "_width", 1000.0)
        h = getattr(self, "_height", 700.0)
        nav_w, top_h, status_h, _, _ = self.analysis_gui.get_layout(w, h)

        active_app = self.tool.get_active_app()
        if active_app is not None and hasattr(active_app, "pointer_move"):
            if x >= nav_w and top_h <= y <= (h - status_h):
                active_app.pointer_move(x - nav_w, y - top_h, buttons, modifiers)
            else:
                active_app.pointer_move(-1.0, -1.0, 0, modifiers)

    def pointer_release(self, x: float, y: float, button: int, modifiers: int = 0) -> None:
        """Release mouse button in shell and active panel."""
        super().pointer_release(x, y, button, modifiers)
        w = getattr(self, "_width", 1000.0)
        h = getattr(self, "_height", 700.0)
        nav_w, top_h, status_h, _, _ = self.analysis_gui.get_layout(w, h)

        active_app = self.tool.get_active_app()
        if active_app is not None and hasattr(active_app, "pointer_release"):
            active_app.pointer_release(x - nav_w, y - top_h, button, modifiers)

    def wheel(self, x: float, y: float, steps: float, modifiers: int = 0) -> None:
        """Route scroll wheel between chrome and active panel."""
        w = getattr(self, "_width", 1000.0)
        h = getattr(self, "_height", 700.0)
        nav_w, top_h, status_h, main_w, main_h = self.analysis_gui.get_layout(w, h)

        if x < nav_w or y < top_h or y > (h - status_h):
            super().wheel(x, y, steps, modifiers)
        else:
            active_app = self.tool.get_active_app()
            if active_app is not None and hasattr(active_app, "wheel"):
                active_app.wheel(x - nav_w, y - top_h, steps, modifiers)
            else:
                super().wheel(x, y, steps, modifiers)

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Route keystrokes to search box when focused, or active panel."""
        if self.io.want_capture_keyboard:
            return super().key(key, text, modifiers)
        active_app = self.tool.get_active_app()
        if active_app is not None and hasattr(active_app, "key"):
            consumed = active_app.key(key, text, modifiers)
            if consumed:
                return True
        return super().key(key, text, modifiers)
