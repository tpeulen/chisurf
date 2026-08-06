Partial donor-donor energy migration
""""""""""""""""""""""""""""""""""""

.. seealso::

   The physics of the transfer step itself: :ref:`concept-fret`. Homo-transfer
   also depolarises the emission — see :ref:`concept-anisotropy`.

A sample labelled with **two chemically identical donors** does not behave like
a sample with one. Excitation hops back and forth between the two fluorophores
(homo-FRET, *energy migration*), and because the two positions are not
equivalent — different local quenching, different orientation — the observed
decay is not the decay of either one alone.

The **PDDEM** model (partial donor-donor energy migration) describes exactly
that case: two donor populations, *A* and *B*, each with its own multi-
exponential decay, coupled by transfer rates in both directions. It follows
Kalinin & Johansson, *J. Phys. Chem. B* :strong:`108` (2004) 3092-3097
(`10.1021/jp038041q <https://doi.org/10.1021/jp038041q>`_).

Choose it in the model selector as :strong:`FRET: PDDEM`.

What the model computes
=======================

Each fluorophore contributes a lifetime spectrum (*fa* and *fb* in the
parameter tree, set up like any other
:doc:`multi-exponential decay <fluorescence_lifetime>`). The transfer rate is
taken from a **distance distribution** — the same Gaussian distribution
machinery the other FRET models use — so a distribution of separations between
the two dyes gives a distribution of migration rates rather than one rate.

Parameters
==========

.. list-table::
   :header-rows: 1
   :widths: 12 88

   * - Parameter
     - Meaning
   * - ``AtB``
     - Whether transfer from *A* to *B* is allowed (probability, usually 0 or 1).
   * - ``BtA``
     - Whether transfer from *B* to *A* is allowed. Setting only one of the two
       gives one-way migration; setting both gives true back-and-forth hopping.
   * - ``xA``, ``xB``
     - Excitation probabilities of *A* and *B* — how the excitation light is
       distributed over the two positions.
   * - ``mA``, ``mB``
     - Emission (detection) probabilities of *A* and *B*.
   * - ``pureA``, ``pureB``
     - Fractions of the sample carrying only *A* or only *B*, i.e. singly
       labelled molecules that cannot migrate at all.
   * - ``alpha_A``, ``alpha_B``
     - Outputs, not inputs: the normalised emission weights
       ``mA / (mA + mB)`` and ``mB / (mA + mB)``.

The excitation and emission probabilities are what make the model *partial*:
with ``xA`` = 1, ``xB`` = 0, ``mA`` = 0, ``mB`` = 1 only the migrated
excitation is observed, and the decay is dominated by the transfer step.

.. note::

   The distance distribution is discretised into a lifetime spectrum, which can
   grow large. The ``fret`` section of the settings file controls that:
   ``bin_lifetime`` switches on binning of the spectrum and ``lifetime_bins``
   sets how many bins are kept.
