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

The main window
---------------

The window opens with one tabbed column on the left — **Read data**,
**Datasets**, **Analysis**, **Plot settings** and **Logging** share it, so the
rest of the width belongs to the workspace where fits and plots open. The
console keeps the bottom edge (turn it off with the ``gui.show_console``
setting).

Docks are yours to rearrange: drag one out of the stack to the right or bottom
edge, resize it, or close it. The arrangement is saved when ChiSurf exits and
restored on the next start.

To get back to the arrangement above, use :menuselection:`View --> Reset Layout`
(also on the ribbon's *Main* tab, under *Other Tools*). It forgets the saved
layout as well as re-applying the default, so the reset survives the next start.

.. note::

   A layout saved by an older version of ChiSurf is ignored once when the
   default arrangement itself changes — otherwise a stale saved layout would
   hide every later improvement to it. Anything you rearrange afterwards is kept
   as usual.

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

Finding help inside ChiSurf
---------------------------

All of this documentation ships with the application: :menuselection:`Help -->
Documentation` opens it in a browser window, with the same structure as this
site — getting started, the concepts, the guides, the fitting manual, the
reference, and one entry per plugin.

Three things are worth knowing about that window:

* **Search covers the full text of every page** (:kbd:`Ctrl+F`). Results are
  ranked, each with the passage that matched, and the tree narrows to them.
* **Cross-references are links.** A concept page's pointer to its guide, a
  DOI in a *Further reading* list, a manual page's *See also* box — all of them
  go somewhere; :kbd:`Alt+Left` walks back, and every page carries previous /
  next along the reading order.
* **Every plugin's** :guilabel:`?` **button opens its page here**, and its
  :guilabel:`Guide` button walks you through the tool's own controls.

Maintainers can turn on the *Authoring* toolbar in that window to edit a page in
place, list the developer documentation, and record the human review that gates
a release.
