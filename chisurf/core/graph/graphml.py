"""GraphML reading and writing.

`GraphML <http://graphml.graphdrawing.org/>`_ is the interchange format the
graph tools around this project speak: an XML document declaring typed
attribute keys and then the nodes and edges that carry them. A file written here
opens in yEd, Gephi or Cytoscape unchanged, and a file written by those opens
here.

Notes
-----
Node identifiers are XML text, so they come back as strings unless ``node_type``
says otherwise -- a graph whose nodes were integers reads back with string keys,
which is the format's behaviour and not a loss of information (the original
value is normally also stored as an attribute).
"""

from __future__ import annotations

import typing
import xml.etree.ElementTree as ET

from .graph import DiGraph, Graph, GraphError

__all__ = ["read_graphml", "write_graphml"]

#: The GraphML XML namespace.
NS = "http://graphml.graphdrawing.org/xmlns"

#: Python type -> GraphML attribute type. Order matters: ``bool`` is a subclass
#: of ``int`` and must be recognised first.
_TYPES: tuple[tuple[type, str], ...] = (
    (bool, "boolean"),
    (int, "long"),
    (float, "double"),
    (str, "string"),
)

_PARSERS: dict[str, typing.Callable[[str], typing.Any]] = {
    "boolean": lambda s: s.strip().lower() in ("true", "1"),
    "int": int,
    "long": int,
    "float": float,
    "double": float,
    "string": str,
}


def _graphml_type(value) -> str:
    """Return the GraphML type name for a Python value."""
    for python_type, name in _TYPES:
        if isinstance(value, python_type):
            return name
    return "string"


def _merge_type(current: str | None, new: str) -> str:
    """Return the type that can hold both ``current`` and ``new`` values."""
    if current is None or current == new:
        return new
    numeric = {"long", "double"}
    if current in numeric and new in numeric:
        return "double"
    return "string"


def _format(value, type_name: str) -> str:
    """Return the XML text for ``value`` declared as ``type_name``."""
    if type_name == "boolean":
        return "true" if value else "false"
    return str(value)


def _collect_keys(
    items: typing.Iterable[dict],
) -> dict[str, str]:
    """Return ``attribute name -> GraphML type`` over a set of attribute dicts."""
    out: dict[str, str] = {}
    for attrs in items:
        for name, value in attrs.items():
            if value is None:
                continue
            out[name] = _merge_type(out.get(name), _graphml_type(value))
    return out


def write_graphml(
    graph: Graph,
    path,
    encoding: str = "utf-8",
    prettyprint: bool = True,
) -> None:
    """Write ``graph`` to ``path`` as GraphML.

    Attribute types are inferred from the values actually present: a key holding
    only integers is declared ``long``, one mixing integers and floats
    ``double``, anything else ``string``. Attributes whose value is ``None`` are
    omitted, since GraphML has no null.

    Parameters
    ----------
    graph : Graph
        Graph to write; directed graphs are marked ``edgedefault="directed"``.
    path : str or path-like or file object
        Destination.
    encoding : str, optional
        XML encoding declared and used.
    prettyprint : bool, optional
        Indent the document so a human can read it.
    """
    node_keys = _collect_keys(attrs for _, attrs in graph.nodes.items())
    edge_keys = _collect_keys(graph.get_edge_data(u, v, {}) for u, v in graph.edges)

    root = ET.Element("graphml", {"xmlns": NS})
    key_ids: dict[tuple[str, str], str] = {}
    for scope, keys in (("node", node_keys), ("edge", edge_keys)):
        for name in keys:
            key_id = f"d{len(key_ids)}"
            key_ids[(scope, name)] = key_id
            ET.SubElement(
                root,
                "key",
                {
                    "id": key_id,
                    "for": scope,
                    "attr.name": name,
                    "attr.type": keys[name],
                },
            )

    graph_element = ET.SubElement(
        root,
        "graph",
        {
            "edgedefault": "directed" if graph.is_directed() else "undirected",
        },
    )
    for name, value in graph.graph.items():
        if value is not None:
            ET.SubElement(
                graph_element,
                "data",
                {
                    "key": name,
                },
            ).text = str(value)

    for node, attrs in graph.nodes.items():
        element = ET.SubElement(graph_element, "node", {"id": str(node)})
        for name, value in attrs.items():
            if value is None:
                continue
            data = ET.SubElement(element, "data", {"key": key_ids[("node", name)]})
            data.text = _format(value, node_keys[name])

    for index, (u, v) in enumerate(graph.edges):
        element = ET.SubElement(
            graph_element,
            "edge",
            {
                "id": f"e{index}",
                "source": str(u),
                "target": str(v),
            },
        )
        for name, value in graph.get_edge_data(u, v, {}).items():
            if value is None:
                continue
            data = ET.SubElement(element, "data", {"key": key_ids[("edge", name)]})
            data.text = _format(value, edge_keys[name])

    tree = ET.ElementTree(root)
    if prettyprint:
        ET.indent(tree, space="  ")
    tree.write(path, encoding=encoding, xml_declaration=True)


def _strip(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def read_graphml(path, node_type: typing.Callable = str) -> Graph:
    """Read a GraphML document and return the graph it describes.

    Parameters
    ----------
    path : str or path-like or file object
        Source document.
    node_type : callable, optional
        Applied to every node identifier; ``str`` by default, ``int`` for a file
        known to hold integer identifiers.

    Returns
    -------
    Graph
        A :class:`~chisurf.core.graph.graph.DiGraph` when the document declares
        ``edgedefault="directed"``, otherwise an undirected
        :class:`~chisurf.core.graph.graph.Graph`.

    Raises
    ------
    GraphError
        If the document holds no ``<graph>`` element.
    """
    tree = ET.parse(path)
    root = tree.getroot()

    #: key id -> (attribute name, GraphML type, default value, scope)
    keys: dict[str, tuple[str, str, typing.Any, str]] = {}
    for element in root:
        if _strip(element.tag) != "key":
            continue
        key_id = element.get("id")
        name = element.get("attr.name", key_id)
        type_name = element.get("attr.type", "string")
        default = None
        for child in element:
            if _strip(child.tag) == "default":
                default = _convert(child.text, type_name)
        keys[key_id] = (name, type_name, default, element.get("for", "all"))

    graph_element = None
    for element in root:
        if _strip(element.tag) == "graph":
            graph_element = element
            break
    if graph_element is None:
        raise GraphError("no <graph> element in the GraphML document")

    directed = graph_element.get("edgedefault", "undirected") == "directed"
    graph = DiGraph() if directed else Graph()

    def _data(element, scope: str) -> dict:
        """Return the ``<data>`` children of ``element`` as an attribute dict.

        Declared defaults for ``scope`` (``node`` or ``edge``) fill in wherever
        the element itself carries no value.
        """
        out = {
            name: default
            for (name, _t, default, key_scope) in keys.values()
            if default is not None and key_scope in (scope, "all")
        }
        for child in element:
            if _strip(child.tag) != "data":
                continue
            key_id = child.get("key")
            name, type_name = keys.get(key_id, (key_id, "string", None, "all"))[:2]
            out[name] = _convert(child.text, type_name)
        return out

    for element in graph_element:
        tag = _strip(element.tag)
        if tag == "node":
            graph.add_node(node_type(element.get("id")), **_data(element, "node"))
        elif tag == "edge":
            graph.add_edge(
                node_type(element.get("source")),
                node_type(element.get("target")),
                **_data(element, "edge"),
            )
    return graph


def _convert(text: str | None, type_name: str):
    """Return ``text`` parsed as ``type_name``, or as a string if it will not parse."""
    if text is None:
        return None
    parser = _PARSERS.get(type_name, str)
    try:
        return parser(text)
    except (TypeError, ValueError):
        return text
