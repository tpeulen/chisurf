"""A survey: a large area imaged tile by tile, its molecules picked and measured on each tile.

The geometry and the bookkeeping, Qt- and GUI-free; the Record tool's ``record_survey`` runs it
(image a tile, auto-pick, measure the points, on to the next tile).

* :func:`piezo_range` -- the stage range a scanner reports (its ``x_um`` / ``y_um`` limits;
  0-100 µm on the E-725 and its simulator).
* :func:`plan_tiles` -- tiles of a given size covering an area with an overlap, every tile
  clamped into the stage range, visited in an **outward square spiral** from the start position
  (the tile where the user focused first, then ring by ring: a coverslip is rarely flat, so the
  tiles nearest the focused spot are the ones most likely in focus), or in serpentine rows.
* :func:`keep_picks` -- the picks a tile may measure: away from its edges by a guard band (a spot
  cut by the edge is measured from the tile that holds it whole), within the stage range, and not
  a molecule an earlier tile has measured already (overlaps).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["DEFAULT_RANGE", "Tile", "keep_picks", "piezo_range", "plan_tiles", "spiral_cells"]

#: The stage range without a scanner that says otherwise (the E-725's 0-100 µm).
DEFAULT_RANGE = ((0.0, 100.0), (0.0, 100.0))


@dataclass
class Tile:
    """One tile of a survey: its place in the grid and its corner on the stage (µm).

    ``state`` is ``pending``, ``current``, ``done`` (molecules measured), ``empty`` (fewer than
    the minimum found) or ``failed``.
    """

    index: int
    row: int
    col: int
    x0_um: float
    y0_um: float
    width_um: float
    height_um: float
    state: str = "pending"
    found: int = 0
    measured: int = 0
    note: str = ""

    def contains(self, x: float, y: float, guard_um: float = 0.0) -> bool:
        """Whether *(x, y)* lies inside the tile, at least *guard_um* from its edges."""
        return (self.x0_um + guard_um <= x <= self.x0_um + self.width_um - guard_um
                and self.y0_um + guard_um <= y <= self.y0_um + self.height_um - guard_um)


def piezo_range(scanner: Any = None) -> tuple[tuple[float, float], tuple[float, float]]:
    """The stage's ``((x_min, x_max), (y_min, y_max))`` in µm: the scanner's ``x_um`` / ``y_um``
    limits as its driver describes them, else :data:`DEFAULT_RANGE`."""
    device = getattr(scanner, "device", None)
    if device is None:
        return DEFAULT_RANGE
    try:
        props = device.schema()["params_schema"]["properties"]
        return tuple(
            (float(props[k]["minimum"]), float(props[k]["maximum"])) for k in ("x_um", "y_um")
        )  # type: ignore[return-value]
    except Exception:  # noqa: BLE001 - a scanner without limits in its schema
        return DEFAULT_RANGE


def _starts(lo: float, length: float, tile: float, step: float) -> list[float]:
    """Tile starts along one axis covering ``[lo, lo + length]``; the last one ends at the end."""
    if length <= tile:
        return [lo]
    out = [lo]
    while out[-1] + tile < lo + length - 1e-9:
        out.append(min(out[-1] + step, lo + length - tile))
    return out


def spiral_cells(rows: int, cols: int, start: tuple[int, int]) -> list[tuple[int, int]]:
    """Every cell of a *rows* x *cols* grid once, in a square spiral out of *start* ``(row,
    col)``: the start, then each ring around it (right, down, left, up with growing legs);
    cells outside the grid are passed over."""
    r, c = start
    out = [(r, c)] if 0 <= r < rows and 0 <= c < cols else []
    leg, moves = 1, ((0, 1), (1, 0), (0, -1), (-1, 0))
    k = 0
    while len(out) < rows * cols:
        for _ in range(2):
            dr, dc = moves[k % 4]
            for _ in range(leg):
                r, c = r + dr, c + dc
                if 0 <= r < rows and 0 <= c < cols:
                    out.append((r, c))
            k += 1
        leg += 1
    return out


def plan_tiles(area: tuple[float, float, float, float], tile_um: tuple[float, float], *,
               overlap_um: float = 0.0,
               stage: tuple[tuple[float, float], tuple[float, float]] = DEFAULT_RANGE,
               order: str = "spiral", start_um: tuple[float, float] | None = None,
               ) -> list[Tile]:
    """Tiles of *tile_um* covering *area* ``(x0, y0, width, height)``.

    The area is first clamped into *stage*; tiles step by ``tile - overlap`` and the last tile of
    a row (column) is shifted back so it ends on the area's edge -- every tile lies wholly inside
    the stage range. *order* ``"spiral"`` (default) starts with the tile nearest *start_um* (the
    stage position the user focused at; the area's centre when ``None``) and spirals outward;
    ``"serpentine"`` goes row by row, alternating direction.
    """
    (sx0, sx1), (sy0, sy1) = stage
    tw, th = float(tile_um[0]), float(tile_um[1])
    if tw <= 0 or th <= 0:
        raise ValueError("a tile needs a width and a height")
    x0 = min(max(float(area[0]), sx0), sx1)
    y0 = min(max(float(area[1]), sy0), sy1)
    x1 = min(max(float(area[0]) + float(area[2]), x0), sx1)
    y1 = min(max(float(area[1]) + float(area[3]), y0), sy1)
    tw, th = min(tw, sx1 - sx0), min(th, sy1 - sy0)
    # an area smaller than a tile still gets one tile, kept inside the stage
    x0, y0 = min(x0, sx1 - tw), min(y0, sy1 - th)
    overlap = max(0.0, float(overlap_um))
    xs = _starts(x0, max(x1 - x0, tw), tw, max(tw - overlap, tw * 0.05))
    ys = _starts(y0, max(y1 - y0, th), th, max(th - overlap, th * 0.05))
    if order == "serpentine":
        cells = [(r, c) for r in range(len(ys))
                 for c in (range(len(xs)) if r % 2 == 0 else reversed(range(len(xs))))]
    elif order == "spiral":
        sx, sy = start_um if start_um is not None else ((x0 + x1) / 2, (y0 + y1) / 2)

        def nearest(starts, size, v):
            return min(range(len(starts)), key=lambda i: abs(starts[i] + size / 2 - v))

        cells = spiral_cells(len(ys), len(xs), (nearest(ys, th, sy), nearest(xs, tw, sx)))
    else:
        raise ValueError(f"order: {order!r} is not 'spiral' or 'serpentine'")
    return [Tile(i, r, c, float(xs[c]), float(ys[r]), tw, th) for i, (r, c) in enumerate(cells)]


def keep_picks(picks: list[tuple[float, float]], tile: Tile, *, guard_um: float,
               taken: list[tuple[float, float]], same_um: float,
               stage: tuple[tuple[float, float], tuple[float, float]] = DEFAULT_RANGE,
               ) -> tuple[list[int], dict[str, int]]:
    """The indices of *picks* the tile measures, and how many each rule left out.

    Rules: inside the tile at least *guard_um* from its edges (``edge``), on the stage
    (``range``), and further than *same_um* from every molecule measured before (``measured``).
    """
    (sx0, sx1), (sy0, sy1) = stage
    keep: list[int] = []
    skipped = {"edge": 0, "range": 0, "measured": 0}
    for i, (x, y) in enumerate(picks):
        if not tile.contains(x, y, guard_um):
            skipped["edge"] += 1
        elif not (sx0 <= x <= sx1 and sy0 <= y <= sy1):
            skipped["range"] += 1
        elif any((x - a) ** 2 + (y - b) ** 2 <= same_um**2 for a, b in taken):
            skipped["measured"] += 1
        else:
            keep.append(i)
    return keep, skipped
