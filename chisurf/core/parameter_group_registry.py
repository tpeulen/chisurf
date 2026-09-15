"""Deprecated path: moved to :mod:`chisurf.core.registry.parameter_groups`.

Kept as a re-export because code outside this repository (the ndxplorer
submodule) imports the old module path. New code imports the new location.
"""

from chisurf.core.registry.parameter_groups import *  # noqa: F401,F403
from chisurf.core.registry.parameter_groups import __all__  # noqa: F401
