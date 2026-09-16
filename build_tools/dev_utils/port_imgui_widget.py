r"""Scaffold a chimol control from a Dear ImGui widget's C++ source.

Why a script and not a checklist
--------------------------------
Fourteen control families in :mod:`chimol.emtk` came out of
``junk/imgui``, and two more out of ``junk/ImGuiColorTextEdit`` and
``junk/imgui_club``. Doing them one after another makes the shape of the work
obvious: roughly a third of each port is **transcription of data** -- an
``enum class`` becomes an ``IntEnum``, an ``IM_COL32`` array becomes a tuple of
colour triples, an options ``struct`` becomes a dataclass, a
``static const char* const keywords[]`` becomes a ``frozenset`` -- and it is
the part where a mistake is silent. A keyword dropped from a 200-word list
colours one word wrong in one language and nothing fails.

The other two thirds are the algorithms, and those need reading and judgement;
no script writes them. So this does the third that is mechanical, exactly, and
hands over a module whose remaining work is *listed*: one ``TODO`` per public
method of the C++ class, in the order the source declares them.

Use
---
    python -m build_tools.dev_utils.port_imgui_widget \\
        junk/imgui_club/imgui_memory_editor/imgui_memory_editor.h \\
        --module memory_editor --class MemoryEditor \\
        --origin "junk/imgui_club -- Omar Cornut's mini memory editor, MIT"

    # look before writing
    python -m build_tools.dev_utils.port_imgui_widget <sources> --module x --print

It writes three files and prints what is left:

* ``chisurf/plugins/chimol/chimol/emtk/<module>.py`` -- the skeleton,
  with the extracted data filled in and the docstring's four required sections
  (where it comes from, the divergences, what is not ported, the contract)
  present but empty, because an empty heading is a prompt and a missing one is
  a thing nobody notices;
* ``chisurf/plugins/chimol/test/test_ui_<module>.py`` -- a construct-and-draw
  test against the recording painter, which is the test that catches a control
  that grew a toolkit dependency;
* a gallery row snippet for ``test/widget_gallery.py``.

It also adds the module to ``CONTROL_MODULES`` in the package ``__init__``, so
the lazy resolver, the documentation generator and the atlas guard all see it
-- three lists that would otherwise each be updated by hand and each be missed
a different time.

What it deliberately does not do
--------------------------------
Translate C++ statements. Every attempt at that produces Python that runs and
is wrong in a way that reads as intentional, which is worse than a stub. The
generated ``draw`` raises :class:`NotImplementedError` and says so.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

__all__ = [
    "extract_enums",
    "extract_palettes",
    "extract_options",
    "extract_word_lists",
    "extract_methods",
    "render_module",
    "render_test",
    "render_gallery_rows",
    "main",
]

#: Where the controls live, relative to the repository root.
UI_DIR = pathlib.Path("chisurf/plugins/chimol/chimol/emtk")

#: Where their tests live.
TEST_DIR = pathlib.Path("chisurf/plugins/chimol/test")

#: C++ spellings mapped to Python ones. ``ImU32`` is a packed colour in the
#: reference and a ``(r, g, b, a)`` tuple here, which is why it maps to the
#: chrome's ``Colour`` rather than to ``int``.
_TYPES = {
    "bool": ("bool", "False"),
    "float": ("float", "0.0"),
    "double": ("float", "0.0"),
    "int": ("int", "0"),
    "size_t": ("int", "0"),
    "unsigned": ("int", "0"),
    "ImU32": ("Colour", "(255, 255, 255, 255)"),
    "ImWchar": ("str", '""'),
    "std::string": ("str", '""'),
    "char": ("str", '""'),
}


def _snake(name: str) -> str:
    """Turn a C++ ``CamelCase`` or ``camelCase`` name into ``snake_case``."""
    body = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", body).lower()


# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------
def extract_enums(text: str) -> dict[str, list[str]]:
    """Return every ``enum``'s members, keyed by the enum's name.

    Parameters
    ----------
    text : str
        C++ source.

    Returns
    -------
    dict of str to list of str
        Member names in declaration order, which is what makes them safe to
        turn into an ``IntEnum``: the reference indexes palettes by these
        values, so the order *is* the meaning.

    Notes
    -----
    Members with an explicit ``= value`` keep only the name; a sentinel called
    ``count`` or ``COUNT`` is dropped, because Python's ``len()`` answers that
    and a member called ``count`` on an ``IntEnum`` shadows a real method.
    """
    found: dict[str, list[str]] = {}
    pattern = re.compile(
        r"enum(?:\s+class)?\s+(\w+)\s*(?::\s*\w+\s*)?\{(.*?)\}\s*;", re.S
    )
    for match in pattern.finditer(text):
        members = []
        for raw in match.group(2).split(","):
            body = re.sub(r"//.*", "", raw)
            body = re.sub(r"/\*.*?\*/", "", body, flags=re.S).strip()
            name = body.split("=")[0].strip()
            # The sentinel is spelled ``count`` in ImGuiColorTextEdit and
            # ``DataFormat_COUNT`` in imgui_club, so both spellings go: it is
            # not a value, and a member called ``count`` on an ``IntEnum``
            # shadows a real method.
            sentinel = name.lower() == "count" or name.lower().endswith("_count")
            if name and not sentinel and re.fullmatch(r"\w+", name):
                members.append(name)
        if members:
            found[match.group(1)] = members
    return found


def extract_palettes(text: str) -> list[tuple[str, list[tuple[tuple[int, ...], str]]]]:
    """Return every run of ``IM_COL32`` literals, with the comment on each line.

    Returns
    -------
    list of tuple
        ``(name, [((r, g, b, a), comment), ...])``. The name is the enclosing
        function's, which for the reference's palettes is ``GetDarkPalette`` and
        friends. The comments matter: they are what say which palette *slot*
        each colour is, and a colour list without them is unreviewable.
    """
    palettes: list[tuple[str, list[tuple[tuple[int, ...], str]]]] = []
    entry = re.compile(
        r"IM_COL32\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*,?\s*(?://\s*(.*))?"
    )
    for block in re.finditer(r"(\w+)\s*\([^)]*\)\s*\{(.*?)\n\}", text, re.S):
        colours = [
            ((int(m[1]), int(m[2]), int(m[3]), int(m[4])), (m[5] or "").strip())
            for m in entry.finditer(block.group(2))
        ]
        if len(colours) >= 3:
            palettes.append((block.group(1), colours))
    return palettes


def extract_options(text: str, struct: str = "Config") -> list[tuple[str, str, str]]:
    """Return an options struct's fields as ``(python_name, type, default)``.

    Parameters
    ----------
    text : str
        C++ source.
    struct : str, optional
        The struct's name. ``Config`` for ImGuiColorTextEdit; a widget that
        keeps its options as plain members instead (``imgui_club``'s memory
        editor does) yields nothing here and is transcribed by hand -- which
        the caller is told rather than left to discover from an empty
        dataclass.
    """
    match = re.search(rf"struct\s+{re.escape(struct)}\s*\{{(.*?)\n\s*\}}", text, re.S)
    if match is None:
        return []
    fields: list[tuple[str, str, str]] = []
    for line in match.group(1).splitlines():
        body = re.sub(r"//.*", "", line).strip().rstrip(";")
        if not body or body.startswith(("struct", "//", "#")):
            continue
        found = re.match(r"^(?:const\s+)?([\w:]+(?:\s*\*)?)\s+(\w+)\s*(?:=\s*(.+))?$", body)
        if found is None:
            continue
        c_type, name, default = found.group(1), found.group(2), found.group(3)
        py_type, py_default = _TYPES.get(c_type.replace(" ", ""), ("object", "None"))
        if default is not None:
            default = default.strip()
            if default in ("true", "false"):
                py_default = default.capitalize()
            elif re.fullmatch(r"-?\d+", default):
                py_default = default
            elif re.fullmatch(r"-?\d*\.\d+f?", default):
                py_default = default.rstrip("f")
            elif default.startswith('"'):
                py_default = default
        fields.append((_snake(name), py_type, py_default))
    return fields


def extract_word_lists(text: str) -> dict[str, list[str]]:
    """Return every ``static const char* const NAME[] = {...}`` as a word list.

    These are the keyword tables, and they are the single most error-prone
    thing to copy by hand: they are long, they are not alphabetical, and a
    missing entry has no symptom except one word that does not colour.

    Notes
    -----
    The array name alone is not a key: the reference declares eleven languages
    and every one of them has an array called ``keywords``, so keying by name
    merges C's keywords into Python's. The enclosing function is what
    distinguishes them, so the key is ``Function.array`` when a function can be
    found by scanning back from the declaration -- which is the difference
    between a usable extraction and one that has to be thrown away.
    """
    found: dict[str, list[str]] = {}
    pattern = re.compile(
        r"static\s+const\s+char\s*\*\s*const\s+(\w+)\s*\[\]\s*=\s*\{(.*?)\}\s*;", re.S
    )
    scope = re.compile(r"(\w+)\s*\(\s*\)\s*\{")
    for match in pattern.finditer(text):
        words = re.findall(r'"([^"]*)"', match.group(2))
        if not words:
            continue
        before = text[: match.start()]
        owner = scope.findall(before[-4000:])
        key = f"{owner[-1]}_{match.group(1)}" if owner else match.group(1)
        found.setdefault(key, []).extend(words)
    return found


def extract_methods(text: str, class_name: str) -> list[tuple[str, str]]:
    """Return the class's public API as ``(cpp_name, python_name)``.

    The reference's own convention is what makes this reliable: Dear ImGui and
    both ported widgets start every *public* member function with an uppercase
    letter and every private one with a lowercase letter, and say so in a
    comment. So the public API is exactly the uppercase-initial declarations,
    and no C++ parsing is needed to find it.

    Notes
    -----
    Only *declarations* count, so the scan stops at the ``protected``/``private``
    label that both references put between their public API and their internals,
    and skips any line carrying ``::`` -- an out-of-line definition in the
    ``.cpp`` is the same method again, and counting it inflates the checklist
    with duplicates until nobody reads it. On ImGuiColorTextEdit that is the
    difference between 253 entries and the ninety-odd the class really has.
    """
    for opener in (f"class {class_name}", f"struct {class_name}"):
        if opener in text:
            text = text.split(opener, 1)[1]
            break
    for closer in ("\nprotected:", "\nprivate:"):
        if closer in text:
            text = text.split(closer, 1)[0]
    seen: list[tuple[str, str]] = []
    pattern = re.compile(
        r"^\s*(?:inline\s+|static\s+|virtual\s+|constexpr\s+)*"
        r"[\w:<>&*,\s]+?\b([A-Z]\w+)\s*\([^;{]*\)\s*(?:const\s*)?[;{]",
        re.M,
    )
    for match in pattern.finditer(text):
        # Only the *return type and name* may not carry ``::`` -- the argument
        # list is full of ``std::string`` and testing the whole match drops
        # every method that takes one, which is most of them.
        head = match.group(0).split("(")[0]
        name = match.group(1)
        if "::" in head or name in (class_name, "IM_COL32") or name.startswith("Im"):
            continue
        python = _snake(name)
        if python not in {one[1] for one in seen}:
            seen.append((name, python))
    return seen


# --------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------
_MODULE_TEMPLATE = '''"""{title}

Where it comes from
-------------------
{origin}

TODO: name the file(s) read and what the widget is for.

Deliberate divergences
----------------------
TODO: every place this does *not* match the reference, and why. The C++ data
structures are usually the first entry -- a struct per element is the right
call in C++ and the wrong one in Python.

What is deliberately not ported
-------------------------------
TODO: the features left out, and what has no caller for them. A reader must be
able to tell "not ported" from "forgotten".

Everything draws through :class:`~chimol.emtk.painter.Painter`'s six
operations, holds its own state, and hit-tests with :func:`.style.hit`.
"""
from __future__ import annotations

from dataclasses import dataclass

from .control import Control
from .painter import ALIGN_LEFT, ALIGN_VCENTER, Colour, Painter
from .style import BORDER, FRAME_BG, TEXT, clamp, hit

__all__ = {exports}

{data}

class {cls}(Control):
    """TODO: one line saying what it is, then why it is not the obvious thing.

    Parameters
    ----------
    TODO
    """

    def __init__(self) -> None:
        self.config = {config_cls}()

    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the control.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box to draw in.
        """
        self.remember(x, y, w, h)
        raise NotImplementedError("port {cls}.draw from {source}")

{todos}
'''

_TEST_TEMPLATE = '''"""Painter-level tests for the ported {module} control.

No GUI toolkit: a control that quietly grows one fails here first, which is the
whole point of the painter seam.
"""
from __future__ import annotations

from chisurf.plugins.chimol.chimol.emtk import {module}
from chisurf.plugins.chimol.test.recording_painter import RecordingPainter


def test_it_draws_without_a_toolkit():
    """Constructing and drawing emits painter operations and nothing else."""
    control = {module}.{cls}()
    painter = RecordingPainter()
    control.draw(painter, 0.0, 0.0, 320.0, 120.0)
    assert painter.fills or painter.strokes or painter.strings


def test_it_remembers_where_it_was_drawn():
    """The box from the last draw is what a press hit-tests against."""
    control = {module}.{cls}()
    control.draw(RecordingPainter(), 10.0, 20.0, 100.0, 40.0)
    assert control.contains(50.0, 30.0)
    assert not control.contains(5.0, 30.0)
'''


def render_module(
    module: str,
    cls: str,
    origin: str,
    enums: dict[str, list[str]],
    palettes: list,
    options: list[tuple[str, str, str]],
    words: dict[str, list[str]],
    methods: list[tuple[str, str]],
    source: str,
) -> str:
    """Return the Python module text for a scaffolded port."""
    blocks: list[str] = []
    exports = [cls]

    for name, members in enums.items():
        exports.append(name)
        lines = [f"class {name}(IntEnum):", f'    """TODO: what {name} distinguishes."""', ""]
        lines += [f"    {_snake(one).upper()} = {index}" for index, one in enumerate(members)]
        blocks.append("\n".join(lines))

    for name, colours in palettes:
        constant = _snake(name).upper()
        exports.append(constant)
        lines = [
            f"#: The reference's ``{name}``, converted to the chrome's 0-255 int tuples.",
            f"{constant}: tuple[Colour, ...] = (",
        ]
        for (r, g, b, a), comment in colours:
            value = f"({r}, {g}, {b})" if a == 255 else f"({r}, {g}, {b}, {a})"
            lines.append(f"    {value},{'  # ' + comment if comment else ''}")
        lines.append(")")
        blocks.append("\n".join(lines))

    for name, entries in words.items():
        constant = _snake(name).upper()
        exports.append(constant)
        body = " ".join(entries)
        wrapped = []
        line = "    "
        for word in body.split():
            if len(line) + len(word) > 92:
                wrapped.append(line.rstrip())
                line = "    "
            line += word + " "
        wrapped.append(line.rstrip())
        joined = "\n".join(f'    "{one.strip()} "' for one in wrapped)
        blocks.append(
            f"#: The reference's ``{name}`` table, verbatim.\n"
            f"{constant} = frozenset(\n{joined}\n    .split()\n)"
        )

    config_cls = f"{cls}Config"
    if options:
        exports.append(config_cls)
        lines = ["@dataclass", f"class {config_cls}:",
                 '    """The reference\'s options struct, field for field."""', ""]
        lines += [f"    {name}: {kind} = {default}" for name, kind, default in options]
        blocks.append("\n".join(lines))
    else:
        blocks.append(
            "@dataclass\n"
            f"class {config_cls}:\n"
            '    """TODO: the widget keeps its options as plain members; list them here."""\n'
        )

    todos = "\n".join(
        f"    # TODO: port {cpp}() -> {python}()" for cpp, python in methods
    ) or "    # TODO: no public methods were detected; list them from the source."

    head = "from enum import IntEnum\n" if enums else ""
    text = _MODULE_TEMPLATE.format(
        title=f"{cls}: a port of {source}.",
        origin=origin,
        exports="[\n" + "".join(f'    "{one}",\n' for one in exports) + "]",
        data="\n\n\n".join(blocks) + "\n",
        cls=cls,
        config_cls=config_cls,
        todos=todos,
        source=source,
    )
    if head:
        text = text.replace("from dataclasses import dataclass",
                            "from dataclasses import dataclass\n" + head.rstrip())
    return text


def render_test(module: str, cls: str) -> str:
    """Return the pytest file text for a scaffolded port."""
    return _TEST_TEMPLATE.format(module=module, cls=cls)


def render_gallery_rows(module: str, cls: str) -> str:
    """Return the snippet to paste into ``test/widget_gallery.py``."""
    return (
        f"def _{module}_rows() -> list[tuple]:\n"
        f'    """The {module} family."""\n'
        f"    from chisurf.plugins.chimol.chimol.emtk import {module} as m\n\n"
        f"    return [\n"
        f'        ("{cls}", lambda: m.{cls}(), 120.0),\n'
        f"    ]\n\n"
        f'# and in _BUILDERS:  "{module}": _{module}_rows,\n'
    )


def _register(root: pathlib.Path, module: str) -> bool:
    """Add *module* to ``CONTROL_MODULES`` if it is not already there."""
    path = root / UI_DIR / "__init__.py"
    text = path.read_text()
    if f'"{module}"' in text:
        return False
    marker = '    "control",\n)'
    if marker not in text:
        marker = ")"
    path.write_text(text.replace(marker, f'    "{module}",\n{marker}', 1))
    return True


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Scaffold a port. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", type=pathlib.Path,
                        help="C++ header and/or implementation to mine")
    parser.add_argument("--module", required=True, help="Python module name, snake_case")
    parser.add_argument("--class", dest="cls", default="",
                        help="C++ class name; defaults to the module name in CamelCase")
    parser.add_argument("--struct", default="Config", help="Name of the options struct")
    parser.add_argument("--origin", default="TODO: the checkout, the author, the licence")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--print", dest="show", action="store_true",
                        help="write nothing; print what would be generated")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args(argv)

    text = "\n".join(one.read_text(errors="replace") for one in args.sources)
    cls = args.cls or "".join(part.capitalize() for part in args.module.split("_"))

    enums = extract_enums(text)
    palettes = extract_palettes(text)
    options = extract_options(text, args.struct)
    words = extract_word_lists(text)
    methods = extract_methods(text, cls)

    print(
        f"mined {sum(one.stat().st_size for one in args.sources) // 1024} kB: "
        f"{len(enums)} enums, {len(palettes)} palettes, {len(options)} options, "
        f"{len(words)} word lists ({sum(len(v) for v in words.values())} words), "
        f"{len(methods)} public methods"
    )

    module_text = render_module(
        args.module, cls, args.origin, enums, palettes, options, words, methods,
        source=", ".join(str(one) for one in args.sources),
    )
    test_text = render_test(args.module, cls)
    gallery = render_gallery_rows(args.module, cls)

    if args.show:
        print(module_text)
        print("---- test ----")
        print(test_text)
        print("---- gallery ----")
        print(gallery)
        return 0

    module_path = args.root / UI_DIR / f"{args.module}.py"
    test_path = args.root / TEST_DIR / f"test_ui_{args.module}.py"
    for path, body in ((module_path, module_text), (test_path, test_text)):
        if path.exists() and not args.force:
            print(f"refusing to overwrite {path} (use --force)", file=sys.stderr)
            return 1
        path.write_text(body)
        print(f"wrote {path}")
    if _register(args.root, args.module):
        print(f"registered {args.module!r} in CONTROL_MODULES")

    print("\npaste into test/widget_gallery.py:\n")
    print(gallery)
    print("still to do, in source order:")
    for cpp, python in methods:
        print(f"  {cpp}() -> {python}()")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
