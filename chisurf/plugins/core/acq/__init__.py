"""
Single-Molecule Acquisition

Acquire single-molecule photon streams from TCSPC hardware (Becker & Hickl SPC,
PicoQuant, BrickMic) or from the built-in tttrlib photon simulator.

Opening the plugin in ChiSurf starts a simulated demo stream, registers it as a
dataset and opens an *Acquisition* fit window whose pages (decay, correlation,
MCS, macro-time trace) fill while the stream runs. The window itself is native
(``gui/app.py``); the dataset and the fit are ``dataset.py`` and
``chisurf.core.models.acquisition``.

The package is Qt-free to import: a vendor device wrapper is loaded only when the
operator initializes that device.
"""

name = "Tools:Views:Acquisition"
