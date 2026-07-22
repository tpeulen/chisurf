"""Reusable MMFDB "select a dataset" helper, shared by every file picker.

Historically each file-drop widget grew its own copy of the MMFDB flow: build
an in-process client, open :class:`MmfdbDatasetPickerDialog`, then turn the
chosen artifact into a local path with ``mmfdb.datasets.open``. This module is
that flow, once, so any file selector — most importantly the general
``path_list`` AutoForm section — can offer "select from the database" without
re-implementing it.

The database is the single place S3 is handled: an MMFDB whose object store is
configured with ``object_store.backend = "s3"`` (see ``mmfdb.config``) fetches
the blob from its S3 endpoint and returns a *local* path from
``mmfdb.datasets.open``. Callers therefore get a local file whether the dataset
lives on disk or on an S3-compatible endpoint, with no S3 code of their own.
"""

from __future__ import annotations

import logging
import typing
from pathlib import Path

logger = logging.getLogger(__name__)

#: Artifact kinds a raw-data file selector should browse by default.
DEFAULT_KINDS = ["raw_data", "raw_measurement", "external_reference"]

#: Process-wide MMFDB client, so every file selector shares one session rather
#: than each starting its own embedded server. This mirrors the token cache in
#: ``mmfdb_admin.gui.session`` (reuse the login across the process); here it is
#: the *client* that is shared. Reset with :func:`reset_session_client`.
_SESSION_CLIENT: typing.Any = None
_SESSION_CLIENT_FAILED = False


def inprocess_client() -> typing.Any:
    """Return the shared, process-global MMFDB client, or ``None`` if unavailable.

    Constructing the embedded client starts MMFDB, so it is built lazily (on the
    first "from database" click) and then reused by every subsequent file
    selector — one global session, not one per widget. A failure (MMFDB not
    installed, database not initialised) is remembered so repeated clicks don't
    retry the expensive construction; the selector simply reports no database.
    """
    global _SESSION_CLIENT, _SESSION_CLIENT_FAILED
    if _SESSION_CLIENT is not None:
        return _SESSION_CLIENT
    if _SESSION_CLIENT_FAILED:
        return None
    try:
        from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient

        client = MMFDBClient(inprocess=True)
        _authenticate(client)
        _SESSION_CLIENT = client
        return _SESSION_CLIENT
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.info("MMFDB in-process client unavailable: %s", exc)
        _SESSION_CLIENT_FAILED = True
        return None


def _authenticate(client: typing.Any) -> None:
    """Adopt the MMFDB session established at ChiSurf login — no login here.

    The session is owned by the application's login flow; this picker only
    *reuses* the token it produced (the same adapter :func:`chisurf.core.transform
    .mmfdb.runtime_session_for_database` uses), with the process token cache in
    ``mmfdb_admin.gui.session`` as a fallback. It never prompts, logs in, or sends
    default credentials. If the user is not logged in, the client stays
    unauthenticated and the dataset browser simply shows nothing until they log in.
    """
    if getattr(client, "token", None):
        return
    host = getattr(client, "host", "127.0.0.1")
    cmd = getattr(client, "cmd_port", 8765)
    pub = getattr(client, "pub_port", 8766)

    token = None
    try:
        import chisurf.core.settings as cs_settings
        from mmfdb.security.credentials import load_runtime_session_token

        config = cs_settings.cs_settings.get("mmfdb", {})
        server_host = str(config.get("last_server", host))
        server_port = int(config.get("last_port", cmd))
        user_id = str(config.get("default_user_id", ""))
        if user_id:
            token = load_runtime_session_token(server_host, server_port, user_id)
    except Exception:
        token = None

    if not token:
        try:
            from chisurf.plugins.core.mmfdb_admin.gui.session import cached_token

            token = cached_token(host, cmd, pub)
        except Exception:
            token = None

    if token:
        try:
            client.token = token
        except Exception:
            pass


def reset_session_client() -> None:
    """Forget the shared MMFDB client so the next call rebuilds it.

    Use after a logout or a database switch, when the cached session no longer
    reflects the connection callers should use.
    """
    global _SESSION_CLIENT, _SESSION_CLIENT_FAILED
    _SESSION_CLIENT = None
    _SESSION_CLIENT_FAILED = False


def resolve_local_path(client: typing.Any, selection: typing.Any) -> typing.Optional[str]:
    """Resolve a picked dataset to a local file path.

    Uses the selection's own ``local_path`` when the picker already resolved it,
    otherwise asks the service via ``mmfdb.datasets.open`` — the step that pulls
    the blob from the object store (local *or* S3) and hands back a local path.
    """
    local = getattr(selection, "local_path", None)
    if local:
        return str(local)
    artifact_id = getattr(selection, "artifact_id", None)
    if not artifact_id:
        return None
    result = client.call("mmfdb.datasets.open", {"artifact_id": artifact_id}) or {}
    return result.get("local_path") or result.get("path")


def pick_local_paths(
    parent: typing.Any = None,
    *,
    kinds: typing.Optional[typing.Sequence[str]] = None,
    scope: str = "all",
    client: typing.Any = None,
) -> typing.List[Path]:
    """Open the MMFDB dataset picker and return the chosen local path(s).

    Returns an empty list when MMFDB is unavailable, the user cancels, or the
    selection cannot be resolved to a local path — callers can therefore treat
    "nothing came back" uniformly without catching exceptions.
    """
    from chisurf.gui.widgets.mmfdb.dataset_browser import MmfdbDatasetPickerDialog

    if client is None:
        client = inprocess_client()
    if client is None:
        return []
    selection = MmfdbDatasetPickerDialog.pick_dataset(
        parent=parent,
        kinds=list(kinds) if kinds is not None else list(DEFAULT_KINDS),
        scope=scope,
        client=client,
    )
    if selection is None:
        return []
    local_path = resolve_local_path(client, selection)
    if not local_path:
        return []
    return [Path(local_path)]


__all__ = [
    "DEFAULT_KINDS",
    "inprocess_client",
    "reset_session_client",
    "resolve_local_path",
    "pick_local_paths",
]
