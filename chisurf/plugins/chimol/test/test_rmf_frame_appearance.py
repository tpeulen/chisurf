"""A trajectory that is a simulation, not just motion.

Every frame path in ChiMOL assumed a trajectory moves atoms and nothing else,
which is true of an MD run and false of an agent simulation: there, particles
appear, grow and change what they are doing. RMF has always stored a radius and
a colour **per frame** and the reader took neither -- radii came from whichever
frame the walk happened to leave current, and the colour factory was built and
never asked -- so a growing colony opened as a full-grown one sliding into
place.

Three things are pinned here:

* a per-frame radius and colour are read as a series, and a file whose values
  hold still still yields one array, so nothing that does not care about time
  pays for it;
* stepping the movie recolours and resizes;
* a particle with no radius in this frame is one that does not exist yet, and it
  is hidden **without** disturbing what the hierarchy panel switched off -- the
  two are different questions and one mask serving both is the bug that keeps
  being rediscovered.
"""

from __future__ import annotations

import numpy as np
import pytest

RMF = pytest.importorskip("RMF")

from chimol.core.viewer import Viewer
from chimol.io.rmf import load_rmf_full
from chimol.io.structure import load_structure_payload

N_BEADS = 6
N_FRAMES = 4


def _write(path, *, vary: bool) -> None:
    """Write a small swarm-shaped RMF.

    Parameters
    ----------
    path : pathlib.Path
        Destination.
    vary : bool
        When true, bead ``i`` is born at frame ``i`` (radius zero before that),
        every bead's colour changes over the run, and the whole set drifts along
        ``x`` -- which is what a molecule wandering across a box does, and the
        only thing a camera can follow. When false, every frame is identical,
        which is the case the reader must collapse.
    """
    handle = RMF.create_rmf_file(str(path))
    particles = RMF.ParticleFactory(handle)
    colored = RMF.ColoredFactory(handle)
    root = handle.get_root_node().add_child("colony", RMF.REPRESENTATION)
    RMF.ChainFactory(handle).get(root).set_chain_id("A")
    nodes = [root.add_child(f"cell_{i}", RMF.REPRESENTATION) for i in range(N_BEADS)]
    for node in nodes:
        particles.get(node).set_mass(1.0)

    for frame in range(N_FRAMES):
        handle.add_frame(f"t{frame}", RMF.FRAME)
        for index, node in enumerate(nodes):
            particle = particles.get(node)
            drift = 2.0 * frame if vary else 0.0
            particle.set_coordinates(RMF.Vector3(3.0 * index + drift, 0.0, 0.0))
            born = (not vary) or index <= frame
            particle.set_radius(1.0 if born else 0.0)
            shade = (frame / (N_FRAMES - 1)) if vary else 0.0
            colored.get(node).set_rgb_color(RMF.Vector3(shade, 1.0 - shade, 0.2))
    del handle


@pytest.fixture(scope="module")
def varying(tmp_path_factory):
    path = tmp_path_factory.mktemp("rmf") / "varying.rmf"
    _write(path, vary=True)
    return path


@pytest.fixture(scope="module")
def constant(tmp_path_factory):
    path = tmp_path_factory.mktemp("rmf") / "constant.rmf"
    _write(path, vary=False)
    return path


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _view(path, qapp):
    _reader, payload = load_structure_payload(str(path))
    view = Viewer()
    view.add_payload(payload, name="colony", source_path=str(path))
    return view


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def test_a_varying_file_yields_a_series(varying):
    data = load_rmf_full(varying)
    assert data["frame_radii"].shape == (N_FRAMES, N_BEADS)
    assert data["frame_colors"].shape == (N_FRAMES, N_BEADS, 3)


def test_a_constant_file_yields_one_array(constant):
    """A model that states one radius and one colour must not grow a time axis.

    Every consumer that does not care about frames asks for ``radii`` and
    ``colors``; handing them a series would push the collapse into each of them.
    """
    data = load_rmf_full(constant)
    assert data["frame_radii"] is None
    assert data["frame_colors"] is None
    assert data["radii"].shape == (N_BEADS,)
    assert data["colors"].shape == (N_BEADS, 3)


def test_the_radii_come_from_the_first_frame(varying):
    """Not from whichever frame the walk left current, which was the last."""
    data = load_rmf_full(varying)
    assert int((data["radii"] > 0).sum()) == 1, data["radii"]


def test_the_colour_in_the_file_is_the_colour_it_opens_with(constant, qapp):
    view = _view(constant, qapp)
    override = view._get_active_state().colors_per_atom_override
    assert override is not None
    assert override.shape == (N_BEADS, 4), "colours must reach the viewer as RGBA"
    assert np.allclose(override[0, :3], [0.0, 1.0, 0.2])


# --------------------------------------------------------------------------- #
# Playing
# --------------------------------------------------------------------------- #
def test_stepping_the_movie_recolours_and_resizes(varying, qapp):
    view = _view(varying, qapp)
    seen = []
    for frame in range(N_FRAMES):
        view.set_current_frame(frame)
        state = view._get_active_state()
        seen.append(
            (
                state.colors_per_atom_override[0, :3].copy(),
                float(np.max(state.all_atom_radii)),
            )
        )
    first_colour, _ = seen[0]
    last_colour, _ = seen[-1]
    assert not np.allclose(first_colour, last_colour), "colour never followed the frame"


def test_a_bead_with_no_radius_is_not_drawn(varying, qapp):
    """Growth is expressed as a radius, and zero means "not yet"."""
    view = _view(varying, qapp)
    for frame in range(N_FRAMES):
        view.set_current_frame(frame)
        mask = view.visible_row_mask(N_BEADS)
        assert mask is not None, frame
        assert int(mask.sum()) == frame + 1, (frame, mask)


def test_hiding_survives_stepping_the_movie(varying, qapp):
    """The reason ``absent_mask`` is its own mask.

    A single visibility mask serving both questions means the next frame
    silently un-hides whatever the hierarchy panel switched off -- the same
    failure ``representation_mask`` was split out to avoid.
    """
    view = _view(varying, qapp)
    view.set_current_frame(N_FRAMES - 1)
    hidden = np.zeros(N_BEADS, dtype=bool)
    hidden[0] = True
    view._get_active_state().hidden_mask = hidden

    view.set_current_frame(N_FRAMES - 2)
    mask = view.visible_row_mask(N_BEADS)
    assert not mask[0], "stepping the movie un-hid a bead that was switched off"
    assert not mask[N_FRAMES - 1], "a bead not yet born was drawn"
    assert mask[1], "a living, un-hidden bead was hidden"


# --------------------------------------------------------------------------- #
# Whether the camera follows the frame
# --------------------------------------------------------------------------- #
@pytest.fixture
def restore_recenter():
    """Put ``movie_recenter`` back, whatever the test did to it.

    ``_DISPLAY_CONFIG`` is one dict for the whole process, so a test that leaves
    a setting changed does not fail here -- it fails somewhere else, in another
    file, for no visible reason.
    """
    from chimol.core.settings.registry import get_setting, set_setting

    before = get_setting("movie_recenter")
    yield set_setting
    set_setting("movie_recenter", before)


def test_the_camera_follows_the_frame_when_asked_to(varying, qapp, restore_recenter):
    """The default, and what keeps a molecule wandering across a box in view."""
    restore_recenter("movie_recenter", True)
    view = _view(varying, qapp)
    centres = []
    for frame in range(N_FRAMES):
        view.set_current_frame(frame)
        centres.append(float(view._get_active_state().center[0]))
    assert len(set(np.round(centres, 6))) > 1, (
        "the camera did not follow the frame with movie_recenter on"
    )


def test_the_floor_stays_put_when_it_is_turned_off(varying, qapp, restore_recenter):
    """What a structure that *grows* needs.

    Following the centroid of a growing film slides the scene out from under it:
    the substratum drifts downward while the surface stays put, so the film
    appears to sink rather than to grow. Measured on the biofilm demo before this
    existed, the scene centre swung from 0 to -21 to +52 scene units.
    """
    restore_recenter("movie_recenter", False)
    view = _view(varying, qapp)
    centres = []
    for frame in range(N_FRAMES):
        view.set_current_frame(frame)
        centres.append(np.asarray(view._get_active_state().center, dtype=float).copy())
    for frame, centre in enumerate(centres[1:], start=1):
        assert np.allclose(centre, centres[0]), (
            f"frame {frame} moved the scene centre to {centre} from {centres[0]}"
        )
