"""The mmCIF dictionaries ChiSurf writes its terms and units against, parsed once.

Units (:mod:`chisurf.core.support.units`) and the container vocabulary (:mod:`chisurf.core.fio.pto`)
both read the bundled plus export-only dictionaries. Each parsed them itself -- about a second
apiece, paid on the first burst search of every session. :func:`dictionary` parses them once per
process and keeps the parse on disk (``<settings>/cache/vocabulary-<key>.pickle``), keyed by the
dictionary files' paths, sizes and modification times, so an edited ``.dic`` is parsed again and an
unchanged one loads in a few tens of milliseconds.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def _paths() -> list[Path]:
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    return [
        Path(MmcifDictionary._resolve_dic(name))
        for name in (*MmcifDictionary.BUNDLED_DICTS, *MmcifDictionary.EXPORT_ONLY_DICTS)
    ]


def _key(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        stat = path.stat()
        digest.update(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns};".encode())
    return digest.hexdigest()[:20]


def _cache_file(key: str) -> Path | None:
    try:
        from chisurf.core.settings.path_utils import get_path

        folder = get_path("settings") / "cache"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"vocabulary-{key}.pickle"
    except Exception:  # noqa: BLE001 - no settings folder: parse every session
        return None


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
    if cache is not None and cache.is_file():
        try:
            with cache.open("rb") as stream:
                parsed = pickle.load(stream)
            if isinstance(parsed, MmcifDictionary):
                return parsed
        except Exception:  # noqa: BLE001 - a stale or broken cache is parsed again
            _log.debug("vocabulary cache %s unreadable; parsing", cache)
    parsed = MmcifDictionary(*paths)
    if cache is not None:
        try:
            with tempfile.NamedTemporaryFile("wb", dir=cache.parent, delete=False) as stream:
                pickle.dump(parsed, stream, protocol=pickle.HIGHEST_PROTOCOL)
                temporary = stream.name
            os.replace(temporary, cache)
            for old in cache.parent.glob("vocabulary-*.pickle"):
                if old != cache:
                    old.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 - caching is an optimisation
            _log.debug("vocabulary cache %s not written", cache)
    return parsed
