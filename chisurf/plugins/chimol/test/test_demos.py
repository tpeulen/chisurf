"""The Demo menu, the demo scripts, and the trajectory commands they exercise.

The demos are ChiMOL **scripts**, not Python: one command per line, run exactly
as ``@file.pml`` runs. That is deliberate — it makes them a test of *language
parity with PyMOL* rather than of the internals, and a demo that stops working is
a command that stopped working. They double as documentation that runs.

The trajectory commands matter beyond the demos: ``intra_fit`` is what makes a
modelling trajectory watchable. Without it a movie shows the model tumbling
through the box and the conformational change — the thing being looked at — is
buried under rigid-body drift.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.app.demos import (
    DEMOS,
    DEMO_DIR,
    demo_path,
    read_demo,
    resolve_structure,
)

_TRAJECTORY = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "trajectory" / "h5-file"
    / "hgbp1_transition.h5"
)


# --------------------------------------------------------------------------- #
# The scripts themselves
# --------------------------------------------------------------------------- #
def test_every_listed_demo_has_a_script():
    for key, _title, _description in DEMOS:
        assert demo_path(key).exists(), f"{key}.pml is missing"


def test_every_script_is_listed():
    """A script nobody can reach from the menu is dead weight."""
    listed = {key for key, _t, _d in DEMOS}
    on_disk = {p.stem for p in DEMO_DIR.glob("*.pml")}
    assert on_disk == listed, f"unlisted: {sorted(on_disk - listed)}"


def test_every_demo_has_a_description():
    for _key, title, description in DEMOS:
        assert title and description


def test_the_scripts_are_commands_not_python():
    """The point of writing them in the command language.

    A demo in Python would test the internals; a demo in ChiMOL's own language
    tests that the language works, which is what parity with PyMOL means.
    """
    for key, _t, _d in DEMOS:
        for line in read_demo(key).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            assert "=" not in stripped.split(",")[0], (
                f"{key}: {stripped!r} looks like Python, not a command"
            )
            assert not stripped.startswith(("import ", "from ", "def ")), key


def test_the_structures_the_demos_name_can_be_found():
    """They say `load 148l.pdb` so they read like something a person types."""
    for key, _t, _d in DEMOS:
        for line in read_demo(key).splitlines():
            stripped = line.strip()
            if stripped.startswith("load ") and "," not in stripped:
                name = stripped[5:].strip()
                assert pathlib.Path(resolve_structure(name)).exists(), (
                    f"{key} loads {name}, which cannot be found"
                )


# --------------------------------------------------------------------------- #
# Running them
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(900, 650)
    win.show()
    for _ in range(12):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    yield win, shared, errors, qapp
    win.close()


def _vertices(viewer):
    scene = viewer.get_current_scene()
    return sum(
        len(o.geometry.positions) if o.geometry.positions is not None else 0
        for o in scene.objects
    )


@pytest.mark.parametrize("key", [key for key, _t, _d in DEMOS])
def test_a_demo_runs_and_draws_something(window, key):
    """Every line is a real command, so this is a command-surface test."""
    win, _shared, errors, qapp = window
    win.run_demo(key)
    for _ in range(30):
        qapp.processEvents()
    assert errors == [], f"{key}: {errors[:2]}"
    assert _vertices(win.viewer) > 0, f"{key} drew nothing"


def test_each_demo_starts_from_a_clean_viewer(window):
    """Otherwise the seventh demo shows a pile of seven molecules."""
    win, _shared, _errors, qapp = window
    for key, _t, _d in DEMOS[:3]:
        win.run_demo(key)
        for _ in range(25):
            qapp.processEvents()
        assert len(win.viewer.list_objects()) == 1, key


def test_the_demo_menu_is_built(window):
    win, _shared, _errors, _qapp = window
    titles = [m.title() for m in win.menuBar().findChildren(type(win.menuBar().addMenu("x")))]
    assert any("Demo" in t for t in titles if t)
    assert len(getattr(win, "_demo_actions", [])) >= len(DEMOS)


def test_script_text_runs_line_by_line(window):
    """The editor, the Demo menu and `@file` all go through this one path."""
    win, _shared, errors, qapp = window
    win.run_script_text(
        "# a comment\n\nload " + resolve_structure("148l.pdb") + "\nshow cartoon\n"
    )
    for _ in range(25):
        qapp.processEvents()
    assert errors == []
    assert len(win.viewer.list_objects()) == 1


# --------------------------------------------------------------------------- #
# The trajectory commands
# --------------------------------------------------------------------------- #
@pytest.fixture
def trajectory(window):
    win, shared, errors, qapp = window
    if not _TRAJECTORY.exists():
        pytest.skip("no trajectory fixture")
    win._load_structure_from_path(_TRAJECTORY)
    for _ in range(30):
        qapp.processEvents()
    errors.clear()
    return win, shared, errors, qapp


def _frames(viewer):
    state = viewer._objects[viewer.get_active_object_id()].state
    return np.asarray(state.frames_raw, dtype=float)


def test_count_states_reports_the_trajectory_length(trajectory):
    win, shared, _errors, _qapp = trajectory
    assert shared.count_states("all") == _frames(win.viewer).shape[0] > 1


def test_count_states_works_without_an_atom_array(trajectory):
    """A coarse-grained model has coordinates and no atoms.

    That is exactly what chisurf's modelling produces, so refusing it would make
    these commands useless for the case they are most wanted for.
    """
    win, shared, _errors, _qapp = trajectory
    state = win.viewer._objects[win.viewer.get_active_object_id()].state
    assert state.atoms is None, "the fixture should be coarse-grained"
    assert shared.count_states("all") > 1


def test_intra_fit_removes_the_rigid_body_drift(trajectory):
    """The whole point: the centroid stops wandering."""
    win, shared, errors, qapp = trajectory

    def drift(frames):
        centres = frames.mean(axis=1)
        return float(np.linalg.norm(centres - centres[0], axis=1).max())

    before = drift(_frames(win.viewer))
    assert before > 0.5, "the fixture should have drift to remove"

    shared.do("intra_fit all, 1")
    for _ in range(20):
        qapp.processEvents()
    assert errors == []
    assert drift(_frames(win.viewer)) < 1e-6


def test_intra_fit_is_rigid(trajectory):
    """A superposition, not a deformation: internal distances cannot change."""
    win, shared, _errors, qapp = trajectory
    before = _frames(win.viewer)[10]
    reference = np.linalg.norm(before[1:200] - before[0], axis=1)

    shared.do("intra_fit all, 1")
    for _ in range(20):
        qapp.processEvents()
    after = _frames(win.viewer)[10]
    assert np.allclose(
        np.linalg.norm(after[1:200] - after[0], axis=1), reference, atol=1e-6
    )


def test_intra_rms_measures_without_moving_anything(trajectory):
    win, shared, _errors, _qapp = trajectory
    before = _frames(win.viewer).copy()
    values = shared.intra_rms("all", "1")
    assert len(values) == before.shape[0]
    assert values[0] == pytest.approx(0.0, abs=1e-9), "the reference reads zero"
    assert np.array_equal(_frames(win.viewer), before), "intra_rms moved the model"


def test_fitting_does_not_change_the_rms(trajectory):
    """Because the RMS is already the best-fit one: `intra_rms` fits internally
    to measure. If fitting changed it, one of the two would be wrong."""
    win, shared, _errors, qapp = trajectory
    before = shared.intra_rms("all", "1")
    shared.do("intra_fit all, 1")
    for _ in range(20):
        qapp.processEvents()
    after = shared.intra_rms("all", "1")
    assert np.allclose(before, after, atol=1e-6)


def test_intra_fit_on_a_single_state_object_says_so(window):
    win, shared, errors, qapp = window
    win.run_demo("cartoon")
    for _ in range(25):
        qapp.processEvents()
    errors.clear()
    shared.do("intra_fit all, 1")
    for _ in range(10):
        qapp.processEvents()
    assert errors and "single state" in errors[-1]


def test_get_state_is_one_based(trajectory):
    """PyMOL's states are 1-based; the viewer's frames are 0-based."""
    win, shared, _errors, qapp = trajectory
    shared.do("frame 1")
    for _ in range(10):
        qapp.processEvents()
    assert shared.get_state() == 1
