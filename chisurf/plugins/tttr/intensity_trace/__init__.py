"""
Intensity Trace Analysis for Single-Molecule Data

A TTTR file binned per detector into an intensity trace, its count histograms, a hidden Markov model of the trace
(states, BIC elbow, dwell times with exponential fits, transition matrix), FRET efficiency per state, and the burst IDs,
traces and histograms written beside the file.

The state and computation are :mod:`.model` (Qt-free); the native window is :mod:`.gui.app`, the Qt widget
:mod:`.qt_tool` (the fallback). The Qt names are imported only when asked for, so the native app loads without Qt.
"""

# Plugin brand icon (unified emoji set)
icon = "📶"

name = "Spectroscopy:Single-Molecule:Intensity trace"

_QT_NAMES = ("DistPlotWindow", "DwellTimeWindow", "ElbowPlotWindow", "IntensityPlotWidget", "IntensityTrace",
             "TransitionMatrixWindow")


def __getattr__(attr):
    if attr in _QT_NAMES:
        from . import qt_tool

        return getattr(qt_tool, attr)
    if attr in ("compute_bic_curve", "compute_dwell_times", "save_burst_ids"):
        from . import model

        return getattr(model, attr)
    raise AttributeError(attr)


if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's gui/emtk entries come first
    from chisurf.plugins.tttr.intensity_trace.qt_tool import IntensityTrace

    window = IntensityTrace()
    window.show()
