"""Who measured what, when, on which sample -- in the files, not only in someone's head.

Every MT200 session directory carries the metadata its file names only hint at: the
operator initials in ``TP_20260930_JH_FluoresceinFCS.sptw``, the dye in
``Alexa647_1.ptu``, the sample in ``DM_20260808_MalE_211_322_Atto655.sptw``.  This module
keeps them explicitly, as one JSON sidecar per measurement -- ``<stem>.meta.json`` next to
``<stem>.ptu`` -- so a measurement is traceable without the workspace::

    {
      "schema": "chisurf.acquisition.meta/1",
      "operator": "TP",
      "experiment_type": "fcs",
      "dyes": ["Alexa 488"],
      "sample": "MalE 211-322, 10 nM",
      "project": "MalE-His titration",
      "instrument": "MT200",
      "started_at": "2026-10-30T14:46:10+01:00",
      "finished_at": "2026-10-30T14:56:12+01:00",
      "session": {"name": "TP_20261030_JH_FluoresceinFCS", "started_at": "..."}
    }

Times are local ISO 8601 with UTC offset (:meth:`AcquisitionMeta.start` /
:meth:`finish` / ``start_session`` / ``end_session`` stamp them).  Free-form fields stay
verbatim -- the *file-safe* forms are derived on demand via
:func:`chisurf.plugins.core.acq.live.naming` helpers, never by mangling what the operator
typed.  Unknown keys survive a round trip (forward compatibility), like the acquisition
settings file's schema.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

__all__ = ["ACQ_META_SCHEMA", "AcquisitionMeta", "read_meta", "write_meta"]

#: Schema identifier written into every sidecar; files with the same major version read.
ACQ_META_SCHEMA = "chisurf.acquisition.meta/1"

_KNOWN_FIELDS = (
    "schema", "operator", "experiment_type", "dyes", "sample", "project", "instrument",
    "notes", "started_at", "finished_at", "session",
)


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class AcquisitionMeta:
    """One measurement's provenance: operator, experiment, dyes, sample, project, times.

    ``experiment_type`` is the analyzer preset (``"fcs"``, ``"pie"``, ``"tcspc"``,
    ``"flim"`` ...) or any instrument label the operator uses; it is recorded, not
    policed.  ``session`` holds the workspace-level facts shared by the measurements of
    one session directory.
    """

    operator: str = ""
    experiment_type: str = ""
    dyes: list[str] = field(default_factory=list)
    sample: str = ""
    project: str = ""
    instrument: str = ""
    notes: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    session: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    # -- time stamps ---------------------------------------------------------
    def start(self) -> str:
        """Stamp and return the measurement start time (local, UTC offset kept)."""
        self.started_at = _now_iso()
        return self.started_at

    def finish(self) -> str:
        """Stamp and return the measurement end time."""
        self.finished_at = _now_iso()
        return self.finished_at

    def start_session(self, name: str = "") -> str:
        """Stamp the session start; ``name`` is the session-directory name."""
        self.session.setdefault("name", name)
        self.session["started_at"] = _now_iso()
        return self.session["started_at"]

    def end_session(self) -> str:
        """Stamp the session end (the moment the last measurement finished)."""
        self.session["finished_at"] = _now_iso()
        return self.session["finished_at"]

    # -- (de)serialisation ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """The sidecar document: known fields plus whatever was in ``extra``."""
        document = {"schema": ACQ_META_SCHEMA}
        document.update({key: value for key, value in asdict(self).items()
                         if key != "extra"})
        document.update(self.extra)
        return document

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> AcquisitionMeta:
        """Read a sidecar document; unknown keys are kept in ``extra``, none dropped."""
        document = dict(document or {})
        document.pop("schema", None)
        known = {key: document.pop(key) for key in _KNOWN_FIELDS if key != "schema" and key in document}
        for list_field in ("dyes",):
            if not isinstance(known.get(list_field), list):
                known[list_field] = [str(known.get(list_field))] if known.get(list_field) else []
        known["session"] = known.get("session") if isinstance(known.get("session"), dict) else {}
        meta = cls(**known)
        meta.extra = document  # everything this version does not know
        return meta

    # -- naming helpers ------------------------------------------------------
    def name_description(self, *, max_length: int = 60) -> str:
        """A human-readable description for a session directory name (sample + dyes)."""
        from .naming import sanitize_component

        parts = [self.sample, " ".join(self.dyes)]
        text = " ".join(part for part in parts if part)
        return sanitize_component(text, max_length=max_length)

    def measurement_base(self) -> str:
        """A per-measurement base name: sanitized sample, or the experiment type."""
        from .naming import sanitize_component

        text = self.sample or self.experiment_type or "measurement"
        return sanitize_component(text, max_length=60)


# -- sidecar I/O ---------------------------------------------------------------

def write_meta(path: Path | str, meta: AcquisitionMeta) -> Path:
    """Write *meta* as JSON to *path* atomically (temp file in the same directory)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(meta.to_dict(), indent=2, ensure_ascii=False, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(path)
    return path


def read_meta(path: Path | str) -> AcquisitionMeta:
    """Read an ``AcquisitionMeta`` from its sidecar JSON (raises ``ValueError`` on junk)."""
    path = Path(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} does not hold a metadata document")
    return AcquisitionMeta.from_dict(document)
