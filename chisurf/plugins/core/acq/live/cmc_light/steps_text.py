"""Compact text form of a step sequence, for typing or pasting sequences.

    1000 B; 100 -; 500 G+R; 2ms 1+2+3; 0.5s blue

One step per ';' or line: a duration (us by default, or with a us/ms/s unit)
followed by the lasers that are on: channel numbers, channel names or their
first letters joined with '+', or '-' for a dark step.
"""


def _duration_us(tok):
    t = tok.strip().lower()
    for unit, scale in (("us", 1), ("ms", 1000), ("s", 1000000)):
        if t.endswith(unit):
            return int(round(float(t[: -len(unit)]) * scale))
    return int(round(float(t)))


def parse(text, channel_names):
    """-> [(duration_us, mask), ...]; raises ValueError with a readable message."""
    names = [n.lower() for n in channel_names]
    steps = []
    for i, raw in enumerate(text.replace("\n", ";").split(";"), 1):
        part = raw.strip()
        if not part:
            continue
        fields = part.split(None, 1)
        try:
            dur = _duration_us(fields[0])
        except ValueError:
            raise ValueError("step %d: bad duration %r" % (i, fields[0]))
        if dur < 1:
            raise ValueError("step %d: duration must be >= 1 us" % i)
        mask = 0
        spec = fields[1].strip() if len(fields) > 1 else "-"
        if spec not in ("-", "0", "off", "dark"):
            for tok in spec.replace(",", "+").split("+"):
                tok = tok.strip().lower()
                if tok.isdigit() and 1 <= int(tok) <= len(names):
                    k = int(tok) - 1
                elif tok in names:
                    k = names.index(tok)
                else:
                    initials = [j for j, n in enumerate(names) if n[:1] == tok]
                    if len(tok) != 1 or len(initials) != 1:
                        raise ValueError("step %d: unknown laser %r" % (i, tok))
                    k = initials[0]
                mask |= 1 << k
        steps.append((dur, mask))
    if not steps:
        raise ValueError("no steps")
    return steps


def format_steps(steps, channel_names):
    out = []
    for dur, mask in steps:
        on = [channel_names[k][:1].upper() for k in range(len(channel_names)) if mask >> k & 1]
        out.append("%d %s" % (dur, "+".join(on) if on else "-"))
    return "; ".join(out)


# --------------------------------------------------------------------------- #
# CSV: one row per step
#
#     duration_us,blue,green,red
#     1000,1,0,0
#     100,0,0,0
#
# The duration column may be duration_us, duration_ms or duration_s; laser
# columns are matched by name or number (1, 2, 3); cells are 1/0, on/off,
# yes/no, x/blank. Lines starting with '#' are comments.

_TRUE = {"1", "on", "yes", "y", "true", "x"}
_FALSE = {"0", "off", "no", "n", "false", "", "-"}


def parse_csv(text, channel_names):
    import csv
    import io

    names = [n.lower() for n in channel_names]
    rows = [r for r in csv.reader(io.StringIO(text))
            if r and not r[0].strip().startswith("#") and any(c.strip() for c in r)]
    if not rows:
        raise ValueError("CSV has no rows")
    header = [h.strip().lower() for h in rows[0]]
    scale = {"duration_us": 1, "duration_ms": 1000, "duration_s": 1000000,
             "us": 1, "ms": 1000, "s": 1000000}.get(header[0])
    if scale is None:
        raise ValueError("first column must be duration_us, duration_ms or duration_s "
                         "(got %r)" % rows[0][0])
    columns = []
    for h in header[1:]:
        if h.isdigit() and 1 <= int(h) <= len(names):
            columns.append(int(h) - 1)
        elif h in names:
            columns.append(names.index(h))
        else:
            raise ValueError("unknown laser column %r (use %s or 1..%d)"
                             % (h, "/".join(names), len(names)))
    steps = []
    for line_no, row in enumerate(rows[1:], 2):
        try:
            dur = int(round(float(row[0]) * scale))
        except (ValueError, IndexError):
            raise ValueError("row %d: bad duration %r" % (line_no, row[0] if row else ""))
        if dur < 1:
            raise ValueError("row %d: duration must be >= 1 us" % line_no)
        mask = 0
        for col, k in enumerate(columns, 1):
            cell = row[col].strip().lower() if col < len(row) else ""
            if cell in _TRUE:
                mask |= 1 << k
            elif cell not in _FALSE:
                raise ValueError("row %d: %s must be 1/0, got %r" % (line_no, header[col], row[col]))
        steps.append((dur, mask))
    if not steps:
        raise ValueError("CSV has a header but no steps")
    return steps


def format_csv(steps, channel_names):
    out = ["duration_us," + ",".join(channel_names)]
    for dur, mask in steps:
        out.append("%d,%s" % (dur, ",".join("1" if mask >> k & 1 else "0"
                                            for k in range(len(channel_names)))))
    return "\n".join(out) + "\n"
