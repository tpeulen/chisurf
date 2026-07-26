"""Saving and restoring a whole chimol session.

PyMOL's ``save x.pse`` writes every object, its representations, its colours, the
camera and the settings, and ``load x.pse`` puts them all back. That is the unit
of work people actually keep -- a figure in progress is a session, not a PDB file
plus a note about what was typed.

Format
------
A zip container holding

* ``manifest.json`` -- everything JSON can carry: names, groups, flags, the view,
  the scene table, the display settings, and the list of anything that could not
  be carried;
* ``arrays.npz`` -- every NumPy array, keyed by where it came from.

Not PyMOL's ``.pse``, which is a pickle of PyMOL's own C structures; nothing
outside PyMOL can read one and chimol does not pretend to. Saving to ``.pse``
therefore says so, and loading a real PyMOL session reports that plainly instead
of failing with a decoding error.

The object field list is **derived from the state dataclass**, not written out
here. A hand-kept list of 53 fields drifts the first time one is added, and the
drift is silent: the session saves, reloads, and quietly lacks whatever was new.
"""

from __future__ import annotations

import dataclasses
import json
import zipfile
from typing import Any

import numpy as np

from .chimol_state import _MolViewObjectState

#: Bumped when the layout changes in a way an older reader cannot handle.
SESSION_VERSION = 1

#: Marker for a value that lives in the npz rather than the manifest.
_ARRAY = "__array__"
_SET = "__set__"
_TUPLE = "__tuple__"
_PAIRS = "__pairs__"


class SessionError(Exception):
    """Raised when a file is not a chimol session, with the reason in the text."""


# --------------------------------------------------------------------------- #
# Encoding
# --------------------------------------------------------------------------- #
def _encode(value: Any, key: str, arrays: dict[str, np.ndarray], skipped: list[str]):
    """Turn one value into something JSON can hold, banking arrays as we go.

    Anything neither JSON-able nor an array is **skipped by name** rather than
    dropped silently: the manifest carries the list, so a reloaded session can
    say what it could not bring back.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, np.ndarray):
        arrays[key] = value
        return {_ARRAY: key}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        if all(isinstance(name, str) for name in value):
            return {
                name: _encode(item, f"{key}.{name}", arrays, skipped)
                for name, item in value.items()
            }
        # JSON objects only have string keys, and some of ours are tuples: the
        # bond-edit map is keyed by an ``(i, j)`` atom pair. Skipping those keys
        # dropped every recorded bond *order* while keeping the bonds, so a
        # reloaded session had single bonds where doubles had been set. Stored as
        # key/value pairs instead, which any encodable key survives.
        return {
            _PAIRS: [
                [
                    _encode(name, f"{key}.k{i}", arrays, skipped),
                    _encode(item, f"{key}.v{i}", arrays, skipped),
                ]
                for i, (name, item) in enumerate(value.items())
            ]
        }
    if isinstance(value, set):
        return {
            _SET: [
                _encode(v, f"{key}.{i}", arrays, skipped)
                for i, v in enumerate(sorted(value, key=repr))
            ]
        }
    if isinstance(value, tuple):
        return {
            _TUPLE: [
                _encode(v, f"{key}.{i}", arrays, skipped)
                for i, v in enumerate(value)
            ]
        }
    if isinstance(value, list):
        return [
            _encode(v, f"{key}.{i}", arrays, skipped) for i, v in enumerate(value)
        ]
    skipped.append(f"{key} ({type(value).__name__})")
    return None


def _decode(value: Any, arrays: dict[str, np.ndarray]):
    """Inverse of :func:`_encode`."""
    if isinstance(value, dict):
        if _ARRAY in value:
            return arrays.get(value[_ARRAY])
        if _SET in value:
            return {_decode(v, arrays) for v in value[_SET]}
        if _TUPLE in value:
            return tuple(_decode(v, arrays) for v in value[_TUPLE])
        if _PAIRS in value:
            return {
                _decode(k, arrays): _decode(v, arrays) for k, v in value[_PAIRS]
            }
        return {name: _decode(item, arrays) for name, item in value.items()}
    if isinstance(value, list):
        return [_decode(v, arrays) for v in value]
    return value


# --------------------------------------------------------------------------- #
# Save
# --------------------------------------------------------------------------- #
def save_session(viewer, path, *, scenes=None) -> dict:
    """Write the viewer's whole session to ``path``.

    Parameters
    ----------
    viewer : MolView
        The viewer to capture.
    path : str or pathlib.Path
        Destination file.
    scenes : SceneStore, optional
        The named scenes to include. They live on the command layer rather than
        on the viewer, so the caller has to hand them over.

    Returns
    -------
    dict
        ``{"objects": n, "skipped": [...]}`` -- what went in, and by name
        anything that could not.
    """
    arrays: dict[str, np.ndarray] = {}
    skipped: list[str] = []
    state_fields = [f.name for f in dataclasses.fields(_MolViewObjectState)]

    objects = []
    for index, (object_id, entry) in enumerate(viewer._objects.items()):
        if entry.placeholder:
            continue
        record = {
            "id": object_id,
            "name": entry.name,
            "visible": bool(entry.visible),
            "source_path": entry.source_path,
            "group": entry.group,
            "state": {},
        }
        for field_name in state_fields:
            value = getattr(entry.state, field_name, None)
            record["state"][field_name] = _encode(
                value, f"obj{index}.{field_name}", arrays, skipped
            )
        objects.append(record)

    manifest: dict[str, Any] = {
        "version": SESSION_VERSION,
        "objects": objects,
        "active_object": viewer._active_object_id,
        "groups_open": dict(getattr(viewer, "_group_open", {}) or {}),
        "skipped": sorted(set(skipped)),
    }

    # The camera, as the 18-float view tuple -- the same numbers `get_view`
    # prints, so a session and a pasted view agree about what a view is.
    # ``get_view`` is a *command*; the viewer's own accessor is
    # ``get_view_state``, and reaching for the command name here silently stored
    # a null view behind the except clause.
    try:
        manifest["view"] = [float(v) for v in viewer.get_view_state()]
    except Exception as exc:
        manifest["view"] = None
        skipped.append(f"view ({exc})")

    # Named scenes. Stored as a list rather than a dict so the recall order --
    # which is what `scene next` walks -- survives the round trip.
    if scenes is not None:
        try:
            manifest["scenes"] = [
                _encode(
                    dataclasses.asdict(scenes.get(name)),
                    f"scene.{name}", arrays, skipped,
                )
                for name in scenes.names()
                if scenes.get(name) is not None
            ]
        except Exception:
            skipped.append("scenes")

    # Display settings travel with the session, as they do in PyMOL: a figure
    # depends on them as much as on the coordinates.
    try:
        from ..config import _DISPLAY_CONFIG

        manifest["settings"] = _encode(
            json.loads(json.dumps(_DISPLAY_CONFIG, default=str)),
            "settings", arrays, skipped,
        )
    except Exception:
        skipped.append("settings")

    manifest["skipped"] = sorted(set(skipped))

    import io

    buffer = io.BytesIO()
    if arrays:
        np.savez_compressed(buffer, **arrays)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=1))
        if arrays:
            archive.writestr("arrays.npz", buffer.getvalue())

    return {"objects": len(objects), "skipped": manifest["skipped"]}


# --------------------------------------------------------------------------- #
# Load
# --------------------------------------------------------------------------- #
def read_manifest(path) -> tuple[dict, dict[str, np.ndarray]]:
    """Read a session file, or explain what it is instead.

    Raises
    ------
    SessionError
        When the file is not a chimol session. A PyMOL ``.pse`` is named as such
        rather than reported as corrupt, because that is the mistake a PyMOL user
        will actually make.
    """
    if not zipfile.is_zipfile(path):
        with open(path, "rb") as handle:
            head = handle.read(2)
        if head[:1] in (b"\x80", b"(") or head[:2] == b"\x1f\x8b":
            raise SessionError(
                "this looks like a PyMOL .pse (a pickle of PyMOL's own "
                "structures); chimol sessions are its own format and the two "
                "cannot be exchanged"
            )
        raise SessionError("not a chimol session file")

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "manifest.json" not in names:
            raise SessionError("no manifest.json: not a chimol session file")
        manifest = json.loads(archive.read("manifest.json"))
        arrays: dict[str, np.ndarray] = {}
        if "arrays.npz" in names:
            import io

            with np.load(io.BytesIO(archive.read("arrays.npz")),
                         allow_pickle=False) as data:
                arrays = {key: data[key] for key in data.files}

    version = int(manifest.get("version", 0))
    if version > SESSION_VERSION:
        raise SessionError(
            f"session version {version} is newer than this chimol understands "
            f"({SESSION_VERSION})"
        )
    return manifest, arrays


def load_session(viewer, path, *, scenes=None) -> dict:
    """Replace the viewer's contents with a saved session.

    Parameters
    ----------
    viewer : MolView
        Viewer to restore into; its current objects are discarded.
    path : str or pathlib.Path
        A file written by :func:`save_session`.
    scenes : SceneStore, optional
        Store to refill with the session's named scenes.

    Returns
    -------
    dict
        ``{"objects": n, "skipped": [...]}``.
    """
    manifest, arrays = read_manifest(path)
    state_fields = {f.name for f in dataclasses.fields(_MolViewObjectState)}

    # Settings first: object state is interpreted against them, and restoring
    # them afterwards would rebuild the scene twice. Updated *in place* -- eight
    # modules hold this dict by reference and would keep the old one otherwise.
    settings = manifest.get("settings")
    if isinstance(settings, dict):
        try:
            from ..config import _DISPLAY_CONFIG

            restored = _decode(settings, arrays)
            if isinstance(restored, dict):
                _DISPLAY_CONFIG.clear()
                _DISPLAY_CONFIG.update(restored)
        except Exception:
            pass

    viewer._objects.clear()
    viewer._active_object_id = None
    if hasattr(viewer, "_group_open"):
        viewer._group_open = {}

    unknown: list[str] = []
    for record in manifest.get("objects", []):
        entry = viewer._create_object(name=str(record.get("name") or "object"))
        entry.visible = bool(record.get("visible", True))
        entry.source_path = record.get("source_path")
        entry.group = record.get("group")
        for field_name, encoded in (record.get("state") or {}).items():
            if field_name not in state_fields:
                # A session from a newer chimol: name it rather than crash.
                unknown.append(field_name)
                continue
            setattr(entry.state, field_name, _decode(encoded, arrays))

    groups_open = manifest.get("groups_open") or {}
    if hasattr(viewer, "_group_open") and isinstance(groups_open, dict):
        viewer._group_open = {str(k): bool(v) for k, v in groups_open.items()}

    # Re-point the active object by *name*: ids are regenerated on create, so the
    # saved id means nothing in this viewer.
    wanted = manifest.get("active_object")
    by_id = {rec["id"]: rec.get("name") for rec in manifest.get("objects", [])}
    target_name = by_id.get(wanted)
    for object_id, entry in viewer._objects.items():
        if target_name is not None and entry.name == target_name:
            viewer._active_object_id = object_id
            break
    else:
        if viewer._objects:
            viewer._active_object_id = next(iter(viewer._objects))

    viewer._update_view()

    # The view goes on last: rebuilding the scene moves the camera, so restoring
    # it earlier is undone by the work that follows. The same ordering trick the
    # scene store needs.
    view = manifest.get("view")
    if view:
        try:
            viewer.set_view_state([float(v) for v in view])
        except Exception:
            pass

    # Scenes, in the saved order.
    saved_scenes = manifest.get("scenes")
    if scenes is not None and isinstance(saved_scenes, list):
        from .scenes import Scene

        scenes._scenes.clear()
        scenes._order.clear()
        for encoded in saved_scenes:
            fields = _decode(encoded, arrays)
            if not isinstance(fields, dict) or not fields.get("name"):
                continue
            name = str(fields["name"])
            scenes._scenes[name] = Scene(**fields)
            scenes._order.append(name)

    skipped = list(manifest.get("skipped") or [])
    if unknown:
        skipped.append(
            "unknown state fields from a newer session: "
            + ", ".join(sorted(set(unknown)))
        )
    # The view is handed back as well as applied: a caller that refreshes a GUI
    # afterwards re-zooms, which silently replaced the restored camera distance
    # and clip planes with ones computed from the bounding sphere. Whoever
    # touches the view last has to be the one restoring it.
    return {
        "objects": len(viewer._objects),
        "skipped": skipped,
        "view": [float(v) for v in view] if view else None,
    }
