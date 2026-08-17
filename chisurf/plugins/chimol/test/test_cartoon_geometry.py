"""Tests for Chimol cartoon geometry generation.

These tests validate the mesh output from the cartoon extrude pipeline
without requiring Qt or OpenGL.
"""

import numpy as np
import pytest

from chimol.geometry.cartoon import (
    _generate_cartoon_tube_arrays,
    _flatten_sheet_path,
    _helix_radials,
    _path_parameterisation,
    _refine_orientations,
    _round_helix_path,
    _sample_path,
    _sample_orientations,
    _propagate_ups,
    _build_frames,
    _make_circle_shape,
    _make_oval_shape,
    _make_rectangle_shape,
    _extrude_shape,
    _extrude_arrowhead,
    _segment_ss,
)


def ideal_helix(n=14, radius=2.3, rise=1.5, twist_deg=100.0):
    """CA positions of an ideal alpha helix about the +z axis."""
    ang = np.radians(twist_deg) * np.arange(n)
    return np.column_stack([
        radius * np.cos(ang), radius * np.sin(ang), rise * np.arange(n),
    ])


# -- Fixtures --

@pytest.fixture
def coords4():
    return np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], dtype=float)


@pytest.fixture
def colors4():
    return np.array([[1, 0, 0, 1], [0, 1, 0, 1], [0, 0, 1, 1], [1, 1, 0, 1]],
                    dtype=float)


@pytest.fixture
def coords10():
    return np.array([[i, 0, 0] for i in range(10)], dtype=float)


@pytest.fixture
def colors10():
    return np.tile([1, 0, 0, 1], (10, 1)).astype(float)


# -- Shape profile tests --

class TestShapeProfiles:

    def test_circle_has_expected_verts(self):
        sv, sn = _make_circle_shape(16, 1.0)
        assert sv.shape == (16, 3)
        assert sn.shape == (16, 3)
        # All verts have z=0
        assert np.allclose(sv[:, 0], 0.0)
        # Radius is 1.0
        radii = np.linalg.norm(sv[:, 1:], axis=1)
        assert np.allclose(radii, 1.0)

    def test_circle_normals_are_unit(self):
        _, sn = _make_circle_shape(16, 1.0)
        norms = np.linalg.norm(sn, axis=1)
        assert np.allclose(norms, 1.0)

    def test_oval_shape(self):
        # width = thickness along the frame's up axis (shape z);
        # length = breadth across the ribbon, on the side axis (shape y).
        # Swapping the two rotates every ribbon 90 degrees about its own path.
        sv, sn = _make_oval_shape(16, 2.0, 3.0)
        assert sv.shape == (16, 3)
        assert sn.shape == (16, 3)
        assert np.allclose(sv[:, 0], 0.0)
        assert np.max(sv[:, 1]) == pytest.approx(3.0, abs=0.01)
        assert np.max(sv[:, 2]) == pytest.approx(2.0, abs=0.01)

    def test_rectangle_is_broader_than_it_is_thick(self):
        # Same axis contract as the oval: PyMOL's cartoon_rect_length is the
        # breadth (side axis), cartoon_rect_width the thickness (up axis).
        sv, _ = _make_rectangle_shape(0.4, 1.4)
        assert np.max(sv[:, 1]) > np.max(sv[:, 2])
        assert np.max(sv[:, 1]) == pytest.approx(1.4 * np.cos(np.pi / 4), abs=1e-6)
        assert np.max(sv[:, 2]) == pytest.approx(0.4 * np.sin(np.pi / 4), abs=1e-6)

    def test_oval_normals_are_unit(self):
        _, sn = _make_oval_shape(16, 2.0, 3.0)
        norms = np.linalg.norm(sn, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-6)

    def test_rectangle_shape(self):
        sv, sn = _make_rectangle_shape(2.0, 0.3)
        assert sv.shape == (8, 3)
        assert sn.shape == (8, 3)
        assert np.allclose(sv[:, 0], 0.0)

    def test_rectangle_normals_are_unit(self):
        _, sn = _make_rectangle_shape(2.0, 0.3)
        norms = np.linalg.norm(sn, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-6)


# -- SS segmenter tests --

class TestSegmenter:

    def test_none_ss_returns_empty(self):
        assert _segment_ss(None) == []
        assert _segment_ss(np.array([])) == []

    def test_all_helix(self):
        segs = _segment_ss(np.array(['H', 'H', 'H'], dtype='U1'))
        assert len(segs) == 1
        assert segs[0]['ss_type'] == 'H'
        assert segs[0] == {'start': 0, 'end': 3, 'ss_type': 'H'}

    def test_mixed(self):
        segs = _segment_ss(np.array(['H', 'H', 'E', 'E', 'C'], dtype='U1'))
        assert len(segs) == 3
        assert segs[0] == {'start': 0, 'end': 2, 'ss_type': 'H'}
        assert segs[1] == {'start': 2, 'end': 4, 'ss_type': 'E'}
        assert segs[2] == {'start': 4, 'end': 5, 'ss_type': 'C'}

    def test_single_residue_types(self):
        segs = _segment_ss(np.array(['H', 'E', 'C'], dtype='U1'))
        assert len(segs) == 3


# -- Extrude tests --

class TestExtrude:

    def test_extrude_circle(self, coords4, colors4):
        path, pc = _sample_path(coords4, colors4, subdivisions=6)
        t, up = _propagate_ups(path, None)
        frames = _build_frames(t, up)
        sv, sn = _make_circle_shape(16, 1.0)
        result = _extrude_shape(path, frames, sv, sn, pc, cap_ends=True)
        assert result is not None
        verts, norms, faces, cols = result
        assert verts.shape[0] > 0
        assert faces.shape[0] > 0
        assert cols is not None
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)
        assert np.all(np.isfinite(verts))

    def test_extrude_oval(self, coords4, colors4):
        path, pc = _sample_path(coords4, colors4, subdivisions=6)
        t, up = _propagate_ups(path, None)
        frames = _build_frames(t, up)
        sv, sn = _make_oval_shape(16, 1.0, 1.5)
        result = _extrude_shape(path, frames, sv, sn, pc, cap_ends=True)
        assert result is not None
        verts, norms, faces, cols = result
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)

    def test_extrude_rectangle(self, coords4, colors4):
        path, pc = _sample_path(coords4, colors4, subdivisions=6)
        t, up = _propagate_ups(path, None)
        frames = _build_frames(t, up)
        sv, sn = _make_rectangle_shape(2.0, 0.3)
        result = _extrude_shape(path, frames, sv, sn, pc, cap_ends=True)
        assert result is not None
        verts, norms, faces, cols = result
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)

    def test_extrude_arrowhead(self, coords4, colors4):
        path, pc = _sample_path(coords4, colors4, subdivisions=6)
        t, up = _propagate_ups(path, None)
        frames = _build_frames(t, up)
        sv, sn = _make_rectangle_shape(2.0, 0.3)
        result = _extrude_arrowhead(path, frames, sv, sn, pc, 2)
        assert result is not None
        verts, norms, faces, cols = result
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)
        assert np.all(np.isfinite(verts))

    def test_short_path_returns_none(self, colors4):
        path = np.zeros((1, 3), dtype=float)
        sv = np.zeros((4, 3), dtype=float)
        sn = np.zeros((4, 3), dtype=float)
        assert _extrude_shape(path, np.zeros((1, 3, 3)), sv, sn, None) is None


# -- Public entry-point tests --

class TestGenerateCartoon:

    def test_tube_style(self, coords4, colors4):
        result = _generate_cartoon_tube_arrays(coords4, colors4, style='tube')
        assert result is not None
        verts, norms, faces, cols = result
        assert verts.shape[0] > 0
        assert faces.shape[0] > 0
        assert cols is not None
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)
        assert np.all(np.isfinite(verts))

    def test_ribbon_no_ss_fallback(self, coords4, colors4):
        result = _generate_cartoon_tube_arrays(coords4, colors4, style='ribbon')
        assert result is not None

    @pytest.mark.parametrize('ss,label', [
        (['H', 'H', 'H', 'H'], 'helix'),
        (['E', 'E', 'E', 'E'], 'strand'),
        (['C', 'C', 'C', 'C'], 'loop'),
    ])
    def test_ribbon_uniform_ss(self, coords4, colors4, ss, label):
        result = _generate_cartoon_tube_arrays(
            coords4, colors4,
            ss_codes=np.array(ss, dtype='U1'),
            style='ribbon',
        )
        assert result is not None, f'{label} returned None'
        verts, norms, faces, cols = result
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)

    def test_ribbon_big_chain(self, coords10, colors10):
        ss = np.array(['C', 'C', 'H', 'H', 'H',
                       'E', 'E', 'E', 'C', 'C'], dtype='U1')
        result = _generate_cartoon_tube_arrays(
            coords10, colors10,
            ss_codes=ss, style='ribbon',
        )
        assert result is not None
        verts, norms, faces, cols = result
        assert verts.shape[0] > 0
        assert faces.shape[0] > 0
        assert np.allclose(np.linalg.norm(norms, axis=1), 1.0, atol=1e-5)

    def test_short_chain_returns_none(self, colors4):
        coords = np.zeros((1, 3), dtype=float)
        result = _generate_cartoon_tube_arrays(coords, colors4[:1])
        assert result is None

    def test_no_nans(self, coords10, colors10):
        ss = np.array(['H', 'E', 'C'] * 3 + ['H'], dtype='U1')
        result = _generate_cartoon_tube_arrays(
            coords10, colors10,
            ss_codes=ss, style='ribbon',
        )
        if result is not None:
            verts, norms, faces, cols = result
            assert np.all(np.isfinite(verts))
            assert np.all(np.isfinite(norms))
            assert np.all(np.isfinite(faces))

    def test_single_residue_ss_blocks_do_not_drop_geometry(self, coords4, colors4):
        ss = np.array(['C', 'H', 'E', 'C'], dtype='U1')
        result = _generate_cartoon_tube_arrays(
            coords4, colors4,
            ss_codes=ss, style='ribbon',
        )
        assert result is not None
        verts, norms, faces, cols = result
        assert verts.shape[0] > 0
        assert faces.shape[0] > 0


# -- PyMOL-parity behaviours --

class TestRoundHelices:
    """PyMOL's ``cartoon_round_helices``: the ribbon follows the cylinder."""

    def test_radials_point_outward_from_the_axis(self):
        ca = ideal_helix()
        is_helix = np.ones(ca.shape[0], dtype=bool)
        radial, has_radial = _helix_radials(ca, is_helix)
        assert has_radial.all(), "every residue of a helix run needs a radial"
        for i, p in enumerate(ca):
            expected = np.array([p[0], p[1], 0.0])
            expected /= np.linalg.norm(expected)
            assert float(radial[i] @ expected) > 0.99

    def test_path_stays_on_the_cylinder_between_residues(self):
        # A plain Catmull-Rom through 100-degree-spaced points sags to ~0.83 of
        # the radius midway between residues; the round-helix pass must not.
        ca = ideal_helix()
        is_helix = np.ones(ca.shape[0], dtype=bool)
        path, _ = _sample_path(ca, None, subdivisions=7)
        raw = np.linalg.norm(path[:, :2], axis=1)
        assert raw.min() < 0.9 * 2.3, "expected the raw spline to cut the corner"

        rounded = _round_helix_path(path, ca, is_helix, subdivisions=7)
        r = np.linalg.norm(rounded[:, :2], axis=1)
        assert np.allclose(r, 2.3, atol=0.02)

    def test_path_still_passes_through_every_ca(self):
        ca = ideal_helix()
        is_helix = np.ones(ca.shape[0], dtype=bool)
        path, _ = _sample_path(ca, None, subdivisions=7)
        rounded = _round_helix_path(path, ca, is_helix, subdivisions=7)
        seg, t = _path_parameterisation(ca.shape[0], 7)
        for i in range(1, ca.shape[0] - 1):
            k = int(np.flatnonzero((seg == i) & (t == 0.0))[0])
            assert np.linalg.norm(rounded[k] - ca[i]) < 1e-6

    def test_leaves_non_helix_residues_alone(self):
        ca = ideal_helix()
        is_helix = np.zeros(ca.shape[0], dtype=bool)
        path, _ = _sample_path(ca, None, subdivisions=7)
        assert np.array_equal(_round_helix_path(path, ca, is_helix, 7), path)


class TestFlatSheets:
    """PyMOL's ``cartoon_flat_sheets``: the strand path is de-pleated."""

    @staticmethod
    def pleated_strand(n=6, rise=3.3, pleat=0.9):
        pts = np.zeros((n, 3))
        pts[:, 0] = rise * np.arange(n)
        pts[:, 1] = pleat * (-1.0) ** np.arange(n)
        return pts

    def test_removes_most_of_the_pleat(self):
        ca = self.pleated_strand()
        is_sheet = np.ones(ca.shape[0], dtype=bool)
        before = np.abs(ca[1:-1, 1] - 0.5 * (ca[:-2, 1] + ca[2:, 1])).mean()
        out, _ = _flatten_sheet_path(ca, is_sheet, cycles=4)
        after = np.abs(out[1:-1, 1] - 0.5 * (out[:-2, 1] + out[2:, 1])).mean()
        assert after < 0.25 * before

    def test_endpoints_and_non_strand_residues_do_not_move(self):
        ca = self.pleated_strand(n=8)
        is_sheet = np.zeros(ca.shape[0], dtype=bool)
        is_sheet[2:6] = True
        out, _ = _flatten_sheet_path(ca, is_sheet, cycles=4)
        # The run's own end points anchor it too, per PyMOL's first+f..last-f.
        assert np.array_equal(out[:3], ca[:3])
        assert np.array_equal(out[5:], ca[5:])

    def test_no_op_without_strands(self):
        ca = self.pleated_strand()
        out, ups = _flatten_sheet_path(
            ca, np.zeros(ca.shape[0], dtype=bool), cycles=4
        )
        assert np.array_equal(out, ca)
        assert ups is None


    def test_it_uses_pymols_uniform_average(self):
        """``RepCartoonFlattenSheets`` averages a point with its two neighbours.

        A weighted kernel such as (1, 2, 1)/4 looks similar but converges more
        slowly, leaving a visible pleat after the four cycles PyMOL runs.
        """
        ca = self.pleated_strand(n=7)
        is_sheet = np.ones(ca.shape[0], dtype=bool)
        out, _ = _flatten_sheet_path(ca, is_sheet, cycles=1)
        expected = (ca[0:5, 1] + ca[1:6, 1] + ca[2:7, 1]) / 3.0
        assert np.allclose(out[1:6, 1], expected)

    def test_up_vectors_are_smoothed_with_the_path(self):
        """Smoothing the path but not the ribbon's face keeps half the twist."""
        ca = self.pleated_strand(n=7)
        is_sheet = np.ones(ca.shape[0], dtype=bool)
        ups = np.zeros_like(ca)
        ups[:, 1] = (-1.0) ** np.arange(ca.shape[0])   # pleated up-vectors
        _, out_ups = _flatten_sheet_path(ca, is_sheet, cycles=4, ups=ups)
        assert out_ups is not None
        # The alternation is gone from the interior...
        interior = out_ups[1:-1]
        assert np.abs(np.diff(interior[:, 1])).max() < 0.5
        # ...and every smoothed vector is still unit length.
        assert np.allclose(np.linalg.norm(interior, axis=1), 1.0, atol=1e-9)

    def test_up_vectors_stay_perpendicular_to_the_path(self):
        """PyMOL re-orthogonalises against normalize(p[b+1] - p[b-1])."""
        ca = self.pleated_strand(n=7)
        is_sheet = np.ones(ca.shape[0], dtype=bool)
        ups = np.tile(np.array([0.4, 0.9, 0.2]), (ca.shape[0], 1))
        out, out_ups = _flatten_sheet_path(ca, is_sheet, cycles=4, ups=ups)
        tangent = out[2:-1] - out[0:-3]
        tangent /= np.linalg.norm(tangent, axis=1, keepdims=True)
        along = np.einsum("ij,ij->i", out_ups[1:-2], tangent)
        assert np.abs(along).max() < 1e-9


class TestOrientationSampling:
    """Ribbon normals are slerped, and helix rotation is not mistaken for a flip."""

    def test_slerp_keeps_vectors_on_the_arc(self):
        ups = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        out = _sample_orientations(ups, subdivisions=4)
        assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
        # midway between two perpendicular vectors is the 45-degree bisector
        mid = out[2]
        assert mid[0] == pytest.approx(np.cos(np.pi / 4), abs=1e-6)
        assert mid[1] == pytest.approx(np.sin(np.pi / 4), abs=1e-6)

    def test_layout_matches_sample_path(self):
        ca = ideal_helix(n=6)
        path, _ = _sample_path(ca, None, subdivisions=5)
        ups = _sample_orientations(np.tile([0.0, 0.0, 1.0], (6, 1)), subdivisions=5)
        assert ups.shape[0] == path.shape[0]

    def test_helix_normals_are_not_sign_flipped(self):
        # Consecutive helix normals sit ~100 degrees apart, so a naive
        # "dot < 0 -> negate" rule would flip every single residue.
        ca = ideal_helix()
        ss = np.array(["H"] * ca.shape[0], dtype="U1")
        vo = np.tile([0.0, 0.0, 1.0], (ca.shape[0], 1)).astype(float)
        refined = _refine_orientations(ca, vo, ss)
        radial = ca.copy()
        radial[:, 2] = 0.0
        radial /= np.linalg.norm(radial, axis=1, keepdims=True)
        dots = np.einsum("ij,ij->i", refined, radial)
        # No normal may point inward: a sign flip would show up as dot < 0.
        assert (dots > 0.0).all(), dots
        # Away from the run's ends, where the tangent is only a chord estimate,
        # each normal is the outward radial to within a degree or so.
        assert (dots[1:-1] > 0.99).all(), dots


class TestSmoothLoops:
    """``cartoon_smooth_loops`` -- ``RepCartoonSmoothLoops``.

    Off by default in PyMOL and here, because rounding the coil pulls it away
    from the real backbone. Implemented so the setting is not a lie.
    """

    @staticmethod
    def kinked_loop(n: int = 11):
        ca = np.zeros((n, 3))
        ca[:, 0] = np.arange(n) * 3.3
        ca[4:7, 1] = [3.0, -3.0, 3.0]        # a zig-zag in the coil
        loop = np.zeros(n, dtype=bool)
        loop[3:8] = True
        return ca, loop

    def test_it_rounds_the_coil(self):
        from chimol.geometry.cartoon import _smooth_loop_path

        ca, loop = self.kinked_loop()
        out, _ = _smooth_loop_path(ca, loop, cycles=2)
        rough = np.abs(np.diff(ca[3:8, 1], 2)).sum()
        smooth = np.abs(np.diff(out[3:8, 1], 2)).sum()
        assert smooth < 0.2 * rough

    def test_the_flanking_elements_are_not_dragged_along(self):
        """The run widens by one residue, no further."""
        from chimol.geometry.cartoon import _smooth_loop_path

        ca, loop = self.kinked_loop()
        out, _ = _smooth_loop_path(ca, loop, cycles=2)
        assert np.allclose(out[:2], ca[:2])
        assert np.allclose(out[9:], ca[9:])

    def test_up_vectors_are_smoothed_and_stay_unit(self):
        from chimol.geometry.cartoon import _smooth_loop_path

        ca, loop = self.kinked_loop()
        ups = np.zeros_like(ca)
        ups[:, 2] = 1.0
        ups[5, 2] = 0.0
        ups[5, 1] = 1.0
        _, out_ups = _smooth_loop_path(ca, loop, cycles=2, ups=ups)
        assert out_ups is not None
        assert np.allclose(np.linalg.norm(out_ups, axis=1), 1.0)

    def test_zero_cycles_and_no_loops_are_both_no_ops(self):
        from chimol.geometry.cartoon import _smooth_loop_path

        ca, loop = self.kinked_loop()
        assert np.allclose(_smooth_loop_path(ca, loop, cycles=0)[0], ca)
        assert np.allclose(
            _smooth_loop_path(ca, np.zeros(ca.shape[0], dtype=bool), cycles=2)[0],
            ca,
        )

    def test_it_is_off_by_default(self):
        """PyMOL ships it off; a rounder loop is further from the truth."""
        from chimol.core.settings import registry as settings

        assert settings.get_setting("cartoon_smooth_loops") is False
