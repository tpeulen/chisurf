"""GUI (widget-level) tests for the Trajectory→FRET tool."""

import pathlib

import numpy as np
from qtpy import QtWidgets

from chisurf.core.structure.trajectory_data import Trajectory
from chisurf.gui.widgets.pdb import PDBSelector


def _fret_trajectory(path, n_frames: int = 5) -> str:
    """Write a minimal *n_frames* trajectory and return the topology beside it.

    The residue carries four labelled atoms so the donor dipole ``(0, 1)`` and
    the acceptor dipole ``(2, 3)`` reference real coordinates and produce a
    transfer.

    Two files, because a DCD holds coordinates and nothing else. The fixture
    used to be one ``.h5`` written by mdtraj and guarded with
    ``importorskip("mdtraj")`` -- which did not skip when mdtraj left, because
    the test environment still had the package installed while the tree no
    longer read what it wrote. Built on ChiSurf's own writers there is nothing
    left to skip on.
    """
    from chisurf.core.fio.trajectory import DCDWriter
    from chisurf.core.structure.topology import Topology, element

    path = pathlib.Path(path)
    topology = Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C", "O"):
        topology.add_atom(name, element.carbon, residue)

    rng = np.random.default_rng(0)
    # Angstrom: DCD's unit, and the range the transfer calculation expects.
    xyz = (rng.random((n_frames, 4, 3)) * 10.0).astype(np.float32)
    with DCDWriter(str(path), n_atoms=4) as writer:
        for frame in xyz:
            writer.write(frame)

    topology_path = path.with_suffix(".pdb")
    Trajectory(xyz=xyz[:1], topology=topology).save_pdb(str(topology_path))
    return str(topology_path)


def test_structure2transfer_creation(qapp, qtbot):
    from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer

    widget = Structure2Transfer()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")


def test_widget_properties_delegate_to_model(qapp, qtbot):
    from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer

    widget = Structure2Transfer()
    qtbot.addWidget(widget)
    widget.trajectory_file = "/data/example.h5"
    widget.t_step = 0.25
    widget.forster_radius = 55.0
    widget.tau0 = 3.5
    widget.stride = 3
    assert widget.trajectory_file == "/data/example.h5"
    assert widget.model.trajectory_file == "/data/example.h5"
    assert widget.t_step == 0.25
    assert widget.forster_radius == 55.0
    assert widget.tau0 == 3.5
    assert widget.stride == 3


def test_form_renders_with_live_log(qapp, qtbot):
    from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer

    widget = Structure2Transfer()
    qtbot.addWidget(widget)
    widget.resize(560, 480)
    widget.show()
    qapp.processEvents()

    # The AutoForm built a non-trivial section tree ...
    assert widget.auto_form.findChildren(QtWidgets.QWidget)
    # ... including the four PDBSelector atom pickers ...
    selectors = widget.auto_form.findChildren(PDBSelector)
    assert len(selectors) == 4
    # ... the picker/run tool buttons ...
    assert widget.auto_form.findChildren(QtWidgets.QToolButton)
    # ... and the live log (info section bound to log_html) shows the initial entry.
    browsers = widget.auto_form.findChildren(QtWidgets.QTextBrowser)
    assert browsers
    assert any("Ready" in b.toPlainText() for b in browsers)

    # The whole widget paints headlessly without Qt errors.
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.width() > 0 and pixmap.height() > 0


def test_gui_interaction_process(qapp, qtbot, tmp_path):
    """Drive the real widgets: load the trajectory, pick atoms, click Process."""
    from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer

    n_frames = 5
    source = tmp_path / "traj.dcd"
    output = tmp_path / "transfer.csv"
    topology = _fret_trajectory(source, n_frames=n_frames)

    widget = Structure2Transfer()
    qtbot.addWidget(widget)
    widget.show()
    qapp.processEvents()

    # Load the trajectory through the real view-model (populates the pickers).
    widget.model.set_topology(topology)
    widget.model.set_trajectory(str(source))
    qapp.processEvents()

    # The atom-pair section hosts the four real PDBSelector widgets.
    selectors = widget.auto_form.findChildren(PDBSelector)
    assert len(selectors) == 4
    for selector in selectors:
        assert selector.atoms is not None

    # Choose donor (0, 1) and acceptor (2, 3) through the hosting section's setters,
    # which drive the actual PDBSelector combos and push indices to the model.
    section = widget.model.atom_pair_section
    section.set_donor(0, 1)
    section.set_acceptor(2, 3)
    qapp.processEvents()
    assert tuple(widget.donor) == (0, 1)
    assert tuple(widget.acceptor) == (2, 3)

    # Invoke the Process action headlessly (output path supplied instead of a dialog).
    result = widget.model.run_section.run(output_file=str(output))
    qapp.processEvents()

    # Functional result: the model computed a transfer series and wrote the file.
    assert output.exists()
    assert result is not None
    assert result.shape == (n_frames, 6)
    assert np.all(np.isfinite(result))
    assert any(
        "Finished" in b.toPlainText() for b in widget.auto_form.findChildren(QtWidgets.QTextBrowser)
    )
