"""
Intensity Trace Analysis for Single-Molecule Data

A TTTR file binned per detector into an intensity trace, its count histograms, a hidden Markov model of the trace
(states, BIC elbow, dwell times with exponential fits, transition matrix), FRET efficiency per state, and the burst IDs,
traces and histograms written beside the file.

The state and computation are :mod:`.model` (Qt-free); the only window is the native app :mod:`.gui.app`. The Qt tool
was retired with the pyqtgraph dependency: the app has every control, plot and hand-off it had.
"""

# Plugin brand icon (unified emoji set)
icon = "📶"

name = "Spectroscopy:Single-Molecule:Intensity trace"


def __getattr__(attr):
    if attr in ("compute_bic_curve", "compute_dwell_times", "save_burst_ids"):
        from . import model

        return getattr(model, attr)
    raise AttributeError(attr)


if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.tttr.intensity_trace.gui.app import make_app

    window = ControlHost(make_app())
    window.show()
