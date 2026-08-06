Discrete FRET rate constants
""""""""""""""""""""""""""""

.. seealso::

   The transfer rate and how a distance becomes one: :ref:`concept-fret`.

Not every sample needs a *distribution* of donor-acceptor distances. A construct
with two or three well-defined conformations is better described by a handful of
**discrete** states, each with its own separation and its own population
fraction — which is what this model fits.

Choose it in the model selector as :strong:`FRET: FD (Discrete)`.

What the model computes
=======================

Each component :math:`i` carries a distance :math:`R_i` and a species fraction
:math:`x_i` (``R(G,i)`` and ``x(G,i)`` in the parameter tree; add and remove
components as needed, and the fractions are normalised for you). Every distance
is converted into a transfer rate,

.. math::

   k_{T,i} = \frac{1}{\tau_{D0}} \left(\frac{R_0}{R_i}\right)^6 ,

using the Förster radius, the donor-only lifetime and :math:`\kappa^2` from the
shared FRET-parameter group. The FRET-induced donor decay is then the
amplitude-weighted sum of exponentials with those rates, and the observed decay
is that combined with the donor's own — possibly multi-exponential —
fluorescence decay.

So the quenching is **not** uniform across the sample: each species is quenched
by its own rate. What *is* assumed is that within one species every molecule
shares that rate; a species with a genuinely broad distance distribution is
better fitted with the Gaussian or polymer models
(:doc:`worm-like chain <wormlike_chain>`).

The plots offer the same result as a distance distribution, as a distribution of
FRET rate constants, or as a fluorescence-lifetime distribution
(:doc:`reference_curves`) — three views of one fitted quantity.
