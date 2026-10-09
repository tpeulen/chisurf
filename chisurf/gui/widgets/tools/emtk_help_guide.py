"""Compatibility alias for :mod:`chisurf.emtk.help_guide`."""

import sys

from chisurf.emtk import help_guide as _implementation

# Preserve shared registries and patch targets across both import paths.
sys.modules[__name__] = _implementation
