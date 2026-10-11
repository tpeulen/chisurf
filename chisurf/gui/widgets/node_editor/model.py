"""Compatibility alias for the canonical native model module."""

import sys

from chisurf.emtk.node_editor import model as _module

sys.modules[__name__] = _module
