"""Compatibility alias for the canonical native registry module."""
import sys

from chisurf.emtk.node_editor import registry as _module

sys.modules[__name__] = _module
