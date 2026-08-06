Worm-like chain
"""""""""""""""

.. seealso::

   The polymer models and what their parameters mean physically:
   :doc:`/guides/03_polymer_distance_distributions`. The FRET step that turns a
   distance distribution into a decay: :ref:`concept-fret`.

A flexible linker or an unfolded chain does not hold the two dyes at one
distance — it samples a *distribution* of them, and the donor decay is the
average over that distribution. The worm-like chain (WLC) is the standard
description of such a chain: a continuous filament with a bending stiffness,
parameterised by its **contour length** :math:`l` (how much chain there is) and
its **persistence length** :math:`l_p` (how far along it a direction is
remembered).

Choose it in the model selector as :strong:`FRET: FD (Worm-like chain)`.

What the model computes
=======================

ChiSurf evaluates the radial distribution function of the worm-like chain from
the multi-piece solution of Becker, Rosa & Everaers, *Eur. Phys. J. E*
:strong:`32` (2010) 53-69
(`10.1140/epje/i2010-10596-0 <https://doi.org/10.1140/epje/i2010-10596-0>`_),
on the :math:`R_{DA}` axis configured in the settings. That distribution is then
converted into a FRET-induced donor decay in the usual way: every distance
contributes a transfer rate :math:`k_T = (1/\tau_D)(R_0/R)^6`, and the decay is
the amplitude-weighted sum over the distribution.

The stiffness enters as the ratio :math:`\kappa = l_p / l`; a chain much longer
than its persistence length is flexible and its end-to-end distribution
approaches a Gaussian, while :math:`l \lesssim l_p` gives a stiff rod with a
narrow, strongly peaked distribution.

Parameters
==========

.. list-table::
   :header-rows: 1
   :widths: 12 88

   * - Parameter
     - Meaning
   * - ``l``
     - Contour length of the chain in Å (default 100). For a polypeptide, about
       3.5 Å per residue between the labelling positions.
   * - ``lp``
     - Persistence length in Å (default 30). Denatured proteins are usually
       described with a few Å; double-stranded DNA with ~500 Å.
   * - ``w``
     - Width of the dye-linker distribution in Å (default 6), used only when the
       linker option is switched on. The linker adds its own spread on top of the
       chain's, and ignoring it biases :math:`l_p` low.

Both lengths are fitted like any other parameter, and both are strongly
correlated with the Förster radius: fix :math:`R_0` from the dye pair before
reading a persistence length off a fit.
