"""Two-channel colocalization analysis for microscopy images.

Colocalization is asked in two regimes, and they need different mathematics:

* **Pixel-wise** (:mod:`~.pixelwise`) — every pixel is a sample of two intensities
  and the answer is a correlation/co-occurrence coefficient. This is the right
  regime for continuous, overlapping distributions (a cytosolic protein and a
  membrane marker), and it is what Pearson, Manders, Costes, Li, Spearman and van
  Steensel all measure.
* **Object-based** (:mod:`~.objects`) — the signal is a set of discrete particles
  (puncta, vesicles, granules) and the question is *how many* of them coincide,
  not how their intensities covary. Below a certain density, correlation
  coefficients on sparse puncta are dominated by the empty background between
  them and report almost nothing; counting objects and measuring centre-to-centre
  distances is the honest answer.

Both regimes are Qt-free NumPy, so the same code backs the GUI tool, the CLI and
the tests. Import either through this package::

    from chisurf.core.fluorescence.imaging import colocalization as coloc

    coloc.pearson(a, b)                 # pixel-wise
    coloc.object_colocalization(a, b)   # object-based
"""

from __future__ import annotations

from .objects import (
    ObjectSet,
    object_colocalization,
    object_distance_histogram,
    segment_objects,
)
from .pixelwise import (
    ColocalizationResult,
    colocalization_metrics,
    costes_significance,
    costes_threshold,
    cross_correlation_2d,
    estimate_background,
    joint_histogram,
    li_icq,
    manders_fractions,
    manders_overlap,
    orthogonal_regression,
    pearson,
    pearson_profile,
    spearman,
    van_steensel,
)

__all__ = [
    "ColocalizationResult",
    "ObjectSet",
    "colocalization_metrics",
    "costes_significance",
    "costes_threshold",
    "cross_correlation_2d",
    "estimate_background",
    "joint_histogram",
    "li_icq",
    "manders_fractions",
    "manders_overlap",
    "object_colocalization",
    "object_distance_histogram",
    "orthogonal_regression",
    "pearson",
    "pearson_profile",
    "segment_objects",
    "spearman",
    "van_steensel",
]
