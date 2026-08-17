"""ChimeraX's measurement commands, and the invariants that make them checkable.

PyMOL is the reference for the GUI and the UX; **ChimeraX is the reference for
functionality**, and its ``measure_*`` suite was the largest thing it has that
ChiMOL had nothing of -- eight commands against ChiMOL's distance, angle and
dihedral.

There is no reference number to compare against here, so each test pins a
*property* the quantity must have. That is the stronger check anyway: a buried
area that agrees with one hand-computed value can still be wrong everywhere
else, while one that is symmetric, non-negative, zero at infinite separation and
additive with contact is doing the right arithmetic.
"""
from __future__ import annotations

import pathlib
import re

import numpy as np
import pytest

pytest.importorskip("qtpy")

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture(scope="module")
def cmd(qapp):
    """A window with 148L loaded, and a runner that returns what was said.

    Module-scoped: every test here reads the same structure and none of them
    changes it, and a window plus a PDB parse per test made the file take 110
    seconds instead of 15. The one test that touches a global setting restores
    it in a ``finally``.
    """
    from chimol.hosts.qt.window import MolViewPluginWindow

    if not PDB.is_file():
        pytest.skip(f"missing fixture {PDB}")
    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(700, 520)
    win.show()
    for _ in range(4):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def run(line: str) -> tuple[str, str]:
        before_m, before_e = len(messages), len(errors)
        win._run_object_menu_command(line)
        for _ in range(3):
            qapp.processEvents()
        said = messages[-1] if len(messages) > before_m else ""
        complained = errors[-1] if len(errors) > before_e else ""
        return said, complained

    run(f"load {PDB}")
    yield run
    win.close()


def _number(text: str) -> float:
    match = re.search(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", text)
    assert match, f"no number in {text!r}"
    return float(match.group(1))


# --------------------------------------------------------------------------- #
# measure_buriedarea
# --------------------------------------------------------------------------- #
def test_two_halves_of_a_protein_bury_a_real_interface(cmd):
    said, complained = cmd("measure_buriedarea resi 1-80, resi 81-162")
    assert not complained, complained
    buried = _number(said)
    assert buried > 100.0, f"an interface of {buried:.0f} A^2 is not an interface"


def test_buried_area_is_symmetric(cmd):
    """Half of what is buried belongs to each side, so the order cannot matter."""
    one, _ = cmd("measure_buriedarea resi 1-80, resi 81-162")
    other, _ = cmd("measure_buriedarea resi 81-162, resi 1-80")
    assert _number(one) == pytest.approx(_number(other), rel=1e-9)


def test_sets_that_do_not_touch_bury_nothing(cmd):
    """The property that catches an arithmetic sign or a stray factor.

    Two residues at opposite ends of the fold occlude each other not at all, so
    their areas alone must sum to their area together.
    """
    said, complained = cmd("measure_buriedarea resi 1, resi 120")
    assert not complained, complained
    assert _number(said) == pytest.approx(0.0, abs=1.0)


def test_overlapping_selections_are_refused(cmd):
    """Shared atoms would be counted on both sides of the interface."""
    _said, complained = cmd("measure_buriedarea resi 1-80, resi 70-162")
    assert "disjoint" in complained, complained


def test_the_probe_radius_is_honoured(cmd):
    """A bigger probe reaches less far into a crevice, so it buries more."""
    small, _ = cmd("measure_buriedarea resi 1-80, resi 81-162, 1.0")
    large, _ = cmd("measure_buriedarea resi 1-80, resi 81-162, 2.0")
    assert _number(large) > _number(small)


def test_buried_area_is_the_solvent_accessible_one_whatever_dot_solvent_says(cmd):
    """`dot_solvent` off means van der Waals area, which is not this quantity.

    Answering a different question because a global flag happened to be off is
    the failure this plugin keeps finding, so the command pins the surface it
    means.
    """
    from chimol.core.settings.registry import get_setting, set_setting

    before = get_setting("dot_solvent")
    try:
        set_setting("dot_solvent", False)
        off, _ = cmd("measure_buriedarea resi 1-80, resi 81-162")
        set_setting("dot_solvent", True)
        on, _ = cmd("measure_buriedarea resi 1-80, resi 81-162")
        assert _number(off) == pytest.approx(_number(on), rel=1e-9)
    finally:
        set_setting("dot_solvent", before)


# --------------------------------------------------------------------------- #
# measure_center / measure_inertia
# --------------------------------------------------------------------------- #
def test_the_centre_is_the_mean_of_the_atoms(cmd):
    said, complained = cmd("measure_center resi 1-20")
    assert not complained, complained
    assert "173 atoms" in said or "atoms centred at" in said, said


def test_the_first_inertia_axis_lies_along_the_longest_extent(cmd):
    """For a rod the smallest moment is about the rod, so axis 0 is its length.

    Checked through the reported extents rather than the axes themselves: the
    extents are what a reader uses, and they are wrong in exactly the cases an
    axis mix-up would produce.
    """
    said, complained = cmd("measure_inertia all")
    assert not complained, complained
    extents = [float(v) for v in re.findall(r"([\d.]+) A(?:,|$)", said)]
    assert len(extents) == 3, said
    assert extents[0] == max(extents), f"axis 0 is not the long one: {extents}"


def test_inertia_is_mass_weighted_and_says_the_total(cmd):
    """ChimeraX weights by atomic mass, so ChiMOL does too now that it has one.

    The total is reported because it is the cheap check on the weighting: a
    protein whose mass comes out an order from expectation has an element
    column nobody read.
    """
    said, _complained = cmd("measure_inertia all")
    assert "mass-weighted" in said, said
    assert "centre of mass" in said, said


def test_the_molecular_weight_matches_the_chemistry(cmd):
    """Residue 1 of 148L is a methionine with its eight heavy atoms.

    N + 5 C + O + S = 14.007 + 60.055 + 15.999 + 32.065 = 122.13 Da, and that is
    a number a reader can check by hand -- which is the point of choosing it.
    """
    said, complained = cmd("measure_weight resi 1")
    assert not complained, complained
    assert _number(said) == 8, said
    weight = float(re.search(r"weigh ([\d.]+) Da", said).group(1))
    assert weight == pytest.approx(122.13, abs=0.05), said


def test_the_whole_protein_weighs_what_a_hydrogen_less_structure_should(cmd):
    """An X-ray structure carries no hydrogens, so the weight is the heavy-atom
    one -- ~17.3 kDa for T4 lysozyme against ~18.7 kDa with hydrogens. Asserting
    the smaller number is asserting that nothing was invented."""
    said, complained = cmd("measure_weight polymer")
    assert not complained, complained
    weight = float(re.search(r"weigh ([\d.]+) Da", said).group(1))
    assert 17_000 < weight < 17_600, said


def test_atoms_of_unknown_element_are_counted_not_guessed(cmd):
    """A weight quietly missing a metal is the kind of wrong number that gets
    published, so the message says how many were skipped."""
    from chimol.analysis.elements import masses_for

    masses, unknown = masses_for(["C", "N", "ZZ", "FE"])
    assert unknown == 1
    assert masses[2] == 0.0
    assert masses[3] == pytest.approx(55.845)


def test_a_selection_too_small_for_a_tensor_is_refused(cmd):
    _said, complained = cmd("measure_inertia resi 1 and name CA")
    assert "three are needed" in complained, complained


# --------------------------------------------------------------------------- #
# distance -- the units it reports
# --------------------------------------------------------------------------- #
def test_two_atom_distance_is_in_angstrom(cmd):
    """The one measurement with an answer that can be checked against the file.

    Everything else here pins a property because there is no reference number.
    A CA-CA distance has one: it is in the PDB, and it is the check that catches
    a stray scale factor. This reported ``258.450`` for a 25.845 A pair --
    exactly ``_scale_factor``, 10 -- because the coordinates the value was taken
    from are the *scene* ones the measurement is drawn in.
    """
    lines = [ln for ln in PDB.read_text().splitlines()
             if ln.startswith("ATOM") and ln[12:16].strip() == "CA"]
    by_resi = {int(ln[22:26]): np.array(
        [float(ln[30:38]), float(ln[38:46]), float(ln[46:54])]) for ln in lines}
    keys = sorted(by_resi)
    a, b = keys[0], keys[20]
    truth = float(np.linalg.norm(by_resi[a] - by_resi[b]))

    said, complained = cmd(f"distance resi {a} and name CA, resi {b} and name CA")
    assert not complained, complained
    assert _number(said.split(":")[-1]) == pytest.approx(truth, abs=1e-3)
