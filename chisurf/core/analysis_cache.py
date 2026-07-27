"""Skip an analysis whose inputs and settings have not changed.

Every burst step re-ran from scratch whenever it was asked to run — and it was
asked often: the workflow shell clicks a step's Run action when you press
*Next*, and re-applies the burst folder to a panel each time you navigate to it,
which the panel takes as "a setting changed, recompute". Walking back and forth
through six steps therefore recomputed minutes of BVA, 2CDE, MLE and H2MM work
that had already been done with byte-identical inputs.

The rule this module implements is the obvious one: **a result stays valid until
one of the things that produced it changes.** "The things that produced it" are

* the input files — identified by name, size and modification time, not by
  content, so the check costs one ``stat`` per file rather than a full read, and
* every setting the computation was given.

Both are folded into one short :func:`fingerprint`. A tool keeps the fingerprint
of the result it is currently showing (:class:`ResultCache`); when a run is
requested it fingerprints the *current* inputs and settings and compares. Equal
means the result on screen is the result that run would produce, so the run is
skipped and said to be skipped. Different — a re-saved file, a changed τ, one
more burst file in the folder — means a real recompute.

Fingerprints are also written next to the outputs as a small JSON *stamp*
(:func:`write_stamp`), which records what produced those files and lets a later
session tell whether they are still current.

Notes
-----
Modification time is a deliberate choice over content hashing: burst folders
routinely hold gigabytes, and re-hashing them to decide whether to skip work
would cost more than the work. A file restored with an old timestamp and
different content is the one case this misses; a tool that must be certain can
pass ``content=True`` to :func:`file_identity`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "ResultCache",
    "file_identity",
    "fingerprint",
    "is_current",
    "outputs_present",
    "read_stamp",
    "write_stamp",
]

#: Bump when a change to this module would make old fingerprints mean something
#: different — every stamp then reads as stale, which is the safe direction.
FORMAT_VERSION = 1

_CHUNK = 1 << 20


def _json_default(value: Any) -> Any:
    """Make settings JSON-serialisable without losing what distinguishes them."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(map(str, value))
    if hasattr(value, "tolist"):  # numpy arrays and scalars
        return value.tolist()
    if hasattr(value, "__dict__"):  # dataclass-like settings objects
        return {k: v for k, v in sorted(vars(value).items()) if not k.startswith("_")}
    return str(value)


def _canonical(params: Mapping[str, Any] | None) -> str:
    """A stable text form of *params* — key order must not change the result."""
    return json.dumps(params or {}, sort_keys=True, default=_json_default)


def file_identity(path, *, content: bool = False) -> dict[str, Any]:
    """Identify one input file.

    Parameters
    ----------
    path : path-like
        The file to identify. A missing file is identified as missing rather
        than raising: its later appearance is itself a change.
    content : bool, optional
        Hash the file's bytes instead of trusting size and modification time.
        Correct in the case mtime misses (a file restored with an old
        timestamp), and far more expensive on burst-sized data.

    Returns
    -------
    dict
        ``{"path": …, "size": …, "mtime_ns": …}``, or ``{"path": …,
        "missing": True}``.
    """
    p = Path(path)
    try:
        stat = p.stat()
    except OSError:
        return {"path": str(p), "missing": True}
    if content:
        digest = hashlib.sha256()
        with open(p, "rb") as fh:
            while chunk := fh.read(_CHUNK):
                digest.update(chunk)
        return {"path": str(p), "sha256": digest.hexdigest()}
    return {"path": str(p), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def fingerprint(
    inputs: Iterable[Any] = (),
    params: Mapping[str, Any] | None = None,
    *,
    extra: str = "",
    content: bool = False,
) -> str:
    """Return a short hex fingerprint of *inputs* + *params*.

    Parameters
    ----------
    inputs : iterable of path-like, optional
        The files the computation reads. Order does not matter — the identities
        are sorted — so a differently ordered file list is not a change.
    params : mapping, optional
        Every setting the computation is given. Nested mappings, sequences,
        numpy values, ``Path``s and dataclass-like objects are all handled.
    extra : str, optional
        Anything else that changes the result but is neither a file nor a
        setting — e.g. an algorithm version.
    content : bool, optional
        Identify inputs by content hash rather than size + mtime.

    Returns
    -------
    str
        16 hex characters. Short enough to log, wide enough that a collision
        between two states of one folder is not a practical concern.
    """
    identities = sorted(
        (file_identity(p, content=content) for p in inputs),
        key=lambda d: d["path"],
    )
    payload = json.dumps(
        {
            "version": FORMAT_VERSION,
            "inputs": identities,
            "params": _canonical(params),
            "extra": extra,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def outputs_present(outputs: Sequence[Any]) -> bool:
    """True when every path in *outputs* exists (an empty list counts as absent).

    A fingerprint match alone does not mean the results are there: someone can
    delete the output folder without touching an input.
    """
    outputs = list(outputs)
    return bool(outputs) and all(Path(p).exists() for p in outputs)


def write_stamp(
    path,
    fingerprint_: str,
    *,
    params: Mapping[str, Any] | None = None,
    inputs: Iterable[Any] = (),
    outputs: Iterable[Any] = (),
    tool: str = "",
) -> None:
    """Record what produced the results next to them.

    The stamp is plain JSON and readable on its own: it answers "what settings
    and which files is this output folder the result of?" whether or not
    anything ever compares fingerprints again.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": FORMAT_VERSION,
        "tool": tool,
        "fingerprint": fingerprint_,
        "params": json.loads(_canonical(params)) if params else {},
        "inputs": [str(Path(i)) for i in inputs],
        "outputs": [str(Path(o)) for o in outputs],
    }
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_stamp(path) -> dict[str, Any] | None:
    """Return a stamp written by :func:`write_stamp`, or ``None``.

    Anything unreadable — missing, truncated, written by a newer format — reads
    as "no stamp", which makes the caller recompute. Recomputing is always safe;
    trusting a stamp that cannot be parsed is not.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != FORMAT_VERSION:
        return None
    return payload


def is_current(stamp_path, fingerprint_: str, outputs: Sequence[Any] = ()) -> bool:
    """True when a previous run's outputs are still valid for *fingerprint_*.

    Both halves are required: the stamp must record this fingerprint *and* the
    outputs it names must still be on disk.
    """
    stamp = read_stamp(stamp_path)
    if stamp is None or stamp.get("fingerprint") != fingerprint_:
        return False
    named = outputs or stamp.get("outputs") or ()
    return outputs_present(list(named))


class ResultCache:
    """The fingerprint of the result a tool is currently holding.

    Deliberately tiny: it stores no results. The tool already keeps its own
    (a dataframe, a fitted model); this only answers "is what you are holding
    what a run right now would produce?", so there is no second copy of the data
    to keep consistent.

    Examples
    --------
    >>> cache = ResultCache()
    >>> cache.matches("abc")
    False
    >>> cache.remember("abc")
    >>> cache.matches("abc")
    True
    >>> cache.invalidate()
    >>> cache.matches("abc")
    False
    """

    __slots__ = ("_fingerprint",)

    def __init__(self) -> None:
        self._fingerprint: str | None = None

    @property
    def fingerprint(self) -> str | None:
        """The fingerprint of the held result, or ``None`` if there is none."""
        return self._fingerprint

    def matches(self, fingerprint_: str) -> bool:
        """True when the held result was produced by exactly *fingerprint_*."""
        return self._fingerprint is not None and self._fingerprint == fingerprint_

    def remember(self, fingerprint_: str) -> None:
        """Record that the tool now holds the result of *fingerprint_*."""
        self._fingerprint = fingerprint_

    def invalidate(self) -> None:
        """Forget the held result — the next run recomputes.

        Call this wherever a tool drops or replaces its results by some path
        other than a run (Clear, a failed run, a new folder).
        """
        self._fingerprint = None
