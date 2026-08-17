"""Atom labels and PyMOL's label expression language.

``cmd.label`` does not take a template — it takes a **Python expression**
evaluated per atom with that atom's properties in scope, which is why PyMOL's
Label menu is full of entries like ``"%s-%s" % (resn, resi)``. Anything less is
not the same feature: half the usefulness of labels is computing them.

Reference: ``pymol/menu.py:mol_labels`` for the expressions, and PyMOL's
documented property names for the namespace.
"""

from __future__ import annotations

import numpy as np
import pytest

from chimol.analysis.labels import (
    ATOM_PROPERTIES,
    evaluate_labels,
    label_expression,
)


def _atoms() -> np.ndarray:
    dtype = [
        ("atom_name", "U4"), ("res_name", "U4"), ("chain", "U2"),
        ("res_id", np.int64), ("element", "U2"), ("bfactor", float),
        ("occupancy", float), ("radius", float), ("i", np.int64),
    ]
    return np.array(
        [
            ("N", "ALA", "A", 10, "N", 12.345, 1.0, 1.55, 0),
            ("CA", "ALA", "A", 10, "C", 20.5, 0.5, 1.70, 1),
            ("O", "HOH", "B", 99, "O", 40.0, 1.0, 1.52, 2),
        ],
        dtype=dtype,
    )


_XYZ = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])


# --------------------------------------------------------------------------- #
# The expression language
# --------------------------------------------------------------------------- #
def test_a_plain_property_labels_every_atom():
    idx, texts = evaluate_labels(_atoms(), _XYZ, "name")
    assert idx.tolist() == [0, 1, 2]
    assert texts == ["N", "CA", "O"]


def test_pymols_own_residue_expression_works_verbatim():
    """The expression straight out of PyMOL's Label menu."""
    idx, texts = evaluate_labels(
        _atoms(), _XYZ, '"%s-%s" % (resn, resi)', np.array([True, False, False])
    )
    assert texts == ["ALA-10"]


def test_oneletter_is_available():
    _, texts = evaluate_labels(
        _atoms(), _XYZ, "oneletter + resi", np.array([True, False, False])
    )
    assert texts == ["A10"]


def test_an_unknown_residue_gets_x_rather_than_failing():
    atoms = _atoms()
    atoms["res_name"][0] = "XYZ"
    _, texts = evaluate_labels(
        atoms, _XYZ, "oneletter", np.array([True, False, False])
    )
    assert texts == ["X"]


def test_numeric_formatting_works():
    _, texts = evaluate_labels(
        _atoms(), _XYZ, "'%1.2f' % b", np.array([True, False, False])
    )
    assert texts == ["12.35"]


def test_coordinates_are_in_scope():
    _, texts = evaluate_labels(
        _atoms(), _XYZ, "'%.1f' % x", np.array([True, False, False])
    )
    assert texts == ["1.0"]


def test_resi_is_a_string_because_insertion_codes_exist():
    """PyMOL gives `resi` as a string; `oneletter + resi` depends on it."""
    _, texts = evaluate_labels(
        _atoms(), _XYZ, "resi + '!'", np.array([True, False, False])
    )
    assert texts == ["10!"]


def test_an_empty_expression_clears():
    idx, texts = evaluate_labels(_atoms(), _XYZ, "")
    assert idx.size == 0 and texts == []


def test_a_selection_limits_which_atoms_are_labelled():
    idx, _ = evaluate_labels(
        _atoms(), _XYZ, "name", np.array([False, True, True])
    )
    assert idx.tolist() == [1, 2]


def test_a_missing_field_still_resolves():
    """A structure without b-factors must not fail every expression using one."""
    bare = np.array(
        [("CA", 1)], dtype=[("atom_name", "U4"), ("res_id", np.int64)]
    )
    _, texts = evaluate_labels(bare, _XYZ[:1], "'%s/%s' % (name, b)")
    assert texts == ["CA/0.0"]


def test_one_bad_atom_does_not_cost_the_others_their_labels():
    """An expression that fails on a single residue skips it and continues."""
    _, texts = evaluate_labels(_atoms(), _XYZ, "1.0 / (b - 20.5)")
    assert len(texts) == 2      # the CA divides by zero and is skipped


def test_a_syntax_error_is_raised_because_it_is_wrong_everywhere():
    with pytest.raises(SyntaxError):
        evaluate_labels(_atoms(), _XYZ, "resn +")


# --------------------------------------------------------------------------- #
# The expression is sandboxed
# --------------------------------------------------------------------------- #
def test_builtins_are_not_reachable():
    """A label expression arrives from a menu or a script; it must not open files."""
    _, texts = evaluate_labels(_atoms(), _XYZ, "open")
    assert texts == []          # NameError per atom, so nothing is labelled


def test_imports_are_not_reachable():
    _, texts = evaluate_labels(_atoms(), _XYZ, "__import__('os').getcwd()")
    assert texts == []


def test_the_formatting_helpers_that_are_allowed_still_work():
    _, texts = evaluate_labels(
        _atoms(), _XYZ, "str(round(b, 1))", np.array([True, False, False])
    )
    assert texts == ["12.3"]


# --------------------------------------------------------------------------- #
# Menu expressions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kind", ["clear", "residues", "residues (oneletter)", "chains", "atom name",
             "element symbol", "residue name", "one letter code",
             "residue identifier", "chain identifier", "b-factor", "occupancy",
             "vdw radius"],
)
def test_every_menu_expression_evaluates(kind):
    expr = label_expression(kind)
    idx, texts = evaluate_labels(_atoms(), _XYZ, expr)
    if not expr:
        assert idx.size == 0
    else:
        assert len(texts) == 3, f"{kind}: {expr!r} produced {texts}"


def test_the_property_names_are_pymols():
    for name in ("name", "resn", "resi", "chain", "elem", "b", "q", "vdw",
                 "index"):
        assert name in ATOM_PROPERTIES


# --------------------------------------------------------------------------- #
# In the viewer, and through the command
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def loaded(qapp):
    import pathlib

    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import MolView

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, pdb), name="148l",
        source_path=str(pdb),
    )

    class _Window:
        viewer = view

    cmd = Cmd(_Window())
    messages, errors = [], []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def _label_objects(view):
    scene = view.get_current_scene()
    return [] if scene is None else [o for o in scene.objects if "label:" in o.id]


def test_the_command_puts_text_in_the_scene(loaded):
    cmd, view, _, errors = loaded
    cmd.do('label name CA and resi 10-12, "%s-%s" % (resn, resi)')
    assert errors == []
    objects = _label_objects(view)
    assert len(objects) == 3
    texts = sorted(o.geometry.meta["labels"][0] for o in objects)
    assert all("-" in t for t in texts)


def test_labels_are_drawn_as_an_overlay(loaded):
    """They have to survive depth-testing against the geometry they annotate."""
    cmd, view, _, _ = loaded
    cmd.do("label name CA and resi 10, resn")
    assert all(o.render_mode == "overlay" for o in _label_objects(view))


def test_an_empty_expression_clears_through_the_command(loaded):
    cmd, view, messages, _ = loaded
    cmd.do("label name CA and resi 10-12, resn")
    assert _label_objects(view)
    cmd.do('label name CA, ""')
    assert _label_objects(view) == []
    assert "Cleared" in messages[-1]


def test_hiding_labels_keeps_the_text(loaded):
    """`hide labels` must not throw the labels away, as PyMOL's does not."""
    cmd, view, _, _ = loaded
    cmd.do("label name CA and resi 10-12, resn")
    view.set_labels_visible(False)
    assert _label_objects(view) == []
    view.set_labels_visible(True)
    assert len(_label_objects(view)) == 3


def test_relabelling_replaces_rather_than_duplicates(loaded):
    cmd, view, _, _ = loaded
    cmd.do("label name CA and resi 10, resn")
    cmd.do("label name CA and resi 10, elem")
    objects = _label_objects(view)
    assert len(objects) == 1
    assert objects[0].geometry.meta["labels"][0] == "C"


def test_a_bad_expression_is_reported(loaded):
    cmd, _, _, errors = loaded
    cmd.do("label name CA, resn +")
    assert errors and "could not parse" in errors[-1]


def test_labelling_nothing_is_reported(loaded):
    cmd, _, _, errors = loaded
    cmd.do("label resi 99999, resn")
    assert errors


def test_the_label_menu_is_no_longer_disabled():
    """It was greyed out in its entirety because there was no label support."""
    from chimol.chrome.object_menus import LABEL_MENU

    live = [
        e for e in LABEL_MENU
        if not e.is_separator and (e.command or e.children)
    ]
    assert len(live) >= 15
