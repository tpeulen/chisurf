"""Guided experiment and calibration workflows: FRET (PIE), polarisation (MFD)
and the per-laser power-diode calibration.

The package is a backend: a workflow engine with staged prerequisites, explicit
user confirmations, transparent quality metrics whose limits the user owns, and
calibrations recorded as measured results with provenance. It never drives
hardware -- measurement and emission changes remain the operator's acts,
recorded here as verified readbacks and confirmations.

* :mod:`.workflow` -- the engine (steps, guards, confirmations, persistence).
* :mod:`.measurements` -- the value estimators (IRF width, tail lifetime,
  background rate, G factor, PIE gamma, power-diode fit).
* :mod:`.lasers` -- the laser inventory, keyed power calibrations, the
  3-calendar-month staleness policy and the device history.
* :mod:`.library` -- the three shipped workflows and the editable optics
  catalog.
"""

from __future__ import annotations
