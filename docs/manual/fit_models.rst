Fit models
----------

A **model** in ChiSurf combines variable parameters with a recipe for computing
theoretical data — a forward model. It is always attached to a data set: the
pair of the two, together with the fit range and the weighting, is a
":strong:`Fit`".

Models are grouped by experiment type, and the selector in the *Analysis* dock
offers the ones that apply to the data that is loaded: correlation models for
FCS curves, decay models for TCSPC histograms, and so on. Creating one is
described in :doc:`creating_fits`; what the parameters then do is
:doc:`parameters`.

The current fit, its data and its model are all reachable from the integrated
Python console, which is the quickest way to inspect a model that is behaving
unexpectedly:

.. code-block:: python

  cs.current_fit
  cs.current_fit.data
  cs.current_fit.model

Everything the graphical interface does is available there as well — a fit set
up by clicking can be re-run, modified or scripted from the console, and a whole
analysis can be replayed headlessly (:doc:`/guides/59_console`).

The catalogue of models that ship with ChiSurf, with every parameter, is in the
:doc:`plugin and model reference </reference/index>`; user-defined models are
described in :doc:`/reference/user_models`.
