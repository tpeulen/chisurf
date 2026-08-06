Fluorescence Lifetime
~~~~~~~~~~~~~~~~~~~~~

.. seealso::

   What a lifetime measures, why the model must be reconvolved with the
   instrument response, and how amplitudes turn into physical numbers:
   :ref:`concept-tcspc-lifetime`. The task-focused version:
   :doc:`/guides/10_lifetime_anisotropy_fitting`.

The workhorse model for time-resolved data is a **linear combination of
exponential decays**,

.. math::

   I(t) = \sum_i x_i \, e^{-t/\tau_i}, \qquad x_i \ge 0 ,

with an amplitude :math:`x_i` and a lifetime :math:`\tau_i` per species. Almost
every time-resolved model in ChiSurf is this expression underneath: anisotropy
decays, FRET-induced donor decays, distance distributions and rate-constant
distributions all produce a *lifetime spectrum* — interleaved amplitudes and
lifetimes — that is then treated identically.

Adding and removing species is done in the model's parameter group; each species
contributes one amplitude and one lifetime, and amplitudes are normalised so
that the fractions are directly readable.

Convolution modes
=================

The measured decay is the model convolved with the instrument response function
(IRF), so the mode chosen in the :doc:`Convolve panel <nuisances>` decides both
what is computed and how fast:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Mode
     - Use it for
   * - Fast exponential
     - The default for lifetime models. Each exponential is convolved with the
       IRF analytically, which is exact for this model family and the fastest
       option.
   * - Fast periodic
     - The same, but accounting for **incomplete decay between laser pulses**:
       excitation is periodic, so what is measured in one time window still
       contains the tail of the previous pulse. Needed whenever the lifetime is
       not short compared with the pulse period; the laser repetition rate is
       taken from the panel.
   * - Curve convolution
     - A numerical convolution of the whole model curve with the IRF. Slower and
       the only option for a model that is not a sum of exponentials — in
       particular the :doc:`equation parser <equation_parsing>`.

Switching the convolution off leaves the ideal (unconvolved) decay, which is
useful for inspecting a model but is not what should be compared with data. The
scatter contribution is added on top of the convolved decay in every mode.
