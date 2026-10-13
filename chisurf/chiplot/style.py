"""Backend-neutral styling value objects for chiplot.

Small, immutable, backend-independent descriptions of *how* a plot element
looks (the successors of the ``mkPen`` / ``mkBrush`` / ``mkColor`` / ``colormap``
helpers of the retired pyqtgraph backend). A backend translates them into its
own pen/brush/lookup-table objects.

Nothing here imports a plotting backend or Qt, so styles can be constructed in
Qt-free code (view specs, model definitions) and rendered anywhere. Colour
names are the SVG/CSS set (read from emtk's colour table, case and spaces
ignored, as Qt read them); a ``QColor`` is still accepted, by its channels.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

# Single-letter color codes (matplotlib / pyqtgraph idiom) that ``QColor``
# does not understand on its own. Kept for drop-in compatibility with the many
# ``mkPen("r")`` / ``"y"`` call sites being migrated.
_SHORT_COLORS: dict[str, tuple[int, int, int, int]] = {
    "r": (255, 0, 0, 255),
    "g": (0, 255, 0, 255),
    "b": (0, 0, 255, 255),
    "c": (0, 255, 255, 255),
    "m": (255, 0, 255, 255),
    "y": (255, 255, 0, 255),
    "k": (0, 0, 0, 255),
    "w": (255, 255, 255, 255),
    "d": (150, 150, 150, 255),  # pyqtgraph: dark grey
    "l": (200, 200, 200, 255),  # pyqtgraph: light grey
    "s": (100, 100, 150, 255),  # pyqtgraph: slate
}


class LineStyle(Enum):
    """Dash pattern for a :class:`Pen`."""

    SOLID = "solid"
    DASH = "dash"
    DOT = "dot"
    DASH_DOT = "dash_dot"
    NONE = "none"


@dataclass(frozen=True)
class Color:
    """An immutable RGBA color with 0–255 integer channels.

    Construct via :func:`to_color`, which parses names (``"red"``), hex
    strings (``"#ff0000"``, ``"#ff000080"``), ``(r, g, b[, a])`` tuples with
    either 0–255 ints or 0–1 floats, a packed integer, or a ``QColor``.

    Parameters
    ----------
    r, g, b, a : int
        Channel values in ``[0, 255]``. ``a`` (alpha) defaults to opaque.
    """

    r: int
    g: int
    b: int
    a: int = 255

    def with_alpha(self, a: int) -> Color:
        """Return a copy of this color with a new alpha channel.

        Parameters
        ----------
        a : int
            New alpha in ``[0, 255]``.
        """
        return replace(self, a=int(a))

    def to_hex(self) -> str:
        """Return this color as an ``#rrggbbaa`` hex string."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}{self.a:02x}"

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Return this color as an ``(r, g, b, a)`` tuple of 0–255 ints."""
        return (self.r, self.g, self.b, self.a)


def to_color(value) -> Color:
    """Coerce a color-like value into a :class:`Color`.

    Parameters
    ----------
    value : Color, str, int, tuple, QColor, or None
        - :class:`Color` — returned unchanged.
        - ``str`` — an SVG/CSS color name or ``#rgb`` / ``#rrggbb`` /
          ``#rrggbbaa`` hex string (case and spaces in a name are ignored).
        - ``(r, g, b)`` / ``(r, g, b, a)`` — ints in ``[0, 255]`` or floats in
          ``[0, 1]`` (auto-detected: all values ``<= 1`` are treated as floats).
        - ``int`` — a packed ``0xRRGGBB`` value.
        - a ``QColor`` (anything with ``red()``/``green()``/``blue()``/``alpha()``).
        - ``None`` — returns opaque black.

    Returns
    -------
    Color

    Raises
    ------
    TypeError
        If ``value`` is not a recognised color specification.
    """
    if value is None:
        return Color(0, 0, 0)
    if isinstance(value, Color):
        return value
    if all(callable(getattr(value, name, None)) for name in ("red", "green", "blue", "alpha")):
        return Color(int(value.red()), int(value.green()), int(value.blue()), int(value.alpha()))
    if isinstance(value, str):
        if value in _SHORT_COLORS:
            return Color(*_SHORT_COLORS[value])
        # Eight hex digits are #RRGGBBAA here, the CSS spelling this module
        # documents. Qt reads the same string as #AARRGGBB, so handing it over
        # swaps alpha into red and comes back opaque: "#ff000080" (red, half
        # transparent) parsed as dark blue at full alpha, and a translucent
        # region band rendered olive. Parse it before Qt sees it.
        if len(value) == 9 and value.startswith("#"):
            try:
                r, g, b, a = (int(value[i : i + 2], 16) for i in (1, 3, 5, 7))
            except ValueError:
                raise TypeError(f"unrecognised color hex: {value!r}") from None
            return Color(r, g, b, a)
        return _named_or_hex(value)
    if isinstance(value, int):
        return Color((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    if isinstance(value, (tuple, list)):
        vals = list(value)
        if not 3 <= len(vals) <= 4:
            raise TypeError(f"color tuple must have 3 or 4 items, got {value!r}")
        # The documented rule, and only that rule: every channel <= 1 is the
        # 0–1 float scale. Requiring each item to *be* a ``float`` as well made
        # the result depend on how the caller spelled its zeros — ``(1.0, 0, 0)``
        # (the module docstring's own example) fell into the 0–255 branch and
        # truncated to near-black instead of red.
        is_float = all(v <= 1.0 for v in vals)
        if is_float:
            chans = [int(round(v * 255)) for v in vals]
        else:
            chans = [int(v) for v in vals]
        r, g, b = chans[:3]
        a = chans[3] if len(chans) == 4 else 255
        return Color(r, g, b, a)
    raise TypeError(f"cannot interpret {value!r} as a color")


def _named_or_hex(value: str) -> Color:
    """An SVG/CSS colour name or a ``#rgb`` / ``#rrggbb`` hex string as a :class:`Color`.

    Names ignore case and spaces (``"Light Blue"`` is ``lightblue``), and
    ``"transparent"`` is transparent black, as Qt's ``QColor`` read them.
    """
    from emtk import colormaps

    text = value.strip()
    key = text.replace(" ", "").lower()
    if key == "transparent":
        return Color(0, 0, 0, 0)
    try:
        r, g, b, a = colormaps.to_rgba_bytes(key if not text.startswith("#") else text)
    except ValueError:
        raise TypeError(f"unrecognised color name/hex: {value!r}") from None
    return Color(r, g, b, a)


@dataclass(frozen=True)
class Pen:
    """A line style: color, width, dash pattern.

    Replaces ``pyqtgraph.mkPen``. Construct directly (``Pen("red", width=2)``)
    or via :func:`to_pen`.

    Parameters
    ----------
    color : Color
        Line color. Use :func:`to_pen` to pass color-likes.
    width : float
        Line width in pixels. ``0`` requests a cosmetic 1-px line.
    style : LineStyle
        Dash pattern.
    cosmetic : bool
        If ``True`` the width is device-independent (does not scale with zoom).
    """

    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    width: float = 1.0
    style: LineStyle = LineStyle.SOLID
    cosmetic: bool = True


def to_pen(value, **overrides) -> Pen:
    """Coerce a pen-like value into a :class:`Pen`.

    Parameters
    ----------
    value : Pen, Color, str, tuple, int, QColor, or None
        A :class:`Pen` (returned with ``overrides`` applied) or any
        :func:`to_color`-compatible value (becomes the pen color).
    **overrides
        ``width``, ``style``, ``cosmetic``, or ``color`` to override.

    Returns
    -------
    Pen
    """
    if isinstance(value, Pen):
        base = value
    else:
        base = Pen(color=to_color(value))
    if "color" in overrides:
        overrides["color"] = to_color(overrides["color"])
    if "style" in overrides and isinstance(overrides["style"], str):
        overrides["style"] = LineStyle(overrides["style"])
    return replace(base, **overrides) if overrides else base


@dataclass(frozen=True)
class Brush:
    """A fill style.

    Replaces ``pyqtgraph.mkBrush``.

    Parameters
    ----------
    color : Color
        Fill color (may be translucent via its alpha channel).
    """

    color: Color = field(default_factory=lambda: Color(255, 255, 255))


def to_brush(value, **overrides) -> Brush:
    """Coerce a brush-like value into a :class:`Brush`.

    Parameters
    ----------
    value : Brush or color-like
        A :class:`Brush` (returned with ``overrides`` applied) or any
        :func:`to_color`-compatible value (becomes the brush color).
    **overrides
        ``color`` override.

    Returns
    -------
    Brush
    """
    if isinstance(value, Brush):
        base = value
    else:
        base = Brush(color=to_color(value))
    if "color" in overrides:
        overrides["color"] = to_color(overrides["color"])
    return replace(base, **overrides) if overrides else base


@dataclass(frozen=True)
class Colormap:
    """A named colormap reference.

    Replaces ``pyqtgraph.colormap.get``. The name is resolved by the active
    backend to a concrete lookup table; chiplot only carries the identity so
    Qt-free code can request a colormap without importing a renderer.

    Parameters
    ----------
    name : str
        A colormap identifier (e.g. ``"viridis"``, ``"inferno"``, ``"CET-L9"``).
    source : str
        Namespace hint for the backend (e.g. ``"matplotlib"``, ``"colorcet"``).
    """

    name: str = "viridis"
    source: str = "matplotlib"


def colormap(name: str, source: str = "matplotlib") -> Colormap:
    """Return a :class:`Colormap` reference by name (``chiplot.colormap("viridis")``).

    Parameters
    ----------
    name : str
        Colormap identifier.
    source : str
        Namespace hint for the backend.

    Returns
    -------
    Colormap
    """
    return Colormap(name=name, source=source)


def to_colormap(value, source: str = "matplotlib") -> Colormap | None:
    """Coerce a colormap-like value to a :class:`Colormap`.

    Parameters
    ----------
    value : str, Colormap or None
        A colormap name, an existing reference, or ``None``.
    source : str
        Namespace hint used when ``value`` is a name.

    Returns
    -------
    Colormap or None
        ``None`` is passed through so callers can mean "leave unchanged".

    Raises
    ------
    TypeError
        If ``value`` is neither a name, a :class:`Colormap`, nor ``None``.
    """
    if value is None or isinstance(value, Colormap):
        return value
    if isinstance(value, str):
        return Colormap(name=value, source=source)
    raise TypeError(f"cannot interpret {value!r} as a colormap")


def int_color(index: int, count: int = 9) -> Color:
    """Return a distinct color for an integer index (categorical palette).

    A backend-neutral replacement for ``pyqtgraph.intColor``: evenly spaced
    hues around the color wheel so successive indices are visually distinct.

    Parameters
    ----------
    index : int
        Item index.
    count : int
        Number of hues to spread across the wheel before repeating.

    Returns
    -------
    Color
    """
    hue = (index % count) / float(max(count, 1))
    return Color(*_hsv_bytes(hue % 1.0), 255)


def _hsv_bytes(hue: float) -> tuple[int, int, int]:
    """Fully saturated, full-value ``hue`` (0..1) as 0..255 RGB, rounded as ``QColor.fromHsvF``.

    Qt stores the hue in 1/100 degree and the channels in 16 bits, then reduces to
    8 bits; doing the same keeps every palette colour identical to what the
    Qt-backed version drew.
    """
    hue_c = int(round(hue * 36000.0))
    h = 0.0 if hue_c == 36000 else hue_c / 6000.0
    i = int(h)
    f = h - i
    v = s = 1.0
    p = v * (1.0 - s)
    if i & 1:
        q = v * (1.0 - (s * f))
        r, g, b = {1: (q, v, p), 3: (p, q, v), 5: (v, p, q)}[i]
    else:
        t = v * (1.0 - (s * (1.0 - f)))
        r, g, b = {0: (v, t, p), 2: (p, v, t), 4: (t, p, v)}[i]

    def eight(channel: float) -> int:
        wide = int(channel * 65535.0 + 0.5)
        return (2 * wide + 257) // 514  # wide / 257, rounded half up

    return eight(r), eight(g), eight(b)
