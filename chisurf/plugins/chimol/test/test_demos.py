"""The Demo menu, the demo scripts, and the trajectory commands they exercise.

The demos are ChiMOL **scripts**, not Python: one command per line, run exactly
as ``@file.cml`` runs. That is deliberate — it makes them a test of *language
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

from chimol.hosts.qt.demos import (
    DEMOS,
    DEMO_DIR,
    demo_path,
    read_demo,
    resolve_structure,
)

_TRAJ_DIR = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "trajectory"
)
#: A trajectory is two files. DCD stores coordinates and nothing else, so the
#: atom names come from the PDB and the frames are laid onto it -- which is what
#: `load_traj` is for and what these tests exercise.
_TOPOLOGY = _TRAJ_DIR / "hgbp1" / "topol.pdb"
_TRAJECTORY = _TRAJ_DIR / "hgbp1" / "hgbp1_transition.dcd"


# --------------------------------------------------------------------------- #
# The scripts themselves
# --------------------------------------------------------------------------- #
def test_every_listed_demo_has_a_script():
    for key, _title, _description in DEMOS:
        assert demo_path(key).exists(), f"{key}.cml is missing"


def test_every_script_is_listed():
    """A script nobody can reach from the menu is dead weight."""
    listed = {key for key, _t, _d in DEMOS}
    on_disk = {p.stem for p in DEMO_DIR.glob("*.cml")}
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
    """They say `load 148l.pdb` so they read like something a person types.

    One demo's material is *computed* rather than shipped, and resolving its
    name runs the simulation into a cache -- so this is also what proves the
    generated path produces a file. Where the simulator is not installed it is
    skipped rather than failed: that is an environment, not a broken demo.
    """
    from chimol.plugins.demos.material import DemoDataUnavailable

    for key, _t, _d in DEMOS:
        for line in read_demo(key).splitlines():
            stripped = line.strip()
            if stripped.startswith("load ") and "," not in stripped:
                name = stripped[5:].strip()
                try:
                    resolved = resolve_structure(name)
                except DemoDataUnavailable as exc:
                    pytest.skip(f"{key}: {exc}")
                assert pathlib.Path(resolved).exists(), (
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
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
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
    from chimol.plugins.demos.material import DemoDataUnavailable, GENERATED_DEMO_DATA
    from chimol.hosts.qt.demos import resolve_structure

    for name in GENERATED_DEMO_DATA:
        if f"load {name}" in read_demo(key):
            try:
                resolve_structure(name)
            except DemoDataUnavailable as exc:
                pytest.skip(f"{key}: {exc}")

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


def _menubar_of(win):
    """The viewport menu bar's ``(title, entries)`` pairs."""
    renderer = win.viewer.renderer or win.viewer
    gui = getattr(renderer, "_internal_gui", None)
    return list(getattr(gui, "menubar", []) or [])


def _demo_menu_of(win):
    """The Demo menu as the *viewer* holds it, or ``None``.

    Read from the internal GUI rather than from ``win.menuBar()``: the Qt bar
    was retired -- on macOS Qt moves it to the system bar at the top of the
    screen, nowhere near the 3-D view, and a browser host has no Qt at all --
    and the menus are now drawn in the viewport from the same ``MENU_BAR``
    table. The property being tested is unchanged: a menu that was built but
    never handed to the bar is a menu the user cannot open.
    """
    for title, entries in _menubar_of(win):
        if "Demo" in str(title):
            return entries
    return None


def test_the_demo_menu_is_on_the_menu_bar(window):
    """On the *bar*, not merely constructed.

    The first version built it before ``_install_menu_bar``, which begins with
    ``bar.clear()`` -- so the menu was created and then silently wiped, and it
    was missing in the running application. A test that inspected the child
    widgets still found it, because the cleared menu object survives as a child
    of the bar without being on it. Reading what the bar was actually *given*
    is what distinguishes the two.
    """
    win, _shared, _errors, _qapp = window
    titles = [str(title) for title, _entries in _menubar_of(win)]
    assert _demo_menu_of(win) is not None, titles


def test_every_demo_has_a_menu_entry(window):
    win, _shared, _errors, _qapp = window
    entries = _demo_menu_of(win)
    assert entries is not None, "no Demo menu on the viewport menu bar"
    labels = [str(getattr(e, "label", "")) for e in entries if getattr(e, "label", "")]
    for _key, title, _description in DEMOS:
        assert title in labels, f"{title} is not in the Demo menu"
    assert any("Edit" in label for label in labels)


def test_the_demo_menu_comes_from_the_menu_bar_and_appears_once(window):
    """It used to be bolted on after `build_menu_bar`, which starts with
    `bar.clear()` -- so the order of construction decided whether the Demo menu
    existed at all, and this test guarded that order.

    It is part of `MENU_BAR` now, generated from the same `DEMOS` table, so it
    survives a rebuild by construction and the separate `build_demo_menu`
    builder is gone: an unused builder that silently adds a *second* Demo menu
    is a trap, not a spare.
    """
    win, _shared, _errors, qapp = window
    from chimol.hosts.qt import demos

    assert not hasattr(demos, "build_demo_menu"), (
        "the bolted-on demo menu builder is back"
    )

    win._install_menu_bar()
    for _ in range(5):
        qapp.processEvents()
    titles = [action.text().replace("&", "") for action in win.menuBar().actions()]
    assert titles.count("Demo") == 1, titles


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
    if not (_TRAJECTORY.exists() and _TOPOLOGY.exists()):
        pytest.skip("no trajectory fixture")
    win.load_structure_from_path(_TOPOLOGY)
    for _ in range(30):
        qapp.processEvents()
    shared.load_traj(str(_TRAJECTORY))
    for _ in range(30):
        qapp.processEvents()
    errors.clear()
    return win, shared, errors, qapp


def _frames(viewer):
    state = viewer.objects[viewer.get_active_object_id()].state
    return np.asarray(state.frames_raw, dtype=float)


def test_count_states_reports_the_trajectory_length(trajectory):
    win, shared, _errors, _qapp = trajectory
    assert shared.count_states("all") == _frames(win.viewer).shape[0] > 1


def test_the_trajectory_topology_is_read(trajectory):
    """The atom names and residues must survive `load_traj`.

    This test used to assert the opposite -- that the fixture had *no* atoms,
    "because it is coarse-grained". That was my wrong reading: the file is
    all-atom, and the 15.3 A "bead spacing" I measured was in scene units
    (1.53 A in the file, an ordinary bond). The loader was dropping
    ``traj.topology``, so every feature keyed on atom identity degraded silently.

    The same failure has a second way in now that the topology arrives from a
    separate file: `load_traj` writes frames over an object's coordinates, and
    if it cleared or replaced the atom array while doing so the degradation
    would be identical and just as quiet.
    """
    win, _shared, _errors, _qapp = trajectory
    state = win.viewer.objects[win.viewer.get_active_object_id()].state
    assert state.atoms is not None, "the topology was dropped at load"
    assert len(state.atoms) == np.asarray(state.frames_raw).shape[1]
    names = {str(n).strip() for n in state.atoms["atom_name"][:40]}
    assert "CA" in names, "no alpha carbons: the topology is not real"
    assert state.residue_ids is not None and len(state.residue_ids) > 100


def test_the_cartoon_is_whole_rather_than_fragmented(trajectory):
    """Without residues the builder splines through every atom.

    That drew ~340 disconnected pieces instead of one ribbon per chain, and is
    what "cartoons do not work on trajectories" actually was.
    """
    win, shared, _errors, qapp = trajectory
    shared.do("hide everything")
    shared.do("show cartoon, polymer")
    for _ in range(20):
        qapp.processEvents()
    pieces = len(win.viewer.get_current_scene().objects)
    assert 0 < pieces <= 10, f"{pieces} cartoon pieces: the ribbon is fragmented"


def test_a_selection_resolves_on_a_trajectory(trajectory):
    """`intra_fit polymer` needs this, and it silently matched nothing before."""
    win, shared, _errors, _qapp = trajectory
    _obj, _name, mask = shared._resolve_selection_to_atom_mask(win.viewer, "polymer")
    assert int(np.asarray(mask, dtype=bool).sum()) > 1000


def test_count_states_reports_the_length(trajectory):
    win, shared, _errors, _qapp = trajectory
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
