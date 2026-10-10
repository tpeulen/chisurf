"""Compatibility alias for the headless graph schema."""
import sys

from chisurf.core import graph_definition as _module

sys.modules[__name__] = _module
