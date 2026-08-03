"""Burst Fusion — merge bursts the same molecule produced.

An optional step of the burst pipeline, placed directly after burst selection:
it reads a burst-analysis folder, uses the recurrence same-molecule probability
``P_same(tau)`` to decide which consecutive bursts came from one molecule that
re-entered the observation volume, and writes a **new** burst folder in which
each such run is a single burst. Every later step (BVA, 2CDE, MLE, H2MM, the
browser) reads that folder unchanged.
"""

from .api.models import FusionSettings

__all__ = ["FusionSettings"]
