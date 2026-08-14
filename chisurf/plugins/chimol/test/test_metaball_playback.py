"""Metaballs during playback: fast enough to watch, and not a different picture.

A trajectory wants 20 fps — 50 ms a frame — and a full metaball build is ~220 ms
on one nuclear-pore spoke, nearly all of it the per-vertex transfer of colour and
normals from the atoms. That transfer is spent on a picture which is replaced
before anyone can look at it, so while frames are arriving quickly it is skipped
and the isosurface is built at a coarser grid; a settle timer bakes the good
version as soon as the frame stops changing.

The rule the cartoon's draft established, and which these tests hold the
metaball to: **the draft may be coarser, never different**. A blob that changes
colour mid-scrub and snaps back is worse than one that is simply chunkier.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

from chimol.config import _DISPLAY_CONFIG
from chimol.io.atoms import make_bead_rows
from chimol.renderer.view import MolView


@pytest.fixture(scope="module")
def _qt_app():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def blob(_qt_app):
    """Return a viewer showing metaballs over a few hundred beads."""
    rng = np.random.default_rng(0)
    xyz = rng.normal(scale=9.0, size=(400, 3))
    view = MolView()
    view.set_coordinates(
        xyz,
        atoms=make_bead_rows(xyz, chain_ids=["A"] * len(xyz)),
        atom_radii=np.full(len(xyz), 3.0),
    )
    view.set_metaballs_visible(True)
    return view


def _build(view, *, draft: bool):
    """Build the metaball scene object at the given quality."""
    view._draft_quality = draft
    cfg = view._metaball_config(_DISPLAY_CONFIG.get("metaball", {}))
    objects = view._update_metaballs(np.asarray(view._coords, dtype=float), cfg, None)
    assert objects, "the metaball builder produced nothing"
    return objects[0]


# --------------------------------------------------------------------------- #
# The draft is coarser, not different
# --------------------------------------------------------------------------- #
def test_the_draft_keeps_the_object_colour(blob):
    """A green model must not turn blue while it is being scrubbed.

    The draft skips the per-vertex colour transfer, and the tempting fallback --
    the representation's own base colour -- discards everything `color` and
    `spectrum` did. The average of the atom colours keeps the hue.
    """
    blob._base_color_single = np.array([0.2, 0.9, 0.3, 1.0])
    settled = np.asarray(_build(blob, draft=False).geometry.colors)[:, :3]
    draft = np.asarray(_build(blob, draft=True).geometry.colors)[:, :3]

    # Same hue: compare mean colour direction, not brightness (the settled
    # version carries occlusion, which darkens).
    def hue(c):
        m = c.mean(axis=0)
        return m / max(np.linalg.norm(m), 1e-9)

    assert float(np.dot(hue(settled), hue(draft))) > 0.99


def test_the_draft_is_cheaper_and_coarser(blob):
    """Fewer vertices from a coarser grid -- that is where the time goes."""
    settled = _build(blob, draft=False)
    draft = _build(blob, draft=True)

    n_settled = np.asarray(settled.geometry.positions).shape[0]
    n_draft = np.asarray(draft.geometry.positions).shape[0]
    assert 0 < n_draft < n_settled


def test_the_draft_grid_is_coarser_only_while_drafting(blob):
    """`_metaball_config` must not coarsen a settled build."""
    base = _DISPLAY_CONFIG.get("metaball", {})
    blob._draft_quality = False
    assert blob._metaball_config(base).get("max_dim") == base.get("max_dim")
    blob._draft_quality = True
    assert blob._metaball_config(base)["max_dim"] == MolView._DRAFT_METABALL["max_dim"]


def test_the_draft_still_produces_a_usable_surface(blob):
    """Coarser is fine; empty or degenerate is not."""
    draft = _build(blob, draft=True)
    verts = np.asarray(draft.geometry.positions)
    norms = np.asarray(draft.geometry.normals)

    assert verts.shape[0] > 100
    assert norms.shape == verts.shape
    lengths = np.linalg.norm(norms, axis=1)
    assert np.all(np.isfinite(lengths))
    assert np.median(lengths) > 0.5, "normals must be normalised, not zero"


# --------------------------------------------------------------------------- #
# Scrubbing is decided by rate, not by a mode
# --------------------------------------------------------------------------- #
def test_a_single_frame_change_is_not_a_scrub(blob):
    """One click of a spinner, or a headless render, gets full quality.

    The decision is made on how fast frames arrive, so that a lone frame change
    is never quietly downgraded to the draft.
    """
    blob._last_frame_change = None
    blob._note_frame_change()
    assert blob._draft_quality is False


def test_frames_arriving_quickly_are_a_scrub(blob):
    """Playback -- frames within the scrub interval -- takes the cheap path."""
    blob._last_frame_change = time.perf_counter()
    blob._note_frame_change()
    assert blob._draft_quality is True


def test_an_unhurried_frame_returns_to_full_quality(blob):
    """After a pause the next frame is baked properly, timer or no timer."""
    blob._last_frame_change = time.perf_counter() - (MolView._SCRUB_INTERVAL_S + 0.05)
    blob._note_frame_change()
    assert blob._draft_quality is False


# --------------------------------------------------------------------------- #
# Normals
# --------------------------------------------------------------------------- #
def test_the_isosurface_normals_are_the_default(blob):
    """Density-gradient normals average over several bead radii and airbrush it.

    They are so much smoother than the isosurface's own that no specular
    highlight survives them, which is why a metaball never looked wet. The
    setting still exists for anyone who wants the soft look.
    """
    cfg = dict(_DISPLAY_CONFIG.get("metaball", {}))
    assert str(cfg.get("normals", "isosurface")).lower() == "isosurface"

    blob._draft_quality = False
    iso = np.asarray(
        blob._update_metaballs(np.asarray(blob._coords, float), cfg, None)[0]
        .geometry.normals
    )
    smooth_cfg = dict(cfg, normals="density")
    smoothed = np.asarray(
        blob._update_metaballs(np.asarray(blob._coords, float), smooth_cfg, None)[0]
        .geometry.normals
    )
    # They must actually differ, or the setting is decoration.
    assert not np.allclose(iso, smoothed)
