"""Fetching bytes from a URL, on whichever host is running.

``fetch 1crn`` is one command, and it must stay one command. What differs
between a desktop and a page is not what fetching *means* but what performs it:
a desktop opens a socket, and a browser tab has none -- Pyodide's ``urllib``
raises rather than connecting, so the shared command failed in the page with a
message about sockets that says nothing about PDB entries.

So the transport is the seam, the way buttons and keys are:
:func:`download` is one function with two implementations, and the command layer
above it does not branch.

What a page can and cannot reach
--------------------------------
A page reads a URL through the browser, so the **server** decides. RCSB serves
``Access-Control-Allow-Origin: *`` and can be read; a mirror that does not send
that header cannot be, and the browser tells the page only that the request
failed. That is why :func:`download` names the URL in its error: it is the only
information the caller can be given.
"""
from __future__ import annotations

__all__ = ["IN_BROWSER", "download"]


def _in_browser() -> bool:
    """Whether this interpreter is Pyodide inside a page."""
    try:
        import pyodide  # noqa: F401,PLC0415
    except ImportError:
        return False
    return True


#: Resolved once. The answer cannot change within a process.
IN_BROWSER = _in_browser()


def download(url: str, timeout: float = 60.0) -> bytes:
    """Return the bytes at *url*.

    Parameters
    ----------
    url : str
        An ``http`` or ``https`` URL.
    timeout : float
        Seconds to wait, on hosts that can be told to wait. A browser's
        ``XMLHttpRequest`` in synchronous mode takes no timeout, so the value is
        ignored there rather than pretended about.

    Returns
    -------
    bytes

    Raises
    ------
    OSError
        Naming the URL. Every caller reports this to a user who typed an
        accession, and "could not reach <url>" is the most that can honestly be
        said in a page.

    Notes
    -----
    Synchronous, deliberately, on both hosts. The engine is synchronous by
    construction -- the browser's one asynchronous step, resolving the GPU
    device, happens in the loader before any engine code runs -- and making a
    command a coroutine would make every caller of it one too.
    """
    if IN_BROWSER:
        from pyodide.http import open_url  # type: ignore[import-not-found]

        try:
            return open_url(url).read().encode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - a page gets no detail
            raise OSError(f"could not fetch {url}: {exc}") from None

    import urllib.request

    from ..cmd.loader import _tls_context

    with urllib.request.urlopen(
        url, timeout=timeout, context=_tls_context()
    ) as response:
        return response.read()
