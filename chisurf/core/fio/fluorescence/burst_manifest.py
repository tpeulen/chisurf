"""What a burst-analysis folder must remember about how its data was read.

A burst analysis folder has always carried *what was found* — the `.bur` tables,
and an `Info/*.mti` sidecar naming each source file and its length. It never
carried **how the source was read**: which container type, which routing
channels, what the macro- and micro-time resolutions were.

That omission is not academic. A burst table is a set of pointers back into
photon streams: every row is a `(first_photon, last_photon)` interval in a named
file. Anything that later wants those photons — sending a gated population to
FCS, to a decay, to PDA — has to open the source files again, and with nothing
recorded it has to *guess* how. The guesses were extension-based tables mapping
`.spc` to a container type called ``"SPC"``, which ``tttrlib`` does not accept.
It does not report that as an error either: it prints to stderr and returns an
object with **zero photons**, so a correlation was computed from nothing at all
and looked like a measurement with no signal.

The fix is not a better guess. It is to write down what was actually used, at
the one moment it is known for certain — while the file is open and being
analysed — and to read it back later instead of inferring it.

The manifest lives at ``<analysis_dir>/Info/analysis.json`` beside the existing
`.mti`, is additive (a second file analysed into the same folder appends its own
source entry), and is optional on read: folders written before this existed
simply return ``None`` and callers fall back to detection.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional

__all__ = [
    "MANIFEST_NAME",
    "MANIFEST_VERSION",
    "write_analysis_manifest",
    "read_analysis_manifest",
    "describe_tttr_source",
    "reading_settings_for",
]

#: File name inside the analysis folder's ``Info`` directory.
MANIFEST_NAME = "analysis.json"

#: Bumped when the on-disk shape changes incompatibly.
MANIFEST_VERSION = 1


def describe_tttr_source(
    path: pathlib.Path | str,
    tttr: Any,
    *,
    container_type: Optional[str] = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record how one source file was read, from the open object itself.

    Read off the live ``tttrlib.TTTR`` rather than taken on trust from the
    caller: the container type the caller *asked* for and the one that was
    actually used can differ (an unrecognised request degrades to detection),
    and it is the latter that has to be written down.

    Parameters
    ----------
    path : path-like
        The source measurement.
    tttr : tttrlib.TTTR
        The open object, queried for resolutions and channels.
    container_type : str, optional
        The container type used, when the caller knows it. Falls back to what
        the object reports.
    settings : dict, optional
        Extra reading settings worth preserving (channel groups, micro-time
        windows, LUT identifiers).

    Returns
    -------
    dict
        One ``sources`` entry.
    """
    entry: Dict[str, Any] = {"path": str(path)}

    detected = container_type
    if detected is None:
        for attribute in ("container_type", "tttr_container_type"):
            value = getattr(tttr, attribute, None)
            if value:
                detected = str(value)
                break
    if detected:
        entry["container_type"] = detected

    header = getattr(tttr, "header", None)
    if header is not None:
        for key, attribute in (
            ("macro_time_resolution", "macro_time_resolution"),
            ("micro_time_resolution", "micro_time_resolution"),
            ("number_of_micro_time_channels", "number_of_micro_time_channels"),
        ):
            value = getattr(header, attribute, None)
            if value is not None:
                entry[key] = float(value) if "resolution" in key else int(value)

    try:
        import numpy as np

        channels = np.asarray(tttr.routing_channels)
        entry["routing_channels"] = sorted(int(c) for c in np.unique(channels))
        entry["n_photons"] = int(channels.size)
    except Exception:
        pass

    if settings:
        entry["settings"] = dict(settings)
    return entry


def write_analysis_manifest(
    analysis_dir: pathlib.Path | str,
    sources: List[Dict[str, Any]],
    *,
    settings: Optional[Dict[str, Any]] = None,
    software_version: Optional[str] = None,
) -> pathlib.Path:
    """Write (or extend) the reading manifest of a burst-analysis folder.

    Appends rather than replaces: analysing a second measurement into an
    existing folder adds its source entry, matching how the `.mti` sidecar
    already behaves. An entry for a path already present is replaced, so
    re-running an analysis updates rather than duplicates.

    Parameters
    ----------
    analysis_dir : path-like
        The analysis folder; ``Info/`` is created inside it if needed.
    sources : list of dict
        Entries from :func:`describe_tttr_source`.
    settings : dict, optional
        Burst-search settings, merged into the manifest's own ``settings``.
    software_version : str, optional
        Version that produced the analysis.

    Returns
    -------
    pathlib.Path
        The manifest path.
    """
    info_dir = pathlib.Path(analysis_dir) / "Info"
    info_dir.mkdir(parents=True, exist_ok=True)
    target = info_dir / MANIFEST_NAME

    manifest: Dict[str, Any] = {
        "format": "chisurf-burst-analysis",
        "version": MANIFEST_VERSION,
        "sources": [],
        "settings": {},
    }
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                manifest.update(existing)
                manifest.setdefault("sources", [])
                manifest.setdefault("settings", {})
        except (OSError, ValueError):
            # A corrupt manifest must not stop the analysis being written; it is
            # replaced by one that is at least readable.
            pass

    by_path = {str(s.get("path")): s for s in manifest["sources"] if isinstance(s, dict)}
    for entry in sources:
        by_path[str(entry.get("path"))] = entry
    manifest["sources"] = list(by_path.values())

    if settings:
        manifest["settings"].update(settings)
    if software_version:
        manifest["software"] = {"package": "chisurf", "version": str(software_version)}

    target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return target


def read_analysis_manifest(
    start: pathlib.Path | str, max_up: int = 4
) -> Optional[Dict[str, Any]]:
    """Find the manifest for a `.bur` file, a folder, or anything beside them.

    Searches *start* and its parents for ``Info/analysis.json``, because callers
    hold different things: the `.bur` path, the `bi4_bur` directory that
    contains it, or the analysis folder above that.

    Parameters
    ----------
    start : path-like
        Where to start looking.
    max_up : int
        How many parent directories to try.

    Returns
    -------
    dict or None
        The manifest, or ``None`` when the folder predates it — which is not an
        error, only a reason to fall back to detection.
    """
    here = pathlib.Path(start)
    if here.is_file():
        here = here.parent
    for _ in range(max_up + 1):
        candidate = here / "Info" / MANIFEST_NAME
        if candidate.is_file():
            try:
                loaded = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
            return loaded if isinstance(loaded, dict) else None
        if here.parent == here:
            break
        here = here.parent
    return None


def reading_settings_for(
    source_path: pathlib.Path | str, manifest: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Return the recorded reading settings for one source measurement.

    Matched on the file name rather than the full path: burst analyses are
    routinely moved, copied off an instrument, or referenced through a different
    mount, and a manifest that only matched absolute paths would be useless
    exactly when it is needed.

    Parameters
    ----------
    source_path : path-like
        The measurement whose settings are wanted.
    manifest : dict or None
        A manifest from :func:`read_analysis_manifest`.

    Returns
    -------
    dict
        The recorded entry, or ``{}`` when there is nothing recorded.
    """
    if not manifest:
        return {}
    wanted = pathlib.Path(source_path)
    sources = manifest.get("sources") or []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        recorded = pathlib.Path(str(entry.get("path", "")))
        if recorded == wanted or recorded.name == wanted.name:
            return dict(entry)
    return {}
