"""In-tree replacements for the scikit-learn estimators this tree uses.

Mirrors scikit-learn's public package layout and spelling, so each call site
that is ported over changes by an import line and nothing else. The only
estimators present are the ones the codebase reaches for — see the OKF concept
[machine learning](/subsystems/machine-learning.md) for the exhaustive table and
for which kernels are compiled.
"""

from .cluster import HDBSCAN, KMeans
from .decomposition import PCA, IncrementalPCA
from .mixture import GaussianMixture
from .neural_network import MLPRegressor
from .preprocessing import StandardScaler

__all__ = [
    "GaussianMixture",
    "HDBSCAN",
    "KMeans",
    "PCA",
    "IncrementalPCA",
    "StandardScaler",
    "MLPRegressor",
]
