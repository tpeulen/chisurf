"""Every documentation page, drawn in the emtk Documentation dock at two window sizes.

The defect class this sweeps for (user report 2026-10-12): figures drawn as blank
white rectangles, prose whose words ran into each other, a caption wrapping at the
source file's column instead of the reader's, and a table row that looked cut off by
the toolbar. Each was found on one page; each would have been on others. So instead
of a test per page, every page under ``docs/`` is opened in the real reader
(:class:`~chisurf.plugins.core.help.gui.help_app.HelpApp`, recorded through the real
``QuadPainter`` by :class:`emtk.testing_realistic.RealisticDriver`) at 800x600 and
1400x900, and for each page:

* every figure the page references loads, and lands in a GPU image atlas as a
  picture -- not declined (the white box) and not a single flat colour;
* no line of the page (scrolled into view or not: immediate mode lays out all of it)
  runs past the right edge of the reader -- the wrapped-text form of a clipped label;
* no two text runs of the page overlap;
* the reader's scroll region starts below the toolbar.

The rendering itself (glyph placement, atlas growth) has its own unit tests in emtk:
``tests/test_prose_glyph_placement.py`` and ``tests/test_gpu_atlas.py``.
"""

from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("emtk")

from emtk.gpu_atlas import ImageAtlas  # noqa: E402
from emtk.testing_realistic import RealisticDriver  # noqa: E402

from chisurf.plugins.core.help.api import toc as help_toc  # noqa: E402

SIZES = [(800, 600), (1400, 900)]


def _pages() -> list[pathlib.Path]:
    root = help_toc.docs_root()
    return sorted(p for p in root.rglob("*.md") if "_build" not in p.parts)


def _reader_texts(driver, reader):
    """``(string, measured_bounds)`` of every text drawn inside the reader's clip."""
    rx, ry, _rw, _rh = reader
    out = []
    for entry, meta in zip(driver.painter.visible_texts, driver.painter.text_metadata):
        string = str(entry[5])
        if not string.strip():
            continue
        if not any(abs(cx - rx) < 2.0 and abs(cy - ry) < 2.0 for cx, cy, _w, _h in
                   meta["clips"]):
            continue
        out.append((string, meta["measured_bounds"]))
    return out


def _overlaps(texts, min_x: float = 2.0, min_y: float = 3.0):
    found = []
    boxes = [(s, b) for s, b in texts if b[2] > 0 and b[3] > 0]
    boxes.sort(key=lambda item: item[1][1])
    for i, (s1, (x1, y1, w1, h1)) in enumerate(boxes):
        for s2, (x2, y2, w2, h2) in boxes[i + 1:]:
            if y2 >= y1 + h1:
                break
            if (min(x1 + w1, x2 + w2) - max(x1, x2) > min_x
                    and min(y1 + h1, y2 + h2) - max(y1, y2) > min_y):
                found.append((s1[:40], s2[:40]))
    return found


def _figure_problem(texture) -> str | None:
    """Why *texture* would not show as a picture, or ``None``."""
    atlas = ImageAtlas()
    region = atlas.region(texture)
    if region is None:
        return "declined by the image atlas (drawn as a blank box)"
    _ref, _rev, x, y, w, h = atlas._placed[id(texture)]
    pixels = atlas.pixels[y:y + h, x:x + w]
    if pixels[:, :, 3].max() == 0:
        return "fully transparent"
    if pixels.reshape(-1, 4).std(axis=0).max() < 1.0:
        return "one flat colour"
    return None


@pytest.fixture(scope="module")
def app():
    from chisurf.plugins.core.help.gui.help_app import HelpApp

    help_app = HelpApp()
    yield help_app
    help_app.close()


def test_every_figure_referenced_from_docs_loads_as_a_picture(app):
    """Every ``{figure}``/``{image}``/``![]()``/``<img>`` in docs/ resolves and decodes."""
    from chisurf.plugins.core.help.gui.help_app import parse_markdown_blocks

    manager = app.help_gui.texture_mgr
    problems = []
    checked = 0
    for page in _pages():
        blocks = parse_markdown_blocks(page.read_text(encoding="utf-8", errors="replace"))
        for block in blocks:
            if block.kind != "figure":
                continue
            checked += 1
            target = manager.resolve_figure(block.arg, page)
            if target is None:
                problems.append(f"{page.relative_to(help_toc.docs_root())}: missing {block.arg}")
                continue
            texture = manager.get_figure_texture(block.arg, page)
            if texture is None:
                problems.append(f"{page.name}: {block.arg} does not decode")
                continue
            why = _figure_problem(texture)
            if why:
                problems.append(f"{page.name}: {block.arg} {why}")
    assert checked > 100, f"only {checked} figures found: the parser lost them"
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_every_page_renders_without_clipped_or_overlapping_text(app, size):
    driver = RealisticDriver(app, size)
    driver.frame(2)
    root = help_toc.docs_root()
    failures: list[str] = []
    for page in _pages():
        app.model.open_page(page)
        driver.frame(2)
        name = str(page.relative_to(root))
        reader = app.help_gui.item_rects.get("doc_reader")
        if reader is None:
            failures.append(f"{name}: the reader was not drawn")
            continue
        rx, ry, rw, _rh = reader
        crumbs = [b for k, b in app.help_gui.item_rects.items()
                  if k in ("home", "go", "zoom_in", "guide") and b]
        if any(b[1] + b[3] > ry + 0.5 for b in crumbs):
            failures.append(f"{name}: the reader starts under the toolbar")
        texts = _reader_texts(driver, reader)
        right = rx + rw
        for string, (x, _y, w, _h) in texts:
            if x + w > right + 1.0 and len(string.strip()) > 1:
                failures.append(f"{name}: runs {x + w - right:.0f} px past the reader: "
                                f"{string[:60]!r}")
                break
        overlaps = _overlaps(texts)
        if overlaps:
            failures.append(f"{name}: overlapping text {overlaps[:2]}")
        for call in driver.painter.calls:
            if call[0] == "image" and call[5] is None:
                failures.append(f"{name}: an image drawn with no texture")
                break
    assert not failures, f"{len(failures)} problems at {size}:\n" + "\n".join(failures)


def test_a_missing_figure_is_a_visible_placeholder_and_a_warning(app, tmp_path, caplog):
    """Never a blank box: the reader says which file is missing, and the log says so too."""
    page = tmp_path / "page.md"
    page.write_text("# Page\n\n```{figure} figures/not_there.png\n\nA caption that\nwraps.\n```\n",
                    encoding="utf-8")
    driver = RealisticDriver(app, (800, 600))
    with caplog.at_level("WARNING"):
        app.model.open_page(page)
        driver.frame(3)
    strings = [str(s) for s in driver.painter.strings]
    assert any("missing: figures/not_there.png" in s for s in strings), strings
    assert any("not_there.png" in r.getMessage() for r in caplog.records)
    # The caption is one paragraph, wrapped at the reader's column, not at the source's.
    assert any(s.startswith("Figure: A caption that wraps.") for s in strings), strings


def test_an_svg_figure_is_drawn_at_its_css_size(app, tmp_path):
    """An SVG (which Pillow cannot open) is rasterised at 2x and drawn at half that."""
    (tmp_path / "f.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">'
        '<rect width="300" height="100" fill="#3070c0"/><circle cx="50" cy="50" r="40" '
        'fill="#f0c000"/></svg>', encoding="utf-8")
    page = tmp_path / "svg.md"
    page.write_text("# SVG\n\n![a figure](f.svg)\n", encoding="utf-8")
    driver = RealisticDriver(app, (800, 600))
    app.model.open_page(page)
    driver.frame(3)
    texture = app.help_gui.texture_mgr.get_figure_texture("f.svg", page)
    assert texture is not None and texture.size == (600, 200)
    assert _figure_problem(texture) is None
    images = [c for c in driver.painter.calls if c[0] == "image" and c[5] is texture]
    assert images, "the SVG figure was not drawn"
    assert images[0][3] == pytest.approx(300.0, abs=1.0)
