"""Real-input driving of the trajectory tools' emtk apps, shared by the family's click tests.

Nothing here calls a model or app method to "click": a :class:`Ui` presses and releases the pointer at the
rectangle a control was drawn in (``app.item_rects``) or at the text a button drew, types with ``key``, drops files
through ``on_files_dropped`` (the host entry point) and reads the *visible* outcome (the strings of the frame, the model
fields the window edits, the files written). The family's apps all draw through ``chisurf.plugins.traj.emtk_tool``;
the helper lives in this plugin's test folder and the other trajectory plugins import it.
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
DATA = REPO / "test" / "data" / "atomic_coordinates" / "trajectory" / "hgbp1"
SIZE = (800, 600)
CTRL_A = 0x04000000      # the select-all modifier the drawn fields answer to (as the other click suites use it)
N_FRAMES = 8


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """Settings and the working directory go to a temporary folder; nothing of the user's is read or written."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture(scope="session")
def small_trajectory(tmp_path_factory):
    """A real trajectory, small: the first frames of the hgbp1 test DCD and its PDB, in a folder of their own.

    The folder holds ``small.dcd`` (8 frames, 5235 atoms), ``other.dcd`` (frames 8-15), ``topol.pdb``, a text file
    and a sub folder, so a file dialog started in it has something to filter and to enter.
    """
    from chisurf.core.structure import trajectory_data as md

    folder = tmp_path_factory.mktemp("traj_inputs")
    full = md.load(str(DATA / "hgbp1_transition.dcd"), top=str(DATA / "topol.pdb"))
    full[:N_FRAMES].save_dcd(str(folder / "small.dcd"))
    full[N_FRAMES:2 * N_FRAMES].save_dcd(str(folder / "other.dcd"))
    shutil.copy(DATA / "topol.pdb", folder / "topol.pdb")
    (folder / "notes.txt").write_text("not a trajectory")
    (folder / "sub").mkdir()
    return folder


def read_xyz(path, top):
    """Coordinates (frames, atoms, 3) of a DCD, read the way the tools read it."""
    from chisurf.core.structure import trajectory_data as md

    return np.asarray(md.load(str(path), top=str(top)).xyz)


class Ui:
    """The mouse, keyboard and host of one app drawn at a small canvas, with the frame's strings at hand."""

    def __init__(self, app, size=SIZE):
        self.app, self.size = app, size
        self.last = None
        self.draw(2)

    # -- frames ---------------------------------------------------------------------------------------------- #
    def draw(self, frames=2):
        for _ in range(frames):
            self.last = RecordingPainter()
            self.app.draw(self.last, 0, 0, *self.size)
        return self.last

    @property
    def strings(self):
        return self.last.strings

    def shown(self, text):
        """Whether *text* is part of a string drawn in the last frame."""
        return any(text in s for s in self.last.strings)

    def settle(self, timeout=120.0):
        """Draw until the worker has finished (``app.running`` clears) and the result is on screen."""
        end = time.monotonic() + timeout
        while self.app.running:
            assert time.monotonic() < end, "the work did not finish"
            time.sleep(0.01)
            self.draw(1)
        return self.draw(2)

    # -- pointer ----------------------------------------------------------------------------------------------- #
    def click_at(self, x, y, clicks=1):
        self.app.pointer_move(x, y)
        self.draw(1)
        self.app.press(x, y, clicks=clicks)
        self.draw(1)
        self.app.release()
        return self.draw(2)          # the frame that sees the release, then the one that shows its effect

    def click(self, key_or_rect, fx=0.5, fy=0.5, clicks=1):
        """Press and release at a control's drawn rectangle (``item_rects`` key) or at an ``(x, y, w, h)``."""
        rect = self.app.item_rects[key_or_rect] if isinstance(key_or_rect, str) else key_or_rect
        x, y, w, h = rect
        return self.click_at(x + w * fx, y + h * fy, clicks)

    def text_rect(self, label, nth=-1):
        hits = [t[:4] for t in self.last.texts if t[5] == label]
        assert hits, f"{label!r} is not drawn; drawn: {self.last.strings[:60]}"
        return hits[nth]

    def press_text(self, label, nth=-1, clicks=1):
        """Click the button (or list entry) whose caption is *label*, at the text it drew."""
        self.draw(1)
        return self.click(self.text_rect(label, nth), clicks=clicks)

    def wheel_over(self, key, steps):
        x, y, w, h = self.app.item_rects[key]
        self.app.wheel(x + w / 2, y + h / 2, steps)
        return self.draw(2)

    # -- keyboard ---------------------------------------------------------------------------------------------- #
    def key(self, code, text=""):
        self.app.key(code, text)
        return self.draw(1)

    def type_text(self, text, replace=True):
        if replace:
            self.app.key(0x41, "a", CTRL_A)
            self.draw(1)
        for ch in text:
            self.app.key(ord(ch), ch)
            self.draw(1)

    def type_into(self, key, text, enter=True, replace=True):
        """Click a field, select its content, type *text* and (by default) press Enter."""
        self.draw(1)
        self.click(key, fx=0.3)
        assert self.app.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.type_text(text, replace)
        if enter:
            self.key(keys.KEY_RETURN, "\r")
        return self.draw(2)

    def arrow(self, key, direction):
        """Click the up (+1) or down (-1) arrow of a number field."""
        self.draw(1)
        x, y, w, h = self.app.item_rects[f"{key}.stepper"]
        return self.click_at(x + w / 2, y + h * (0.25 if direction > 0 else 0.75))

    # -- host ---------------------------------------------------------------------------------------------------- #
    def drop(self, *paths):
        """Hand files to the window as the host does; the return value is the host's "accepted"."""
        accepted = self.app.on_files_dropped([str(p) for p in paths])
        self.draw(2)
        return accepted

    # -- the file dialog ---------------------------------------------------------------------------------- #
    @property
    def dialog_open(self):
        return self.app.dialog is not None

    def dialog_pick(self, name, action="Open", double=False):
        """Click the entry *name* of the open dialog, then its action button (or double click the entry)."""
        self.draw(2)
        assert self.dialog_open, "no dialog is open"
        self.press_text(name, clicks=2 if double else 1)
        if not double:
            self.press_text(action)
        return self.draw(2)

    def save_dialog_type_name(self, name):
        """Type into the save dialog's name field (the field is the one showing the suggested file name)."""
        self.draw(2)
        suggested = self.app.dialog.filename or "file name"          # the empty field shows its hint
        self.click(self.text_rect(suggested), fx=0.3)
        assert self.app.io.want_capture_keyboard
        self.type_text(name)


def folder_of(path) -> str:
    return os.path.dirname(str(path))


# -- checks every single-panel trajectory tool shares (each plugin's click suite calls them with its own rows) ---- #


def check_guide_and_help_buttons(make_app, size=SIZE, prev_step=3, close_step=3):
    """Guide and Help are pressed: the tour card walks Next / Prev / Close, the help page opens and closes.

    Next is pressed on the first (introduction) step, Prev on *prev_step*, Close Tour on *close_step*. On some
    steps of some tools a card button lies over a field or the log, which take the press instead (see
    :func:`dead_tour_buttons`), so the steps are chosen where the buttons answer.
    """
    ui = Ui(make_app(), size)
    try:
        steps = len(ui.app.tour.steps)
        assert steps >= 5
        ui.click("guide")
        assert ui.app.tour.active and ui.shown(f"Step 1 of {steps}")
        ui.press_text("Next ►")
        assert ui.app.tour.step_idx == 1 and ui.shown(f"Step 2 of {steps}") and not ui.shown(f"Step 1 of {steps}")
        ui.app.tour.start(prev_step)
        ui.draw(2)
        ui.press_text("◄ Prev")
        assert ui.app.tour.step_idx == prev_step - 1 and ui.shown(f"Step {prev_step} of {steps}")
        ui.app.tour.start(close_step)
        ui.draw(2)
        ui.press_text("Close Tour")
        assert not ui.app.tour.active and not ui.shown("Step 1 of")
        assert not ui.app.help_window.open
        ui.click("help")
        assert ui.app.help_window.open and ui.shown("Close Help")
        ui.press_text("Close Help")
        assert not ui.app.help_window.open and not ui.shown("Close Help")
    finally:
        ui.app.close()


def dead_tour_buttons(make_app, size=SIZE):
    """The tour card's Prev / Close Tour buttons that do not answer a press at their centre, as ``(button, step)``.

    The card is drawn over the window without blocking it, so a button lying over an input field or the log loses
    the press to it (an emtk gap, repro in the report); the list is empty where the card sits over free space.
    """
    ui = Ui(make_app(), size)
    dead = []
    for step in range(len(ui.app.tour.steps)):
        ui.app.tour.start(step)
        ui.draw(2)
        ui.click(ui.text_rect("Close Tour"))
        if ui.app.tour.active:
            dead.append(("Close Tour", step + 1))
        if step:
            ui.app.tour.start(step)
            ui.draw(2)
            ui.click(ui.text_rect("◄ Prev"))
            if ui.app.tour.step_idx != step - 1:
                dead.append(("Prev", step + 1))
    ui.app.close()
    return dead


def check_browse_row(make_app, row, pick, other, folder, title, wrong=("notes.txt",), model_attr=None, size=SIZE):
    """A row's ``…``: the dialog opens in *folder* (the working directory, set by the caller), lists only matching files, and every way out is clicked.

    ``pick`` is the file the row must take, ``other`` a file of the other kind (filtered out), ``title`` the dialog's
    caption. Covers: open, filter, select + Open, double click, Cancel, the window's close button, Open with
    nothing selected, entering a folder and going up.
    """
    ui = Ui(make_app(), size)
    app = ui.app
    attr = model_attr or next(p.attr for p in app.paths if p.key == row)
    try:
        assert not ui.dialog_open
        ui.click(f"{row}_browse")
        assert ui.dialog_open and ui.shown(title) and ui.shown("Cancel")
        assert ui.shown(pick.name) and not ui.shown(other.name) and not any(ui.shown(w) for w in wrong)
        assert ui.shown("sub")                                       # folders are listed
        # Open with nothing selected: the dialog stays and says so
        ui.press_text("Open")
        assert ui.dialog_open and ui.shown("Select a file first.") and not getattr(app.model, attr)
        # Cancel closes without a choice
        ui.press_text("Cancel")
        assert not ui.dialog_open and not getattr(app.model, attr)
        # the window's close button
        ui.click(f"{row}_browse")
        ui.press_text("×")
        assert not ui.dialog_open and not getattr(app.model, attr)
        # a folder is entered by a click and left by "[..]"
        ui.click(f"{row}_browse")
        ui.press_text("[sub]")
        assert os.path.basename(app.dialog.directory) == "sub" and not ui.shown(pick.name)
        ui.press_text("[..]")
        assert app.dialog.directory == str(folder) and ui.shown(pick.name)
        # a click selects, Open takes it into the row
        ui.press_text(pick.name)
        assert app.dialog.selection == [pick.name]
        ui.press_text("Open")
        assert not ui.dialog_open and getattr(app.model, attr) == str(pick)
        assert ui.shown(str(pick)) or ui.shown(pick.name)
        # a double click on an entry takes it at once
        setattr(app.model, attr, "")
        ui.click(f"{row}_browse")
        ui.press_text(pick.name, clicks=2)
        assert not ui.dialog_open and getattr(app.model, attr) == str(pick)
    finally:
        app.close()


def check_row_is_read_only(make_app, row, folder, size=SIZE):
    """Typing into a path row changes nothing: the path is chosen with ``…`` or a drop only, as in Qt."""
    ui = Ui(make_app(), size)
    try:
        before = getattr(ui.app.model, next(p.attr for p in ui.app.paths if p.key == row))
        ui.click(row, fx=0.3)
        ui.type_text("/etc/passwd")
        ui.key(keys.KEY_RETURN, "\r")
        assert getattr(ui.app.model, next(p.attr for p in ui.app.paths if p.key == row)) == before
        assert not ui.shown("/etc/passwd")
    finally:
        ui.app.close()


def check_action_flow(make_app, folder, tmp_path, load, suggested, title, precondition, cancelled, verify,
                      log_names_target=True, size=SIZE):
    """The action button, from an empty window to a written file, every dialog button clicked.

    ``load(ui)`` puts the inputs in with real input (drops or dialogs); ``verify(path)`` checks the written file.
    Covers: the precondition message, the dialog (title, suggested name), Cancel and the close button (the
    cancelled line in the log, no file), a typed name + Save (the file, the log), a second Save onto the same
    name (the overwrite question: Choose another name, Cancel, then Replace existing file).
    """
    ui = Ui(make_app(), size)
    app = ui.app
    target = tmp_path / f"typed_name{Path(suggested).suffix or '.txt'}"
    try:
        ui.click("save" if "save" in app.item_rects else app.action.key)
        key = app.action.key
        assert not ui.dialog_open and ui.shown(precondition)
        load(ui)
        ui.click(key)
        assert ui.dialog_open and ui.shown(title) and (not suggested or ui.shown(suggested))
        ui.press_text("Cancel")
        assert not ui.dialog_open and any(cancelled in line for line in app.model.log_text())
        ui.click(key)
        ui.press_text("×")
        assert not ui.dialog_open and not list(tmp_path.glob("typed_name*"))
        # the dialog starts where the first input is; the typed name is joined to it, so type an absolute path
        ui.click(key)
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        assert not ui.dialog_open
        ui.settle()
        assert target.exists(), app.status
        verify(target)
        if log_names_target:
            assert ui.shown(target.name) or any(target.name in line for line in app.model.log_text())
        # a second save onto the same file asks first
        stamp = target.stat().st_mtime_ns
        ui.click(key)
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        assert ui.dialog_open and ui.shown("Replace the existing file?")
        ui.press_text("Choose another name")
        assert ui.dialog_open and not ui.shown("Replace the existing file?")
        ui.press_text("Save")
        ui.press_text("Cancel")
        assert not ui.dialog_open and target.stat().st_mtime_ns == stamp
        ui.click(key)
        ui.save_dialog_type_name(str(target))
        ui.press_text("Save")
        ui.press_text("Replace existing file")
        ui.settle()
        assert target.stat().st_mtime_ns != stamp
        verify(target)
    finally:
        app.close()


def spec_description(app, attr):
    """The ``description`` the app's spec declares for field *attr* (what its tooltip must say)."""
    def walk(sections):
        for section in sections:
            if section.get("attr") == attr:
                return section["description"]
            found = walk(section.get("sections", []))
            if found:
                return found
        return None

    extra = [getattr(app, name) for name in ("_weight_spec", "_choice_spec") if hasattr(app, name)]
    extra += list(getattr(app, "_specs", {}).values())               # a tool with an editor built from a registry
    for spec in [app.spec, *extra]:
        found = walk(spec["sections"])
        if found:
            return found
    raise AssertionError(attr)


def hover_tooltip(ui, key_or_rect, text, wait=0.15, frames=8):
    """Rest the pointer on a control until its tooltip is drawn; True when the start of *text* is in it.

    A long tooltip wraps, so only its first words (the first drawn line) are compared.
    """
    text = text[:24]
    rect = ui.app.item_rects[key_or_rect] if isinstance(key_or_rect, str) else key_or_rect
    x, y, w, h = rect
    ui.app.pointer_move(1, 1)                  # a pointer that already rests on the item (after a popup) shows nothing
    ui.draw(2)
    ui.app.pointer_move(x + w / 2, y + h / 2)
    for _ in range(frames):
        time.sleep(wait)
        ui.draw(1)
        if ui.shown(text):
            return True
    return False


def clear_field(ui, key, enter=False):
    """Click a text field, select everything, delete it with Backspace and commit it.

    The commit is a click on the log (the Qt box commits on focus loss); with ``enter=True`` it is Enter instead.
    """
    ui.draw(1)
    ui.click(key, fx=0.3)
    ui.app.key(0x41, "a", CTRL_A)
    ui.draw(1)
    ui.key(keys.KEY_BACKSPACE, "")
    if enter:
        ui.key(keys.KEY_RETURN, "\r")
    else:
        ui.click("log", fy=0.9)


def check_number_field(make_app, key, start, typed, minimum, maximum, step, as_type=float, size=SIZE, model_of=None,
                       prepare=None):
    """One spin field: typed value + Enter, click-away commit, rejected text, both limits, arrows, the tooltip.

    The Qt spin boxes clamp to the spec's range and step by ``step``; the arrows stop at the limits.
    """
    ui = Ui(make_app(), size)
    if prepare is not None:
        prepare(ui)
    model = model_of(ui.app) if model_of else ui.app.model
    attr = key
    try:
        assert getattr(model, attr) == start
        assert hover_tooltip(ui, key, spec_description(ui.app, key))
        ui.type_into(key, str(typed))
        assert getattr(model, attr) == as_type(typed) and ui.shown(str(typed))
        ui.type_into(key, "not a number")                   # text that is no number leaves the value
        assert getattr(model, attr) == as_type(typed)
        ui.type_into(key, str(maximum * 10 + 1))            # above the range: the maximum, as the Qt box clamps
        assert getattr(model, attr) == maximum
        ui.type_into(key, str(minimum - 5))                 # below it: the minimum
        assert getattr(model, attr) == minimum
        ui.arrow(key, -1)                                   # an arrow at the limit stays
        assert getattr(model, attr) == minimum
        ui.arrow(key, +1)
        assert getattr(model, attr) == pytest.approx(minimum + step)
        ui.arrow(key, +1)
        assert getattr(model, attr) == pytest.approx(minimum + 2 * step)
        ui.arrow(key, -1)
        assert getattr(model, attr) == pytest.approx(minimum + step)
        # typing without Enter, then a click on another field commits (the Qt box commits on focus loss)
        ui.draw(1)
        ui.click(key, fx=0.3)
        ui.type_text(str(typed))
        assert getattr(model, attr) == pytest.approx(minimum + step)
        other = next(k for k in ("trajectory", "topology") if k in ui.app.item_rects)
        ui.click(other, fx=0.9)
        assert getattr(model, attr) == as_type(typed)
        assert ui.app.status == ""
    finally:
        ui.app.close()


def check_text_field(make_app, key, start, typed, size=SIZE):
    """A text field: typed + Enter, emptied with Backspace and a click away (an empty value is allowed), the tooltip."""
    ui = Ui(make_app(), size)
    model = ui.app.model
    try:
        assert getattr(model, key) == start
        assert hover_tooltip(ui, key, spec_description(ui.app, key))
        ui.type_into(key, typed)
        assert getattr(model, key) == typed and ui.shown(typed)
        clear_field(ui, key)
        assert getattr(model, key) == ""
    finally:
        ui.app.close()


def enter_commits_an_emptied_field(make_app, key, typed, size=SIZE):
    """Backspace a typed text field empty and press Enter; returns the model value (the Qt box would be empty)."""
    ui = Ui(make_app(), size)
    ui.type_into(key, typed)
    clear_field(ui, key, enter=True)
    value = getattr(ui.app.model, key)
    ui.app.close()
    return value


def wheel_steps_a_number_field(make_app, key, size=SIZE):
    """The wheel over a spin field steps it (the Qt spin boxes do); returns (before, after)."""
    ui = Ui(make_app(), size)
    before = getattr(ui.app.model, key)
    x, y, w, h = ui.app.item_rects[key]
    ui.app.pointer_move(x + w / 2, y + h / 2)
    ui.draw(2)
    ui.app.wheel(x + w / 2, y + h / 2, 3)
    ui.draw(3)
    after = getattr(ui.app.model, key)
    ui.app.close()
    return before, after


def check_log_scrolls_with_the_wheel(make_app, size=SIZE):
    """A long log scrolls under the wheel (the Qt log is a scrolling text); returns the y of its first line as it was,
    after a turn down and after a turn back."""
    ui = Ui(make_app(), size)
    try:
        for index in range(60):
            ui.app.model.append_log(f"line {index}")             # the log's content is data, the scrolling is input
        ui.draw(3)

        def first():
            return [t[1] for t in ui.last.texts if t[5].endswith("] line 0")][0]

        at_start = first()
        x, y, w, h = ui.app.item_rects["log"]
        ui.app.pointer_move(x + w / 2, y + h / 2)
        ui.draw(1)
        ui.app.wheel(x + w / 2, y + h / 2, -5)                    # a turn down: later lines come into view
        ui.draw(3)
        scrolled_down = first()
        ui.app.wheel(x + w / 2, y + h / 2, 3)                     # and back
        ui.draw(3)
        return at_start, scrolled_down, first()
    finally:
        ui.app.close()
