"""What one step of the burst workflow hands the next: the detector setup, the raw files, the bursts.

Shared by the native hub (:mod:`.gui.native`) and the legacy Qt shell (:mod:`.gui.tool`), so both answer "which
bursts do the later steps read" the same way. Nothing here imports a GUI toolkit.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


@dataclass
class BurstWorkflowContext:
    """Shared state handed from earlier burst workflow steps to later steps."""

    channel_settings: dict[str, Any] = field(default_factory=dict)
    #: Name of the detector setup ``channel_settings`` was read from — panels
    #: that take a setup by name (rather than a detector table) need it.
    setup_name: str = ""
    raw_files: list[Path] = field(default_factory=list)
    burst_folder: Path | None = None
    bur_files: list[Path] = field(default_factory=list)
    mmfdb_artifacts: dict[str, Any] = field(default_factory=dict)
    raw_mmfdb_artifacts: dict[str, Any] = field(default_factory=dict)
    #: VV/VH-stacked {detector: {"irf", "bg"}} patterns from the IRF/background
    #: tool, applied to the MLE panel when it loads.
    irf_background_patterns: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-compatible workflow context payload."""
        return {
            "channel_settings": self.channel_settings,
            "setup_name": self.setup_name,
            "raw_files": [str(path) for path in self.raw_files],
            "burst_folder": str(self.burst_folder) if self.burst_folder else None,
            "bur_files": [str(path) for path in self.bur_files],
            "mmfdb_artifacts": self.mmfdb_artifacts,
            "raw_mmfdb_artifacts": self.raw_mmfdb_artifacts,
        }

    def set_burst_folder(self, folder: Path) -> None:
        """Adopt *folder* (a burst-analysis folder or a ``.pto`` container) as the bursts the later steps read."""
        folder = Path(folder)
        self.burst_folder = folder
        # A container *is* the burst source, so it has no `.bur` files to list — and `glob` on a file returns
        # nothing rather than raising, which would have left this silently empty either way.
        self.bur_files = sorted(folder.glob("**/*.bur")) if folder.is_dir() else []


def folder_from_result(result: object) -> Path | None:
    """The output folder named by a burst-selection result payload (``None`` if it names none that exists)."""
    if not isinstance(result, dict):
        return None
    candidates: list[str] = []
    for key in ("output_folder", "analysis_folder"):
        value = result.get(key)
        if isinstance(value, str):
            candidates.append(value)
    for nested_key in ("metadata", "output_paths"):
        nested = result.get(nested_key) or {}
        if isinstance(nested, dict):
            value = nested.get("output_folder")
            if isinstance(value, str):
                candidates.append(value)
    for candidate in candidates:
        path = Path(candidate)
        if path.exists() and path.is_dir():
            return path
    return None


def materialize_handoff(context: BurstWorkflowContext, frames_by_file: Mapping[Any, Any]) -> Path | None:
    """Give the later steps something to read the bursts from when the search wrote no folder.

    For a `.pto` source that is the container itself: it already holds the bursts, beside the photons they were
    found in, and every downstream read goes through ``read_burst_analysis``, which opens one. Writing a
    ``burst_analysis_handoff/`` folder of `.bur` files there put the same results in a second place — and the
    second place went stale the moment the selection was re-run.

    Anything else still gets the folder: a vendor file has nowhere to keep the bursts, and the legacy layout is
    what the readers understand. *frames_by_file* maps a raw file (path or its string) to its burst table.
    """
    if not frames_by_file:
        return None
    raw_files = [Path(p) for p in context.raw_files] or [Path(p) for p in frames_by_file.keys()]
    if not raw_files:
        return None

    from chisurf.core.fio.pto import SUFFIX

    containers = [p for p in raw_files if p.suffix.lower() == SUFFIX]
    if containers and len(containers) == len(raw_files):
        # One container is one measurement; the later steps take the first and read the rest the same way.
        return containers[0]

    output_folder = raw_files[0].parent / "burst_analysis_handoff"
    bur_folder = output_folder / "bi4_bur"
    bur_folder.mkdir(parents=True, exist_ok=True)

    from chisurf.plugins.burst.burst_selection.api.io import write_bur, write_container

    for raw_path in raw_files:
        frame = None
        for key in (raw_path.resolve(), raw_path, str(raw_path.resolve()), str(raw_path)):
            frame = frames_by_file.get(key)
            if frame is not None:
                break
        if frame is None:
            continue
        write_bur(frame, bur_folder / f"{raw_path.stem}.bur")
        # The same bursts, in the measurement's own file: the handoff folder is a bridge between two steps of
        # one session and is rewritten each time; the container is where they keep living.
        try:
            write_container(raw_path, frame, parameters=context.to_payload())
        except Exception as exc:  # noqa: BLE001 - the .bur hand-off above is what the later steps read
            logger.warning(f"Could not write the container for {raw_path}: {exc}")

    payload = context.to_payload()
    payload["raw_files"] = [str(path) for path in raw_files]
    (output_folder / "burst_analysis_handoff.json").write_text(json.dumps(payload, indent=2, default=str))
    return output_folder


def burst_sources(context: BurstWorkflowContext) -> list[Path]:
    """The burst tables this workflow has produced, however stored.

    A burst search over a `.pto` keeps its bursts **inside the measurement** and writes no ``.bur`` at all, so a
    step that reads only ``bur_files`` sees nothing after a perfectly successful run. Both shapes come back as
    paths: a loose ``.bur``, or a container run addressed like a folder (``m000.pto/sliding_window_All 0.1500#60``),
    which every burst reader in ChiSurf understands.
    """
    if context.bur_files:
        return list(context.bur_files)
    folder = context.burst_folder
    if folder is None:
        return []
    from chisurf.core.fio.fluorescence import burst_tree

    if not burst_tree.is_container_path(folder):
        return []
    if folder.suffix.lower() != burst_tree.SUFFIX:
        return [folder]  # the path already names one run
    try:
        runs = burst_tree.list_runs(folder)
    except Exception as exc:  # noqa: BLE001 - an unreadable container has no sources
        logger.warning(f"burst analysis: could not list the runs of {folder} — {exc}")
        return []
    if not runs:
        return []
    # Newest last -- but newest is not automatically *usable*: a search made before the detector definitions
    # reached the step writes a table with no per-detector split at all. So: the newest run whose columns *map*,
    # and only if none of them do, the newest run there is.
    from chisurf.core.fluorescence.burst.table import maps_fret_channels

    for run in reversed(runs):
        candidate = folder / run
        if maps_fret_channels(candidate):
            if run != runs[-1]:
                logger.info(
                    f"burst analysis: using the run '{run}' — the newer '{runs[-1]}' has no per-detector "
                    "columns (it was searched without detector definitions)."
                )
            return [candidate]
    return [folder / runs[-1]]


def analysis_path(context: BurstWorkflowContext) -> Path | None:
    """The burst analysis a folder-taking tool should read: the folder, or the newest usable run of a container."""
    folder = context.burst_folder
    if folder is None:
        return None
    from chisurf.core.fio.fluorescence import burst_tree

    if folder.suffix.lower() != burst_tree.SUFFIX:
        return folder
    sources = burst_sources(context)
    return sources[0] if sources else folder


__all__ = [
    "BurstWorkflowContext",
    "analysis_path",
    "burst_sources",
    "folder_from_result",
    "materialize_handoff",
]
