"""In-tree replacements for the scikit-learn estimators this tree uses.

Mirrors scikit-learn's public package layout and spelling, so each call site
that is ported over changes by an import line and nothing else. The only
estimators present are the ones the codebase reaches for — see OKF PRD-87 for
the exhaustive table; ``HDBSCAN`` still comes from the library.
"""

from .cluster import KMeans
from .decomposition import IncrementalPCA, PCA
from .mixture import GaussianMixture
from .neural_network import MLPRegressor
from .preprocessing import StandardScaler

__all__ = [
    "GaussianMixture",
    "KMeans",
    "PCA",
    "IncrementalPCA",
    "StandardScaler",
    "MLPRegressor",
]
