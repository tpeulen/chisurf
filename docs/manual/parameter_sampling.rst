Parameter sampling
------------------

.. seealso::

   What an error bar from sampling actually means, which sampler suits which
   posterior, and how to tell a converged run from a stuck one:
   :ref:`concept-parameter-uncertainty` and
   :doc:`/guides/39_parameter_uncertainty`.

Optimisation returns the *best* parameter values. Sampling returns the
**distribution** of values compatible with the data, which is what an
uncertainty is — and, unlike the curvature at the optimum, it shows the
correlations between parameters and survives a posterior that is not a
paraboloid.

Sampling is started with the "Distribution" button beside "Fit" in the fitting
and optimisation interface (:strong:`Fig.15`).

.. image:: _images/image_rId23.png
  :align: center

:strong:`Fig.15 Sampling over variable model parameters, illustrated for
time-resolved fluorescence analysis.` The data and model of the fit are shown
below. Clicking the sampling button (highlighted in orange) samples the free
model parameters and asks for an output folder. The chains are written there and
can be opened in a multidimensional-histogram tool — nDXplorer, which ships with
ChiSurf, or Margarita — to look at the distributions and their correlations
(bottom right).

Defaults for the number of steps, the number of independent runs and the chain
format live in the ``optimization.sampling`` section of the settings file
(:strong:`Fig.14`).

From the shell
==============

.. code-block:: python

  fit = cs.current_fit
  report = chisurf.core.fitting.fit.sample_fit(fit, "/output/directory")

The second argument is a **directory**, not a file name: a timestamped
sub-directory is created inside it holding the chains and a ``diagnostics.json``.
The same report is returned — per-parameter mean, standard deviation, quantiles,
effective sample size, split R-hat and autocorrelation time, plus a list of
warnings. **Read the warnings before the numbers**: a chain that has not
converged still produces a confident-looking standard deviation.

The sampler is chosen with ``method``:

.. list-table::
   :header-rows: 1
   :widths: 16 84

   * - ``method``
     - When to use it
   * - ``ensemble``
     - The default. An affine-invariant ensemble whose walkers take their scale
       from each other, so it needs no prior knowledge of the posterior — the
       fallback when nothing is known about it.
   * - ``slice``
     - The same ensemble idea without an accept/reject step: every walker moves
       every step, at the cost of several model evaluations per step.
   * - ``blocked``
     - Proposes from a per-block covariance seeded by the curvature at the
       optimum. The one to reach for on a strongly *correlated* posterior.
   * - ``de``
     - Proposes from the differences within a population of chains: no gradient,
       no covariance, and so it cannot be misled by a covariance taken at the
       wrong point. Strong on curved posteriors started away from the optimum.
   * - ``collapsed``
     - For a **linked global fit**: each data set's private parameters are
       integrated out analytically and only the shared parameters are sampled.
   * - ``mcmc``
     - The historical diagonal random walk, kept for reproducing old analyses.

Other useful arguments: ``steps`` and ``thin`` (chain length and thinning),
``n_runs`` (independent runs, which is what makes the R-hat diagnostic
meaningful), ``chi2max`` (reject moves above a score), and ``chain_format`` —
``er4``, tab-separated text that any tool reads, or ``hdf5``, about a quarter of
the size, which is what a long run needs. Both open in nDXplorer.

.. note::

   For a trustworthy analysis the sampling has to be *complete*. A
   high-dimensional or strongly correlated model needs more steps than the
   default, and the diagnostics — not the appearance of the histogram — are how
   you know whether it got there.
