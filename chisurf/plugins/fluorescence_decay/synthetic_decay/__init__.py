"""Synthetic decay generator plugin.

Full-stack (API / CLI / RPC / GUI) surface over the single canonical decay
generator ``chisurf.core.fluorescence.decay.synthetic_decay``. Generates
synthetic TCSPC fluorescence-decay histograms from lifetimes / spectra with
optional IRF convolution and Poisson shot noise.
"""

name = "Spectroscopy:Fluorescence Decay:Synthetic Decay Generator"


if __name__ == "plugin":  # pragma: no cover
    from .gui.tool import SyntheticDecayTool

    _tool = SyntheticDecayTool()
    _tool.show()
