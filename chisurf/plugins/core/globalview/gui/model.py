"""The Global View, as a model: what it shows, what it edits, what its controls do.

Everything the window needs that is not drawing lives here, with no Qt in it:
the settings its ``globalview.view.json`` binds, the network or factor graph
it draws (as a :class:`~chisurf.gui.widgets.node_editor.document.GraphDocument`
the emtk node editor takes), the records of its two tables, the selection, and
an action per button. :mod:`.surface` draws it and :mod:`.tool` hosts it in a
window; a test drives it with neither.

Where the graph comes from
--------------------------
One enumeration, :func:`chisurf.core.fitting.parameter_network.session_owners`,
feeds all of it: the parameter table's rows, the network, and the factor
graph. The window used to hold four parallel arrays (positions, edges, names,
kinds) indexed by position, which is how an edge ended up on the wrong
parameter whenever a filter dropped a node; nodes are now named by an id that
survives a rebuild (``"owner:<n>"``, ``"param:<uid>"``), and the selection is
kept by it.

Direction
---------
A link drawn from A to B in the editor makes **A follow B** -- the arrow the
user drew is the arrow the network then shows, follower to master. The Link
button keeps its documented order: the first parameter selected is the
master. Breaking a link in the editor unlinks its *follower*.
"""

from __future__ import annotations

import csv
import logging
import typing

from chisurf.core.fitting import parameter_network as pn
from chisurf.gui.widgets.node_editor.document import GraphDocument, GraphEdge, GraphNode
from chisurf.gui.widgets.node_editor.model import PortSpec
from chisurf.plugins.core.globalview.gui import emtk_view as ev

__all__ = ["GRAPH_LAYOUTS", "LAYOUT_EXTENT", "GlobalViewModel", "to_pixels"]

logger = logging.getLogger(__name__)

GRAPH_LAYOUTS = ["kamada_kawai", "spring", "shell", "arf", "spectral"]

#: The pixel box a layout is fitted into before it becomes a document.
LAYOUT_EXTENT: tuple = (900.0, 620.0)

REPRESENTATION_NETWORK = "network"
REPRESENTATION_FACTORS = "factor graph"


def to_pixels(positions: typing.Sequence, spread: float) -> list:
    """Fit layout coordinates into a pixel box, keeping their aspect ratio.

    Parameters
    ----------
    positions : sequence
        ``(x, y)`` per node, in the layout algorithm's own units (roughly
        ``-1..1``; used raw, every node lands within two grid units of every
        other and the editor's fit-to-content leaves a single pile).
    spread : float
        Multiplier on the fitted extent: above 1 the graph grows past the box
        and is read by panning.

    Returns
    -------
    list
        ``(x, y)`` per node, in grid pixels.
    """
    points = [(float(x), float(y)) for x, y in positions]
    if not points:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    if span_x < 1e-9 and span_y < 1e-9:
        return [(0.0, index * 90.0) for index, _ in enumerate(points)]
    scale = min(
        LAYOUT_EXTENT[0] / span_x if span_x > 1e-9 else float("inf"),
        LAYOUT_EXTENT[1] / span_y if span_y > 1e-9 else float("inf"),
    ) * max(float(spread), 0.05)
    return [((x - min(xs)) * scale, (y - min(ys)) * scale) for x, y in points]


def _layout(node_ids: list, edges: list, method: str) -> dict:
    """Positions by node id, from :mod:`chisurf.core.graph`'s layouts."""
    from chisurf.core import graph as cg

    graph = cg.Graph()
    number = {node_id: i for i, node_id in enumerate(node_ids)}
    for i in range(len(node_ids)):
        graph.add_node(i)
    for source, target, _kind in edges:
        if source in number and target in number:
            graph.add_edge(number[source], number[target])
    if len(node_ids) < 2:
        return {node_id: (0.0, 0.0) for node_id in node_ids}
    try:
        if method == "shell":
            pos = cg.shell_layout(graph, scale=1.0)
        elif method == "kamada_kawai":
            pos = cg.kamada_kawai_layout(graph, scale=1.0)
        elif method == "arf":
            pos = cg.arf_layout(graph, etol=1e-9, dt=0.01, scale=1.0)
        elif method == "spectral":
            pos = cg.spectral_layout(graph, scale=1.0)
        else:
            pos = cg.spring_layout(graph, iterations=500, scale=1.0)
    except Exception:  # noqa: BLE001 - a layout that fails must not blank the window
        logger.debug("globalview: layout %s failed", method, exc_info=True)
        pos = cg.spring_layout(graph, iterations=200, scale=1.0)
    return {node_id: tuple(pos[number[node_id]]) for node_id in node_ids}


class _Picture:
    """What is drawn: marks and edges by id, before a layout places them."""

    def __init__(self) -> None:
        #: ``node_id -> (kind, label, parameter or owner)``, in draw order.
        self.marks: dict = {}
        #: ``(source_id, target_id, edge kind)``.
        self.edges: list = []

    def signature(self) -> tuple:
        return (tuple((k, v[0], v[1]) for k, v in self.marks.items()), tuple(self.edges))


def _parameter_id(param: typing.Any) -> str:
    uid = str(getattr(param, "unique_identifier", "") or "")
    return f"param:{uid or id(param)}"


def _flag(obj: typing.Any, name: str) -> bool:
    try:
        return bool(getattr(obj, name, False))
    except Exception:  # noqa: BLE001
        return False


def _number(value: typing.Any) -> typing.Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class GlobalViewModel:
    """The Global View's state and behaviour; see the module docstring.

    Parameters
    ----------
    fits : callable, optional
        Returns the session's fits, in order. Defaults to the fitting client's.
    groups : callable, optional
        Returns the registered out-of-fit groups as ``(owner_id, label, group)``.
    mutator : object, optional
        Changes parameters (``set_value``, ``set_fixed``, ``set_bounds``,
        ``set_bounds_on``, ``link``, ``unlink``). Defaults to
        :class:`~chisurf.gui.widgets.fitting.parameter_mutator.FittingClientParamMutator`.

    Attributes
    ----------
    ask_open_path, ask_save_path : callable or None
        ``(title, file_filter) -> path or ""``, supplied by the host.
    warn : callable or None
        ``(title, message)``: tell the user something went wrong.
    open_help, open_guide : callable or None
        The host's help and guided tour.
    """

    representation_options = [REPRESENTATION_NETWORK, REPRESENTATION_FACTORS]

    def __init__(self, fits=None, groups=None, mutator=None) -> None:
        from chisurf.gui.widgets.node_editor.emtk_control import GraphControl

        self._fits = fits if fits is not None else _session_fits
        self._groups = groups if groups is not None else _registered_groups
        if mutator is None:
            from chisurf.gui.widgets.fitting.parameter_mutator import FittingClientParamMutator

            mutator = FittingClientParamMutator()
        self.mutator = mutator

        # -- settings (globalview.view.json) --
        self.representation = REPRESENTATION_NETWORK
        self.graph_layout = GRAPH_LAYOUTS[0]
        self.node_size = 13.0
        self.graph_scale = 1.0
        self.connect_owners = False
        self.include_fixed = False
        self.auto_refresh = True
        self.unlink_all = False
        self.shade_values = True

        # -- host hooks --
        self.ask_open_path: typing.Optional[typing.Callable] = None
        self.ask_save_path: typing.Optional[typing.Callable] = None
        self.warn: typing.Optional[typing.Callable] = None
        self.open_help: typing.Optional[typing.Callable] = None
        self.open_guide: typing.Optional[typing.Callable] = None

        # -- what is shown --
        self.owners: list = []
        self.rows: list = []
        self.factor_graph = None
        self.selection: list = []
        self.status = ""
        self.stale = False
        self._signature: typing.Optional[tuple] = None
        self._objects: dict = {}
        self._records: list = []
        self._records_by_uid: dict = {}

        self.content = ev.GlobalViewContent()
        self.content.radius_scale = self.node_size / 11.0
        self.control = GraphControl(
            content=self.content,
            on_select=self._on_graph_select,
            on_link=self._on_graph_link,
            on_unlink=self._on_graph_unlink,
        )
        ev.apply_network_style(self.control.editor)
        self.control.read_only = False
        self.rebuild(force=True)

    # ------------------------------------------------------------------ #
    # building
    # ------------------------------------------------------------------ #

    def rebuild(self, force: bool = False) -> None:
        """Re-read the fits; lay the graph out again if its shape changed.

        Parameters
        ----------
        force : bool
            Lay it out even when its shape is unchanged: what Refresh, a new
            layout or a new spread ask for. A running fit changes values every
            iteration and nothing else, and a layout re-run for each of those
            moves nothing and costs a lot -- so the automatic path passes
            ``False`` and only the tables and tooltips catch up.
        """
        try:
            fits = list(self._fits() or [])
        except Exception:  # noqa: BLE001
            logger.debug("globalview: no fits", exc_info=True)
            fits = []
        try:
            groups = list(self._groups() or [])
        except Exception:  # noqa: BLE001
            groups = []
        self.owners = pn.session_owners(fits, groups)
        self.rows = pn.parameter_rows(self.owners)
        self.factor_graph = pn.build_session_factor_graph(self.owners)
        self._refresh_records()
        picture = self._picture()
        signature = (self.representation, picture.signature())
        self.stale = False
        if force or signature != self._signature:
            self._signature = signature
            self._place(picture)
        self._update_status()

    def _picture(self) -> _Picture:
        if self.representation == REPRESENTATION_FACTORS:
            return self._factor_picture()
        return self._network_picture()

    def _network_picture(self) -> _Picture:
        """Owners and their parameters; an arrow from each follower to its master."""
        picture = _Picture()
        network = pn.build_parameter_network(self.owners, self.include_fixed, self.connect_owners)
        ids = {}
        for node in network.nodes:
            kind = ev._node_kind(node)
            node_id = node.node_id if node.node_type != "parameter" else _parameter_id(node.obj)
            ids[node.node_idx] = node_id
            picture.marks[node_id] = (kind, node.name, node.obj)
        for edge in network.edges:
            picture.edges.append((ids[edge.source], ids[edge.target], edge.kind))
        return picture

    def _factor_picture(self) -> _Picture:
        """Likelihoods over the variables they read, links resolved.

        A variable read by two or more likelihoods is *shared* and drawn gold:
        it is what couples the datasets. A follower is not a variable -- its
        value is its master's -- so it hangs off its master by a link arrow,
        and a held parameter is evidence on the likelihood that reads it.
        """
        from chisurf.core.fitting import factorgraph as fg

        picture = _Picture()
        graph = self.factor_graph
        readers: dict = {key: len(graph.factors_of(key)) for key in graph.variables}
        roots: dict = {}
        for owner in self.owners:
            for param in owner.parameters:
                root = fg.resolve_root(param)
                roots.setdefault(fg.parameter_key(root), root)
        for number, owner in enumerate(self.owners):
            factor_id = f"owner:{number}"
            picture.marks[factor_id] = (ev.NODE_FACTOR, owner.title, owner)
        for key, root in roots.items():
            if key not in graph.variables:
                continue
            kind = ev.NODE_SHARED if readers.get(key, 0) > 1 else ev.NODE_VARIABLE
            picture.marks[_parameter_id(root)] = (kind, str(getattr(root, "name", key)), root)
        for number, owner in enumerate(self.owners):
            factor_id = f"owner:{number}"
            for key in graph.factors[f"likelihood:{number}"].scope:
                picture.edges.append((factor_id, _parameter_id(roots[key]), "scope"))
            for param in owner.parameters:
                root = fg.resolve_root(param)
                if root is not param and not _flag(root, "fixed"):
                    follower_id = _parameter_id(param)
                    picture.marks[follower_id] = (ev.NODE_PARAM_LINKED, str(param.name), param)
                    picture.edges.append((follower_id, _parameter_id(root), "link"))
                elif _flag(root, "fixed") and self.include_fixed:
                    held_id = _parameter_id(param)
                    picture.marks[held_id] = (ev.NODE_PARAM_FIXED, str(param.name), param)
                    picture.edges.append((held_id, factor_id, "evidence"))
        return picture

    def _place(self, picture: _Picture) -> None:
        """Lay the picture out and hand it to the editor."""
        ids = list(picture.marks)
        positions = _layout(ids, picture.edges, self.graph_layout)
        placed = dict(zip(ids, to_pixels([positions[i] for i in ids], self.graph_scale)))
        document = GraphDocument()
        self._objects = {}
        for node_id, (kind, label, obj) in picture.marks.items():
            self._objects[node_id] = obj
            config = {"kind": kind}
            if isinstance(obj, pn.Owner):
                config.update(owner=obj.title, model=obj.model, data=obj.data_filename)
            else:
                config.update(
                    value=_number(getattr(obj, "value", None)),
                    fixed=_flag(obj, "fixed"),
                    is_linked=_flag(obj, "is_linked"),
                )
            document.add_node(
                GraphNode(
                    node_id=node_id,
                    node_type="owner" if isinstance(obj, pn.Owner) else "parameter",
                    title=str(label),
                    inputs=[PortSpec(name=ev.PORT_IN, is_output=False, port_type="param")],
                    outputs=[PortSpec(name=ev.PORT_OUT, is_output=True, port_type="param")],
                    config=config,
                    pos=placed[node_id],
                )
            )
        for source, target, kind in picture.edges:
            if source in picture.marks and target in picture.marks:
                document.add_edge(GraphEdge(source, 0, target, 0, config={"kind": kind}))
        self.control.set_document(document, fit=True)
        self.selection = [s for s in self.selection if s in self._objects]

    # ------------------------------------------------------------------ #
    # the tables
    # ------------------------------------------------------------------ #

    def _refresh_records(self) -> None:
        rows = self.rows
        position = {id(row.param): i for i, row in enumerate(rows)}
        records = []
        for i, row in enumerate(rows):
            p = row.param
            bounds = getattr(p, "bounds", None) or (None, None)
            try:
                link = getattr(p, "link", None)
            except Exception:  # noqa: BLE001
                link = None
            master = position.get(id(link)) if link is not None else None
            error = _number(getattr(p, "error_estimate", None))
            follower = _flag(p, "is_linked")
            records.append(
                {
                    "uid": _parameter_id(p),
                    "row": i + 1,
                    "owner": row.owner_label,
                    "local": row.local_label,
                    "parameter": str(getattr(p, "name", "")),
                    "value": _number(getattr(p, "value", None)),
                    "fixed": _flag(p, "fixed"),
                    "lo": _number(bounds[0]) if len(bounds) > 0 else None,
                    "hi": _number(bounds[1]) if len(bounds) > 1 else None,
                    "bounded": _flag(p, "bounds_on"),
                    "error": error if error is not None and error == error else None,
                    "link": str(master + 1) if master is not None else "",
                    "follower": follower,
                    "muted": follower or _flag(p, "fixed"),
                    "tip": str(getattr(p, "description", "") or ""),
                }
            )
        self._records = records
        self._records_by_uid = {r["uid"]: (r, rows[i]) for i, r in enumerate(records)}

    def parameter_records(self) -> list:
        """Every parameter's record, for the Parameters table."""
        return self._records

    def selection_records(self) -> list:
        """The selected parameters' records, oldest selection first, with a role."""
        out = []
        parameters = [s for s in self.selection if s in self._records_by_uid]
        for rank, node_id in enumerate(parameters):
            record = dict(self._records_by_uid[node_id][0])
            if record["follower"]:
                role = "follower"
            elif record["fixed"]:
                role = "fixed"
            elif rank == 0 and len(parameters) > 1:
                role = "master"
            else:
                role = "free"
            record["role"] = role
            out.append(record)
        return out

    def selection_hint(self) -> str:
        """What to do in the Selection panel, until two parameters are selected."""
        if len([s for s in self.selection if s in self._records_by_uid]) >= 2:
            return "Link makes the second follow the master."
        return (
            "Click a parameter node to edit it here. Click a second one and press "
            "Link to make it follow the first."
        )

    def value_shading(self) -> typing.Optional[str]:
        """How the Parameters table shades numbers: by column, or not at all."""
        return "column" if self.shade_values else None

    def may_edit_parameter(self, record: dict, key: str) -> bool:
        """A follower's value is its master's; a bound counts only while bounds are on."""
        if key == "value":
            return not record.get("follower")
        if key in ("lo", "hi"):
            return bool(record.get("bounded")) and not record.get("follower")
        return key in ("fixed", "bounded", "link")

    def edit_parameter(self, record: dict, key: str, value: typing.Any) -> None:
        """Route a table edit to the mutator; a refused one is reported, not kept."""
        entry = self._records_by_uid.get(record.get("uid"))
        if entry is None:
            return
        _record, row = entry
        result: dict = {"ok": False}
        try:
            if key == "value":
                result = self.mutator.set_value(row, float(value))
            elif key == "fixed":
                result = self.mutator.set_fixed(row, bool(value))
            elif key == "bounded":
                result = self.mutator.set_bounds_on(row, bool(value))
            elif key in ("lo", "hi"):
                bounds = list(getattr(row.param, "bounds", None) or (0.0, 0.0))
                bounds[0 if key == "lo" else 1] = float(value)
                result = self.mutator.set_bounds(row, tuple(bounds))
            elif key == "link":
                result = self._link_by_row(row, str(value).strip())
        except (TypeError, ValueError) as error:
            result = {"ok": False, "error": str(error)}
        if not result.get("ok", False) and result.get("error"):
            self._warn("Could not change the parameter", str(result["error"]))
        self.rebuild()

    def _link_by_row(self, row, text: str) -> dict:
        if text in ("", "0"):
            return self.mutator.unlink(row)
        if not text.isdigit() or not 1 <= int(text) <= len(self.rows):
            return {"ok": False, "error": f"There is no row {text}."}
        return self._link(row, self.rows[int(text) - 1])

    def select_parameter(self, record: typing.Any) -> None:
        """A row picked in the table selects its node in the graph."""
        if not isinstance(record, dict):
            return
        node_id = record.get("uid")
        document = self.control.document
        node = document.node(node_id) if node_id else None
        if node is None:
            return
        from emtk import nodes

        nodes.clear_node_selection(self.control.editor)
        nodes.select_node(self.control.editor, document.node_number(node_id))
        self.selection = [node_id]

    # ------------------------------------------------------------------ #
    # linking
    # ------------------------------------------------------------------ #

    def _row_of(self, node_id: str):
        entry = self._records_by_uid.get(node_id)
        return entry[1] if entry is not None else None

    def _link(self, follower_row, master_row) -> dict:
        """Make *follower_row*'s parameter follow *master_row*'s, if that is sound."""
        from chisurf.core.parameter import Parameter

        follower, master = follower_row.param, master_row.param
        if follower is master:
            return {"ok": False, "error": "A parameter cannot follow itself."}
        if Parameter.check_recursive_link(master, follower):
            return {
                "ok": False,
                "error": (
                    f"Cannot link '{follower.name}' to '{master.name}': this would make a "
                    "cycle of parameters following each other."
                ),
            }
        return self.mutator.link(follower_row, master_row)

    def _on_graph_select(self, kind: str, payload: typing.Any) -> None:
        from emtk import nodes

        document = self.control.document
        chosen = [
            document.node_for_number(n) for n in nodes.get_selected_nodes(self.control.editor)
        ]
        ids = [n.id for n in chosen if n is not None]
        # Oldest first: the Link button's master is the one selected first.
        self.selection = [s for s in self.selection if s in ids] + [
            i for i in ids if i not in self.selection
        ]

    def _on_graph_link(self, source_id: str, target_id: str) -> None:
        """A link drawn from *source* to *target*: *source* follows *target*."""
        follower, master = self._row_of(source_id), self._row_of(target_id)
        if follower is None or master is None:
            return
        result = self._link(follower, master)
        if not result.get("ok", False):
            self._warn("Cannot link", str(result.get("error", "The link was refused.")))
        self.rebuild()

    def _on_graph_unlink(self, source_id: str, target_id: str) -> None:
        """A link broken in the editor: its follower -- the edge's source -- lets go."""
        row = self._row_of(source_id)
        if row is not None:
            self.mutator.unlink(row)
        self.rebuild()

    # ------------------------------------------------------------------ #
    # actions (the view spec's buttons)
    # ------------------------------------------------------------------ #

    def refresh(self) -> None:
        """Re-read everything and lay it out again."""
        self.rebuild(force=True)

    def relayout(self) -> None:
        """A setting that moves nodes changed."""
        self.rebuild(force=True)

    def auto_refresh_changed(self) -> None:
        """Catch up at once when automatic refreshing comes back on."""
        if self.auto_refresh and self.stale:
            self.rebuild(force=True)
        self._update_status()

    def apply_node_size(self) -> None:
        """Rescale the marks: appearance only, no layout."""
        self.content.radius_scale = float(self.node_size) / 11.0

    def fit_view(self) -> None:
        """Frame the whole graph again."""
        self.control.fit()

    def link_selected(self) -> None:
        """Link the two selected parameters: the second follows the first."""
        rows = [self._row_of(s) for s in self.selection]
        rows = [r for r in rows if r is not None]
        if len(rows) < 2:
            self.status = "Select two parameters first -- the first one is the master."
            return
        result = self._link(rows[1], rows[0])
        if not result.get("ok", False):
            self._warn("Cannot link", str(result.get("error", "The link was refused.")))
        self.rebuild()

    def unlink_selected(self) -> None:
        """Remove the links of the selected parameters, or of every parameter."""
        rows = self.rows if self.unlink_all else [self._row_of(s) for s in self.selection]
        for row in rows:
            if row is not None and _flag(row.param, "is_linked"):
                self.mutator.unlink(row)
        self.rebuild()

    def reload_parameters(self) -> None:
        """Re-read the parameters without laying the graph out again."""
        self.rebuild()

    def export_parameters(self) -> None:
        """Write the Parameters table to a CSV file the host asks for."""
        path = self.ask_save_path("Export parameters", "CSV (*.csv)") if self.ask_save_path else ""
        if not path:
            return
        keys = [
            "row",
            "owner",
            "local",
            "parameter",
            "value",
            "fixed",
            "lo",
            "hi",
            "bounded",
            "error",
            "link",
        ]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self._records)
        self.status = f"Exported {len(self._records)} parameters to {path}"

    def save_network(self) -> None:
        """Write the parameter network to GraphML."""
        from chisurf.core import graph as cg

        path = (
            self.ask_save_path("Save network", "CS-GraphML (*.gml)") if self.ask_save_path else ""
        )
        if not path:
            return
        network = pn.build_parameter_network(self.owners, True, False)
        cg.write_graphml(network.to_graph(), path, encoding="utf-8", prettyprint=True)
        self.status = f"Saved network to {path}"

    def load_network(self, path: typing.Optional[str] = None) -> None:
        """Apply a saved network: parameter values, fixed flags and links."""
        from chisurf.core import graph as cg

        if path is None:
            path = (
                self.ask_open_path("Load network", "CS-GraphML (*.gml)")
                if self.ask_open_path
                else ""
            )
        if not path:
            return
        self.apply_graph(cg.read_graphml(path))

    def apply_graph(self, graph: typing.Any) -> None:
        """Apply a network read back from GraphML to the live parameters.

        Nodes are matched by the parameter's unique identifier, or by owner
        position and name for a file from another session.
        """
        by_uid = {row.param_uid: row for row in self.rows if row.param_uid}
        by_name = {(row.fit_index, str(getattr(row.param, "name", ""))): row for row in self.rows}
        found: dict = {}
        for node in graph.nodes:
            data = graph.nodes[node]
            if data.get("node.type") != "parameter":
                continue
            row = by_uid.get(data.get("param.uid", "")) or by_name.get(
                (data.get("fit.idx"), data.get("node.name"))
            )
            if row is None:
                continue
            found[node] = row
            if data.get("value") is not None:
                self.mutator.set_value(row, float(data["value"]))
            self.mutator.set_fixed(row, bool(data.get("fixed", False)))
        for source, target in graph.edges:
            # Only parameter-to-parameter edges are links; ownership edges end
            # on an owner node, which is never in *found*.
            if source in found and target in found:
                self._link(found[source], found[target])
        self.rebuild(force=True)

    def show_help(self) -> None:
        if self.open_help is not None:
            self.open_help()

    def show_guide(self) -> None:
        if self.open_guide is not None:
            self.open_guide()

    # ------------------------------------------------------------------ #
    # outside changes
    # ------------------------------------------------------------------ #

    def fits_changed(self) -> None:
        """A fit or a parameter changed somewhere: catch up, or say the picture is old."""
        if not self.auto_refresh:
            self.stale = True
            self._update_status()
            return
        self.rebuild(force=False)

    # ------------------------------------------------------------------ #

    def _warn(self, title: str, message: str) -> None:
        self.status = message
        if self.warn is not None:
            self.warn(title, message)

    def _update_status(self) -> None:
        if self.stale:
            self.status = "The fits changed -- press Refresh to redraw the network."
            return
        if not self.owners:
            self.status = "No fits and no registered parameter groups -- nothing to draw."
            return
        if self.representation == REPRESENTATION_FACTORS:
            graph = self.factor_graph
            shared = sorted(
                {graph.variables[k].name for k in graph.variables if len(graph.factors_of(k)) > 1}
            )
            blocks = len(graph.connected_components()) if graph.variables else 0
            text = (
                f"{len(graph.factors)} likelihoods over {len(graph.variables)} variables · "
                f"{len(shared)} shared"
            )
            if shared:
                text += f" ({', '.join(shared[:4])}{'…' if len(shared) > 4 else ''})"
            text += f" · {blocks} independent block{'' if blocks == 1 else 's'}"
            self.status = text
            return
        linked = sum(1 for row in self.rows if _flag(row.param, "is_linked"))
        self.status = (
            f"{len(self.owners)} owners · {len(self.rows)} parameters · {linked} linked. "
            "Drag a parameter onto the one it should follow."
        )


def _session_fits() -> list:
    from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

    fc = get_fitting_client()
    return fc.get_fit_objects() if fc is not None else []


def _registered_groups() -> list:
    from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups

    return iter_registered_parameter_groups()
