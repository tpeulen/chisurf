"""The node editor, drawn by cmtk instead of by a ``QGraphicsScene``.

This is the replacement for ``scene.py`` + ``view.py`` + ``node_item.py`` +
``edge_item.py`` + ``port_item.py``: one control that draws a
:class:`~.document.GraphDocument` through :mod:`cmtk.nodes` and edits it in
place. It owns no ``QGraphicsItem``, imports no Qt, and runs in a test with no
display -- which is the point of the move, since the Qt version could not.

Two objects
-----------
:class:`GraphControl`
    The whole editor, as a cmtk *control*: ``draw``, ``press``, ``drag``,
    ``release``, ``hover``, ``scroll``, ``key``. That is the contract
    :func:`cmtk.qt_host.ControlHost` hosts, and it is also the contract a
    browser host and a headless test satisfy, so there is one implementation
    rather than one per surface.
:class:`NodeContentRenderer`
    What goes *inside* a node body. The Qt editor put a real ``QWidget`` in
    each node -- a slider, a combo, a code editor -- through a proxy item. cmtk
    has the same controls as immediate-mode calls, so a node's body is a
    function of its config rather than a widget to keep in sync with it.

Reading the pointer
-------------------
The host reports presses and drags but not which button, and never a wheel
button. cmtk's node editor pans on the middle button, which therefore cannot
arrive. The panning gesture is **Alt-drag** here, and the wheel zooms; both are
translated into the ``IO`` fields :mod:`cmtk.nodes` reads, so the editor itself
needs no special case.
"""
from __future__ import annotations

import logging
import typing

from cmtk import im, nodes

from .document import GraphDocument, GraphEdge, GraphNode

__all__ = ["GraphControl", "NodeContentRenderer"]

logger = logging.getLogger(__name__)

#: Qt's modifier mask bits, as integers, so this module needs no Qt import to
#: read the mask the host hands it. ``Qt.ShiftModifier`` is 0x02000000 and
#: ``Qt.ControlModifier`` 0x04000000 on every binding.
_SHIFT: int = 0x02000000
_CONTROL: int = 0x04000000
_ALT: int = 0x08000000

#: Width pushed for the controls inside a node body. Without it a slider claims
#: the whole editor's width -- an item's default width comes from its container,
#: and a node is not one.
NODE_ITEM_WIDTH: float = 130.0


class NodeContentRenderer:
    """Draws the body of a node: whatever its type says belongs there.

    The Qt editor built a ``QWidget`` per node and parked it in the scene with
    a proxy item. That is why the old node code is 700 lines: a proxy has to be
    positioned, scaled with the view, shown and hidden with the node, and told
    when the model changed. Immediate mode has none of that -- a body is a
    function called while the node is open, and deleting the call deletes the
    control.

    Subclass and override :meth:`draw_body` to add a node type. The default
    renders the config keys it recognises and, for anything else, the value as
    read-only text -- which is deliberately not nothing: a node type nobody has
    written a body for still shows what it holds.

    **Nothing here may draw at the container's full width.** A node is not a
    container: an item that takes the width it is offered takes the width of
    the whole *editor*, so one node grows to span the viewport, every node
    behind it is hidden, and a fit-to-content then zooms out to frame a graph
    that is a thousand pixels wide for no reason. ``label_text`` and the other
    label/value pairs do exactly that -- they right-align the value against the
    container edge -- so a key/value row is drawn here as one ``text`` call
    instead, and every real control gets an explicit width
    (:data:`NODE_ITEM_WIDTH`, pushed by the caller).
    """

    #: Config keys drawn as a float slider, mapped to ``(low, high)``.
    SLIDERS: dict = {
        "value": (0.0, 10000.0),
        "kappa2": (0.0, 4.0),
        "n": (1.0, 2.0),
    }

    #: Config keys drawn as a combo, mapped to their options.
    COMBOS: dict = {
        "op": ["Add", "Subtract", "Multiply", "Divide"],
        "source_mode": ["Laser Lines (Manual)", "Spectrum"],
        "mode": ["A", "B", "C"],
    }

    def node_style(self, node: GraphNode) -> typing.Optional[tuple]:
        """The title-bar colour this node should have, if not the default.

        Parameters
        ----------
        node : GraphNode
            The node about to be drawn.

        Returns
        -------
        tuple or None
            ``(r, g, b, a)``, or ``None`` to take the editor's palette.

        Notes
        -----
        A hook rather than a field on the node, because the colour is a
        *rendering* decision about a kind of node and the document is what gets
        serialised. Writing it into the config would put a palette in every
        saved file, and changing the palette would then leave every existing
        file painted the old way.
        """
        return None

    def link_style(self, edge: typing.Any) -> typing.Optional[tuple]:
        """The colour and thickness this edge should have, if not the default.

        Parameters
        ----------
        edge : GraphEdge
            The edge about to be drawn.

        Returns
        -------
        tuple or None
            ``(colour, thickness)``, or ``None`` to take the editor's palette.

        Notes
        -----
        Exists because a graph whose edges mean different things cannot say so
        in one colour. A dataflow graph does not need this -- every edge means
        the same -- but a parameter network has ownership, links and base
        edges, and drawing them alike is a claim the picture makes and the
        model does not.
        """
        return None

    def port_label(self, node: GraphNode, port: typing.Any, is_output: bool) -> str:
        """The text drawn beside a pin.

        Parameters
        ----------
        node : GraphNode
            The node the port belongs to.
        port : PortSpec
            The port.
        is_output : bool
            Which side it is on.

        Returns
        -------
        str
            The name, with the declared type appended when there is one.
            Return ``""`` to draw no label at all -- which is right for a graph
            where every node has the same one input and one output, since the
            label then costs a row per node and says nothing that the shape of
            the graph does not already say.
        """
        return f"{port.name} [{port.port_type}]" if port.port_type else port.name

    def draw_body(self, node: GraphNode, read_only: bool) -> bool:
        """Draw one node's contents and report whether anything changed.

        Parameters
        ----------
        node : GraphNode
            The node being drawn. Its ``config`` is edited in place.
        read_only : bool
            When ``True`` the controls are drawn but not accepted, so a viewer
            looks like the editor rather than like a different program.

        Returns
        -------
        bool
            ``True`` when the user changed something.
        """
        changed = False
        for key, value in list(node.config.items()):
            if key.startswith("_"):
                # Convention in this tree: an underscore key is machinery the
                # node kept for itself (a cached result, a redraw callback),
                # not something a user set.
                continue
            if key in self.SLIDERS and isinstance(value, (int, float)):
                low, high = self.SLIDERS[key]
                moved, new = im.slider_float(key, float(value), low, high)
                if moved and not read_only:
                    node.config[key] = new
                    changed = True
            elif key in self.COMBOS:
                options = self.COMBOS[key]
                index = options.index(value) if value in options else 0
                moved, new_index = im.combo(key, index, options)
                if moved and not read_only:
                    node.config[key] = options[new_index]
                    changed = True
            elif isinstance(value, bool):
                moved, new = im.checkbox(key, value)
                if moved and not read_only:
                    node.config[key] = new
                    changed = True
            elif isinstance(value, str) and len(value) < 60:
                im.text(f"{key}: {value}")
            elif isinstance(value, (int, float)):
                im.text(f"{key}: {value:g}")
        return changed


class GraphControl:
    """A node editor over one :class:`~.document.GraphDocument`.

    Parameters
    ----------
    document : GraphDocument, optional
        The graph to edit; an empty one when omitted.
    read_only : bool
        Refuse every edit -- no dragging, no linking, no deleting. Selection
        and navigation still work, because a viewer nobody can pan is not a
        viewer.
    content : NodeContentRenderer, optional
        What to draw inside node bodies.
    on_change : callable, optional
        Called with no arguments after any edit that changed the graph.
    on_select : callable, optional
        Called with ``(kind, payload)`` when the selection changes, where
        `kind` is ``"node"`` or ``"edge"``.

    Attributes
    ----------
    document : GraphDocument
        The graph. Replace it with :meth:`set_document`, which resets the view
        state that belonged to the old one.
    editor : cmtk.nodes.EditorContext
        Pan, zoom, node positions and selection.
    """

    def __init__(
        self,
        document: typing.Optional[GraphDocument] = None,
        read_only: bool = False,
        content: typing.Optional[NodeContentRenderer] = None,
        on_change: typing.Optional[typing.Callable] = None,
        on_select: typing.Optional[typing.Callable] = None,
    ) -> None:
        self.document = document if document is not None else GraphDocument()
        self.read_only = bool(read_only)
        self.content = content if content is not None else NodeContentRenderer()
        self.on_change = on_change
        self.on_select = on_select

        self.editor = nodes.EditorContext()
        self.show_minimap = True
        self.io = im.IO()
        self.storage: dict = {}

        #: The box the control was last drawn into, so a caller that wants to
        #: fit the view has something to fit *to* without guessing.
        self._box: tuple = (0.0, 0.0, 0.0, 0.0)
        #: Set when the pointer is panning, since the host never reports the
        #: middle button that cmtk.nodes pans with.
        self._panning = False
        self._pan_from: tuple = (0.0, 0.0)
        #: Deferred to the next draw, because a fit needs measured node sizes
        #: and those only exist after a frame has been drawn.
        self._fit_pending = False
        self._last_selection: tuple = ((), ())

    # -- the graph ------------------------------------------------------

    def set_document(self, document: GraphDocument, fit: bool = True) -> None:
        """Replace the graph.

        Parameters
        ----------
        document : GraphDocument
            The new graph.
        fit : bool
            Frame it once it has been drawn.

        Notes
        -----
        A fresh :class:`~cmtk.nodes.EditorContext` comes with it. Keeping the
        old one would carry the previous graph's node positions across by id,
        so loading a second graph whose ids happen to overlap would place its
        nodes wherever the first graph's were -- and the saved positions in the
        file would be silently ignored.
        """
        self.document = document
        self.editor = nodes.EditorContext()
        self._fit_pending = bool(fit)
        self._sync_positions()

    def _sync_positions(self) -> None:
        """Push each node's stored position into the renderer's pool."""
        for node in self.document.nodes:
            nodes.set_node_grid_space_pos(
                self.editor, self.document.node_number(node.id), node.pos
            )
            if self.read_only:
                nodes.set_node_draggable(
                    self.editor, self.document.node_number(node.id), False
                )

    def _pull_positions(self) -> None:
        """Copy dragged positions back out of the renderer into the document.

        Notes
        -----
        The renderer is the authority *while dragging* and the document is the
        authority for everything else, so this runs every frame rather than on
        drag-end: a node moved by a keyboard nudge, a layout pass or an undo
        must also end up in the document, and each of those would need its own
        hook otherwise.
        """
        for node in self.document.nodes:
            node.pos = nodes.get_node_grid_space_pos(
                self.editor, self.document.node_number(node.id)
            )

    def fit(self) -> None:
        """Frame the whole graph at the next draw."""
        self._fit_pending = True

    # -- the cmtk control contract --------------------------------------

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        """Draw the editor into the given box.

        Parameters
        ----------
        painter : object
            Anything implementing cmtk's painter contract.
        x, y, w, h : float
            The box, in the painter's coordinates.
        """
        self._box = (x, y, w, h)
        with im.frame(painter, (x, y, w, h), io=self.io, storage=self.storage):
            self._draw_graph((x, y, w, h))

    def _draw_graph(self, box: tuple) -> None:
        """Submit the whole editor for one frame.

        Parameters
        ----------
        box : tuple
            The editor's box, ``(x, y, w, h)``.
        """
        document = self.document
        changed = False

        with nodes.editor_context(self.editor, box=box):
            if self.show_minimap and document.nodes:
                nodes.mini_map(self.editor, size_fraction=0.18,
                               location=nodes.MiniMapLocation.BOTTOM_RIGHT)

            for node in document.nodes:
                changed |= self._draw_node(node)

            for index, edge in enumerate(document.edges):
                source, target = document.node(edge.source), document.node(edge.target)
                if source is None or target is None:
                    continue
                style = self.content.link_style(edge)
                colour, thickness = style if style is not None else (None, None)
                nodes.link(
                    document.link_id(index),
                    document.pin_id(source.id, edge.source_port, True),
                    document.pin_id(target.id, edge.target_port, False),
                    colour=colour,
                    thickness=thickness,
                )

        self._pull_positions()
        changed |= self._apply_interactions()
        self._report_selection()

        if self._fit_pending and self.editor.content_bounds() is not None:
            # Only now: the fit needs node sizes, and a node has no size until
            # it has been drawn once.
            self.editor.fit_to_content(box)
            self._fit_pending = False

        if changed and self.on_change is not None:
            self.on_change()

    def _draw_node(self, node: GraphNode) -> bool:
        """Submit one node.

        Parameters
        ----------
        node : GraphNode
            The node to draw.

        Returns
        -------
        bool
            ``True`` when the user changed its config.
        """
        document = self.document
        number = document.node_number(node.id)
        title_colour = self.content.node_style(node)
        if title_colour is not None:
            # Pushed around the whole node, not just the title bar: the body is
            # drawn at end_node(), which reads the palette then, so a pop
            # before that would paint every node in the default colour.
            nodes.push_color_style(nodes.Col.TITLE_BAR, title_colour)
        nodes.begin_node(number)
        im.push_item_width(NODE_ITEM_WIDTH)

        nodes.begin_node_title_bar()
        im.text(node.title)
        nodes.end_node_title_bar()

        changed = False
        if not node.collapsed:
            # Inputs first, then the body, then outputs: a pin's vertical
            # position is its attribute's, so this order is what puts inputs
            # up the left side and outputs down the right rather than
            # interleaving them.
            for index, port in enumerate(node.inputs):
                nodes.begin_input_attribute(document.pin_id(node.id, index, False))
                im.text(self.content.port_label(node, port, False))
                nodes.end_input_attribute()

            if node.config:
                nodes.begin_static_attribute(number * document.PINS_PER_NODE - 1)
                changed = self.content.draw_body(node, self.read_only)
                nodes.end_static_attribute()

            for index, port in enumerate(node.outputs):
                nodes.begin_output_attribute(document.pin_id(node.id, index, True))
                im.text(self.content.port_label(node, port, True))
                nodes.end_output_attribute()
        else:
            # Collapsed still submits the pins, or every link to this node
            # would vanish while it is folded up -- which reads as the edges
            # having been deleted.
            for index, port in enumerate(node.inputs):
                nodes.begin_input_attribute(document.pin_id(node.id, index, False))
                im.text("")
                nodes.end_input_attribute()
            for index, port in enumerate(node.outputs):
                nodes.begin_output_attribute(document.pin_id(node.id, index, True))
                im.text("")
                nodes.end_output_attribute()

        im.pop_item_width()
        nodes.end_node()
        if title_colour is not None:
            nodes.pop_color_style()
        return changed

    def _apply_interactions(self) -> bool:
        """Turn this frame's editor events into edits of the document.

        Returns
        -------
        bool
            ``True`` when the graph changed.
        """
        if self.read_only:
            return False
        document = self.document
        changed = False

        created = nodes.is_link_created(self.editor)
        if created is not None:
            output, input_ = created
            source = document.port_for_pin(output)
            target = document.port_for_pin(input_)
            if source is not None and target is not None:
                edge = GraphEdge(source[0].id, source[1], target[0].id, target[1])
                if self._accepts(edge):
                    changed |= document.add_edge(edge)

        destroyed = nodes.is_link_destroyed(self.editor)
        if destroyed is not None:
            edge = document.edge_for_link(destroyed)
            if edge is not None:
                document.remove_edge(edge)
                changed = True

        return changed

    def _accepts(self, edge: GraphEdge) -> bool:
        """Decide whether an edge the user drew is allowed.

        Parameters
        ----------
        edge : GraphEdge
            The proposed edge.

        Returns
        -------
        bool
            ``False`` for a self-link, for an input that is already fed, or
            for two ports whose declared types disagree.

        Notes
        -----
        An **untyped** port matches only another untyped one, which is what
        the two "spectral" defaults used to mean before the default was
        removed. Matching untyped against everything would let a spectrum be
        wired into a scalar and only fail at evaluation.
        """
        if edge.source == edge.target:
            return False
        source = self.document.node(edge.source)
        target = self.document.node(edge.target)
        if source is None or target is None:
            return False
        out_port = source.port(edge.source_port, True)
        in_port = target.port(edge.target_port, False)
        if out_port is None or in_port is None:
            return False
        if out_port.port_type != in_port.port_type:
            return False
        # One edge per input. A second one is not a merge, it is the first one
        # being silently ignored by everything downstream.
        return not any(
            e.target == edge.target and e.target_port == edge.target_port
            for e in self.document.edges
        )

    def _report_selection(self) -> None:
        """Tell the host about a selection that changed since last frame."""
        if self.on_select is None:
            return
        selection = (
            tuple(nodes.get_selected_nodes(self.editor)),
            tuple(nodes.get_selected_links(self.editor)),
        )
        if selection == self._last_selection:
            return
        self._last_selection = selection
        node_ids, link_ids = selection
        if node_ids:
            node = self.document.node_for_number(node_ids[0])
            if node is not None:
                self.on_select("node", self._node_payload(node))
        elif link_ids:
            edge = self.document.edge_for_link(link_ids[0])
            if edge is not None:
                self.on_select("edge", self._edge_payload(edge))

    def _node_payload(self, node: GraphNode) -> dict:
        """What a host is told about a selected node.

        Parameters
        ----------
        node : GraphNode
            The selected node.

        Returns
        -------
        dict
            The node's serialised form -- the same shape the JSON carries, so
            a host reads one format rather than two.
        """
        return {
            "id": node.id,
            "type": node.type,
            "title": node.title,
            "config": dict(node.config),
            "pos": list(node.pos),
        }

    def _edge_payload(self, edge: GraphEdge) -> dict:
        """What a host is told about a selected edge.

        Parameters
        ----------
        edge : GraphEdge
            The selected edge.

        Returns
        -------
        dict
            The edge's serialised form.
        """
        return {
            "source": edge.source,
            "source_port": edge.source_port,
            "target": edge.target,
            "target_port": edge.target_port,
            "config": dict(edge.config),
        }

    # -- pointer and keyboard -------------------------------------------

    def press(self, px: float, py: float, *box, modifiers: int = 0, clicks: int = 1) -> None:
        """Accept a press.

        Parameters
        ----------
        px, py : float
            Where the press landed.
        *box
            The control's box, as the host passes it; and, positionally, the
            modifier mask and click count the host appends.
        modifiers : int
            Qt's modifier mask, when passed by keyword.
        clicks : int
            1 for a click, 2 for a double click.
        """
        modifiers, clicks = self._trailing(box, modifiers, clicks)
        self.io.mouse_pos = (px, py)
        self.io.mouse_clicked_pos[0] = (px, py)
        self.io.key_ctrl = bool(modifiers & _CONTROL)
        self.io.key_shift = bool(modifiers & _SHIFT)

        if modifiers & _ALT:
            # The host never reports the middle button, which is what
            # cmtk.nodes pans with, so panning is a modifier here and is
            # applied directly rather than through the editor's own machine.
            self._panning = True
            self._pan_from = (px, py)
            return

        self.io.mouse_clicked[0] = True
        self.io.mouse_down[0] = True
        if clicks >= 2:
            self.io.mouse_double_clicked[0] = True
            self._toggle_collapse_under(px, py)

    @staticmethod
    def _trailing(box: tuple, modifiers: int, clicks: int) -> tuple:
        """Read the modifier mask and click count out of the trailing args.

        Parameters
        ----------
        box : tuple
            Everything the host passed after ``px``/``py``.
        modifiers, clicks : int
            The keyword defaults.

        Returns
        -------
        tuple
            ``(modifiers, clicks)``.

        Notes
        -----
        ``cmtk.qt_host`` calls ``press(px, py, x, y, w, h, modifiers, clicks)``
        positionally, and other hosts pass them by keyword. Accepting both is
        two lines here and saves every host from agreeing on one.
        """
        extra = list(box)[4:]
        if len(extra) >= 1:
            modifiers = int(extra[0])
        if len(extra) >= 2:
            clicks = int(extra[1])
        return modifiers, clicks

    def _toggle_collapse_under(self, px: float, py: float) -> None:
        """Fold or unfold the node under the pointer.

        Parameters
        ----------
        px, py : float
            The pointer, in screen space.
        """
        if self.read_only:
            return
        number = nodes.is_node_hovered(self.editor)
        if number is None:
            return
        node = self.document.node_for_number(number)
        if node is not None:
            node.collapsed = not node.collapsed
            if self.on_change is not None:
                self.on_change()

    def drag(self, px: float, py: float, *_box) -> None:
        """Accept a drag.

        Parameters
        ----------
        px, py : float
            The pointer's new position.
        *_box
            The control's box; unused.
        """
        if self._panning:
            self.editor.canvas.panning = (
                self.editor.canvas.panning[0] + (px - self._pan_from[0]),
                self.editor.canvas.panning[1] + (py - self._pan_from[1]),
            )
            self._pan_from = (px, py)
            return
        self.io.mouse_pos = (px, py)
        self.io.mouse_clicked[0] = False
        self.io.mouse_down[0] = True

    def release(self) -> None:
        """Accept the button coming up."""
        self._panning = False
        self.io.mouse_down[0] = False
        self.io.mouse_released[0] = True

    def hover(self, px: float, py: float, *_box) -> None:
        """Accept a move with no button down.

        Parameters
        ----------
        px, py : float
            The pointer's position.
        *_box
            The control's box; unused.
        """
        self.io.mouse_pos = (px, py)

    def scroll(self, rows: int) -> None:
        """Zoom on the wheel.

        Parameters
        ----------
        rows : int
            Negative for a notch away from the user, as the host sends it.

        Notes
        -----
        Zoom rather than scroll, because a node canvas has no rows to scroll
        through -- and because that is what every node editor a user has met
        does with the wheel.
        """
        self.io.mouse_wheel = -float(rows) / 3.0

    def key(self, key: int, text: str, modifiers: int) -> bool:
        """Accept a key press.

        Parameters
        ----------
        key : int
            Qt's key code.
        text : str
            The character it produced, if any.
        modifiers : int
            Qt's modifier mask.

        Returns
        -------
        bool
            ``True`` when the editor consumed it, so the host stops there.
        """
        # Qt.Key_Delete is 0x01000007 and Qt.Key_Backspace 0x01000003 on every
        # binding; naming them here keeps this module Qt-free.
        if key in (0x01000007, 0x01000003) and not self.read_only:
            return self.delete_selection()
        if text in ("f", "F"):
            self.fit()
            return True
        return False

    def delete_selection(self) -> bool:
        """Delete every selected node and link.

        Returns
        -------
        bool
            ``True`` when anything was deleted.
        """
        if self.read_only:
            return False
        document = self.document
        removed = False

        # Links first: deleting a node already takes its edges, and doing links
        # afterwards would then be deleting by an index the node removal moved.
        for link_id in nodes.get_selected_links(self.editor):
            edge = document.edge_for_link(link_id)
            if edge is not None:
                document.remove_edge(edge)
                removed = True

        for number in nodes.get_selected_nodes(self.editor):
            node = document.node_for_number(number)
            if node is not None:
                document.remove_node(node.id)
                removed = True

        if removed:
            nodes.clear_node_selection(self.editor)
            nodes.clear_link_selection(self.editor)
            # Node numbers are positions in the list, so removing one renumbers
            # everything after it. The renderer's pool is keyed by those
            # numbers, and keeping it would move the survivors onto the deleted
            # node's coordinates.
            self.set_document(document, fit=False)
            if self.on_change is not None:
                self.on_change()
        return removed

    def content_key(self) -> tuple:
        """What this control is about to draw, for :mod:`cmtk.redraw`.

        Returns
        -------
        tuple
            Everything the picture depends on: the graph's shape, where the
            nodes are, the view, and the selection.
        """
        return (
            tuple((n.id, n.title, n.collapsed, n.pos, len(n.inputs), len(n.outputs))
                  for n in self.document.nodes),
            tuple(e.key() for e in self.document.edges),
            self.editor.canvas.panning,
            self.editor.canvas.zoom,
            tuple(sorted(self.editor.selected_nodes)),
            tuple(sorted(self.editor.selected_links)),
        )
