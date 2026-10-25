"""The live IMP.bff graph session as portable project state.

Owner decision 2026-10-24: a ``.cs.pto`` project
keeps the live node graph again.  Nodes and free ports that no fit owns are
serialized by IMP.bff's own ``GraphSession`` codec and travel as one typed
container entry (``session.jsonl``); loading a project installs the stored
graph as the live session, replacing what is there (restore replaces, it
never merges -- the same contract as ``GraphSession.clear``).

IMP.bff stays optional: without it a project simply carries no graph entry
and a load leaves the session untouched, exactly as before.
"""

from __future__ import annotations

import pathlib
import tempfile


def capture_graph_session() -> bytes | None:
    """Serialize the live bff graph session, or ``None`` when there is none.

    ``None`` means "nothing to persist": no IMP.bff installation, or a live
    session without nodes.  A session that *has* nodes but fails to serialize
    raises -- a save must not silently drop the graph it was asked to keep.
    """
    try:
        import IMP.bff as bff
    except ImportError:
        return None
    session = bff.get_session()
    if session.get_number_of_nodes() == 0:
        return None
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "graph-session.json"
        session.save(str(path))
        return path.read_bytes()


def restore_graph_session(data: bytes) -> bool:
    """Install *data* as the live bff graph session, replacing the current one.

    Returns ``False`` when IMP.bff is not installed (the caller keeps the
    bytes; nothing else changes).
    """
    loaded = load_graph_session(data)
    if loaded is None:
        return False
    import IMP.bff as bff

    live = bff.get_session()
    live.clear()
    for name in list(loaded.nodes):  # the map yields node names
        live.add_node(name, loaded.get_node(name))
    return True


def load_graph_session(data: bytes):
    """Deserialize graph-session *data* without touching the live session."""
    try:
        import IMP.bff as bff
    except ImportError:
        return None
    with tempfile.TemporaryDirectory() as directory:
        path = pathlib.Path(directory) / "graph-session.json"
        path.write_bytes(data)
        return bff.GraphSession.load(str(path))
