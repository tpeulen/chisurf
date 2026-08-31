Concepts (theory)
=================

These pages explain the **theory** behind each analysis ChiSurf performs — what
the models mean, which assumptions they make, and how their parameters map onto
physical quantities. They are self-contained and cited, and each links to the
:doc:`guide </guides/index>` that shows how to run the analysis in ChiSurf. The
ordering below runs from the core methods to the specialized ones.

The photophysics these pages assume — the excited state, orientation and
transfer, the instrument, the counting statistics — is one layer down, in
:doc:`Fundamentals </fundamentals/index>`. Symbols and the common literature
alternatives are collected in :doc:`/fundamentals/conventions`.

.. rubric:: Core methods

.. toctree::
   :maxdepth: 1

   fret
   kappa2_orientation
   distance_distributions
   energy_migration
   distributed_acceptors
   tcspc_lifetime
   anisotropy
   fcs_correlation

.. rubric:: Fitting and inference

.. toctree::
   :maxdepth: 1

   global_analysis
   maximum_entropy
   parameter_uncertainty

.. rubric:: Correlation methods

.. toctree::
   :maxdepth: 1

   fcs_saturation
   filtered_fcs
   image_correlation
   pair_correlation
   scan_precision
   pch_fida
   frap

.. rubric:: Single-molecule FRET (bursts)

.. toctree::
   :maxdepth: 1

   smfret_bursts
   accurate_fret
   burst_2cde
   burst_fusion
   bva
   recurrence
   pda2c
   pda3c

.. rubric:: Dynamics (hidden Markov)

.. toctree::
   :maxdepth: 1

   hidden_markov_models
   h2mm
   photon_by_photon_kinetics
   mfd_fitting
   ebfret

.. rubric:: Imaging and resolution

.. toctree::
   :maxdepth: 1

   super_resolution

.. rubric:: Exploration & selection

.. toctree::
   :maxdepth: 1

   multidimensional_exploration
   density_clustering
   deconvolution

.. rubric:: Data and provenance

.. toctree::
   :maxdepth: 1

   photon_container
   live_streaming_analysis

.. rubric:: Structure & imaging

.. toctree::
   :maxdepth: 1

   accessible_volume
   molecular_surfaces
   imaging_flim_phasor
   region_properties
   colocalization
   drift_correction
   particle_tracking
   frc_resolution

.. rubric:: Simulation

.. toctree::
   :maxdepth: 1

   photophysics_simulation
   biofilm_growth
