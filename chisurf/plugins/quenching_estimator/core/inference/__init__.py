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
:mod:`.columns`               the declared table layouts (``settings/analysis/*.yaml``)
:mod:`.titration`             Stern-Volmer lines per day, the hierarchical K_SV
                              posterior with its day-to-day error, kq
:mod:`.lifetime_errors`       water quenching per site, lifetime scatter and site
                              errors, leave-one-out coverage, free-dye tau0,
                              measured water access
:mod:`.kq_scaling`            contact kQ per dye from the titration ratios
:mod:`.site_table`            per-voxel site tables (neighbour counts, quencher
                              contacts, water exposure) from IMP.bff kernels, cached
:mod:`.site_model`            the equilibrium site model: tau_X, dark fraction and
                              visible exposure for a parameter set
:mod:`.graph_fit`             the Bayesian graph: robust multistart search, model
                              error, joint fit, Laplace, leave-one-out, propagation,
                              quench-scale profile, factor-graph description
:mod:`.stages`                the declared stages (A, B, naive H2O test, C,
                              summary) and the headless entry (``Analysis``)
:mod:`.report`                the plain-language texts, written from the numbers
============================  ====================================================

Everything here is numpy only: no pandas, no scipy. The record of what is ported from the
MalE prototype, and what is still to come, is the OKF concept
``okf/plugins/quest-prototype-migration.md``.
"""
