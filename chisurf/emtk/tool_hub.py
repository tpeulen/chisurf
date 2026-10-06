"""A native tool hub: a searchable rail of tools on the left, the selected tool's own emtk app on the right.

The emtk counterpart of the Qt ``NavigationPanelTool`` shell (FCS, TTTR Tools, ...). Each panel names a child app by
a factory: ``"factory"`` (a callable) or ``"plugin"`` (a plugin folder under ``chisurf/plugins``, whose manifest's
``entrypoints.emtk`` is the factory). Children are made on first selection and kept, so a tool keeps its state while
the user looks at another one. ``{"separator": true, "name": "Tools"}`` groups the rail under a caption.

A hub that is a *workflow* (the FCS correlator steps) overrides :meth:`ToolHubApp.panel_enabled` (a step that is
switched off is grey and skipped by Back / Next) and :meth:`ToolHubApp.on_select` (hand the previous steps' results
to the step being opened).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.i18n import tr

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

PLUGINS = Path(__file__).resolve().parents[1] / "plugins"
#: Height of the window naming the selected tool.
HEADER = 62.0
#: Height of the status bar with Back / Next.
BAR = 30.0


def plugin_factory(panel: dict) -> tuple[Callable[[], Any] | None, str]:
    """The child factory of a panel: its ``factory``, else its plugin's ``entrypoints.emtk`` (``None`` if it has none)."""
    if callable(panel.get("factory")):
        return panel["factory"], getattr(panel["factory"], "__qualname__", "factory")
    manifest = PLUGINS / str(panel["plugin"]) / "manifest.json"
    spec = json.loads(manifest.read_text(encoding="utf-8")).get("entrypoints", {}).get("emtk")
    if not spec:
        return None, ""
    module, attribute = spec.split(":", 1)
    return getattr(importlib.import_module(module), attribute), spec


#: The maturity flags a plugin manifest may set, with the default banner of each (the Qt rail's markers).
MATURITY = {
    "experimental": ("⚠", "This tool is experimental: validate its results on known controls."),
    "deprecated": ("⛔", "This tool is deprecated and will be removed."),
}


def _with_maturity(panel: dict) -> dict:
    """Copy the ``experimental`` / ``deprecated`` flags (and messages) of a panel's plugin manifest onto it, as the Qt
    ``apply_manifest_flags`` does: the flag lives in the manifest, not in every host that embeds the tool."""
    if panel.get("separator") or not panel.get("plugin"):
        return panel
    try:
        data = json.loads((PLUGINS / str(panel["plugin"]) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return panel
    for flag, (_mark, default) in MATURITY.items():
        if data.get(flag):
            panel[flag] = True
            panel[flag + "_message"] = str(data.get(flag + "_message") or default)
    return panel


def _marker(panel: dict) -> str:
    return "".join(f" {mark}" for flag, (mark, _msg) in MATURITY.items() if panel.get(flag))


class ToolHubApp(ImApp):
    """The rail, the destination header, the selected child and a status bar with Back / Next."""

    def __init__(
        self,
        title: str,
        panels: list[dict],
        *,
        help_resource: Path | None = None,
        guide: Path | None = None,
        resolver: Callable[[dict], tuple[Any, str]] = plugin_factory,
        initial: str | None = None,
    ) -> None:
        self.title = title
        self.panels = [_with_maturity(dict(p)) for p in panels]
        self.tools = [p for p in self.panels if not p.get("separator")]
        self.selected = initial or (self.tools[0]["role"] if self.tools else None)
        self.children: dict[str, Any] = {}
        self.routes: dict[str, str] = {}
        self.errors: dict[str, str] = {}
        self.filter = ""
        self.status = "Ready"
        self.item_rects: dict[str, tuple] = {}
        self.resolver = resolver
        self.child_box = (230.0, HEADER, 970.0, 688.0)
        self._painter = None
        self._child_focus = False
        self._child_capture = False
        #: Steps still to walk (fast-forward), and whether Next waits for the current step's run to end.
        self._ff_queue: list[str] = []
        self._pending_next = False
        self.help = EmTkHelpWindow(title=f"{title} — Help", resource=help_resource, owner=self)
        self.child_help = None
        self.tour = EmTkGuidedTour(
            guide,
            owner=self,
            on_step_change=self._tour_step,
            get_target_rect=self._target_rect,
            wait_for_controls=True,
        )
        super().__init__(self.render, continuous=False)

    # ── what a workflow hub overrides ─────────────────────────────────────

    def panel_enabled(self, role: str) -> bool:
        """Whether a tool can be opened (a switched-off workflow step cannot)."""
        return True

    def on_select(self, role: str, child: Any) -> None:
        """Called each time a tool is opened, after its child exists (hand it the earlier steps' results)."""

    # ── selection ─────────────────────────────────────────────────────────

    @property
    def child(self):
        return self.children.get(self.selected)

    @property
    def panel(self):
        return next((p for p in self.tools if p["role"] == self.selected), None)

    @property
    def native_layouts(self):
        layouts = {}
        for role, child in self.children.items():
            if hasattr(child, "docks"):
                layouts[role] = child.docks
            for name, manager in getattr(child, "native_layouts", {}).items():
                layouts[role + "/" + name] = manager
        return layouts

    def ensure_child(self, role: str):
        """The child app of *role*, made now if it was not (``None`` if it cannot be; the reason is in :attr:`errors`)."""
        panel = next((p for p in self.tools if p["role"] == role), None)
        if panel is None:
            raise ValueError(f"Unknown {self.title} panel: {role}")
        if role not in self.children and role not in self.errors:
            try:
                factory, route = self.resolver(panel)
                self.routes[role] = route
                if factory is None:
                    self.errors[role] = "This tool has no native emtk app yet."
                else:
                    self.children[role] = factory()
            except Exception as exc:  # noqa: BLE001 - shown in place of the tool, with Retry
                self.errors[role] = f"{type(exc).__name__}: {exc}"
        return self.children.get(role)

    def select(self, role: str, retry: bool = False, by_user: bool = True):
        panel = next((p for p in self.tools if p["role"] == role), None)
        if panel is None:
            raise ValueError(f"Unknown {self.title} panel: {role}")
        if not self.panel_enabled(role):
            self.status = f"{tr(panel['name'])} is switched off in the steps."
            return self.child
        self.selected = role
        self._child_focus = self._child_capture = False
        if retry:
            self.errors.pop(role, None)
        child = self.ensure_child(role)
        if child is not None:
            try:
                self.on_select(role, child)
            except Exception as exc:  # noqa: BLE001 - the tool still opens; the bar says what went wrong
                self.status = f"{type(exc).__name__}: {exc}"
            else:
                self.status = "Ready"
        if by_user:
            self._ff_queue, self._pending_next = [], False  # picking a step by hand stops a fast-forward
            self.tour.notify_used(panel["name"])
            self.tour.notify_used("nav." + role)
            if self.tour.active:  # a step names its panel by a part of the name ("Files & Steps")
                key = self.tour._target_key(self.tour.steps[self.tour.step_idx].get("target"))
                if key and key.casefold() in panel["name"].casefold():
                    self.tour.notify_used(key)
        self.child_help = None
        self.wants_frame = True
        return self.child

    def step(self, delta: int) -> None:
        """Back / Next: the neighbouring tool that can be opened (Back also stops a fast-forward)."""
        if delta < 0:
            self._ff_queue, self._pending_next = [], False
        roles = [p["role"] for p in self.tools]
        index = roles.index(self.selected) if self.selected in roles else 0
        index += delta
        while 0 <= index < len(roles) and not self.panel_enabled(roles[index]):
            index += delta
        if 0 <= index < len(roles):
            self.select(roles[index])

    # ── Next runs the step, >> walks the rest (the Qt rail's Next and fast-forward) ─────────────────────────────────

    def _busy(self) -> bool:
        return bool(self.child and getattr(self.child, "running", False))

    def _run_current(self) -> bool:
        """Run the open step's own action (``run_step()``, e.g. Correlate) unless it is ``optional``; whether it ran."""
        panel = self.panel
        run = getattr(self.child, "run_step", None)
        if panel is None or panel.get("optional") or not callable(run):
            return False
        return run() is not False

    def next_step(self) -> None:
        """Next: run this step, then go on once it is done."""
        self._ff_queue = []
        self._run_current()
        self._pending_next = True
        self._advance()

    @property
    def fast_forwarding(self) -> bool:
        return bool(self._ff_queue)

    def fast_forward(self) -> None:
        """Run every remaining step of this group in order, waiting for each; pressed again, stop after the current one."""
        if self._ff_queue:
            self._ff_queue = []
            self.status = "Fast-forward stopped."
            return
        queue = []
        started = False
        for panel in self.panels:
            if panel.get("separator"):
                if started:
                    break
                continue
            if panel["role"] == self.selected:
                started = True
            if started and self.panel_enabled(panel["role"]):
                queue.append(panel["role"])
        self._ff_queue = queue
        self._ff_total = len(queue)
        self._advance()

    def _advance(self) -> None:
        """One tick of Next / fast-forward: nothing while the step is busy, then the next move."""
        if self._busy():
            self.wants_frame = True
            return
        if self._pending_next:
            self._pending_next = False
            self.step(1)
            return
        if self._ff_queue:
            role = self._ff_queue.pop(0)
            if role != self.selected:
                self.select(role, by_user=False)
            self.status = f"Fast-forward {self._ff_total - len(self._ff_queue)}/{self._ff_total}: {self.panel['name']}"
            self._run_current()
            if not self._ff_queue:
                self.status = "Fast-forward finished."
            self.wants_frame = True

    def _neighbour(self, delta: int) -> bool:
        roles = [p["role"] for p in self.tools]
        index = (roles.index(self.selected) if self.selected in roles else 0) + delta
        while 0 <= index < len(roles):
            if self.panel_enabled(roles[index]):
                return True
            index += delta
        return False

    # ── tour ──────────────────────────────────────────────────────────────

    def _target_rect(self, key):
        """A step's target: a control of the hub, a rail row (by part of its name), or a control of the open tool."""
        if key in self.item_rects:
            return self.item_rects[key]
        panel = next((p for p in self.tools if key and key.casefold() in p["name"].casefold()), None)
        if panel is not None:
            return self.item_rects.get("nav." + panel["role"])
        child = self.child
        rects = getattr(child, "item_rects", None) or {}
        if key in rects:
            x, y, w, h = rects[key]
            return (x + self.child_box[0], y + self.child_box[1], w, h)
        return None

    def _tour_step(self, index, step):
        target = (step.get("target") or {}).get("panel", "")
        panel = next((p for p in self.tools if target and target.casefold() in p["name"].casefold()), None)
        if panel and not step.get("await"):
            self.select(panel["role"], by_user=False)

    # ── frame ─────────────────────────────────────────────────────────────

    def matching_panels(self):
        query = self.filter.casefold()
        return [
            p
            for p in self.tools
            if query in (tr(p["name"]) + " " + tr(p.get("description", "")) + " " + p["role"]).casefold()
        ]

    def show_child_help(self):
        panel = self.panel
        if panel is None:
            return
        path = Path(panel["help"]) if panel.get("help") else None
        if path is None and panel.get("plugin"):
            for candidate in ("gui/help.md", "help.md"):
                if (PLUGINS / panel["plugin"] / candidate).is_file():
                    path = PLUGINS / panel["plugin"] / candidate
                    break
        self.child_help = EmTkHelpWindow(
            title=panel["name"] + " — Help",
            resource=path if path is not None and path.is_file() else None,
            text="" if path is not None and path.is_file() else panel.get("description", ""),
            owner=self,
        )
        self.child_help.show()

    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if self.selected and self.selected not in self.children and self.selected not in self.errors:
            self.select(self.selected, by_user=False)
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None

    def render(self):
        width, height = im.get_main_viewport().size
        left = min(230.0, width * 0.26)
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, height), im.Cond.ALWAYS)
        if im.begin(self.title, flags=im.WindowFlags.NO_RESIZE):
            if im.button("Help"):
                self.help.show()
            im.set_item_tooltip(f"Read the {self.title} reference.")
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if im.button("Guide"):
                self.tour.start()
            im.set_item_tooltip("A step-by-step walk through the tools, pointing at each control.")
            self.item_rects["guide"] = im.get_item_rect()
            _, self.filter = im.input_text(f"##Find {self.title}", self.filter, hint=tr("Search…"))
            im.set_item_tooltip("Find tools by name or description.")
            self.item_rects["search"] = im.get_item_rect()
            matching = {p["role"] for p in self.matching_panels()}
            for panel in self.panels:
                if panel.get("separator"):
                    if not self.filter:
                        if panel.get("name"):
                            im.text_disabled(tr(panel["name"]))
                        else:
                            im.separator()
                    continue
                if panel["role"] not in matching:
                    continue
                enabled = self.panel_enabled(panel["role"])
                im.begin_disabled(not enabled)
                if im.selectable(
                    tr(panel["name"]) + _marker(panel) + "##" + panel["role"],
                    self.selected == panel["role"],
                    size=(left - 8, 28),
                    icon=panel.get("icon"),
                ):
                    self.select(panel["role"])
                im.end_disabled()
                tip = " ".join(
                    [tr(panel.get("description", ""))]
                    + [panel[flag + "_message"] for flag in MATURITY if panel.get(flag)]
                )
                if not enabled:
                    tip += " " + tr("(switched off in Files & Steps)")
                im.set_item_tooltip(tip)
                self.item_rects["nav." + panel["role"]] = im.get_item_rect()
            if not matching:
                im.text_wrapped(tr("No matching tools."))
        im.end()
        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, HEADER), im.Cond.ALWAYS)
        if im.begin(f"{self.title} destination", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            if self.panel:
                im.text_unformatted(tr(self.panel["name"]))
                im.same_line()
                if im.button("Tool help"):
                    self.show_child_help()
                im.set_item_tooltip("Read help for the selected tool.")
                self.item_rects["tool_help"] = im.get_item_rect()
                banners = [self.panel[flag + "_message"] for flag in MATURITY if self.panel.get(flag)]
                if banners:
                    im.push_style_color(im.Col.TEXT, (240, 190, 60, 255))
                    im.text_wrapped(MATURITY["experimental" if self.panel.get("experimental") else "deprecated"][0]
                                    + " " + tr(" ".join(banners)))
                    im.pop_style_color(1)
                    self.item_rects["maturity"] = im.get_item_rect()
                else:
                    im.text_wrapped(tr(self.panel.get("description", "")))
        im.end()
        self.child_box = (left, HEADER, max(1.0, width - left), max(1.0, height - HEADER - BAR))
        im.set_next_window_pos((left, height - BAR), im.Cond.ALWAYS)
        im.set_next_window_size((width - left, BAR), im.Cond.ALWAYS)
        if im.begin(f"{self.title} status", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            buttons_x = max(120.0, width - left - 230.0)
            # The status keeps to the room left of Back / >> / Next (cut, whole text as tooltip):
            # it must not run under the buttons, however long a step's message is.
            im.text_ellipsis(tr(self.status), buttons_x - 2.0 * im.get_style().item_spacing[0])
            self.item_rects["status"] = im.get_item_rect()
            im.same_line(buttons_x)
            im.begin_disabled(not self._neighbour(-1))
            if im.button(tr("Back")):
                self.step(-1)
            self.item_rects["back"] = im.get_item_rect()
            im.set_item_tooltip(tr("Go to the previous step or tool."))
            im.end_disabled()
            im.same_line()
            im.same_line()
            if im.button(tr("Stop") if self.fast_forwarding else ">>"):
                self.fast_forward()
            self.item_rects["fast_forward"] = im.get_item_rect()
            im.set_item_tooltip(tr("Fast-forward: run every remaining step of this group in order, waiting for each "
                                   "to finish. Press again to stop after the current step."))
            im.same_line()
            im.begin_disabled(not self._neighbour(1))
            if im.button(tr("Next")):
                self.next_step()
            self.item_rects["next"] = im.get_item_rect()
            im.set_item_tooltip(tr("Run this step (where it has a run), then go to the next one."))
            im.end_disabled()
        im.end()
        if self.child:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        elif self.selected in self.errors:
            im.set_next_window_pos((left, HEADER), im.Cond.ALWAYS)
            im.set_next_window_size((width - left, height - HEADER - BAR), im.Cond.ALWAYS)
            if im.begin(f"{self.title} tool unavailable", flags=im.WindowFlags.NO_RESIZE):
                im.text_wrapped(tr("The selected tool could not be opened."))
                im.text_wrapped(tr(self.errors[self.selected]))
                if im.button("Retry"):
                    self.select(self.selected, retry=True)
                self.item_rects["retry"] = im.get_item_rect()
                im.set_item_tooltip("Build the tool again.")
            im.end()
        if self._pending_next or self._ff_queue:
            self._advance()
        self.help.draw((0, 0, width, height))
        if self.child_help:
            self.child_help.draw((0, 0, width, height))
        self.tour.draw(width, height)

    # ── input: the child gets what lands on it ────────────────────────────

    def _overlay_open(self, x: float | None = None, y: float | None = None) -> bool:
        """Whether input at (x, y) belongs to a window over the tool: a help window, or the guide's card. The rest of
        the screen stays live during a tour, so an awaited step's control (in the tool) can be pressed."""
        if self.help.open or bool(self.child_help and self.child_help.open):
            return True
        if not self.tour.active:
            return False
        if x is None:
            return False
        try:
            from emtk.im_core import get_current_context

            window = get_current_context().find_hovered_window(float(x), float(y))
        except Exception:  # noqa: BLE001 - before the first frame
            return False
        return window is not None and "tour_card" in str(getattr(window, "name", ""))

    def _inside(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self._child_focus = self._inside(x, y) and not self._overlay_open(x, y)
        self._child_capture = self._child_focus
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child and self._child_capture:
            self.child.pointer_press(x - self.child_box[0], y - self.child_box[1], button, modifiers, clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child and self._child_capture:
            self.child.pointer_release(x - self.child_box[0], y - self.child_box[1], button, modifiers)
        self._child_capture = False

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child:
            self.child.pointer_move(x - self.child_box[0], y - self.child_box[1], buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        if self.child and self._inside(x, y) and not self._overlay_open(x, y):
            self.child.wheel(x - self.child_box[0], y - self.child_box[1], steps, modifiers)
        else:
            super().wheel(x, y, steps, modifiers)

    def scroll(self, rows):
        if self.child and self._child_focus and not self._overlay_open():
            return self.child.scroll(rows)
        return super().scroll(rows)

    def key(self, key, text="", modifiers=0):
        if self.child and self._child_focus and not self._overlay_open():
            return self.child.key(key, text, modifiers)
        return super().key(key, text, modifiers)

    def animating(self):
        return super().animating() or bool(self.child and self.child.animating())

    def next_frame_in(self):
        delays = [super().next_frame_in()]
        if self.child:
            delays.append(self.child.next_frame_in())
        return min((d for d in delays if d is not None), default=None)

    def on_files_dropped(self, paths):
        if not self.child or self._overlay_open():
            return False
        for name in ("on_paths_dropped", "on_files_dropped", "files_dropped"):
            handler = getattr(self.child, name, None)
            if callable(handler):
                return handler(paths) is not False
        return False

    def on_paths_dropped(self, paths):
        return self.on_files_dropped(paths)

    # ── persistence ───────────────────────────────────────────────────────

    def export_settings(self):
        children = {}
        for role, child in self.children.items():
            export = getattr(child, "export_settings", None) or getattr(child, "export_state", None)
            if callable(export):
                children[role] = export()
        return {"selected": self.selected, "children": children}

    def restore_settings(self, state):
        roles = {p["role"] for p in self.tools}
        for role, data in (state or {}).get("children", {}).items():
            if role in roles:
                child = self.ensure_child(role)
                restore = getattr(child, "restore_settings", None) or getattr(child, "restore_state", None)
                if callable(restore):
                    restore(data)
        if (state or {}).get("selected") in roles:
            self.select(state["selected"], by_user=False)

    def close(self):
        for child in self.children.values():
            close = getattr(child, "close", None)
            if callable(close):
                close()
        self.children.clear()


__all__ = ["BAR", "HEADER", "ToolHubApp", "plugin_factory"]
