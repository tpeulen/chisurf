"""Forwarder — this module moved to :mod:`IMP.bff.fret.distributions` (PRD-97).

The implementation lives in IMP.bff; this alias keeps every ChiSurf import
path and symbol (including private helpers used by tests) working unchanged.
"""

import sys

import IMP.bff.fret.distributions as _impl

sys.modules[__name__] = _impl
