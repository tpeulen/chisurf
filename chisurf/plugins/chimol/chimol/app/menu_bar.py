"""PyMOL's main menu bar, as far as chimol can honour it.

PyMOL's bar is **File · Edit · Build · Movie · Display · Setting · Scene · Mouse
· Wizard · Plugin · Help** (``pymol/_gui.py:get_menudata``). A PyMOL user looks
for things by that grouping, so the menus chimol *can* fill keep PyMOL's name,
position and wording.

Unlike the per-object menus, whole top-level menus are **omitted** rather than
shown empty: Build, Movie, Scene, Wizard and Plugin have no chimol equivalent at
all, and an empty menu on the bar is a promise with nothing behind it. Within a
menu that does exist, individual entries follow the object-menu rule — present,
disabled and explained — so the shape of the menu still matches.
"""

from __future__ import annotations

from collections.abc import Callable

from qtpy import QtWidgets

from ..object_menus import SEP, MenuEntry

#: Menus PyMOL has that chimol cannot fill at all, and why.
OMITTED_MENUS: dict[str, str] = {
    "Build": "no structure editing",
    "Movie": "no movie programming; frames are driven by the timeline panel",
    "Scene": "no stored scenes",
    "Plugin": "chimol is itself a ChiSurf plugin",
}


FILE_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Open...", "open", "Load a structure file."),
    MenuEntry("Fetch PDB...", "fetch {text}",
              prompt=("Fetch", "PDB id (e.g. 1dg3):")),
    SEP,
    MenuEntry("Save Image As...", "png {text}",
              prompt=("Save image", "File name:")),
    MenuEntry("Save Movie As...", None, "Chimol cannot export movies."),
    SEP,
    MenuEntry("Log File", None, "Chimol does not log commands to a file."),
    MenuEntry("Working Directory", None, "Chimol has no working-directory "
                                         "concept; paths are absolute."),
    SEP,
    MenuEntry("Reinitialize", "reinitialize"),
    SEP,
    MenuEntry("Quit", "quit"),
)


EDIT_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Undo", None, "Chimol has no undo stack."),
    MenuEntry("Redo", None, "Chimol has no undo stack."),
)


DISPLAY_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Sequence", None, "", children=(
        MenuEntry("Show", "set seq_view, on"),
        MenuEntry("Hide", "set seq_view, off"),
    )),
    SEP,
    MenuEntry("Stereo", None, "Chimol has no stereo modes."),
    SEP,
    MenuEntry("Zoom", None, "", children=(
        MenuEntry("4 Angstrom", "zoom all, 4"),
        MenuEntry("6 Angstrom", "zoom all, 6"),
        MenuEntry("8 Angstrom", "zoom all, 8"),
        MenuEntry("12 Angstrom", "zoom all, 12"),
        MenuEntry("20 Angstrom", "zoom all, 20"),
        MenuEntry("All", "zoom"),
        MenuEntry("Complete", "zoom all, 0, 1"),
    )),
    MenuEntry("Clip", None, "", children=(
        MenuEntry("Near in", "clip near, -5"),
        MenuEntry("Near out", "clip near, 5"),
        MenuEntry("Far in", "clip far, -5"),
        MenuEntry("Far out", "clip far, 5"),
    )),
    SEP,
    MenuEntry("Background", None, "", children=(
        MenuEntry("White", "bg_color white"),
        MenuEntry("Light Grey", "bg_color grey80"),
        MenuEntry("Grey", "bg_color grey50"),
        MenuEntry("Black", "bg_color black"),
        SEP,
        MenuEntry("Opaque", None, "Chimol always renders an opaque background."),
    )),
    SEP,
    MenuEntry("Perspective", None, "", children=(
        MenuEntry("Orthoscopic View", "set orthoscopic, on"),
        MenuEntry("Perspective View", "set orthoscopic, off"),
        SEP,
        MenuEntry("Field of view 20", "set field_of_view, 20"),
        MenuEntry("Field of view 45", "set field_of_view, 45"),
    )),
    MenuEntry("Quality", None, "", children=(
        MenuEntry("Maximum Quality", "set cartoon_sampling, 14; "
                                     "set cartoon_oval_quality, 30; "
                                     "set cartoon_loop_quality, 20"),
        MenuEntry("Default Quality", "unset cartoon_sampling; "
                                     "unset cartoon_oval_quality; "
                                     "unset cartoon_loop_quality"),
        MenuEntry("Maximum Performance", "set cartoon_sampling, 4; "
                                         "set cartoon_oval_quality, 8; "
                                         "set cartoon_loop_quality, 6"),
    )),
    SEP,
    MenuEntry("Grid", None, "", children=(
        MenuEntry("Show", "show grid"),
        MenuEntry("Hide", "hide grid"),
    )),
)


SETTING_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Edit All...", "__config__", "Open the display configuration."),
    SEP,
    MenuEntry("Label", None, "Chimol has no label representation yet."),
    MenuEntry("Lines & Sticks", None, "", children=(
        MenuEntry("Stick radius 0.1", "set stick_radius, 0.1"),
        MenuEntry("Stick radius 0.15", "set stick_radius, 0.15"),
        MenuEntry("Stick radius 0.25", "set stick_radius, 0.25"),
    )),
    MenuEntry("Cartoon", None, "", children=(
        MenuEntry("Flat Sheets", "set cartoon_flat_sheets, on"),
        MenuEntry("Curvy Sheets", "set cartoon_flat_sheets, off"),
        SEP,
        MenuEntry("Round Helices", "set cartoon_round_helices, on"),
        MenuEntry("Trace Helices", "set cartoon_round_helices, off"),
        SEP,
        MenuEntry("Ribbon", "cartoon automatic"),
        MenuEntry("Tube", "cartoon tube"),
    )),
    MenuEntry("Ambient Occlusion", None, "", children=(
        MenuEntry("On", "set occlusion.enabled, on"),
        MenuEntry("Off", "set occlusion.enabled, off"),
        SEP,
        MenuEntry("Subtle", "set occlusion.darkness, 0.4"),
        MenuEntry("Default", "set occlusion.darkness, 0.7"),
        MenuEntry("Strong", "set occlusion.darkness, 0.9"),
        SEP,
        MenuEntry("Occlude with residues", "set occlusion.occluders, residues"),
        MenuEntry("Occlude with atoms", "set occlusion.occluders, atoms"),
    )),
    MenuEntry("Surface", None, "", children=(
        MenuEntry("Solvent radius 1.4", "set solvent_radius, 1.4"),
        MenuEntry("Fine (slow)", "set surface_quality, 0.5"),
        MenuEntry("Coarse (fast)", "set surface_quality, 1.2"),
    )),
    MenuEntry("Transparency", None, "Chimol has no per-representation "
                                    "transparency yet."),
    MenuEntry("Rendering", None, "", children=(
        MenuEntry("Shadows On", "set ray_shadow, on"),
        MenuEntry("Shadows Off", "set ray_shadow, off"),
        SEP,
        MenuEntry("Antialias 1", "set antialias, 1"),
        MenuEntry("Antialias 2", "set antialias, 2"),
        MenuEntry("Antialias 4", "set antialias, 4"),
    )),
    SEP,
    MenuEntry("PDB File Loading", None, "Chimol always loads the whole "
                                        "deposited model."),
)


MOUSE_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("PyMOL drag mode", "set mouse_mode, pymol",
              "Left-drag moves the object, following the cursor."),
    MenuEntry("Chimol drag mode", "set mouse_mode, chimol",
              "Left-drag moves the camera, so the object goes the other way."),
)


#: PyMOL's Wizard menu, with the one wizard chimol has. The rest of PyMOL's
#: -- measurement, appearance, density, sculpting -- are listed nowhere rather
#: than listed and disabled: a wizard is a *mode*, and offering to enter one
#: that does not exist is worse than not offering it.
WIZARD_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Mutagenesis", "wizard mutagenesis",
              "Pick a residue, choose what it becomes, step the rotamers and "
              "watch the clashes; nothing is committed until Apply."),
    SEP,
    MenuEntry("Done", "wizard done", "Leave the wizard, discarding a preview."),
)


HELP_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Commands", "help"),
    MenuEntry("Settings", "help_setting"),
)


#: The bar, in PyMOL's order, minus the menus listed in OMITTED_MENUS.
MENU_BAR: tuple[tuple[str, tuple[MenuEntry, ...]], ...] = (
    ("File", FILE_MENU),
    ("Edit", EDIT_MENU),
    ("Display", DISPLAY_MENU),
    ("Setting", SETTING_MENU),
    ("Mouse", MOUSE_MENU),
    ("Wizard", WIZARD_MENU),
    ("Help", HELP_MENU),
)


def build_menu_bar(
    window: QtWidgets.QMainWindow,
    run_command: Callable[[str], None],
    special: dict[str, Callable[[], None]] | None = None,
) -> QtWidgets.QMenuBar:
    """Install PyMOL's menu bar on ``window``.

    Parameters
    ----------
    window : QtWidgets.QMainWindow
        Window to receive the bar.
    run_command : callable
        Runs a chimol command line; menu entries go through the same layer the
        command line does, so every action is reproducible as a typed command.
    special : dict, optional
        Handlers for entries whose command is a ``__name__`` marker rather than
        a command line, such as opening a dialog.

    Returns
    -------
    QtWidgets.QMenuBar
        The installed bar.
    """
    special = special or {}
    bar = window.menuBar()
    bar.clear()
    for title, entries in MENU_BAR:
        menu = bar.addMenu(title)
        _populate(menu, entries, run_command, special)
    return bar


def _populate(menu, entries, run_command, special) -> None:
    for entry in entries:
        if entry.is_separator:
            menu.addSeparator()
            continue
        if entry.is_submenu:
            sub = menu.addMenu(entry.label)
            if entry.note:
                sub.setToolTip(entry.note)
            _populate(sub, entry.children, run_command, special)
            continue
        action = menu.addAction(entry.label)
        if entry.note:
            action.setToolTip(entry.note)
        if entry.command is None:
            action.setEnabled(False)
            action.setToolTip(entry.note or "Not implemented in Chimol.")
            continue
        action.triggered.connect(
            lambda _checked=False, e=entry: _run(e, run_command, special, menu)
        )
    menu.setToolTipsVisible(True)


def _run(entry: MenuEntry, run_command, special, parent) -> None:
    """Run a bar entry, asking for a value first when it needs one."""
    command = entry.command or ""
    if command.startswith("__") and command.endswith("__"):
        handler = special.get(command.strip("_"))
        if handler is not None:
            handler()
        return

    text = None
    if entry.prompt is not None:
        title, question = entry.prompt
        text, ok = QtWidgets.QInputDialog.getText(parent, title, question)
        if not ok or not str(text).strip():
            return
        text = str(text).strip()

    for line in command.split(";"):
        line = line.strip()
        if not line:
            continue
        if text is not None:
            line = line.replace("{text}", text)
        run_command(line)


__all__ = ["MENU_BAR", "OMITTED_MENUS", "build_menu_bar"]
