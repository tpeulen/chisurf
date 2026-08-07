"""Read a ``.pto`` and say what is in it — Qt-free, so the CLI and the GUI share it.

A photon container answers three different questions, and they are usually asked
in this order: *what is in this file*, *how did that come to be*, and *what are
the numbers*. The writer side ([the PTO.MFDB seam](/specs/pto-mfdb.md)) already
records all three; nothing until now read them back for a person.

The provenance answer is a **graph**, not a list. A burst table has one parent
and a lifetime fit has two, so an indented text tree either duplicates a node or
drops an edge — and the duplicated node is the one that matters, because a
result reached by two paths is exactly what "the background correction was used
here as well" looks like. :func:`provenance_graph` therefore emits the node-editor
graph format, and the viewer draws the DAG.

Nothing here opens a payload it was not asked for: a container is the size of the
raw data, and listing it must not cost a read of it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from chisurf.core.fio.pto import Measurement, is_measurement

logger = logging.getLogger(__name__)

__all__ = [
    "KIND_COLORS",
    "PtoInspection",
    "artifact_rows",
    "provenance_graph",
    "short_uid",
]

#: Header colour per artifact kind, so a glance at the graph separates the
#: photons from the tables from the curves without reading a single label.
#: Anything not named here falls back to the node editor's own theme colour.
KIND_COLORS: dict[str, tuple[int, int, int]] = {
    "tttr_photon_stream": (150, 90, 40),
    "raw_data": (150, 90, 40),
    "raw_measurement": (150, 90, 40),
    "sample_metadata": (95, 95, 110),
    "readme": (95, 95, 110),
    "burst_table": (60, 120, 170),
    "burst_selection": (60, 140, 140),
    "analysis_result": (95, 120, 60),
    "fit_result": (95, 120, 60),
    "background_data": (130, 105, 55),
    "tcspc_decay": (120, 70, 130),
    "fcs_correlation": (120, 70, 130),
    "anisotropy_curve": (120, 70, 130),
    "irf_curve": (120, 70, 130),
    "model_curve": (150, 80, 90),
    "residual": (150, 80, 90),
    "image_data": (70, 110, 150),
    "visualization": (70, 110, 150),
}

#: Kinds whose payload is a columnar store and can therefore be shown as a table.
_TABULAR_FORMATS = ("dstore",)


def short_uid(uid: int) -> str:
    """Return a UID abbreviated for display.

    A PTO uid is a 53-bit random integer: unique, and unreadable. Sixteen digits
    in a table column push every other column off the panel, so lists show the
    first six and the full value stays in the tooltip and in the detail pane.

    Parameters
    ----------
    uid : int
        The object UID.

    Returns
    -------
    str
        The first six digits followed by ``…``, or the whole number when it is
        already short enough to read.
    """
    text = str(int(uid))
    return text if len(text) <= 7 else f"{text[:6]}…"


def _human_bytes(n: int) -> str:
    """Return a byte count as a short human-readable string."""
    value = float(n)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


@dataclass
class ArtifactInfo:
    """One object in a container, with everything the container records about it.

    Attributes
    ----------
    uid : int
        Object UID.
    name, kind : str
        The label it was written under, and its ``_mmfdb_artifact.artifact_kind``.
    data_format : str
        ``dstore`` for a columnar table, ``cif`` for metadata, otherwise the
        payload's own format.
    grain : str
        What one row *is* — empty for a payload that has no rows.
    operation : str
        The ``_mmfdb_operation.operation_type`` that produced it, empty for
        something carried rather than computed (the instrument file, the README).
    rows, size_bytes, capacity_bytes : int
        Row count, payload size and the space reserved for it.
    settings : dict
        The parsed analysis settings; ``{}`` when none were recorded.
    settings_hash, software, dictionary : str
        The identity of the run, what wrote it, and the dictionary revision its
        terms came from.
    relationship : str
        How it relates to its parents (``derived_from`` unless stated otherwise).
    parents : list of int
        Parent UIDs — more than one is normal.
    source_row_column, target_row_column : str
        The declared join keys, when the grains differ.
    checksum : str
        The recorded SHA-256, or empty.
    """

    uid: int
    name: str
    kind: str
    data_format: str = ""
    grain: str = ""
    operation: str = ""
    rows: int = 0
    size_bytes: int = 0
    capacity_bytes: int = 0
    settings: dict = field(default_factory=dict)
    settings_hash: str = ""
    software: str = ""
    dictionary: str = ""
    relationship: str = ""
    parents: list = field(default_factory=list)
    source_row_column: str = ""
    target_row_column: str = ""
    checksum: str = ""

    @property
    def is_tabular(self) -> bool:
        """Whether the payload can be read back as a table."""
        return self.data_format in _TABULAR_FORMATS

    def as_row(self) -> dict:
        """Return the record a list view shows, with display-ready fields."""
        return {
            "uid": self.uid,
            "uid_short": short_uid(self.uid),
            "name": self.name,
            "kind": self.kind,
            "grain": self.grain,
            "operation": self.operation,
            "rows": self.rows if self.is_tabular else 0,
            "size": _human_bytes(self.size_bytes),
            "size_bytes": self.size_bytes,
            "parents": len(self.parents),
        }


class PtoInspection:
    """An open, read-only view of one container.

    Kept open rather than read whole: the artifact list and the provenance graph
    are cheap tag reads, while a table is megabytes and is read only when its row
    is actually looked at.

    Parameters
    ----------
    path : str or pathlib.Path
        The ``.pto`` to inspect.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If *path* is not a photon container.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(str(self.path))
        if not is_measurement(self.path):
            raise ValueError(f"{self.path.name} is not a PTO.MFDB container")
        self._m: Measurement | None = Measurement.open(self.path, writable=False)
        self._infos: list[ArtifactInfo] | None = None

    # -- lifetime -------------------------------------------------------------

    def close(self) -> None:
        """Close the container. Idempotent."""
        if self._m is not None:
            try:
                self._m.close()
            except Exception:
                logger.debug("closing %s failed", self.path, exc_info=True)
            self._m = None

    def __enter__(self) -> "PtoInspection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    @property
    def measurement(self) -> Measurement:
        """The open :class:`~chisurf.core.fio.pto.Measurement`."""
        if self._m is None:
            raise RuntimeError("the container is closed")
        return self._m

    # -- what is in it --------------------------------------------------------

    @property
    def file_size(self) -> int:
        """Size of the container on disk, in bytes."""
        return self.path.stat().st_size

    def container_tags(self) -> dict:
        """Return the file-level tags — profile, format and dictionary versions.

        Returns
        -------
        dict
            Keys ``profile``, ``profile_version``, ``format``, ``format_version``
            and ``dictionary_version``; values are empty when the file predates
            the tag.
        """
        m = self.measurement
        return {
            "profile": m.tag(0, "_mmfdb_container.profile"),
            "profile_version": m.tag(0, "_mmfdb_container.profile_version"),
            "format": m.tag(0, "_mmfdb_container.format"),
            "format_version": m.tag(0, "_mmfdb_container.format_version"),
            "dictionary_version": m.tag(0, "_mmfdb_container.dictionary_version"),
        }

    def infos(self, *, refresh: bool = False) -> list[ArtifactInfo]:
        """Return one :class:`ArtifactInfo` per object, in write order.

        Parameters
        ----------
        refresh : bool, optional
            Re-read instead of returning the cached list.

        Returns
        -------
        list of ArtifactInfo
        """
        if self._infos is not None and not refresh:
            return self._infos
        m = self.measurement
        out: list[ArtifactInfo] = []
        for obj in m.artifacts():
            prov = m.provenance(obj.uid)
            out.append(
                ArtifactInfo(
                    uid=obj.uid,
                    name=obj.name or str(obj.uid),
                    kind=obj.kind,
                    data_format=m.tag(obj.uid, "_mmfdb_artifact.data_format")
                    or getattr(obj, "encoding", ""),
                    grain=prov["grain"],
                    operation=prov["operation"],
                    rows=int(getattr(obj, "rows", 0) or 0),
                    size_bytes=int(getattr(obj, "size", 0) or 0),
                    capacity_bytes=int(getattr(obj, "capacity", 0) or 0),
                    settings=prov["settings"],
                    settings_hash=prov["settings_hash"],
                    software=prov["software"],
                    dictionary=prov["dictionary"],
                    relationship=prov["relationship"],
                    parents=list(prov["parents"]),
                    source_row_column=prov["source_row_column"],
                    target_row_column=prov["target_row_column"],
                    checksum=m.tag(obj.uid, "_mmfdb_artifact.checksum"),
                )
            )
        self._infos = out
        return out

    def info(self, uid: int) -> ArtifactInfo | None:
        """Return the :class:`ArtifactInfo` for *uid*, or ``None``."""
        for item in self.infos():
            if item.uid == int(uid):
                return item
        return None

    def rows(self) -> list[dict]:
        """Return the artifact list as display records."""
        return [item.as_row() for item in self.infos()]

    # -- payloads -------------------------------------------------------------

    def store(self, uid: int) -> Any:
        """Read one tabular payload back as a store.

        Parameters
        ----------
        uid : int

        Returns
        -------
        tttrlib.DataStore or None
            ``None`` when the object is not a table.
        """
        item = self.info(uid)
        if item is None or not item.is_tabular:
            return None
        return self.measurement.get_store(int(uid))

    def curve(self, uid: int) -> dict | None:
        """Read one curve back, with its axis units.

        Returns
        -------
        dict or None
            The :meth:`~chisurf.core.fio.pto.Measurement.get_curve` mapping, or
            ``None`` when the object is not a curve.
        """
        item = self.info(uid)
        if item is None or item.grain != "curve_point":
            return None
        try:
            return self.measurement.get_curve(int(uid))
        except Exception:
            logger.debug("reading curve %s failed", uid, exc_info=True)
            return None

    def text(self, uid: int) -> str:
        """Read a text payload (README, mmCIF metadata) back as a string.

        Through :meth:`~chisurf.core.fio.pto.Measurement.get_blob`, which
        verifies the recorded checksum on the way out — a reader that shows a
        damaged payload as if it were intact is worse than one that shows
        nothing.
        """
        try:
            return self.measurement.get_blob(int(uid)).decode("utf-8", "replace")
        except Exception:
            logger.debug("reading text %s failed", uid, exc_info=True)
            return ""

    def verify(self) -> list[str]:
        """Check every recorded checksum. Empty result means the file is intact."""
        return self.measurement.verify()

    def lineage(self, uid: int) -> list[dict]:
        """Return the path from *uid* back to the primary data."""
        return self.measurement.lineage(int(uid))

    def describe_lineage(self, uid: int) -> str:
        """Return :meth:`lineage` as readable text."""
        return self.measurement.describe_lineage(int(uid))

    def graph(self, *, focus: int | None = None) -> dict:
        """Return the provenance DAG in the node-editor graph format."""
        return provenance_graph(self.infos(), focus=focus)


# -- free functions (testable without a file) ---------------------------------


def artifact_rows(infos: Iterable[ArtifactInfo]) -> list[dict]:
    """Return display records for *infos*."""
    return [item.as_row() for item in infos]


def _depths(infos: list[ArtifactInfo]) -> dict[int, int]:
    """Return each object's distance from the primary data.

    The layer a node is drawn in. Computed as the *longest* path from a root, not
    the shortest: a lifetime fit derived from both the bursts and the background
    must be drawn to the right of both, and taking the shortest path would put it
    beside the bursts with an edge running backwards.
    """
    known = {item.uid for item in infos}
    parents = {item.uid: [p for p in item.parents if p in known] for item in infos}
    depth: dict[int, int] = {}

    def resolve(uid: int, seen: frozenset) -> int:
        if uid in depth:
            return depth[uid]
        if uid in seen:  # a cycle cannot happen in a written container, but a
            return 0  # damaged one must not hang the viewer
        ps = parents.get(uid, ())
        value = 0 if not ps else 1 + max(resolve(p, seen | {uid}) for p in ps)
        depth[uid] = value
        return value

    for item in infos:
        resolve(item.uid, frozenset())
    return depth


def provenance_graph(
    infos: Iterable[ArtifactInfo],
    *,
    focus: int | None = None,
    x_spacing: float = 180.0,
    y_spacing: float = 90.0,
) -> dict:
    """Build the node-editor graph for a container's provenance.

    One node per object, one edge per recorded parent. Nodes are laid out in
    columns by their distance from the primary data, so the instrument file is on
    the left and the last thing computed is on the right — the direction the
    reader is already asking the question in.

    Parameters
    ----------
    infos : iterable of ArtifactInfo
        The container's objects.
    focus : int, optional
        A UID to mark as selected in the returned ``meta``, so a viewer can
        highlight the artifact the user came from.
    x_spacing, y_spacing : float, optional
        Column and row pitch in scene units.

    Returns
    -------
    dict
        A graph in [the node-editor JSON schema](node_editor/json_schema.md):
        ``nodes``, ``edges``, ``version`` and a ``meta`` carrying ``focus``.
    """
    items = list(infos)
    depth = _depths(items)
    known = {item.uid for item in items}

    per_layer: dict[int, int] = {}
    nodes = []
    for item in items:
        layer = depth.get(item.uid, 0)
        row = per_layer.get(layer, 0)
        per_layer[layer] = row + 1
        subtitle = item.operation or item.kind
        nodes.append(
            {
                "id": str(item.uid),
                "type": item.kind or "artifact",
                "title": item.name,
                # A parentless object is a root and genuinely has no input; the
                # port is omitted rather than drawn empty, which is what makes
                # the instrument file read as the start of the chain.
                "inputs": ["from"] if any(p in known for p in item.parents) else [],
                "outputs": ["to"],
                "config": {
                    "uid": item.uid,
                    "kind": item.kind,
                    "operation": item.operation,
                    "grain": item.grain,
                    "rows": item.rows,
                    "subtitle": subtitle,
                    "title_color": list(KIND_COLORS.get(item.kind, (70, 130, 175))),
                    # Circles, not boxes. These nodes hold nothing -- they name a
                    # thing and its connections -- and a page of titled boxes
                    # reads as a form where a page of circles reads as a network,
                    # which is what this is. It is also what makes the whole
                    # chain fit without scrolling: a box is 210x80, a circle 44.
                    "shape": "circle",
                    "diameter": 42,
                },
                "pos": [layer * x_spacing, row * y_spacing],
                "collapsed": False,
            }
        )

    edges = []
    for item in items:
        for parent in item.parents:
            if parent not in known:
                continue
            edges.append(
                {
                    "source": str(parent),
                    "source_port": 0,
                    "target": str(item.uid),
                    "target_port": 0,
                    "config": {"color": [140, 150, 160]},
                }
            )

    return {
        "version": 1,
        "meta": {"purpose": "pto_provenance", "focus": str(focus) if focus else ""},
        "nodes": nodes,
        "edges": edges,
    }


def settings_text(settings: dict) -> str:
    """Return analysis settings as sorted, readable lines.

    Parameters
    ----------
    settings : dict

    Returns
    -------
    str
        ``key = value`` per line, empty when nothing was recorded.
    """
    if not settings:
        return ""
    lines = []
    for key in sorted(settings):
        value = settings[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True)
        lines.append(f"{key} = {value}")
    return "\n".join(lines)
