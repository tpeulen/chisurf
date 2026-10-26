"""Links to objects of an MMFDB server: ``mmfdb://artifact/<id>`` (optionally ``?server=<host>``).

A project may link a measurement that lives in an MMFDB database instead of a local file (owner
directive 2026-10-26, ``okf/specs/data-workspace.md`` "Remote link targets"). The link records the
URI, the object's size and sha256 -- never credentials -- and resolves in two phases, the same on the
desktop and in the browser (:mod:`mmfdb.links`):

1. :func:`prefetch` fetches the linked objects into MMFDB's link cache (keyed by sha256) -- on the
   desktop with the user's session token, in the browser with the server's session cookie; a link
   whose server has no session is reported as *sign-in needed* (:data:`SIGN_IN`), not as missing;
2. :func:`resolve_remote` only reads that cache: a cached object of the recorded size resolves to its
   local path, anything else is *fetching* (not fetched yet) or the reason the last prefetch gave.

ptolib/tttrlib read an ``mmfdb://`` link target through the cache-only resolver
:func:`register_resolvers` registers at startup (where the installed tttrlib has the registry). Every
call here is guarded: without :mod:`mmfdb` nothing is registered and a remote link stays *fetching*.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

__all__ = [
    "FETCHING",
    "SCHEME",
    "SIGN_IN",
    "find_copies",
    "is_remote",
    "link_for",
    "prefetch",
    "prefetch_async",
    "register_resolvers",
    "resolve_remote",
    "server_of",
    "state",
]

_log = logging.getLogger(__name__)

SCHEME = "mmfdb://"
#: Status of a remote link whose object is not in the cache yet.
FETCHING = "fetching"
#: Status of a remote link whose server has no session for this user.
SIGN_IN = "sign-in needed"

#: The last prefetch outcome per URI: ``(status, reason)``; ``status`` is ``"ok"``, :data:`SIGN_IN`
#: or ``"missing"`` (the server refused or has no such object).
_STATE: dict[str, tuple[str, str]] = {}


def _mmfdb_links() -> Any:
    """:mod:`mmfdb.links` (``ImportError`` without it); imported by its module path, so a blocked
    module is honoured even when the :mod:`mmfdb` package is loaded."""
    import importlib

    return importlib.import_module("mmfdb.links")


def is_remote(link_or_address: Any) -> bool:
    """Whether *link_or_address* (a link record or an address string) points at an MMFDB object."""
    if isinstance(link_or_address, dict):
        return str(link_or_address.get("uri") or "").startswith(SCHEME)
    return str(link_or_address or "").startswith(SCHEME)


def link_for(uri: str, *, size: int, sha256: str, name: str = "") -> dict[str, Any]:
    """The link record of an MMFDB object: its URI, size and sha256 (from the artifact's metadata).

    No credentials and no local path are recorded; the object is checked against the size and hash
    after every fetch, exactly like a linked file.
    """
    from chisurf.core.project.links import LINK_SCHEME, LinkError

    if not is_remote(uri):
        raise LinkError(f"not an MMFDB address: {uri!r}")
    sha = str(sha256 or "").strip().lower().removeprefix("sha256:")
    if len(sha) != 64 or int(size) < 0:
        raise LinkError(f"{uri}: an MMFDB link needs the object's size and sha256")
    return {
        "scheme": LINK_SCHEME,
        "uri": str(uri),
        "container": "",
        "member": "",
        "name": name or str(uri).rsplit("/", 1)[-1].split("?", 1)[0],
        "size": int(size),
        "sha256": sha,
        "companions": [],
    }


def server_of(uri: str) -> str:
    """The server a link's object is fetched from: its ``?server=``, or the configured MMFDB server."""
    try:
        from mmfdb.links import parse_link_uri

        target = parse_link_uri(str(uri))
        if target.server:
            return target.server
        from mmfdb.config import ClientConfig, ConfigError, load_client_config

        try:
            return load_client_config().base_url
        except ConfigError:
            return ClientConfig().base_url
    except Exception:  # noqa: BLE001 - only used for the message
        return ""


def state(uri: str) -> tuple[str, str] | None:
    """The last prefetch outcome of *uri*, ``(status, reason)``, or ``None`` before any."""
    return _STATE.get(str(uri))


def _cache_path(link: dict[str, Any]) -> Path | None:
    try:
        cache = _mmfdb_links().LinkCache()
    except ImportError:
        return None
    try:
        return cache.get(str(link.get("sha256") or ""))
    except Exception:  # noqa: BLE001 - an unreadable cache is "not fetched"
        return None


def resolve_remote(link: dict[str, Any], *, check_hash: bool = False):
    """Resolve an ``mmfdb://`` link from the cache only (never the network).

    Returns a :class:`chisurf.core.project.links.Resolution`: ``"ok"`` with the cached file's path,
    :data:`SIGN_IN` or ``"missing"`` from the last prefetch, else :data:`FETCHING`.
    """
    from chisurf.core.project.links import Resolution, file_digest

    uri = str(link.get("uri", ""))
    cached = _cache_path(link)
    if cached is not None and cached.is_file():
        size = cached.stat().st_size
        if size != int(link.get("size", -1)):
            return Resolution(
                "size changed",
                None,
                cached,
                f"the cached copy of {uri} is {size} bytes, the link recorded {link.get('size')}",
            )
        if check_hash and file_digest(cached)[1] != link.get("sha256"):
            return Resolution("hash changed", None, cached, f"the cached copy of {uri} differs")
        return Resolution("ok", str(cached), cached)
    last = _STATE.get(uri)
    if last is not None and last[0] in (SIGN_IN, "missing"):
        return Resolution(last[0], None, None, last[1])
    return Resolution(FETCHING, None, None, f"fetching {uri}…")


def _classify(uri: str, error: str) -> tuple[str, str]:
    text = str(error)
    if "no MMFDB session" in text or "401" in text or "log in" in text:
        server = server_of(uri) or "the MMFDB server"
        return SIGN_IN, f"sign-in needed for {server}"
    return "missing", f"{uri}: {text}"


def _record(results: list[Any]) -> dict[str, tuple[str, str]]:
    out = {}
    for result in results:
        if result.ok:
            outcome = ("ok", "")
        else:
            outcome = _classify(result.uri, result.error)
        _STATE[result.uri] = outcome
        out[result.uri] = outcome
    return out


def _items(links: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(str(link["uri"]), str(link.get("sha256", ""))) for link in links if is_remote(link)]


def prefetch(links: list[dict[str, Any]], progress=None, **kwargs) -> dict[str, tuple[str, str]]:
    """Fetch the ``mmfdb://`` links among *links* into the cache (desktop; blocks per object).

    *progress* is called with ``(done, total)`` after each object. Returns ``{uri: (status,
    reason)}`` and remembers it for :func:`resolve_remote`. Without :mod:`mmfdb`, nothing is
    fetched and the links stay *fetching*.
    """
    items = _items(links)
    try:
        mmfdb_links = _mmfdb_links()
    except ImportError:
        return {}
    out: dict[str, tuple[str, str]] = {}
    for done, item in enumerate(items, start=1):
        try:
            results = mmfdb_links.prefetch([item], **kwargs)
        except Exception as exc:  # noqa: BLE001 - one object's failure is that object's
            results = [mmfdb_links.PrefetchResult(item[0], item[1], error=str(exc))]
        out.update(_record(results))
        if progress is not None:
            progress(done, len(items))
    return out


async def prefetch_async(links: list[dict[str, Any]], **kwargs) -> dict[str, tuple[str, str]]:
    """:func:`prefetch` for the browser build, where fetching must be awaited (Pyodide)."""
    items = _items(links)
    try:
        mmfdb_links = _mmfdb_links()
    except ImportError:
        return {}
    results = await mmfdb_links.prefetch_async(items, **kwargs)
    return _record(results)


def _drive(coro: Any) -> Any:
    """Run a coroutine that never suspends (the desktop transport is synchronous)."""
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    coro.close()
    raise RuntimeError("the MMFDB transport suspended; this needs the page's event loop")


def find_copies(sha256: str, *, transport: Any = None, limit: int = 5) -> list[dict[str, str]]:
    """MMFDB objects whose content has *sha256* -- copies a missing linked file can be read from.

    MMFDB's store is content-addressed, so any object with the link's checksum is that file. Returns
    ``[{"uri": "mmfdb://object/<uuid>", "object_uuid": ..., "name": ..., "server": ...}]``; an empty
    list without :mod:`mmfdb`, without a session, or when the server has none.
    """
    sha = str(sha256 or "").strip().lower()
    if len(sha) != 64:
        return []
    try:
        mmfdb_links = _mmfdb_links()
    except ImportError:
        return []
    try:
        server = transport or mmfdb_links.default_transport()
        found = _drive(
            server.rpc(mmfdb_links.RPC_OBJECT_LIST, {"content_sha256": sha, "limit": limit})
        )
    except Exception as exc:  # noqa: BLE001 - no session, no server: no copies
        _log.debug("MMFDB copy search failed: %s", exc)
        return []
    base = str(getattr(server, "base_url", "") or "")
    out = []
    for obj in (found or {}).get("objects") or ():
        uuid = str(obj.get("object_uuid") or "")
        if not uuid or str(obj.get("content_sha256") or sha).lower() != sha:
            continue
        out.append(
            {
                "uri": f"mmfdb://object/{uuid}",
                "object_uuid": uuid,
                "name": str(obj.get("original_filename") or uuid),
                "server": base,
            }
        )
    return out


def register_resolvers() -> list[str]:
    """Register MMFDB's cache-only resolver for ``mmfdb://`` with ptolib/tttrlib, where they have one.

    Quietly does nothing without :mod:`mmfdb` or with a tttrlib that has no link-resolver registry
    (the remote link then resolves through :func:`resolve_remote` in ChiSurf only).
    """
    try:
        mmfdb_links = _mmfdb_links()
    except ImportError:
        return []
    try:
        return list(mmfdb_links.register())
    except Exception as exc:  # noqa: BLE001 - never fail startup over an optional resolver
        _log.debug("mmfdb link resolver not registered: %s", exc)
        return []
