Getting started
===============

Installation and environment
----------------------------

ChiSurf uses `pixi <https://pixi.sh>`_ as the canonical environment and build
manager (the CI uses it too). From a checkout of the repository:

.. code-block:: bash

   pixi run chisurf        # launch the GUI  (== python -m chisurf)
   pixi run test           # non-GUI test suite
   pixi run test-gui       # GUI / widget tests

The sibling packages in ``modules/`` (``tttrlib``, built from C++ source, plus
the pure-Python ``chinet``, ``ndxplorer`` and ``quest``) must be installed
before the tests run; the ``test*`` tasks already depend on
``build-extensions``. If imports of those modules fail, run
``pixi run build-extensions``.

.. note::

   Always launch ChiSurf with ``python -m chisurf`` (or ``pixi run chisurf``),
   never by pointing Python at ``__main__.py`` directly — running the file adds
   ``chisurf/`` to ``sys.path`` and shadows the standard-library ``math`` module.

Entry points
------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Command
     - Purpose
   * - ``chisurf``
     - Launch the graphical analysis platform.
   * - ``csc``
     - Command-line interface.
   * - ``python -m chisurf.server``
     - Headless ZMQ / JSON-RPC server (server mode).
   * - ``csg_*``
     - Individual plugin GUIs (see ``[project.gui-scripts]``).

Your first analysis
--------------------

The fastest way to see ChiSurf work end-to-end is one of the guides:

* :doc:`Fitting a fluorescence-lifetime decay </guides/10_lifetime_anisotropy_fitting>`
  — load a TCSPC decay, choose a model, and fit it.
* :doc:`A complete µs-ALEX smFRET workflow </guides/27_alex_smfret_workflow>`
  — from raw photons to FRET-efficiency populations.
* :doc:`Computing an FCS correlation curve </guides/09_diffusion_fcs>`
  — correlate a photon stream and fit a diffusion model.

Each guide links back to the matching :doc:`concept </concepts/index>` page that
explains the underlying theory.
