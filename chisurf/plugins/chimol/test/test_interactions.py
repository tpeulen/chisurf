"""Hydrogen-bond networks and the bump check.

The clash arithmetic is transcribed from sculpting's van der Waals term, so the
tests assert the three things a reader loses when they re-derive it: that a
hydrogen bond is *not* a clash (the pair cutoff drops by the hb allowance), that
bonded neighbours are excluded and a 1-4 pair merely softened, and that the
colour crosses from green to red exactly where `sculpt_vdw_vis_mid` and `_max`
put it.

The networks are ours rather than PyMOL's -- it has no notion of one -- so those
tests are about the grouping: what counts as connected, and what the three water
policies do to a donor-water-acceptor bridge, which is the case the whole
feature exists for.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.analysis.clashes import (
    BAD_COLOR,
    GOOD_COLOR,
    ClashCriteria,
    clash_color,
    find_clashes,
    radii_for,
)
from chimol.analysis.hbond_networks import (
    NetworkOptions,
    find_hbond_networks,
    network_colors,
)
from chimol.analysis.hbonds import HBond

_PDB = pathlib.Path(__file__).resolve().parents[4] / "test" / "data" / (
    "atomic_coordinates"
) / "pdb_files"


def _atoms(*rows) -> np.ndarray:
    """``(name, resn, resi, chain, element, xyz)`` as a structured array."""
    dtype = np.dtype([
        ("atom_name", "U4"), ("res_name", "U4"), ("res_id", "i4"),
        ("chain", "U2"), ("element", "U2"), ("xyz", "f8", 3),
    ])
    return np.array(
        [(n, r, i, c, e, tuple(v)) for n, r, i, c, e, v in rows], dtype=dtype
    )


# --------------------------------------------------------------------------- #
# Clashes
# --------------------------------------------------------------------------- #
def test_two_carbons_inside_each_other_clash():
    """The cutoff is the sum of the radii and the overlap is what is left."""
    coords = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0]])
    radii = np.array([1.7, 1.7])

    report = find_clashes(coords, radii, [])

    assert len(report.clashes) == 1
    clash = report.clashes[0]
    assert clash.cutoff == pytest.approx(3.4)
    assert clash.overlap == pytest.approx(0.4)
    # SculptDoBump's strain: |cutoff * vdw_scale - distance|.
    assert clash.strain == pytest.approx(abs(3.4 * 0.97 - 3.0))
    assert report.strain == pytest.approx(clash.strain)


def test_a_comfortable_contact_is_reported_but_costs_nothing():
    """`sculpt_vdw_vis_min` is *negative*: a pair just outside contact is drawn.

    In green, saying "this one is fine". Reading `min` as a positive threshold
    drops exactly the contacts a bump check is meant to reassure you about.
    """
    coords = np.array([[0.0, 0.0, 0.0], [3.45, 0.0, 0.0]])
    radii = np.array([1.7, 1.7])

    report = find_clashes(coords, radii, [])

    assert len(report.clashes) == 1
    assert report.clashes[0].overlap < 0
    assert report.strain == 0.0


def test_a_hydrogen_bond_is_not_a_clash():
    """Without the hb allowance every hydrogen bond reports as an overlap.

    A donor N and an acceptor O at 2.9 A are 0.15 A inside the sum of their
    radii; `sculpt_hb_overlap_base` (0.35) is what says that is a bond rather
    than a bump.
    """
    coords = np.array([[0.0, 0.0, 0.0], [2.9, 0.0, 0.0]])
    radii = np.array([1.55, 1.5])
    donors = np.array([True, False])
    acceptors = np.array([False, True])

    plain = find_clashes(coords, radii, [])
    typed = find_clashes(coords, radii, [], donors=donors, acceptors=acceptors)

    assert plain.clashes[0].overlap > 0, "the fixture is not close enough to test"
    assert plain.strain > 0
    assert typed.strain == 0.0, "the hydrogen-bond allowance did not apply"


def test_bonded_neighbours_never_clash():
    """1-2, 1-3 and 1-4 pairs are never *drawn* -- PyMOL's `ex` arms.

    Two bonded carbons are 1.5 A apart, a metre inside the sum of their radii;
    without the exclusion every bond in the structure is a clash. A 1-4 pair
    is the subtler one: PyMOL scales its cutoff by `sculpt_vdw_scale14` and
    counts its strain, but never calls `SculptCGOBump` for it, because a
    torsion the geometry already fixes is not something to draw a red line
    across -- and drawing them buries the real clashes in intra-residue haze.
    """
    coords = np.array([
        [0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.2, 1.2, 0.0], [2.9, 0.1, 0.0],
    ])
    radii = np.full(4, 1.7)
    bonds = [(0, 1), (1, 2), (2, 3)]

    report = find_clashes(coords, radii, bonds)

    assert report.clashes == [], "a bonded chain has nothing to draw"
    assert report.strain > 0, "the 1-4 pair still contributes strain"


def test_a_one_four_pair_uses_the_softer_scale():
    """`sculpt_vdw_scale14` is 0.90 against 0.97, so a 1-4 pair strains less."""
    coords = np.array([
        [0.0, 0.0, 0.0], [1.5, 0.0, 0.0], [2.2, 1.2, 0.0], [2.9, 0.1, 0.0],
    ])
    radii = np.full(4, 1.7)
    bonded = find_clashes(coords, radii, [(0, 1), (1, 2), (2, 3)])
    free = find_clashes(coords, radii, [])

    same_pair = next(c for c in free.clashes if (c.i, c.j) == (0, 3))
    assert bonded.strain < same_pair.strain


def test_the_bump_colour_runs_green_to_red_where_pymol_puts_it():
    criteria = ClashCriteria()
    assert clash_color(criteria.vis_mid - 0.01, criteria) == pytest.approx(GOOD_COLOR)
    assert clash_color(
        criteria.vis_mid + criteria.vis_max, criteria
    ) == pytest.approx(BAD_COLOR)
    half = clash_color(criteria.vis_mid + criteria.vis_max / 2, criteria)
    assert half[0] == pytest.approx(0.5 * GOOD_COLOR[0] + 0.5 * BAD_COLOR[0])


def test_the_subject_restricts_which_pairs_are_looked_at():
    """Only pairs involving the subject are looked at.

    The wizard checks one side chain against everything, not everything against
    everything -- and on a real neighbourhood that is the difference between
    fifty pairs and nine million.
    """
    coords = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [6.0, 0.0, 0.0], [9.0, 0.0, 0.0]])
    radii = np.full(4, 1.7)

    everything = find_clashes(coords, radii, [])
    just_one = find_clashes(coords, radii, [], subject=np.array([1]))

    assert len(everything.clashes) == 3
    assert {(c.i, c.j) for c in just_one.clashes} == {(0, 1), (1, 2)}


# --------------------------------------------------------------------------- #
# Networks
# --------------------------------------------------------------------------- #
def _bond(donor: int, acceptor: int) -> HBond:
    return HBond(
        donor=donor, acceptor=acceptor, hydrogen=None,
        hydrogen_xyz=np.zeros(3), distance=2.9,
    )


def test_bonds_that_share_an_atom_are_one_network():
    atoms = _atoms(
        ("N", "SER", 1, "A", "N", (0, 0, 0)),
        ("OG", "SER", 1, "A", "O", (3, 0, 0)),
        ("OD1", "ASP", 2, "A", "O", (6, 0, 0)),
        ("N", "LYS", 9, "A", "N", (20, 0, 0)),
        ("O", "GLU", 8, "A", "O", (23, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2), _bond(3, 4)]

    networks = find_hbond_networks(atoms, None, bonds=bonds)

    assert [net.size for net in networks] == [2, 1]
    assert networks[0].atoms == [0, 1, 2]
    assert len(networks[0].residues) == 2


def test_water_bridges_two_halves_or_does_not(monkeypatch):
    """The three water policies, on the case the feature exists for.

    A donor and an acceptor too far apart to bond, each bonded to the same
    ordered water: one network through the water, two lone bonds without it,
    and nothing at all when only water-to-water is asked for.
    """
    atoms = _atoms(
        ("OG", "SER", 1, "A", "O", (0, 0, 0)),
        ("O", "HOH", 500, "A", "O", (3, 0, 0)),
        ("OD1", "ASP", 2, "A", "O", (6, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2)]

    bridged = find_hbond_networks(atoms, None, bonds=bonds)
    assert [net.size for net in bridged] == [2]
    assert bridged[0].waters == 1

    without = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(waters="exclude")
    )
    assert without == []

    wire = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(waters="only")
    )
    assert wire == []


def test_a_water_wire_is_found_on_its_own():
    atoms = _atoms(
        ("O", "HOH", 1, "A", "O", (0, 0, 0)),
        ("O", "HOH", 2, "A", "O", (3, 0, 0)),
        ("O", "HOH", 3, "A", "O", (6, 0, 0)),
        ("OG", "SER", 9, "A", "O", (9, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2), _bond(2, 3)]

    wire = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(waters="only")
    )

    assert [net.size for net in wire] == [2]
    assert wire[0].waters == 3


def test_min_size_drops_the_lone_surface_contacts():
    atoms = _atoms(
        ("N", "SER", 1, "A", "N", (0, 0, 0)),
        ("OG", "SER", 1, "A", "O", (3, 0, 0)),
        ("OD1", "ASP", 2, "A", "O", (6, 0, 0)),
        ("N", "LYS", 9, "A", "N", (20, 0, 0)),
        ("O", "GLU", 8, "A", "O", (23, 0, 0)),
    )
    bonds = [_bond(0, 1), _bond(1, 2), _bond(3, 4)]

    kept = find_hbond_networks(
        atoms, None, bonds=bonds, options=NetworkOptions(min_size=2)
    )

    assert [net.size for net in kept] == [2]


def test_a_network_reports_the_chains_it_spans():
    atoms = _atoms(
        ("OG", "SER", 1, "A", "O", (0, 0, 0)),
        ("OD1", "ASP", 2, "B", "O", (3, 0, 0)),
    )
    networks = find_hbond_networks(atoms, None, bonds=[_bond(0, 1)])

    assert networks[0].spans_chains
    assert networks[0].chains == ["A", "B"]
    assert "chains A+B" in networks[0].describe()


def test_the_colours_are_stable_and_cycle():
    """A figure whose networks change colour between runs cannot be referred to."""
    assert network_colors(3) == network_colors(3)
    assert network_colors(12)[10] == network_colors(12)[0]


# --------------------------------------------------------------------------- #
# On a real structure
# --------------------------------------------------------------------------- #
def _read(name: str):
    from chisurf.core.fio.structure.coordinates import read_coordinates
    from chimol.geometry.bonds import (
        build_bond_pairs_by_element,
    )

    path = _PDB / name
    if not path.exists():
        pytest.skip(f"no {name} fixture")
    atoms = read_coordinates(
        str(path), keep_water=True, only_standard_residues=False
    )
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    bonds = build_bond_pairs_by_element(
        np.asarray(atoms["xyz"], dtype=float),
        np.asarray(atoms["radius"], dtype=float),
        elements,
    )
    return atoms, bonds


def test_a_real_protein_has_networks_and_almost_no_clashes():
    """148L: a deposited structure is refined, so its strain must be small.

    This is the test that would catch the hydrogen-bond allowance going
    missing, or the neighbour exclusion breaking -- either turns a clean
    crystal structure into hundreds of clashes.
    """
    from chimol.analysis.hbonds import type_atoms

    atoms, bonds = _read("148l.pdb")
    networks = find_hbond_networks(atoms, bonds, options=NetworkOptions(min_size=3))
    assert networks, "no hydrogen-bond networks in a 165-residue protein"
    assert networks[0].size >= 5, "the largest network is suspiciously small"

    typing = type_atoms(atoms, bonds)
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    report = find_clashes(
        np.asarray(atoms["xyz"], dtype=float),
        radii_for(elements),
        bonds,
        donors=typing.donor,
        acceptors=typing.acceptor,
        is_hydrogen=np.isin(elements, ("H", "D")),
    )
    overlapping = [c for c in report.clashes if c.overlap > 0.4]
    assert len(overlapping) < 0.05 * len(atoms), (
        f"{len(overlapping)} deep overlaps in a refined structure of "
        f"{len(atoms)} atoms -- the exclusion or the hb allowance is not applying"
    )


# --------------------------------------------------------------------------- #
# Mutagenesis
# --------------------------------------------------------------------------- #
def test_every_standard_residue_has_a_fragment_and_its_rotamers():
    """Twenty fragments, eighteen libraries -- ALA and GLY have no chi angle."""
    from chimol.analysis.residue_library import (
        FRAGMENTS,
        ROTAMERS,
    )

    assert len(FRAGMENTS) == 20
    assert set(ROTAMERS) | {"ALA", "GLY"} == set(FRAGMENTS)
    for resn, rotamers in ROTAMERS.items():
        freqs = [freq for freq, _chis in rotamers]
        assert freqs == sorted(freqs, reverse=True), f"{resn} is not sorted"
        assert all(chis for _f, chis in rotamers), f"{resn} has a chi-less rotamer"


def test_a_built_rotamer_has_the_chi_angles_it_says():
    """The whole point of the library: the built side chain *is* that rotamer."""
    from chimol.analysis.mutate import (
        _dihedral,
        build_rotamers,
    )

    backbone = {
        "N": np.array([0.0, 0.0, 0.0]),
        "CA": np.array([1.458, 0.0, 0.0]),
        "C": np.array([2.0, 1.42, 0.0]),
    }
    site = build_rotamers("ARG", backbone, hydrogens=False)
    index = {name: i for i, name in enumerate(site.names)}

    for rotamer in site.rotamers[:5]:
        for quad, angle in rotamer.chis.items():
            built = _dihedral(*(rotamer.coords[index[name]] for name in quad))
            assert built == pytest.approx(angle, abs=0.5), f"{quad} is off"


def test_the_backbone_is_kept_exactly():
    """The side chain grows out of the existing backbone; the chain does not move."""
    from chimol.analysis.mutate import build_rotamers

    backbone = {
        "N": np.array([3.1, -1.2, 0.7]),
        "CA": np.array([4.4, -0.7, 1.1]),
        "C": np.array([5.3, -1.8, 1.7]),
        "O": np.array([6.5, -1.6, 1.9]),
    }
    site = build_rotamers("TYR", backbone, hydrogens=False)
    index = {name: i for i, name in enumerate(site.names)}

    for atom, xyz in backbone.items():
        assert site.rotamers[0].coords[index[atom]] == pytest.approx(xyz)
    # And the bond the rotamer angles are measured against is a real bond.
    ca_cb = np.linalg.norm(
        site.rotamers[0].coords[index["CA"]] - site.rotamers[0].coords[index["CB"]]
    )
    assert ca_cb == pytest.approx(1.53, abs=0.06), f"CA-CB is {ca_cb:.3f} A"


def test_a_residue_without_a_backbone_is_refused():
    """PyMOL's wizard requires N, C and O before it offers anything."""
    from chimol.analysis.mutate import build_rotamers

    with pytest.raises(ValueError):
        build_rotamers("LEU", {"CA": np.zeros(3)})


def test_hydrogens_follow_the_structure():
    """`hyd auto`: a crystal structure with no hydrogens gets none back.

    One residue drawn with hydrogens and 164 without reads as a rendering
    fault, and the fragments all carry them.
    """
    from chimol.analysis.mutate import build_rotamers

    backbone = {
        "N": np.zeros(3), "CA": np.array([1.458, 0.0, 0.0]),
        "C": np.array([2.0, 1.42, 0.0]),
    }
    with_h = build_rotamers("SER", backbone, hydrogens=True)
    without = build_rotamers("SER", backbone, hydrogens=False)

    assert any(e.upper() == "H" for e in with_h.elements)
    assert not any(e.upper() == "H" for e in without.elements)
    assert without.rotamers[0].coords.shape[0] == len(without.names)


def test_rebuilding_a_residue_as_itself_reproduces_it(tmp_path):
    """The validation that says the *geometry* is right rather than the choice.

    Rebuilt as itself, one of the library's rotamers has to land close to the
    deposited side chain -- the library is a set of cluster means, so 0.5 A is
    the resolution of the answer, not an error. Which rotamer the bump check
    picks is a separate question: the least strained one is often not the
    crystallographic one, and PyMOL has exactly the same property, which is why
    its wizard shows the list.
    """
    from chimol.analysis.mutate import mutate_residue

    atoms, _bonds = _read("148l.pdb")
    resid = np.asarray(atoms["res_id"], dtype=int)
    resn = np.array([str(r).strip() for r in atoms["res_name"]])
    names = np.array([str(n).strip() for n in atoms["atom_name"]])
    xyz = np.asarray(atoms["xyz"], dtype=float)

    deviations = []
    for target in range(3, 40):
        rows = np.nonzero(resid == target)[0]
        if not len(rows) or resn[rows[0]] in ("HOH", "GLY"):
            continue
        try:
            result = mutate_residue(atoms, rows, resn[rows[0]])
        except (KeyError, ValueError):
            continue
        index = {name: i for i, name in enumerate(result.site.names)}
        best = None
        for rotamer in result.site.rotamers:
            errors = [
                float(np.linalg.norm(rotamer.coords[index[names[row]]] - xyz[row]))
                for row in rows
                if names[row] not in ("N", "CA", "C", "O") and names[row] in index
            ]
            if errors:
                best = min(best, float(np.mean(errors))) if best else float(np.mean(errors))
        if best is not None:
            deviations.append(best)

    assert len(deviations) > 20, "not enough residues were rebuilt to mean anything"
    assert float(np.mean(deviations)) < 0.8, (
        f"rebuilt side chains average {np.mean(deviations):.2f} A from the "
        "deposited ones -- the fragment fit or the chi rotation is wrong"
    )
    assert sum(1 for d in deviations if d < 1.0) >= 0.85 * len(deviations)


# --------------------------------------------------------------------------- #
# The wizard panel
# --------------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def wizard_cmd(qapp, tmp_path):
    """A loaded window with the command layer wired to it."""
    import shutil

    from chimol.hosts.qt.window import MolViewPluginWindow
    from chimol.commands.command import Cmd

    src = _PDB / "148l.pdb"
    if not src.is_file():
        pytest.skip("no 148l fixture")
    pdb = tmp_path / "148l.pdb"
    shutil.copyfile(src, pdb)

    window = MolViewPluginWindow()
    window._load_structure_from_path(pdb, name="148l")
    cmd = Cmd(window)
    errors: list[str] = []
    cmd.set_error_callback(errors.append)
    cmd.set_message_callback(lambda _m: None)
    cmd._errors = errors
    # Not closed: tearing down a QOpenGLWidget inside pytest aborts the
    # interpreter in this environment, which takes the whole run with it. The
    # window is left to the process, as the other window fixtures here do.
    return cmd, window


def _panel(window):
    gui = window.viewer.view._internal_gui
    return [(row.kind, row.label) for row in gui.wizard_rows]


def _residue_name(window, resi: int) -> str:
    entry = next(
        e for e in window.viewer.objects.values() if e.name == "148l"
    )
    rows = np.nonzero(np.asarray(entry.state.atoms["res_id"], dtype=int) == resi)[0]
    return str(entry.state.atoms["res_name"][rows[0]]).strip()


def _preview(window):
    """The `mutation` object PyMOL's wizard creates, or ``None``."""
    for entry in window.viewer.objects.values():
        if entry.name == "mutation":
            return entry
    return None


def test_the_wizard_panel_is_pymols_shape(wizard_cmd):
    """A banner, pop-ups carrying their value, and buttons. Nothing else.

    PyMOL's `get_panel` has exactly three row codes and every wizard it ships
    is built from them; a panel that grows a fourth kind is a panel that has
    stopped being the simplest thing that works.
    """
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")

    rows = _panel(window)
    assert rows[0] == ("title", "Mutagenesis")
    assert {kind for kind, _label in rows} <= {"title", "menu", "button"}
    assert ("button", "Apply") in rows and ("button", "Done") in rows
    assert any("THR`54" in label for _k, label in rows), "the residue is not named"


def test_choosing_a_target_builds_one_state_per_rotamer(wizard_cmd):
    """PyMOL's `do_library`: an object called `mutation`, a state per rotamer.

    And the source structure untouched -- the preview is a *different object*,
    which is what makes Clear and Done free and stepping a frame change rather
    than a rebuild.
    """
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    cmd.do("wizard target, TRP")

    assert cmd._errors == []
    assert _residue_name(window, 54) == "THR", "the source was modified by a preview"
    preview = _preview(window)
    assert preview is not None, "no `mutation` object was created"
    frames = np.asarray(preview.state.frames)
    assert frames.ndim == 3 and frames.shape[0] == len(window.viewer._wizard.scores)
    labels = [label for _kind, label in _panel(window)]
    assert any("rotamer" in label for label in labels)
    assert any("strain" in label for label in labels)


def test_stepping_is_a_state_change_not_a_rebuild(wizard_cmd):
    """The rotamer on screen changes; nothing is built and nothing is touched."""
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    cmd.do("wizard target, TRP")
    state = window.viewer._wizard
    before = state.rotamer
    frames_before = np.asarray(_preview(window).state.frames).copy()

    cmd.do("wizard rotamer, next")

    state = window.viewer._wizard
    assert state.rotamer != before
    frames_after = np.asarray(_preview(window).state.frames)
    assert np.array_equal(frames_before, frames_after), (
        "the states were rebuilt -- stepping must only change which one is shown"
    )
    shown = np.asarray(_preview(window).state.coords)
    assert shown.shape[0] == frames_after.shape[1]


def test_the_wizard_never_moves_the_camera(wizard_cmd):
    """You framed the residue; previewing a rotamer must not take that away.

    PyMOL turns `auto_zoom` off around `do_library` for this. chimol has more
    ways to lose the framing than that flag covers -- adding an object moves
    the scene centre, and a state change re-derives the radius -- and the
    symptom is not subtle once it is on screen: measured, the protein receded
    until the viewport read as black with a few sticks in it, and every step
    took it further. The view is therefore saved and put back around both the
    build and the step.
    """
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    before = list(window.viewer.get_view_state())

    cmd.do("wizard target, TRP")
    after_build = list(window.viewer.get_view_state())
    assert after_build == pytest.approx(before), "building the rotamers moved the camera"

    cmd.do("wizard rotamer, next")
    cmd.do("wizard rotamer, next")
    after_steps = list(window.viewer.get_view_state())
    assert after_steps == pytest.approx(before), "stepping a rotamer moved the camera"


def test_clear_drops_the_preview_object(wizard_cmd):
    """There is nothing to undo -- only an object to delete."""
    cmd, window = wizard_cmd
    before = _residue_name(window, 54)

    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    cmd.do("wizard target, TRP")
    assert _preview(window) is not None

    cmd.do("wizard clear")

    assert _preview(window) is None
    assert _residue_name(window, 54) == before


def test_done_without_apply_leaves_the_structure_alone(wizard_cmd):
    cmd, window = wizard_cmd
    before = _residue_name(window, 54)

    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    cmd.do("wizard target, ALA")
    cmd.do("wizard done")

    assert _residue_name(window, 54) == before
    assert _preview(window) is None, "the preview object outlived the wizard"
    assert _panel(window) == [], "the panel outlived the wizard"
    assert window.viewer._wizard is None


def test_apply_keeps_it(wizard_cmd):
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    cmd.do("wizard target, ALA")
    cmd.do("wizard apply")

    assert _residue_name(window, 54) == "ALA"
    assert _preview(window) is None
    assert window.viewer._wizard is None


def test_the_residue_menu_offers_the_twenty_by_class(wizard_cmd):
    """Grouped as PyMOL's own menu groups them, not alphabetically."""
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")

    entries = window.viewer._wizard.menu("residue")
    names = [e.label for e in entries if not e.is_separator]
    assert len(names) == 20
    assert names[:3] == ["ALA", "GLY", "PRO"]
    assert any(e.is_separator for e in entries), "the classes are not separated"
    assert all(e.command.startswith("wizard target,") for e in entries if e.command)


def test_the_bump_check_can_be_turned_off(wizard_cmd):
    cmd, window = wizard_cmd
    cmd.do("select resi 54")
    cmd.do("wizard mutagenesis")
    cmd.do("wizard target, TRP")
    assert any(
        key.startswith("_bump_check") for key in window.viewer.measurements
    ), "the bump check drew nothing"

    cmd.do("wizard bump, toggle")

    assert not any(
        key.startswith("_bump_check") for key in window.viewer.measurements
    )
    assert any("off" in label for _k, label in _panel(window))
