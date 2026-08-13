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
from typing import TYPE_CHECKING

from ..object_menus import SEP, MenuEntry

if TYPE_CHECKING:  # pragma: no cover - annotations only
    # The *tables* below are plain data, and the in-viewport menu bar is drawn
    # from them by a host with no toolkit at all. Only `build_menu_bar` installs
    # a Qt bar, so Qt is imported there rather than here.
    from qtpy import QtWidgets

#: Menus PyMOL has that chimol cannot fill at all, and why.
OMITTED_MENUS: dict[str, str] = {
    "Movie": "no movie programming; frames are driven by the timeline panel",
    "Scene": "no stored scenes",
    "Plugin": "chimol is itself a ChiSurf plugin",
    "Mouse": "the mouse-mode matrix is chosen in the viewport block, and the "
             "drag style is PyMOL's with nothing to switch to",
}


FILE_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Open...", "open", "Load a structure file."),
    MenuEntry("Fetch PDB...", "fetch {text}",
              prompt=("Fetch", "PDB id (e.g. 1dg3):")),
    SEP,
    MenuEntry("Save Molecule As...", "save {text}",
              "The structure as the viewer holds it -- coordinates as "
              "transformed, atoms as present.",
              file_prompt=("save", "Save molecule",
                           "Structures (*.pdb *.cif *.mmcif *.pqr)")),
    MenuEntry("Save Image As...", "png {text}",
              file_prompt=("save", "Save image", "Images (*.png)")),
    MenuEntry("Export", None, "", children=(
        MenuEntry("glTF for PowerPoint...", "save {text}",
                  "Binary glTF (.glb) of the drawn scene -- place it on a "
                  "slide with Insert ▸ 3D Models.",
                  file_prompt=("save", "Export glTF (PowerPoint: Insert ▸ 3D Models)",
                               "glTF binary (*.glb)")),
        MenuEntry("STL...", "save {text}",
                  "Triangles for printing and CAD; STL carries no colours.",
                  file_prompt=("save", "Export STL", "STL (*.stl)")),
        MenuEntry("WRL (VRML)...", "save {text}",
                  "VRML 2.0 with per-vertex colours.",
                  file_prompt=("save", "Export WRL", "VRML (*.wrl)")),
    )),
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
    MenuEntry("Undo", "undo",
              "Coordinate undo, PyMOL's scope: sixteen snapshots per object; "
              "colours, representations and deletions are outside it."),
    MenuEntry("Redo", "redo"),
)


#: PyMOL's Build menu, with the structure-editing tools chimol has. This menu
#: was omitted as "no structure editing" long after the editing landed --
#: bond/unbond with orders, remove, alter, pseudoatom, h_add and the
#: mutagenesis wizard all exist and are tested; the menu was the missing half.
BUILD_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Bond Picked Pair", "bond",
              "Create a bond between exactly two selected atoms "
              "(`bond atom1, atom2` at the prompt for anything else)."),
    MenuEntry("Unbond Picked Pair", "unbond",
              "Remove the bond between two selected atoms."),
    SEP,
    MenuEntry("Add Hydrogens", "h_add",
              "Add hydrogens to the selection, or to everything without one."),
    MenuEntry("Add Pseudoatom", "pseudoatom",
              "A placeholder atom at the origin (`pseudoatom name, pos=[x,y,z]` "
              "places it)."),
    SEP,
    MenuEntry("Remove Selection", "remove sele",
              "Delete the selected atoms from the structure.",
              color="#c03333"),
    SEP,
    MenuEntry("Mutagenesis Wizard", "wizard mutagenesis",
              "Pick a residue, choose what it becomes, step the rotamers; "
              "nothing is committed until Apply."),
)


DISPLAY_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Sequence", None, "", children=(
        MenuEntry("Show", "set seq_view, on"),
        MenuEntry("Hide", "set seq_view, off"),
    )),
    MenuEntry("Hierarchy", "hierarchy_panel toggle",
              "The structure's node tree, in a window inside the viewport."),
    MenuEntry("Density controls", "density_panel toggle",
              "The map's contour levels and display mode, in a window inside "
              "the viewport."),
    MenuEntry("Object List", "object_panel toggle",
              "The loaded objects with their A/S/H/L/C menus -- the window "
              "snapped top-right until you move it."),
    MenuEntry("Mouse Settings", "mouse_panel toggle",
              "The mouse-mode reference block, as its own window."),
    MenuEntry("Settings", "settings_panel toggle",
              "Every display setting, edited in the view it changes."),
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
    MenuEntry("Edit All...", "config", "Open the display configuration."),
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




#: The toolbar above the scene, migrated from the Qt one in `controls_panel.py`.
#:
#: Every button is a **command**, which is the difference from the Qt row: those
#: were wired to Qt slots, so the toolbar worked only on the desktop and taught
#: nobody the command behind it. Drawn by the chrome, the same row serves the
#: browser -- and each press is echoed at the prompt like any other command.
TOOLBAR: tuple[tuple[str, str, str], ...] = (
    ("Open", "open", "Load a structure file."),
    ("Plane", "toggle_rep plane", "Show or hide the reference plane."),
    ("Surf", "toggle_rep surface", "Show or hide the molecular surface."),
    ("Cfg", "config", "Open the display configuration."),
    ("AA", "color by_residue", "Colour by amino-acid type."),
    ("SS", "color by_ss", "Colour by secondary structure."),
    ("Seq", "color by_sequence", "Colour N to C."),
    ("Info", "info_panel toggle", "Show or hide the system-info panel."),
    ("Density", "density_panel toggle", "Contour levels for a loaded map."),
    ("Tree", "hierarchy_panel toggle", "The structure's node tree."),
)


def _demo_menu() -> tuple[MenuEntry, ...]:
    """The shipped demos, built from the one table that lists them.

    Generated rather than transcribed: a demo added to `DEMOS` and forgotten
    here would be shipped and unreachable, which is the failure the Qt menu
    already avoided by being generated the same way.
    """
    from .demo_catalog import DEMOS

    entries = [
        MenuEntry(title, f"demo {key}", note) for key, title, note in DEMOS
    ]

    # The guided tours, above the demos' own housekeeping. A demo runs itself
    # and shows a finished result; a tour points at the controls and waits for
    # the user to press them, which is the half a finished result cannot teach.
    # Generated from the shipped files for the same reason the demos are: one
    # added and not listed here would be unreachable.
    from ..tour import available_tours

    tours = available_tours()
    if tours:
        entries.append(SEP)
        for key, title in tours:
            entries.append(
                MenuEntry(f"Tour: {title}", f"tour {key}",
                          "Step by step, pointing at the real controls.")
            )

    entries.append(SEP)
    entries.append(
        MenuEntry("List them at the prompt", "demo",
                  "Print every demo and what it shows.")
    )
    entries.append(
        MenuEntry("Edit a demo script…", "demo_edit",
                  "A demo is a starting point, not a fixed recital.")
    )
    entries.append(MenuEntry("New script…", "demo_edit new"))
    return tuple(entries)


DEMO_MENU: tuple[MenuEntry, ...] = _demo_menu()


def _preset_menu() -> tuple[MenuEntry, ...]:
    """The reference viewer's presets, generated from the JSON that declares them.

    Title *and* tooltip come from `gui/presets.json`, which is also what
    `preset_cx` lists and what the documentation quotes. A menu label written
    here would be a second copy of a sentence that already exists, and the
    second copy is the one that goes stale -- a tooltip describing what a
    control used to do is worse than none.

    Its own menu rather than more rows under the object menu's `preset`
    sub-menu, because it is a different question: PyMOL's presets choose *what
    to show* -- ligands, sites, interfaces -- and these choose *how what is
    already shown should look*. Mixed, they make one list of twenty-five
    entries in which neither is findable.
    """
    from ..cmd.presets import load_reference_presets

    entries = [
        MenuEntry(entry["title"], f"preset_cx {key}", entry["description"])
        for key, entry in load_reference_presets().items()
    ]
    if not entries:
        return ()
    entries.append(SEP)
    entries.append(
        MenuEntry("List them at the prompt", "preset_cx",
                  "Print every preset and what it does.")
    )
    return tuple(entries)


PRESET_MENU: tuple[MenuEntry, ...] = _preset_menu()


#: PyMOL's Wizard menu, with the one wizard chimol has. The rest of PyMOL's
#: -- measurement, appearance, density, sculpting -- are listed nowhere rather
#: than listed and disabled: a wizard is a *mode*, and offering to enter one
#: that does not exist is worse than not offering it.
WIZARD_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Mutagenesis", "wizard mutagenesis",
              "Pick a residue, choose what it becomes, step the rotamers and "
              "watch the clashes; nothing is committed until Apply."),
    MenuEntry("Measurement", "wizard measurement",
              "Click atoms in the viewport; every two become a distance. The "
              "panel switches to angles and dihedrals."),
    SEP,
    MenuEntry("Done", "wizard done", "Leave the wizard, discarding a preview."),
)


#: The Tools menu, grouped into submenus the way the reference viewer groups
#: its tools. PyMOL's bar has no Tools menu -- this one exists because the map
#: tools have no natural PyMOL home, and burying Hide Dust under Display would
#: hide the tool the way the dust hides the map. Every entry is a command, so
#: everything here is reproducible at the prompt.
TOOLS_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Map", None, "", children=(
        MenuEntry("Density Controls", "density_panel toggle",
                  "Contour levels, style, quality and colours, in a window "
                  "inside the viewport."),
        MenuEntry("Map Info", "map_info",
                  "Size, voxel step, origin and value range at the prompt."),
        SEP,
        MenuEntry("Hide Dust", "hide_dust",
                  "Hide the small disconnected crumbs of the contour; the "
                  "default keeps pieces larger than five voxels. Tune with "
                  "`hide_dust map, size`."),
        MenuEntry("Show Dust", "show_dust",
                  "Show the hidden pieces again."),
        MenuEntry("Gaussian Filter", "volume_gaussian",
                  "A Gaussian-smoothed copy of the map, added as a new map. "
                  "Width defaults to one voxel; `volume_gaussian map, sdev` "
                  "chooses another."),
        SEP,
        MenuEntry("Style", None, "", children=(
            MenuEntry("Surface", "isosurface"),
            MenuEntry("Mesh", "isomesh"),
            MenuEntry("Solid", "volume"),
        )),
        MenuEntry("Surface Quality", None, "", children=(
            MenuEntry("Coarse", "volume_quality coarse"),
            MenuEntry("Normal", "volume_quality normal"),
            MenuEntry("Smooth", "volume_quality smooth"),
            MenuEntry("Fine", "volume_quality fine"),
        )),
    )),
    MenuEntry("Measure", None, "", children=(
        MenuEntry("Measurement Wizard", "wizard measurement",
                  "Click atoms in the viewport; every two become a distance."),
        MenuEntry("Distance...", "distance {text}",
                  prompt=("Distance",
                          "name, selection 1, selection 2:")),
    )),
    MenuEntry("Panels", None, "", children=(
        MenuEntry("Hierarchy", "hierarchy_panel toggle"),
        MenuEntry("Density", "density_panel toggle"),
        MenuEntry("Object List", "object_panel toggle"),
        MenuEntry("Mouse Settings", "mouse_panel toggle"),
        MenuEntry("Settings", "settings_panel toggle"),
        MenuEntry("System Info", "info_panel toggle"),
    )),
)


HELP_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("Commands", "help"),
    MenuEntry("Settings", "help_setting"),
    SEP,
    # The way out of a layout that has gone wrong. It belongs in a menu rather
    # than only as a command because the state it repairs -- a window dragged
    # off-screen, or saved at a size a bug produced -- is exactly the state in
    # which the user cannot find the thing they need.
    MenuEntry("Reset GUI", "window_reset"),
    # The frame-rate readout and the chrome-size slider. In a menu because a
    # mode you have to know the command for is a mode nobody finds -- and this
    # is the one people want the moment they wonder why something feels slow.
    MenuEntry("Debug Mode", "debug_mode"),
)


#: Menus chimol adds that PyMOL's bar does not have. Kept in one place so the
#: ordering test can hold PyMOL's menus to PyMOL's order while allowing these.
EXTRA_MENUS: frozenset[str] = frozenset({"Demo", "Tools", "Preset"})

#: The bar, in PyMOL's order, minus the menus listed in OMITTED_MENUS, plus
#: the chimol-specific EXTRA_MENUS slotted where they read best.
MENU_BAR: tuple[tuple[str, tuple[MenuEntry, ...]], ...] = (
    ("File", FILE_MENU),
    ("Edit", EDIT_MENU),
    ("Build", BUILD_MENU),
    ("Display", DISPLAY_MENU),
    ("Setting", SETTING_MENU),
    ("Preset", PRESET_MENU),
    ("Demo", DEMO_MENU),
    ("Wizard", WIZARD_MENU),
    ("Tools", TOOLS_MENU),
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
    from qtpy import QtWidgets

    command = entry.command or ""
    if command.startswith("__") and command.endswith("__"):
        handler = special.get(command.strip("_"))
        if handler is not None:
            handler()
        return

    text = None
    if entry.file_prompt is not None:
        # A real file dialog, not a text box: a filename typed blind lands
        # wherever the process is running, which for a menu action is nowhere
        # the user chose. The command line keeps taking paths as text -- a
        # dialog is the menu's affordance, not the CLI's.
        mode, title, name_filter = entry.file_prompt
        if mode == "open":
            text, _used = QtWidgets.QFileDialog.getOpenFileName(
                parent, title, "", name_filter
            )
        else:
            text, _used = QtWidgets.QFileDialog.getSaveFileName(
                parent, title, "", name_filter
            )
        if not str(text).strip():
            return
        text = str(text).strip()
    elif entry.prompt is not None:
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


__all__ = ["EXTRA_MENUS", "MENU_BAR", "OMITTED_MENUS", "build_menu_bar"]
