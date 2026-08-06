F-Calculator
------------

.. image:: _images/image_rId32.png
  :align: center

:strong:`Fig.25 F-Calculator.` Convert between the quantities of a FRET
measurement, and compute the F-values used to put a confidence level on a
:doc:`parameter scan <parameter_scan>`.

The calculator is opened from :strong:`Tools → FRET-Calculator`. It is a small
set of coupled fields: change any one of them and the rest follow, which makes
it the fastest way to answer "what distance does that efficiency correspond to"
without setting up a fit.

It relates

* the FRET efficiency :math:`E`,
* the donor-acceptor distance :math:`R`,
* the Förster radius :math:`R_0`,
* the donor lifetimes with and without acceptor, :math:`\tau_{DA}` and
  :math:`\tau_D`,
* the FRET rate constant :math:`k_{FRET}`,
* and the width :math:`\sigma` of a Gaussian distance distribution.

With :math:`\sigma = 0` the calculator uses a single distance,
:math:`E = 1/(1 + (R/R_0)^6)`. With :math:`\sigma > 0` it averages over the
distribution instead — which is the honest calculation whenever a flexible
linker is involved, and gives a different answer: averaging the *rate* and
inverting is not the same as inverting the average distance
(:ref:`concept-fret`).

For the theory of the correction factors that stand between measured signals and
:math:`E`, see :ref:`concept-accurate-fret`; for the calculator's own reference
page, :doc:`/reference/plugins/fret_calculator`.
