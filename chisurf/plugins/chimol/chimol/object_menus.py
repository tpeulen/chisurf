"""PyMOL's per-object A / S / H / L / C menus, transcribed entry for entry.

PyMOL's object panel is how most people drive PyMOL: every molecule gets five
buttons, and almost everything you do day to day is in them. The tables below are
a **1:1 transcription** of ``pymol/menu.py`` — same entries, same order, same
separators, same labels (including the ones with an odd space or abbreviation, so
they read identically) — taken from PyMOL's own builders
``mol_action``/``mol_show``/``mol_hide``/``mol_labels``/``mol_color`` rather than
from a screenshot.

Each entry carries the **chimol** command it runs. Where chimol has no
equivalent, ``command`` is ``None`` and the entry is rendered greyed out with a
note saying so. That is deliberate: dropping the entry would make the menu a
different shape from PyMOL's and hide the gap, while wiring it to something
approximate would lie about what happened. A disabled entry with a reason is the
honest middle, and it keeps the menu navigable by muscle memory.

``{sele}`` in a command is replaced by the object or selection the menu was
opened on. ``{text}`` marks a command that first asks for a value.

This table sits above ``app/`` because it has two consumers now: the docked
Qt panel and the panel the renderer draws inside the viewport. Left in
``app/``, the renderer importing it pulled in ``app/__init__``, which imports
the main window, which imports the renderer -- a cycle, for a module that is
nothing but data.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MenuEntry:
    """One row of an object menu.

    Attributes
    ----------
    label : str
        PyMOL's own label, verbatim, including leading spaces used for
        indentation in its sub-groupings.
    command : str or None
        Chimol command template, with ``{sele}`` for the target and ``{text}``
        for a prompted value. ``None`` means chimol has no equivalent; the entry
        is shown disabled.
    note : str
        Shown as the tooltip. For an unsupported entry this says what is missing;
        for a supported one that differs from PyMOL, what the difference is.
    prompt : tuple of str
        ``(title, question)`` when the command needs a value first.
    children : tuple of MenuEntry
        Submenu entries.
    color : str or None
        ``#rrggbb`` for entries PyMOL tints. It marks the destructive ones with
        an RGB (9, 3, 3) escape on its 0-9 scale, and that warning is worth
        keeping.
    """

    label: str
    command: str | None = None
    note: str = ""
    prompt: tuple[str, str] | None = None
    children: tuple["MenuEntry", ...] = field(default_factory=tuple)
    color: str | None = None

    @property
    def is_separator(self) -> bool:
        """Whether this row is a gap between groups rather than an entry."""
        return self.label == ""

    @property
    def is_submenu(self) -> bool:
        """Whether this row opens a submenu."""
        return bool(self.children)


SEP = MenuEntry("")


def _pymol_color(escape: str) -> str:
    """Convert a PyMOL colour escape such as ``933`` into ``#rrggbb``."""
    return "#" + "".join(f"{round(int(d) / 9 * 255):02x}" for d in escape)


#: PyMOL's `del_col`/`rem_col`, the tint it puts on destructive entries.
DESTRUCTIVE = _pymol_color("933")

_NO_LABELS = "Chimol has no label representation yet."
_NO_SURFACE_TYPE = (
    "Chimol draws one solid surface: it has no surface_type (dot/mesh) and no "
    "per-object transparency, so these variants would all look the same."
)
_NO_EDIT = "Chimol has no structure editing yet."
_NO_MATRIX = "Chimol has no per-object matrix dragging yet."


# --------------------------------------------------------------------------- #
# A — Action  (pymol.menu.mol_action)
# --------------------------------------------------------------------------- #
ACTION_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("zoom", "zoom {sele}"),
    MenuEntry("orient", "orient {sele}"),
    MenuEntry("center", "center {sele}"),
    MenuEntry("origin", None, "Chimol rotates about the scene centre; "
                              "a per-object origin is not implemented."),
    SEP,
    MenuEntry("drag matrix", None, _NO_MATRIX),
    MenuEntry("reset matrix", None, _NO_MATRIX),
    SEP,
    MenuEntry("drag coordinates", None, _NO_MATRIX),
    MenuEntry("clean", None, _NO_EDIT),
    SEP,
    # PyMOL's own preset menu (`menu.presets`), entry for entry. These used to
    # be four hand-rolled `hide everything; show cartoon` lines wearing PyMOL's
    # labels: same words, different picture. Each now runs the transcribed
    # recipe in `cmd/presets.py`, which reports whatever step chimol cannot do.
    MenuEntry("preset", None, "", children=(
        MenuEntry("classified", "preset classified, {sele}"),
        SEP,
        MenuEntry("simple", "preset simple, {sele}"),
        MenuEntry("simple (no solvent)", "preset simple_no_solv, {sele}"),
        MenuEntry("ball and stick", "preset ball_and_stick, {sele}"),
        MenuEntry("b factor putty", "preset b_factor_putty, {sele}"),
        MenuEntry("technical", "preset technical, {sele}"),
        MenuEntry("ligands", "preset ligands, {sele}"),
        # PyMOL's "ligand sites" is itself a submenu (`menu.preset_ligand_sites`)
        # of six surface variants. The three that differ only by `surface_type`
        # / `surface_quality` / transparency are the ones chimol cannot tell
        # apart yet, so they are shown disabled with the reason rather than
        # dropped -- the menu keeps PyMOL's shape and the gap stays visible.
        MenuEntry("ligand sites", None, "", children=(
            MenuEntry("cartoon", "preset ligand_cartoon, {sele}"),
            SEP,
            MenuEntry("solid surface", "preset ligand_sites, {sele}"),
            MenuEntry("solid (better)", None, _NO_SURFACE_TYPE),
            SEP,
            MenuEntry("transparent surface", None, _NO_SURFACE_TYPE),
            MenuEntry("transparent (better)", None, _NO_SURFACE_TYPE),
            SEP,
            MenuEntry("dot surface", None, _NO_SURFACE_TYPE),
            MenuEntry("mesh surface", None, _NO_SURFACE_TYPE),
        )),
        MenuEntry("pretty", "preset pretty, {sele}"),
        MenuEntry("pretty (with solvent)", "preset pretty_solv, {sele}"),
        MenuEntry("publication", "preset publication, {sele}"),
        MenuEntry("publication (with solvent)", "preset pub_solv, {sele}"),
        SEP,
        MenuEntry("protein interface", "preset interface, {sele}"),
        SEP,
        MenuEntry("default", "preset default, {sele}"),
    )),
    # PyMOL's `find` submenu, from menu.py::find/polar. Only the polar-contact
    # arm is transcribed: halogen bonds, salt bridges and pi interactions are
    # separate detectors (`distance` modes 6-10) rather than variations on this
    # one, and each is left visible-and-disabled rather than dropped.
    MenuEntry("find", None, "", children=(
        MenuEntry("polar contacts", None, "", children=(
            MenuEntry("within selection",
                      "distance {sele}_polar_conts, {sele}, {sele}, "
                      "mode=2, label=0"),
            MenuEntry("involving side chains",
                      "distance {sele}_polar_conts, ({sele}), "
                      "({sele}) and sidechain, mode=2, label=0"),
            MenuEntry("involving solvent",
                      "distance {sele}_polar_conts, ({sele}) and solvent, "
                      "({sele}) and not solvent, mode=2, label=0"),
            MenuEntry("excluding solvent",
                      "distance {sele}_polar_conts, ({sele}) and not solvent, "
                      "({sele}) and not solvent, mode=2, label=0"),
            MenuEntry("excluding main chain",
                      "distance {sele}_polar_conts, ({sele}) and not backbone, "
                      "({sele}) and not backbone, mode=2, label=0"),
            MenuEntry("excluding intra-main chain",
                      "distance {sele}_polar_conts, ({sele}), "
                      "({sele}) and not backbone, mode=2, label=0"),
            MenuEntry("just intra-side chain",
                      "distance {sele}_polar_conts, ({sele}) and sidechain, "
                      "({sele}) and sidechain, mode=2, label=0"),
            MenuEntry("just intra-main chain",
                      "distance {sele}_polar_conts, ({sele}) and backbone, "
                      "({sele}) and backbone, mode=2, label=0"),
            SEP,
            MenuEntry("to any atoms",
                      "distance {sele}_polar_conts, ({sele}), not ({sele}), "
                      "mode=2, label=0"),
            MenuEntry("to any excluding solvent",
                      "distance {sele}_polar_conts, ({sele}) and not solvent, "
                      "(not ({sele})) and not solvent, mode=2, label=0"),
        )),
        MenuEntry("any contacts", None, "", children=(
            MenuEntry("between chains within 3.0A", None,
                      "Chimol has no interchain-distance helper yet; "
                      "`distance name, chain A, chain B, 3.0` does it by hand."),
            MenuEntry("within selection, 4.0A",
                      "distance {sele}_contacts, {sele}, {sele}, 4.0, "
                      "mode=3, label=0"),
        )),
        MenuEntry("halogen-bond interactions", None,
                  "Chimol has no halogen-bond detector (`distance mode=9`)."),
        MenuEntry("salt-bridge interactions", None,
                  "Chimol has no salt-bridge detector (`distance mode=10`)."),
        MenuEntry("pi interactions", None,
                  "Chimol has no pi-stacking detector (`distance mode=5-7`)."),
    )),
    MenuEntry("align", None, "", children=(
        MenuEntry("align to ...", "align {sele}, {text}",
                  prompt=("Align", "Align onto which object?")),
        MenuEntry("super to ...", "super {sele}, {text}",
                  prompt=("Super", "Superpose onto which object?")),
    )),
    MenuEntry("generate", None, "Chimol cannot generate symmetry mates or "
                                "surfaces as new objects yet."),
    SEP,
    MenuEntry("assign sec. struc.", "dss"),
    SEP,
    MenuEntry("rename object", "set_name {sele}, {text}",
              prompt=("Rename object", "New name:")),
    MenuEntry("copy to object", "copy {text}, {sele}",
              prompt=("Copy to object", "Name of the copy:")),
    # PyMOL's `move_to_group` builds this submenu at open time so it can list
    # every existing group. This table is static, so the prompt does that job:
    # typing a group that already exists moves the object into it, which is what
    # picking it from PyMOL's list does. The note says so rather than leaving the
    # difference to be discovered.
    MenuEntry("group", None, "", children=(
        MenuEntry("move to group...", "group {text}, {sele}",
                  "Type an existing group to join it, or a new name to start "
                  "one. PyMOL lists the existing groups here; chimol asks.",
                  prompt=("Move to group", "Group name:")),
        MenuEntry("ungroup", "ungroup {sele}"),
    )),
    MenuEntry("delete object", "delete {sele}", color=DESTRUCTIVE),
    SEP,
    MenuEntry("hydrogens", None, "", children=(
        MenuEntry("add", None, _NO_EDIT),
        MenuEntry("remove", "remove elem H and {sele}", color=DESTRUCTIVE),
    )),
    MenuEntry("remove waters", "remove solvent and {sele}",
              color=DESTRUCTIVE),
    SEP,
    MenuEntry("state", None, "Chimol frames are driven by the timeline panel."),
    MenuEntry("masking", None, "Chimol has no atom masking yet."),
    MenuEntry("sequence", None, "", children=(
        MenuEntry("show", "set seq_view, on"),
        MenuEntry("hide", "set seq_view, off"),
    )),
    MenuEntry("movement", None, "Chimol has no per-object motion yet."),
    MenuEntry("compute", None, "", children=(
        MenuEntry("count atoms", "count_atoms {sele}"),
    )),
)


# --------------------------------------------------------------------------- #
# S / H — Show and Hide  (pymol.menu.mol_show / mol_hide, via rep_action)
# --------------------------------------------------------------------------- #
# PyMOL's wire/licorice pairs are one representation with a fine-grained
# sub-entry; chimol has a single representation each, so both rows drive it.
_LINES_NOTE = "Chimol's lines are the backbone trace, not per-bond wireframe."
_NB_NOTE = "Mapped to the non-polymer atoms, which is what PyMOL's nonbonded "\
           "glyphs mark."
_NO_CELL = "Chimol does not read crystal cells."
_NO_FLAG = "Chimol has no per-atom flags yet."
_NO_VALENCE = "Chimol does not draw bond valences."


def _rep_action(action: str) -> tuple[MenuEntry, ...]:
    """PyMOL's ``rep_action`` table, shared by the Show and Hide menus."""
    return (
        MenuEntry("wire", f"{action} lines, {{sele}}", _LINES_NOTE),
        MenuEntry("  lines", f"{action} lines, {{sele}}", _LINES_NOTE),
        MenuEntry("  nonbonded", f"{action} spheres, hetatm and {{sele}}", _NB_NOTE),
        SEP,
        MenuEntry("licorice", f"{action} sticks, {{sele}}"),
        MenuEntry("  sticks", f"{action} sticks, {{sele}}"),
        MenuEntry("  nb_spheres", f"{action} spheres, hetatm and {{sele}}", _NB_NOTE),
        SEP,
        MenuEntry("ribbon", f"{action} cartoon, {{sele}}",
                  "Chimol draws one cartoon; set cartoon_tube_radius for a "
                  "ribbon-like tube."),
        MenuEntry("cartoon", f"{action} cartoon, {{sele}}"),
        SEP,
        MenuEntry("label", f"{action} labels, {{sele}}"),
        MenuEntry("cell", None, _NO_CELL),
        SEP,
        MenuEntry("dots", f"{action} dots, {{sele}}"),
        MenuEntry("spheres", f"{action} spheres, {{sele}}"),
        SEP,
        MenuEntry("mesh", f"{action} metaball, {{sele}}",
                  "Chimol's mesh is the metaball surface."),
        MenuEntry("surface", f"{action} surface, {{sele}}"),
        MenuEntry("flag ignore", None, _NO_FLAG),
    )


def _chimol_extra_reps(action: str) -> tuple[MenuEntry, ...]:
    """Representations ChiMOL has that PyMOL's menus do not name.

    They were reachable only from the toolbar, so a menu-driven session could not
    get at them at all -- which is the whole reason the menus exist. ``metaball``
    is the clearest case: PyMOL has no equivalent, so a PyMOL user has no reason
    to go looking for it.

    Appended **after** PyMOL's entries, never among them: the target's rule is
    that extensions are additive, so the familiar part of the menu stays exactly
    where a PyMOL user expects it.
    """
    return (
        SEP,
        MenuEntry("trace", f"{action} trace, {{sele}}",
                  "The CA trace on its own -- PyMOL's ribbon_trace."),
        MenuEntry("nonbonded", f"{action} nonbonded, {{sele}}",
                  "Crosses on atoms that draw no bond: waters and free ions."),
        MenuEntry("metaball", f"{action} metaball, {{sele}}",
                  "A blended isosurface over the atoms."),
    )


def _as_action() -> tuple[MenuEntry, ...]:
    """The ``as`` submenu: every representation ChiMOL can show, PyMOL-named.

    PyMOL's ``as rep`` switches the object to a single representation, and its
    mouse-free equivalent is the toolbar buttons ChiMOL is removing. The submenu
    that replaced them must therefore offer everything the buttons did -- which
    is the whole point of the request "show as opengl menu misses
    representations; include all". Each entry routes through the ``as`` command,
    which now understands every representation ``show``/``hide`` do, so the
    submenu and the command cannot drift apart.

    Every entry carries ``, {sele}`` like the Show/Hide entries do: ``as`` is
    "show this, hide the rest", and the rest is *the selection*. Without a
    target the entry ran ``as sticks`` with no selection at all, which switched
    the whole molecule; from the ``sele`` row it must switch only the
    selection.
    """
    return (
        MenuEntry("cartoon", "as cartoon, {sele}"),
        MenuEntry("ribbon", "as cartoon, {sele}",
                  "Chimol draws one cartoon; set cartoon_tube_radius for a "
                  "ribbon-like tube."),
        MenuEntry("trace", "as trace, {sele}",
                  "The CA trace on its own -- PyMOL's ribbon_trace."),
        MenuEntry("lines", "as lines, {sele}", _LINES_NOTE),
        MenuEntry("wire", "as lines, {sele}", _LINES_NOTE),
        MenuEntry("nonbonded", "as nonbonded, {sele}", _NB_NOTE),
        SEP,
        MenuEntry("sticks", "as sticks, {sele}"),
        MenuEntry("licorice", "as sticks, {sele}"),
        MenuEntry("atoms", "as atoms, {sele}"),
        MenuEntry("spheres", "as atoms, {sele}"),
        SEP,
        MenuEntry("dots", "as dots, {sele}"),
        MenuEntry("surface", "as surface, {sele}"),
        MenuEntry("metaball", "as metaball, {sele}",
                  "A blended isosurface over the atoms."),
        MenuEntry("labels", "as labels, {sele}"),
    )


SHOW_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("as", None, "Switch to a single representation.", children=_as_action()),
    SEP,
    *_rep_action("show"),
    SEP,
    MenuEntry("organic", "show spheres, organic and {sele}"),
    MenuEntry("main chain", "show sticks, name N+CA+C+O and {sele}"),
    MenuEntry("side chain", "show sticks, not name N+CA+C+O and {sele}"),
    MenuEntry("disulfides", None, "Chimol cannot find disulfides yet."),
    SEP,
    MenuEntry("valence", None, _NO_VALENCE),
) + _chimol_extra_reps("show")


HIDE_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("everything", "hide everything, {sele}"),
    SEP,
    *_rep_action("hide"),
    SEP,
    MenuEntry("main chain", "hide sticks, name N+CA+C+O and {sele}"),
    MenuEntry("side chain", "hide sticks, not name N+CA+C+O and {sele}"),
    MenuEntry("waters", "hide everything, solvent and {sele}"),
    SEP,
    MenuEntry("hydrogens", "hide everything, elem H and {sele}"),
    SEP,
    MenuEntry("unselected", "hide everything, not {sele}"),
    SEP,
    MenuEntry("valence", None, _NO_VALENCE),
) + _chimol_extra_reps("hide")


# --------------------------------------------------------------------------- #
# L — Label  (pymol.menu.mol_labels)
# --------------------------------------------------------------------------- #
# Kept in full and entirely disabled: chimol has no label representation, and a
# menu that silently loses fifteen entries is harder to trust than one that says
# what it cannot do.
LABEL_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("clear", 'label {sele}, ""'),
    SEP,
    MenuEntry("residues", 'label {sele}, "%s-%s" % (resn, resi)'),
    MenuEntry("residues (oneletter)", "label {sele}, oneletter + resi"),
    MenuEntry("chains", "label {sele}, chain"),
    MenuEntry("segments", "label {sele}, segi",
              "Chimol does not read segment identifiers from PDB files, so this "
              "labels with an empty string on most structures."),
    SEP,
    MenuEntry("atom name", "label {sele}, name"),
    MenuEntry("element symbol", "label {sele}, elem"),
    MenuEntry("residue name", "label {sele}, resn"),
    MenuEntry("one letter code", "label {sele}, oneletter"),
    MenuEntry("residue identifier", "label {sele}, resi"),
    MenuEntry("chain identifier", "label {sele}, chain"),
    MenuEntry("segment identifier", "label {sele}, segi"),
    SEP,
    MenuEntry("b-factor", "label {sele}, '%1.2f' % b"),
    MenuEntry("occupancy", "label {sele}, '%1.2f' % q"),
    MenuEntry("vdw radius", "label {sele}, '%1.2f' % vdw"),
    SEP,
    MenuEntry("other properties", None,
              "Chimol carries no user-defined atom properties."),
    SEP,
    MenuEntry("atom identifiers", None, "", children=(
        MenuEntry("index", "label {sele}, index"),
        MenuEntry("name + index", 'label {sele}, "%s/%s" % (name, index)'),
    )),
)


# --------------------------------------------------------------------------- #
# C — Color  (pymol.menu.mol_color)
# --------------------------------------------------------------------------- #
def _color_shades(name: str, colors: tuple[str, ...]) -> MenuEntry:
    """One of PyMOL's colour-family submenus."""
    return MenuEntry(name, None, "", children=tuple(
        MenuEntry(c, f"color {c}, {{sele}}") for c in colors
    ))


COLOR_MENU: tuple[MenuEntry, ...] = (
    MenuEntry("by element", None, "", children=(
        MenuEntry("by element", "color byelement, {sele}"),
    )),
    MenuEntry("by chain", None, "", children=(
        MenuEntry("by chain", "color bychain, {sele}"),
    )),
    # PyMOL's label carries trailing spaces; kept for an exact match.
    MenuEntry("by ss  ", None, "", children=(
        MenuEntry("by secondary structure", "color by_ss, {sele}"),
    )),
    MenuEntry("by rep", None, "Chimol colours per object and selection, "
                              "not per representation."),
    MenuEntry("spectrum", None, "", children=(
        MenuEntry("by sequence", "color by_sequence, {sele}"),
        MenuEntry("spectrum", "spectrum"),
    )),
    SEP,
    MenuEntry("auto", None, "Chimol has no automatic per-object colour cycle."),
    SEP,
    _color_shades("reds", ("red", "firebrick", "salmon", "darksalmon")),
    _color_shades("greens", ("green", "forest", "limon", "palegreen")),
    _color_shades("blues", ("blue", "skyblue", "marine", "slate")),
    _color_shades("yellows", ("yellow", "paleyellow", "wheat", "sand")),
    _color_shades("magentas", ("magenta", "hotpink", "violet", "purple")),
    _color_shades("cyans", ("cyan", "palecyan", "aquamarine", "teal")),
    _color_shades("oranges", ("orange", "brightorange", "olive", "deepolive")),
    # PyMOL's own tints, from its `menu.py`. An earlier list here invented
    # `yellowtint`, which is not a PyMOL colour and so could never be applied.
    _color_shades("tints", ("wheat", "palegreen", "lightblue", "paleyellow",
                            "lightpink", "palecyan", "lightorange", "bluewhite")),
    _color_shades("grays", ("white", "gray90", "gray70", "gray50", "gray30",
                            "black")),
)


#: The five buttons, in PyMOL's order, with their menus.
OBJECT_MENUS: tuple[tuple[str, str, tuple[MenuEntry, ...]], ...] = (
    ("A", "Action", ACTION_MENU),
    ("S", "Show", SHOW_MENU),
    ("H", "Hide", HIDE_MENU),
    ("L", "Label", LABEL_MENU),
    ("C", "Color", COLOR_MENU),
)


__all__ = [
    "MenuEntry",
    "SEP",
    "ACTION_MENU",
    "SHOW_MENU",
    "HIDE_MENU",
    "LABEL_MENU",
    "COLOR_MENU",
    "OBJECT_MENUS",
    "DESTRUCTIVE",
]
