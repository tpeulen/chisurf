"""Forwarder — this module moved to :mod:`IMP.bff.fret.imp_engine`.

The implementation lives in IMP.bff; this alias keeps every ChiSurf import
path and symbol (including private helpers used by tests) working unchanged.
"""

import sys

import IMP.bff.fret.imp_engine as _impl

sys.modules[__name__] = _impl
