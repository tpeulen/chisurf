"""EMTK immediate-mode UI for the MFD preparation plugin.

One window: pick a burst folder, prepare it for MFD analysis, read the report
(verified channels, count agreement, source resolution, diagnostics). The
panel (:class:`~.tool.MfdPrepareTool`) keeps the RPC client and the workflow;
this app only renders its state and calls back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
from emtk.app import ImApp
from emtk.im_core import Col

from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

if TYPE_CHECKING:
    from .tool import MfdPrepareTool

WINDOW_BG = (30, 32, 38, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)


class MfdPrepareGui:
    """EMTK GUI for preparing burst folders for MFD analysis."""

    def __init__(
        self,
        tool: MfdPrepareTool,
        on_browse: Callable[[], None] | None = None,
        on_prepare: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_browse = on_browse
        self.on_prepare = on_prepare
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        self.help_window = EmTkHelpWindow(
            title="MFD Prepare — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
        )

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 760.0)
        height = float(h or vp.size[1] or 560.0)

        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)
        if im.begin(
            "##mfd_prepare",
            (0.0, 0.0, width, height),
            im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE,
        ):
            folder = getattr(self.tool, "_folder", "")
            if folder:
                im.text_colored(f"📂 {Path(folder).name}", (0.35, 0.75, 1.0, 1.0))
                im.same_line()
                im.text_disabled(folder)
            else:
                im.text_disabled("No folder selected")

            if im.button("Browse…"):
                if callable(self.on_browse):
                    self.on_browse()
            self.remember("browse")

            im.same_line()
            im.push_style_color(Col.BUTTON, ACCENT_GREEN)
            im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
            im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
            if im.button("Prepare"):
                if callable(self.on_prepare):
                    self.on_prepare()
            im.pop_style_color(3)
            self.remember("prepare")

            im.same_line()
            if im.button("❓ Help"):
                self.show_help()
            self.remember("help")

            im.separator()
            report = getattr(self.tool, "_report_text", "")
            if report:
                for line in report.splitlines():
                    im.text_wrapped(line)
            else:
                im.text_disabled(
                    "Select a burst folder and click Prepare to see the MFD preparation report."
                )
        im.end()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)


class MfdPrepareApp(ImApp):
    """The EMTK ImApp for the MFD Prepare tool."""

    def __init__(
        self,
        tool: MfdPrepareTool,
        on_browse: Callable[[], None] | None = None,
        on_prepare: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.prepare_gui = MfdPrepareGui(
            tool,
            on_browse=on_browse,
            on_prepare=on_prepare,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.prepare_gui.item_rects

    def start_guide(self) -> None:
        self.prepare_gui.start_guide()

    def show_help(self) -> None:
        self.prepare_gui.show_help()

    def _render(self) -> None:
        self.prepare_gui.draw()


__all__ = ["MfdPrepareApp", "WINDOW_BG"]
