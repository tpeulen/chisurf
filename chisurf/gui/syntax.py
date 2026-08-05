"""Syntax highlighting for every ChiSurf text widget.

One home for what used to be two near-identical copies -- one in the code
editor, one in the node editor -- plus the console's needs. A third copy was
the alternative, and the two that existed had already drifted.

Colours arrive as a *palette* rather than being baked in, because the same
class now serves the editor's colour scheme and each of the console's themes.
The previous copies hard-coded a dark palette and were drawn against the
editor's light ``paper_color``.
"""

from __future__ import annotations

import keyword
import typing

from qtpy import QtCore, QtGui

__all__ = [
    "SyntaxHighlighter",
    "PythonHighlighter",
    "JSONHighlighter",
    "YAMLHighlighter",
    "DEFAULT_DARK",
    "DEFAULT_LIGHT",
    "palette_for_paper",
    "palette_from_editor_settings",
]

#: Token names a palette may define.
TOKENS = (
    "keyword", "builtin", "class", "function", "string", "fstring_expr",
    "comment", "number", "decorator", "self", "operator", "magic",
)

DEFAULT_DARK: dict[str, str] = {
    "keyword": "#569cd6",
    "builtin": "#4ec9b0",
    "class": "#4ec9b0",
    "function": "#dcdcaa",
    "string": "#ce9178",
    "fstring_expr": "#d7ba7d",
    "comment": "#6a9955",
    "number": "#b5cea8",
    "decorator": "#dcdcaa",
    "self": "#9cdcfe",
    "operator": "#d4d4d4",
    "magic": "#c586c0",
}

DEFAULT_LIGHT: dict[str, str] = {
    "keyword": "#0000ff",
    "builtin": "#267f99",
    "class": "#267f99",
    "function": "#795e26",
    "string": "#a31515",
    "fstring_expr": "#8a5a00",
    "comment": "#008000",
    "number": "#098658",
    "decorator": "#795e26",
    "self": "#001080",
    "operator": "#333333",
    "magic": "#af00db",
}

#: Block states. Anything above :data:`IN_STRING_SINGLE` means the block began
#: inside a triple-quoted string, which is what stops a docstring's contents
#: being highlighted as code.
NORMAL = 0
IN_STRING_SINGLE = 1
IN_STRING_DOUBLE = 2


def _is_dark(colour: str) -> bool:
    """Return whether *colour* is dark enough to need light text.

    Parameters
    ----------
    colour : str
        ``#rrggbb``.

    Returns
    -------
    bool
    """
    try:
        value = QtGui.QColor(colour)
        if not value.isValid():
            return True
        # Rec. 709 luma; the midpoint is where light-on-dark stops working.
        return (0.2126 * value.redF() + 0.7152 * value.greenF() + 0.0722 * value.blueF()) < 0.5
    except Exception:
        return True


def palette_for_paper(paper_colour: str) -> dict[str, str]:
    """Return the syntax palette legible against *paper_colour*.

    Parameters
    ----------
    paper_colour : str
        The background the text will be drawn on, ``#rrggbb``.

    Returns
    -------
    dict
    """
    return dict(DEFAULT_DARK if _is_dark(paper_colour) else DEFAULT_LIGHT)


def palette_from_editor_settings() -> dict[str, str]:
    """Return the syntax palette matching the editor's paper colour.

    Returns
    -------
    dict
        :data:`DEFAULT_DARK` on a dark paper, :data:`DEFAULT_LIGHT` otherwise.

    Notes
    -----
    Choosing by paper colour rather than hard-coding is the fix for a real
    defect: both previous highlighters used a dark palette unconditionally, and
    the editor's shipped ``paper_color`` is light, so several token colours were
    drawn at very low contrast.
    """
    try:
        import chisurf.core.settings

        paper = str(chisurf.core.settings.gui["editor"]["paper_color"])
    except Exception:
        return dict(DEFAULT_DARK)
    return dict(DEFAULT_DARK if _is_dark(paper) else DEFAULT_LIGHT)


class SyntaxHighlighter(QtGui.QSyntaxHighlighter):
    """Regex-rule syntax highlighter.

    Parameters
    ----------
    parent : QtGui.QTextDocument or QtCore.QObject, optional
    palette : mapping, optional
        Token name to ``#rrggbb``. Defaults to the editor's.
    font_family : str, optional
    font_point_size : float, optional
    """

    def __init__(
            self,
            parent=None,
            palette: typing.Mapping[str, str] | None = None,
            font_family: str | None = None,
            font_point_size: float | None = None,
    ) -> None:
        super().__init__(parent)
        self.highlighting_rules: list[tuple[QtCore.QRegularExpression, QtGui.QTextCharFormat, int]] = []
        self._rule_sources: list[tuple[str, str, int]] = []
        self.palette = dict(palette) if palette else palette_from_editor_settings()
        self.formats: dict[str, QtGui.QTextCharFormat] = {}
        self._build_formats()

        if font_family or font_point_size:
            self.default_font = QtGui.QFont(font_family or "", int(font_point_size or 10))
        else:
            self.default_font = QtGui.QFont()

    def _build_formats(self) -> None:
        """Create a :class:`QTextCharFormat` for every palette entry."""
        for token, colour in self.palette.items():
            fmt = QtGui.QTextCharFormat()
            fmt.setForeground(QtGui.QColor(colour))
            if token in ("keyword", "class"):
                fmt.setFontWeight(QtGui.QFont.Bold)
            if token == "comment":
                fmt.setFontItalic(True)
            self.formats[token] = fmt

    def set_palette(self, palette: typing.Mapping[str, str]) -> None:
        """Change the colours and re-highlight.

        Rules are rebuilt from their recorded sources rather than having their
        formats mutated in place, because a format object is shared by every
        rule that uses it and editing one would silently recolour the others.

        Parameters
        ----------
        palette : mapping
        """
        sources = list(self._rule_sources)
        self.palette = dict(palette)
        self._build_formats()
        self.highlighting_rules = []
        self._rule_sources = []
        for pattern, format_name, group in sources:
            self.add_rule(pattern, format_name, group=group)
        self.rehighlight()

    def add_rule(self, pattern: str, format_name: str, *, group: int = 0) -> None:
        """Register a rule.

        Parameters
        ----------
        pattern : str
            Regular expression.
        format_name : str
            Key into :attr:`formats`.
        group : int, optional
            Capture group to colour. ``0`` is the whole match; naming a group
            is what lets ``class Foo`` colour only ``Foo`` and leave the keyword
            to the keyword rule.
        """
        fmt = self.formats.get(format_name)
        if fmt is None:
            return
        expression = QtCore.QRegularExpression(pattern)
        self.highlighting_rules.append((expression, fmt, group))
        self._rule_sources.append((pattern, format_name, group))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt override
        """Apply the rules to one block.

        Parameters
        ----------
        text : str
        """
        for expression, fmt, group in self.highlighting_rules:
            iterator = expression.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart(group)
                length = match.capturedLength(group)
                if start >= 0 and length > 0:
                    self.setFormat(start, length, fmt)


class PythonHighlighter(SyntaxHighlighter):
    """Highlighter for Python source.

    Parameters
    ----------
    parent : QtGui.QTextDocument or QtCore.QObject, optional
    palette : mapping, optional
    font_family : str, optional
    font_point_size : float, optional
    """

    def __init__(
            self,
            parent=None,
            palette: typing.Mapping[str, str] | None = None,
            font_family: str | None = None,
            font_point_size: float | None = None,
            **_legacy,
    ) -> None:
        super().__init__(parent, palette, font_family, font_point_size)
        self._build_rules()
        self._triple_single = QtCore.QRegularExpression(r"'''")
        self._triple_double = QtCore.QRegularExpression(r'"""')

    def _build_rules(self) -> None:
        """Register the Python rules, in the order they should apply."""
        for word in keyword.kwlist:
            self.add_rule(rf"\b{word}\b", "keyword")
        for word in getattr(keyword, "softkwlist", ()):
            self.add_rule(rf"\b{word}\b", "keyword")

        self.add_rule(r"\b(self|cls)\b", "self")

        builtins_names = (
            "abs", "all", "any", "bool", "bytes", "callable", "dict", "dir",
            "enumerate", "filter", "float", "format", "frozenset", "getattr",
            "hasattr", "hash", "id", "int", "isinstance", "issubclass", "iter",
            "len", "list", "map", "max", "min", "next", "object", "open", "ord",
            "print", "range", "repr", "reversed", "round", "set", "setattr",
            "slice", "sorted", "str", "sum", "super", "tuple", "type", "zip",
        )
        for word in builtins_names:
            self.add_rule(rf"\b{word}\b(?=\s*\()", "builtin")

        # Group 1, not the whole match: colouring the whole match would paint
        # the ``class``/``def`` keyword too and override the keyword rule.
        self.add_rule(r"\bclass\s+(\w+)", "class", group=1)
        self.add_rule(r"\bdef\s+(\w+)", "function", group=1)

        self.add_rule(r"^\s*(@\w[\w.]*)", "decorator", group=1)
        self.add_rule(r"^\s*(%{1,2}\w+)", "magic", group=1)
        self.add_rule(r"^\s*(!)", "magic", group=1)

        self.add_rule(r"\b\d+\.?\d*(?:[eE][+-]?\d+)?[jJ]?\b", "number")
        self.add_rule(r"\b0[xXoObB][0-9a-fA-F_]+\b", "number")

        # Strings last, so a keyword inside a literal is overwritten by the
        # string colour rather than the other way round.
        self.add_rule(r'[bBrRuUfF]{0,2}"[^"\\]*(?:\\.[^"\\]*)*"', "string")
        self.add_rule(r"[bBrRuUfF]{0,2}'[^'\\]*(?:\\.[^'\\]*)*'", "string")

        self.add_rule(r"#[^\n]*", "comment")

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt override
        """Highlight one block, tracking multi-line strings.

        Parameters
        ----------
        text : str

        Notes
        -----
        Without the block-state tracking a docstring's contents are highlighted
        as code -- every ``if``, ``for`` and ``return`` in prose lights up as a
        keyword. Both highlighters this replaces had that defect.
        """
        state = self.previousBlockState()
        if state in (IN_STRING_SINGLE, IN_STRING_DOUBLE):
            delimiter = "'''" if state == IN_STRING_SINGLE else '"""'
            end = text.find(delimiter)
            if end == -1:
                self.setFormat(0, len(text), self.formats["string"])
                self.setCurrentBlockState(state)
                return
            stop = end + len(delimiter)
            self.setFormat(0, stop, self.formats["string"])
            self.setCurrentBlockState(NORMAL)
            self._highlight_rest(text, stop)
            return

        self.setCurrentBlockState(NORMAL)
        super().highlightBlock(text)
        self._open_triple(text, 0)

    def _highlight_rest(self, text: str, offset: int) -> None:
        """Apply the ordinary rules to *text* from *offset*.

        Parameters
        ----------
        text : str
        offset : int
        """
        tail = text[offset:]
        for expression, fmt, group in self.highlighting_rules:
            iterator = expression.globalMatch(tail)
            while iterator.hasNext():
                match = iterator.next()
                start = match.capturedStart(group)
                length = match.capturedLength(group)
                if start >= 0 and length > 0:
                    self.setFormat(offset + start, length, fmt)
        self._open_triple(text, offset)

    def _open_triple(self, text: str, offset: int) -> None:
        """Record an unterminated triple-quoted string opening in this block.

        Parameters
        ----------
        text : str
        offset : int
        """
        best_state = NORMAL
        best_index = -1
        for delimiter, state in (("'''", IN_STRING_SINGLE), ('"""', IN_STRING_DOUBLE)):
            index = text.find(delimiter, offset)
            while index != -1:
                closing = text.find(delimiter, index + 3)
                if closing == -1:
                    if best_index == -1 or index < best_index:
                        best_index, best_state = index, state
                    break
                index = text.find(delimiter, closing + 3)
        if best_index != -1:
            self.setFormat(best_index, len(text) - best_index, self.formats["string"])
            self.setCurrentBlockState(best_state)


class JSONHighlighter(SyntaxHighlighter):
    """Highlighter for JSON."""

    def __init__(self, parent=None, palette=None, font_family=None,
                 font_point_size=None, **_legacy) -> None:
        super().__init__(parent, palette, font_family, font_point_size)
        self.add_rule(r'"[^"\\]*(?:\\.[^"\\]*)*"\s*:', "keyword")
        self.add_rule(r'"[^"\\]*(?:\\.[^"\\]*)*"', "string")
        self.add_rule(r"\b-?\d+\.?\d*(?:[eE][+-]?\d+)?\b", "number")
        self.add_rule(r"\b(?:true|false|null)\b", "builtin")


class YAMLHighlighter(SyntaxHighlighter):
    """Highlighter for YAML."""

    def __init__(self, parent=None, palette=None, font_family=None,
                 font_point_size=None, **_legacy) -> None:
        super().__init__(parent, palette, font_family, font_point_size)
        self.add_rule(r"^\s*([\w.-]+)\s*:", "keyword", group=1)
        self.add_rule(r'"[^"\\]*(?:\\.[^"\\]*)*"', "string")
        self.add_rule(r"'[^'\\]*(?:\\.[^'\\]*)*'", "string")
        self.add_rule(r"\b-?\d+\.?\d*\b", "number")
        self.add_rule(r"\b(?:true|false|null|yes|no|on|off)\b", "builtin")
        self.add_rule(r"#[^\n]*", "comment")
