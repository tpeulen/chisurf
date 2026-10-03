"""Pure EMTK Help Browser and Documentation Assistant.

Provides an immediate-mode documentation reader, table-of-contents navigator,
live search, markdown source editor, and AI-grounded Ask Assistant with zero Qt
dependencies.
"""

from __future__ import annotations

import base64
import io
import getpass
import logging
import pathlib
import re
import threading
from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Callable

from PIL import Image
from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col
from emtk.texture import Texture
from emtk.widgets.chat import ChatHistory, draw_chat_input_bar, draw_chat_transcript
from emtk.widgets.text_editor import TextEditor
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import math_to_image

from chisurf.plugins.core.help.api import io as help_io
from chisurf.plugins.core.help.api import review as help_review
from chisurf.plugins.core.help.api import toc as help_toc
from chisurf.plugins.core.help.api.mathtext import html_math, normalise_latex, _unicode_fallback
from chisurf.plugins.core.help.api.xref import document_reference, resolve_document, resolve_ref

_LOGGER = logging.getLogger(__name__)

WINDOW_BG = (28, 30, 36, 255)

START_PAGES = [
    ("docs/getting_started/index.md", "Getting Started", "Install, launch, and find your way around"),
    ("docs/manual/data_import.md", "Data Import", "Import TTTR / photon data and setup your workspace"),
    ("docs/manual/fit_interface.md", "Fitting Interface", "ChiSurf fitting interface parameter guide"),
    ("docs/guides/index.md", "Workflow Guides", "Step-by-step guides for burst and decay analysis"),
    ("docs/concepts/accurate_fret.md", "Accurate FRET", "Correction factors, FRET lines and photophysics"),
    ("docs/concepts/bva.md", "Burst Variance Analysis", "Diagnosing dynamic FRET from burst variance"),
]

QUICK_QUESTIONS = [
    "How do I fit a fluorescence decay?",
    "What is burst variance analysis (BVA)?",
    "How does accurate FRET calculation work?",
    "How do I import TTTR photon data?",
]

_SUBSCRIPTS = str.maketrans("0123456789+-=()aeoxhklmnpstij", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼ")
_SUPERSCRIPTS = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")


def format_inline_math(latex: str) -> str:
    """Format an inline LaTeX snippet into high-legibility Unicode text."""
    try:
        from emtk import latex_to_unicode

        res = latex_to_unicode(latex.strip())
        if res:
            return res
    except Exception:
        pass
    h = html_math(latex.strip())
    if not h:
        return _unicode_fallback(latex.strip())

    def _sub_repl(m: re.Match) -> str:
        inner = re.sub(r"<[^>]+>", "", m.group(1))
        return inner.translate(_SUBSCRIPTS)

    def _sup_repl(m: re.Match) -> str:
        inner = re.sub(r"<[^>]+>", "", m.group(1))
        return inner.translate(_SUPERSCRIPTS)

    s = re.sub(r"<sub>(.*?)</sub>", _sub_repl, h)
    s = re.sub(r"<sup>(.*?)</sup>", _sup_repl, s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&#8201;", " ")


class HelpTextureManager:
    """Manages and caches EMTK Textures for rendered LaTeX math and figure images."""

    def __init__(self) -> None:
        self._fig_cache: dict[str, Texture | None] = {}
        self._math_cache: dict[tuple[str, str, float], Texture | None] = {}

    def get_figure_texture(self, rel_path: str, doc_path: pathlib.Path | None = None) -> Texture | None:
        if not rel_path:
            return None
        arg = rel_path.strip()
        cache_key = f"{doc_path}::{arg}"
        if cache_key in self._fig_cache:
            return self._fig_cache[cache_key]

        target_file: pathlib.Path | None = None
        d_root = help_toc.docs_root()
        r_root = help_toc.repository_root()

        cands = []
        if doc_path is not None:
            cands.append(doc_path.parent / arg)
        cands.extend([
            d_root / arg.lstrip("/"),
            r_root / arg.lstrip("/"),
            d_root / re.sub(r"^(\.\./|docs/)+", "", arg),
            r_root / "docs" / re.sub(r"^(\.\./|docs/)+", "", arg),
            d_root / "guides" / "figures" / pathlib.Path(arg).name,
            d_root / "concepts" / "figures" / pathlib.Path(arg).name,
            d_root / "manual" / "pic" / pathlib.Path(arg).name,
            d_root / "manual" / "_images" / pathlib.Path(arg).name,
            d_root / "manual" / "figures" / pathlib.Path(arg).name,
        ])

        for c in cands:
            try:
                res = c.resolve()
                if res.is_file():
                    target_file = res
                    break
            except Exception:
                continue

        if target_file is None:
            _LOGGER.debug("Figure not found: %s (doc: %s)", arg, doc_path)
            self._fig_cache[cache_key] = None
            return None

        try:
            tex = Texture.from_file(target_file)
            self._fig_cache[cache_key] = tex
            return tex
        except Exception as e:
            _LOGGER.warning("Failed to load figure %s: %s", target_file, e)
            self._fig_cache[cache_key] = None
            return None


    def get_math_texture(
        self,
        formula: str,
        colour: str = "#d8dee9",
        font_size: float = 13.0,
    ) -> Texture | None:
        raw = formula.strip()
        if not raw:
            return None

        cache_key = (raw, colour, font_size)
        if cache_key in self._math_cache:
            return self._math_cache[cache_key]

        try:
            from emtk import render_math_to_texture

            tex = render_math_to_texture(raw, colour=colour, font_size=font_size)
            if tex is not None:
                self._math_cache[cache_key] = tex
                return tex
        except Exception as e:
            _LOGGER.debug("emtk.render_math_to_texture failed for %r: %s", raw, e)

        try:
            from chisurf.plugins.core.help.api.mathtext import MathRenderer

            renderer = MathRenderer(colour=colour, font_size=font_size)
            html = renderer.to_html(raw, display=True)
            m = re.search(r"data:image/png;base64,([^\"]+)", html)
            if m:
                png_bytes = base64.b64decode(m.group(1))
                pil_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                tex = Texture(pil_img.width, pil_img.height, pil_img.tobytes())
                self._math_cache[cache_key] = tex
                return tex
        except Exception as e:
            _LOGGER.debug("MathRenderer failed for %r: %s", raw, e)

        # Fallback to math_to_image with transparent alpha mask
        try:
            buf = io.BytesIO()
            prop = FontProperties(size=font_size)
            norm = normalise_latex(raw)
            math_to_image(norm, buf, prop=prop, dpi=120, format="png", color=colour)
            buf.seek(0)
            pil_img = Image.open(buf).convert("RGBA")
            data = pil_img.getdata()
            new_data = []
            for item in data:
                if item[0] > 235 and item[1] > 235 and item[2] > 235:
                    new_data.append((item[0], item[1], item[2], 0))
                else:
                    new_data.append(item)
            pil_img.putdata(new_data)
            tex = Texture(pil_img.width, pil_img.height, pil_img.tobytes())
            self._math_cache[cache_key] = tex
            return tex
        except Exception as e:
            _LOGGER.debug("Failed to render math %r: %s", raw, e)
            self._math_cache[cache_key] = None
            return None


@dataclass
class MarkdownBlock:
    """A parsed block of documentation content for immediate-mode rendering."""

    kind: str  # "h1", "h2", "h3", "h4", "p", "code", "admonition", "list_item", "hr", "math", "figure", "table"
    text: str = ""
    arg: str = ""  # language for code, kind for admonition, image path for figure
    items: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)


_OPTION = re.compile(r"^[ \t]*:([\w-]+):\s*(.*)$")


def _split_directive_body(body_lines: list[str]) -> tuple[dict[str, str], str]:
    options: dict[str, str] = {}
    idx = 0
    while idx < len(body_lines):
        line = body_lines[idx]
        if not line.strip():
            idx += 1
            if options:
                break
            continue
        opt_match = _OPTION.match(line)
        if opt_match is None:
            break
        options[opt_match.group(1).lower()] = opt_match.group(2).strip()
        idx += 1
    caption = "\n".join(body_lines[idx:]).strip()
    return options, caption


def parse_markdown_blocks(raw_text: str, base_dir: pathlib.Path | None = None) -> list[MarkdownBlock]:
    """Parse Markdown or reStructuredText into immediate-mode renderable blocks."""
    blocks: list[MarkdownBlock] = []
    lines = raw_text.splitlines()
    n = len(lines)
    i = 0
    pending_anchors: list[str] = []

    def slugify(s: str) -> str:
        return re.sub(r"[^\w.-]+", "-", s.lower()).strip("-")

    def add_block(b: MarkdownBlock) -> None:
        nonlocal pending_anchors
        if pending_anchors:
            b.anchors = list(dict.fromkeys(b.anchors + pending_anchors))
            pending_anchors = []
        blocks.append(b)

    # Skip YAML front-matter if present
    if n > 1 and lines[0].strip() == "---":
        i = 1
        while i < n and lines[i].strip() != "---":
            i += 1
        if i < n:
            i += 1

    p_lines: list[str] = []

    def flush_p():
        nonlocal p_lines
        if p_lines:
            text = " ".join(line.strip() for line in p_lines if line.strip())
            if text:
                add_block(MarkdownBlock(kind="p", text=text))
            p_lines = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 1. Target anchor: (anchor-id)=
        m_anc = re.match(r"^\(([\w.-]+)\)=\s*$", stripped)
        if m_anc:
            pending_anchors.append(m_anc.group(1).lower().strip())
            i += 1
            continue

        # 2. MyST Directive Fence (``` {directive} or ::: {directive})
        d_match = re.match(r"^(?P<fence>`{3,}|~{3,}|:{3,})\{(?P<name>[\w.-]+)\}\s*(?P<arg>.*)$", stripped)
        if d_match:
            flush_p()
            fence = d_match.group("fence")
            name = d_match.group("name").lower()
            arg = d_match.group("arg").strip()
            marker = fence[0]
            body_lines = []
            i += 1
            while i < n:
                sub = lines[i].strip()
                c_match = re.match(r"^(?P<fence>`{3,}|~{3,}|:{3,})\s*$", sub)
                if c_match and c_match.group("fence")[0] == marker and len(c_match.group("fence")) >= len(fence):
                    i += 1
                    break
                body_lines.append(lines[i])
                i += 1

            opts, body_text = _split_directive_body(body_lines)
            dir_anchors: list[str] = []
            if "name" in opts:
                dir_anchors.append(opts["name"].lower().strip())

            if name in ("figure", "image"):
                fig_arg = arg or opts.get("figure", "")
                add_block(
                    MarkdownBlock(
                        kind="figure",
                        text=body_text,
                        arg=fig_arg,
                        items=[opts.get("alt", ""), opts.get("width", "")],
                        anchors=dir_anchors,
                    )
                )
            elif name == "math":
                add_block(MarkdownBlock(kind="math", text="\n".join(body_lines).strip(), anchors=dir_anchors))
            elif name in ("code-block", "code", "sourcecode"):
                add_block(MarkdownBlock(kind="code", text="\n".join(body_lines).rstrip(), arg=arg, anchors=dir_anchors))
            elif name in ("note", "warning", "tip", "important", "caution", "danger", "error", "hint", "seealso", "admonition", "details", "dropdown"):
                title = arg or opts.get("title", "") or name.capitalize()
                add_block(MarkdownBlock(kind="admonition", text=body_text, arg=name, items=[title], anchors=dir_anchors))
            elif name in ("toctree", "contents", "index", "meta", "raw", "only"):
                pass
            else:
                add_block(MarkdownBlock(kind="admonition", text=body_text, arg="note", items=[arg or name.capitalize()], anchors=dir_anchors))
            continue

        # 3. RST Directive: .. name:: arg
        rst_match = re.match(r"^\.\.\s+([\w-]+)::\s*(.*)$", stripped)
        if rst_match:
            flush_p()
            name = rst_match.group(1).lower()
            arg = rst_match.group(2).strip()
            body_lines = []
            i += 1
            while i < n:
                cur_line = lines[i]
                # Any indented line continues the directive — options are
                # sometimes indented by two spaces rather than three, and
                # stopping short leaked them into the text as literal
                # ":align: center" (the bug that motivated this branch).
                if cur_line.strip() and not (cur_line.startswith((" ", "\t")) or cur_line.startswith("..")):
                    break
                body_lines.append(cur_line.strip())
                i += 1

            opts, body_text = _split_directive_body(body_lines)
            dir_anchors = []
            if "name" in opts:
                dir_anchors.append(opts["name"].lower().strip())

            if name in ("image", "figure"):
                add_block(
                    MarkdownBlock(
                        kind="figure",
                        text=body_text,
                        arg=arg,
                        items=[opts.get("alt", ""), opts.get("width", "")],
                        anchors=dir_anchors,
                    )
                )
            elif name == "math":
                add_block(MarkdownBlock(kind="math", text="\n".join(body_lines).strip(), anchors=dir_anchors))
            elif name in ("code-block", "sourcecode"):
                add_block(MarkdownBlock(kind="code", text="\n".join(body_lines).rstrip(), arg=arg, anchors=dir_anchors))
            elif name in ("note", "warning", "tip", "important", "seealso", "admonition"):
                add_block(MarkdownBlock(kind="admonition", text=body_text, arg=name, items=[name.capitalize()], anchors=dir_anchors))
            elif name in ("toctree", "contents", "index"):
                pass
            else:
                if body_text:
                    add_block(MarkdownBlock(kind="p", text=body_text, anchors=dir_anchors))
            continue

        # 4. Plain Code Fence (``` or ~~~ without directive)
        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush_p()
            code_lang = stripped.lstrip("`~").strip()
            marker = stripped[0]
            body_lines = []
            i += 1
            while i < n:
                sub = lines[i].strip()
                if sub.startswith(marker * 3) and all(c == marker for c in sub):
                    i += 1
                    break
                body_lines.append(lines[i])
                i += 1
            add_block(MarkdownBlock(kind="code", text="\n".join(body_lines), arg=code_lang))
            continue

        # 5. Display math block: $$ ... $$
        if stripped.startswith("$$"):
            flush_p()
            if stripped.endswith("$$") and len(stripped) > 2:
                math_content = stripped[2:-2].strip()
                add_block(MarkdownBlock(kind="math", text=math_content))
                i += 1
                continue
            else:
                math_lines = [stripped.lstrip("$").strip()]
                i += 1
                while i < n and not lines[i].strip().endswith("$$"):
                    math_lines.append(lines[i].strip())
                    i += 1
                if i < n:
                    math_lines.append(lines[i].strip().rstrip("$").strip())
                    i += 1
                add_block(MarkdownBlock(kind="math", text="\n".join(math_lines).strip()))
                continue

        # 6. Standard Markdown Image: ![alt](path)
        img_match = re.match(r"^!\[(.*?)\]\((.*?)\)\s*$", stripped)
        if img_match:
            flush_p()
            add_block(MarkdownBlock(kind="figure", text="", arg=img_match.group(2).strip(), items=[img_match.group(1).strip(), ""]))
            i += 1
            continue

        # 7. HTML <img> tag
        if stripped.startswith("<img") and "src=" in stripped:
            flush_p()
            s_m = re.search(r'src=[\'"]([^\'"]+)[\'"]', stripped)
            a_m = re.search(r'alt=[\'"]([^\'"]+)[\'"]', stripped)
            if s_m:
                add_block(
                    MarkdownBlock(
                        kind="figure",
                        text="",
                        arg=s_m.group(1).strip(),
                        items=[a_m.group(1).strip() if a_m else "", ""],
                    )
                )
                i += 1
                continue

        # 8. GitHub style blockquote callouts: > [!NOTE], > [!WARNING], > [!TIP]
        if stripped.startswith("> [!"):
            flush_p()
            m = re.match(r"^>\s*\[!(\w+)\]\s*(.*)", stripped)
            adm_k = m.group(1).lower() if m else "note"
            adm_t = (m.group(2).strip() if m else "") or adm_k.capitalize()
            b_lines: list[str] = []
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                b_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            add_block(MarkdownBlock(kind="admonition", text=" ".join(b_lines), arg=adm_k, items=[adm_t]))
            continue

        # Regular blockquote: > text
        if stripped.startswith(">"):
            flush_p()
            b_lines = [stripped.lstrip(">").strip()]
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                b_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            add_block(MarkdownBlock(kind="admonition", text=" ".join(b_lines), arg="quote", items=["Quote"]))
            continue

        # 9. Markdown table: | cell | cell |
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_p()
            table_rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                r_strip = lines[i].strip()
                cells = [c.strip() for c in r_strip.strip("|").split("|")]
                if not all(re.match(r"^:?-+:?$", c) for c in cells):
                    table_rows.append(cells)
                i += 1
            if table_rows:
                add_block(MarkdownBlock(kind="table", items=["\t".join(r) for r in table_rows]))
            continue

        # 10. Headings (# H1, ## H2, ### H3, #### H4)
        if stripped.startswith("#"):
            flush_p()
            lvl = len(stripped) - len(stripped.lstrip("#"))
            h_title = stripped.lstrip("#").strip()
            custom_id = ""
            m_id = re.search(r"\{\s*#([-\w]+)\s*\}\s*$", h_title)
            if m_id:
                custom_id = m_id.group(1).lower().strip()
                h_title = re.sub(r"\{\s*#[-\w]+\s*\}\s*$", "", h_title).strip()
            h_slug = slugify(h_title)
            h_anchors = [h_slug, h_title.lower()]
            if custom_id:
                h_anchors.append(custom_id)
            add_block(MarkdownBlock(kind=f"h{min(lvl, 4)}", text=h_title, anchors=h_anchors))
            i += 1
            continue

        # RST Heading underline (=== or --- or ~~~ under text)
        if i + 1 < n:
            next_strip = lines[i + 1].strip()
            if (
                stripped
                and len(next_strip) >= 3
                and all(c == next_strip[0] for c in next_strip)
                and next_strip[0] in ("=", "-", "~", "^", '"')
            ):
                flush_p()
                char = next_strip[0]
                kind = "h1" if char == "=" else ("h2" if char == "-" else "h3")
                r_slug = slugify(stripped)
                add_block(MarkdownBlock(kind=kind, text=stripped, anchors=[r_slug, stripped.lower()]))
                i += 2
                continue

        # 11. Horizontal rule
        if stripped in ("---", "***", "___", "===="):
            flush_p()
            add_block(MarkdownBlock(kind="hr"))
            i += 1
            continue

        # 12. List Items (- , * , + , or 1. , 2. )
        list_m = re.match(r"^([-*+]|\d+\.)\s+(.*)", stripped)
        if list_m:
            flush_p()
            bullet = list_m.group(1)
            item_lines = [list_m.group(2).strip()]
            i += 1
            while i < n:
                next_l = lines[i]
                next_s = next_l.strip()
                if not next_s:
                    break
                if (
                    re.match(r"^([-*+]|\d+\.)\s+", next_s)
                    or next_s.startswith(("#", "```", "~~~", ":::", ">", "$$", "<img", "|"))
                    or next_s in ("---", "***", "___", "====")
                ):
                    break
                if i + 1 < n and lines[i + 1].strip() and len(lines[i + 1].strip()) >= 3 and all(c == lines[i + 1].strip()[0] for c in lines[i + 1].strip()) and lines[i + 1].strip()[0] in ("=", "-", "~", "^", '"'):
                    break
                item_lines.append(next_s)
                i += 1
            add_block(MarkdownBlock(kind="list_item", text=" ".join(item_lines), arg=bullet))
            continue

        # 13. Blank line separates paragraphs
        if not stripped:
            flush_p()
            i += 1
            continue

        # Ordinary text line
        p_lines.append(line)
        i += 1

    flush_p()
    return blocks


_ACTIVE_HELP_INSTANCES: list[HelpModel] = []


def register_help_model(model: HelpModel) -> None:
    """Register an active EMTK help model instance."""
    if model not in _ACTIVE_HELP_INSTANCES:
        _ACTIVE_HELP_INSTANCES.append(model)


def unregister_help_model(model: HelpModel) -> None:
    """Unregister an EMTK help model instance."""
    if model in _ACTIVE_HELP_INSTANCES:
        _ACTIVE_HELP_INSTANCES.remove(model)


def open_help_page(path: str | pathlib.Path, anchor: str | None = None) -> bool:
    """Target and open a documentation page and optional anchor in an active EMTK help viewer."""
    for model in reversed(_ACTIVE_HELP_INSTANCES):
        if model is not None:
            return model.open_page(path, anchor=anchor)
    return False


class HelpModel:
    """Document state, table-of-contents navigation, search, and AI assistant."""

    def __init__(self) -> None:
        self.toc: help_toc.Node | None = None
        self.doc_nodes: dict[str, help_toc.Node] = {}
        self.order: list[help_toc.Node] = []

        self.current_path: pathlib.Path | None = None
        self.current_title: str = "ChiSurf Documentation"
        self.current_content: str = ""
        self.current_blocks: list[MarkdownBlock] = []
        self.editor: TextEditor = TextEditor(text="", language=None)
        self.is_modified: bool = False
        self.edit_mode: bool = False

        self.current_anchor: str | None = None
        self.target_anchor: str | None = None

        # Embedded Source Viewer
        self.source_view: bool = False
        self.source_path: pathlib.Path | None = None
        self.source_line: int | None = None
        self.source_symbol: str = ""
        from emtk.widgets.text_editor import Language

        self.source_editor: TextEditor = TextEditor(text="", language=Language.python())

        self.search_query: str = ""
        self.search_results: list[dict] = []

        self.history: list[pathlib.Path | None] = []
        self._history_anchors: list[str | None] = []
        self.history_idx: int = -1

        self.review_status: str = help_review.STATUS_UNREVIEWED
        self.address_text = ""
        self.navigation_error = ""
        self.authoring_mode = False
        self.review_filter = "all"
        self.include_development = False
        self.review_summary = ""
        self.font_size = 12.0
        self._review_cache: dict[str, str] = {}
        self.event_queue: Queue[Callable[[], None]] = Queue()

        # Embedded AI Docs Assistant
        self.chat_history: ChatHistory = ChatHistory()
        self.is_asking: bool = False
        self._closed = False
        self._ask_generation = 0
        self.input_prompt: str = ""

        register_help_model(self)
        self._load_toc()
        self.show_home()

    def _load_toc(self) -> None:
        try:
            self.toc = help_toc.build_toc(include_development=self.include_development)
            self.doc_nodes.clear()
            self.order.clear()

            for node in self.toc.walk():
                if node.path:
                    resolved = pathlib.Path(node.path).resolve()
                    self.doc_nodes[str(resolved)] = node
                    self.order.append(node)
        except Exception as e:
            _LOGGER.warning(f"Failed to build documentation TOC: {e}")

    def set_include_development(self, include: bool) -> None:
        """List architecture notes and module READMEs in the tree too (the Qt *Developer docs*)."""
        include = bool(include)
        if include != self.include_development:
            self.include_development = include
            self._load_toc()

    # -- Navigation -----------------------------------------------------------

    def show_home(self, add_history: bool = True) -> None:
        self.current_path = None
        self.review_status = help_review.STATUS_UNREVIEWED
        self.address_text = ""
        self.navigation_error = ""
        self.current_title = "ChiSurf Documentation"
        self.current_content = self._build_home_content()
        self.current_blocks = parse_markdown_blocks(self.current_content)
        self.editor.text = self.current_content
        self.is_modified = False
        self.edit_mode = False
        self.source_view = False
        self.current_anchor = None
        self.target_anchor = None

        if add_history:
            self._record_history(None, None)

    def _record_history(self, path: pathlib.Path | None, anchor: str | None) -> None:
        if self.history_idx >= 0:
            if self.history[self.history_idx] == path and self._history_anchors[self.history_idx] == anchor:
                return
        self.history = self.history[: self.history_idx + 1]
        self._history_anchors = self._history_anchors[: self.history_idx + 1]
        self.history.append(path)
        self._history_anchors.append(anchor)
        self.history_idx = len(self.history) - 1

    #: The Qt start page's "Start here" list (same pages, same descriptions).
    START_HERE = (
        ("docs/getting_started/index", "Install, launch, and find your way around"),
        ("docs/manual/data_import", "Import data and create your first fit"),
        ("docs/manual/fit_interface", "The fitting interface, parameter by parameter"),
        ("docs/guides/index", "Pick the workflow you want to run"),
    )

    def _build_home_content(self) -> str:
        """The start page, built from the table of contents as the Qt help builds it."""
        root = help_toc.repository_root()
        lines = [
            "# ChiSurf documentation",
            "",
            "ChiSurf analyses time-resolved and single-molecule fluorescence data — TCSPC, FCS "
            "and smFRET. The documentation is in four layers: the **theory** of each method, a "
            "**guide** that runs it in this application, the **fitting interface** itself with "
            "complete worked examples, and a **reference** for formats, settings and every "
            "plugin parameter.",
            "",
            "## Start here",
            "",
        ]
        for stem, description in self.START_HERE:
            path = next((root / f"{stem}{ext}" for ext in (".md", ".rst")
                         if (root / f"{stem}{ext}").is_file()), None)
            if path is None:
                continue
            title = help_toc.page_title(path) or path.stem
            lines.append(f"- [{title}]({path.relative_to(root).as_posix()}) — {description}")
        lines += ["", "## The parts of the documentation", ""]
        for section in self.toc.children if self.toc else []:
            target = section.path or (section.children[0].path if section.children else None)
            heading = section.title
            if target is not None:
                try:
                    heading = f"[{section.title}]({pathlib.Path(target).resolve().relative_to(root).as_posix()})"
                except ValueError:
                    heading = f"[{section.title}]({target})"
            lines.append(f"- {heading}" + (f" — {section.summary}" if section.summary else ""))
            lines.append("")
            names = [child.title for child in section.children[:6]]
            if names:
                lines.append(" · ".join(names) + ("…" if len(section.children) > 6 else ""))
                lines.append("")
        lines += ["---", "",
                  "Search every page from the box above the tree, or use the tree on the left. "
                  "Every plugin's **?** button opens its own help here."]
        return "\n".join(lines)

    def breadcrumb(self) -> list[str]:
        """Titles of the sections above the open page, as the Qt help shows them."""
        if self.current_path is None or self.toc is None:
            return []
        target = str(self.current_path)

        def walk(node, trail):
            for child in node.children:
                if child.path and str(pathlib.Path(child.path).resolve()) == target:
                    return trail
                found = walk(child, trail + [child.title])
                if found is not None:
                    return found
            return None

        return walk(self.toc, []) or []

    def jump_to_anchor(self, anchor: str) -> None:
        """Target and scroll to an anchor on the current page."""
        clean = anchor.strip().lstrip("#")
        self.current_anchor = clean if clean else None
        self.target_anchor = self.current_anchor

    def open_source(self, path: str | pathlib.Path, line: int | None = None, symbol: str = "") -> bool:
        """Display a source code file with syntax highlighting in the embedded reader."""
        resolved = pathlib.Path(path).resolve()
        if not resolved.is_file():
            candidate = help_toc.repository_root() / path
            if candidate.is_file():
                resolved = candidate.resolve()
            else:
                return False

        try:
            with open(resolved, "r", encoding="utf-8") as f:
                code = f.read()
            self.source_path = resolved
            self.source_line = line
            self.source_symbol = symbol
            from emtk.widgets.text_editor import Language, Pos

            ext = resolved.suffix.lower()
            lang = Language.python() if ext in (".py", ".pyx", ".pyi") else (Language.json() if ext == ".json" else Language.c_plus_plus())
            self.source_editor.language = lang
            self.source_editor.set_text(code)
            if line:
                t_line = max(0, int(line) - 1)
                self.source_editor.set_cursor(Pos(t_line, 0))
                self.source_editor.scroll_to_line(t_line, align="middle")
            self.source_view = True
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to open source file {resolved}: {e}")
            return False

    def open_page(self, path: str | pathlib.Path, anchor: str | None = None, add_history: bool = True) -> bool:
        path_str = str(path).strip()
        if "#" in path_str:
            clean_path, _, hash_anchor = path_str.partition("#")
            path = clean_path
            if not anchor:
                anchor = hash_anchor

        candidate_path = pathlib.Path(path)
        if not candidate_path.is_absolute() and self.current_path is not None:
            relative = self.current_path.parent / candidate_path
            if relative.is_file():
                candidate_path = relative
        resolved = candidate_path.resolve()
        if not resolved.is_file():
            # Try resolving relative to docs root
            docs_r = help_toc.docs_root()
            candidate = docs_r / path
            if candidate.is_file():
                resolved = candidate.resolve()
            else:
                repo_r = help_toc.repository_root()
                candidate2 = repo_r / path
                if candidate2.is_file():
                    resolved = candidate2.resolve()
                else:
                    for sub in ("guides", "concepts", "manual", "getting_started"):
                        c = docs_r / sub / path
                        if c.is_file():
                            resolved = c.resolve()
                            break

        if not resolved.is_file():
            _LOGGER.warning(f"Documentation page not found: {path}")
            return False

        try:
            content = help_io.read_doc(str(resolved))
            if content is None:
                with open(resolved, "r", encoding="utf-8") as f:
                    content = f.read()

            self.current_path = resolved
            node = self.doc_nodes.get(str(resolved))
            self.current_title = node.title if node else resolved.stem.replace("_", " ").title()
            self.current_content = content
            self.current_blocks = parse_markdown_blocks(content, base_dir=resolved.parent)
            self.editor.text = content
            self.is_modified = False
            self.edit_mode = False
            self.source_view = False

            # Set targeted anchor
            clean_anc = anchor.strip().lstrip("#") if anchor else None
            self.current_anchor = clean_anc
            self.target_anchor = clean_anc
            try:
                address = resolved.relative_to(help_toc.repository_root()).as_posix()
            except ValueError:
                address = str(resolved)
            self.address_text = address + (f"#{clean_anc}" if clean_anc else "")
            self.navigation_error = ""

            # Check review status
            self.review_status = self._get_review_status(resolved)

            if add_history:
                self._record_history(resolved, clean_anc)

            return True
        except Exception as e:
            _LOGGER.error(f"Failed to open page {path}: {e}")
            return False

    def set_font_size(self, size: float) -> None:
        self.font_size = max(7.0, min(24.0, float(size)))

    def zoom(self, steps: int = 1) -> None:
        self.set_font_size(self.font_size + steps * 0.5)

    def reset_zoom(self) -> None:
        self.font_size = 12.0

    def _get_review_status(self, path: pathlib.Path) -> str:
        return help_review.status_of(path).status

    def refresh_review_summary(self) -> None:
        self._review_cache.clear()
        try:
            self.review_summary = help_review.scan().summary()
        except Exception as error:
            self.review_summary = f"Could not read review summary: {error}"

    def set_review_status(self, status: str) -> bool:
        path = self.current_path
        if path is None or not help_review.is_tracked(path):
            self.navigation_error = "Review sign-off is available only for tracked documentation pages."
            return False
        if self.editor.text != self.current_content:
            self.navigation_error = "Save source changes before recording review status."
            return False
        try:
            reviewer = "agent" if status == help_review.STATUS_AI_REVIEWED else getpass.getuser()
            kind = "ai" if status == help_review.STATUS_AI_REVIEWED else "human"
            if not help_review.set_status(path, status, reviewer=reviewer, reviewer_kind=kind):
                self.navigation_error = f"Could not record review status for {path.name}."
                return False
            self.review_status = self._get_review_status(path)
            self.navigation_error = ""
            self.refresh_review_summary()
            return True
        except Exception as error:
            self.navigation_error = f"Could not record review status: {error}"
            return False

    def review_status_for(self, path) -> str:
        key = str(path)
        if key not in self._review_cache:
            self._review_cache[key] = self._get_review_status(pathlib.Path(path))
        return self._review_cache[key]

    def address_suggestions(self, query: str) -> list[str]:
        if query.startswith("cite:"):
            from chisurf.plugins.core.help.api.bibliography import bibliography
            return [f"cite:{key}" for key in bibliography() if key.lower().startswith(query[5:].lower())][:8]
        options = []
        for node in self.order:
            if not node.path:
                continue
            path = pathlib.Path(node.path)
            try:
                address = path.relative_to(help_toc.repository_root()).as_posix()
            except ValueError:
                address = str(path)
            if query.lower() in address.lower():
                options.append(address)
        return options[:8]

    def navigate_address(self, address: str) -> bool:
        text = address.strip()
        self.address_text = text
        self.navigation_error = ""
        if not text:
            return False
        base = self.current_path.parent if self.current_path else None
        if text.startswith(("http://", "https://", "ftp://", "doi:", "mailto:")):
            from chisurf.emtk.doc_links import open_link
            return open_link(text, base)
        if text.startswith("cite:"):
            from chisurf.emtk.doc_links import open_link
            from chisurf.plugins.core.help.api.bibliography import bibliography, entry_url
            entry = bibliography().get(text[5:].strip())
            if entry is not None:
                return open_link(entry_url(entry), base)
            self.navigation_error = f"Unknown citation: {text[5:]}"
            return False
        from chisurf.plugins.core.help.api.source_links import is_source_path
        if text.startswith(("src:", "source:", "code:")) or is_source_path(text):
            from chisurf.emtk.code_links import open_source
            if open_source(text, base, prefer_emtk=True):
                return True
            self.navigation_error = f"Source target was not found: {text}"
            return False
        if text.startswith("#"):
            self.jump_to_anchor(text[1:])
            return True
        if text.startswith("ref:"):
            target = resolve_ref(text[4:])
            if target is not None:
                return self.open_page(target, anchor=text[4:])
        target_text, _, anchor = text.partition("#")
        target = resolve_document(target_text, base)
        if target is not None:
            return self.open_page(target, anchor=anchor or None)
        self.update_search(text)
        return True

    def save_current_page(self) -> bool:
        if not self.current_path:
            return False
        new_text = self.editor.text
        ok = help_io.save_doc(str(self.current_path), new_text)
        if ok:
            self.current_content = new_text
            self.current_blocks = parse_markdown_blocks(new_text, base_dir=self.current_path.parent)
            self.is_modified = False
            self.editor.mark_saved()
            self.review_status = self._get_review_status(self.current_path)
            self._review_cache.clear()
            if self.authoring_mode:
                self.refresh_review_summary()
        else:
            self.navigation_error = f"Could not save {self.current_path}."
        return ok

    def go_back(self) -> None:
        if self.history_idx > 0:
            self.history_idx -= 1
            target = self.history[self.history_idx]
            if target is None:
                self.show_home(add_history=False)
            else:
                self.open_page(target, anchor=self._history_anchors[self.history_idx], add_history=False)

    def go_forward(self) -> None:
        if self.history_idx < len(self.history) - 1:
            self.history_idx += 1
            target = self.history[self.history_idx]
            if target is None:
                self.show_home(add_history=False)
            else:
                self.open_page(target, anchor=self._history_anchors[self.history_idx], add_history=False)

    def go_prev_order(self) -> None:
        if not self.current_path or not self.order:
            return
        curr_str = str(self.current_path)
        for i, node in enumerate(self.order):
            if node.path and str(pathlib.Path(node.path).resolve()) == curr_str:
                if i > 0 and self.order[i - 1].path:
                    self.open_page(self.order[i - 1].path)
                return

    def go_next_order(self) -> None:
        if not self.current_path or not self.order:
            return
        curr_str = str(self.current_path)
        for i, node in enumerate(self.order):
            if node.path and str(pathlib.Path(node.path).resolve()) == curr_str:
                if i < len(self.order) - 1 and self.order[i + 1].path:
                    self.open_page(self.order[i + 1].path)
                return

    # -- Search ---------------------------------------------------------------

    def update_search(self, query: str) -> None:
        self.search_query = query
        q = query.strip()
        if not q:
            self.search_results.clear()
            return
        try:
            self.search_results = help_io.search_docs(q)[:25]
        except Exception as e:
            _LOGGER.warning(f"Error during search: {e}")
            self.search_results.clear()

    search = update_search

    # -- AI Ask Docs Assistant ------------------------------------------------

    def ask(self, question: str) -> None:
        clean_q = question.strip()
        if not clean_q or self.is_asking or self._closed:
            return

        self.chat_history.add_message("user", clean_q)
        self.is_asking = True

        self._ask_generation += 1
        threading.Thread(target=self._run_ask_thread, args=(clean_q, self._ask_generation), daemon=True).start()

    def cancel_ask(self) -> None:
        self._ask_generation += 1
        self.is_asking = False
        self.chat_history.finish_generation("cancelled")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel_ask()
        unregister_help_model(self)
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except Empty:
                break

    def _queue_ask_event(self, generation: int, callback: Callable[[], None]) -> None:
        if not self._closed:
            self.event_queue.put(lambda: callback() if not self._closed and generation == self._ask_generation else None)

    def _run_ask_thread(self, question: str, generation: int | None = None) -> None:
        generation = self._ask_generation if generation is None else generation
        try:
            from chisurf.plugins.core.help.api.ask import ask as ask_api

            answer = ask_api(question)
            if answer.ok:
                resp_text = answer.text
                if answer.pages:
                    resp_text += "\n\n**Cited Documentation Pages:**"
                    for p in answer.pages:
                        title = p.get("title") or p.get("document", "Doc")
                        doc_path = p.get("document", "")
                        resp_text += f"\n- [{title}]({doc_path})"

                self._queue_ask_event(generation, lambda: self.chat_history.add_message("assistant", resp_text))
            else:
                err_msg = answer.error or "Failed to retrieve an answer."
                self._queue_ask_event(generation, lambda: self.chat_history.add_message("error", f"Assistant error: {err_msg}"))
        except Exception as err:
            error_text = f"Could not answer from docs: {err}"
            self._queue_ask_event(generation,
                lambda: self.chat_history.add_message("error", error_text)
            )
        finally:
            self._queue_ask_event(generation, self._finish_ask)

    def _finish_ask(self) -> None:
        self.is_asking = False
        self.chat_history.finish_generation("complete")

    def process_events(self) -> None:
        if self._closed:
            return
        while not self.event_queue.empty():
            try:
                fn = self.event_queue.get_nowait()
                fn()
            except Empty:
                break
            except Exception as e:
                _LOGGER.error(f"Error executing queued help event: {e}")


class HelpGui:
    """EMTK immediate-mode rendering and interaction for the Help Browser."""

    def __init__(self, model: HelpModel | None = None) -> None:
        self.model = model or HelpModel()
        self.texture_mgr = HelpTextureManager()
        self.provider_settings = None
        self.provider_settings_open = False

        # Keep navigation and the assistant in tabs so the document has room to read.
        layout = Split("h", 0.24, Region("toc"), Region("document"))
        self.docks = DockManager(layout)
        self.docks.add_window("toc", "Documentation", self._draw_toc_pane, dock="toc", closable=True, scrollable=False)
        self.docks.add_window("document", "Document", self._draw_document_pane, dock="document", closable=True, scrollable=False)
        self.docks.add_window("ask", "Ask Docs", self._draw_ask_pane, dock="toc", closable=True, scrollable=False)
        self._reveal_keys: set[int] = set()
        self._revealed_for: pathlib.Path | None = None

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        self.model.process_events()
        if self.provider_settings is not None:
            self.provider_settings.process_events()
        io = im.get_io()
        if (io.key_ctrl or io.key_super) and io.mouse_wheel:
            self.model.zoom(1 if io.mouse_wheel > 0 else -1)
            io.mouse_wheel = 0.0

        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1200.0)
        height = float(h or vp.size[1] or 760.0)

        im.push_font("sans-serif")
        self.docks.draw((0.0, 0.0, width, height))
        im.pop_font()
        self._draw_provider_settings()

    def _expand_inline_markup(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Expand inline math and Sphinx/MyST roles, returning clean text and links."""
        base_dir = self.model.current_path.parent if self.model.current_path else None
        links: list[tuple[str, str]] = []

        # 1. Expand roles: {ref}`...`, {doc}`...`, {src}`...`, {cite}`...`
        def role_repl(m: re.Match) -> str:
            role, body = m.group(1), m.group(2)
            if role == "src":
                from chisurf.plugins.core.help.api import source_links

                clean_body = body.strip()
                caption = ""
                if "<" in clean_body and clean_body.endswith(">"):
                    caption, clean_body = clean_body[: clean_body.index("<")].strip(), clean_body[clean_body.index("<") + 1 : -1]
                resolved = source_links.resolve(clean_body, base_dir)
                label = caption or source_links.link_label(clean_body, resolved)
                target = f"src:{clean_body}"
                if (label, target) not in links:
                    links.append((label, target))
                return f"`{label}`"

            if role == "cite":
                from chisurf.plugins.core.help.api import bibliography as bib
                from chisurf.plugins.core.help.api.xref import ref_index

                entries = bib.bibliography()
                refs = ref_index()
                labels = []
                for key in (k.strip() for k in body.split(",")):
                    if not key:
                        continue
                    entry = entries.get(key)
                    if entry is not None:
                        label = bib.short_citation(entry)
                        target = bib.entry_url(entry)
                        if (label, target) not in links:
                            links.append((label, target))
                        labels.append(label)
                    elif key in refs:
                        ref_entry = refs[key]
                        label = ref_entry[1] or key
                        target = f"{ref_entry[0]}#{key}"
                        if (label, target) not in links:
                            links.append((label, target))
                        labels.append(label)
                    else:
                        labels.append(f"`{key}`")
                return "; ".join(labels) if labels else body

            path, anchor, label = document_reference(role, body, base_dir)
            target = f"{path}#{anchor}" if (path and anchor) else (str(path) if path else body)
            caption = label or body
            if path or anchor:
                if (caption, target) not in links:
                    links.append((caption, target))
            return caption

        s = re.sub(r"\{(ref|doc|numref|eq|term|src|cite)\}`([^`]+)`", role_repl, text)

        # 2. Extract standard markdown links: [label](target)
        def link_repl(m: re.Match) -> str:
            label, target = m.group(1), m.group(2)
            from chisurf.plugins.core.help.api.source_links import is_source_path

            if is_source_path(target):
                if not target.startswith(("src:", "code:", "source:")):
                    target = f"src:{target}"
            if (label, target) not in links:
                links.append((label, target))
            return label

        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, s)

        # 3. Format inline math: $...$
        def math_repl(m: re.Match) -> str:
            expr = m.group(1).strip()
            return format_inline_math(expr)

        s = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", math_repl, s)

        # 4. Strip stray markdown bold/italic asterisks for clean reading
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)

        return s, links

    # -- Left Pane: Table of Contents & Search --------------------------------

    def _ancestors_of_current(self) -> set[int]:
        """ids of the tree nodes above the open page."""
        target = str(self.model.current_path) if self.model.current_path else None
        if target is None or self.model.toc is None:
            return set()

        def walk(node, trail):
            for child in node.children:
                if child.path and str(pathlib.Path(child.path).resolve()) == target:
                    return trail
                found = walk(child, trail | {id(child)})
                if found is not None:
                    return found
            return None

        return walk(self.model.toc, set()) or set()

    def _draw_toc_pane(self, box: tuple[float, float, float, float]) -> None:
        avail_w = box[2]
        if self.model.current_path != self._revealed_for:
            self._revealed_for = self.model.current_path
            self._reveal_keys = self._ancestors_of_current()

        if self.model.authoring_mode:
            statuses = ["all", help_review.STATUS_UNREVIEWED, help_review.STATUS_AI_REVIEWED,
                help_review.STATUS_REVIEWED, help_review.STATUS_STALE]
            im.set_next_item_width(avail_w)
            changed_filter, selected = im.combo("##review_filter", statuses.index(self.model.review_filter),
                ["All pages", "Unreviewed", "AI-reviewed", "Human-reviewed", "Stale"])
            im.set_item_tooltip("Filter tracked documentation by its review status")
            if changed_filter:
                self.model.review_filter = statuses[selected]
        # Search bar
        im.set_next_item_width(avail_w)
        changed, new_q = im.input_text("##doc_search", self.model.search_query, hint="Search documentation...")
        im.set_item_tooltip("Search documentation titles and text")
        if changed:
            self.model.update_search(new_q)

        im.separator()

        curr_y = im.get_cursor_screen_pos()[1]
        rem_h = max(20.0, box[1] + box[3] - curr_y)
        im.begin_child((*im.get_cursor_screen_pos(), avail_w, rem_h), child_id="toc_tree_view")

        # Show Search Results if query active
        if self.model.search_query.strip():
            im.text_disabled(f"Search results for '{self.model.search_query.strip()}':")
            im.dummy(0.0, 4.0)

            if not self.model.search_results:
                im.text_disabled("No matching documentation found.")
            else:
                for idx, res in enumerate(self.model.search_results):
                    im.push_id(f"sr_{idx}")
                    title = res.get("title") or "Untitled"
                    path_str = res.get("path", "")
                    excerpt = res.get("excerpt", "")

                    active = bool(self.model.current_path and pathlib.Path(path_str).resolve() == self.model.current_path)
                    if im.selectable(title, active):
                        self.model.open_page(path_str)
                    im.set_item_tooltip("Open this documentation item")
                    self._draw_document_context_menu(path_str)

                    if excerpt:
                        im.text_disabled(f"  {excerpt[:90]}...")
                    im.dummy(0.0, 2.0)
                    im.pop_id()
        else:
            # Show TOC Tree
            if self.model.toc:
                for idx, section in enumerate(self.model.toc.children):
                    self._draw_toc_node(section, f"sec_{idx}")
            else:
                im.text_disabled("Documentation TOC is unavailable.")

        im.end_child()
        self._reveal_keys = set()

    def _matches_review_filter(self, node) -> bool:
        if not self.model.authoring_mode or self.model.review_filter == "all":
            return True
        if node.children:
            return any(self._matches_review_filter(child) for child in node.children)
        return (not node.path or not help_review.is_tracked(node.path)
            or self.model.review_status_for(node.path) == self.model.review_filter)

    def _draw_toc_node(self, node: help_toc.Node, key: str) -> None:
        if not self._matches_review_filter(node):
            return
        im.push_id(key)
        has_children = bool(node.children)

        if has_children:
            # The branch holding the open page opens itself once per page, as the
            # Qt tree expands to the selected item. `collapsing_header(label, True)`
            # plus the indent is `tree_node` opened from outside: emtk's tree_node
            # ignores `set_next_item_open`.
            if id(node) in self._reveal_keys:
                expanded = im.collapsing_header(node.title, True)
                if expanded:
                    im.indent()
            else:
                expanded = im.tree_node(node.title)
            im.set_item_tooltip(f"Expand or collapse {node.title}")
            if expanded:
                for idx, child in enumerate(node.children):
                    self._draw_toc_node(child, f"c_{idx}")
                im.tree_pop()
        else:
            is_active = bool(
                self.model.current_path
                and node.path
                and str(pathlib.Path(node.path).resolve()) == str(self.model.current_path)
            )
            label = node.title
            status = self.model.review_status_for(node.path) if self.model.authoring_mode and node.path and help_review.is_tracked(node.path) else None
            colors = {help_review.STATUS_REVIEWED: (130, 220, 140, 255), help_review.STATUS_AI_REVIEWED: (110, 190, 255, 255),
                help_review.STATUS_STALE: (235, 185, 95, 255), help_review.STATUS_UNREVIEWED: (225, 125, 125, 255)}
            if status in colors:
                im.push_style_color(Col.TEXT, colors[status])
            if im.selectable(label, is_active):
                if node.path:
                    self.model.open_page(node.path)
            if status in colors:
                im.pop_style_color()
            im.set_item_tooltip(f"{node.title} — {status}" if status else node.title)
            self._draw_document_context_menu(node.path)

        im.pop_id()

    def _draw_document_context_menu(self, path: str | pathlib.Path | None) -> None:
        if not path or not im.begin_popup_context_item("document_actions"):
            return
        if im.menu_item("Open document"):
            self.model.open_page(path)
        im.set_item_tooltip('Open document')
        if im.menu_item("View source"):
            if self.model.open_page(path):
                self.model.edit_mode = True
        im.set_item_tooltip('View source')
        if im.menu_item("Copy path"):
            im.set_clipboard_text(str(pathlib.Path(path).resolve()))
        im.set_item_tooltip('Copy path')
        im.end_popup()

    # -- Center Pane: Document Reader & Editor --------------------------------

    def _draw_document_pane(self, box: tuple[float, float, float, float]) -> None:
        im.set_next_item_width(max(100.0, box[2] - 64.0))
        changed, address = im.input_text("##doc_address", self.model.address_text,
            hint="docs/page.md#anchor, src:path#symbol, cite:key, URL or search")
        self.model.address_text = address
        im.set_item_tooltip("Enter a document, source symbol, citation key or web address; press Enter or Go")
        entered = im.is_item_active() and im.is_key_pressed(im.Key.ENTER)
        if changed and self.model.address_suggestions(address):
            im.open_popup("address_suggestions")
        im.same_line()
        if im.button("Go") or entered:
            self.model.navigate_address(address)
        im.set_item_tooltip("Navigate to this address or search for its text")
        if im.begin_popup("address_suggestions"):
            for index, suggestion in enumerate(self.model.address_suggestions(address)):
                if im.selectable(f"{suggestion}##address_{index}"):
                    self.model.navigate_address(suggestion)
                    im.close_current_popup()
                im.set_item_tooltip("Open this documentation address")
            im.end_popup()
        if self.model.navigation_error:
            im.text_wrapped(self.model.navigation_error)
        # Navigation toolbar with clear emoticons and tooltips
        if im.button("Home"):
            self.model.show_home()
        im.set_item_tooltip('Show documentation start page')
        im.same_line()
        can_back = self.model.history_idx > 0
        im.begin_disabled(not can_back)
        if im.button("Back"):
            self.model.go_back()
        im.set_item_tooltip('Return to the previous page in navigation history')
        im.end_disabled()

        im.same_line()
        can_fwd = self.model.history_idx < len(self.model.history) - 1
        im.begin_disabled(not can_fwd)
        if im.button("Fwd"):
            self.model.go_forward()
        im.set_item_tooltip('Advance to the next page in navigation history')
        im.end_disabled()

        im.same_line()
        if im.button("Prev"):
            self.model.go_prev_order()
        im.set_item_tooltip('Open the previous document in the table of contents')
        im.same_line()
        if im.button("Next"):
            self.model.go_next_order()
        im.set_item_tooltip('Open the next document in the table of contents')

        im.dummy(0.0, 2.0)
        import webbrowser
        if im.button("Online docs"):
            from chisurf.core.info import help_url

            webbrowser.open_new(help_url)
        im.set_item_tooltip("Open the documentation website in a browser")
        im.same_line()
        if im.button("Videos"):
            webbrowser.open_new("https://www.peulen.xyz/tutorial/")
        im.set_item_tooltip('Open tutorial videos in your web browser')

        im.same_line()
        im.text_disabled("|")
        im.same_line()

        # View / Edit Mode Toggle
        mode_btn_label = "Read" if self.model.edit_mode else "Source"
        im.begin_disabled(self.model.current_path is None)
        if im.button(mode_btn_label):
            self.model.edit_mode = not self.model.edit_mode
        im.set_item_tooltip("Switch between reading the document and editing its source; the virtual Home page has no source file")
        im.end_disabled()

        if self.model.edit_mode:
            im.same_line()
            if im.button("Save"):
                self.model.save_current_page()
            im.set_item_tooltip('Save changes to the current documentation source')

        im.same_line()
        # Review status badge with explicit icon
        if self.model.current_path is not None and help_review.is_tracked(self.model.current_path):
            badge_col, badge_text = self._status_badge(self.model.review_status)
            im.text_colored(badge_col, badge_text)
        im.same_line()
        if im.small_button("A−"):
            self.model.zoom(-1)
        im.set_item_tooltip("Reduce document text by half a point")
        im.same_line()
        if im.small_button("Reset zoom"):
            self.model.reset_zoom()
        im.set_item_tooltip("Restore the default 12-point document text")
        im.same_line()
        if im.small_button("A+"):
            self.model.zoom(1)
        im.set_item_tooltip("Increase document text by half a point; Ctrl/Command+wheel also zooms")
        changed_authoring, authoring = im.checkbox("Authoring tools", self.model.authoring_mode)
        im.set_item_tooltip("Show human and AI review sign-off actions, status filters and manual review summary")
        if changed_authoring:
            self.model.authoring_mode = authoring
            if authoring:
                self.model.refresh_review_summary()
            else:
                self.model.review_filter = "all"
        if self.model.authoring_mode:
            im.same_line()
            changed_dev, include_dev = im.checkbox("Developer docs", self.model.include_development)
            im.set_item_tooltip("Also list architecture notes and the bundled modules' documentation.")
            if changed_dev:
                self.model.set_include_development(include_dev)
            tracked = self.model.current_path is not None and help_review.is_tracked(self.model.current_path)
            if tracked:
                for label, status in [("Mark human reviewed", help_review.STATUS_REVIEWED),
                    ("Mark AI reviewed", help_review.STATUS_AI_REVIEWED), ("Clear review", help_review.STATUS_UNREVIEWED)]:
                    if im.small_button(label):
                        self.model.set_review_status(status)
                    im.set_item_tooltip("Record this saved page's review status; later edits make the sign-off stale")
                    im.same_line()
                im.text_disabled("")
            else:
                im.text_disabled("Review sign-off is available for tracked documentation pages.")
            im.text_wrapped(self.model.review_summary)
        crumbs = self.model.breadcrumb()
        if crumbs:
            im.text_disabled(" › ".join(crumbs))
        im.separator()

        curr_y = im.get_cursor_screen_pos()[1]
        avail_w = box[2]
        avail_h = max(20.0, box[1] + box[3] - curr_y)

        if self.model.source_view and self.model.source_path:
            # Embedded Source Code Viewer
            if im.button("Back to document"):
                self.model.source_view = False
            im.set_item_tooltip("Return from the source view to the document")

            im.same_line()
            im.text_disabled("|")
            im.same_line()
            sym_str = f" :: {self.model.source_symbol}" if self.model.source_symbol else ""
            line_str = f" (Line {self.model.source_line})" if self.model.source_line else ""
            im.text_colored((140, 205, 255, 255), f"{self.model.source_path.name}{sym_str}{line_str}")

            im.same_line()
            im.text_disabled("|")
            im.same_line()
            if im.small_button("Open in code editor##open_ext"):
                from chisurf.emtk.code_links import open_source

                t = f"{self.model.source_path}#{self.model.source_symbol or (self.model.source_line or '')}"
                open_source(t)
            im.set_item_tooltip("Open this source file in the code editor")

            im.separator()
            curr_v_y = im.get_cursor_screen_pos()[1]
            rem_h = max(20.0, box[1] + box[3] - curr_v_y)
            im.text_editor("##doc_source_viewer", self.model.source_editor, (avail_w, rem_h))
            im.set_item_tooltip("Read the referenced source; open the full code editor to edit it")
            return

        if self.model.edit_mode:
            # Source Editor mode
            im.text_editor("##doc_source_editor", self.model.editor, (avail_w, avail_h))
            self.model.is_modified = self.model.editor.text != self.model.current_content
            im.set_item_tooltip("Edit the documentation source; Save writes your changes to the document")
        else:
            # Formatted Reader view
            self._draw_markdown_reader(avail_w, avail_h)

    def _status_badge(self, status: str) -> tuple[tuple[int, int, int, int], str]:
        if status == help_review.STATUS_REVIEWED:
            return (130, 220, 140, 255), "[Reviewed]"
        elif status == help_review.STATUS_AI_REVIEWED:
            return (110, 190, 255, 255), "[AI reviewed]"
        elif status == help_review.STATUS_STALE:
            return (235, 185, 95, 255), "[Needs review]"
        return (180, 185, 195, 255), "[Draft]"

    def _handle_link_click(self, target: str) -> None:
        target = str(target or "").strip()
        if not target:
            return

        if target.startswith(("http://", "https://", "ftp://", "mailto:")):
            import webbrowser

            try:
                webbrowser.open_new(target)
            except Exception:
                pass
            return

        from chisurf.plugins.core.help.api.source_links import is_source_path

        if target.startswith(("src:", "code:", "source:")) or is_source_path(target):
            base = self.model.current_path.parent if self.model.current_path else None
            from chisurf.emtk.code_links import open_source

            open_source(target, base, prefer_emtk=True)
            return

        if target.startswith("#"):
            self.model.jump_to_anchor(target.lstrip("#"))
            return

        self.model.open_page(target)

    def _draw_link_chips(self, links: list[tuple[str, str]], id_prefix: str) -> None:
        if not links:
            return
        im.dummy(0.0, 1.0)
        sep_w = im.calc_text_size("•")[0] + 12.0
        is_first = True
        for l_idx, (label, target) in enumerate(links):
            link_label = label
            tw = im.calc_text_size(link_label)[0]
            needed_w = tw if is_first else (tw + sep_w)

            if not is_first:
                avail = im.get_line_avail()
                if avail >= needed_w:
                    im.same_line()
                    im.text_disabled("•")
                    im.same_line()
                else:
                    is_first = True

            if im.text_link(f"{link_label}##{id_prefix}_{l_idx}"):
                self._handle_link_click(target)
            im.set_item_tooltip(f"Open: {target}")
            is_first = False

    def _draw_markdown_reader(self, width: float, height: float) -> None:
        """Render formatted markdown elements in an immediate-mode child container."""
        child_id = f"doc_{self.model.current_path or 'home'}"
        child_start_y = im.get_cursor_screen_pos()[1]
        im.begin_child((*im.get_cursor_screen_pos(), width, height), child_id=child_id)

        if not self.model.current_blocks:
            im.dummy(0.0, 20.0)
            im.text_disabled("No document content loaded.")
            im.end_child()
            return

        im.push_font({"family": "sans-serif", "size": self.model.font_size})

        for idx, block in enumerate(self.model.current_blocks):
            im.push_id(f"blk_{idx}")

            # Check targeted anchor
            if self.model.target_anchor and getattr(block, "anchors", None):
                wanted = self.model.target_anchor.lower().strip()
                wanted_stem = wanted.rstrip("s")
                words = [w.rstrip("s") for w in re.split(r"[^\w]+", wanted) if len(w) > 2]
                match = any(
                    wanted == a.lower()
                    or wanted in a.lower()
                    or a.lower() in wanted
                    or (wanted_stem and wanted_stem in a.lower())
                    or any(w in a.lower() for w in words)
                    for a in block.anchors
                )
                if match:
                    block_rel_y = im.get_cursor_screen_pos()[1] - child_start_y + im.get_scroll_y()
                    im.set_scroll_y(max(0.0, block_rel_y - 12.0))
                    self.model.target_anchor = None

            if block.kind == "h1":
                im.dummy(0.0, 12.0)
                clean_title, _ = self._expand_inline_markup(block.text)
                im.push_font({"family": "sans-serif", "bold": True})
                im.push_font_scale(1.55)
                im.text_colored((125, 205, 255, 255), clean_title)
                im.pop_font_scale()
                im.pop_font()
                im.dummy(0.0, 2.0)
                im.separator()
                im.dummy(0.0, 6.0)

            elif block.kind == "h2":
                im.dummy(0.0, 10.0)
                clean_title, _ = self._expand_inline_markup(block.text)
                im.push_font({"family": "sans-serif", "bold": True})
                im.push_font_scale(1.3)
                im.text_colored((145, 225, 160, 255), clean_title)
                im.pop_font_scale()
                im.pop_font()
                im.dummy(0.0, 4.0)

            elif block.kind == "h3":
                im.dummy(0.0, 8.0)
                clean_title, _ = self._expand_inline_markup(block.text)
                im.push_font({"family": "sans-serif", "bold": True})
                im.push_font_scale(1.15)
                im.text_colored((245, 205, 115, 255), clean_title)
                im.pop_font_scale()
                im.pop_font()
                im.dummy(0.0, 3.0)

            elif block.kind == "h4":
                im.dummy(0.0, 6.0)
                clean_title, _ = self._expand_inline_markup(block.text)
                im.push_font({"family": "sans-serif", "bold": True})
                im.push_font_scale(1.05)
                im.text_colored((220, 225, 235, 255), clean_title)
                im.pop_font_scale()
                im.pop_font()
                im.dummy(0.0, 2.0)

            elif block.kind == "p":
                clean_text, links = self._expand_inline_markup(block.text)
                if not links or clean_text.strip() != "; ".join(label for label, _ in links):
                    im.text_wrapped(clean_text)
                if links:
                    self._draw_link_chips(links, f"plnk_{idx}")
                im.dummy(0.0, 4.0)

            elif block.kind == "math":
                im.dummy(0.0, 4.0)
                im.math(
                    block.text,
                    colour=(216, 222, 233, 255),
                    font_size=20.0 * self.model.font_size / 12.0,
                    scale=1.0,
                    align_center=True,
                    max_width=max(50.0, width - 28.0),
                )
                im.dummy(0.0, 4.0)

            elif block.kind == "figure":
                tex = self.texture_mgr.get_figure_texture(block.arg, self.model.current_path)
                if tex is not None:
                    im.dummy(0.0, 6.0)
                    max_w = max(100.0, width - 28.0)
                    pct = 1.0
                    if block.items and len(block.items) > 1 and "%" in str(block.items[1]):
                        try:
                            pct = float(str(block.items[1]).replace("%", "").strip()) / 100.0
                        except ValueError:
                            pct = 1.0
                    target_max_w = max_w * pct
                    im.image(
                        tex,
                        max_size=(target_max_w, 560.0),
                        align_center=True,
                    )

                    if block.text:
                        im.dummy(0.0, 2.0)
                        caption, _ = self._expand_inline_markup(block.text)
                        im.push_style_color(Col.TEXT, (175, 185, 200, 255))
                        im.text_wrapped(f"Figure: {caption}")
                        im.pop_style_color()
                    im.dummy(0.0, 6.0)
                else:
                    im.dummy(0.0, 4.0)
                    im.text_disabled(f"[Figure: {block.arg}]")
                    if block.text:
                        im.text_disabled(f"  {block.text}")
                    im.dummy(0.0, 4.0)

            elif block.kind == "code":
                im.dummy(0.0, 2.0)
                lang_tag = f" [{block.arg}]" if block.arg else ""
                im.text_disabled(f"Code{lang_tag}")
                im.same_line()
                if im.small_button(f"Copy##cp_{idx}"):
                    try:
                        from emtk.clipboard import set_clipboard_text

                        set_clipboard_text(block.text)
                    except Exception:
                        pass
                im.set_item_tooltip("Copy this code block to the clipboard")

                im.push_font("monospace")
                im.push_style_color(Col.FRAME_BG, (20, 24, 30, 255))
                im.text_wrapped(block.text)
                im.pop_style_color()
                im.pop_font()
                im.dummy(0.0, 4.0)

            elif block.kind == "admonition":
                adm_color = (
                    (110, 190, 255, 255)
                    if block.arg in ("note", "tip", "hint", "seealso")
                    else ((235, 185, 95, 255) if block.arg in ("warning", "caution", "attention") else (245, 110, 110, 255))
                )
                adm_title = block.items[0] if block.items else block.arg.capitalize()
                clean_body, adm_links = self._expand_inline_markup(block.text)
                im.dummy(0.0, 4.0)
                x, y = im.get_cursor_screen_pos()
                body_w = max(40.0, width - 24.0)
                measured_w, measured_h = im.calc_text_size(clean_body, wrap_width=body_w)
                line_height = im.get_text_line_height_with_spacing()
                estimated_lines = max(1, int((measured_h + line_height - 1) // line_height))
                if measured_w > body_w:
                    estimated_lines *= max(1, int((measured_w + body_w - 1) // body_w))
                panel_h = 20.0 + line_height * (1 + estimated_lines + len(adm_links))
                draw_list = im.get_window_draw_list()
                draw_list.add_rect_filled((x, y), (x + width, y + panel_h), (30, 40, 55, 255))
                draw_list.add_rect_filled((x, y), (x + 3.0, y + panel_h), adm_color)
                im.indent(12.0)
                im.dummy(0.0, 6.0)
                im.push_font({"family": "sans-serif", "bold": True})
                im.text_colored(adm_color, adm_title)
                im.pop_font()
                im.text_wrapped(clean_body)
                if adm_links:
                    self._draw_link_chips(adm_links, f"admlnk_{idx}")
                im.dummy(0.0, 8.0)
                im.unindent(12.0)
                remaining = y + panel_h - im.get_cursor_screen_pos()[1]
                if remaining > 0:
                    im.dummy(0.0, remaining)
                im.dummy(0.0, 6.0)

            elif block.kind == "table" and block.items:
                rows = [item.split("\t") for item in block.items]
                cols = max(len(r) for r in rows) if rows else 1
                im.dummy(0.0, 4.0)
                column_widths = [max(im.calc_text_size(self._expand_inline_markup(row[column] if column < len(row) else "")[0])[0]
                    for row in rows) + 24.0 for column in range(cols)]
                table_width = min(width, sum(column_widths))
                scale = table_width / max(1.0, sum(column_widths))
                if im.begin_table(f"tbl_{idx}", cols, flags=im.TableFlags.BORDERS | im.TableFlags.ROW_BG, size=(table_width, 0.0)):
                    for column, column_width in enumerate(column_widths):
                        im.table_setup_column(str(column), flags=im.TableColumnFlags.WIDTH_FIXED, init_width_or_weight=column_width * scale)
                    for r_idx, row in enumerate(rows):
                        im.table_next_row()
                        for c_idx in range(cols):
                            cell_text = row[c_idx] if c_idx < len(row) else ""
                            im.table_next_column()
                            clean_cell, _ = self._expand_inline_markup(cell_text)
                            if r_idx == 0:
                                im.push_font({"family": "sans-serif", "bold": True})
                                im.text_colored((140, 200, 255, 255), clean_cell)
                                im.pop_font()
                            else:
                                im.text_wrapped(clean_cell)
                    im.end_table()
                im.dummy(0.0, 4.0)

            elif block.kind == "list_item":
                clean_item, item_links = self._expand_inline_markup(block.text)
                bullet = block.arg if block.arg and not block.arg.startswith(("-", "*", "+")) else "•"
                im.text_wrapped(f"  {bullet}  {clean_item}")
                if item_links:
                    self._draw_link_chips(item_links, f"llnk_{idx}")
                im.dummy(0.0, 1.0)


            elif block.kind == "hr":
                im.dummy(0.0, 4.0)
                im.separator()
                im.dummy(0.0, 4.0)

            im.pop_id()

        im.dummy(0.0, 50.0)
        im.pop_font()
        im.end_child()

    def _draw_provider_settings(self) -> None:
        if not self.provider_settings_open or self.provider_settings is None:
            return
        im.set_next_window_size((700, 660), im.Cond.FIRST_USE_EVER)
        if im.begin("Provider settings##help_provider_settings"):
            if im.button("Close provider settings"):
                self.provider_settings_open = False
            im.set_item_tooltip("Close the shared provider configuration form")
            im.begin_child((*im.get_cursor_screen_pos(), *im.get_content_region_avail()), child_id="help_provider_fields")
            self.provider_settings.draw()
            im.end_child()
        im.end()

    # -- Right Pane: Ask AI Assistant -----------------------------------------

    def _draw_ask_pane(self, box: tuple[float, float, float, float]) -> None:
        avail_w = box[2]

        im.text_colored((140, 170, 210, 255), "Ask Documentation AI")
        im.text_disabled("Grounded Q&A from ChiSurf docs")
        if im.small_button("Provider settings…"):
            if self.provider_settings is None:
                from chisurf.plugins.ai_settings.gui.app import AISettingsGui
                self.provider_settings = AISettingsGui()
            self.provider_settings_open = True
        im.set_item_tooltip("Configure the shared API provider, masked credential, models and sampling")
        im.separator()

        # Quick question prompt buttons
        for q_idx, q_text in enumerate(QUICK_QUESTIONS):
            if im.small_button(f"{q_text}##quick_{q_idx}"):
                self.model.ask(q_text)
            im.set_item_tooltip(f"Ask the documentation assistant: {q_text}")

        im.separator()

        # Transcript and input bar
        input_total_h = 52.0 + 30.0 + 14.0
        curr_y = im.get_cursor_screen_pos()[1]
        rem_h = max(70.0, box[1] + box[3] - curr_y - input_total_h)
        transcript_h = rem_h

        draw_chat_transcript(
            self.model.chat_history,
            size=(avail_w, transcript_h),
            on_insert_code=None,
            on_replace_code=None,
        )

        im.separator()

        new_prompt, send_requested = draw_chat_input_bar(
            self.model.input_prompt,
            is_generating=self.model.is_asking,
            on_send=self.model.ask,
            on_cancel=self.model.cancel_ask,
            on_clear=self.model.chat_history.clear,
            input_height=52.0,
        )
        self.model.input_prompt = new_prompt


class HelpApp(ImApp):
    """Standalone pure EMTK Application for the ChiSurf Help Browser."""

    window_size = (800, 600)

    def __init__(self) -> None:
        self.model = HelpModel()
        self.help_gui = HelpGui(model=self.model)
        super().__init__(gui=self._render, continuous=False)

    def export_settings(self) -> dict:
        return {"font_size": self.model.font_size}

    def restore_settings(self, settings: dict) -> None:
        value = settings.get("font_size")
        if isinstance(value, (int, float)):
            self.model.set_font_size(value)

    def close(self) -> None:
        self.model.close()
        if self.help_gui.provider_settings is not None:
            self.help_gui.provider_settings.close()

    def animating(self) -> bool:
        if self.model._closed:
            return False
        return (super().animating() or self.model.is_asking
            or not self.model.event_queue.empty()
            or (self.help_gui.provider_settings is not None and self.help_gui.provider_settings.busy))

    def _render(self) -> None:
        self.help_gui.draw()


def make_help_app() -> HelpApp:
    """Factory for pure EMTK execution (e.g. via emtk.native or emtk.web)."""
    return HelpApp()


def main() -> None:
    """Run Help Browser directly via pure EMTK without Qt."""
    from emtk.native import main as emtk_main

    emtk_main(["--app", "chisurf.plugins.core.help.gui.help_app:make_help_app"])


if __name__ == "__main__":
    main()
