"""Streaming a `.chm.pto` container to the screen: file in, pixels out.

`test_chm_container.py` proves the container is a valid PTO document and that
the atoms survive the round trip. This proves the other half -- that the thing
can actually be *navigated* -- end to end: build a container from atoms, open
it, and draw frames from it, with nothing between the mapped file and the GPU
but one upload.

What each claim below is worth:

* **It draws the same molecule.** The container's frame is compared against the
  same atoms drawn through the ordinary impostor path. Not pixel-equality --
  positions are 16-bit deltas and colours are 8-bit -- but silhouette overlap,
  which is what "no one can tell which drew it" means.
* **The ladder is climbed.** From far away the traversal must return a coarse
  level and orders of magnitude fewer atoms, while still covering the same
  silhouette. A hierarchy that is never used is a hierarchy that does not work,
  and it fails silently: the picture stays right and the frame stays slow.
* **The cut is bounded.** Culling drops what is off-screen, and a byte budget
  makes the picture *coarser*, never partial.
* **Residency is reused.** Coming back to the same camera re-uses the GPU
  buffers instead of re-uploading them, and a small VRAM ceiling evicts.

The rendering tests need a GPU and skip without one.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
from chimol.core.camera.view_state import pack_view_state
from chimol.render import pack, scene
from chimol.render.chm import CHUNK_ROW, ChmIndex, ContainerView, build_chm
from chimol.render.stream import chunk_selection
from chimol.render.wgpu_backend import WgpuMeshRenderer, perspective, view_matrix

SIZE = (320, 320)
ATOMS = 60_000
CHUNK = 4_096
RADIUS = 1.6


@pytest.fixture(scope="module")
def atoms():
    rng = np.random.default_rng(19)
    #: Three blobs, so a camera can look at one and cull the others.
    centres = np.array([[0.0, 0.0, 0.0], [90.0, 0.0, 0.0], [0.0, 90.0, 0.0]])
    xyz = np.concatenate([rng.normal(c, 12.0, (ATOMS // 3, 3)) for c in centres])
    radii = np.full(xyz.shape[0], RADIUS)
    rgba = np.zeros((xyz.shape[0], 4))
    rgba[:, 0], rgba[:, 1], rgba[:, 2], rgba[:, 3] = 0.9, 0.45, 0.2, 1.0
    return xyz, radii, rgba


@pytest.fixture(scope="module")
def container(atoms, tmp_path_factory):
    xyz, radii, rgba = atoms
    return build_chm(
        xyz,
        radii,
        rgba,
        None,
        tmp_path_factory.mktemp("chm") / "blobs",
        levels=6,
        chunk_atoms=CHUNK,
    )


@pytest.fixture()
def view(container):
    # Pinned: naming a detail level turns the frame-time steering off, which is
    # what a measurement wants. The steering has a test of its own.
    opened = ContainerView.open(container, detail_px=4.0)
    yield opened
    opened.close()


@pytest.fixture(scope="module")
def renderer():
    try:
        return WgpuMeshRenderer(*SIZE)
    except Exception as exc:  # noqa: BLE001 - no GPU on this runner
        pytest.skip(f"no WebGPU adapter: {exc}")


def _camera(view, distance, *, target=None, rotation=None):
    return pack_view_state(
        rotation=np.eye(3) if rotation is None else rotation,
        distance=float(distance),
        target=tuple(view.center if target is None else target),
        near=0.1,
        far=float(view.radius * 40.0),
    )


def _matrices(view, state, renderer):
    """Build the (mvp, view, proj_scale, anchor) the renderer derives from a camera."""
    from chimol.core.camera.view_state import unpack_view_state

    s = unpack_view_state(state)
    anchor = np.asarray(view.center, dtype=np.float64)
    v = view_matrix(s.rotation, np.asarray(s.target, np.float64) - anchor, s.distance, s.shift)
    p = perspective(s.fov, renderer.width / renderer.height, max(s.near, 1e-3), s.far)
    return p @ v, v, renderer.point_scale(s.fov), anchor


def _empty(view):
    return pack.pack_scene(scene.Scene(objects=[], center=tuple(view.center), radius=view.radius))


def _silhouette(frame: np.ndarray) -> np.ndarray:
    return frame.max(axis=2) > 12


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    union = (a | b).sum()
    return 1.0 if union == 0 else float((a & b).sum() / union)


# ── the level ladder, without a GPU ──────────────────────────────────────
def test_the_cut_is_the_whole_structure_at_every_distance(view, renderer):
    """Far or near, the selection covers every atom exactly once -- at some level."""
    for distance in (view.radius * 8, view.radius * 2, view.radius * 0.4):
        state = _camera(view, distance)
        chosen = view.select(*_matrices(view, state, renderer))
        levels = view.stats["levels"]
        assert chosen.size, f"nothing selected at {distance}"
        # A chunk and an ancestor may both be drawn -- that is a handover in
        # progress -- but their weights *share* the pixel rather than doubling
        # it: along any root-to-leaf path the weights sum to one.
        table = view.index.table
        # `weight` rows are (weight, dither base); the weight is column 0.
        weights = {int(c): float(w) for c, w in zip(chosen, view.weight[:, 0])}
        for chunk, weight in weights.items():
            assert 0.0 < weight <= 1.0 + 1e-6, weight
            total = weight
            parent = int(table["parent"][chunk])
            while parent >= 0:
                total += weights.get(parent, 0.0)
                parent = int(table["parent"][parent])
            assert total <= 1.0 + 1e-3, f"{chunk}: weights along its path sum to {total}"
        assert levels, "no level recorded"


def test_distance_climbs_the_ladder(view, renderer):
    near = view.select(*_matrices(view, _camera(view, view.radius * 0.4), renderer))
    near_atoms = view.stats["atoms"]
    far = view.select(*_matrices(view, _camera(view, view.radius * 40), renderer))
    far_atoms, far_levels = view.stats["atoms"], view.stats["levels"]
    assert far.size < near.size
    # The point of the hierarchy: several times fewer atoms, not 10%. Not the
    # full 8:1 of the decimation, because a level dissolves into the next
    # rather than replacing it, so a far frame is still finishing a fade.
    assert far_atoms * 4 <= near_atoms, (far_atoms, near_atoms)
    assert min(far_levels) > 0, f"still drawing leaves from far away: {far_levels}"


def test_looking_away_selects_nothing(view, renderer):
    """The cull is answered from the index -- no chunk is opened to be dropped."""
    away = np.array([view.radius * 500.0, 0.0, 0.0])
    state = _camera(view, view.radius * 0.2, target=view.center + away)
    chosen = view.select(*_matrices(view, state, renderer))
    assert chosen.size == 0
    assert view.stats["culled"] >= 1


def test_a_byte_budget_makes_the_picture_coarser_not_partial(view, renderer):
    state = _camera(view, view.radius * 0.5)
    full = view.select(*_matrices(view, state, renderer))
    full_bytes = view.stats["bytes"]
    view.budget_bytes = max(full_bytes // 8, 4096)
    tight = view.select(*_matrices(view, state, renderer))
    assert tight.size, "the budget emptied the frame"
    assert view.stats["bytes"] <= full_bytes
    assert view.stats["atoms"] < view.index.meta["n_atoms"]
    assert min(view.stats["levels"]) > 0 or view.stats["bytes"] < full_bytes
    assert full.size >= tight.size


def test_the_traversal_reads_no_geometry_to_decide(view, renderer):
    """Selection touches the index only: the mapping stays cold."""
    state = _camera(view, view.radius * 4)
    table, (offsets, ids) = view.index.table, view.index.tree
    mvp, v, scale, anchor = _matrices(view, state, renderer)
    before = dict(view.residency.stats)
    chunk_selection(table, offsets, ids, mvp, v, proj_scale=scale, anchor=anchor)[0]
    assert dict(view.residency.stats) == before


# ── the picture ──────────────────────────────────────────────────────────
def test_a_container_draws_the_molecule_it_holds(view, renderer, atoms):
    """The streamed frame against the same atoms through the impostor path."""
    xyz, radii, rgba = atoms
    state = _camera(view, view.radius * 1.6)
    streamed = renderer.render(_empty(view), state, container=view)

    geometry = scene.Geometry(
        kind="points",
        positions=xyz.astype(np.float32),
        radii=radii.astype(np.float32).reshape(-1, 1),
        colors=rgba.astype(np.float32),
        meta={"world_radius": True},
    )
    reference = renderer.render(
        pack.pack_scene(
            scene.Scene(
                objects=[scene.SceneObject(id="ref", geometry=geometry)],
                center=tuple(view.center),
                radius=view.radius,
            )
        ),
        state,
    )
    # At this distance the atoms are pixels, so the leaves are what should be
    # drawn. (Not *all* of them -- the cull drops the blobs that are off-frame,
    # which is the point of the cull.)
    assert set(view.stats["levels"]) == {0}, view.stats["levels"]
    overlap = _iou(_silhouette(streamed), _silhouette(reference))
    assert overlap > 0.97, f"silhouette IoU {overlap:.4f}"
    lit = _silhouette(streamed)
    assert lit.sum() > 0.05 * lit.size, "the frame is nearly empty"


def test_a_coarse_frame_still_covers_the_structure(view, renderer, atoms):
    """The far frame is beadier, not smaller: LOD must not shrink the model."""
    xyz, radii, rgba = atoms
    state = _camera(view, view.radius * 40)
    coarse = renderer.render(_empty(view), state, container=view)
    assert min(view.stats["levels"]) > 0
    geometry = scene.Geometry(
        kind="points",
        positions=xyz.astype(np.float32),
        radii=radii.astype(np.float32).reshape(-1, 1),
        colors=rgba.astype(np.float32),
        meta={"world_radius": True},
    )
    reference = renderer.render(
        pack.pack_scene(
            scene.Scene(
                objects=[scene.SceneObject(id="ref", geometry=geometry)],
                center=tuple(view.center),
                radius=view.radius,
            )
        ),
        state,
    )
    # "Covers" is the claim, so it is recall that is asserted: the coarse cut
    # must still paint (nearly) everywhere the atoms do. IoU would fail this
    # for the *right* reason -- beads over-cover -- so the over-coverage is
    # bounded separately instead of being folded into one number.
    lit, ref = _silhouette(coarse), _silhouette(reference)
    recall = float((lit & ref).sum() / max(ref.sum(), 1))
    assert recall > 0.9, f"the coarse frame lost {1 - recall:.1%} of the model"
    assert lit.sum() < 2.5 * ref.sum(), "the beads swallowed the structure"


def test_the_gpu_keeps_chunks_and_evicts_them(view, renderer, monkeypatch):
    state = _camera(view, view.radius * 0.6)
    renderer.__dict__.pop("_chunk_vbo_cache", None)
    renderer.__dict__.pop("chunk_stats", None)
    renderer.render(_empty(view), state, container=view)
    first = dict(renderer.chunk_stats)
    assert first["uploads"] >= 1 and first["evictions"] == 0
    renderer.render(_empty(view), state, container=view)
    second = dict(renderer.chunk_stats)
    assert second["hits"] > first["hits"], "the same camera re-uploaded its chunks"
    assert second["uploads"] == first["uploads"]

    monkeypatch.setenv("CHIMOL_CHM_VRAM", str(2 * CHUNK * CHUNK_ROW.itemsize))
    renderer.__dict__.pop("_chunk_vbo_cache", None)
    renderer.__dict__.pop("chunk_stats", None)
    renderer.render(_empty(view), state, container=view)
    assert renderer.chunk_stats["evictions"] >= 1


def test_a_container_and_ordinary_objects_share_one_depth_buffer(view, renderer):
    """A sphere in front of the container occludes it, not the other way round."""
    state = _camera(view, view.radius * 1.6)
    blocker = scene.Geometry(
        kind="points",
        positions=np.array(
            [view.center + np.array([0.0, 0.0, view.radius * 0.5])], dtype=np.float32
        ),
        radii=np.array([[view.radius * 0.35]], dtype=np.float32),
        colors=np.array([[0.1, 0.9, 0.1, 1.0]], dtype=np.float32),
        meta={"world_radius": True},
    )
    packed = pack.pack_scene(
        scene.Scene(
            objects=[scene.SceneObject(id="blocker", geometry=blocker)],
            center=tuple(view.center),
            radius=view.radius,
        )
    )
    frame = renderer.render(packed, state, container=view)
    green = (frame[:, :, 1] > 120) & (frame[:, :, 0] < 90)
    assert green.sum() > 500, "the blocker was drawn over by the container"


# ── the seam a person actually uses ──────────────────────────────────────
def test_the_format_registry_knows_a_container_is_not_a_structure():
    """`load` routes by kind, so this is what makes `load foo.chm.pto` work."""
    from chimol.io.registry import FORMATS

    assert FORMATS.kind_of(pathlib.Path("gigastructure.chm.pto")) == "container"
    assert FORMATS.kind_of(pathlib.Path("protein.cif.gz")) == "structure"


def test_the_demo_names_a_container_the_generated_material_can_build():
    """The demo ships a script, not a container; the container is made once."""
    from chimol.plugins.demos.catalog import DEMOS, read_demo
    from chimol.plugins.demos.material import GENERATED_DEMO_DATA

    script = read_demo("gigastream")
    named = [line.split()[1] for line in script.splitlines() if line.strip().startswith("stream ")]
    assert named, "the streaming demo does not stream anything"
    for name in named:
        assert name in GENERATED_DEMO_DATA, f"{name} is neither shipped nor generated"
    assert any(key == "gigastream" for key, _t, _n in DEMOS), "not in the menu"


def test_streaming_works_in_a_viewer_with_no_toolkit_at_all(container):
    """The whole chain, in a child process: command -> viewer -> canvas -> pixels.

    A container reaches the renderer through ``frame_arguments`` -- the one
    description of a frame every host draws from -- so proving it here proves
    it for the browser too, which builds its frame from the same dictionary.
    """
    probe = pytest.importorskip("toolkit_free").probe
    results = probe(f"""
        import numpy as np
        app = open_app(size=(320, 240))
        app.cmd.do("stream {container}")
        view = app.viewer.container
        emit("opened", view is not None)
        emit("atoms", view.index.meta["n_atoms"])
        frame = np.asarray(app.draw_frame())
        emit("lit", int((frame[..., :3].max(axis=2) > 12).sum()))
        emit("cut", view.stats["atoms"])
        app.cmd.do("delete all")
        emit("closed", app.viewer.container is None)
    """)
    assert results["opened"] == "True"
    assert int(results["atoms"]) == ATOMS
    assert int(results["lit"]) > 500, "the container drew nothing"
    # A cut may name *more* atoms than the container holds: mid-dissolve two
    # levels are drawn, each on part of every pixel.
    assert int(results["cut"]) > 0
    # `delete all` is the first line of every demo script; a container that
    # survived it would leave the next demo streaming the previous one.
    assert results["closed"] == "True"


# ── the level change ─────────────────────────────────────────────────────
def test_a_level_change_is_not_a_pop(view, renderer, atoms):
    """The measurement the whole dissolve exists for.

    A dolly changes the picture on its own, so the claim is a *ratio*: on the
    frames where the cut changed, the picture may not change much more than it
    does on the frames where it did not. Before the dissolve the worst switch
    measured 6.8x an ordinary frame -- that is what a pop is.
    """
    far, near = view.radius * 30, view.radius * 1.2
    steps = 60
    previous_image = previous_cut = None
    switch, steady = [], []
    for i in range(steps):
        distance = far * (near / far) ** (i / (steps - 1))
        frame = renderer.render(_empty(view), _camera(view, distance), container=view).astype(
            np.int16
        )
        cut = (tuple(sorted(view.stats["levels"].items())), view.stats["atoms"])
        if previous_image is not None:
            change = float(np.abs(frame - previous_image).mean())
            (switch if cut != previous_cut else steady).append(change)
        previous_image, previous_cut = frame, cut

    assert switch, "no level changed over the whole dolly"
    # Against the *busiest* ordinary frames, not the median. A dolly's frames
    # are wildly uneven -- most barely change, the ones crossing the structure
    # change a lot -- so the median is not what a level change has to hide
    # among. The claim is that a switch is no bigger a change than an ordinary
    # frame near the top of that distribution.
    busy = float(np.percentile(steady, 95))
    assert max(switch) < 1.5 * busy, (
        f"worst switch {max(switch):.2f} against a busy steady frame's {busy:.2f}"
    )


def test_the_detail_level_steers_itself_towards_the_frame_time(container):
    """Slow frames coarsen the picture; fast ones sharpen it.

    There is no static ``detail_px`` that is right in two places -- on the demo
    container an unbounded cut is 30 ms looking at the whole model and 200 ms
    from inside it -- so the container walks its own, from what frames actually
    cost. Bounded at both ends: a stall cannot reduce the structure to blobs,
    and a fast frame cannot ask for detail finer than the leaves.
    """
    view = ContainerView.open(container)
    try:
        assert view.adaptive
        # From the fine end, so there is room to coarsen: a container opens at
        # the ceiling, which is where the steering starts and cannot go past.
        view.detail_px = float(view.detail_range[0]) * 2.0
        start = view.detail_px
        for _ in range(20):
            view.note_frame(0.200)  # 200 ms frames: too slow
        slow = view.detail_px
        assert slow > start, "slow frames did not coarsen the picture"
        assert slow <= view.detail_range[1]
        for _ in range(60):
            view.note_frame(0.004)  # 4 ms frames: room to spare
        assert view.detail_px < slow, "fast frames did not sharpen the picture"
        assert view.detail_px >= view.detail_range[0]
        # A frame time that cannot be real (a debugger, a suspended tab) is not
        # a signal, and steering on it would coarsen the picture for good.
        pinned = view.detail_px
        view.note_frame(30.0)
        view.note_frame(-1.0)
        assert view.detail_px == pinned
    finally:
        view.close()


def test_naming_a_detail_level_pins_it(container):
    """`stream <file> 4` means 4, not "start at 4 and drift"."""
    view = ContainerView.open(container, detail_px=4.0)
    try:
        assert not view.adaptive
        for _ in range(20):
            view.note_frame(0.500)
        assert view.detail_px == 4.0
    finally:
        view.close()


# ── the coarse levels are Gaussians ──────────────────────────────────────
def test_a_parent_level_is_gaussians_and_the_leaves_are_atoms(container):
    """Two row kinds in one container, and the index says which is which."""
    from chimol.render.chm import CHUNK_GAUSS_ROW, CHUNK_ROW, ROW_ATOMS, ROW_GAUSS

    index = ChmIndex.open(container)
    try:
        table = index.table
        leaves = index.level(0)
        assert set(table["kind"][leaves].tolist()) == {ROW_ATOMS}
        assert (table["nbytes"][leaves] == table["count"][leaves] * CHUNK_ROW.itemsize).all()
        for level in range(1, index.n_levels):
            ids = index.level(level)
            assert set(table["kind"][ids].tolist()) == {ROW_GAUSS}, level
            assert (table["nbytes"][ids] == table["count"][ids] * CHUNK_GAUSS_ROW.itemsize).all()
    finally:
        index.close()


def test_a_gaussian_stands_for_the_spread_of_what_it_replaces(container, atoms):
    """The fit is moment-matching, so the covariance must come back out.

    This is what makes a level a *low-pass* of the level below rather than a
    thinner copy of it: an L2 Gaussian carries the spread of the L1 Gaussians
    under it, which carry the spread of the atoms.
    """
    from chimol.render.chm import CHUNK_GAUSS_ROW, ChunkResidency

    index = ChmIndex.open(container)
    try:
        residency = ChunkResidency(index, 1 << 24)
        table = index.table
        for level in range(1, index.n_levels):
            for chunk in index.level(level):
                row = table[chunk]
                rows = np.frombuffer(residency.rows(int(chunk)), dtype=CHUNK_GAUSS_ROW)
                span = float(row["r_max"]) - float(row["r_min"])
                sigma = float(row["r_min"]) + rows["scale"][:, :3] / 65535.0 * span
                assert (sigma > 0).all(), "a Gaussian with no extent"
                quat = rows["rot"].astype(np.float64) / 127.0
                assert np.abs(np.linalg.norm(quat, axis=1) - 1.0).max() < 0.05
                # A level is coarser than the one below it, never finer.
                if level > 1:
                    below = table["bead"][index.children(int(chunk))]
                    assert float(row["bead"]) >= float(below.max()) * 0.9
    finally:
        index.close()


def test_the_coarse_levels_still_look_like_the_molecule(view, renderer, atoms):
    """Every level, against the atoms it stands for -- silhouette and pixels.

    The bar is what the sphere beads this replaced could not clear: measured on
    real molecular data, an L2 of beads reached IoU 0.55 and a mean pixel error
    of 103, against 0.73 and 52 for the Gaussians -- because a group of eight
    Morton-adjacent atoms is 5.2x longer than it is wide and a sphere has to
    swallow it whole.
    """
    xyz, radii, rgba = atoms
    geometry = scene.Geometry(
        kind="points",
        positions=xyz.astype(np.float32),
        radii=radii.astype(np.float32).reshape(-1, 1),
        colors=rgba.astype(np.float32),
        meta={"world_radius": True},
    )
    reference = renderer.render(
        pack.pack_scene(
            scene.Scene(
                objects=[scene.SceneObject(id="ref", geometry=geometry)],
                center=tuple(view.center),
                radius=view.radius,
            )
        ),
        _camera(view, view.radius * 2.2),
    )

    for level in range(1, view.index.n_levels):
        ids = view.index.level(level)
        if not len(ids):
            continue
        view.select = lambda *a, **k: ids  # noqa: B023
        frame = renderer.render(_empty(view), _camera(view, view.radius * 2.2), container=view)
        lit, ref = _silhouette(frame), _silhouette(reference)
        assert lit.sum() > 0, f"level {level} drew nothing"
        # It may not shrink the molecule, and it may not swell into a blob.
        assert (lit & ref).sum() / max(ref.sum(), 1) > 0.75, f"level {level} lost the shape"
        assert lit.sum() < 2.0 * ref.sum(), f"level {level} swelled to {lit.sum() / ref.sum():.1f}x"


def test_a_coarse_level_is_drawn_like_an_atom_not_like_fog(container, renderer, atoms):
    """The coarse levels shade the way the leaves do.

    A level of detail may change the *shape* it draws with; it may not change
    the material. Soft, low-contrast blobs beside crisp shaded spheres do not
    read as the same structure at a different distance -- they read as fog
    rolling in, which is what the first version (blended Gaussian splats) did.
    Ellipsoid impostors are ray-traced and shaded by the same `shade()`, so the
    only thing that changes across a level is how many there are.

    Checked on brightness and contrast rather than by eye: a fogged level is
    dimmer and flatter than the atoms it stands for.
    """
    xyz, radii, rgba = atoms
    view = ContainerView.open(container, detail_px=4.0)
    try:
        state = _camera(view, view.radius * 2.2)
        leaves = view.index.level(0)
        view.weight = np.ones(len(leaves))
        view.select = lambda *a, _i=leaves, **k: _i
        fine = renderer.render(_empty(view), state, container=view)
        lit = _silhouette(fine)
        assert lit.sum() > 500
        fine_mean = float(fine[lit].mean())
        fine_spread = float(fine[lit].std())

        for level in range(1, view.index.n_levels):
            ids = view.index.level(level)
            if not len(ids):
                continue
            view.weight = np.ones(len(ids))
            view.select = lambda *a, _i=ids, **k: _i
            coarse = renderer.render(_empty(view), state, container=view)
            mask = _silhouette(coarse)
            assert mask.sum() > 100, f"level {level} drew nothing"
            # Within a stop of the leaves' brightness, and not washed flat.
            assert float(coarse[mask].mean()) > 0.5 * fine_mean, f"level {level} is dim"
            assert float(coarse[mask].std()) > 0.5 * fine_spread, f"level {level} is flat"
    finally:
        view.close()
