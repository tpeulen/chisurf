"""A trajectory must not turn the CA trace into every atom.

The bug this pins
-----------------
``load_traj`` laid 464 frames of 5,235 atoms onto a 570-residue protein, and the
render trace went from **570 points to 5,235**. The cartoon then splined a
ribbon through every atom in file order, which draws a spiky hairball rather
than a protein -- and only ever *after* loading a trajectory, which is what made
it look like a trajectory bug. The same molecule drew perfectly from its PDB
alone.

The cause was one field. ``_select_state_frame`` extracts the CA trace from each
frame using ``state._ca_indices``, and that field was only ever filled by
``set_coordinates``. A structure loaded by any other route left it ``None``, the
extraction was skipped, and the fallback is "use the whole frame".

So the test is not about trajectories at all, really: it is that a value every
frame needs must not depend on which door the structure came in through.

What is asserted
----------------
The trace length, because that is the thing that broke and it is one number.
Pixels would also have caught it, but a hairball and a ribbon differ in ways a
threshold cannot state, while ``570 != 5235`` is exact.
"""
from __future__ import annotations

import os
import pathlib

import numpy as np
import pytest

os.environ.setdefault("CHIMOL_TOOLKIT", "none")
os.environ.setdefault("CHIMOL_CANVAS", "offscreen")

#: The demo trajectory: 570 residues, 5,235 atoms, 464 frames.
DATA = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "trajectory" / "hgbp1"
)
TOPOLOGY = DATA / "topol.pdb"
FRAMES = DATA / "hgbp1_transition.dcd"


@pytest.fixture
def app():
    if not TOPOLOGY.is_file() or not FRAMES.is_file():
        pytest.skip("the hgbp1 trajectory fixture is not present")
    run = pytest.importorskip("chisurf.plugins.chimol.chimol.host.run")
    try:
        instance = run.ChimolApp(backend="offscreen", size=(640, 480))
    except Exception as exc:  # pragma: no cover - no WebGPU adapter here
        pytest.skip(f"no offscreen renderer: {exc}")
    instance.cmd.do(f"load {TOPOLOGY}")
    return instance


def _trace(app) -> np.ndarray:
    return np.asarray(app.viewer._coords)


def test_the_trace_is_one_point_per_residue_before_any_trajectory(app):
    """The baseline the rest of this file is measured against."""
    viewer = app.viewer
    assert _trace(app).shape[0] == len(viewer._residue_ids)


def test_a_trajectory_does_not_replace_the_trace_with_every_atom(app):
    """The bug, stated as the number that changed."""
    residues = len(app.viewer._residue_ids)
    atoms = len(app.viewer._atoms)
    assert atoms > residues, "fixture assumption: more atoms than residues"

    app.cmd.do(f"load_traj {FRAMES}")
    length = _trace(app).shape[0]
    assert length != atoms, (
        f"the trace became one point per *atom* ({atoms}); the cartoon will "
        "spline a ribbon through every atom in file order"
    )
    assert length == residues


@pytest.mark.parametrize("frame", [1, 5, 25])
def test_the_trace_stays_per_residue_as_frames_change(app, frame):
    """Stepping must not reintroduce it -- the extraction runs per frame."""
    app.cmd.do(f"load_traj {FRAMES}")
    residues = len(app.viewer._residue_ids)
    app.cmd.do(f"frame {frame}")
    assert _trace(app).shape[0] == residues


def test_the_trace_still_looks_like_a_backbone_after_a_frame_change(app):
    """Consecutive guide atoms stay a CA-CA bond apart.

    The length being right is necessary but not sufficient: picking 570 of the
    5,235 atoms by the wrong rule also gives 570 points. A real CA trace steps
    about 3.8 Angstrom per residue, times the scene scale.
    """
    app.cmd.do(f"load_traj {FRAMES}")
    app.cmd.do("frame 10")
    trace = _trace(app)
    scale = float(getattr(app.viewer, "_scale_factor", 1.0)) or 1.0
    steps = np.linalg.norm(np.diff(trace, axis=0), axis=1) / scale
    # The median, not the max: a chain break is a real, large jump and this
    # fixture has two chains.
    assert 3.0 < float(np.median(steps)) < 4.5, (
        f"median consecutive step is {np.median(steps) / 1:.2f} A -- that is not "
        "a backbone"
    )
