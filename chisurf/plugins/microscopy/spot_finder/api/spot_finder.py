"""Run detection over a list of files, and say what happened to each.

The loop is here, once, rather than in the GUI and again behind the CLI. That
is not tidiness: the two loops the molecule MLE grew do different things — one
writes the result into the measurement's container and the other does not — so
whether a run left provenance behind depended on which surface it was started
from, and nothing said so.

The other rule this enforces is that a batch answers for **every** input. A
file that raised and a file with nothing in it are rows with a status, not
files that quietly leave the result set. ``len(result.rows) == len(files)`` is
the invariant, and it is the batch-level restatement of the region table's own
one-row-per-region rule.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import SpotFinderRequest, SpotFinderRunResult

logger = logging.getLogger(__name__)

#: ``(index, total, name)`` — the name matters, because a status line that only
#: counts cannot say which file is slow or which one is failing.
ProgressCallback = Callable[[int, int, str], None]


def detect_request(
    request: SpotFinderRequest,
    *,
    progress: ProgressCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> SpotFinderRunResult:
    """Detect in every file of *request*.

    Parameters
    ----------
    request : SpotFinderRequest
        Files, settings and where the results go.
    progress : callable, optional
        Called ``(index, total, name)`` before each file.
    should_stop : callable, optional
        Polled between files; when it returns true the run stops and the
        remaining inputs are recorded as ``skipped`` rather than vanishing.

    Returns
    -------
    SpotFinderRunResult
        One row per input, in input order.
    """
    from ..core.spots import detect, load_intensity
    from .models import RunRow, SpotFinderRunResult

    result = SpotFinderRunResult()
    stopped = False

    for index, file_str in enumerate(request.files):
        path = Path(file_str)
        if stopped or (should_stop is not None and should_stop()):
            stopped = True
            result.rows.append(RunRow(str(path), "skipped", reason="run cancelled"))
            continue
        if progress is not None:
            progress(index, len(request.files), path.name)

        try:
            image = load_intensity(str(path), channels=request.channels, frame=request.frame)
            found = detect(image, dataclasses.replace(request.settings))
        except Exception as exc:  # noqa: BLE001 - reported per file, never fatal
            logger.debug("detection failed for %s", path, exc_info=True)
            result.rows.append(RunRow(str(path), "failed", reason=str(exc)))
            continue

        if found.n_regions == 0:
            # Not a failure, and not nothing: a field with no spots in it is a
            # measurement with an answer, and the answer is zero.
            result.rows.append(RunRow(str(path), "empty", reason="no regions detected"))
            continue

        container = ""
        if request.write:
            try:
                container = found.write(
                    path,
                    name=request.name,
                    out_dir=request.out_dir or None,
                )
            except Exception as exc:  # noqa: BLE001 - the detection still happened
                result.rows.append(
                    RunRow(
                        str(path),
                        "failed",
                        found.n_regions,
                        reason=f"container not written ({exc})",
                    )
                )
                continue

        result.rows.append(RunRow(str(path), "ok", found.n_regions, container))
        result.n_regions += found.n_regions

    return result


def run_table(result: SpotFinderRunResult):
    """Return the run's rows as a table, for display or for a file.

    Parameters
    ----------
    result : SpotFinderRunResult
        The run, with one row per input.

    Returns
    -------
    tttrlib.DataStore
        Columns ``input``, ``status``, ``n_regions``, ``container``, ``reason``.
    """
    import numpy as np

    from chisurf.core.datastore import store_from_arrays

    rows = result.rows
    return store_from_arrays(
        {
            "input": np.asarray([r.input for r in rows], dtype=object),
            "status": np.asarray([r.status for r in rows], dtype=object),
            "n_regions": np.asarray([r.n_regions for r in rows], dtype=np.int64),
            "container": np.asarray([r.container for r in rows], dtype=object),
            "reason": np.asarray([r.reason for r in rows], dtype=object),
        }
    )
