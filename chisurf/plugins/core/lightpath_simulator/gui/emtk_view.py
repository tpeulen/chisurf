"""The beam path, drawn by emtk: nodes with their spectra inside them.

This replaces the `QGraphicsProxyWidget` node bodies in ``node_types.py``. The
old arrangement put a real ``QWidget`` -- a combo, a line edit, a chiplot plot
-- inside every node, which is why that module contains a function that patches
``QComboBox.showPopup`` to force an opaque background, another that walks up
from a proxy through the scene to a view to a parent to find something with a
``propagate_graph`` method, and a "hack to trigger node resize" that reaches
into the node item's private ``_build_path``. None of those are bugs in that
code; they are what embedding widgets in a scene costs.

Immediate mode has none of it. A node body is a function of the node's config,
called while the node is open. There is no proxy to cross, so an edit reports
itself by returning ``True``; there is nothing to resize, because the node is
measured from what was drawn; and a popup is drawn by the same painter as
everything else, so it cannot be transparent against its own background.

The three-layer spectrum
------------------------
Every optical node draws the same picture, and it is the point of the tool:

* the **input** spectrum, summed over every upstream port, dotted and grey;
* the **output** spectrum, summed over this node's ports, solid and white;
* the node's own **characteristic** -- a filter's transmission, a detector's
  quantum efficiency, a sample's absorption *and* emission -- on top, coloured,
  so what the component does is visible against what reaches it.

Each is normalised independently. They are physically different quantities
(a spectral flux, a dimensionless transmission), so a shared axis would
either flatten the transmission curve to nothing or clip the flux.
"""
from __future__ import annotations

import logging
import typing

import numpy as np

from emtk import im, implot, nodes

from chisurf.gui.widgets.node_editor.emtk_control import NodeContentRenderer
from chisurf.gui.widgets.node_editor.document import GraphNode
from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import WAVELENGTHS

__all__ = ["BeampathContent", "PROBE_CATEGORY"]

logger = logging.getLogger(__name__)

#: Which probes each node type may be assigned, as a predicate over the probe
#: records the backend hands back. Taken from the Qt factories so the same
#: filter reaches the same list; a filter node offering detector responses is
#: how a beam path acquires a component that cannot be there.
PROBE_CATEGORY: dict = {
    "filter": lambda p: (p.get("category") == "filter"
                         or (not p.get("category") and p.get("has_trans"))),
    "splitter": lambda p: (p.get("category") in ("dichroic", "polarizer")
                           or (not p.get("category") and p.get("has_trans"))),
    "detector": lambda p: (p.get("category") == "detector"
                           or (not p.get("category") and p.get("has_qe"))),
    "sample": lambda p: bool(p.get("has_abs") or p.get("has_em")),
    "light_source": lambda p: bool(p.get("has_ex") or p.get("has_em")),
}

#: The plot's size inside a node, in pixels. Fixed rather than proportional:
#: a node is sized by its contents, so a plot that asked for a fraction of
#: something would be asking for a fraction of itself.
PLOT_SIZE: tuple = (200.0, 96.0)

#: Curve colours, matching the Qt version so a user recognises the picture.
INPUT_COLOUR: tuple = (150, 150, 150, 255)
OUTPUT_COLOUR: tuple = (235, 235, 235, 255)
CHARACTERISTIC_COLOUR: tuple = (80, 220, 120, 255)
ABSORPTION_COLOUR: tuple = (0, 200, 255, 255)
EMISSION_COLOUR: tuple = (255, 180, 0, 255)


def _summed(spectra: typing.Any) -> typing.Optional[np.ndarray]:
    """Add up the arrays in a nested ``{port: {source: array}}`` mapping.

    Parameters
    ----------
    spectra : object
        What the backend puts in ``_input_spectra`` / ``_output_spectra``: a
        mapping of port name to a mapping of upstream node id to an array.

    Returns
    -------
    numpy.ndarray or None
        The sum over every array found, or ``None`` when there are none.

    Notes
    -----
    Written to tolerate anything, because this reads a *deserialised RPC
    response*: a port whose upstream produced nothing is an empty dict, a
    failed node is missing entirely, and a stale graph has ports that no
    longer exist. None of those is an error worth stopping a repaint for --
    the node simply has no input spectrum to draw yet.
    """
    if not isinstance(spectra, dict):
        return None
    total = None
    for per_port in spectra.values():
        if not isinstance(per_port, dict):
            continue
        for array in per_port.values():
            if not isinstance(array, np.ndarray) or array.shape != WAVELENGTHS.shape:
                continue
            total = array.astype(float).copy() if total is None else total + array
    return total


def _normalised(values: typing.Optional[np.ndarray]) -> typing.Optional[list]:
    """Scale a spectrum to peak at one, for plotting beside the others.

    Parameters
    ----------
    values : numpy.ndarray or None
        The spectrum.

    Returns
    -------
    list or None
        The values as a list, scaled so the maximum is 1, or ``None`` when
        there is nothing to draw. An all-zero spectrum returns ``None`` rather
        than a flat line along the axis: a component that passes nothing and a
        component that has not been computed yet look identical as a zero line,
        and only one of them is worth drawing.
    """
    if values is None:
        return None
    peak = float(np.max(values)) if values.size else 0.0
    if not np.isfinite(peak) or peak <= 0.0:
        return None
    return (values / peak).tolist()


class BeampathContent(NodeContentRenderer):
    """Node bodies for the beam path: a probe chooser and the spectra.

    Parameters
    ----------
    probes : list, optional
        The probe records the backend offers, each with ``probe_id``,
        ``name`` and the ``has_*``/``category`` fields
        :data:`PROBE_CATEGORY` filters on.

    Attributes
    ----------
    probes : list
        As passed. Replace it with :meth:`set_probes` when the loader finishes,
        which it does on a worker thread after the window is already open.
    """

    def __init__(self, probes: typing.Optional[list] = None) -> None:
        self.probes: list = list(probes or [])
        #: Node ids whose plot the user has folded away, so a dense path can be
        #: read as a diagram rather than as a wall of axes.
        self.hidden_plots: set = set()

    def set_probes(self, probes: list) -> None:
        """Adopt a freshly loaded probe list.

        Parameters
        ----------
        probes : list
            The probe records.
        """
        self.probes = list(probes or [])

    def choices(self, node_type: str) -> list:
        """The probes a node of this type may be assigned.

        Parameters
        ----------
        node_type : str
            The registry type id.

        Returns
        -------
        list
            ``[(label, probe_id), ...]``, always starting with ``("None", None)``
            so a component can be cleared as well as set.
        """
        matches = PROBE_CATEGORY.get(node_type)
        chosen = [p for p in self.probes if matches is None or matches(p)]
        return [("None", None)] + [
            (str(p.get("name", p.get("probe_id"))), p.get("probe_id")) for p in chosen
        ]

    # -- the body -------------------------------------------------------

    def draw_body(self, node: GraphNode, read_only: bool) -> bool:
        """Draw one optical node's contents.

        Parameters
        ----------
        node : GraphNode
            The node. Its ``config`` is edited in place.
        read_only : bool
            Draw but do not accept.

        Returns
        -------
        bool
            ``True`` when the user changed something the simulation depends on.
        """
        changed = False
        if node.type == "detector":
            changed |= self._draw_detector_name(node, read_only)
        if node.type == "light_source":
            changed |= self._draw_light_source(node, read_only)
        elif node.type == "forster_radius":
            return self._draw_forster(node, read_only)
        elif node.type in PROBE_CATEGORY:
            changed |= self._draw_probe_chooser(node, read_only)

        changed |= self._draw_spectra(node)
        return changed

    def _draw_detector_name(self, node: GraphNode, read_only: bool) -> bool:
        """Draw the detector's name field.

        Parameters
        ----------
        node : GraphNode
            The detector.
        read_only : bool
            Draw but do not accept.

        Returns
        -------
        bool
            ``True`` when the name changed. It is not just a label: the
            crosstalk table is keyed by it, so renaming a detector renames a
            column of results.
        """
        edited, value = im.input_text("name", str(node.config.get("detector_name", "Detector")))
        if edited and not read_only:
            node.config["detector_name"] = value
            return True
        return False

    def _draw_probe_chooser(self, node: GraphNode, read_only: bool) -> bool:
        """Draw the component chooser for a filter, splitter, detector or sample.

        Parameters
        ----------
        node : GraphNode
            The node.
        read_only : bool
            Draw but do not accept.

        Returns
        -------
        bool
            ``True`` when a different component was chosen.
        """
        options = self.choices(node.type)
        labels = [label for label, _ in options]
        current = node.config.get("probe_id", node.config.get("spectrum_id"))
        index = next((i for i, (_, pid) in enumerate(options) if pid == current), 0)

        moved, chosen = im.combo("component", index, labels)
        if moved and not read_only:
            node.config["probe_id"] = options[chosen][1]
            # The two keys are alternatives, and leaving the old one behind
            # means the backend sees a component the user replaced.
            node.config.pop("spectrum_id", None)
            return True
        return False

    def _draw_light_source(self, node: GraphNode, read_only: bool) -> bool:
        """Draw the light source's mode and its manual laser lines.

        Parameters
        ----------
        node : GraphNode
            The source.
        read_only : bool
            Draw but do not accept.

        Returns
        -------
        bool
            ``True`` when the source changed.
        """
        modes = ["manual", "probe"]
        current = str(node.config.get("source_mode", "manual"))
        index = modes.index(current) if current in modes else 0
        changed = False

        moved, chosen = im.combo("mode", index, modes)
        if moved and not read_only:
            node.config["source_mode"] = modes[chosen]
            changed = True

        if node.config.get("source_mode", "manual") == "manual":
            lines = node.config.get("manual_lines") or []
            text = ", ".join(f"{float(v):g}" for v in lines if _is_number(v))
            edited, value = im.input_text("lines", text)
            if edited and not read_only:
                node.config["manual_lines"] = _parse_lines(value)
                changed = True
        else:
            changed |= self._draw_probe_chooser(node, read_only)
        return changed

    def _draw_forster(self, node: GraphNode, read_only: bool) -> bool:
        """Draw the Förster-radius node: its two constants and the result.

        Parameters
        ----------
        node : GraphNode
            The node.
        read_only : bool
            Draw but do not accept.

        Returns
        -------
        bool
            ``True`` when a constant changed.
        """
        changed = False
        moved, kappa = im.slider_float(
            "kappa2", float(node.config.get("kappa2", 2.0 / 3.0)), 0.0, 4.0
        )
        if moved and not read_only:
            node.config["kappa2"] = kappa
            changed = True
        moved, refractive = im.slider_float(
            "n", float(node.config.get("n", 1.33)), 1.0, 2.0
        )
        if moved and not read_only:
            node.config["n"] = refractive
            changed = True

        radius = node.config.get("_r0")
        # Written as text rather than as a disabled field: it is an output,
        # and a greyed-out input still invites an edit that goes nowhere.
        im.text(f"R0: {radius:.1f} A" if _is_number(radius) else "R0: -")
        return changed

    def _draw_spectra(self, node: GraphNode) -> bool:
        """Draw the node's three-layer spectrum, with a fold-away toggle.

        Parameters
        ----------
        node : GraphNode
            The node whose config carries the simulated spectra.

        Returns
        -------
        bool
            Always ``False`` -- folding a plot away changes the picture, not
            the simulation, so it must not trigger a re-propagation.
        """
        incoming = _normalised(_summed(node.config.get("_input_spectra")))
        outgoing = _normalised(_summed(node.config.get("_output_spectra")))
        characteristic = node.config.get("_node_char")
        if incoming is None and outgoing is None and characteristic is None:
            return False

        shown = node.id not in self.hidden_plots
        toggled, shown = im.checkbox("spectrum", shown)
        if toggled:
            self.hidden_plots.discard(node.id) if shown else self.hidden_plots.add(node.id)
        if not shown:
            return False

        # NoLegend as well as CanvasOnly: a legend is drawn inside the plot
        # area and, at this size, covers the curves it names.
        scale = nodes.content_scale()
        flags = implot.ImPlotFlags_CanvasOnly | implot.ImPlotFlags_NoLegend
        if not implot.begin_plot(
            f"##spectrum{node.id}",
            (PLOT_SIZE[0] * scale, PLOT_SIZE[1] * scale), flags,
        ):
            return False
        try:
            axis = WAVELENGTHS.tolist()
            if incoming is not None:
                implot.set_next_line_style(INPUT_COLOUR, 1.0 * scale)
                implot.plot_line("in", axis, incoming)
            if outgoing is not None:
                implot.set_next_line_style(OUTPUT_COLOUR, 2.0 * scale)
                implot.plot_line("out", axis, outgoing)
            self._draw_characteristic(axis, characteristic, scale)
        finally:
            implot.end_plot()
        return False

    @staticmethod
    def _draw_characteristic(axis: list, characteristic: typing.Any,
                             scale: float = 1.0) -> None:
        """Draw the node's own response curve, on top of the spectra.

        Parameters
        ----------
        axis : list
            The wavelength axis.
        characteristic : object
            One array for a one-curve component, or a pair for a sample --
            absorption and emission, which are two curves and must not be
            summed into one.
        scale : float
            The editor's content scale, for the line widths.
        """
        if characteristic is None:
            return
        if isinstance(characteristic, (tuple, list)) and len(characteristic) == 2:
            for values, colour in zip(characteristic,
                                      (ABSORPTION_COLOUR, EMISSION_COLOUR)):
                curve = _normalised(np.asarray(values, dtype=float))
                if curve is not None:
                    implot.set_next_line_style(colour, 1.5 * scale)
                    implot.plot_line("char", axis, curve)
            return
        curve = _normalised(np.asarray(characteristic, dtype=float))
        if curve is not None:
            implot.set_next_line_style(CHARACTERISTIC_COLOUR, 1.5 * scale)
            implot.plot_line("char", axis, curve)


def _is_number(value: typing.Any) -> bool:
    """Report whether `value` is a finite real number.

    Parameters
    ----------
    value : object
        Anything.

    Returns
    -------
    bool
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and np.isfinite(value)


def _parse_lines(text: str) -> list:
    """Read a comma- or space-separated list of laser lines.

    Parameters
    ----------
    text : str
        What the user typed.

    Returns
    -------
    list
        The wavelengths that parsed, in order. Anything that does not parse is
        dropped rather than raising -- the field is edited a character at a
        time, so every intermediate state would otherwise be an error.
    """
    out = []
    for piece in text.replace(",", " ").split():
        try:
            out.append(float(piece))
        except ValueError:
            continue
    return out
