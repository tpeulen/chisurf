Parameter scan
--------------

A Chi Square support plane analysis around the minimum (the fitted solution) can be performed in in fits/model that offer a "Parameter scan". In the parameter scan a free model parameter can be selected from a dropdown menu. The selected parameter is varied in a defined range. Other free model parameters are optimized.

.. image:: _images/image_rId26.png
  :align: center

:strong:`Fig.19 Parameter scan plots` are offered by fits of certain models. The parameter scan varies a parameter in a certain range (top) and optimizes other free model parameters to create a :math:`\chi^2_r` curve that depends on the parameter (bottom). The resulting :math:`\chi^2_r` curve can be used to estimate uncertainties of model parameters. Red line chi2 confidence level 95% computed with F-Calculator.

This procedure (Support plane analysis) produces a :math:`\chi^2_r` curve of the scanned parameter that can be used to estimate uncertainties (:strong:`Fig.19`). Upper limits of :math:`\chi^2_r` at a chosen confidence level are computed with the :doc:`FRET/F-Calculator <fcalculator>`.

Reduced Chi Square
