"""Reusable in-EMTK Help Window and Guided Tour.

Provides rich, responsive Help and Step-by-Step Guided Tours completely inside
the EMTK immediate-mode canvas. Zero external Qt dialogs, zero modal event loops,
and zero separate windows that could cause OpenGL context lockups or hangs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.dialog_window import DialogWindow
from emtk.im_core import Col
from emtk.keys import KEY_ESCAPE

logger = logging.getLogger(__name__)


def _clean_html_text(text: str) -> str:
    """Convert common HTML formatting like <br/> and <b> to plain text."""
    s = re.sub(r"<\s*br\s*/?>|<\s*p\s*/?>", "\n", text, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


ACCENT_BLUE = (0.4, 0.8, 1.0, 1.0)
ACCENT_GREEN = (46, 160, 67, 255)
TEXT_WHITE = (0.95, 0.95, 0.95, 1.0)
TEXT_MUTED = (0.65, 0.7, 0.75, 1.0)
BORDER_BLUE = (70, 140, 240, 255)
BORDER_GREEN = (56, 210, 80, 255)


def resolve_resource_file(resource: str | Path, owner: Any = None) -> Path | None:
    """Resolve a help.md or guide.json resource path."""
    if not resource:
        return None
    path = Path(resource)
    if path.is_file():
        return path
    if path.is_absolute():
        return None

    bases: list[Path] = []
    if owner is not None:
        view_json = getattr(owner, "_view_json", None)
        if view_json:
            bases.append(Path(view_json).parent)
        mod_name = getattr(type(owner), "__module__", "")
        if mod_name:
            import sys

            mod = sys.modules.get(mod_name)
            if mod and getattr(mod, "__file__", None):
                bases.append(Path(mod.__file__).parent)
    bases.append(Path.cwd())

    for base in bases:
        cand = base / path
        if cand.is_file():
            return cand
    return None


def _safe_request_frame() -> None:
    """Request an EMTK frame if a context is active."""
    try:
        ctx = im.get_current_context()
        if ctx:
            ctx.request_frame()
    except Exception:
        pass


class EmTkHelpWindow:
    """A floating, movable Help Window rendered 100% inside EMTK."""

    def __init__(
        self,
        title: str = "Help & Reference",
        resource: str | Path | None = None,
        text: str = "",
        owner: Any = None,
        on_start_guide: Callable[[], None] | None = None,
        size: tuple[float, float] = (720.0, 540.0),
        categories: list[tuple[str, list[str]]] | None = None,
    ) -> None:
        self.title = title
        self.resource = resource
        self.owner = owner
        self.on_start_guide = on_start_guide
        self.size = size
        self.open = False
        self.active_category = "All"
        self.dlg = DialogWindow(title, size=size, key=f"help_{title}")

        # Parsed help content: list of (heading, content_lines)
        self.sections: list[tuple[str, list[str]]] = []
        if categories:
            self.sections = list(categories)
        else:
            raw_text = text
            if not raw_text and resource:
                resolved = resolve_resource_file(resource, owner)
                if resolved and resolved.is_file():
                    try:
                        raw_text = resolved.read_text(encoding="utf-8")
                    except Exception as exc:
                        logger.warning("Could not read help resource %s: %s", resolved, exc)
            self._parse_markdown(raw_text or "No documentation available.")

    def _parse_markdown(self, raw_text: str) -> None:
        """Parse raw markdown into major sections."""
        lines = raw_text.splitlines()
        curr_heading = "Overview"
        curr_lines: list[str] = []
        parsed: list[tuple[str, list[str]]] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                # Heading
                if curr_lines:
                    parsed.append((curr_heading, curr_lines))
                    curr_lines = []
                curr_heading = stripped.lstrip("#").strip()
            else:
                curr_lines.append(line)

        if curr_lines or not parsed:
            parsed.append((curr_heading, curr_lines))

        self.sections = parsed

    def show(self) -> None:
        """Show the help window inside the EMTK canvas."""
        self.open = True
        self.active_category = "All"
        self.dlg.show()
        _safe_request_frame()

    def hide(self) -> None:
        """Hide the help window."""
        self.open = False
        self.dlg.hide()
        _safe_request_frame()

    def close(self) -> None:
        """Alias for hide()."""
        self.hide()

    def toggle(self) -> None:
        """Toggle help window visibility."""
        if self.open:
            self.hide()
        else:
            self.show()

    def draw(self, frame: tuple[float, float, float, float]) -> None:
        """Render the help window over the given frame rect (0, 0, w, h)."""
        if not self.open:
            return

        ctx = im.get_current_context()
        fx, fy, fw, fh = frame

        # Translucent backdrop to dim the background behind the dialog
        ctx.draw.add_rect_filled((fx, fy), (fx + fw, fy + fh), (0, 0, 0, 110))

        pressed = self.dlg.begin(frame)

        # Header controls
        im.align_text_to_frame_padding()
        im.text_colored(self.title, ACCENT_BLUE)

        if callable(self.on_start_guide):
            im.same_line()
            im.push_style_color(Col.BUTTON, ACCENT_GREEN)
            if im.button("Start Guided Tour##help"):
                self.hide()
                self.on_start_guide()
            im.pop_style_color()

        im.same_line()
        if im.button("Close##help_top"):
            pressed = "close"

        im.separator()

        # Category pills / filters if more than 1 section
        if len(self.sections) > 1:
            cats = ["All"] + [h for h, _ in self.sections]
            for c in cats:
                is_sel = c == self.active_category
                if is_sel:
                    im.push_style_color(Col.BUTTON, (40, 90, 180, 255))
                if im.button(f" {c} ##filter"):
                    self.active_category = c
                if is_sel:
                    im.pop_style_color()
                im.same_line()
            im.new_line()
            im.separator()

        # Content scrolling area
        avail_w, avail_h = ctx.layout.avail()
        im.begin_child(
            (*im.get_cursor_screen_pos(), max(100.0, avail_w), max(80.0, avail_h - 38.0)), clip=True
        )

        for heading, lines in self.sections:
            if self.active_category != "All" and heading != self.active_category:
                continue

            im.spacing()
            im.text_colored(heading, (0.4, 0.8, 1.0, 1.0))
            im.separator()

            for line in lines:
                s = line.strip()
                if not s:
                    im.spacing()
                elif s.startswith(("- ", "* ")):
                    im.bullet()
                    im.text_wrapped(s[2:])
                elif len(s) >= 3 and s[0].isdigit() and s[1:3] in (". ", ") "):
                    im.text_colored(f"  {s[:3]}", (0.3, 0.85, 0.5, 1.0))
                    im.same_line()
                    im.text_wrapped(s[3:])
                elif s.startswith("### "):
                    im.text_colored(s[4:], (0.3, 0.85, 0.5, 1.0))
                elif s.startswith("## "):
                    im.text_colored(s[3:], (0.4, 0.8, 1.0, 1.0))
                else:
                    im.text_wrapped(s)

        im.end_child()

        # Footer action bar
        im.separator()
        if im.button("Close Help##footer"):
            pressed = "close"

        self.dlg.end()

        if pressed == "close" or (ctx.io.key == KEY_ESCAPE):
            self.hide()


class EmTkGuidedTour:
    """An interactive step-by-step Guided Tour rendered 100% inside EMTK."""

    def __init__(
        self,
        steps: list[dict[str, Any]] | str | Path,
        get_target_rect: Callable[[str], tuple[float, float, float, float] | None] | None = None,
        on_step_change: Callable[[int, dict[str, Any]], None] | None = None,
        owner: Any = None,
    ) -> None:
        self.get_target_rect = get_target_rect
        self.on_step_change = on_step_change
        self.active = False
        self.step_idx = 0
        self.steps: list[dict[str, Any]] = []

        if isinstance(steps, (str, Path)):
            resolved = resolve_resource_file(steps, owner)
            if resolved and resolved.is_file():
                try:
                    data = json.loads(resolved.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        self.steps = data
                    elif isinstance(data, dict) and "steps" in data:
                        self.steps = data["steps"]
                except Exception as exc:
                    logger.warning("Could not read guide steps from %s: %s", resolved, exc)
        elif isinstance(steps, list):
            self.steps = list(steps)

    def start(self, step: int = 0) -> None:
        """Start the guided tour at the specified step."""
        if not self.steps:
            return
        self.active = True
        self.step_idx = max(0, min(step, len(self.steps) - 1))
        self._notify_change()
        _safe_request_frame()

    def stop(self) -> None:
        """Stop/close the guided tour."""
        self.active = False
        _safe_request_frame()

    def next(self) -> None:
        """Advance to the next step, or finish if on the last step."""
        if self.step_idx >= len(self.steps) - 1:
            self.stop()
        else:
            self.step_idx += 1
            self._notify_change()

    def prev(self) -> None:
        """Go back to previous step."""
        if self.step_idx > 0:
            self.step_idx -= 1
            self._notify_change()

    next_step = next
    prev_step = prev

    def _notify_change(self) -> None:
        if callable(self.on_step_change) and 0 <= self.step_idx < len(self.steps):
            self.on_step_change(self.step_idx, self.steps[self.step_idx])
        _safe_request_frame()

    def draw(self, width: float, height: float) -> None:
        """Render the tour spotlight and floating card over the EMTK viewport."""
        if not self.active or not (0 <= self.step_idx < len(self.steps)):
            self.active = False
            return

        step = self.steps[self.step_idx]
        ctx = im.get_current_context()

        # 1. Dimmed backdrop
        ctx.draw.add_rect_filled((0.0, 0.0), (width, height), (0, 0, 0, 95))

        # 2. Target Spotlight
        target = step.get("target")
        target_rect = None
        if target:
            target_key = (
                target
                if isinstance(target, str)
                else target.get("name") or target.get("action") or target.get("key") or ""
            )
            if callable(self.get_target_rect):
                target_rect = self.get_target_rect(str(target_key))

        card_w = min(480.0, width - 40.0)
        card_h = 195.0

        if target_rect:
            tx, ty, tw, th = target_rect
            # Spotlight border around the active target control
            ctx.draw.add_rect(
                (tx - 3.0, ty - 3.0),
                (tx + tw + 3.0, ty + th + 3.0),
                BORDER_GREEN,
                rounding=4.0,
                thickness=2.5,
            )

            # Smart placement:
            # If target is on the left panel (dock), put card to its right so it doesn't obscure controls
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

        # 3. Floating Tour Card Body
        ctx.draw.add_rect_filled(
            (cx, cy),
            (cx + card_w, cy + card_h),
            (26, 28, 36, 250),
            rounding=8.0,
        )
        ctx.draw.add_rect(
            (cx, cy),
            (cx + card_w, cy + card_h),
            BORDER_BLUE,
            rounding=8.0,
            thickness=1.5,
        )

        # 4. Content Area with Native Word Wrapping
        content_margin = 14.0
        im.begin_child(
            (cx + content_margin, cy + 10.0, card_w - 2 * content_margin, card_h - 48.0),
            clip=True,
        )
        title = step.get("title", "")
        im.text_colored(f"Step {self.step_idx + 1} of {len(self.steps)}: {title}", ACCENT_BLUE)
        im.spacing()
        raw_text = str(step.get("text", ""))
        clean_text = _clean_html_text(raw_text)
        im.text_wrapped(clean_text)

        hint = step.get("hint") or (
            step.get("await", {}).get("hint") if isinstance(step.get("await"), dict) else None
        )
        if hint:
            im.spacing()
            clean_hint = _clean_html_text(str(hint))
            im.text_colored(f"💡 {clean_hint}", (0.5, 0.9, 0.5, 1.0))
        im.end_child()

        # 5. Tour Controls at Bottom of Card
        btn_y = cy + card_h - 34.0
        im.set_cursor_screen_pos((cx + 14.0, btn_y))
        if im.button("Close Tour##tour"):
            self.stop()

        im.set_cursor_screen_pos((cx + card_w - 170.0, btn_y))
        if self.step_idx > 0:
            if im.button("◄ Prev##tour"):
                self.prev()
        else:
            im.begin_disabled()
            im.button("◄ Prev##tour")
            im.end_disabled()

        im.same_line()
        is_last = self.step_idx == len(self.steps) - 1
        next_label = "Finish ✓##tour" if is_last else "Next ►##tour"
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        if im.button(next_label):
            self.next()
        im.pop_style_color()

        # Escape closes tour
        if ctx.io.key == KEY_ESCAPE:
            self.stop()
