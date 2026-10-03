"""Tests for the pure EMTK Help Browser and Documentation Assistant."""

from __future__ import annotations

import importlib

import chisurf.plugins.core.help.gui.help_app as help_app_module
from chisurf.plugins.core.help.gui.help_app import (
    HelpApp,
    HelpGui,
    HelpModel,
    make_help_app,
    parse_markdown_blocks,
)
from chisurf.plugins.core.help.gui.tool import HelpEmtkTool


def test_parse_markdown_blocks():
    md = """---
title: Test Page
---

(anchor-id)=

# Main Title

This is a paragraph with [Link](docs/guide.md).

## Subtitle

```python
import numpy as np
a = np.array([1, 2, 3])
```

:::{note} Important Note
This is a note body.
:::

> [!WARNING] Watch Out
> Be careful with parameters.

| Col A | Col B |
|---|---|
| 1 | 2 |
| 3 | 4 |

$$
E = \\frac{1}{1 + (R/R_0)^6}
$$

- Item 1
- Item 2

---
"""
    blocks = parse_markdown_blocks(md)
    kinds = [b.kind for b in blocks]

    assert "h1" in kinds
    assert "h2" in kinds
    assert "p" in kinds
    assert "code" in kinds
    assert "admonition" in kinds
    assert "table" in kinds
    assert "math" in kinds
    assert "list_item" in kinds
    assert "hr" in kinds

    # Verify anchor was stripped
    for b in blocks:
        assert "(anchor-id)=" not in b.text

    # Verify code block language
    code_block = next(b for b in blocks if b.kind == "code")
    assert code_block.arg == "python"
    assert "import numpy as np" in code_block.text

    # Verify admonitions
    adms = [b for b in blocks if b.kind == "admonition"]
    assert any(b.arg == "note" for b in adms)
    assert any(b.arg == "warning" for b in adms)


def test_help_model_init_and_home():
    model = HelpModel()
    assert model.toc is not None
    assert len(model.order) > 0
    assert "ChiSurf Documentation" in model.current_title
    assert len(model.current_blocks) > 0
    assert not model.edit_mode


def test_help_model_open_page():
    model = HelpModel()
    ok = model.open_page("docs/concepts/accurate_fret.md")
    assert ok
    assert model.current_path is not None
    assert "Accurate FRET" in model.current_title
    assert len(model.current_blocks) > 0
    assert model.editor.text == model.current_content

    # Test history navigation
    model.show_home()
    assert model.current_path is None
    model.go_back()
    assert model.current_path is not None
    assert "accurate_fret" in str(model.current_path)


def test_help_model_search():
    model = HelpModel()
    model.update_search("burst")
    assert len(model.search_results) > 0
    first = model.search_results[0]
    assert "title" in first
    assert "path" in first

    model.update_search("")
    assert len(model.search_results) == 0


def test_help_app_standalone():
    app = make_help_app()
    assert isinstance(app, HelpApp)
    assert isinstance(app.model, HelpModel)
    assert isinstance(app.help_gui, HelpGui)


def test_help_app_declares_compact_native_window_size():
    app = make_help_app()
    try:
        assert app.window_size == (800, 600)
    finally:
        app.close()


def test_help_main_defers_default_size_to_native_launcher(monkeypatch):
    native = importlib.import_module("emtk.native")

    calls = []
    monkeypatch.setattr(native, "main", calls.append)

    help_app_module.main()

    assert calls == [["--app", "chisurf.plugins.core.help.gui.help_app:make_help_app"]]


def test_help_emtk_tool_dock_integration(qapp, qtbot):
    tool = HelpEmtkTool()
    qtbot.addWidget(tool)

    assert "Help" in tool.windowTitle()
    assert (tool.width(), tool.height()) == HelpApp.window_size
    assert hasattr(tool, "model")
    assert hasattr(tool, "app")
    assert hasattr(tool, "host")

    ok = tool.open_doc("docs/concepts/accurate_fret.md")
    assert ok
    assert "Accurate FRET" in tool.model.current_title


def test_figure_and_math_parsing():
    md = """```{figure} ../guides/figures/accurate_fret_lines.png
:alt: Static and dynamic FRET lines
:width: 80%

Figure caption explaining the static FRET line.
```

$$
E = \\frac{F_{12}}{F_{12} + \\gamma F_{11}}
$$

```{math}
S = \\frac{\\gamma F_{11} + F_{12}}{\\gamma F_{11} + F_{12} + F_{22}/\\beta}
```

![Inline image](guides/figures/test.png)

.. figure:: manual/_images/test.png
   :width: 60%
   :alt: RST Alt Text

   RST figure caption
"""
    blocks = parse_markdown_blocks(md)
    figs = [b for b in blocks if b.kind == "figure"]
    maths = [b for b in blocks if b.kind == "math"]

    assert len(figs) == 3
    assert figs[0].arg == "../guides/figures/accurate_fret_lines.png"
    assert "Figure caption explaining" in figs[0].text
    assert figs[0].items[0] == "Static and dynamic FRET lines"
    assert figs[0].items[1] == "80%"

    assert figs[1].arg == "guides/figures/test.png"
    assert figs[1].items[0] == "Inline image"

    assert figs[2].arg == "manual/_images/test.png"
    assert "RST figure caption" in figs[2].text

    assert len(maths) == 2
    assert "F_{12}" in maths[0].text
    assert "\\beta" in maths[1].text


def test_texture_manager_math_and_figure():
    from emtk.texture import Texture
    from chisurf.plugins.core.help.gui.help_app import HelpTextureManager
    from chisurf.plugins.core.help.api.toc import docs_root

    mgr = HelpTextureManager()

    # Test math equation to Texture
    tex_math = mgr.get_math_texture(r"E = \frac{1}{1 + (R/R_0)^6}")
    assert tex_math is not None
    assert isinstance(tex_math, Texture)
    assert tex_math.width > 0
    assert tex_math.height > 0

    # Test figure file to Texture
    doc_path = docs_root() / "concepts" / "accurate_fret.md"
    tex_fig = mgr.get_figure_texture("../guides/figures/accurate_fret_lines.png", doc_path)
    assert tex_fig is not None
    assert isinstance(tex_fig, Texture)
    assert tex_fig.width > 0
    assert tex_fig.height > 0


def test_inline_markup_expansion():
    app = make_help_app()
    gui = app.help_gui

    text = "Channel $I_{11}$ with leakage $\\alpha$ and radius $R_0$. See {ref}`concept-fret` and [User Guide](docs/guide.md)."
    clean_text, links = gui._expand_inline_markup(text)

    # Verify math translated
    assert "α" in clean_text
    assert "R₀" in clean_text

    # Verify links extracted
    assert len(links) >= 2
    labels = [l[0] for l in links]
    assert any("FRET" in lbl for lbl in labels)
    assert any("User Guide" in lbl for lbl in labels)


def test_help_emtk_default_and_ribbon_handler(qapp, qtbot):
    import chisurf.plugins.core.help as help_module

    # Must be HelpEmtkTool by default
    assert help_module.HelpTool is HelpEmtkTool

    tool = HelpEmtkTool()
    qtbot.addWidget(tool)

    # Duck typing and interface compatibility
    assert hasattr(tool, "open_markdown_path")
    assert hasattr(tool, "_open_document_path")
    assert hasattr(tool, "filter_line_edit")

    tool.filter_line_edit.setText("fret")
    assert tool.model.search_query == "fret"

    # Test open_markdown_path
    ok = tool.open_markdown_path("docs/concepts/accurate_fret.md", "corrections")
    assert ok
    assert tool.model.current_path is not None

    # Test emtk upstream math integration
    from emtk import im, latex_to_unicode, render_math_to_texture

    tex = render_math_to_texture(r"\chi^2 = \sum \frac{(y_i - f_i)^2}{\sigma_i^2}")
    assert tex is not None
    assert tex.width > 0
    assert tex.height > 0
    assert "χ²" in latex_to_unicode(r"\chi^2")

    # Test drawing help GUI through EMTK with font scaling and markdown
    from emtk.testing import RecordingPainter
    with im.frame(RecordingPainter(), (0, 0, 1200.0, 800.0)):
        tool.app.help_gui.draw(1200.0, 800.0)


def test_no_indentation_cascading_on_centered_elements():
    """Verify that multiple centered equations and figures do not cause progressive indentation."""
    from emtk import im
    from emtk.testing import RecordingPainter

    app = make_help_app()
    ok = app.model.open_page("docs/concepts/bva.md")
    assert ok

    p = RecordingPainter()
    with im.frame(p, (0, 0, 1200.0, 800.0)):
        app.help_gui.draw(1200.0, 800.0)

    # In bva.md, there are multiple equations and paragraphs.
    # Check that paragraph texts in RecordingPainter are aligned near left margin (around x=0 to x=60)
    # and NOT progressively pushed rightwards (e.g. x > 200).
    bva_texts = [entry for entry in p.texts if isinstance(entry[5], str) and ("A burst is a stream of photons" in entry[5] or "taken over the" in entry[5])]
    assert len(bva_texts) > 0
    for t in bva_texts:
        # Paragraph text should start near left edge of the document pane
        # Check that x is consistent and not progressively shifted (e.g. > 500)
        assert t[0] < 450.0, f"Paragraph text was shifted right to x={t[0]}! Cascading indentation occurred."


def test_child_scrolling_and_toolbar_navigation():
    """Verify toolbar navigation, review badges, and child scrolling."""
    from emtk import im, IO
    from emtk.testing import RecordingPainter

    app = make_help_app()
    app.model.open_page("docs/concepts/accurate_fret.md")
    assert app.model.history_idx == 1

    app.model.go_back()
    assert app.model.history_idx == 0

    app.model.go_forward()
    assert app.model.history_idx == 1

    io = IO()
    io.mouse_pos = (500.0, 400.0)
    io.mouse_wheel = -2.0  # Scroll down
    p = RecordingPainter()
    storage = {}
    with im.frame(p, (0, 0, 1200.0, 800.0), io=io, storage=storage):
        app.help_gui.draw(1200.0, 800.0)


def test_source_links_expansion_and_jump():
    """Verify that {src} roles expand to clickable links and jump directly to source."""
    app = make_help_app()
    gui = app.help_gui

    text = "See {src}`chisurf/core/fitting/fit.py#sample_fit` for fitting implementation."
    clean, links = gui._expand_inline_markup(text)

    assert len(links) == 1
    label, target = links[0]
    assert "fit.py" in label
    assert "sample_fit" in label
    assert target.startswith("src:")

    # Test direct model source opening
    ok = app.model.open_source("chisurf/core/fitting/fit.py", line=10, symbol="sample_fit")
    assert ok is True
    assert app.model.source_path is not None
    assert app.model.source_path.name == "fit.py"
    assert "def sample_fit" in app.model.source_editor.text
    assert app.model.source_line == 10

    # Test full code editor routing via open_source
    from chisurf.gui.widgets.tools.code_links import _ACTIVE_EMTK_EDITORS
    from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app

    editor_app = make_editor_app()
    assert editor_app.model in _ACTIVE_EMTK_EDITORS

    # Trigger jumping to source from GUI link
    gui._handle_link_click(target)
    # File must be opened in the full EMTK code editor
    active_doc = editor_app.model.active_doc
    assert active_doc is not None
    assert active_doc.name == "fit.py"
    assert "def sample_fit" in active_doc.text


def test_targeted_anchor_navigation():
    """Verify opening a document with targeted anchor and scrolling to the block."""
    from emtk import im
    from emtk.testing import RecordingPainter

    app = make_help_app()

    # Open with targeted anchor
    ok = app.model.open_page("docs/concepts/accurate_fret.md", anchor="corrections")
    assert ok is True
    assert app.model.current_anchor == "corrections"
    assert app.model.target_anchor == "corrections"

    # Render frame: anchor should be resolved and scrolled
    p = RecordingPainter()
    storage = {}
    with im.frame(p, (0, 0, 1200.0, 800.0), storage=storage):
        app.help_gui.draw(1200.0, 800.0)

    # After draw, target_anchor was consumed and scrolled
    assert app.model.target_anchor is None


def test_plugin_to_help_doc_links(qapp):
    """Verify doc_links.open_link routes targeted anchors and source links."""
    from chisurf.gui.widgets.tools import doc_links

    app = make_help_app()

    # 1. Targeted anchor from plugin link
    handled = doc_links.open_link("docs/concepts/accurate_fret.md#corrections")
    assert handled is True
    assert app.model.current_path is not None
    assert "accurate_fret" in str(app.model.current_path)
    assert app.model.current_anchor == "corrections"

    # 2. Source link from plugin link
    handled_src = doc_links.open_link("src:chisurf/core/fitting/fit.py#sample_fit")
    assert handled_src is True


def test_help_pinned_toolbar_and_bounded_scroll():
    """Verify toolbar remains pinned at top and scrolling is bounded strictly to visible text range."""
    from emtk import im
    from emtk.testing import RecordingPainter
    from emtk.im_core import IO

    app = make_help_app()
    app.model.open_page("docs/getting_started/index.md")

    p = RecordingPainter()
    box = (0.0, 0.0, 1200.0, 760.0)
    storage = {}
    io = IO()

    # Frame 1: Initial layout
    with im.frame(p, box, io=io, storage=storage):
        app.help_gui.draw(1200.0, 760.0)

    pinned_labels = {"Home", "Back", "Fwd", "Source", "Read"}
    initial_toolbar = {text[5]: text[1] for text in p.texts if text[5] in pinned_labels}
    # Find the document child key
    doc_child_keys = [
        k for k in storage.keys()
        if isinstance(k, tuple) and len(k) > 0 and k[0] == "__child__" and any("getting_started" in str(elem) for elem in k)
    ]
    assert len(doc_child_keys) == 1
    doc_key = doc_child_keys[0]

    content_h = storage[doc_key]["content_height"]
    assert content_h > 500.0

    # Frame 2: Aggressive scroll down beyond the bottom
    io.mouse_pos = (500.0, 300.0)
    io.mouse_wheel = -200.0  # Scroll down heavily
    with im.frame(p, box, io=io, storage=storage):
        app.help_gui.draw(1200.0, 760.0)

    # Scroll position must be strictly clamped and not exceed content height minus visible height
    assert storage[doc_key]["scroll_y"] <= storage[doc_key]["content_height"]
    assert storage[doc_key]["scroll_y"] > 0.0

    # Record element positions while scrolled to verify toolbar is pinned
    toolbar_positions = []
    text_positions = []
    orig_text = p.text
    def inspect_text(x, y, w, h, align, string, colour, bold=False):
        if string in pinned_labels:
            toolbar_positions.append((y, string))
        elif "Every plugin" in string or "Authoring toolbar" in string:
            text_positions.append((y, string))
        return orig_text(x, y, w, h, align, string, colour, bold)

    p.text = inspect_text
    with im.frame(p, box, io=io, storage=storage):
        app.help_gui.draw(1200.0, 760.0)

    # Toolbar must remain pinned near the top of the pane (y in ~20..50), not scrolled off
    assert len(toolbar_positions) > 0
    for y_pos, label in toolbar_positions:
        assert y_pos == initial_toolbar[label], f"Toolbar item {label} moved while scrolling: y={y_pos}"

    # Frame 3: Scroll all the way back up
    io.mouse_wheel = 200.0  # Scroll up heavily
    with im.frame(p, box, io=io, storage=storage):
        app.help_gui.draw(1200.0, 760.0)

    # Must clamp strictly to 0.0, never negative
    assert storage[doc_key]["scroll_y"] == 0.0


def test_long_document_full_scroll_no_bottom_cutoff():
    """Verify long documents with embedded tables compute full height and do not cut off at the bottom."""
    from emtk import im
    from emtk.testing import RecordingPainter

    app = make_help_app()
    ok = app.model.open_page("docs/fundamentals/absorption_and_emission.md")
    assert ok is True

    p = RecordingPainter()
    box = (0.0, 0.0, 1200.0, 800.0)
    io = im.IO()
    storage = {}

    # Frame 1: Initial layout
    with im.frame(p, box, io=io, storage=storage):
        app.help_gui.draw(1200.0, 800.0)

    doc_key = ("__child__", ("dockwin", "document"), f"doc_{app.model.current_path}")
    assert doc_key in storage
    initial_h = storage[doc_key]["content_height"]
    # Document contains 32 blocks spanning >2500px; ensure tables didn't reset origin
    assert initial_h > 2500.0

    # Frame 2: Scroll down to the bottom
    io.mouse_pos = (600.0, 400.0)
    io.mouse_wheel = -100.0  # Large scroll down
    with im.frame(p, box, io=io, storage=storage):
        app.help_gui.draw(1200.0, 800.0)

    assert storage[doc_key]["scroll_y"] > 1800.0
    assert storage[doc_key]["scroll_y"] <= storage[doc_key]["content_height"]


def test_multiline_list_item_and_link_wrapping():
    """Verify that multi-line list items are parsed into single blocks and links wrap cleanly."""
    md = """
- First line of item
  second line of item
  third line with [Link 1](docs/one.md) and [Link 2](docs/two.md).
- Second item with [Link 3](docs/three.md).
"""
    blocks = parse_markdown_blocks(md)
    assert len(blocks) == 2
    assert blocks[0].kind == "list_item"
    assert blocks[0].text == "First line of item second line of item third line with [Link 1](docs/one.md) and [Link 2](docs/two.md)."
    assert blocks[1].kind == "list_item"
    assert blocks[1].text == "Second item with [Link 3](docs/three.md)."

    # Test rendering in GUI
    from emtk import im
    from emtk.testing import RecordingPainter

    app = make_help_app()
    app.model.current_blocks = blocks
    p = RecordingPainter()
    with im.frame(p, (0.0, 0.0, 600.0, 400.0)):
        app.help_gui.draw(600.0, 400.0)

    # Verify link chips were drawn
    link_strings = [s for s in p.strings if s in ("Link 1", "Link 2", "Link 3")]
    assert len(link_strings) == 3


def test_literature_citations_expansion_and_links():
    """Verify that {cite} roles expand to formatted citations and clickable literature links."""
    from chisurf.plugins.core.help.api.xref import document_reference

    # Test document_reference resolution for cite
    path, anchor, label = document_reference("cite", "kasha1950")
    assert "Kasha (1950)" in label
    assert anchor == "kasha1950"
    assert path is not None and "references/index.md" in str(path)

    app = make_help_app()
    gui = app.help_gui

    # Test single and multiple citations in text
    text = "Literature: {cite}`kasha1950` and {cite}`lakowicz2006`."
    clean, links = gui._expand_inline_markup(text)

    assert "Kasha (1950)" in clean
    assert "Lakowicz (2006)" in clean
    assert "{cite}" not in clean

    assert len(links) == 2
    l1, u1 = links[0]
    l2, u2 = links[1]
    assert "Kasha (1950)" in l1
    assert "doi.org" in u1
    assert "Lakowicz (2006)" in l2
    assert "doi.org" in u2

    # Test GUI rendering draws the literature link chips
    from emtk import im
    from emtk.testing import RecordingPainter

    md = "- Literature: {cite}`kasha1950` for rule; {cite}`lakowicz2006` for rest."
    app.model.current_blocks = parse_markdown_blocks(md)
    p = RecordingPainter()
    with im.frame(p, (0.0, 0.0, 800.0, 400.0)):
        gui.draw(800.0, 400.0)

    chips = [s for s in p.strings if s.startswith(("Kasha", "Lakowicz"))]
    assert len(chips) == 2











def test_document_relative_links_and_navigation_history(tmp_path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n\n## Detail\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    model = HelpModel()
    assert model.open_page(first, anchor="detail")
    assert model.open_page("second.md")
    assert model.current_path == second
    model.go_back()
    assert model.current_path == first
    assert model.current_anchor == "detail"
    model.go_forward()
    assert model.current_path == second
    count = len(model.history)
    assert model.open_page(second)
    assert len(model.history) == count
    model.edit_mode = True
    assert model.open_page(first)
    assert not model.edit_mode


def test_document_reader_has_majority_of_available_width():
    gui = make_help_app().help_gui
    regions = gui.docks.regions
    assert set(regions) == {"toc", "document"}
    assert "ask" in gui.docks.tabs["toc"]
    assert gui.docks.layout.ratio <= 0.28


def test_ask_failure_survives_delayed_event_processing(monkeypatch):
    import importlib

    ask_api = importlib.import_module("chisurf.plugins.core.help.api.ask")

    def fail(question):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ask_api, "ask", fail)
    model = HelpModel()
    model.is_asking = True
    model._run_ask_thread("How do I import data?")
    assert not model.chat_history.messages
    model.process_events()
    assert not model.is_asking
    assert len(model.chat_history.messages) == 1
    message = model.chat_history.messages[0]
    assert message.role == "error"
    assert "provider unavailable" in message.content


def test_cancelled_help_answer_cannot_replace_new_request():
    model = HelpModel()
    model.is_asking = True
    generation = model._ask_generation
    model._queue_ask_event(generation, lambda: model.chat_history.add_message("assistant", "late answer"))
    model.cancel_ask()
    model.process_events()
    assert not model.chat_history.messages
    assert not model.is_asking
    model.close()


def test_help_address_routes_documents_sources_citations_and_search(tmp_path, monkeypatch):
    import chisurf.emtk.code_links as code_links
    import chisurf.emtk.doc_links as doc_links
    from chisurf.plugins.core.help.api import bibliography as bib
    path = tmp_path / "address.md"
    path.write_text("# Address\n\n## Detail\n")
    model = HelpModel()
    assert model.navigate_address(str(path) + "#detail")
    assert model.current_path == path
    assert model.current_anchor == "detail"
    opened = []
    monkeypatch.setattr(code_links, "open_source", lambda target, base=None, prefer_emtk=None: opened.append(target) or True)
    monkeypatch.setattr(doc_links, "open_link", lambda target, base=None: opened.append(target) or True)
    monkeypatch.setattr(bib, "bibliography", lambda: {"reference": object()})
    monkeypatch.setattr(bib, "entry_url", lambda entry: "https://example.org/reference")
    assert model.navigate_address("src:source.py#symbol")
    assert model.navigate_address("cite:reference")
    assert opened == ["src:source.py#symbol", "https://example.org/reference"]
    assert model.navigate_address("fluorescence decay")
    assert model.search_query == "fluorescence decay"
    model.close()


def test_help_human_and_ai_review_write_current_saved_page(tmp_path, monkeypatch):
    from chisurf.plugins.core.help.api import review
    path = tmp_path / "review.md"
    path.write_text("# Review\n")
    model = HelpModel()
    model.open_page(path)
    calls = []
    monkeypatch.setattr(review, "is_tracked", lambda path: True)
    monkeypatch.setattr(review, "set_status", lambda path, status, **kwargs: calls.append((path, status, kwargs)) or True)
    monkeypatch.setattr(model, "_get_review_status", lambda path: calls[-1][1] if calls else review.STATUS_UNREVIEWED)
    assert model.set_review_status(review.STATUS_REVIEWED)
    assert calls[-1][2]["reviewer_kind"] == "human"
    assert model.set_review_status(review.STATUS_AI_REVIEWED)
    assert calls[-1][2]["reviewer_kind"] == "ai"
    model.editor.set_text("unsaved source")
    assert not model.set_review_status(review.STATUS_REVIEWED)
    assert "Save" in model.navigation_error
    model.close()


def test_virtual_help_home_has_no_review_badge():
    from emtk import im
    from emtk.testing import RecordingPainter
    app = make_help_app()
    painter = RecordingPainter()
    with im.frame(painter, (0, 0, 1200, 760)):
        app._render()
    assert not any("[Reviewed]" in text for text in painter.strings)
    assert app.model.current_path is None
    app.close()


def test_loaded_help_rich_content_renders_math_table_figure_and_anchor(tmp_path):
    from PIL import Image
    from emtk import im
    from emtk.testing import PixelPainter
    Image.new("RGBA", (32, 16), "blue").save(tmp_path / "figure.png")
    path = tmp_path / "rich.md"
    path.write_text("# Rich page\n\n(detail)=\n## Detail\n\n$$\nE = \\frac{1}{1+(R/R_0)^6}\n$$\n\n| Parameter | Value |\n|---|---|\n| Distance | 42 |\n\n![Figure](figure.png)\n")
    app = make_help_app()
    assert app.model.open_page(path, anchor="detail")
    class RichPainter(PixelPainter):
        def __init__(self):
            super().__init__(1200, 900)
            self.strings = []
            self.textures = []
        def text(self, *args, **kwargs):
            self.strings.append(args[5])
            return super().text(*args, **kwargs)
        def image(self, *args, **kwargs):
            self.textures.append(args[4])
            return super().image(*args, **kwargs)
    painter = RichPainter()
    with im.frame(painter, (0, 0, 1200, 900)):
        app._render()
    assert "Distance" in "\n".join(painter.strings)
    assert app.help_gui.texture_mgr._fig_cache
    assert any(texture is not None for texture in app.help_gui.texture_mgr._fig_cache.values())
    drawn_textures = {id(texture) for texture in painter.textures}
    assert len(drawn_textures) >= 2  # The formula and figure each paint a texture.
    assert app.model.target_anchor is None
    app.close()


def test_native_help_review_registry_staleness_and_human_signoff(tmp_path, monkeypatch):
    from chisurf.plugins.core.help.api import review
    monkeypatch.setattr(review, "tracked_dirs", lambda: [tmp_path])
    path = tmp_path / "tracked.md"
    path.write_text("# Tracked\n")
    model = HelpModel()
    model.open_page(path)
    assert model.set_review_status(review.STATUS_REVIEWED)
    assert model.review_status == review.STATUS_REVIEWED
    assert model.set_review_status(review.STATUS_AI_REVIEWED)
    assert model.review_status == review.STATUS_REVIEWED  # Preserve an intact human sign-off.
    model.editor.set_text("# Changed\n")
    assert model.save_current_page()
    assert model.review_status == review.STATUS_STALE
    assert model.set_review_status(review.STATUS_AI_REVIEWED)
    assert model.review_status == review.STATUS_AI_REVIEWED
    assert model.set_review_status(review.STATUS_UNREVIEWED)
    assert model.review_status == review.STATUS_UNREVIEWED
    model.close()


def test_native_help_zoom_clamps_and_preferences_roundtrip():
    app = make_help_app()
    app.model.set_font_size(100)
    assert app.model.font_size == 24
    app.model.set_font_size(1)
    assert app.model.font_size == 7
    app.model.reset_zoom()
    app.model.zoom(2)
    assert app.model.font_size == 13
    settings = app.export_settings()
    fresh = make_help_app()
    fresh.restore_settings(settings)
    assert fresh.model.font_size == 13
    app.close()
    fresh.close()
