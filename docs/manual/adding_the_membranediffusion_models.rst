Adding the membrane-diffusion models
""""""""""""""""""""""""""""""""""""

Upon installation, ChiSurf comes with a bunch of FCS fit models; however, your required fit model might not be among them. The FCS models are defined in a YAML file, ``chisurf/core/models/fcs/models.yaml``, in the installation folder. (Earlier versions used a JSON file; the structure is the same.)

.. image:: _images/image_rId83.png
  :align: center

Before modifying the file, (i) create a copy on a different place as a backup and (ii) make a second copy to work on as modifying / saving directly in the programs installation folder is usually not allowed.

Open it in a text editor.

Each model is one entry with three keys under its name:

.. code-block:: yaml

  3D Gauss, 1 bunching:
    equation: b+1/abs(N)*(1+x/td)**(-1)*(1+1/s**2*x/td)**(-0.5)*(1-ba+ba*exp(-x/bt))
    initial:
      N: 1
      s: 3.5
      td: 0.5
      b: 1
      bt: 0.002
      ba: 0.1
    description: 3D Gaussian diffusion with one exponential blinking term

The key is the model name as it appears in the selector, ``equation`` is the correlation function in terms of the lag ``x``, ``initial`` gives every parameter a starting value — a parameter exists because it appears here — and ``description`` is the tooltip.

:emphasis:`It is vital to keep this notation and take care of proper punctuation and indentation!`

.. image:: _images/image_rId84.png
  :align: center

Add the two models below — bimodal membrane diffusion, with and without an additional relaxation / triplet term:

For analysis of autocorrelation curves:

where :emphasis:`tD1` and :emphasis:`tD2` are the two diffusion time and :emphasis:`a1` is the fraction of :emphasis:`tD1`. :emphasis:`aR` and :emphasis:`tR` describe the triplet blinking / photophysics.

For analysis of cross-correlation curves:

In cross-correlation curves, usually no triplet blinking can be seen.

Don't forget to define reasonable initial values for each of the model parameter.

Save the file and restart ChiSurf.

.. note::

   Editing the installed file means your models are lost on the next update, and a
   permission error is likely on Windows. The supported route is an override in your
   user settings folder — see :doc:`/reference/user_models`.

:emphasis:`The model catalogue is read once at startup, so a change only takes effect after a restart.`
