"""Movable, snapping, collapsible, closable panel windows -- in the style of chimol.

emtk's immediate-mode windows have no chrome (no title bar, no dragging), so
the window system lives here, modelled on chimol's in-viewport windows
(``chimol/ui/gui/windows.py`` and ``chimol/ui/window_state.py``):

* a title bar (highlighted when the window is on top) with a collapse and a
  close button, a resize grip in the bottom-right corner;
* a press raises the window; dragging the title moves it; near a viewport
  edge or another window's edge it **snaps** flush, and a window snapped to a
  viewport edge is **anchored** there and follows it when the viewport resizes;
* a drag takes one window alone: it detaches from the windows it touched and
  snaps again where it is dropped; Shift-drag moves the whole stuck group
  (windows flush against each other); a double-click on the title folds it;
* the code follows chimol's WindowsMixin method by method (layout_windows,
  _window_hit, _press_window, _drag_window, _snap_to_windows, _stuck_group);
* each window's body is its own emtk frame with its own IO, drawn in z-order,
  so the window you see on top is the window that gets the click;
* placement, visibility and fold state persist in an imgui.ini-style file (``cmc-light.ini``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional

TITLE_H = 22.0          # chimol WINDOW_TITLE_H (20) plus room for emtk's font
PAD_X, PAD_Y = 8.0, 6.0  # inner padding of a window body
GRIP = 14.0             # chimol WINDOW_GRIP
GRAB_PAD = 4.0          # chimol WINDOW_GRAB_PAD: the grip reaches a little past the corner
SNAP_DISTANCE = 14.0    # chimol window_state.SNAP_DISTANCE: viewport edges
STICK = 8.0             # chimol WINDOW_STICK: other windows' edges
MIN_W, MIN_H = 120.0, 32.0  # chimol WINDOW_MIN_W / WINDOW_MIN_H
MARGIN = 8.0            # chimol MARGIN
GAP = 4.0               # default layout: windows apart, so each moves alone until snapped together

WINDOW_BG = (26, 28, 34, 255)  # opaque: a covered window must not show through
TITLE_BG = (10, 10, 10, 255)
TITLE_ACTIVE_BG = (41, 74, 122, 255)
BORDER = (110, 110, 128, 128)
TITLE_FG = (255, 255, 255, 255)
DIM_FG = (160, 160, 160, 255)
GRIP_COL = (66, 150, 250, 128)
SNAP_HINT = (66, 150, 250, 220)
SNAP_HINT_BAND = 3.0

HIT_TITLE, HIT_BODY, HIT_RESIZE, HIT_COLLAPSE, HIT_CLOSE = range(5)


@dataclass
class Window:
    key: str
    title: str
    x: float
    y: float
    w: float
    h: float
    draw: Callable = None           # draw(w, h) -> None, immediate mode inside the body
    overlay: Callable = None        # overlay(painter, body_rect) -> None, painter controls on top
    scroll: Callable = None         # scroll(rows, px, py) -> bool, True when consumed
    visible: bool = True
    collapsed: bool = False
    closable: bool = True
    resizable: bool = True
    movable: bool = True
    anchor: Optional[str] = None
    min_w: float = MIN_W
    min_h: float = MIN_H
    modal: bool = False
    on_close: Callable = None
    io: object = None
    storage: dict = field(default_factory=dict)
    defaults: dict = None
    desired_w: float = 0.0          # chimol: the size the user asked for; the clamp works from it
    desired_h: float = 0.0
    measure: bool = True            # the contents set the minimum size (dialogs fill any size instead)
    content_floor: Callable = None  # () -> (w, h): extra minimum for painter-drawn contents
    content_w: float = 0.0          # measured last frame: what the contents need
    content_h: float = 0.0

    def floor_w(self):
        return max(self.min_w, MIN_W, self.content_w)

    def floor_h(self):
        return max(self.min_h, MIN_H, self.content_h)

    def frame(self):
        """chimol window_frame: collapsed to the title bar when folded."""
        h = TITLE_H if self.collapsed else max(self.h, TITLE_H)
        return (self.x, self.y, self.w, h)

    def body(self):
        if self.collapsed:
            return (0.0, 0.0, 0.0, 0.0)
        return (self.x, self.y + TITLE_H, self.w, max(0.0, self.h - TITLE_H))


def load_ini(path):
    """Read an imgui.ini-style layout file -> {key: {x, y, w, h, visible, collapsed, anchor}}."""
    states, section = {}, None
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return states

    def pair(text):
        parts = text.split(",")
        try:
            return (float(parts[0]), float(parts[1])) if len(parts) == 2 else None
        except ValueError:
            return None

    for line in lines:
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            if line.startswith("[Window][") and line.endswith("]"):
                section = states.setdefault(line[len("[Window]["):-1], {})
            elif line == "[Viewport][Main]":
                section = states.setdefault("_viewport_raw", {})
            elif line == "[MainWindow][Main]":
                section = states.setdefault("_main", {})
            else:
                section = None
            continue
        if section is None or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name in ("Pos", "Size"):
            v = pair(value)
            if v:
                if name == "Pos":
                    section["x"], section["y"] = v
                else:
                    section["w"], section["h"] = v
        elif name in ("Collapsed", "Visible"):
            section[name.lower()] = value.strip() == "1"
        elif name == "Anchor":
            section["anchor"] = value.strip() or None
    raw = states.pop("_viewport_raw", None)
    if raw and "w" in raw and "h" in raw:
        states["_viewport"] = (raw["w"], raw["h"])
    return states


def save_ini(path, windows, viewport, main_window=None):
    """Write the layout in imgui.ini style (plus Visible/Anchor and the main window)."""
    out = ["; cmc-light window layout (imgui.ini style)", ""]
    if main_window:
        out += ["[MainWindow][Main]",
                "Pos=%d,%d" % (main_window.get("x", 0), main_window.get("y", 0)),
                "Size=%d,%d" % (main_window.get("w", 1280), main_window.get("h", 900)), ""]
    if viewport[0] > 0:
        out += ["[Viewport][Main]", "Size=%d,%d" % (viewport[0], viewport[1]), ""]
    for w in windows:
        out += ["[Window][%s]" % w.key, "Pos=%d,%d" % (round(w.x), round(w.y)),
                "Size=%d,%d" % (round(w.w), round(w.h)),
                "Collapsed=%d" % (1 if w.collapsed else 0), "Visible=%d" % (1 if w.visible else 0)]
        if w.anchor:
            out.append("Anchor=%s" % w.anchor)
        out.append("")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(out))
    except OSError:
        pass


def _inside(px, py, rect):
    x, y, w, h = rect
    return x <= px < x + w and y <= py < y + h


def snap(x, y, w, h, width, height, top=0.0, distance=SNAP_DISTANCE):
    """chimol window_state.snap: flush to an edge that is near **or overshot**; returns the anchor."""
    left = x <= distance
    right = (x + w) >= width - distance
    high = y <= top + distance
    low = (y + h) >= height - distance
    if left:
        x = 0.0
    elif right:
        x = width - w
    if high:
        y = top
    elif low:
        y = height - h
    vertical = "top" if high else ("bottom" if low else "")
    horizontal = "left" if left else ("right" if right else "")
    return x, y, ("-".join(p for p in (vertical, horizontal) if p) or None)


def anchored_position(anchor, x, y, w, h, width, height, top=0.0):
    """chimol window_state.anchored_position: a corner pins both, a side pins one."""
    parts = set(str(anchor).split("-"))
    if "left" in parts:
        x = 0.0
    elif "right" in parts:
        x = max(width - w, 0.0)
    if "top" in parts:
        y = top
    elif "bottom" in parts:
        y = max(height - h, top)
    return x, y


class WindowManager:
    """A port of chimol's in-viewport windows (``chimol/ui/gui/windows.py``)."""

    def __init__(self, top=0.0, state_path=None):
        self.windows: list[Window] = []  # z-order, last on top
        self.top = top
        self.size = (0.0, 0.0)
        self.state_path = state_path
        self._window_drag = None      # (window, dx, dy)
        self._window_resize = None    # (window, press x, press y, w, h)
        self._window_body_drag = None
        self._drag_followers = []     # (window, offset x, offset y)
        self._snap_hint = ()
        self._snap_hint_keys = set()
        self._states = load_ini(state_path) if state_path else {}
        self._states.pop("_viewport", None)
        self.main_window = self._states.pop("_main", None)

    # -- registry (chimol add_window / _apply_saved_state) ---------------------- #
    def add(self, win: Window) -> Window:
        import emtk

        if win.defaults is None:
            win.defaults = dict(x=win.x, y=win.y, w=win.w, h=win.h, visible=win.visible,
                                collapsed=win.collapsed, anchor=win.anchor)
        saved = self._states.get(win.key)
        if isinstance(saved, dict):
            for name in ("x", "y") + (("w", "h") if win.resizable else ()):
                if name in saved:
                    try:
                        setattr(win, name, float(saved[name]))
                    except (TypeError, ValueError):
                        pass
            for name in ("visible", "collapsed"):
                if name in saved:
                    setattr(win, name, bool(saved[name]))
            if "anchor" in saved:
                win.anchor = saved["anchor"] or None
        if not win.desired_w:
            win.desired_w = float(win.w)
        if not win.desired_h:
            win.desired_h = float(win.h)
        win.io = emtk.IO()
        self.windows = [w for w in self.windows if w.key != win.key] + [win]
        return win

    def get(self, key):
        return next((w for w in self.windows if w.key == key), None)

    def raise_window(self, win):
        if win in self.windows and self.windows[-1] is not win:
            self.windows.remove(win)
            self.windows.append(win)

    def show(self, key, visible=True, focus=True):
        win = self.get(key)
        if win is None:
            return
        if visible and not win.visible:
            win.collapsed = False
        win.visible = visible
        if visible and focus:
            self.raise_window(win)
        self.persist()

    def top_window(self):
        for win in reversed(self.windows):
            if win.visible:
                return win
        return None

    def modal_window(self):
        for win in reversed(self.windows):
            if win.visible and win.modal:
                return win
        return None

    def reset_layout(self):
        """chimol reset_windows: back to the authored placement, saved layout forgotten."""
        for win in self.windows:
            if not win.defaults:
                continue
            for name, value in win.defaults.items():
                setattr(win, name, value)
            win.desired_w, win.desired_h = float(win.w), float(win.h)
        self._states = {}
        if self.size[0] > 0:
            self.layout(*self.size)
        self.persist()

    def persist(self):
        if self.state_path:
            save_ini(self.state_path, self.windows, self.size, self.main_window)

    # -- layout (chimol layout_windows) ------------------------------------------- #
    def layout(self, width, height):
        """Keep every window inside the viewport, and no smaller than its floor.

        Sizes are restored from what the user asked for (desired_w/h), so a window
        squeezed by a small viewport gets its size back when the viewport grows.
        """
        if width <= 0 or height <= 0:
            return
        self.size = (width, height)
        ceiling = float(self.top)
        for win in self.windows:
            if win.resizable:
                if not win.desired_w:
                    win.desired_w = float(win.w)
                if not win.desired_h:
                    win.desired_h = float(win.h)
                win.w, win.h = float(win.desired_w), float(win.desired_h)
            win.w = max(float(win.w), win.floor_w())
            win.h = max(float(win.h), win.floor_h())
            win.w = min(win.w, max(float(width) - 2 * MARGIN, MIN_W))
            win.h = min(win.h, max(float(height) - ceiling, MIN_H))  # never cut off at the bottom
            if win.anchor:
                _x, _y, _w, fh = win.frame()
                win.x, win.y = anchored_position(win.anchor, win.x, win.y, win.w, fh,
                                                 float(width), float(height), ceiling)
            _x, _y, fw, fh = win.frame()
            win.x = min(max(float(win.x), 0.0), max(float(width) - fw, 0.0))
            win.y = min(max(float(win.y), ceiling), max(float(height) - fh, ceiling))

    # -- painting (chimol _paint_windows) --------------------------------------- #
    def paint(self, painter):
        import emtk
        from emtk import im
        from emtk.painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_VCENTER

        active = self.top_window()
        modal = self.modal_window()
        drag_win = self._window_drag[0] if self._window_drag else (
            self._window_resize[0] if self._window_resize else None)
        for win in self.windows:
            if not win.visible:
                continue
            x, y, w, h = win.frame()
            if not win.collapsed:
                painter.fill_rect(x, y, w, h, WINDOW_BG)
            painter.fill_rect(x, y, w, TITLE_H, TITLE_ACTIVE_BG if win is active else TITLE_BG)
            painter.text(x, y, TITLE_H, TITLE_H, ALIGN_CENTER, ">" if win.collapsed else "v", DIM_FG)
            painter.text(x + TITLE_H, y, max(w - 2 * TITLE_H, 1.0), TITLE_H, ALIGN_VCENTER | ALIGN_LEFT,
                         win.title or win.key, TITLE_FG)
            if win.closable:
                painter.text(x + w - TITLE_H, y, TITLE_H, TITLE_H, ALIGN_CENTER, "x", TITLE_FG)
            if not win.collapsed:
                bx, by, bw, bh = win.body()
                with emtk.frame(painter, (bx, by, bw, bh), io=win.io, storage=win.storage):
                    im.begin(win.key, (bx + PAD_X, by + PAD_Y, max(10.0, bw - 2 * PAD_X),
                                       max(10.0, bh - 2 * PAD_Y)), im.WindowFlags.NO_TITLE_BAR)
                    im.begin_disabled(modal is not None and win is not modal)
                    if win.draw:
                        win.draw(bw - 2 * PAD_X, bh - 2 * PAD_Y)
                    im.end_disabled()
                    if win.measure:
                        self._measure(win)
                    im.end()
                if win.overlay:
                    win.overlay(painter, (bx, by, bw, bh))
                if win.resizable:
                    for step in range(3):  # chimol's grip: three stacked bars
                        size = GRIP - step * 4.0
                        painter.fill_rect(x + w - size, y + h - 2.0 - step * 4.0, size, 2.0, GRIP_COL)
            glued = win is drag_win and (self._snap_hint or self._snap_hint_keys)
            partner = drag_win is not None and win.key in self._snap_hint_keys
            painter.stroke_rect(x, y, w, h, SNAP_HINT if (glued or partner) else BORDER)
        self._paint_snap_hint(painter)

    @staticmethod
    def _measure(win):
        """The window's minimum size is what its contents reached (see gui.flex for
        contents that stretch with the window and must not count their stretch)."""
        from emtk.im_widgets import get_current_context

        lay = get_current_context().layout
        w = lay.content_width() + 2 * PAD_X + 2.0
        h = lay.content_height() - getattr(lay, "flex_y", 0.0) + 2 * PAD_Y + TITLE_H + 2.0
        if win.content_floor is not None:
            fw, fh = win.content_floor()
            w, h = max(w, fw), max(h, fh)
        win.content_w, win.content_h = float(w), float(h)

    def _paint_snap_hint(self, painter):
        if not self._snap_hint or (self._window_drag is None and self._window_resize is None):
            return
        width, height = self.size
        top, band = self.top, SNAP_HINT_BAND
        for edge in self._snap_hint:
            if edge == "left":
                painter.fill_rect(0.0, top, band, height - top, SNAP_HINT)
            elif edge == "right":
                painter.fill_rect(width - band, top, band, height - top, SNAP_HINT)
            elif edge == "top":
                painter.fill_rect(0.0, top, width, band, SNAP_HINT)
            elif edge == "bottom":
                painter.fill_rect(0.0, height - band, width, band, SNAP_HINT)

    # -- input (chimol _window_hit / _press_window / _drag_window / release) ------ #
    def hit(self, px, py):
        for win in reversed(self.windows):
            if not win.visible:
                continue
            x, y, w, h = win.frame()
            if win.resizable and not win.collapsed:
                grip = (x + w - GRIP, y + h - GRIP, GRIP + GRAB_PAD, GRIP + GRAB_PAD)
                if _inside(px, py, grip):
                    return win, HIT_RESIZE
            if not _inside(px, py, (x, y, w, h)):
                continue
            if py <= y + TITLE_H:
                if win.closable and px >= x + w - TITLE_H:
                    return win, HIT_CLOSE
                if px <= x + TITLE_H:
                    return win, HIT_COLLAPSE
                return win, HIT_TITLE
            return win, HIT_BODY
        return None, None

    def press(self, px, py, shift=False, double=False):
        """Returns the window whose body received the press, or None (chrome / nothing)."""
        win, zone = self.hit(px, py)
        if win is None:
            return None
        modal = self.modal_window()
        if modal is not None and win is not modal:
            self.raise_window(modal)
            return None
        self.raise_window(win)
        if zone == HIT_CLOSE:
            self.close(win)
            return None
        if zone == HIT_COLLAPSE:
            win.collapsed = not win.collapsed
            self.persist()
            return None
        if zone == HIT_TITLE:
            if double:  # ImGui folds on a double-click of the title bar
                win.collapsed = not win.collapsed
                self.persist()
                return None
            if win.movable:
                self._window_drag = (win, px - win.x, py - win.y)
                # a drag takes the window alone (it detaches from its neighbours and snaps
                # again where it is dropped); Shift-drag moves the whole stuck group
                self._drag_followers = [] if not shift else [
                    (o, o.x - win.x, o.y - win.y) for o in self.stuck_group(win) if o is not win]
            return None
        if zone == HIT_RESIZE and win.resizable:
            self._window_resize = (win, px, py, win.w, win.h)
            return None
        self._window_body_drag = win
        return win

    def close(self, win):
        win.visible = False
        if win.on_close:
            win.on_close()
        self.persist()

    def dragging_body(self):
        return self._window_body_drag

    def drag(self, px, py):
        """Continue a window move or resize. Returns whether a window moved."""
        width, height = self.size
        if self._window_drag is not None:
            win, dx, dy = self._window_drag
            followers = [(o, ox, oy) for o, ox, oy in self._drag_followers if o in self.windows]
            skip = {win.key} | {o.key for o, _ox, _oy in followers}
            new_x, new_y, stuck_keys = self._snap_to_windows(win, px - dx, py - dy, skip)
            _x, _y, fw, fh = win.frame()
            new_x, new_y, anchor = snap(new_x, new_y, fw, fh, float(width), float(height), self.top)
            if followers:
                # the group travels rigidly: stop the lead where a follower would leave the viewport
                xs = [new_x] + [new_x + ox for _o, ox, _oy in followers]
                ys = [new_y] + [new_y + oy for _o, _ox, oy in followers]
                rights = [new_x + fw] + [new_x + ox + o.frame()[2] for o, ox, _oy in followers]
                bottoms = [new_y + fh] + [new_y + oy + o.frame()[3] for o, _ox, oy in followers]
                new_x += max(0.0, -min(xs)) - max(0.0, max(rights) - width)
                new_y += max(0.0, self.top - min(ys)) - max(0.0, max(bottoms) - height)
                # glued only to an edge the lead still touches after that
                new_x, new_y, anchor = snap(new_x, new_y, fw, fh, float(width), float(height),
                                            self.top, 0.5)
            win.x, win.y = new_x, new_y
            win.anchor = anchor
            self._snap_hint = tuple(anchor.split("-")) if anchor else ()
            self._snap_hint_keys = stuck_keys
            for other, offx, offy in followers:
                other.x, other.y, other.anchor = win.x + offx, win.y + offy, None
            self.layout(width, height)
            return True
        if self._window_resize is not None:
            win, ox, oy, ow, oh = self._window_resize
            w = max(ow + (px - ox), win.floor_w())
            h = max(oh + (py - oy), win.floor_h())
            w, h, edges, keys = self._snap_resize(win, w, h, width, height)
            win.w, win.h = w, h
            win.desired_w, win.desired_h = win.w, win.h
            self._snap_hint, self._snap_hint_keys = edges, keys
            self.layout(width, height)
            return True
        return False

    def release(self):
        moved = self._window_drag is not None or self._window_resize is not None
        was = self._window_drag or self._window_resize
        self._window_drag = None
        self._window_resize = None
        self._window_body_drag = None
        self._drag_followers = []
        self._snap_hint = ()
        self._snap_hint_keys = set()
        if moved:
            self.persist()
        return was

    @staticmethod
    def _frames_touch(a, b, slack=2.0):
        """chimol: two frames share an edge (flush within slack, spans overlapping)."""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        h_overlap = min(ax + aw, bx + bw) - max(ax, bx)
        v_overlap = min(ay + ah, by + bh) - max(ay, by)
        beside = abs((ax + aw) - bx) <= slack or abs((bx + bw) - ax) <= slack
        stacked = abs((ay + ah) - by) <= slack or abs((by + bh) - ay) <= slack
        return (beside and v_overlap > 0) or (stacked and h_overlap > 0)

    def stuck_group(self, win):
        """chimol _stuck_group: the windows transitively touching *win*, including it."""
        candidates = [o for o in self.windows if o.visible and o.movable and not o.modal]
        group, ordered, grew = {win.key}, [win], True
        while grew:
            grew = False
            for other in candidates:
                if other.key in group:
                    continue
                if any(self._frames_touch(m.frame(), other.frame()) for m in ordered):
                    group.add(other.key)
                    ordered.append(other)
                    grew = True
        return ordered

    def _snap_resize(self, win, w, h, width, height):
        """Snap a resized window's right and bottom edges to the viewport and to other
        windows' edges (flush against them, or level with them)."""
        x, y = win.x, win.y
        right, bottom = x + w, y + h
        edges = []
        best_r, best_b = STICK + 1.0, STICK + 1.0
        snap_r, snap_b, key_r, key_b = None, None, None, None
        if abs(width - right) <= SNAP_DISTANCE:
            snap_r, best_r = float(width), 0.0
            edges.append("right")
        if abs(height - bottom) <= SNAP_DISTANCE:
            snap_b, best_b = float(height), 0.0
            edges.append("bottom")
        for other in self.windows:
            if other is win or not other.visible:
                continue
            ox, oy, ow, oh = other.frame()
            v_overlap = min(bottom, oy + oh) - max(y, oy)
            h_overlap = min(right, ox + ow) - max(x, ox)
            for target in (ox, ox + ow):  # flush against its left side, or level with its right
                d = abs(right - target)
                if target > x and d < best_r and (v_overlap > -STICK or target == ox + ow):
                    snap_r, best_r, key_r = target, d, other.key
            for target in (oy, oy + oh):
                d = abs(bottom - target)
                if target > y and d < best_b and (h_overlap > -STICK or target == oy + oh):
                    snap_b, best_b, key_b = target, d, other.key
        if snap_r is not None:
            w = max(snap_r - x, win.floor_w())
        if snap_b is not None:
            h = max(snap_b - y, win.floor_h())
        keys = {k for k in (key_r if best_r > 0 or "right" not in edges else None,
                            key_b if best_b > 0 or "bottom" not in edges else None) if k}
        return w, h, tuple(edges), keys

    def _snap_to_windows(self, win, x, y, skip=()):
        """chimol _snap_to_windows: flush against other windows' edges, align the perpendicular edge."""
        _fx, _fy, w, h = win.frame()
        hit_keys = set()
        for other in self.windows:
            if other is win or other.key in skip or not other.visible:
                continue
            ox, oy, ow, oh = other.frame()
            v_overlap = min(y + h, oy + oh) - max(y, oy)
            h_overlap = min(x + w, ox + ow) - max(x, ox)
            snapped = False
            if v_overlap > 0:
                if abs((x + w) - ox) <= STICK:
                    x, snapped = ox - w, True
                elif abs((ox + ow) - x) <= STICK:
                    x, snapped = ox + ow, True
            if h_overlap > 0:
                if abs((y + h) - oy) <= STICK:
                    y, snapped = oy - h, True
                elif abs((oy + oh) - y) <= STICK:
                    y, snapped = oy + oh, True
            if snapped:
                if abs(y - oy) <= STICK:
                    y = oy
                if abs(x - ox) <= STICK:
                    x = ox
                hit_keys.add(other.key)
        return x, y, hit_keys
