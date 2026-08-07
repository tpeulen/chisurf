"""Qt-free view model for the ``.pto`` inspector.

Holds the open container, the current selection, and the sources the view spec
names — the artifact list, the provenance graph, the selected payload as a table
or a curve, and the prose that says how it was made. No Qt import, so the whole
thing is testable headlessly and the same object drives the CLI's output.

The one piece of behaviour worth naming is the **jump to the tool**. A container
records the *operation* that produced a result, never the program that ran it;
:mod:`chisurf.core.plugin.operations` inverts that from the plugin manifests, and
this model turns the answer into something the GUI can open. Reading a result and
continuing the analysis are different acts, and the second one was missing.
"""

from __future__ import annotations

import html
import logging
import pathlib
from collections.abc import Callable
from typing import Any

from chisurf.core.plugin.operations import tools_for_operation

from ..core import PtoInspection, settings_text, short_uid

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "pto.view.json"


class PtoInspectorViewModel:
    """One open container, one selected artifact, and the views onto both."""

    def __init__(self) -> None:
        """Start with nothing open."""
        self._view_json = _VIEW_JSON
        self._observers: list[Callable[[str], None]] = []

        self.filename: str = ""
        self._inspection: PtoInspection | None = None
        self._selected: int = 0
        self._status: str = "Open a .pto container."
        self._verify: list[str] | None = None

    # -- observer hook --------------------------------------------------------

    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("pto inspector observer failed", exc_info=True)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(self._view_json)

    # -- opening --------------------------------------------------------------

    @property
    def status(self) -> str:
        """The one-line status shown in the host's status bar."""
        return self._status

    @property
    def inspection(self) -> PtoInspection | None:
        """The open container, or ``None``."""
        return self._inspection

    def set_filename(self, path: str) -> None:
        """Open *path* as a container, replacing whatever was open.

        Parameters
        ----------
        path : str
            A ``.pto`` file. An empty string closes the current one.
        """
        self.close()
        self.filename = str(path or "")
        if not self.filename:
            self._status = "Open a .pto container."
            self.notify("opened")
            return
        try:
            self._inspection = PtoInspection(self.filename)
        except Exception as exc:
            self._status = f"Cannot open {pathlib.Path(self.filename).name}: {exc}"
            logger.debug("opening %s failed", self.filename, exc_info=True)
            self.notify("opened")
            return
        infos = self._inspection.infos()
        # Select the last artifact rather than the first: the first is the README
        # and the last is what was computed most recently, which is what somebody
        # opening the file is nearly always looking for.
        self._selected = infos[-1].uid if infos else 0
        self._status = f"{pathlib.Path(self.filename).name} — {len(infos)} objects"
        self.notify("opened")

    def close(self) -> None:
        """Close the open container, if any."""
        if self._inspection is not None:
            self._inspection.close()
        self._inspection = None
        self._selected = 0
        self._verify = None

    def reload(self) -> None:
        """Re-open the current file, picking up anything written since."""
        if self.filename:
            self.set_filename(self.filename)

    # -- selection ------------------------------------------------------------

    @property
    def selected_uid(self) -> int:
        """UID of the artifact the detail views describe."""
        return self._selected

    def select_uid(self, uid: int) -> None:
        """Select the artifact *uid* and refresh the detail views."""
        if not uid or int(uid) == self._selected:
            return
        self._selected = int(uid)
        self.notify("selected")

    def select_row(self, row: Any) -> None:
        """Select from an artifact-list row (the table section's callback)."""
        if isinstance(row, dict) and row.get("uid"):
            self.select_uid(int(row["uid"]))

    def open_row(self, row: Any) -> None:
        """Select from a list row and ask the host to open its tool."""
        self.select_row(row)
        self.notify("open_tool")

    def select_node(self, node: Any) -> None:
        """Select from a provenance-graph node (the graph section's callback)."""
        if not isinstance(node, dict):
            return
        uid = (node.get("config") or {}).get("uid") or node.get("id")
        if uid:
            try:
                self.select_uid(int(uid))
            except (TypeError, ValueError):
                logger.debug("graph node has no usable uid: %r", node)

    @property
    def selected(self):
        """The selected :class:`~..core.ArtifactInfo`, or ``None``."""
        if self._inspection is None:
            return None
        return self._inspection.info(self._selected)

    # -- sources named by the view spec --------------------------------------

    def artifact_rows(self) -> list[dict]:
        """Rows for the artifact list."""
        return self._inspection.rows() if self._inspection else []

    def provenance_graph(self) -> dict:
        """The container's provenance DAG, in the node-editor graph format."""
        if self._inspection is None:
            return {}
        return self._inspection.graph(focus=self._selected or None)

    def current_store(self):
        """The selected artifact's payload as a store, or ``None``."""
        if self._inspection is None or not self._selected:
            return None
        try:
            return self._inspection.store(self._selected)
        except Exception:
            logger.debug("reading store %s failed", self._selected, exc_info=True)
            return None

    def curve_series(self) -> list[dict]:
        """The selected artifact as plot series, when it is a curve."""
        if self._inspection is None or not self._selected:
            return []
        curve = self._inspection.curve(self._selected)
        if not curve:
            return []
        item = self.selected
        name = item.name if item else "curve"
        series = [{"x": curve["x"], "y": curve["y"], "name": name}]
        return series

    def curve_axes(self) -> dict:
        """Axis labels and scales for the selected curve (the plot's ``axes_source``).

        The units come from the stored columns rather than from the artifact
        kind: an FCS lag axis is milliseconds and a decay axis is nanoseconds,
        and an axis labelled only "x" is how the two get confused. The lag axis
        also spans six decades, so a correlation gets a log x axis and a decay
        does not — read from the data, because the same plot shows both.
        """
        if self._inspection is None or not self._selected:
            return {"x_label": "no container open", "y_label": "", "log_x": False}
        curve = self._inspection.curve(self._selected)
        if not curve:
            # An empty plot with default 0…1 ticks looks like a curve of zeros.
            # Say why it is empty instead.
            item = self.selected
            what = f"“{item.name}” is not a curve" if item else "nothing selected"
            return {"x_label": what, "y_label": "", "log_x": False, "log_y": False}
        from chisurf.core.units import symbol

        item = self.selected
        x_unit = symbol(str(curve.get("x_units", "") or ""))
        y_unit = symbol(str(curve.get("y_units", "") or ""))
        return {
            "x_label": f"x [{x_unit}]" if x_unit else "x",
            "y_label": f"y [{y_unit}]" if y_unit else "y",
            "log_x": bool(item and item.kind == "fcs_correlation"),
            "log_y": False,
        }

    # -- prose ----------------------------------------------------------------

    def summary_html(self) -> str:
        """A short description of the open container."""
        if self._inspection is None:
            return (
                "<p><i>No container open.</i> Drop a <code>.pto</code> here, or use "
                "📂 Browse. A container holds one measurement: the instrument file "
                "verbatim, and every result computed from it beside it.</p>"
            )
        insp = self._inspection
        tags = insp.container_tags()
        infos = insp.infos()
        kinds: dict[str, int] = {}
        for item in infos:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        payload = sum(item.size_bytes for item in infos)
        rows = [
            ("File", html.escape(pathlib.Path(insp.path).name)),
            ("Size", f"{insp.file_size / 1e6:,.1f} MB ({payload / 1e6:,.1f} MB payload)"),
            ("Profile", f"{tags['profile']} {tags['profile_version']}"),
            ("Container", f"{tags['format']} {tags['format_version']}"),
            ("Dictionary", tags["dictionary_version"] or "—"),
            ("Objects", str(len(infos))),
        ]
        if self._verify is not None:
            rows.append(
                (
                    "Integrity",
                    "every checksum matches"
                    if not self._verify
                    else f"<b style='color:#c33'>{len(self._verify)} mismatch(es)</b>",
                )
            )
        body = "".join(
            f"<tr><td style='padding-right:10px;color:#888'>{k}</td><td>{v}</td></tr>"
            for k, v in rows
        )
        kind_list = ", ".join(f"{n}× {html.escape(k)}" for k, n in sorted(kinds.items()))
        return f"<table>{body}</table><p style='color:#888'>{kind_list}</p>"

    def detail_html(self) -> str:
        """Everything recorded about the selected artifact."""
        item = self.selected
        if item is None:
            return "<p><i>Select an artifact.</i></p>"
        rows = [
            ("Name", html.escape(item.name)),
            ("UID", str(item.uid)),
            ("Kind", html.escape(item.kind)),
            ("Operation", html.escape(item.operation) or "— (carried, not computed)"),
            ("Grain", f"one row per {html.escape(item.grain)}" if item.grain else "—"),
            ("Rows", f"{item.rows:,}" if item.is_tabular else "—"),
            ("Size", f"{item.size_bytes:,} B (reserved {item.capacity_bytes:,} B)"),
            ("Software", html.escape(item.software) or "—"),
            ("Dictionary", html.escape(item.dictionary) or "—"),
            ("Run id", f"<code>{html.escape(item.settings_hash[:16])}…</code>"
             if item.settings_hash else "—"),
            ("Checksum", f"<code>{html.escape(item.checksum[:16])}…</code>"
             if item.checksum else "—"),
        ]
        if item.parents:
            names = []
            for parent in item.parents:
                info = self._inspection.info(parent) if self._inspection else None
                names.append(html.escape(info.name) if info else short_uid(parent))
            joined = ""
            if item.source_row_column:
                joined = (
                    f" on <code>{html.escape(item.source_row_column)}</code> = "
                    f"<code>{html.escape(item.target_row_column or item.source_row_column)}</code>"
                )
            rows.append(
                (item.relationship or "derived from", ", ".join(names) + joined)
            )
        body = "".join(
            f"<tr><td style='padding-right:10px;color:#888;vertical-align:top'>{k}</td>"
            f"<td>{v}</td></tr>"
            for k, v in rows
        )
        out = [f"<table>{body}</table>"]

        text = settings_text(item.settings)
        if text:
            out.append(
                "<p style='color:#888;margin-bottom:2px'>Settings — the identity of "
                "this run; changing one produces a new artifact rather than "
                "overwriting this one.</p>"
                f"<pre style='margin-top:0'>{html.escape(text)}</pre>"
            )
        else:
            out.append("<p style='color:#888'>No settings recorded.</p>")

        tools = tools_for_operation(item.operation)
        if tools:
            names = ", ".join(html.escape(m.display_name or m.id) for m in tools)
            out.append(
                f"<p style='color:#888'>Computed by a <b>{names}</b> step — "
                "▶ Open tool re-opens it.</p>"
            )
        elif item.operation:
            out.append(
                "<p style='color:#888'>No installed tool claims this step, so it was "
                "probably computed elsewhere. The settings above are still the whole "
                "recipe.</p>"
            )
        return "".join(out)

    def lineage_text(self) -> str:
        """The selected artifact's path back to the primary data, as text."""
        if self._inspection is None or not self._selected:
            return ""
        try:
            return self._inspection.describe_lineage(self._selected)
        except Exception:
            logger.debug("lineage of %s failed", self._selected, exc_info=True)
            return ""

    def lineage_html(self) -> str:
        """:meth:`lineage_text` as HTML, with its indentation preserved.

        The info section renders HTML, which collapses the leading spaces the
        lineage uses to show depth — the one thing that made it readable.
        """
        text = self.lineage_text()
        if not text:
            return "<p><i>Nothing selected, or nothing recorded.</i></p>"
        return f"<pre style='margin:0'>{html.escape(text)}</pre>"

    def payload_text(self) -> str:
        """A text payload (README, mmCIF metadata) of the selected artifact."""
        item = self.selected
        if item is None or self._inspection is None:
            return ""
        if item.kind not in ("readme", "sample_metadata") and item.data_format != "cif":
            return ""
        return self._inspection.text(item.uid)

    # -- actions --------------------------------------------------------------

    def verify(self) -> str:
        """Check every recorded checksum and return a readable verdict."""
        if self._inspection is None:
            return "No container open."
        try:
            self._verify = self._inspection.verify()
        except Exception as exc:
            self._verify = [str(exc)]
        self.notify("verified")
        if not self._verify:
            return "Every recorded checksum matches the stored bytes."
        return "Checksum mismatch:\n" + "\n".join(self._verify)

    def tool_manifests(self) -> list:
        """Manifests of the tools that perform the selected artifact's operation."""
        item = self.selected
        return tools_for_operation(item.operation) if item else []

    def open_node(self, node: Any) -> None:
        """Select a node and ask the host to open its tool (graph double-click)."""
        self.select_node(node)
        self.notify("open_tool")

    def request_tool(self) -> None:
        """Ask the host to open the tool for the current selection."""
        self.notify("open_tool")
