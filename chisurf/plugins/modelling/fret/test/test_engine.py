"""Headless tests for the rigid-body docking data model + IMP-free pose scoring.

Covers PRD-58 rigid-body-docking (RBD) pieces that were implemented but untested:

* ``RigidBody`` coordinate transforms (``core/engine.py``).
* ``DistanceRestraint.global_position_a/b`` + ``get_effective_distance``.
* ``core.evaluate.score_bodies`` — the IMP-free pose → chi² scorer.
* the three geometry evaluators (Euler / Translation / MinDistance).
* ``core.distance.chi2_score`` asymmetric-error branch selection.

Pure numpy — no IMP, AV backend, or external data.
"""

from __future__ import annotations

import numpy as np
import pytest

from ..core.distance import chi2_score
from ..core.engine import DistanceRestraint, RigidBody
from ..core.evaluate import score_bodies
from ..evaluators import EulerAngleEvaluator, MinDistanceEvaluator, TranslationEvaluator


def _rot_z(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _body(name, coords, com=(0.0, 0.0, 0.0), rotation=None):
    coords = np.asarray(coords, dtype=np.float64)
    atoms_local = np.column_stack([coords, np.ones(len(coords))])
    com = np.asarray(com, dtype=np.float64)
    rotation = np.eye(3) if rotation is None else rotation
    return RigidBody(
        name=name,
        atoms_local=atoms_local,
        com=com.copy(),
        rotation=rotation,
        translation=com.copy(),
    )


def _restraint(**kw):
    base = dict(
        name="AB",
        body_a=0,
        offset_a=np.array([1.0, 0.0, 0.0]),
        body_b=1,
        offset_b=np.zeros(3),
        distance_exp=6.0,
        error_neg=3.0,
        error_pos=3.0,
        transfer_function_type="None",
    )
    base.update(kw)
    return DistanceRestraint(**base)


# --------------------------------------------------------------------------------------
# RigidBody transforms
# --------------------------------------------------------------------------------------
def test_rigid_body_global_coords():
    # local +x, body rotated 90° about z and translated
    body = _body("a", [[1.0, 0.0, 0.0]], com=[10.0, 0.0, 0.0], rotation=_rot_z(np.pi / 2))
    g = body.global_coords()
    np.testing.assert_allclose(g[0], [10.0, 1.0, 0.0], atol=1e-9)  # +x -> +y, +com
    xyzr = body.global_xyzr()
    assert xyzr.shape == (1, 4)
    assert xyzr[0, 3] == pytest.approx(1.0)  # radius preserved


# --------------------------------------------------------------------------------------
# DistanceRestraint
# --------------------------------------------------------------------------------------
def test_distance_restraint_global_positions_and_effective_distance():
    bodies = [_body("A", [[0, 0, 0]], com=[0, 0, 0]), _body("B", [[0, 0, 0]], com=[10, 0, 0])]
    r = _restraint()
    np.testing.assert_allclose(r.global_position_a(bodies), [1.0, 0.0, 0.0])
    np.testing.assert_allclose(r.global_position_b(bodies), [10.0, 0.0, 0.0])
    assert r.get_effective_distance(9.0) == pytest.approx(9.0)  # "None" transfer = identity


# --------------------------------------------------------------------------------------
# score_bodies — IMP-free pose scorer
# --------------------------------------------------------------------------------------
def test_score_bodies_chi2():
    bodies = [_body("A", [[0, 0, 0]], com=[0, 0, 0]), _body("B", [[0, 0, 0]], com=[10, 0, 0])]
    # rmp = |[1,0,0] - [10,0,0]| = 9; chi2 = (9-6)^2 / 3^2 = 1
    total, per = score_bodies(bodies, [_restraint()])
    assert total == pytest.approx(1.0)
    assert len(per) == 1
    name, rmp, d_model, chi2 = per[0]
    assert name == "AB"
    assert rmp == pytest.approx(9.0)
    assert d_model == pytest.approx(9.0)
    assert chi2 == pytest.approx(1.0)


def test_score_bodies_skips_inactive():
    bodies = [_body("A", [[0, 0, 0]]), _body("B", [[0, 0, 0]], com=[10, 0, 0])]
    total, per = score_bodies(bodies, [_restraint(active=False)], only_active=True)
    assert total == pytest.approx(0.0)
    assert per == []


# --------------------------------------------------------------------------------------
# geometry evaluators
# --------------------------------------------------------------------------------------
def test_translation_evaluator():
    bodies = [_body("A", [[0, 0, 0]], com=[1.0, 2.0, 3.0])]
    res = TranslationEvaluator("t", 0, 1).evaluate({}, bodies)  # y component
    assert res.value == pytest.approx(2.0)
    assert res.unit == "Å"


def test_euler_angle_evaluator_z_rotation():
    bodies = [_body("A", [[0, 0, 0]], rotation=_rot_z(np.pi / 4))]
    # pure z-rotation → beta = 0, gamma = theta
    gamma = EulerAngleEvaluator("g", 0, 2).evaluate({}, bodies).value
    assert gamma == pytest.approx(np.pi / 4)


def test_min_distance_evaluator():
    bodies = [_body("A", [[0, 0, 0]], com=[0, 0, 0]), _body("B", [[0, 0, 0]], com=[5, 0, 0])]
    assert MinDistanceEvaluator("m", 0, 1).evaluate({}, bodies).value == pytest.approx(5.0)


def test_geometry_evaluators_guard_without_bodies():
    assert TranslationEvaluator("t", 0, 0).evaluate({}, None).value == pytest.approx(0.0)
    assert EulerAngleEvaluator("g", 0, 0).evaluate({}, None).value == pytest.approx(0.0)
    assert MinDistanceEvaluator("m", 0, 1).evaluate({}, None).value == pytest.approx(0.0)


# --------------------------------------------------------------------------------------
# chi2_score asymmetric branch
# --------------------------------------------------------------------------------------
def test_chi2_score_asymmetric_branches():
    assert chi2_score(9.0, 6.0, 2.0, 4.0) == pytest.approx((3 / 4) ** 2)  # delta>0 → error_pos
    assert chi2_score(3.0, 6.0, 2.0, 4.0) == pytest.approx((3 / 2) ** 2)  # delta<0 → error_neg
    assert chi2_score(6.0, 6.0, 2.0, 4.0) == pytest.approx(0.0)
    assert chi2_score(9.0, 6.0, 0.0, 0.0) == pytest.approx(0.0)  # err<=0 → 0
