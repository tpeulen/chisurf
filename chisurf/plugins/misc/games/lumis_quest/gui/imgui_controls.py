"""ImGui-style menu controls for Lumis Quest, drawn onto a chigame scene.

The controls themselves are Chimol's painter-level widgets
(:mod:`chisurf.plugins.chimol.chimol.renderer.ui.widgets`) -- state, hit tests
and drawing, all against six rectangle-and-text operations. Nothing here
reimplements them.

What is here is the *seam*. Chimol hands a widget a
:class:`~chimol.renderer.ui.painter.Painter` and a top-left box; the game has a
:class:`~chisurf.gui.chigame.scene.Scene` and thinks in world units around a
centre. :class:`ScenePainterAdapter` is the first half of that, and the thin
subclasses below are the second: they add the game's ``draw(scene, at=...,
width=..., height=..., scale=..., selected=...)`` signature and delegate to the
Chimol drawing underneath.

That second half is not decoration. Re-exporting the Chimol classes directly
gave every menu row a control whose ``draw`` took a painter, and the pause menu
called it with a scene -- which is a ``TypeError`` on the frame the menu opens,
in a game that had otherwise been tested. :func:`test_imgui_controls
<...test.test_imgui_controls>` now draws every control through a recording
scene for exactly that reason.
"""

from __future__ import annotations

from typing import Sequence, Tuple

from chisurf.plugins.chimol.chimol.renderer.ui import widgets as _widgets
from chisurf.plugins.chimol.chimol.renderer.ui.painter import (
    ALIGN_HCENTER,
    ALIGN_RIGHT,
)

__all__ = [
    "SliderFloat",
    "ColorEdit4",
    "Table",
    "Checkbox",
    "Combo",
    "Button",
    "ProgressBar",
    "TreeNode",
    "Separator",
    "Toggle",
    "RadioGroup",
    "InputInt",
    "ListBox",
    "Tabs",
    "PlotLines",
    "Histogram",
    "Tooltip",
    "TextInput",
    "ACCENT_COLORS",
    "ScenePainterAdapter",
]

# ImGui StyleColorsDark accent palette
ACCENT_COLORS: dict[str, tuple[float, float, float, float]] = {
    "Gold": (0.96, 0.88, 0.50, 1.0),
    "Cyan": (0.35, 0.85, 0.95, 1.0),
    "Emerald": (0.35, 0.90, 0.45, 1.0),
    "Ruby": (0.95, 0.40, 0.45, 1.0),
    "Violet": (0.80, 0.50, 0.95, 1.0),
}

#: Behind the row the cursor is on. Dim enough that the control still reads,
#: bright enough that it is the first thing the eye lands on.
SELECTED_BG: tuple[float, float, float, float] = (0.28, 0.24, 0.12, 0.92)


class ScenePainterAdapter:
    """Chimol's :class:`Painter` interface, drawn into a chigame scene.

    Parameters
    ----------
    scene : chisurf.gui.chigame.scene.Scene
        Frame under construction.
    scale : float, optional
        View scale, so hairlines stay hairlines when the camera zooms.
    text_height : float, optional
        Cell height for text, in world units. The painter interface passes a
        *box* to draw text in and leaves the size to the implementation; the
        game's rows are one line tall, so the height comes from the row.
    """

    def __init__(self, scene, scale: float = 1.0, text_height: float = 10.0) -> None:
        self.scene = scene
        self.scale = float(scale)
        self.text_height = float(text_height)
        self._clip_stack: list[tuple[float, float, float, float]] = []

    # ------------------------------------------------------------------ #
    def _color(self, c: Sequence) -> tuple[float, float, float, float]:
        """Accept either 0-255 ints (Chimol) or 0-1 floats (the game)."""
        values = [float(v) for v in c]
        if len(values) < 4:
            values = values + ([255.0] if any(v > 1.0 for v in values) else [1.0]) * (4 - len(values))
        if any(v > 1.0 for v in values):
            return (values[0] / 255.0, values[1] / 255.0, values[2] / 255.0, values[3] / 255.0)
        return (values[0], values[1], values[2], values[3])

    # ------------------------------------------------------------------ #
    def fill_rect(self, x: float, y: float, w: float, h: float, colour) -> None:
        """Fill the box whose top-left corner is ``(x, y)``."""
        if w <= 0.0 or h <= 0.0:
            return
        self.scene.draw("ui", "bar", at=(x + w * 0.5, y + h * 0.5), size=(w, h),
                        color=self._color(colour))

    def stroke_rect(self, x: float, y: float, w: float, h: float, edge, fill=None) -> None:
        """Draw an outline, optionally over a fill."""
        if fill is not None:
            self.fill_rect(x, y, w, h, fill)
        edge_col = self._color(edge)
        t = max(1.0 * self.scale, 0.5)
        self.scene.draw("ui", "bar", at=(x + w * 0.5, y), size=(w, t), color=edge_col)
        self.scene.draw("ui", "bar", at=(x + w * 0.5, y + h), size=(w, t), color=edge_col)
        self.scene.draw("ui", "bar", at=(x, y + h * 0.5), size=(t, h), color=edge_col)
        self.scene.draw("ui", "bar", at=(x + w, y + h * 0.5), size=(t, h), color=edge_col)

    def gradient_rect(self, x: float, y: float, w: float, h: float, stops: Sequence, edge=None) -> None:
        """Fill with the first stop. The sprite batch has no gradient quad."""
        self.fill_rect(x, y, w, h, stops[0] if len(stops) else (50, 50, 50))

    def text(self, x: float, y: float, w: float, h: float, align: int, string: str,
             colour, bold: bool = False) -> None:
        """Draw a string inside a box, honouring the horizontal alignment.

        Vertical alignment is always centred: the scene anchors a line by its
        middle, and every box a control asks for is one line tall.
        """
        col = self._color(colour)
        if align & ALIGN_HCENTER:
            anchor, side = x + w * 0.5, "center"
        elif align & ALIGN_RIGHT:
            anchor, side = x + w, "right"
        else:
            anchor, side = x, "left"
        self.scene.text(string, at=(anchor, y + h * 0.5),
                        height=min(self.text_height, h * 0.9), color=col, align=side)

    # ------------------------------------------------------------------ #
    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Push a clip rectangle.

        Recorded rather than applied: the sprite batch clips nothing, and every
        control here is drawn into a box the menu already sized to fit. The
        stack is kept so a control that reads it back gets an honest answer.
        """
        self._clip_stack.append((x, y, w, h))

    def pop_clip(self) -> None:
        """Pop the innermost clip rectangle."""
        if self._clip_stack:
            self._clip_stack.pop()

    def text_width(self, string: str) -> float:
        """Advance width of ``string`` in world units, measured on the font."""
        font = getattr(self.scene, "font", None)
        if font is not None and hasattr(font, "measure"):
            return float(font.measure(string, self.text_height))
        return len(string) * self.text_height * 0.6

    def line_height(self) -> float:
        """Height of one line in world units."""
        return self.text_height * 1.2


class _SceneWidget:
    """Adds the game's scene-native ``draw`` to a Chimol painter widget.

    The mixin owns the whole conversion: the game gives a **centre** and a size
    in world units, Chimol wants a **top-left** corner, and the row under the
    cursor wants a highlight behind whatever the control drew.
    """

    def draw(
        self,
        scene,
        at: Tuple[float, float],
        width: float,
        height: float,
        scale: float = 1.0,
        selected: bool = False,
        text_height: float | None = None,
    ) -> None:
        """Draw the control into a scene.

        Parameters
        ----------
        scene : chisurf.gui.chigame.scene.Scene
            Frame under construction.
        at : tuple of float
            Centre of the control, in world units.
        width, height : float
            Size in world units.
        scale : float, optional
            View scale, for hairline thickness and text size.
        selected : bool, optional
            Draw the cursor highlight behind the control.
        text_height : float, optional
            Cell height for text. Defaults to filling the control, which is
            right for a one-line row and wrong for anything taller than its
            own text -- a tab strip, a list, a plot -- so those pass their own.
        """
        painter = ScenePainterAdapter(
            scene, scale=scale,
            text_height=height * 0.92 if text_height is None else float(text_height),
        )
        x = float(at[0]) - width * 0.5
        y = float(at[1]) - height * 0.5
        if selected:
            pad = 2.0 * scale
            painter.fill_rect(x - pad * 2.0, y - pad, width + pad * 4.0,
                              height + pad * 2.0, SELECTED_BG)
        super().draw(painter, x, y, width, height)


class SliderFloat(_SceneWidget, _widgets.SliderFloat):
    """A floating-point slider, drawn onto a chigame scene."""


class Table(_SceneWidget, _widgets.Table):
    """A multi-column table, drawn onto a chigame scene."""


class Checkbox(_SceneWidget, _widgets.Checkbox):
    """A checkbox, drawn onto a chigame scene."""


class Combo(_SceneWidget, _widgets.Combo):
    """A ``< value >`` cycling selector, drawn onto a chigame scene."""


class Button(_SceneWidget, _widgets.Button):
    """An action button, drawn onto a chigame scene."""


class ProgressBar(_SceneWidget, _widgets.ProgressBar):
    """A progress bar, drawn onto a chigame scene."""


class TreeNode(_SceneWidget, _widgets.TreeNode):
    """A collapsible node, drawn onto a chigame scene."""


class Separator(_SceneWidget, _widgets.Separator):
    """A captioned rule, drawn onto a chigame scene."""


class Toggle(_SceneWidget, _widgets.Toggle):
    """An on/off switch, drawn onto a chigame scene."""


class RadioGroup(_SceneWidget, _widgets.RadioGroup):
    """A row of exclusive options, drawn onto a chigame scene."""


class InputInt(_SceneWidget, _widgets.InputInt):
    """A whole-number stepper, drawn onto a chigame scene."""


class ListBox(_SceneWidget, _widgets.ListBox):
    """A scrolling list, drawn onto a chigame scene."""


class Tabs(_SceneWidget, _widgets.Tabs):
    """A tab strip, drawn onto a chigame scene."""


class PlotLines(_SceneWidget, _widgets.PlotLines):
    """A sparkline, drawn onto a chigame scene."""


class Histogram(_SceneWidget, _widgets.Histogram):
    """A bar chart, drawn onto a chigame scene."""


class Tooltip(_SceneWidget, _widgets.Tooltip):
    """A framed floating box, drawn onto a chigame scene."""


class TextInput(_SceneWidget, _widgets.TextInput):
    """A one-line editable field, drawn onto a chigame scene."""


class ColorEdit4(_SceneWidget, _widgets.ColorEdit4):
    """A colour swatch, drawn onto a chigame scene.

    The colour is kept exactly as the game passed it -- the game speaks in 0-1
    floats and :class:`ScenePainterAdapter` understands them, so rounding the
    accent tone to 0-255 ints on the way in would only lose precision that has
    to survive a round trip through the options menu.
    """

    def __init__(self, label: str = "", color: Sequence = (1.0, 1.0, 1.0, 1.0)) -> None:
        self.label = label
        self.color = tuple(color)
