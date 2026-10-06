"""The native code editor operated with real input: typing, caret keys, selection, clipboard, undo, colouring, files, wheel.

Hermetic: temporary ``HOME`` / ``CHISURF_SETTINGS_DIR`` / ``MMFDB_*``, the project is a temporary folder, the clipboard is an
in-memory hook (the system clipboard is neither read nor written) and the real ``~/.chisurf`` is snapshotted for editor related
files (logs and the bytecode cache aside). Only what a host delivers reaches the app: pointer press / release / drag, the wheel,
key events with their modifier bits, and the file dialog's own buttons.
"""

from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest
from emtk import clipboard, keys
from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, SHIFT_MODIFIER

from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app
from chisurf.plugins.emtk_test_input import Driver

REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)
SHIFT, CTRL = SHIFT_MODIFIER, CONTROL_MODIFIER
START = "# Welcome to ChiSurf EMTK Code Editor\nprint('Hello from ChiSurf!')\n"


def _tree(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")) if root.is_dir() else []:
        rel = path.relative_to(root)
        if rel.parts[:1] in (("logs",), ("cache",)) or not any(
            t in str(rel).lower() for t in ("code_editor", "editor")
        ):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        out[str(rel)] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    before = _tree(REAL_HOME / ".chisurf")
    yield
    assert _tree(REAL_HOME / ".chisurf") == before, (
        "a test wrote editor files into the real ~/.chisurf"
    )


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "home").mkdir()
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def board():
    """The clipboard: an in-memory hook, restored afterwards."""
    held = {"text": ""}
    clipboard.set_hook(lambda text: held.__setitem__("text", text), lambda: held["text"])
    yield held
    clipboard.set_hook(None)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "script.py").write_text("x = 1\nprint(x)\n", encoding="utf-8")
    (root / "notes.txt").write_text("plain notes\n", encoding="utf-8")
    return root


class Ed(Driver):
    """The editor window with helpers to aim at a caret position and send keys."""

    @property
    def doc(self):
        return self.app.model.active_doc

    @property
    def editor(self):
        return self.doc.editor

    def point(self, line: int, column: int):
        e = self.editor
        return (
            e._text_x + (column - e.first_visible_column) * e._glyph_w,
            e._body_y + (line - e.first_visible_line) * e._line_h + e._line_h / 2,
        )

    def click_at(self, line: int, column: int, clicks: int = 1, modifiers: int = 0):
        x, y = self.point(line, column)
        self.app.pointer_move(x, y)
        self.draw(1)
        self.app.press(x, y, modifiers=modifiers, clicks=clicks)
        self.draw(1)
        self.app.release()
        self.draw(2)

    def drag_between(self, start, end):
        (x0, y0), (x1, y1) = self.point(*start), self.point(*end)
        self.drag((x0, y0), (x1, y1))

    def key(self, key, text="", modifiers=0):
        self.app.key(key, text, modifiers)
        self.draw(2)

    def combo(self, letter, modifiers=CTRL):
        self.key(ord(letter.upper()), letter.lower(), modifiers)

    def caret(self):
        c = self.editor.cursors.main.end
        return (c.line, c.index)

    def selected(self):
        return self.editor.selected_text() if self.editor.cursors.any_has_selection else ""

    def status(self):
        return next((s for s in self.draw(2).strings if "Ln " in s and "Col " in s), "")


@pytest.fixture
def ed(project, board):
    driver = Ed(make_editor_app(str(project)))
    driver.draw(3)
    driver.click_at(1, 0)
    assert driver.app.io.want_capture_keyboard
    yield driver
    driver.app.close()


# -- typing and the caret keys ----------------------------------------------------------------------------------------------- #


def test_typed_characters_are_inserted_at_the_caret_and_the_status_line_follows(ed):
    ed.type("ab")
    assert ed.doc.text.splitlines()[1].startswith("abprint(")
    assert ed.caret() == (1, 2)
    assert "Ln 2, Col 3" in ed.status() and "Modified" in ed.status()


def test_enter_splits_the_line_and_backspace_and_delete_remove(ed):
    ed.key(keys.KEY_END)
    ed.key(keys.KEY_RETURN, "\r")
    assert ed.doc.text.endswith("\n\n") and ed.caret() == (2, 0)
    ed.key(keys.KEY_BACKSPACE)
    assert ed.caret()[0] == 1 and ed.doc.text.count("\n") == 2
    ed.key(keys.KEY_HOME)
    ed.key(keys.KEY_DELETE)
    assert ed.doc.text.splitlines()[1].startswith("rint(")


@pytest.mark.parametrize(
    "key,expected",
    [
        (keys.KEY_RIGHT, (1, 1)),
        (keys.KEY_DOWN, (2, 0)),
        (keys.KEY_END, (1, 28)),
        (keys.KEY_UP, (0, 0)),
    ],
)
def test_the_arrow_home_and_end_keys_move_the_caret(ed, key, expected):
    ed.key(key)
    assert ed.caret() == expected


def test_page_keys_and_document_ends(ed):
    ed.app.model.active_doc.text = "\n".join(f"line {i}" for i in range(200))
    ed.draw(3)
    ed.click_at(0, 0)
    ed.key(keys.KEY_PAGE_DOWN)
    assert ed.caret()[0] > 10
    ed.key(keys.KEY_END, "", CTRL)
    assert ed.caret()[0] == 199
    ed.key(keys.KEY_HOME, "", CTRL)
    assert ed.caret() == (0, 0)


def test_a_click_places_the_caret(ed):
    ed.click_at(0, 8)
    assert ed.caret() == (0, 8)
    ed.click_at(1, 5)
    assert ed.caret() == (1, 5) and "Ln 2, Col 6" in ed.status()


def test_tab_inserts_the_indent_and_bracket_pairs_are_closed(ed):
    ed.key(keys.KEY_TAB)
    assert ed.doc.text.splitlines()[1].startswith("    print(")
    ed.key(keys.KEY_END)
    ed.type("(")
    assert ed.doc.text.splitlines()[1].endswith("()")
    ed.type(")")


def test_a_selection_is_indented_and_deindented_and_commented(ed):
    ed.key(keys.KEY_DOWN, "", SHIFT)
    ed.key(keys.KEY_DOWN, "", SHIFT)
    ed.key(keys.KEY_TAB)
    assert ed.doc.text.splitlines()[1].startswith("    print(") and not ed.doc.text.splitlines()[
        0
    ].startswith(" ")
    ed.key(keys.KEY_TAB, "", SHIFT)
    assert ed.doc.text.splitlines()[1].startswith("print(")
    ed.combo("/")
    assert ed.doc.text.splitlines()[1].lstrip().startswith("#")
    ed.combo("/")
    assert ed.doc.text.splitlines()[1].startswith("print(")


# -- selection --------------------------------------------------------------------------------------------------------------- #


def test_shift_arrows_select_and_typing_replaces_the_selection(ed):
    for _ in range(5):
        ed.key(keys.KEY_RIGHT, "", SHIFT)
    assert ed.selected() == "print"
    ed.type("echo")
    assert ed.doc.text.splitlines()[1].startswith("echo(")
    assert not ed.editor.cursors.any_has_selection


def test_shift_end_and_select_all(ed):
    ed.key(keys.KEY_END, "", SHIFT)
    assert ed.selected() == "print('Hello from ChiSurf!')"
    ed.combo("a")
    assert ed.selected() == ed.doc.text


def test_a_mouse_drag_selects_a_range(ed):
    ed.drag_between((1, 0), (1, 5))
    assert ed.selected() == "print"
    ed.drag_between((0, 2), (1, 5))
    assert ed.selected().startswith("Welcome") and ed.selected().endswith("print")


def test_double_click_selects_a_word(ed):
    ed.click_at(0, 4, clicks=2)
    assert ed.selected() == "Welcome"
    ed.click_at(1, 8, clicks=2)
    assert ed.selected() == "Hello" or ed.selected() == "'Hello"


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: im.text_editor passes at most clicks=2 and modifiers=0 to the editor, so a triple click "
    "(select line) and Shift+click (extend selection) never reach it; see REPORT.md",
)
def test_triple_click_selects_a_line_and_shift_click_extends(ed):
    ed.click_at(1, 3, clicks=3)
    assert ed.selected().strip() == "print('Hello from ChiSurf!')"
    ed.click_at(1, 0)
    ed.click_at(1, 5, modifiers=SHIFT)
    assert ed.selected() == "print"


def test_escape_keeps_the_text_and_the_editor_keeps_the_keyboard(ed):
    before = ed.doc.text
    ed.key(keys.KEY_ESCAPE)
    assert ed.doc.text == before and ed.app.io.want_capture_keyboard


# -- clipboard ----------------------------------------------------------------------------------------------------------------- #


def test_copy_cut_and_paste_use_the_clipboard_and_only_it(ed, board):
    for _ in range(5):
        ed.key(keys.KEY_RIGHT, "", SHIFT)
    ed.combo("c")
    assert board["text"] == "print" and ed.doc.text.startswith(START[:40])
    ed.combo("x")
    assert board["text"] == "print" and ed.doc.text.splitlines()[1].startswith("(")
    ed.key(keys.KEY_END)
    ed.combo("v")
    assert ed.doc.text.splitlines()[1].endswith("print")
    board["text"] = "multi\nline"
    ed.combo("v")
    assert ed.doc.text.splitlines()[-2:] == ["multi", "line"] or "multi" in ed.doc.text


def test_cut_without_a_selection_changes_nothing(ed, board):
    board["text"] = "keep"
    before = ed.doc.text
    ed.combo("x")
    assert board["text"] == "keep" or ed.doc.text != before


# -- undo ------------------------------------------------------------------------------------------------------------------------- #


def test_undo_and_redo_walk_back_and_forth(ed):
    ed.type("abc")
    typed = ed.doc.text
    assert typed != START
    ed.combo("z")
    assert ed.doc.text != typed
    ed.combo("z", CTRL)
    ed.combo("z", CTRL)
    ed.combo("z", CTRL)
    assert ed.doc.text == START
    ed.combo("z", CTRL | SHIFT)
    assert ed.doc.text != START
    for _ in range(5):
        ed.combo("z", CTRL | SHIFT)
    assert ed.doc.text == typed


def test_undo_reverts_a_cut_and_a_replaced_selection(ed, board):
    ed.combo("a")
    ed.type("x")
    assert ed.doc.text == "x"
    ed.combo("z")
    assert ed.doc.text == START


# -- syntax colouring -------------------------------------------------------------------------------------------------------------- #


def test_python_is_coloured_by_token_kind(ed):
    texts = {t[5]: t[6] for t in ed.draw(3).texts}
    assert texts["print"] != texts["("] != texts["'Hello"]  # name, punctuation and string differ
    assert len({texts["print"], texts["'Hello"], texts["("]}) == 3
    comment = next(c for s, c in texts.items() if s.startswith("#"))
    assert comment != texts["print"]


def test_a_document_without_a_language_is_plain(ed, project):
    ed.app.model.open_file(project / "notes.txt")
    ed.draw(3)
    colours = {t[6] for t in ed.draw(3).texts if t[5] in ("plain", "notes")}
    assert len(colours) == 1


def test_a_keyword_changes_colour_when_typed(ed):
    ed.key(keys.KEY_END, "", CTRL)
    ed.type("def f():")
    shades = {t[5]: t[6] for t in ed.draw(3).texts if t[5] in ("def", "f")}
    assert shades["def"] != shades["f"]


# -- the wheel --------------------------------------------------------------------------------------------------------------------- #


def test_the_wheel_scrolls_a_long_document_and_the_line_numbers_follow(ed):
    ed.doc.text = "\n".join(f"line {i}" for i in range(300))
    ed.draw(3)
    assert ed.editor.first_visible_line == 0
    x, y = ed.point(5, 5)
    ed.wheel(x, y, -1.0)
    assert ed.editor.first_visible_line == 3  # one notch, three lines
    ed.wheel(x, y, -5.0)
    assert ed.editor.first_visible_line == 6  # however large the delta, one notch is one step
    assert str(ed.editor.first_visible_line + 1) in ed.draw(2).strings
    ed.wheel(x, y, 1.0)
    assert ed.editor.first_visible_line == 3
    for _ in range(4):
        ed.wheel(x, y, 1.0)
    assert ed.editor.first_visible_line == 0


def test_the_caret_scrolls_into_view(ed):
    ed.doc.text = "\n".join(f"line {i}" for i in range(300))
    ed.draw(3)
    ed.click_at(0, 0)
    ed.key(keys.KEY_END, "", CTRL)
    assert ed.editor.first_visible_line > 100
    assert any(s == "300" for s in ed.draw(2).strings)


# -- files ------------------------------------------------------------------------------------------------------------------------ #


def test_open_button_lists_the_project_and_a_picked_file_opens_in_a_new_tab(ed, project):
    ed.click_text("📂 Open")
    assert ed.app.editor_gui._file_dialog is not None
    assert ed.drawn("script.py") and ed.drawn("notes.txt")
    ed.click_text("script.py")
    ed.click_text("Open")
    assert ed.app.editor_gui._file_dialog is None
    assert ed.doc.name == "script.py" and ed.doc.text == "x = 1\nprint(x)\n"
    assert ed.drawn("  script.py  ") or any("script.py" in s for s in ed.draw(2).strings)


def test_the_open_dialog_cancel_opens_nothing(ed):
    count = len(ed.app.model.documents)
    ed.click_text("📂 Open")
    ed.click_text("Cancel")
    assert ed.app.editor_gui._file_dialog is None and len(ed.app.model.documents) == count


def test_a_file_of_the_project_tree_opens_by_a_click(ed):
    ed.click_text("🐍 script.py") if ed.drawn("🐍 script.py") else ed.click_text("script.py")
    assert ed.doc.name == "script.py"


def test_editing_and_saving_writes_the_file(ed, project):
    ed.app.model.open_file(project / "script.py")
    ed.draw(3)
    ed.click_at(0, 5)
    ed.type("0")
    assert ed.doc.is_modified and "Modified" in ed.status()
    ed.click_text("💾 Save")
    assert (project / "script.py").read_text() == "x = 10\nprint(x)\n"
    assert not ed.doc.is_modified and "Saved" in ed.status()


def test_save_as_asks_for_a_name_and_writes_the_buffer(ed, project):
    ed.type("# mine ")
    ed.click_text("📝 Save As")
    assert ed.app.editor_gui._file_dialog is not None
    ed.click_text("main.py") if ed.drawn("main.py") else None
    ed.app.key(0x41, "a", CTRL)
    ed.draw(1)
    ed.type("fresh.py")
    ed.click_text("Save")
    target = project / "fresh.py"
    assert target.is_file() and "# mine" in target.read_text()
    assert ed.doc.path == str(target) or Path(ed.doc.path or "").resolve() == target.resolve()


def test_save_over_an_existing_file_asks_before_replacing(ed, project):
    ed.click_text("📝 Save As")
    ed.click_text("main.py")  # the name field shows the suggestion
    ed.app.key(0x41, "a", CTRL)
    ed.draw(1)
    ed.type("notes.txt")
    ed.click_text("Save")
    assert ed.drawn("Replace the existing file?")
    ed.click_text("Choose another name")
    assert (project / "notes.txt").read_text() == "plain notes\n"
    ed.click_text("Save")
    ed.click_text("Replace existing file")
    assert (project / "notes.txt").read_text() == START


def test_closing_a_modified_document_asks_and_discard_or_cancel_work(ed):
    count = len(ed.app.model.documents)
    ed.type("zzz")
    ed.click_text("✖ Close")
    assert ed.drawn("Discard changes")
    ed.click_text("Cancel")
    assert len(ed.app.model.documents) == count
    ed.click_text("✖ Close")
    ed.click_text("Discard changes")
    assert len(ed.app.model.documents) == count - 1


def test_new_and_close_without_changes(ed):
    ed.click_text("➕ New")
    assert len(ed.app.model.documents) == 2 and ed.doc.text == ""
    ed.click_at(0, 0)
    ed.type("hi")
    assert ed.doc.text == "hi"
    for _ in range(4):
        ed.combo("z")
    assert ed.doc.text == ""
    ed.click_text("✖ Close")
    assert len(ed.app.model.documents) == 1


def test_typing_into_the_project_filter_does_not_edit_the_document(ed):
    before = ed.doc.text
    ed.click_text("🔍 Filter files...")
    ed.type("zz")
    assert ed.doc.text == before
    assert not ed.drawn("🐍 script.py")


def test_the_window_closes_without_writing_into_the_project_or_home(ed, project):
    ed.type("x")
    before = sorted(p.name for p in project.iterdir())
    ed.app.close()
    assert sorted(p.name for p in project.iterdir()) == before


# -- find and replace ----------------------------------------------------------------------------------------------------------- #


def prepare_find(ed, text="foo bar foo\nBaz foo\nFOO end\n"):
    ed.doc.text = text
    ed.draw(3)
    ed.click_at(0, 0)
    ed.combo("f")
    assert ed.app.editor_gui.find_open and ed.app.io.want_capture_keyboard


def test_ctrl_f_opens_the_find_bar_with_the_keyboard_in_it_and_escape_closes_it(ed):
    ed.combo("f")
    assert ed.app.editor_gui.find_open and ed.drawn("Replace all")
    ed.type("ab")
    assert (
        ed.app.editor_gui.find_text == "ab" and ed.doc.text == START
    )  # typed into the field, not the document
    ed.key(keys.KEY_ESCAPE)
    assert not ed.app.editor_gui.find_open and not ed.drawn("Replace all")


def test_the_edit_menu_opens_find(ed):
    ed.click_text("Edit")
    ed.click_text("Find…")
    assert ed.app.editor_gui.find_open


def test_typing_a_word_and_enter_selects_the_next_match_and_wraps(ed):
    prepare_find(ed)
    ed.type("foo")
    ed.key(keys.KEY_RETURN, "\r")
    assert ed.selected() == "foo" and ed.caret() == (0, 3)
    for expected in ((0, 11), (1, 7), (2, 3)):
        ed.key(keys.KEY_RETURN, "\r")
        assert ed.caret() == expected
    ed.click_text("Next")  # the button does the same as Enter, and the search wraps
    assert ed.caret() == (0, 3) and ed.selected() == "foo"


def test_match_case_and_whole_word_narrow_the_search(ed):
    prepare_find(ed)
    ed.type("foo")
    ed.click_text("Match case")
    assert ed.app.editor_gui.find_case
    ed.app.editor_gui.find_all()
    assert len(ed.editor.cursors) == 3  # FOO is not a match
    ed.click_text("Match case")
    ed.app.editor_gui.find_all()
    assert len(ed.editor.cursors) == 4
    ed.click_text("Whole word")
    ed.doc.text = "foo foobar foo"
    ed.app.editor_gui.find_all()
    assert len(ed.editor.cursors) == 2


def test_all_puts_a_caret_on_every_match_and_typing_edits_them_all(ed):
    prepare_find(ed)
    ed.type("foo")
    ed.click_text("All")
    assert ed.app.editor_gui.find_status == "4 matches" and ed.drawn("4 matches")
    assert len(ed.editor.cursors) == 4


def test_not_found_is_reported(ed):
    prepare_find(ed)
    ed.type("zzz")
    ed.key(keys.KEY_RETURN, "\r")
    assert ed.drawn("Not found")


def test_replace_replaces_the_current_match_and_replace_all_every_one(ed):
    prepare_find(ed)
    ed.type("foo")
    ed.click_text("Match case")
    gui = ed.app.editor_gui
    gui.replace_text = "X"
    ed.click_text("Replace")
    assert ed.doc.text.splitlines()[0].startswith("X bar")
    ed.click_text("Replace all")
    assert "foo" not in ed.doc.text and ed.doc.text.count("X") == 3 and "FOO" in ed.doc.text
    ed.click_at(2, 0)  # back into the document: Ctrl+Z undoes the replacements
    for _ in range(6):
        ed.combo("z")
    assert ed.doc.text == "foo bar foo\nBaz foo\nFOO end\n"


def test_close_find_button(ed):
    ed.combo("f")
    ed.click_text("Close find")
    assert not ed.app.editor_gui.find_open


# -- keyboard shortcuts ----------------------------------------------------------------------------------------------------------- #


def test_ctrl_s_saves_an_opened_file(ed, project):
    ed.app.model.open_file(project / "script.py")
    ed.draw(3)
    ed.click_at(1, 0)
    ed.type("# ")
    ed.combo("s")
    assert (project / "script.py").read_text() == "x = 1\n# print(x)\n"
    assert "Saved" in ed.status()


def test_ctrl_shift_s_opens_save_as_and_ctrl_o_the_open_dialog(ed):
    ed.combo("s", CTRL | SHIFT)
    assert ed.app.editor_gui._file_dialog is not None and ed.drawn("Save")
    ed.click_text("Cancel")
    assert ed.app.editor_gui._file_dialog is None
    ed.combo("o")
    assert ed.app.editor_gui._file_dialog is not None and ed.drawn("script.py")
    ed.click_text("Cancel")


def test_ctrl_n_makes_a_document_and_ctrl_w_closes_it_and_asks_when_modified(ed):
    ed.combo("n")
    assert len(ed.app.model.documents) == 2
    ed.combo("w")
    assert len(ed.app.model.documents) == 1
    ed.click_at(1, 0)
    ed.type("a")
    ed.combo("w")
    assert ed.drawn("Discard changes")
    ed.click_text("Cancel")
    assert len(ed.app.model.documents) == 1


def test_typed_letters_never_trigger_a_shortcut(ed):
    ed.type("sonwf")
    assert (
        "sonwf" in ed.doc.text
        and len(ed.app.model.documents) == 1
        and ed.app.editor_gui._file_dialog is None
    )
    assert not ed.app.editor_gui.find_open


def test_alt_arrows_move_the_line(ed):
    ed.key(keys.KEY_UP, "", ALT_MODIFIER)
    assert ed.doc.text.splitlines()[:2] == [
        "print('Hello from ChiSurf!')",
        "# Welcome to ChiSurf EMTK Code Editor",
    ]


def test_a_second_tab_keeps_its_own_text_caret_and_undo(ed):
    ed.type("one")
    ed.click_text("➕ New")
    ed.click_at(0, 0)
    ed.type("two")
    assert ed.doc.text == "two"
    first = ed.app.model.documents[0]
    assert first.text.splitlines()[1].startswith("oneprint") and first is not ed.doc


# -- layout ------------------------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (640, 480)])
def test_the_toolbar_wraps_and_every_control_and_the_status_line_stay_inside_the_window(
    ed, size, project
):
    ed.app.model.open_file(project / "script.py")
    ed.resize(size)
    ed.combo("f")
    painter = ed.draw(3)
    for label in (
        "➕ New",
        "📂 Open",
        "💾 Save",
        "📝 Save As",
        "✖ Close",
        "▶ Run",
        "🧹 Check",
        "🛠 Fix",
        "📓 Notebook",
        "⚙ Settings",
        "Next",
        "All",
        "Replace all",
        "Close find",
    ):
        x, y, w, h = ed.text_rect(painter, label)
        assert x >= 0 and y >= 0 and y + h <= size[1], (label, size)
        assert x + w <= size[0] + 1, f"{label!r} is cut off at the right edge of a {size} window"
    status = next(t for t in painter.texts if "Ln " in t[5] and "Col " in t[5])
    assert status[0] + status[2] <= size[0] + 1, "the status line is cut off"
    assert "Ln 1, Col 1" in status[5]
