"""AV size and sphere overlap metrics."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union, Sequence

import numpy as np

from .base import Evaluator, EvaluatorResult


class AVSizeEvaluator(Evaluator):
    """Evaluates the spatial size of an accessible volume as its radius of gyration.

    The (weight-aware) radius of gyration measures how far the accessible-volume
    point cloud spreads about its mean position, in Å:

    .. math::

        R_g = \\sqrt{\\frac{\\sum_i w_i\\,\\lVert r_i - \\bar r\\rVert^2}{\\sum_i w_i}}

    This is distinct from the point count (:class:`~..positions.PositionEvaluator`)
    and the physical volume (:class:`~..positions.AVVolumeEvaluator`): a compact and
    a diffuse AV can share a volume yet differ in spatial extent.
    """

    def __init__(self, name: str, position_name: str) -> None:
        super().__init__(name)
        self.position_name = position_name

    def evaluate(
        self,
        av_cache: Dict[str, Any],
        bodies: Optional[List[Any]] = None,
    ) -> EvaluatorResult:
        av = av_cache.get(self.position_name)
        if av is None or not av.has_volume:
            return EvaluatorResult(self.name, 0.0, "Å")
        pts = av.points[:, :3]
        w = av.points[:, 3]
        sum_w = w.sum()
        if sum_w == 0:
            return EvaluatorResult(self.name, 0.0, "Å")
        mean = np.average(pts, axis=0, weights=w)
        msd = np.average(np.sum((pts - mean) ** 2, axis=1), weights=w)
        return EvaluatorResult(self.name, float(np.sqrt(msd)), "Å")


class AVSphereOverlapEvaluator(Evaluator):
    """Evaluates the fraction of AV points inside a given sphere."""

    def __init__(
        self,
        name: str,
        position_name: str,
        center: Union[np.ndarray, Sequence[float]],
        radius: float,
    ) -> None:
        super().__init__(name)
        self.position_name = position_name
        self.center = np.asarray(center, dtype=np.float64)
        self.radius = radius

    def evaluate(
        self,
        av_cache: Dict[str, Any],
        bodies: Optional[List[Any]] = None,
    ) -> EvaluatorResult:
        av = av_cache.get(self.position_name)
        if av is None or not av.has_volume:
            return EvaluatorResult(self.name, 0.0, "")

        pts = av.points[:, :3]
        w = av.points[:, 3]
        dists = np.linalg.norm(pts - self.center, axis=1)
        inside = dists <= self.radius

        sum_w = w.sum()
        if sum_w == 0:
            val = 0.0
        else:
            val = float(w[inside].sum() / sum_w)

        return EvaluatorResult(self.name, val, "")
