Provided test data – live cell experiments
""""""""""""""""""""""""""""""""""""""""""

The second part of the FCS example uses measurements on **live cells** rather
than a dye solution. The optical settings — excitation wavelengths, detection
filters, pinhole and correlator settings — are identical to the calibration
measurements described in :doc:`provided_test_data__calibration`, so the
detection volumes determined there apply unchanged.

What differs is the sample, and that changes which models are appropriate: a
membrane-bound species diffuses in two dimensions rather than three, and the
concentration and brightness are set by expression rather than by pipetting.
The analysis of these data starts at
:doc:`analysis_of_live_cell_experiments`, and the two-dimensional models it
needs are added in :doc:`adding_the_membranediffusion_models`.
