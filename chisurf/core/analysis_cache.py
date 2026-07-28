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
  content, so the check costs one ``stat`` per file rather than a full read,
* every setting the computation was given,
* the ambient state a photon read silently depends on (:func:`photon_read_context`),
  and
* the code that did the computing (:func:`algorithm_tag`).

The last two exist because the first two are not enough to make "nothing
changed" true. A per-channel TAC linearisation LUT is applied inside
``staging.open_tttr`` from process-global state, so changing it changes every
micro-time an analysis sees without touching one file or one setting. And an
estimator that has been fixed since the result was written produces a different
answer from the same inputs, which is precisely what a cache must not hide.

All four are folded into one short :func:`fingerprint`. A tool keeps the
fingerprint of the result it is currently showing (:class:`ResultCache`); when a
run is requested it fingerprints the *current* state and compares. Equal means
the result on screen is the result that run would produce, so the run is skipped
and said to be skipped. Different — a re-saved file, a changed τ, one more burst
file in the folder, a rebuilt fitting library — means a real recompute.

Fingerprints are also written next to the outputs as a small JSON *stamp*
(:func:`write_stamp`), which records what produced those files and lets a later
session tell whether they are still current. A stamp holds several entries, one
per fingerprint, so two selections of the same folder do not evict each other,
and it records each output's size and modification time rather than only its
name — an output that was truncated or rewritten underneath is not current, and
existence alone cannot tell you that.

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
import importlib
import itertools
import json

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "ResultCache",
    "algorithm_tag",
    "file_identity",
    "fingerprint",
    "is_current",
    "library_version",
    "output_identities",
    "outputs_present",
    "photon_read_context",
    "read_stamp",
    "stamp_entry",
    "write_stamp",
]

#: Bump when a change to this module would make old fingerprints or old stamps
#: mean something different — every stamp then reads as stale, which is the safe
#: direction.
FORMAT_VERSION = 2

#: How many fingerprints one stamp file remembers. Enough that switching between
#: a few selections of the same folder reuses all of them, bounded so a folder
#: worked on for months does not accumulate an unbounded record.
MAX_STAMP_ENTRIES = 16

_CHUNK = 1 << 20

_nonce = itertools.count()


def _describes_itself(value: Any) -> bool:
    """Whether ``str(value)`` carries the value's state.

    Asked of the type rather than the text: a class that overrides neither
    ``__str__`` nor ``__repr__`` renders as ``<module.Class object at 0x…>``,
    which says nothing about the settings it holds and changes address every
    run. Anything that defines either one is taken at its word.
    """
    cls = type(value)
    return not (cls.__str__ is object.__str__ and cls.__repr__ is object.__repr__)


def _json_default(value: Any) -> Any:
    """Make settings JSON-serialisable without losing what distinguishes them.

    A value this cannot describe faithfully is rendered as a *nonce* — a token
    that differs on every call — so the fingerprint changes and the caller
    recomputes. The alternative, falling back to ``str``, silently collapses
    two different settings onto one text whenever the object's ``__repr__`` does
    not carry its state, which is the one failure this module must not have.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(map(str, value))
    if hasattr(value, "tolist"):  # numpy arrays and scalars
        return value.tolist()
    if hasattr(value, "__dict__"):  # dataclass-like settings objects
        return {k: v for k, v in sorted(vars(value).items()) if not k.startswith("_")}
    if not _describes_itself(value):
        return {
            "__unrepresentable__": type(value).__name__,
            "nonce": next(_nonce),
        }
    return str(value)


def _canonical(params: Mapping[str, Any] | None) -> str:
    """A stable text form of *params* — key order must not change the result."""
    return json.dumps(params or {}, sort_keys=True, default=_json_default)


def _digest(value: Any) -> str:
    """A short digest of any settings-like value."""
    return hashlib.sha256(_canonical({"v": value}).encode("utf-8")).hexdigest()[:16]


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


@lru_cache(maxsize=None)
def library_version(module_name: str) -> str:
    """Identify the installed version of a library that does the computing.

    Used by :func:`algorithm_tag` for the compiled dependencies that hold the
    estimator itself — a rebuilt ``fit2x`` or ``tttrlib`` changes the answer
    without changing one line of chisurf.

    A module without a ``__version__`` falls back to the size and modification
    time of its file, which moves when it is rebuilt. A module that cannot be
    imported is reported as absent rather than raising: fingerprinting must not
    be the thing that breaks a tool.

    Parameters
    ----------
    module_name : str
        Importable name, e.g. ``"tttrlib"``.

    Returns
    -------
    str
        A short token identifying this build. Cached: within one process the
        answer cannot change, and fingerprints are computed on every navigation.
    """
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return f"{module_name}=absent"
    version = getattr(module, "__version__", None)
    if version:
        return f"{module_name}={version}"
    origin = getattr(module, "__file__", None)
    if origin:
        ident = file_identity(origin)
        return f"{module_name}@{ident.get('size', '?')}:{ident.get('mtime_ns', '?')}"
    return f"{module_name}=unknown"


def algorithm_tag(tool: str, version: int, *libraries: str) -> str:
    """Identify the code that produces a result, for :func:`fingerprint`'s *extra*.

    Inputs and settings describe what a computation was *given*; this describes
    what did the computing. Without it a result written by a since-corrected
    estimator reads as current forever, and the status line asserts as much.

    Parameters
    ----------
    tool : str
        The step's name, e.g. ``"burst_mle"``.
    version : int
        The tool's own ``ALGORITHM_VERSION`` — bump it in the same change that
        alters what the tool computes.
    *libraries : str
        Importable names of the libraries that hold the estimator, resolved
        through :func:`library_version`.

    Returns
    -------
    str
        e.g. ``"burst_mle/v1|fit2x=0.9.4|tttrlib=0.25.3"``.
    """
    parts = [f"{tool}/v{int(version)}"]
    parts.extend(library_version(name) for name in libraries)
    return "|".join(parts)


def photon_read_context() -> dict[str, Any]:
    """Describe the ambient state that changes what a photon read returns.

    ``staging.open_tttr`` consults process-global state for per-channel TAC
    linearisation LUTs and micro-time shifts whenever the caller does not pass
    its own. Nothing in a tool's settings mentions them, so switching setup
    changes every micro-time an analysis sees while its fingerprint stands
    still. Folding this into ``params`` is what stops that being silent.

    Returns
    -------
    dict
        Digests rather than the arrays themselves — a LUT is one value per
        micro-time channel per detector, and a fingerprint should stay cheap.
        ``{"available": False}`` when the correction subsystem is not importable,
        which is itself a stable state.
    """
    try:
        from chisurf.core.fio.lut_context import get_active_setup_lut
        from chisurf.core.fio.staging import LUT_DITHER_SEED
    except Exception:
        return {"available": False}
    try:
        luts, shifts, apply_lut = get_active_setup_lut()
    except Exception:
        return {"available": False}
    context: dict[str, Any] = {
        "apply_lut": bool(apply_lut),
        # Shifts are applied independently of the LUT gate, so they count even
        # when linearisation is off.
        "shifts": _digest(shifts),
    }
    if apply_lut:
        context["luts"] = _digest(luts)
        context["dither_seed"] = int(LUT_DITHER_SEED)
    return context


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
        setting — in practice :func:`algorithm_tag`.
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


def output_identities(outputs: Iterable[Any]) -> list[dict[str, Any]]:
    """Identify each produced file, so a later run can tell it is untouched."""
    return sorted(
        (file_identity(p) for p in outputs),
        key=lambda d: d["path"],
    )


def outputs_present(outputs: Sequence[Any]) -> bool:
    """True when every path in *outputs* exists (an empty list counts as absent).

    A fingerprint match alone does not mean the results are there: someone can
    delete the output folder without touching an input.
    """
    outputs = list(outputs)
    return bool(outputs) and all(Path(p).exists() for p in outputs)


def outputs_unchanged(identities: Sequence[Mapping[str, Any]]) -> bool:
    """True when every recorded output is still exactly as it was written.

    Existence is not enough. A result opened and re-saved by another tool, a
    truncated write, a file replaced by a copy of a different run — all leave
    the path in place while the contents stop being the ones the fingerprint
    describes.
    """
    identities = list(identities)
    if not identities:
        return False
    for recorded in identities:
        path = recorded.get("path")
        if not path:
            return False
        current = file_identity(path)
        if current.get("missing"):
            return False
        for key in ("size", "mtime_ns", "sha256"):
            if key in recorded and recorded[key] != current.get(key):
                return False
    return True


def _empty_stamp(tool: str = "") -> dict[str, Any]:
    return {
        "format": "chisurf-analysis-stamp",
        "version": FORMAT_VERSION,
        "tool": tool,
        "entries": [],
    }


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

    Entries accumulate, newest first and capped at :data:`MAX_STAMP_ENTRIES`, so
    a folder analysed with two selections of burst files remembers both and
    switching between them reuses both. Writing the same fingerprint twice
    replaces its entry rather than duplicating it.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    payload = read_stamp(p) or _empty_stamp(tool)
    if tool:
        payload["tool"] = tool

    entry = {
        "fingerprint": fingerprint_,
        "tool": tool,
        "params": json.loads(_canonical(params)) if params else {},
        "inputs": [str(Path(i)) for i in inputs],
        "outputs": output_identities(outputs),
    }
    entries = [e for e in payload.get("entries", []) if e.get("fingerprint") != fingerprint_]
    payload["entries"] = [entry, *entries][:MAX_STAMP_ENTRIES]

    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def read_stamp(path) -> dict[str, Any] | None:
    """Return a stamp written by :func:`write_stamp`, or ``None``.

    Anything unreadable — missing, truncated, written by a newer or older format
    — reads as "no stamp", which makes the caller recompute. Recomputing is
    always safe; trusting a stamp that cannot be parsed is not.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != FORMAT_VERSION:
        return None
    if not isinstance(payload.get("entries"), list):
        return None
    return payload


def stamp_entry(path, fingerprint_: str) -> dict[str, Any] | None:
    """Return the stamp entry recorded for *fingerprint_*, or ``None``."""
    payload = read_stamp(path)
    if payload is None:
        return None
    for entry in payload["entries"]:
        if isinstance(entry, dict) and entry.get("fingerprint") == fingerprint_:
            return entry
    return None


def is_current(stamp_path, fingerprint_: str, outputs: Sequence[Any] = ()) -> bool:
    """True when a previous run's outputs are still valid for *fingerprint_*.

    Both halves are required: the stamp must record this fingerprint *and* the
    outputs it named must still be on disk, unmodified since they were written.
    """
    entry = stamp_entry(stamp_path, fingerprint_)
    if entry is None:
        return False
    if outputs and not outputs_present(list(outputs)):
        return False
    return outputs_unchanged(entry.get("outputs") or ())


class ResultCache:
    """The fingerprint of the result a tool is currently holding.

    Deliberately tiny: it stores no results. The tool already keeps its own
    (a dataframe, a fitted model); this only answers "is what you are holding
    what a run right now would produce?", so there is no second copy of the data
    to keep consistent.

    It also remembers a fingerprint the user *stopped*, which is a different
    state from both "held" and "unknown": a stopped run computed part of an
    answer, so it must not be reused, and it must not silently start again
    either when the step is opened for the second time.

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

    __slots__ = ("_fingerprint", "_abandoned")

    def __init__(self) -> None:
        self._fingerprint: str | None = None
        self._abandoned: str | None = None

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
        self._abandoned = None

    def invalidate(self) -> None:
        """Forget the held result — the next run recomputes.

        Call this wherever a tool drops or replaces its results by some path
        other than a run (Clear, a failed run, a new folder).
        """
        self._fingerprint = None

    def abandon(self, fingerprint_: str | None) -> None:
        """Record that the user stopped the run for *fingerprint_*.

        The partial result is dropped, and the same computation will not start
        by itself again — see :meth:`was_abandoned`. Any change to the inputs or
        the settings gives a different fingerprint, which is not abandoned, so
        stopping suppresses exactly the run that was stopped and nothing else.
        """
        self._fingerprint = None
        self._abandoned = fingerprint_

    def was_abandoned(self, fingerprint_: str) -> bool:
        """True when the user stopped exactly this computation."""
        return self._abandoned is not None and self._abandoned == fingerprint_

    def allow(self) -> None:
        """Forget any abandonment — an explicit Run means the user wants it."""
        self._abandoned = None
