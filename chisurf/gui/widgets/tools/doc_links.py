"""Compatibility alias for :mod:`chisurf.emtk.doc_links`."""

import sys

from chisurf.emtk import doc_links as _implementation

# Preserve shared registries and patch targets across both import paths.
sys.modules[__name__] = _implementation
