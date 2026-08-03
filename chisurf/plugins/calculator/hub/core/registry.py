"""Registry of embeddable calculators for the Calculators hub (Qt-free).

The hub is a two-panel tool: a list of calculators on the left, the selected
calculator embedded on the right. Each entry names an *embeddable* ``QWidget``
(a plain panel or window, no required constructor arguments) by dotted import
path; the GUI resolves and instantiates it lazily on first selection. Keeping the
catalogue here — as plain data — lets it be unit-tested and extended without
importing Qt.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class CalculatorEntry:
    """One selectable calculator in the hub.

    Parameters
    ----------
    id : str
        Stable identifier (used for selection persistence).
    label : str
        Text shown in the selector list.
    description : str
        One-line summary shown above the embedded calculator.
    widget : str
        Dotted import path ``"pkg.module:ClassName"`` of an embeddable ``QWidget``
        that constructs with no required arguments.
    icon : str
        Optional emoji/icon shown next to the label.
    """

    id: str
    label: str
    description: str
    widget: str
    icon: str = ""


def default_calculators() -> list[CalculatorEntry]:
    """Return the built-in calculators embedded by the hub."""
    return [
        CalculatorEntry(
            id="fret_calculator",
            label="FRET / homoFRET",
            description=(
                "Combined heteroFRET and homoFRET parameter calculator — convert "
                "between distance, efficiency, lifetime and rate."
            ),
            widget="chisurf.plugins.calculator.fret_calculator.gui.tool:FretCalculatorTool",
            icon="🧮",
        ),
        CalculatorEntry(
            id="fret_line",
            label="FRET line",
            description=(
                "Compute static, dynamic, WLC and mixture FRET lines for parameter "
                "ranges, ready to overlay on smFRET 2D histograms."
            ),
            widget="chisurf.plugins.fret_line.gui.tool:FRETLineTool",
            icon="📈",
        ),
        CalculatorEntry(
            id="fcs_calculator",
            label="FCS diffusion",
            description=(
                "Confocal-FCS diffusion/volume calculator — solve τ, D, rₕ, V_eff "
                "and concentration from one constraint."
            ),
            widget="chisurf.plugins.fcs.fcs_calculator.wizard:ConfocalCalcWidget",
            icon="🌀",
        ),
        CalculatorEntry(
            id="rics_precision",
            label="RICS precision",
            description=(
                "Predict how precisely a raster scan would measure a diffusion "
                "coefficient, and sweep the pixel dwell time to find the one that "
                "measures it best — from the intended settings, before acquiring."
            ),
            widget="chisurf.plugins.calculator.rics_precision.gui.tool:RicsPrecisionTool",
            icon="📐",
        ),
        CalculatorEntry(
            id="phasor",
            label="Phasor plot",
            description=(
                "Interactive phasor plot — universal semicircle with a reference-"
                "lifetime grid/ticks, a FRET trajectory and a two-component mixing line."
            ),
            widget="chisurf.plugins.calculator.phasor_calculator.gui.tool:PhasorCalculatorTool",
            icon="◐",
        ),
        CalculatorEntry(
            id="kappa2_dist",
            label="κ² distribution",
            description=(
                "Orientation-factor distribution p(κ²) for FRET — wobbling-in-cone, "
                "diffusion-with-traps and isotropic models with apparent-distance error."
            ),
            widget="chisurf.plugins.calculator.kappa2_dist.gui.tool:Kappa2Dist",
            icon="🎯",
        ),
        CalculatorEntry(
            id="f_test",
            label="F-test / χ²-max",
            description=(
                "Compare two nested model fits (confidence ↔ χ² threshold) and compute "
                "the χ²-max upper limit of a single fit at a confidence level."
            ),
            widget="chisurf.plugins.core.f_test.gui.tool:FTestTool",
            icon="📉",
        ),
        CalculatorEntry(
            id="fcs_saturation",
            label="FCS Saturation",
            description=(
                "Numerical calculation of excitation saturation and effective volume expansion "
                "in FCS across arbitrary multi-state kinetic schemes (e.g. Cy5)."
            ),
            widget="chisurf.plugins.calculator.fcs_saturation_calc.gui.tool:SaturationCalculatorTool",
            icon="🔆",
        ),
        CalculatorEntry(
            id="psf_calculator",
            label="PSF calculator",
            description=(
                "Compute a 3-D point-spread function and view it as a volume: vectorial "
                "Richards-Wolf, scalar Airy or Gaussian, with the polarization entering "
                "the objective pupil."
            ),
            widget="chisurf.plugins.calculator.psf_calculator.gui.tool:PSFCalculator",
            icon="🔬",
        ),
    ]


__all__ = ["CalculatorEntry", "default_calculators"]
