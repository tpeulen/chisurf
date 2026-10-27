"""The tttrlib photon simulator of the acquisition tool (``simulation``).

Real TCSPC hardware is not wrapped here: devices are driven through the phacq library
(native drivers for PicoQuant MultiHarp / PicoHarp 330 / HydraHarp 500, Becker & Hickl SPC
cards and the PicoQuant Sepia II laser, without vendor libraries). This package only holds
the simulated source.
"""
