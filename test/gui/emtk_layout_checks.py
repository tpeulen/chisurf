"""Layout assertions for emtk tool windows, read from what a draw recorded.

A recorded draw (:class:`emtk.testing.RecordingPainter`) keeps every string with the box it was placed in,
and the apps keep the rect of each control they named (``item_rects``). That is enough to check what the
screenshots show: nothing outside the window, no two texts on top of each other, a pictogram set clear of
its caption, short inputs not as wide as the window, and a control above another where the form says so.
"""

from __future__ import annotations

from emtk.testing import RecordingPainter

SIZES = [(1200, 800), (800, 600)]

#: A control narrower than this is "short" (a stride, a count, a matrix cell): never the window's width.
SHORT_MAX = 140.0


def draw(app, size, frames: int = 3) -> RecordingPainter:
    """Draw *app* ``frames`` times into a window of *size* and return the last recording."""
    painter = RecordingPainter()
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def boxes(painter: RecordingPainter) -> list[tuple[float, float, float, float, str]]:
    """``(x, y, w, h, string)`` of every drawn string that has a width."""
    return [(x, y, w, h, s) for x, y, w, h, _a, s, *_ in painter.texts if s.strip() and w > 0]


def _overlap(a, b) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def assert_texts_apart(
    painter: RecordingPainter, region: tuple | None = None, slack: float = 1.0
) -> None:
    """No two strings (inside *region* ``(x, y, w, h)``, default everywhere) overlap by more than *slack* px²."""
    found = [b for b in boxes(painter) if region is None or _overlap(b[:4], region) > 0]
    for i, a in enumerate(found):
        for b in found[i + 1 :]:
            assert _overlap(a[:4], b[:4]) <= slack, f"text {a[4]!r} overlaps {b[4]!r}"


def assert_inside(rects: dict, size: tuple, names=None, margin: float = 0.5) -> None:
    """Every named rect (default: all) lies inside the window."""
    for name in names or rects:
        x, y, w, h = rects[name]
        assert x >= -margin and y >= -margin, f"{name} starts outside the window: {rects[name]}"
        assert x + w <= size[0] + margin, f"{name} is cut off at the right edge: {rects[name]}"
        assert y + h <= size[1] + margin, f"{name} is cut off at the bottom: {rects[name]}"


def assert_disjoint(rects: dict, names, slack: float = 1.0) -> None:
    """The named rects do not overlap one another."""
    names = list(names)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert _overlap(rects[a], rects[b]) <= slack, (
                f"{a} overlaps {b}: {rects[a]} / {rects[b]}"
            )


def assert_above(rects: dict, upper: str, lower: str) -> None:
    """*upper* ends at or above where *lower* starts."""
    assert rects[upper][1] + rects[upper][3] <= rects[lower][1] + 1.0, (
        f"{upper} {rects[upper]} is not above {lower} {rects[lower]}"
    )


def assert_short(rects: dict, names, limit: float = SHORT_MAX) -> None:
    """The named inputs are short fields, not stretched across the window."""
    for name in names:
        assert rects[name][2] <= limit, f"{name} is {rects[name][2]:.0f}px wide: {rects[name]}"


def assert_icons_clear(painter: RecordingPainter) -> None:
    """A button caption that opens with a colour pictogram has two spaces before the text."""
    for *_, s in boxes(painter):
        if (
            s
            and ord(s[0]) >= 0x2300
            and not 0x25A0 <= ord(s[0]) <= 0x25FF
            and len(s) > 2
            and s[1] == " "
        ):
            assert s[2] == " ", f"pictogram touches its caption: {s!r}"


def assert_aligned(rects: dict, names, tolerance: float = 1.5) -> None:
    """The named rects start at the same x (one label column)."""
    xs = [rects[n][0] for n in names]
    assert max(xs) - min(xs) <= tolerance, (
        f"fields do not start in one column: {dict(zip(names, xs))}"
    )


def assert_log_capped(rects: dict, size: tuple, key: str = "log") -> None:
    """The log is a bounded region (a few lines that scroll), not what is left of the window."""
    assert rects[key][3] <= 0.4 * size[1], f"the log fills the window: {rects[key]} in {size}"
