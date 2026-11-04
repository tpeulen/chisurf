"""A small spreadsheet for step sequences, drawn through a emtk Painter.

Rows are the panel's custom steps (``[duration_us, [on per laser]]``), edited in
place. Columns: ``#``, ``duration (us)``, one 0/1 column per laser, ``start``.

Mouse: click selects a cell; click on a laser cell toggles it; double click on a
duration edits it; the ``+ new row`` line appends a row.
Keys: arrows / Tab / Shift+Tab move; digits start editing a duration; Return
commits and moves down; Esc cancels; Space or 0/1 set a laser cell; Insert adds a
row below; Ctrl+Backspace deletes the row; Ctrl+D duplicates it; Ctrl+C copies the
table as tab-separated text, Ctrl+V pastes rows (from Excel or a CSV).
"""

from __future__ import annotations

ROW_H = 22.0
HEAD_H = 24.0
NUM_W, DUR_W, LASER_W, START_W = 36.0, 110.0, 56.0, 86.0
MAX_DURATION = 60_000_000

BG = (30, 32, 38, 255)
ROW_ALT = (36, 38, 46, 255)
HEAD_BG = (52, 58, 74, 255)
GRID = (70, 74, 88, 255)
TEXT = (230, 232, 238, 255)
DIM = (150, 155, 165, 255)
SEL = (66, 150, 250, 255)
EDIT_BG = (20, 22, 28, 255)

# Qt key codes as delivered by the host (emtk.keys uses the same numbers)
K_LEFT, K_UP, K_RIGHT, K_DOWN = 0x01000012, 0x01000013, 0x01000014, 0x01000015
K_TAB, K_BACKTAB, K_BACKSPACE, K_RETURN, K_ENTER = 0x01000001, 0x01000002, 0x01000003, 0x01000004, 0x01000005
K_INSERT, K_DELETE, K_ESCAPE, K_F2 = 0x01000006, 0x01000007, 0x01000000, 0x01000031
CTRL = 0x04000000
META = 0x10000000


class StepSheet:
    def __init__(self, rows_get, rows_set, channels_get, hex_rgb, max_rows=512,
                 clipboard_get=None, clipboard_set=None):
        self.rows_get = rows_get      # -> list of [duration, [bool, ...]]
        self.rows_set = rows_set
        self.channels_get = channels_get
        self.hex_rgb = hex_rgb
        self.max_rows = max_rows
        self.clipboard_get = clipboard_get
        self.clipboard_set = clipboard_set
        self.sel = None               # (row, col) ; col 1 = duration, 2.. = lasers
        self.edit = None              # text while editing a duration
        self.top = 0
        self.focused = False
        self.message = ""
        self.min_duration = 1
        self._box = (0.0, 0.0, 0.0, 0.0)
        self._last_press = (0.0, None)

    # -- geometry --------------------------------------------------------- #
    def n_lasers(self):
        return len(self.channels_get())

    def columns(self):
        cols = [("#", NUM_W), ("duration (us)", DUR_W)]
        cols += [(c["name"], LASER_W) for c in self.channels_get()]
        cols += [("start (ms)", START_W)]
        return cols

    def visible_rows(self):
        return max(1, int((self._box[3] - HEAD_H) // ROW_H))

    def cell_at(self, px, py):
        x, y, w, h = self._box
        if not (x <= px < x + w and y + HEAD_H <= py < y + h):
            return None
        row = self.top + int((py - y - HEAD_H) // ROW_H)
        cx = x
        for col, (_, cw) in enumerate(self.columns()):
            if cx <= px < cx + cw:
                return row, col
            cx += cw
        return row, None

    # -- drawing ---------------------------------------------------------- #
    def draw(self, p, x, y, w, h):
        from emtk.painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER

        self._box = (x, y, w, h)
        rows = self.rows_get()
        cols = self.columns()
        n = self.n_lasers()
        p.fill_rect(x, y, w, h, BG)
        p.push_clip(x, y, w, h)
        try:
            cx = x
            p.fill_rect(x, y, w, HEAD_H, HEAD_BG)
            for name, cw in cols:
                p.text(cx + 4, y, cw - 8, HEAD_H, ALIGN_CENTER, name, TEXT, True)
                cx += cw
            self.top = max(0, min(self.top, max(0, len(rows) + 1 - self.visible_rows())))
            starts, t = [], 0
            for dur, _ in rows:
                starts.append(t)
                t += dur
            ry = y + HEAD_H
            for r in range(self.top, len(rows) + 1):
                if ry >= y + h:
                    break
                if r == len(rows):
                    if len(rows) < self.max_rows:
                        p.text(x + 8, ry, w, ROW_H, ALIGN_LEFT | ALIGN_VCENTER, "+ new row", DIM)
                    break
                dur, on = rows[r]
                if r % 2:
                    p.fill_rect(x, ry, w, ROW_H, ROW_ALT)
                cx = x
                for col, (_, cw) in enumerate(cols):
                    selected = self.sel == (r, col)
                    if col == 0:
                        p.text(cx, ry, cw - 6, ROW_H, ALIGN_RIGHT | ALIGN_VCENTER, str(r + 1), DIM)
                    elif col == 1:
                        text = self.edit if (selected and self.edit is not None) else str(dur)
                        if selected and self.edit is not None:
                            p.fill_rect(cx + 1, ry + 1, cw - 2, ROW_H - 2, EDIT_BG)
                            text = text + "|"
                        p.text(cx, ry, cw - 8, ROW_H, ALIGN_RIGHT | ALIGN_VCENTER, text, TEXT)
                    elif col < 2 + n:
                        k = col - 2
                        is_on = k < len(on) and on[k]
                        colour = self.hex_rgb(self.channels_get()[k]["color"], 255 if is_on else 40)
                        p.fill_rect(cx + cw / 2 - 12, ry + 4, 24, ROW_H - 8, colour)
                        p.text(cx, ry, cw, ROW_H, ALIGN_CENTER, "1" if is_on else "0",
                               (0, 0, 0, 255) if is_on else DIM)
                    else:
                        p.text(cx, ry, cw - 8, ROW_H, ALIGN_RIGHT | ALIGN_VCENTER,
                               "%.3f" % (starts[r] / 1000.0), DIM)
                    if selected:
                        p.stroke_rect(cx + 1, ry + 1, cw - 2, ROW_H - 2, SEL)
                    cx += cw
                ry += ROW_H
            # grid lines, down to the last row only
            grid_h = min(h, HEAD_H + (len(rows) - self.top) * ROW_H)
            cx = x
            for _, cw in cols:
                p.fill_rect(cx, y, 1, grid_h, GRID)
                cx += cw
            p.fill_rect(cx, y, 1, grid_h, GRID)
            p.fill_rect(x, y + grid_h - 1, cx - x, 1, GRID)
            p.fill_rect(x, y + HEAD_H - 1, w, 1, GRID)
            if len(rows) + 1 > self.visible_rows():
                frac = self.visible_rows() / float(len(rows) + 1)
                bar_h = max(16.0, (h - HEAD_H) * frac)
                bar_y = y + HEAD_H + (h - HEAD_H - bar_h) * (self.top / max(1.0, len(rows) + 1 - self.visible_rows()))
                p.fill_rect(x + w - 5, bar_y, 4, bar_h, (110, 120, 140, 255))
        finally:
            p.pop_clip()

    # -- editing helpers -------------------------------------------------- #
    def _commit(self):
        if self.edit is None or self.sel is None:
            return True
        r, _ = self.sel
        rows = self.rows_get()
        try:
            v = int(float(self.edit)) if self.edit.strip() else None
        except ValueError:
            v = None
        if v is None or not self.min_duration <= v <= MAX_DURATION:
            self.message = "duration must be %d .. %d us on this control path" % (
                self.min_duration, MAX_DURATION)
            return False
        if r < len(rows):
            rows[r][0] = v
        self.edit = None
        self.message = ""
        return True

    def _move(self, dr, dc):
        rows = self.rows_get()
        ncols = 2 + self.n_lasers()
        r, c = self.sel or (0, 1)
        c = min(max(1, c + dc), ncols - 1)
        r = min(max(0, r + dr), max(0, len(rows) - 1))
        self.sel = (r, c)
        vis = self.visible_rows()
        if r < self.top:
            self.top = r
        elif r >= self.top + vis:
            self.top = r - vis + 1

    def insert_row(self, below=True):
        rows = self.rows_get()
        if len(rows) >= self.max_rows:
            self.message = "at most %d steps" % self.max_rows
            return
        n = self.n_lasers()
        r = self.sel[0] + (1 if below else 0) if self.sel else len(rows)
        template = rows[self.sel[0]] if self.sel and self.sel[0] < len(rows) else [1000, [False] * n]
        rows.insert(min(r, len(rows)), [template[0], [False] * n])
        self.sel = (min(r, len(rows) - 1), 1)

    def delete_row(self):
        rows = self.rows_get()
        if self.sel and len(rows) > 1 and self.sel[0] < len(rows):
            rows.pop(self.sel[0])
            self._move(0, 0)

    def duplicate_row(self):
        rows = self.rows_get()
        if self.sel and self.sel[0] < len(rows) and len(rows) < self.max_rows:
            dur, on = rows[self.sel[0]]
            rows.insert(self.sel[0] + 1, [dur, list(on)])
            self._move(1, 0)

    def move_row(self, delta):
        rows = self.rows_get()
        if not self.sel:
            return
        r = self.sel[0]
        t = r + delta
        if 0 <= r < len(rows) and 0 <= t < len(rows):
            rows[r], rows[t] = rows[t], rows[r]
            self.sel = (t, self.sel[1])

    def copy_text(self):
        names = [c["name"] for c in self.channels_get()]
        lines = ["duration_us\t" + "\t".join(names)]
        for dur, on in self.rows_get():
            lines.append("%d\t%s" % (dur, "\t".join("1" if b else "0" for b in on)))
        return "\n".join(lines) + "\n"

    def paste_text(self, text):
        try:
            from . import steps_text
        except (ImportError, ValueError):
            from cmc_light import steps_text

        names = [c["name"] for c in self.channels_get()]
        body = text.replace("\t", ",").strip()
        first = body.split("\n", 1)[0].split(",")[0].strip()
        try:
            float(first)
            body = "duration_us," + ",".join(names[: max(0, len(body.split("\n", 1)[0].split(",")) - 1)]) + "\n" + body
        except ValueError:
            pass
        steps = steps_text.parse_csv(body, names)
        rows = self.rows_get()
        at = self.sel[0] if self.sel else len(rows)
        new = [[d, [bool(m >> k & 1) for k in range(len(names))]] for d, m in steps]
        if len(rows) + len(new) > self.max_rows:
            raise ValueError("pasting %d rows would exceed %d steps" % (len(new), self.max_rows))
        rows[at:at] = new
        self.sel = (at, 1)
        return len(new)

    # -- input ------------------------------------------------------------ #
    def press(self, px, py, now=0.0):
        cell = self.cell_at(px, py)
        self.focused = cell is not None
        if cell is None:
            return False
        r, c = cell
        rows = self.rows_get()
        if r >= len(rows):
            if r == len(rows) and len(rows) < self.max_rows:
                self._commit()
                rows.append([rows[-1][0] if rows else 1000, [False] * self.n_lasers()])
                self.sel = (len(rows) - 1, 1)
            return True
        if not self._commit():
            return True
        if c is None or c == 0:
            self.sel = (r, 1)
            return True
        double = self._last_press[1] == (r, c) and now - self._last_press[0] < 0.4
        self._last_press = (now, (r, c))
        if 2 <= c < 2 + self.n_lasers():
            on = rows[r][1]
            on[c - 2] = not on[c - 2]
        elif c == 1 and double:
            self.edit = str(rows[r][0])
        if c >= 2 + self.n_lasers():
            c = 1
        self.sel = (r, c)
        return True

    def scroll(self, rows):
        self.top = max(0, self.top + int(rows))

    def key(self, key, text="", modifiers=0):
        """Returns True when the key was used."""
        if not self.focused or self.sel is None:
            return False
        rows = self.rows_get()
        ctrl = bool(modifiers & (CTRL | META))
        r, c = self.sel
        n = self.n_lasers()
        ch = (text or "")[:1]
        if ctrl and key in (ord("C"), ord("c")):
            if self.clipboard_set:
                self.clipboard_set(self.copy_text())
            return True
        if ctrl and key in (ord("V"), ord("v")):
            if self.clipboard_get:
                try:
                    count = self.paste_text(self.clipboard_get() or "")
                    self.message = "pasted %d rows" % count
                except ValueError as e:
                    self.message = "paste: %s" % e
            return True
        if ctrl and key in (ord("D"), ord("d")):
            self.duplicate_row()
            return True
        if ctrl and key == K_BACKSPACE:
            self.delete_row()
            return True
        if self.edit is not None:
            if ch and (ch.isdigit() or ch in ".eE"):
                self.edit += ch
            elif key == K_BACKSPACE:
                self.edit = self.edit[:-1]
            elif key in (K_RETURN, K_ENTER):
                if self._commit():
                    self._move(1, 0)
            elif key == K_TAB:
                if self._commit():
                    self._move(0, 1)
            elif key == K_ESCAPE:
                self.edit = None
                self.message = ""
            elif key in (K_UP, K_DOWN):
                if self._commit():
                    self._move(-1 if key == K_UP else 1, 0)
            return True
        if key == K_UP:
            self._move(-1, 0)
        elif key == K_DOWN:
            self._move(1, 0)
        elif key == K_LEFT:
            self._move(0, -1)
        elif key in (K_RIGHT, K_TAB):
            self._move(0, 1)
        elif key == K_BACKTAB:
            self._move(0, -1)
        elif key == K_INSERT:
            self.insert_row()
        elif key in (K_RETURN, K_ENTER, K_F2) and c == 1 and r < len(rows):
            self.edit = str(rows[r][0])
        elif c == 1 and ch.isdigit():
            self.edit = ch
        elif 2 <= c < 2 + n and r < len(rows) and (ch in (" ", "0", "1")):
            on = rows[r][1]
            on[c - 2] = (not on[c - 2]) if ch == " " else (ch == "1")
        elif key == K_ESCAPE:
            self.focused = False
            return False
        else:
            return False
        return True
