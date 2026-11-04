"""A small formatted Markdown viewer drawn through a emtk Painter.

emtk has no Markdown renderer (its imgui_markdown port is a test fixture with
hand-translation TODOs), so this is a painter-level control in the style of
``emtk.widgets``: construct it, ``draw(p, x, y, w, h)`` it into a box, feed it
``scroll(rows)``. Supported: ATX headings, paragraphs, bullet and numbered
lists, pipe tables, fenced code blocks, block quotes, horizontal rules, and
inline ``**bold**`` and ```code``` spans.
"""

from __future__ import annotations

import re

TEXT = (225, 228, 235, 255)
DIM = (150, 155, 165, 255)
HEADING = (140, 180, 255, 255)
CODE = (235, 200, 120, 255)
CODE_BG = (28, 30, 36, 255)
RULE = (80, 86, 100, 255)
BG = (40, 43, 52, 255)

_INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


def inline_runs(text):
    """'a **b** `c`' -> [('a ', 'text'), ('b', 'bold'), (' ', 'text'), ('c', 'code')]"""
    runs = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            runs.append((part[2:-2], "bold"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            runs.append((part[1:-1], "code"))
        else:
            runs.append((part, "text"))
    return runs


def parse_blocks(md):
    """Markdown text -> list of (kind, payload) blocks."""
    blocks = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    para = []

    def flush():
        if para:
            blocks.append(("p", " ".join(s.strip() for s in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            blocks.append(("code", code))
        elif not s:
            flush()
        elif re.match(r"^#{1,6}\s", s):
            flush()
            level = len(s) - len(s.lstrip("#"))
            blocks.append(("h", (level, s[level:].strip())))
        elif re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            flush()
            blocks.append(("hr", None))
        elif s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows))
            continue
        elif re.match(r"^([-*+]|\d+[.)])\s", s):
            flush()
            m = re.match(r"^([-*+]|\d+[.)])\s+(.*)$", s)
            marker = "•" if m.group(1) in "-*+" else m.group(1)
            item = [m.group(2)]
            while i + 1 < len(lines) and lines[i + 1].startswith(("  ", "\t")) and lines[i + 1].strip() \
                    and not re.match(r"^\s*([-*+]|\d+[.)])\s", lines[i + 1]):
                i += 1
                item.append(lines[i].strip())
            blocks.append(("li", (marker, " ".join(item))))
        elif s.startswith(">"):
            flush()
            blocks.append(("quote", s.lstrip("> ").strip()))
        else:
            para.append(s)
        i += 1
    flush()
    return blocks


class MarkdownView:
    """Formatted, scrollable Markdown in a box."""

    def __init__(self, text=""):
        self.text = text
        self.scroll_y = 0.0
        self._layout_key = None
        self._ops = []
        self._height = 0.0
        self._line_h = 14.0
        self._box = (0.0, 0.0, 0.0, 0.0)

    def set_text(self, text):
        self.text = text
        self.scroll_y = 0.0
        self._layout_key = None

    # -- layout --------------------------------------------------------- #
    def _scale(self, p, s):
        fn = getattr(p, "set_font_scale", None)
        if callable(fn):
            fn(s)
            return True
        return False

    def _wrap_runs(self, p, runs, width, style_width):
        """Greedy word wrap of styled runs -> list of lines of (x, text, style)."""
        lines, line, x = [], [], 0.0
        space = p.text_width(" ")
        for text, style in runs:
            words = re.split(r"(\s+)", text)
            for word in words:
                if not word:
                    continue
                if word.isspace():
                    if line:
                        x += space
                    continue
                w = style_width(word, style)
                if line and x + w > width:
                    lines.append(line)
                    line, x = [], 0.0
                line.append((x, word, style))
                x += w
        if line:
            lines.append(line)
        return lines or [[]]

    def _layout(self, p, width):
        key = (self.text, round(width))
        if key == self._layout_key:
            return
        self._layout_key = key
        lh = p.line_height() + 3.0
        self._line_h = lh
        ops = []  # (kind, y, payload)
        y = 4.0
        pad = 6.0

        def sw(word, style):
            return p.text_width(word) + (2.0 if style == "code" else 0.0)

        for kind, data in parse_blocks(self.text):
            if kind == "h":
                level, text = data
                scale = {1: 1.45, 2: 1.25, 3: 1.1}.get(level, 1.0)
                y += 6.0 if ops else 0.0
                ops.append(("h", y, (text, scale, level)))
                y += lh * scale + 2.0
                if level <= 2:
                    ops.append(("hr", y, None))
                    y += 5.0
            elif kind == "p" or kind == "quote":
                indent = 14.0 if kind == "quote" else 0.0
                for line in self._wrap_runs(p, inline_runs(data), width - pad - indent, sw):
                    ops.append(("line", y, (indent, line, kind == "quote")))
                    y += lh
                y += 5.0
            elif kind == "li":
                marker, text = data
                indent = 22.0
                first = True
                for line in self._wrap_runs(p, inline_runs(text), width - pad - indent, sw):
                    if first:
                        ops.append(("marker", y, marker))
                        first = False
                    ops.append(("line", y, (indent, line, False)))
                    y += lh
                y += 2.0
            elif kind == "code":
                ops.append(("codebg", y, len(data)))
                y += 3.0
                for code_line in data:
                    ops.append(("codeline", y, code_line))
                    y += lh
                y += 8.0
            elif kind == "hr":
                y += 4.0
                ops.append(("hr", y, None))
                y += 8.0
            elif kind == "table":
                rows = data
                ncol = max(len(r) for r in rows) if rows else 0
                if not ncol:
                    continue
                widths = [0.0] * ncol
                for r in rows:
                    for c, cell in enumerate(r):
                        text = "".join(t for t, _ in inline_runs(cell))
                        widths[c] = max(widths[c], p.text_width(text) + 14.0)
                total = sum(widths)
                if total > width - pad:
                    scale = (width - pad) / total
                    widths = [w * scale for w in widths]
                ops.append(("table", y, (rows, widths)))
                for r_i, r in enumerate(rows):
                    height = 1
                    for c, cell in enumerate(r):
                        wrapped = self._wrap_runs(p, inline_runs(cell), widths[c] - 10.0, sw)
                        height = max(height, len(wrapped))
                    y += lh * height + 2.0
                y += 8.0
        self._ops = ops
        self._height = y

    # -- control contract ------------------------------------------------ #
    def scroll(self, rows):
        _, _, _, h = self._box
        max_scroll = max(0.0, self._height - h + 10.0)
        self.scroll_y = min(max_scroll, max(0.0, self.scroll_y + rows * self._line_h))
        return self.scroll_y

    def scroll_pages(self, pages):
        _, _, _, h = self._box
        return self.scroll(pages * max(1.0, (h - 40.0) / self._line_h))

    def contains(self, px, py):
        x, y, w, h = self._box
        return x <= px < x + w and y <= py < y + h

    def draw(self, p, x, y, w, h):
        from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER

        self._box = (x, y, w, h)
        self._layout(p, w - 14.0)
        self.scroll(0)  # clamp after a resize
        p.fill_rect(x, y, w, h, BG)
        p.push_clip(x, y, w, h)
        lh = self._line_h
        align = ALIGN_LEFT | ALIGN_VCENTER
        x0, y0 = x + 6.0, y - self.scroll_y

        def visible(top, height):
            return top + height >= y and top <= y + h

        def draw_runs(line, left, top, dim=False):
            for rx, word, style in line:
                colour = DIM if dim else TEXT
                if style == "code":
                    tw = p.text_width(word) + 2.0
                    p.fill_rect(left + rx - 1, top + 1, tw, lh - 2, CODE_BG)
                    p.text(left + rx, top, tw, lh, align, word, CODE)
                else:
                    p.text(left + rx, top, w, lh, align, word, colour, style == "bold")

        try:
            for kind, oy, data in self._ops:
                top = y0 + oy
                if kind == "h":
                    text, scale, level = data
                    if not visible(top, lh * scale):
                        continue
                    scaled = self._scale(p, scale)
                    words = [(0.0, t, "bold") for t in [text]]
                    for rx, word, _ in words:
                        p.text(x0 + rx, top, w, lh * scale, align, word,
                               HEADING if level <= 2 else TEXT, True)
                    if scaled:
                        self._scale(p, 1.0)
                elif kind == "line":
                    indent, line, dim = data
                    if visible(top, lh):
                        if dim:
                            p.fill_rect(x0, top, 3.0, lh, RULE)
                        draw_runs(line, x0 + indent, top, dim)
                elif kind == "marker":
                    if visible(top, lh):
                        p.text(x0 + 6.0, top, 16.0, lh, align, data, HEADING)
                elif kind == "hr":
                    if visible(top, 2):
                        p.fill_rect(x0, top, w - 20.0, 1.0, RULE)
                elif kind == "codebg":
                    height = data * lh + 6.0
                    if visible(top, height):
                        p.fill_rect(x0, top, w - 20.0, height, CODE_BG)
                elif kind == "codeline":
                    if visible(top, lh):
                        p.text(x0 + 8.0, top, w, lh, align, data, CODE)
                elif kind == "table":
                    rows, widths = data
                    ty = top
                    for r_i, row in enumerate(rows):
                        height = 1
                        wrapped_cells = []
                        for c in range(len(widths)):
                            cell = row[c] if c < len(row) else ""
                            wrapped = self._wrap_runs(p, inline_runs(cell), widths[c] - 10.0,
                                                      lambda s, st: p.text_width(s) + (2.0 if st == "code" else 0.0))
                            wrapped_cells.append(wrapped)
                            height = max(height, len(wrapped))
                        row_h = lh * height + 2.0
                        if visible(ty, row_h):
                            if r_i == 0:
                                p.fill_rect(x0, ty, sum(widths), row_h, (52, 58, 74, 255))
                            cx = x0
                            for c, wrapped in enumerate(wrapped_cells):
                                for k, line in enumerate(wrapped):
                                    if r_i == 0:
                                        line = [(rx, word, "bold") for rx, word, _ in line]
                                    draw_runs(line, cx + 5.0, ty + k * lh)
                                cx += widths[c]
                            p.fill_rect(x0, ty + row_h - 1, sum(widths), 1.0, RULE)
                        ty += row_h
            # scroll indicator
            if self._height > h:
                frac = h / self._height
                bar_h = max(20.0, h * frac)
                bar_y = y + (h - bar_h) * (self.scroll_y / max(1.0, self._height - h + 10.0))
                p.fill_rect(x + w - 6.0, bar_y, 4.0, bar_h, (110, 120, 140, 255))
        finally:
            p.pop_clip()
