"""Tests for the ImGui-widget port scaffolder.

The scaffolder's value is that the *data* half of a port stops being typed by
hand -- so what has to be true is that its extractors read real C++ correctly
and that what it emits is valid Python. Both are checked here against small
literal snippets, and, when the checkouts are present, against the two real
sources chimol was ported from.
"""
from __future__ import annotations

import pathlib

import pytest

from build_tools.dev_utils import port_imgui_widget as tool

#: The reference checkouts. ``junk/`` is gitignored and re-clonable, so tests
#: that read it skip rather than fail when it is absent.
JUNK = pathlib.Path(__file__).resolve().parents[1] / "junk"
TEXT_EDIT = JUNK / "ImGuiColorTextEdit"
CLUB = JUNK / "imgui_club" / "imgui_memory_editor" / "imgui_memory_editor.h"


# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------
def test_an_enum_class_becomes_ordered_members_without_its_count_sentinel():
    """The order *is* the meaning: the reference indexes palettes by it.

    ``count`` is dropped because Python's ``len()`` answers it and a member
    called ``count`` on an ``IntEnum`` shadows a real method.
    """
    found = tool.extract_enums(
        "enum class Color : char {\n"
        "    text,\n"
        "    keyword, // a comment\n"
        "    number = 7,\n"
        "    count\n"
        "};"
    )
    assert found == {"Color": ["text", "keyword", "number"]}


def test_a_palette_keeps_the_comment_that_says_which_slot_each_colour_is():
    """A colour list without its comments is unreviewable."""
    found = tool.extract_palettes(
        "const Palette& GetDarkPalette() {\n"
        "    static Palette p = {{\n"
        "        IM_COL32(224, 224, 224, 255), // text\n"
        "        IM_COL32(197, 134, 192, 255), // keyword\n"
        "        IM_COL32( 90, 179, 155, 255), // declaration\n"
        "    }};\n"
        "}"
    )
    assert len(found) == 1
    name, colours = found[0]
    assert name == "GetDarkPalette"
    assert colours[1] == ((197, 134, 192, 255), "keyword")


def test_an_options_struct_becomes_typed_python_defaults():
    """bool/float/size_t and their C++ literals, mapped to Python ones."""
    found = tool.extract_options(
        "struct Config {\n"
        "    size_t tabSize = 4;\n"
        "    bool insertSpacesOnTabs = false;\n"
        "    float lineSpacing = 1.5f;\n"
        "    const Language* language = nullptr;\n"
        "}"
    )
    assert ("tab_size", "int", "4") in found
    assert ("insert_spaces_on_tabs", "bool", "False") in found
    assert ("line_spacing", "float", "1.5") in found


def test_word_lists_are_keyed_by_the_function_that_declares_them():
    """Eleven languages each have an array called ``keywords``.

    Keying by array name alone merges C's keywords into Python's -- silently,
    and the symptom is that ``goto`` colours as a keyword in a Python file.
    """
    found = tool.extract_word_lists(
        'const Language* Language::C() {\n'
        '    static const char* const keywords[] = { "break", "case" };\n'
        '}\n'
        'const Language* Language::Python() {\n'
        '    static const char* const keywords[] = { "def", "lambda" };\n'
        '}\n'
    )
    assert found["C_keywords"] == ["break", "case"]
    assert found["Python_keywords"] == ["def", "lambda"]


def test_only_public_declarations_count_as_methods():
    """Both references start public members with a capital and say so.

    The scan stops at ``protected:``/``private:`` and ignores out-of-line
    definitions, or the checklist fills with duplicates until nobody reads it.
    """
    found = tool.extract_methods(
        "class Widget {\n"
        "public:\n"
        "    void SetText(const std::string& t);\n"
        "    inline bool IsEmpty() const { return true; }\n"
        "protected:\n"
        "    void NotPublic();\n"
        "};\n"
        "void Widget::SetText(const std::string& t) {}\n",
        "Widget",
    )
    assert found == [("SetText", "set_text"), ("IsEmpty", "is_empty")]


# --------------------------------------------------------------------------
# Emitters
# --------------------------------------------------------------------------
def _compilable(text: str) -> str:
    """Strip the relative imports so a generated module can be compiled alone."""
    return (
        text.replace("from .control import Control", "Control = object")
        .replace("from .painter import", "# ")
        .replace("from .style import", "# ")
    )


def test_the_generated_module_is_valid_python():
    """A skeleton that does not import is worse than no skeleton."""
    text = tool.render_module(
        "demo",
        "Demo",
        "origin",
        {"Mode": ["one", "two"]},
        [("GetDarkPalette", [((1, 2, 3, 255), "text")] * 3)],
        [("tab_size", "int", "4")],
        {"C_keywords": ["break", "case"]},
        [("SetText", "set_text")],
        "source.h",
    )
    compile(_compilable(text), "generated", "exec")
    assert "# TODO: port SetText() -> set_text()" in text
    assert "class Demo(Control):" in text


def test_the_generated_module_carries_the_four_required_headings():
    """An empty heading is a prompt; a missing one is never noticed."""
    text = tool.render_module("demo", "Demo", "origin", {}, [], [], {}, [], "s.h")
    for heading in (
        "Where it comes from",
        "Deliberate divergences",
        "What is deliberately not ported",
    ):
        assert heading in text


def test_the_generated_test_imports_the_shared_recording_painter():
    """Ten copied painters is how the metrics quietly stopped agreeing."""
    text = tool.render_test("demo", "Demo")
    assert "from chisurf.plugins.chimol.test.recording_painter import RecordingPainter" in text
    compile(text, "generated_test", "exec")


def test_registering_a_module_is_idempotent(tmp_path):
    """Running the scaffolder twice must not list a module twice."""
    ui = tmp_path / tool.UI_DIR
    ui.mkdir(parents=True)
    (ui / "__init__.py").write_text('CONTROL_MODULES = (\n    "widgets",\n    "control",\n)\n')
    assert tool._register(tmp_path, "demo")
    assert not tool._register(tmp_path, "demo")
    assert (ui / "__init__.py").read_text().count('"demo"') == 1


# --------------------------------------------------------------------------
# Against the real sources
# --------------------------------------------------------------------------
@pytest.mark.skipif(not TEXT_EDIT.is_dir(), reason="reference checkout absent")
def test_the_real_text_editor_source_yields_the_tables_chimol_ships():
    """The port's own word tables came out of this path; it must still work."""
    source = (TEXT_EDIT / "TextEditor.cpp").read_text(errors="replace")
    words = tool.extract_word_lists(source)
    assert len(words["Python_keywords"]) == 35
    assert "def" in words["Python_keywords"]
    assert len(tool.extract_palettes(source)) == 2


@pytest.mark.skipif(not CLUB.is_file(), reason="reference checkout absent")
def test_the_real_memory_editor_source_reports_no_options_struct():
    """It keeps its options as plain members, and the tool must say so.

    Silently emitting an empty dataclass would read as "this widget has no
    options", which is the opposite of true -- it has fourteen.
    """
    source = CLUB.read_text(errors="replace")
    assert tool.extract_options(source, "Config") == []
    assert tool.extract_enums(source)["DataFormat"] == ["DataFormat_Bin",
                                                        "DataFormat_Dec",
                                                        "DataFormat_Hex"]
    text = tool.render_module(
        "memory_demo", "MemoryDemo", "o", {}, [], [], {}, [], str(CLUB)
    )
    assert "the widget keeps its options as plain members" in text
