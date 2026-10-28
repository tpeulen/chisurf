"""
Single-Molecule Acquisition

Record single-molecule photon streams from TCSPC hardware or from the built-in
tttrlib photon simulator. Hardware is driven through the phacq library (native
drivers for PicoQuant MultiHarp / PicoHarp 330 / HydraHarp 500, Becker & Hickl SPC
cards and the PicoQuant Sepia II laser; no vendor libraries).

The window is the native Record tool (``gui/record_app.py``); the demo dataset and
its *Acquisition* fit window are ``dataset.py`` and ``chisurf.core.models.acquisition``.
The package is Qt-free to import.
"""

name = "Tools:Views:PhAcq"
