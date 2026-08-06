Model scores
------------

The fitting minimizes the difference between the model and the data. Sampling samples over variable (free) model parameters to estimate probability distributions over parameters. Both, sampling, and optimization require a score. The score depends on the model, the data, and the data noise. The score of the current fit is read as follows:

.. code-block:: python

  fit = cs.current_fit
  fit.get_score(score_type='chi2')

``score_type`` selects the score. Every fit/model combination implements at least ``'chi2'`` — the sum of squared deviations between model and data, each weighted by the noise of that data point — and ``'chi2r'``, the same sum divided by the degrees of freedom (number of observations minus number of free model parameters). A reduced chi-square near 1 means the model describes the data to within its noise; well above 1 means it does not, and well below 1 usually means the noise was overestimated. Values of 'chi2' and 'chi2r' can also be accessed as follows:

.. code-block:: python

  fit = cs.current_fit
  fit.chi2
  fit.chi2r

For a fit object the code

.. code-block:: python

  fit.get_wres()

returns the deviation between the data and the model weighted by the data noise.
