"""The Qt-free model behind MFD Prepare: the burst folder, the preparation run and the result tables.

Everything shown is computed by :func:`~chisurf.plugins.burst.mfd_prepare.api.prepare_folder` (or the RPC method of the
same name when a client is connected); the model reformats that result, it adds no number of its own. The report text is
the one the Qt tool showed; the tables are the same facts, one row per detector or photon source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: A detector whose recomputed photon count agrees with the burst table in at least this fraction of bursts is ``ok``.
AGREEMENT_REQUIRED = 0.98


class MfdPrepareModel:
    """State and actions of the window (the app reads this, the spec calls it)."""

    def __init__(self, client: Any = None) -> None:
        self.client = client
        self.folder: str = ""
        self.report: str = ""
        self.result: dict[str, Any] = {}
        self.error: str = ""
        self.status_text: str = ""
        self.prepared_folder: str = ""
        self._observers: list = []

    # -- observers (SnapshotJob reads the model through these) ----------------------------------------- #
    def notify(self, event: str, *args: Any) -> None:
        for observer in list(self._observers):
            observer(event)

    # -- the actions ------------------------------------------------------------------------------------ #
    def set_folder(self, path: str) -> bool:
        """Take *path* (a folder, or a ``.bur`` file inside one) as the folder to prepare; False if it does not exist."""
        p = Path(str(path))
        if not (p.is_dir() or p.is_file()):
            self.status_text = f"Error: not a folder or burst table: {path}"
            return False
        self.folder = str(p)
        self.status_text = f"Folder: {p}. Press Prepare."
        return True

    def prepare(self) -> None:
        """Run the preparation (blocking; the app runs it through a ``SnapshotJob``) and fill the report and result."""
        self.error = ""
        if not self.folder:
            self.report = "Select a folder first."
            self.result = {}
            return
        self.status_text = "Preparing..."
        try:
            if self.client is not None and getattr(self.client, "_rpc", None) is not None:
                result = self.client.prepare(self.folder)
            else:
                from ..api import prepare_folder
                from ..api.models import PrepareRequest

                result = prepare_folder(PrepareRequest(folder=self.folder)).to_dict()
            if result.get("error"):
                self.report = f"Error: {result['error']}"
                self.error = str(result["error"])
                self.result = {}
            elif result.get("ok"):
                payload = result.get("result", result)
                self.report = payload.get("report", json.dumps(payload, indent=2, default=str))
                self.result = payload
            else:
                self.report = result.get("report", json.dumps(result, indent=2, default=str))
                self.result = result
        except Exception as exc:  # noqa: BLE001 - shown in the report, as the Qt tool did
            self.report = f"Error: {exc}"
            self.error = str(exc)
            self.result = {}
        self.prepared_folder = self.folder if self.result else ""
        self.status_text = self.report.splitlines()[0] if self.error else (
            f"Prepared {Path(self.folder).name}: {self.result.get('n_bursts', 0)} bursts, "
            f"{self.verdict_text()}" if self.result else "Done.")

    # -- what the window shows ------------------------------------------------------------------------- #
    @property
    def folder_line(self) -> str:
        return self.folder or "No folder selected"

    def detector_names(self) -> list[str]:
        return [str(c) for c in self.result.get("channels", [])]

    def unverified(self) -> list[str]:
        summary = self.result.get("summary", {}) or {}
        unverified = [str(n) for n in summary.get("unverified_channels", [])]
        if unverified or "unverified_channels" in summary:
            return unverified
        verified = {str(c) for c in self.result.get("verified_channels", [])}
        return [n for n in self.detector_names() if n not in verified]

    def verdict_text(self) -> str:
        if not self.result:
            return ""
        bad = self.unverified()
        return "every detector verified" if not bad else "UNVERIFIED: " + ", ".join(bad)

    def detector_rows(self) -> list[dict]:
        """One row per detector: its channel definition, bursts without photons, count agreement and verdict."""
        summary = self.result.get("summary", {}) or {}
        agreement = self.result.get("count_agreement", {}) or {}
        empty = summary.get("n_empty", {}) or {}
        streams = summary.get("inferred_streams", {}) or {}
        origin = str(summary.get("stream_origin", ""))
        bad = set(self.unverified())
        rows = []
        for name in self.detector_names():
            definition = streams.get(name) or {}
            windows = definition.get("micro_time_ranges") or []
            rows.append({
                "detector": name,
                "channels": ", ".join(str(c) for c in definition.get("channels", [])) or f"({origin})",
                "window": ", ".join(f"{int(a)}-{int(b)}" for a, b in windows) or ("all" if definition else ""),
                "empty": int(empty.get(name, 0)),
                "agreement": float(agreement.get(name, float("nan"))),
                "verdict": "UNVERIFIED" if name in bad else ("ok" if agreement.get(name, 0.0) >= AGREEMENT_REQUIRED else "check"),
            })
        return rows

    def source_rows(self) -> list[dict]:
        """One row per photon file: where it was found and how many photons it holds."""
        summary = self.result.get("summary", {}) or {}
        sources = self.result.get("sources", {}) or {}
        origins = sources.get("origin", {}) or {}
        photons = summary.get("photons", {}) or {}
        paths = {}
        for line in self.report.splitlines():
            if " -> " in line and line.startswith("  "):
                name, _, rest = line.strip().partition(" -> ")
                paths[name] = rest.rsplit(" [", 1)[0]
        return [{"file": str(name), "path": paths.get(str(name), ""), "origin": str(origins.get(name, "")),
                 "photons": int(photons.get(name, 0))} for name in sorted(set(origins) | set(photons))]

    def summary_rows(self) -> list[dict]:
        """The report's header facts and the totals the result carries, as quantity / value rows."""
        if not self.result:
            return []
        rows = []
        for line in self.report.splitlines():
            if line.startswith(" "):
                break
            key, sep, value = line.partition(": ")
            if sep and key != "burst folder":
                rows.append({"quantity": key, "value": value})
        rows.append({"quantity": "duration (s)", "value": f"{float(self.result.get('duration_s', 0.0)):.6g}"})
        rows.append({"quantity": "photons in the bursts", "value": str(int(self.result.get("total_photons", 0)))})
        return rows

    @property
    def report_text(self) -> str:
        return self.report
