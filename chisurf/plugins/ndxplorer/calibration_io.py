"""Save and load an accurate-FRET calibration.

A calibration is a handful of numbers — gamma, alpha, beta, delta, R0, the
backgrounds — that took a measurement and a fit to obtain. Losing them means
running the calibration again on data that may no longer be open, and typing
them into another window by hand is how a factor ends up transcribed wrong.

**The default place to keep them is the measurement itself.** A `.pto`
container already holds the photon stream, the burst table and the background
estimate; a calibration determined *from* that measurement belongs beside them,
not in a stray file next to it that a later copy will leave behind. So
:func:`save_calibration` writes into the container when the window has one, and
falls back to a JSON file only when it does not, or when the caller asks.

Both routes write the same JSON payload, so a calibration read out of a
container and one read out of a file are the same object.

The payload carries more than the numbers: the report text the calibration
printed, the uncertainties, which factors were actually written and which were
held fixed, and where it came from. A bare set of factors cannot answer "was
this gamma fitted here, or carried in from a reference sample?", and that is the
question a reader has a year later.
"""

from __future__ import annotations

import datetime
import json
import logging
import pathlib
from typing import Any

__all__ = [
    "CALIBRATION_ARTIFACT",
    "SUFFIX",
    "container_of",
    "save_calibration",
    "load_calibration",
    "stored_calibrations",
]

#: Object name inside a `.pto` container. One name, so a later save is found
#: as another version of the same thing rather than as an unrelated object.
CALIBRATION_ARTIFACT = "fret_calibration"

#: Suffix for the file fallback. Plain JSON, deliberately: a calibration a
#: person may need to read, diff or mail should not need this program to open.
SUFFIX = ".fretcal.json"

#: Payload version. Bumped when a field changes meaning, never when one is
#: added — a reader that does not know a key ignores it.
VERSION = 1


def container_of(ndx) -> str:
    """The `.pto` file the window's data came from, or ``""``.

    The same provenance lookup the background step uses: the burst table
    records the container it was read from, so the calibration can be written
    back to it without asking the user where the measurement lives.
    """
    data_source = getattr(ndx, "data_source", None)
    provenance = getattr(data_source, "provenance", None) or {}
    container = provenance.get("container_path") or ""
    if not container:
        metadata = getattr(data_source, "metadata", None) or {}
        container = (metadata.get("provenance") or {}).get("container_path", "")
    return str(container or "")


def _payload(constants: dict, *, result: dict | None = None, note: str = "") -> bytes:
    """The bytes written by either route."""
    result = result or {}
    doc: dict[str, Any] = {
        "format": "chisurf.fret_calibration",
        "version": VERSION,
        "saved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="microseconds"
        ),
        "constants": {
            str(k): (float(v) if isinstance(v, (int, float)) else v)
            for k, v in dict(constants or {}).items()
        },
    }
    if note:
        doc["note"] = str(note)
    for key in (
        "factors",
        "uncertainties",
        "held",
        "determined",
        "report",
        "background",
        "background_fitted",
        "columns",
    ):
        if key in result and result[key] not in (None, {}, []):
            doc[key] = result[key]
    return json.dumps(doc, indent=2, sort_keys=True).encode("utf-8")


#: How many saved calibrations a measurement keeps. A FIFO rather than a single
#: slot: the previous one is what you compare against when a new calibration
#: comes out differently, and the one before that is what you go back to when it
#: turns out worse. Unbounded is not the alternative -- a container reached
#: thirteen of these in one session, and every reader then walks them all.
CALIBRATION_HISTORY = 5


def _saved_at(measurement, uid) -> str:
    """The ``saved_utc`` recorded in one calibration, or ``""``.

    Sorting on this rather than on the object's position is what makes the
    history reliable once anything has been removed.
    """
    try:
        blob = measurement.get_blob(uid)
        if isinstance(blob, (bytes, bytearray)):
            blob = blob.decode("utf-8")
        return str(json.loads(blob).get("saved_utc", ""))
    except Exception:
        return ""


def _prune_calibrations(measurement, keep: int = CALIBRATION_HISTORY) -> int:
    """Drop all but the newest *keep* saved calibrations. Returns how many went.

    The container appends, so saving is what makes the history grow; pruning
    here means the bound holds however the window is used, rather than depending
    on somebody remembering to tidy up.
    """
    handle = getattr(measurement, "_f", None)
    remove = getattr(handle, "remove", None)
    if handle is None or not callable(remove):
        return 0
    try:
        entries = [
            (_saved_at(measurement, obj.uid), index, obj.uid)
            for index, obj in enumerate(handle.objects())
            if getattr(obj, "name", "") == CALIBRATION_ARTIFACT
        ]
    except Exception:
        return 0
    # By the timestamp *in the payload*, not by position. Removing an object
    # frees its slot and the next write reuses it, so after the very first prune
    # the order of ``objects()`` no longer tells you which calibration is newer
    # -- and a FIFO that drops the wrong end is worse than no FIFO at all.
    entries.sort()
    uids = [uid for _, _, uid in entries]
    dropped = 0
    for uid in uids[: max(0, len(uids) - int(keep))]:
        try:
            if remove(uid):
                dropped += 1
        except Exception:
            continue
    return dropped


def save_calibration(
    constants: dict,
    *,
    ndx=None,
    path: str | None = None,
    result: dict | None = None,
    note: str = "",
    embed: bool = True,
) -> dict:
    """Write a calibration to the measurement container, or to a file.

    Parameters
    ----------
    constants : dict
        The ndX constants as they now stand — what the window will use.
    ndx : object, optional
        The window, used to find its `.pto` container.
    path : str, optional
        Write here instead. Given a path, the file route is always taken.
    result : dict, optional
        The optimizer's return value, for the report and uncertainties.
    note : str, optional
        A line from the user saying what this calibration is of.
    embed : bool, optional
        Prefer the container (default). ``False`` forces the file route.

    Returns
    -------
    dict
        ``{"ok", "where", "target"}``; ``{"ok": False, "error": …}`` on failure.
        ``where`` is ``"container"`` or ``"file"`` — the caller should say which
        happened rather than claim "saved".
    """
    data = _payload(constants, result=result, note=note)

    if path is None and embed:
        container = container_of(ndx)
        if container:
            try:
                from chisurf.core.fio.pto import Measurement

                with Measurement.open(container, writable=True) as measurement:
                    measurement.put_blob(
                        CALIBRATION_ARTIFACT,
                        data,
                        artifact_kind="calibration_data",
                        data_format="json",
                        operation_type="calibration",
                        mime_type="application/json",
                    )
                    dropped = _prune_calibrations(measurement)
                if dropped:
                    logging.info(
                        "calibration saved; dropped %d older one(s), keeping the last %d",
                        dropped,
                        CALIBRATION_HISTORY,
                    )
                return {"ok": True, "where": "container", "target": container}
            except Exception as exc:  # noqa: BLE001
                # Fall through to the file route rather than lose the numbers:
                # a read-only container or a lock held by another window is a
                # reason to write elsewhere, not a reason to write nothing.
                fallback = str(exc)
                if path is None:
                    stem = pathlib.Path(container).with_suffix("")
                    path = str(stem) + SUFFIX
                pathlib.Path(path).write_bytes(data)
                return {
                    "ok": True,
                    "where": "file",
                    "target": path,
                    "warning": f"could not write into the container ({fallback})",
                }

    if path is None:
        return {"ok": False, "error": "no container for this window and no path given"}
    try:
        pathlib.Path(path).write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "where": "file", "target": path}


def stored_calibrations(ndx=None, container: str | None = None) -> list[dict]:
    """Every calibration stored in the container, **oldest first**.

    Returns a list of ``{"uid", "saved_utc", "note", "constants", …}``. The
    container keeps each save as its own object, so an earlier calibration is
    still there after a later one is written — which is the point of putting
    them in the measurement rather than overwriting a file.

    The order is taken from each payload's own ``saved_utc``, not from the
    order the container lists objects in. Two separate things make position
    unusable: the container was observed to list objects newest-first, which
    silently made "the latest calibration" the oldest one, and removing an
    object (which :func:`_prune_calibrations` does) frees a slot that the next
    save reuses, so from the first prune onwards position is not even a
    permutation of write order. The timestamp is recorded to the microsecond
    so that two saves in one second still order; the uid only breaks a tie.
    """
    target = container or container_of(ndx)
    if not target:
        return []
    try:
        from chisurf.core.fio.pto import Measurement

        out = []
        with Measurement.open(target, writable=False) as measurement:
            for obj in measurement.artifacts(artifact_kind="calibration_data"):
                if getattr(obj, "name", "") != CALIBRATION_ARTIFACT:
                    continue
                try:
                    doc = json.loads(bytes(measurement.get_blob(obj.uid)).decode("utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                doc["uid"] = int(obj.uid)
                out.append(doc)
        out.sort(key=lambda d: (str(d.get("saved_utc", "")), int(d.get("uid", 0))))
        return out
    except Exception:  # noqa: BLE001
        return []


def load_calibration(*, ndx=None, path: str | None = None, uid: int | None = None) -> dict:
    """Read a calibration back.

    With *path*, reads that file. Otherwise reads the newest calibration stored
    in the window's container, or the one named by *uid*.

    Returns
    -------
    dict
        ``{"ok", "constants", "where", "target", "saved_utc", "note", "report"}``
        or ``{"ok": False, "error": …}``. Nothing is applied — the caller
        decides whether to write these into the window, because replacing a
        calibration is a decision and this function is a reader.
    """
    if path:
        try:
            doc = json.loads(pathlib.Path(path).read_text("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        if doc.get("format") != "chisurf.fret_calibration":
            return {"ok": False, "error": f"{path} is not a ChiSurf FRET calibration"}
        return {
            "ok": True,
            "where": "file",
            "target": path,
            "constants": doc.get("constants") or {},
            "saved_utc": doc.get("saved_utc", ""),
            "note": doc.get("note", ""),
            "report": doc.get("report", ""),
            "document": doc,
        }

    stored = stored_calibrations(ndx)
    if not stored:
        return {"ok": False, "error": "this measurement carries no stored calibration"}
    if uid is not None:
        stored = [d for d in stored if d.get("uid") == int(uid)] or stored
    doc = stored[-1]
    return {
        "ok": True,
        "where": "container",
        "target": container_of(ndx),
        "constants": doc.get("constants") or {},
        "saved_utc": doc.get("saved_utc", ""),
        "note": doc.get("note", ""),
        "report": doc.get("report", ""),
        "document": doc,
    }
