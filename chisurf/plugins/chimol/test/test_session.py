"""Saving and restoring a whole session.

A figure in progress is a session, not a PDB file plus a note about what was
typed, so this has to bring back *everything*: objects, their representations and
colours, groups and whether they are collapsed, the camera, the named scenes and
the display settings.

Two design points are pinned deliberately because both were bugs first:

* the object field list is **derived from the state dataclass**. A hand-kept list
  of 53 fields drifts the first time one is added, and the drift is silent -- the
  session saves, reloads, and quietly lacks whatever was new. The bond-edit test
  is the guard: that field was added by separate work and must survive without
  anyone naming it here.
* the camera is restored **after** the GUI refresh. Rebuilding the object panel
  re-zooms, which replaced the saved distance and clip planes with ones computed
  from the bounding sphere. Rotation and pivot survived, so the view looked
  restored while the framing was wrong -- a difference of three numbers out of
  eighteen, and invisible unless compared element by element.
"""

from __future__ import annotations

import json
import pathlib
import zipfile

import numpy as np
import pytest

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _new_window(qapp):
    """A window on 148L, with the shared command layer pointed at it.

    Callbacks are wired **after** construction on purpose: a window rebinds the
    shared command layer's output to its own console when it is built, so a test
    that set them earlier would silently stop hearing anything.
    """
    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(1000, 700)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win._load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    return win, shared, do, messages, errors


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    win, shared, do, messages, errors = _new_window(qapp)
    yield win, shared, do, messages, errors
    win.close()


def _furnish(do):
    """Build a session worth saving: reps, colours, a group, a scene."""
    for line in (
        "hide everything",
        "show cartoon, polymer",
        "show spheres, organic",
        "spectrum count, rainbow, polymer",
        "create lig, organic",
        "group things, lig",
        "group things, close",
        "orient",
        "zoom",
        "scene base, store",
    ):
        do(line)


def _snapshot(viewer, shared):
    return {
        "objects": [o["name"] for o in viewer.list_objects()],
        "groups": viewer.group_names(),
        "open": {g: viewer.is_group_open(g) for g in viewer.group_names()},
        "view": [float(x) for x in viewer.get_view_state()],
        "n_atoms": len(viewer._atoms),
        "cartoon": bool(viewer._show_cartoon),
        "bonds": len(viewer.bond_list()),
        "scenes": shared._scene_store.names(),
    }


# --------------------------------------------------------------------------- #
# Round trip
# --------------------------------------------------------------------------- #
def test_a_session_round_trips(session, qapp, tmp_path):
    win, shared, do, _messages, errors = session
    _furnish(do)
    before = _snapshot(win.viewer, shared)
    colours_before = np.asarray(win.viewer._colors_per_ca).copy()

    path = tmp_path / "s.cms"
    do(f"session_save {path}")
    assert errors == []
    assert path.exists()

    win2, shared2, do2, _m2, errors2 = _new_window(qapp)
    try:
        do2(f"session_load {path}")
        assert errors2 == []
        after = _snapshot(win2.viewer, shared2)
        for key in before:
            assert after[key] == before[key], f"{key} did not round trip"
        colours_after = np.asarray(win2.viewer._colors_per_ca)
        assert colours_after.shape == colours_before.shape
        assert np.allclose(colours_after, colours_before)
    finally:
        win2.close()


def test_the_camera_survives_the_panel_refresh(session, qapp, tmp_path):
    """All eighteen floats, not just the rotation.

    The distance (slot 11) and the clip planes (15, 16) were the ones lost, and
    they are lost *after* a successful restore, by the GUI refresh that follows.
    """
    win, shared, do, _messages, _errors = session
    _furnish(do)
    view_before = [float(v) for v in win.viewer.get_view_state()]

    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    win2, _shared2, do2, _m2, _e2 = _new_window(qapp)
    try:
        do2(f"session_load {path}")
        view_after = [float(v) for v in win2.viewer.get_view_state()]
        assert len(view_after) == 18
        for index, (a, b) in enumerate(zip(view_before, view_after)):
            assert a == pytest.approx(b, abs=1e-4), f"view slot {index} differs"
    finally:
        win2.close()


def test_a_restored_session_actually_draws(session, qapp, tmp_path):
    """State restored but no geometry would be the same class of bug as a mask
    set without its flag: everything looks right and nothing is on screen."""
    win, shared, do, _messages, _errors = session
    _furnish(do)
    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    win2, _shared2, do2, _m2, _e2 = _new_window(qapp)
    try:
        do2(f"session_load {path}")
        scene = win2.viewer.get_current_scene()
        assert scene.objects, "the restored session drew nothing"
        verts = sum(
            len(o.geometry.positions)
            for o in scene.objects
            if o.geometry.positions is not None
        )
        assert verts > 1000
    finally:
        win2.close()


def test_manual_bond_edits_survive(session, qapp, tmp_path):
    """The guard on deriving the field list from the dataclass.

    ``bond_edits`` was added by separate work and is named nowhere in the session
    code. If the field list were hand-kept, this is what would silently vanish.
    """
    win, shared, do, _messages, errors = session
    viewer = win.viewer
    n = int(np.asarray(viewer._all_atom_coords).shape[0])
    i, j = 0, n - 1
    assert (i, j) not in {tuple(sorted(map(int, p))) for p in viewer.bond_list()}
    do(f"bond index {i + 1}, index {j + 1}, 2")
    assert errors == []

    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    win2, _shared2, do2, _m2, _e2 = _new_window(qapp)
    try:
        do2(f"session_load {path}")
        restored = win2.viewer
        keys = {tuple(sorted(map(int, p))) for p in restored.bond_list()}
        assert (i, j) in keys, "the manual bond did not survive the session"
        assert restored.bond_order(i, j) == 2, "the bond order did not survive"
    finally:
        win2.close()


def test_group_collapse_state_survives(session, qapp, tmp_path):
    win, shared, do, _messages, _errors = session
    _furnish(do)
    assert win.viewer.is_group_open("things") is False
    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    win2, _shared2, do2, _m2, _e2 = _new_window(qapp)
    try:
        do2(f"session_load {path}")
        assert win2.viewer.group_names() == ["things"]
        assert win2.viewer.is_group_open("things") is False
    finally:
        win2.close()


# --------------------------------------------------------------------------- #
# Extension dispatch
# --------------------------------------------------------------------------- #
def test_save_routes_a_session_extension(session, tmp_path):
    """`save figure.pse` is what a PyMOL user types."""
    win, shared, do, messages, errors = session
    path = tmp_path / "figure.pse"
    do(f"save {path}")
    assert errors == []
    assert path.exists() and zipfile.is_zipfile(path)


def test_saving_to_pse_says_it_is_not_pymols_format(session, tmp_path):
    """A file PyMOL cannot open should say so when written, not when opened."""
    win, shared, do, messages, _errors = session
    do(f"save {tmp_path / 'figure.pse'}")
    assert any("PyMOL cannot read it" in m for m in messages)


def test_load_routes_a_session_extension(session, qapp, tmp_path):
    win, shared, do, _messages, errors = session
    _furnish(do)
    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    win2, _shared2, do2, _m2, errors2 = _new_window(qapp)
    try:
        do2(f"load {path}")
        assert errors2 == []
        assert [o["name"] for o in win2.viewer.list_objects()] == ["148l", "lig"]
    finally:
        win2.close()


def test_a_missing_suffix_becomes_a_session_file(session, tmp_path):
    win, shared, do, _messages, errors = session
    do(f"session_save {tmp_path / 'noext'}")
    assert errors == []
    assert (tmp_path / "noext.cms").exists()


# --------------------------------------------------------------------------- #
# Refusing what it cannot read, by name
# --------------------------------------------------------------------------- #
def test_a_pymol_pse_is_named_not_called_corrupt(session, tmp_path):
    """The mistake a PyMOL user will actually make.

    A real ``.pse`` is a pickle; reporting "could not read" would send someone
    looking for a damaged file instead of telling them the formats differ.
    """
    win, shared, do, _messages, errors = session
    fake = tmp_path / "frompymol.pse"
    fake.write_bytes(b"\x80\x04\x95pretend this is a pickle")
    do(f"session_load {fake}")
    assert errors and "PyMOL" in errors[-1]


def test_a_file_that_is_not_a_session_says_so(session, tmp_path):
    win, shared, do, _messages, errors = session
    plain = tmp_path / "notes.cms"
    plain.write_text("just some text")
    do(f"session_load {plain}")
    assert errors and "not a chimol session" in errors[-1]


def test_a_zip_without_a_manifest_says_so(session, tmp_path):
    win, shared, do, _messages, errors = session
    bogus = tmp_path / "bogus.cms"
    with zipfile.ZipFile(bogus, "w") as archive:
        archive.writestr("hello.txt", "nothing useful")
    do(f"session_load {bogus}")
    assert errors and "manifest" in errors[-1]


def test_a_newer_session_version_is_refused_with_the_number(session, tmp_path):
    win, shared, do, _messages, errors = session
    from chimol.renderer.session import SESSION_VERSION

    future = tmp_path / "future.cms"
    with zipfile.ZipFile(future, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"version": SESSION_VERSION + 5, "objects": []}),
        )
    do(f"session_load {future}")
    assert errors and str(SESSION_VERSION + 5) in errors[-1]


def test_loading_a_missing_file_says_which(session, tmp_path):
    win, shared, do, _messages, errors = session
    do(f"session_load {tmp_path / 'nope.cms'}")
    assert errors and "no such file" in errors[-1]


def test_both_commands_need_a_filename(session):
    win, shared, do, _messages, errors = session
    for line in ("session_save", "session_load", "session_info"):
        errors.clear()
        do(line)
        assert errors and "Usage" in errors[-1], line


# --------------------------------------------------------------------------- #
# session_info
# --------------------------------------------------------------------------- #
def test_session_info_reports_without_loading(session, tmp_path):
    win, shared, do, messages, errors = session
    _furnish(do)
    path = tmp_path / "s.cms"
    do(f"session_save {path}")
    before = [o["name"] for o in win.viewer.list_objects()]

    messages.clear()
    do(f"session_info {path}")
    assert errors == []
    assert messages and "2 objects" in messages[-1]
    assert "1 scenes" in messages[-1]
    # Nothing was disturbed by asking.
    assert [o["name"] for o in win.viewer.list_objects()] == before


def test_session_info_on_a_pymol_file_explains(session, tmp_path):
    win, shared, do, _messages, errors = session
    fake = tmp_path / "x.pse"
    fake.write_bytes(b"\x80\x04\x95nope")
    do(f"session_info {fake}")
    assert errors and "PyMOL" in errors[-1]


# --------------------------------------------------------------------------- #
# What it cannot carry, it names
# --------------------------------------------------------------------------- #
def test_an_unserialisable_field_is_reported_not_dropped_silently(session, tmp_path):
    """``rmf_hierarchy`` holds an opaque handle; a session cannot carry it.

    Saying so is the point: a session that comes back missing something without
    mentioning it is worse than one that refuses.
    """
    win, shared, do, messages, _errors = session

    class _Opaque:
        pass

    entry = next(iter(win.viewer._objects.values()))
    entry.state.rmf_hierarchy = _Opaque()

    messages.clear()
    do(f"session_save {tmp_path / 's.cms'}")
    joined = " ".join(messages)
    assert "rmf_hierarchy" in joined, joined


def test_an_unknown_field_from_a_newer_session_is_named(session, tmp_path):
    """Forward compatibility: name the field, do not crash on it."""
    win, shared, do, messages, errors = session
    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    # Add a field this chimol does not know about.
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        arrays = archive.read("arrays.npz") if "arrays.npz" in archive.namelist() else None
    manifest["objects"][0]["state"]["a_field_from_the_future"] = 42
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        if arrays is not None:
            archive.writestr("arrays.npz", arrays)

    messages.clear()
    do(f"session_load {path}")
    assert errors == []
    assert any("a_field_from_the_future" in m for m in messages)


# --------------------------------------------------------------------------- #
# The container itself
# --------------------------------------------------------------------------- #
def test_the_file_is_an_inspectable_container(session, tmp_path):
    """Readable without chimol: a session people keep should not be opaque."""
    win, shared, do, _messages, _errors = session
    _furnish(do)
    path = tmp_path / "s.cms"
    do(f"session_save {path}")

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "arrays.npz" in names
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["version"] >= 1
    assert [o["name"] for o in manifest["objects"]] == ["148l", "lig"]
    assert len(manifest["view"]) == 18


def test_arrays_are_stored_without_pickling(session, tmp_path):
    """``allow_pickle=False`` on read, so a session cannot execute anything.

    A format people exchange must not be a code-execution path, which is the
    other reason not to copy PyMOL's pickled ``.pse``.
    """
    import io

    win, shared, do, _messages, _errors = session
    path = tmp_path / "s.cms"
    do(f"session_save {path}")
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("arrays.npz")
    with np.load(io.BytesIO(raw), allow_pickle=False) as data:
        assert data.files, "no arrays were stored"
