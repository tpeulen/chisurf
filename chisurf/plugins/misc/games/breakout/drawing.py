"""Plugin-owned bitmap font from the legacy chigame pixel face."""
import json
from pathlib import Path

from emtk import im

GLYPHS = json.loads(Path(__file__).with_name("glyphs.json").read_text())

def pixel_text(draw, text, pos, height, colour, align="left"):
    """Draw the original proportional pixel face, with Unicode fallback."""
    if any(char not in GLYPHS for char in text):
        im.push_font_scale(max(.3, height / 12))
        width, line_height = draw.calc_text_size(text)
        x = pos[0] - (width / 2 if align == "center" else width if align == "right" else 0)
        draw.add_text((x, pos[1] - line_height / 2), colour, text)
        im.pop_font_scale()
        return
    glyphs = []
    for char in text:
        rows = GLYPHS[char].split("//")
        columns = [x for x in range(7) if any(row[x] == "#" for row in rows)]
        left, width = (min(columns), max(columns) - min(columns) + 1) if columns else (0, 3)
        glyphs.append((rows, left, width))
    unit = height / 11
    width = sum(width + 1 for rows, left, width in glyphs) * unit
    x = pos[0] - (width / 2 if align == "center" else width if align == "right" else 0)
    for rows, left, width in glyphs:
        for y, row in enumerate(rows):
            for column in range(left, left + width):
                if row[column] == "#":
                    at = (x + (column - left) * unit, pos[1] - height / 2 + y * unit)
                    draw.add_rect_filled(at, (at[0] + unit, at[1] + unit), colour)
        x += (width + 1) * unit



def text_width(draw, text, height):
    if any(char not in GLYPHS for char in text):
        im.push_font_scale(max(.3, height / 12))
        width, _ = draw.calc_text_size(text)
        im.pop_font_scale()
        return width
    width = 0
    for char in text:
        rows = GLYPHS[char].split("//")
        columns = [x for x in range(7) if any(row[x] == "#" for row in rows)]
        width += (max(columns) - min(columns) + 2) if columns else 4
    return width * height / 11
