Parameter optimization
----------------------

ChiSurf uses the lmdif and the lmder algorithm implemented in MINPACK to optimize variable parameters. Variable parameters are optimized either by clicking on the 'Fit' button in the data optimization and sampling interface (:strong:`Fig.13`) or using the shell:

.. code-block:: python

  fit = cs.current_fit
  fit.run()

Grouped fits offer the option to first optimize local variable parameters before optimizing the global fit.

.. code-block:: python

  fit = cs.current_fit
  fit.run(local_first=True)

The effect of optimizing (fitting) variable model parameters to data for a fluorescence decay curve are displayed in :strong:`Fig.13`.

.. image:: _images/image_rId22.png
  :align: center

:strong:`Fig.13 Optimizing variable parameters.` The Fit button (red box) optimizes the agreement between the model and the data. The middle panels display fixed and variable model parameters before and after fitting (clicking the 'Fit' button). The bottom displays the data and the model before and after fitting. The autocorrelation of the weighted deviations between the data and the model weighted by the data noise (weighted residuals) and the weighted residuals visually captures the similarity between the data and the model.


Settings
========

The optimiser's own parameters live in the ``optimization`` section of the
:doc:`settings file </reference/settings>` (:strong:`Fig.14`):

.. code-block:: yaml

  optimization:
    global_optimize_local_first: false
    global_threaded_model_update: false
    global_structure_aware_update: true
    leastsq:
      epsfcn: 1.0e-06
      factor: 100
      ftol: 1.49012e-08
      full_output: true
      gtol: 0
      maxfev: 0
      xtol: 1.49012e-08
    mem:
      factr: 10
      lower_bound: 1.0e-08
      maxfun: 1500000
      maxiter: 150000
      reg_scale: 1
      upper_bound: 10000000
    sampling:
      method: blocked
      steps: 1000
      thin: 1
      chi2max: 1000000000
      n_runs: 10

The ``leastsq`` block is passed straight to MINPACK. One of its entries is worth
knowing about: ``epsfcn`` sets the relative step used for the forward-difference
Jacobian. Left at 0 — MINPACK's "use machine epsilon" — the step is far below the
numerical accuracy of a reconvolved decay model, the Jacobian columns are then
dominated by rounding noise, and the optimiser fails to move the lifetimes at all
from many starting points. The shipped default is deliberately larger.

The ``mem`` block configures the maximum-entropy (regularised) fits, and
``sampling`` the defaults used by :doc:`parameter_sampling`.

:strong:`Fig.14 Optimization section of the settings file.` Every setting is
listed in the :doc:`settings reference </reference/settings>`.
