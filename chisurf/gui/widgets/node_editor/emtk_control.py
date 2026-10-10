"""Compatibility alias for the canonical native control module."""
import sys

from chisurf.emtk.node_editor import control as _module

sys.modules[__name__] = _module
