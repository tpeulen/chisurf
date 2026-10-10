"""Compatibility alias for the canonical native document module."""
import sys

from chisurf.emtk.node_editor import document as _module

sys.modules[__name__] = _module
