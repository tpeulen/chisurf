"""Mathematical helpers used across ChiSurf.

Submodules are served **lazily** (PEP 562), matching the treatment already
applied to :mod:`chisurf.core.fio` and :mod:`chisurf.core.fluorescence`.

Importing them eagerly cost every consumer of this package ~1.6 s:
:mod:`~chisurf.core.math.rand` pulls in ``scipy.stats`` (~1.0 s) and
:mod:`~chisurf.core.math.linalg` pulls in ``numba`` (~0.4 s). Since this package
is reached from :mod:`chisurf.core.curve`, *every* model paid for both -- yet
only the Monte-Carlo structure models use ``rand`` at all.

Both ``import chisurf.core.math.signal`` and attribute access
(``chisurf.core.math.signal`` after ``import chisurf.core.math``) continue to
work; the submodule is simply imported on first use.
"""

import importlib
from typing import Any

#: Submodules imported on first attribute access rather than at package import.
_LAZY_SUBMODULES = (
    "datatools",
    "functions",
    "hmm",
    "linalg",
    "optimization",
    "rand",
    "reaction",
    "regularization",
    "signal",
    "statistics",
)


def __getattr__(name: str) -> Any:
    """Import a submodule on first attribute access."""
    if name in _LAZY_SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List module contents including the lazily-imported submodules."""
    return sorted({*globals(), *_LAZY_SUBMODULES})
