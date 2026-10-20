"""Inverse analysis: from measured lifetimes and titrations back to the dye's surface behaviour.

The forward simulator (:mod:`~chisurf.plugins.quenching_estimator.core.simulation`) predicts a
lifetime from a structure. This package goes the other way. It reads lifetimes measured on a
labelled protein and free-dye/amino-acid titrations, and infers per-dye stickiness, quench
scale, contact offset and shielding parameters with their errors.

============================  ====================================================
module                        owns
============================  ====================================================
:mod:`.measurements`          the measurement tables (CSV -> numpy record arrays),
                              site numbers corrected from the data file names
============================  ====================================================

Everything here is numpy only: no pandas, no scipy. The record of what is ported from the
MalE prototype, and what is still to come, is the OKF concept
``okf/plugins/quest-prototype-migration.md``.
"""
