API Reference
=============

Plot axis labels and units
--------------------------

Use ``chisurf.gui.chiplot`` for plotting. Axis text and units are independent
metadata on the existing ``Plot.set_labels`` API::

    plot.set_labels(left="Count rate", left_units="Hz",
                    bottom="Burst duration", bottom_units="ms")
    plot.set_si_prefix(y=True)

The optional ``left_units``, ``bottom_units``, ``right_units`` and ``top_units``
arguments describe the supplied numeric data; they never convert samples.
``None`` preserves the existing field and ``""`` clears it, for both text and
units. Updating the text alone preserves units.

SI prefix display is off by default. Enable it explicitly to display, for
example, 20,000 Hz as 20 kHz. Tick positions, ranges and curve data retain their
original values, including on logarithmic axes. Units such as ``ms`` describe
data already measured in milliseconds; they do not request conversion from
seconds.

``curve.get_data()`` returns the current source sample arrays, independent of
log display, SI prefixes and downsampling. Clearing a curve returns two empty
arrays.

The emtk backend supports left/bottom labels, units and SI tick display. It stores
right/top metadata but currently renders only left/bottom axes.

Top Level
---------

.. automodule:: chisurf
   :members:
   :undoc-members:
   :show-inheritance:

Core API Facade
---------------

.. automodule:: chisurf.core.api
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: chisurf.core.api.context
   :members:
   :undoc-members:
   :show-inheritance:

Action Infrastructure
---------------------

.. automodule:: chisurf.core.actions._infra
   :members:
   :undoc-members:
   :show-inheritance:

Server Infrastructure
---------------------

.. Members of ``chisurf.server`` are re-exports of the submodules documented
.. below (e.g. ``SessionState`` from ``chisurf.server.session``).  ``:no-index:``
.. keeps the package overview rendered while leaving each name with exactly one
.. cross-reference target, in its defining submodule.
.. automodule:: chisurf.server
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

.. automodule:: chisurf.server.app
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: chisurf.server.dispatcher
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: chisurf.server.protocol
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: chisurf.server.session
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: chisurf.server.services
   :members:
   :undoc-members:
   :show-inheritance:

Source resolution and shell data
--------------------------------

Widget source resolvers use the Python class and its inspectable source line.
Obsolete Designer-path fallback metadata is no longer produced or read. The
existing local-file drag injector retains its supplied target list, sorted
opt-out and once-only callback after mutation. The deferred main shell XML is
installed explicitly as ``chisurf.gui/gui.ui``; broad ``*.ui`` inclusion is
removed. New surfaces remain native AutoForm specs.
