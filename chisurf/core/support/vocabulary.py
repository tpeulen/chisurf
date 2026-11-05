"""The mmCIF dictionaries ChiSurf writes its terms and units against, parsed once.

Units (:mod:`chisurf.core.support.units`) and the container vocabulary (:mod:`chisurf.core.fio.pto`)
both read the bundled plus export-only dictionaries (~21 MB of ``.dic``; 1.3 s to parse on an M-series
laptop, 10.8 s under cProfile). :func:`dictionary` parses them once per process and keeps the parse
on disk, so the parse is paid once per *machine* and dictionary edition rather than once per session:

* **Keyed on content.** The key is a hash of the dictionary files' bytes, the parser's own source
  and the Python version -- not of paths or modification times. An edited ``.dic`` (or parser) is
  parsed again; a re-checkout, a copy, a second worktree or a touched file with the same bytes is
  not.
* **One shared user cache**, not one per settings folder: ``$CHISURF_CACHE_DIR``, else the
  platform's user cache (``~/Library/Caches/chisurf`` on macOS, ``$XDG_CACHE_HOME/chisurf`` or
  ``~/.cache/chisurf`` on Linux, ``%LOCALAPPDATA%\\chisurf\\Cache`` on Windows). A fresh settings
  folder -- every hermetic test, benchmark and batch worker -- finds the parse already there.
* **Safe under concurrent writers.** A process writes its own temporary file in the cache folder and
  renames it over the cache (``os.replace``, atomic on one file system): a reader sees the old file
  or the whole new one, never a partial write, and writers racing on one key write the same bytes.
  A cache that does not load (truncated by a crash, another Python) is parsed and replaced.
* Caches of other keys are left to their checkouts and removed only once unused for
  :data:`STALE_DAYS` days, so two worktrees on different dictionaries do not evict each other.

``python -m chisurf.core.support.vocabulary`` builds the cache ahead of time (a batch launcher can
run it before spawning workers) and prints where it is.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import os
import pickle
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

#: Bumped when what is pickled changes shape in a way the parser's source hash would not show.
CACHE_FORMAT = 2
#: A cache of another key is deleted once it has not been used for this long.
STALE_DAYS = 30.0


def _paths() -> list[Path]:
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    return [
        Path(MmcifDictionary._resolve_dic(name))
        for name in (*MmcifDictionary.BUNDLED_DICTS, *MmcifDictionary.EXPORT_ONLY_DICTS)
    ]


def _parser_source() -> bytes:
    """The parser module's source: a changed parser makes a different parse of the same files."""
    from mmfdb.schema import pdbx_metadata

    try:
        return Path(pdbx_metadata.__file__).read_bytes()
    except (OSError, TypeError):  # frozen / zipped: fall back to the package's version
        return str(getattr(sys.modules.get("mmfdb"), "__version__", "")).encode()


def _key(paths: list[Path]) -> str:
    """Content key of a parse of *paths*: their names and bytes, the parser, the Python."""
    digest = hashlib.sha256()
    digest.update(f"format {CACHE_FORMAT}|python {sys.version_info[0]}.{sys.version_info[1]};".encode())
    digest.update(hashlib.sha256(_parser_source()).digest())
    for path in paths:
        digest.update(f"{path.name}|".encode())
        try:
            with path.open("rb") as stream:
                digest.update(hashlib.file_digest(stream, "sha256").digest()
                              if hasattr(hashlib, "file_digest")
                              else hashlib.sha256(stream.read()).digest())
        except OSError:
            digest.update(b"<missing>")  # the parser skips a missing file; so does the key
        digest.update(b";")
    return digest.hexdigest()[:24]


def cache_dir() -> Path:
    """The per-user folder the parse is kept in (see the module docstring)."""
    override = os.environ.get("CHISURF_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "chisurf"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / "chisurf" / "Cache"
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else home / ".cache") / "chisurf"


def _cache_file(key: str) -> Path | None:
    try:
        folder = cache_dir()
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"vocabulary-{key}.pickle"
    except OSError:  # no writable cache folder: parse every session
        return None


def _load(cache: Path, kind: type) -> Any | None:
    try:
        with cache.open("rb") as stream:
            parsed = pickle.load(stream)
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - truncated, another Python, a moved class: parse again
        _log.debug("vocabulary cache %s unreadable; parsing", cache)
        return None
    if not isinstance(parsed, kind):
        return None
    try:
        os.utime(cache)  # used: keeps it off the stale list of other checkouts
    except OSError:
        pass
    return parsed


def _store(cache: Path, parsed: Any) -> None:
    """Write *parsed* to *cache* atomically: a private temporary file, then one rename."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=cache.parent, prefix=cache.stem + ".", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            pickle.dump(parsed, stream, protocol=pickle.HIGHEST_PROTOCOL)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, cache)
        temporary = None
    except Exception:  # noqa: BLE001 - caching is an optimisation
        _log.debug("vocabulary cache %s not written", cache)
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    _prune(cache)


def _prune(keep: Path) -> None:
    """Delete caches (and orphaned temporary files) nobody has used for :data:`STALE_DAYS`."""
    cutoff = time.time() - STALE_DAYS * 86400.0
    for pattern in ("vocabulary-*.pickle", "vocabulary-*.tmp"):
        for old in keep.parent.glob(pattern):
            if old == keep:
                continue
            try:
                if old.stat().st_mtime < cutoff:
                    old.unlink()
            except OSError:
                pass


@functools.lru_cache(maxsize=1)
def dictionary() -> Any:
    """The parsed bundled + export-only mmCIF dictionaries (``mmfdb``'s ``MmcifDictionary``).

    Returns
    -------
    mmfdb.schema.pdbx_metadata.MmcifDictionary
        Shared: callers read it, never change it.
    """
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    paths = _paths()
    cache = _cache_file(_key(paths))
    if cache is not None:
        parsed = _load(cache, MmcifDictionary)
        if parsed is not None:
            return parsed
    parsed = MmcifDictionary(*paths)
    if cache is not None:
        _store(cache, parsed)
    return parsed


def main() -> int:
    """Build (or confirm) the cache and say where it is and what it cost."""
    t0 = time.perf_counter()
    dictionary()
    elapsed = time.perf_counter() - t0
    print(f"{_cache_file(_key(_paths()))}  ({elapsed:.2f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
