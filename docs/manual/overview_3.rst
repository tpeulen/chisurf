Global view: overview
~~~~~~~~~~~~~~~~~~~~~

In ChiSurf dependencies between parameters can be introduced by linking and visualized in graphs (:strong:`Fig.31`). The :emphasis:`Global view` plugin (:emphasis:`i`) visualizes parameter dependencies in directed graphs, (:emphasis:`ii`) saves parameter dependencies, and (:emphasis:`iii`) restores dependencies from files.

.. image:: _images/image_rId43.png
  :align: center

:strong:`Fig.31. Parameter dependency graph in time-resolved fluorescence decay analysis.` Four fluorescence decays are analysed jointly: the donor in a donor-only sample, :math:`f_{D(0)}`; the donor in the presence of an acceptor, :math:`f_{D(A)}`; the directly excited acceptor in the FRET sample, :math:`f_{A}`; and the FRET-sensitised acceptor emission, :math:`f_{A(D)}`. Parameters and models are represented by circles. Dependencies are illustrated by arrows. Parameters dependent on other parameters are colored in green. Fixed parameters are displayed in light green. Variable parameters are highlighted in magenta.

.. image:: _images/image_rId44.png
  :align: center

The :emphasis:`Global view` plugin opens from the Plugin menu, Plugins → Global view, in a separate window (:strong:`Fig.32`).

:strong:`Fig.32.` User interface of the :emphasis:`Global view` plugin. The plugin represents models and parameters in graphs (bottom). The Visualization group box of the plugin gathers options controlling the graph visualization (Node size, Graph scale). The Network group box can be used to save and load dependencies. The Link group box can be used to introduce and delete (clear) dependencies across selected and all parameters.
