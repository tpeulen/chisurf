"""Edit a step sequence by dragging in the timing preview.

The sequence is periodic, so step 0's left neighbour is the last step.

* ``drag_boundary(durations, j, dt, lo)`` moves the boundary at the *start* of
  step ``j`` (1 <= j <= n-1) by ``dt``: step ``j-1`` grows, step ``j`` shrinks.
  ``j == n`` is the end of the last step: only that step changes (the period
  changes with it).
* ``move_step(durations, i, dt, lo)`` slides step ``i`` in time, keeping its own
  length: the step before it grows by ``dt`` and the step after it shrinks.

Every result keeps all durations >= ``lo``; ``dt`` is clamped to what fits.
"""

import math


def snap(dt, period):
    """Round a drag to a readable grid: about 1/200 of the period, 1-2-5 steps."""
    raw = max(1.0, period / 200.0)
    mag = 10 ** math.floor(math.log10(raw))
    for f in (1, 2, 5, 10):
        if raw <= f * mag:
            grid = f * mag
            break
    return int(round(dt / grid) * grid)


def drag_boundary(durations, j, dt, lo=1):
    d = [int(v) for v in durations]
    n = len(d)
    if n == 0:
        return d
    if j >= n:  # end of the last step
        d[-1] = max(lo, d[-1] + int(dt))
        return d
    if j <= 0:
        return d
    left, right = j - 1, j
    dt = max(lo - d[left], min(int(dt), d[right] - lo))
    d[left] += dt
    d[right] -= dt
    return d


def move_step(durations, i, dt, lo=1):
    d = [int(v) for v in durations]
    n = len(d)
    if n < 3:  # needs a neighbour on each side that is not the step itself
        return d
    before, after = (i - 1) % n, (i + 1) % n
    dt = max(lo - d[before], min(int(dt), d[after] - lo))
    d[before] += dt
    d[after] -= dt
    return d


def step_at(durations, t):
    """Index of the step containing time t (within one period)."""
    acc = 0
    for i, v in enumerate(durations):
        acc += v
        if t < acc:
            return i
    return len(durations) - 1


def boundaries(durations):
    """Start times of steps 1..n-1 and the period end, paired with their index j."""
    out, acc = [], 0
    for j, v in enumerate(durations):
        acc += v
        out.append((j + 1, acc))
    return out


# --------------------------------------------------------------------------- #
# Per-laser windows: each laser's on-windows edited on their own (they may overlap)

def laser_windows(steps, n):
    """steps -> for each laser the merged (start, end) windows it is granted within a period."""
    out = [[] for _ in range(n)]
    t = 0
    for dur, mask in steps:
        for k in range(n):
            if (mask >> k) & 1:
                if out[k] and out[k][-1][1] == t:
                    out[k][-1] = (out[k][-1][0], t + dur)
                else:
                    out[k].append((t, t + dur))
        t += dur
    return out


def steps_from_windows(windows, period, lo=1):
    """Per-laser windows -> steps covering [0, period). Edges closer than *lo* are merged."""
    n = len(windows)
    points = {0, int(period)}
    for wins in windows:
        for s, e in wins:
            points.add(max(0, min(int(period), int(s))))
            points.add(max(0, min(int(period), int(e))))
    merged = []
    for p in sorted(points):
        if not merged or p - merged[-1] >= lo:
            merged.append(p)
        elif p == period:  # keep the period end exact; drop the edge just before it
            merged[-1] = p
    if merged[-1] != period:
        merged.append(int(period))
    steps = []
    for a, b in zip(merged, merged[1:]):
        mid = (a + b) / 2.0
        mask = 0
        for k in range(n):
            if any(s <= mid < e for s, e in windows[k]):
                mask |= 1 << k
        if steps and steps[-1][1] == mask:
            steps[-1] = (steps[-1][0] + (b - a), mask)
        else:
            steps.append((b - a, mask))
    return steps


def move_window(windows, k, idx, dt, period, lo=1):
    wins = [list(w) for w in windows]
    s, e = wins[k][idx]
    dt = max(-s, min(int(dt), int(period) - e))
    wins[k][idx] = (s + dt, e + dt)
    return [[tuple(w) for w in ws] for ws in wins]


def resize_window(windows, k, idx, edge, dt, period, lo=1):
    wins = [list(w) for w in windows]
    s, e = wins[k][idx]
    if edge == "start":
        s = max(0, min(s + int(dt), e - lo))
    else:
        e = min(int(period), max(e + int(dt), s + lo))
    wins[k][idx] = (s, e)
    return [[tuple(w) for w in ws] for ws in wins]


def merge_windows(windows):
    """Sorted, merged (start, end) list; touching windows join."""
    out = []
    for s, e in sorted(windows):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
