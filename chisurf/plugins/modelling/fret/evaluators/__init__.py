"""OLGA-style evaluators package."""

from __future__ import annotations

from typing import Any, Dict

from .av_metrics import AVSizeEvaluator, AVSphereOverlapEvaluator
from .base import EvaluationStorage, Evaluator, EvaluatorResult
from .chi2 import Chi2ContributionEvaluator, Chi2Evaluator, ReducedChi2Evaluator
from .distance import DistanceDistributionEvaluator, DistanceEvaluator
from .fret_efficiency import FretEfficiencyEvaluator
from .geometry import EulerAngleEvaluator, MinDistanceEvaluator, TranslationEvaluator
from .positions import AVVolumeEvaluator, PositionEvaluator
from .residuals import WeightedResidualEvaluator

EVALUATOR_CLASSES = {
    "PositionEvaluator": PositionEvaluator,
    "AVVolumeEvaluator": AVVolumeEvaluator,
    "DistanceEvaluator": DistanceEvaluator,
    "DistanceDistributionEvaluator": DistanceDistributionEvaluator,
    "FretEfficiencyEvaluator": FretEfficiencyEvaluator,
    "Chi2Evaluator": Chi2Evaluator,
    "ReducedChi2Evaluator": ReducedChi2Evaluator,
    "Chi2ContributionEvaluator": Chi2ContributionEvaluator,
    "WeightedResidualEvaluator": WeightedResidualEvaluator,
    "EulerAngleEvaluator": EulerAngleEvaluator,
    "TranslationEvaluator": TranslationEvaluator,
    "MinDistanceEvaluator": MinDistanceEvaluator,
    "AVSizeEvaluator": AVSizeEvaluator,
    "AVSphereOverlapEvaluator": AVSphereOverlapEvaluator,
}


def from_dict(d: dict[str, Any]) -> Evaluator:
    """Instantiate an Evaluator from its serialized dictionary format.

    Parameters
    ----------
    d : dict
        Serialized representation of the evaluator.

    Returns
    -------
    evaluator : Evaluator
        Instantiated evaluator.
    """
    etype = d.get("type")
    if not etype:
        raise ValueError("Missing 'type' key in evaluator specification")
    cls = EVALUATOR_CLASSES.get(etype)
    if not cls:
        raise ValueError(f"Unknown evaluator type: '{etype}'")
    return cls.from_dict(d)
