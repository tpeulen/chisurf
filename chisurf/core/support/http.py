"""A small HTTP client over the standard library.

Everything ChiSurf sends over HTTP is one JSON round trip: a model provider's
``/chat/completions``, a plugin registry's file listing, an icon download. That
is ``urllib.request`` plus a response wrapper, so it lives here instead of
pulling in a third-party client -- which, being undeclared, was installed on
every developer machine and in no packaged install.

The surface deliberately mirrors the well-known one, because the call sites were
written against it: :func:`get` / :func:`post` take ``headers``, ``json``,
``params`` and ``timeout``, and return a :class:`Response` with ``status_code``,
``text``, ``content``, ``json()`` and ``raise_for_status()``. As there, a 4xx or
5xx is a *returned* response, not an exception -- only a transport failure
(no route, TLS, timeout) raises, and it raises :class:`RequestError`.

What is intentionally absent: sessions and connection pooling, streaming
responses, multipart uploads, automatic retries. Nothing here needs them; code
that does should say so rather than grow this module by accident.

Examples
--------
>>> response = post(                                    # doctest: +SKIP
...     "https://openrouter.ai/api/v1/chat/completions",
...     headers={"Authorization": f"Bearer {key}"},
...     json={"model": model, "messages": messages},
...     timeout=60,
... )
>>> response.raise_for_status()                          # doctest: +SKIP
>>> reply = response.json()["choices"][0]["message"]     # doctest: +SKIP
"""

from __future__ import annotations

import json as _json
import typing
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["Headers", "Response", "RequestError", "HTTPStatusError", "request", "get", "post"]

#: Sent when the caller does not set one; some APIs reject the urllib default.
USER_AGENT = "chisurf"

#: The only schemes this client speaks. ``urlopen`` serves every scheme urllib
#: has a handler for -- ``file:`` reads off the local disk, ``ftp:`` dials out --
#: and the URLs reaching here come from model providers and plugin registries,
#: so anything but HTTP is refused before the request is opened.
ALLOWED_SCHEMES = frozenset({"http", "https"})


class RequestError(OSError):
    """The request never produced a response (DNS, TLS, timeout, refused)."""


class HTTPStatusError(RequestError):
    """The response carried an error status and the caller asked to raise.

    Parameters
    ----------
    response : Response
        The response that failed; kept so handlers can read the body.
    """

    def __init__(self, response: Response):
        self.response = response
        super().__init__(f"{response.status_code} for {response.url}: {response.text[:300]}")


class Headers(dict):
    """Response headers, looked up without regard to case.

    HTTP header names are case-insensitive and servers disagree about spelling
    (``Retry-After`` / ``retry-after``), so a plain dict lookup is a coin flip.
    Iteration and ``repr`` keep the sender's spelling.
    """

    def __init__(self, source=None):
        super().__init__(source or {})
        self._folded = {key.lower(): key for key in self}

    def __getitem__(self, key):
        """Return the value for *key*, ignoring case."""
        return super().__getitem__(self._folded.get(key.lower(), key))

    def __contains__(self, key):
        """Return whether *key* is present, ignoring case."""
        return key.lower() in self._folded

    def get(self, key, default=None):
        """Return the value for *key*, ignoring case, or *default*."""
        try:
            return self[key]
        except KeyError:
            return default


class Response:
    """An HTTP response.

    Parameters
    ----------
    status_code : int
        HTTP status of the response.
    headers : Headers
        Response headers; lookups ignore case.
    content : bytes
        Raw response body.
    url : str
        The URL that produced this response.
    """

    def __init__(self, status_code: int, headers, content: bytes, url: str):
        self.status_code = status_code
        self.headers = Headers(headers)
        self.content = content
        self.url = url

    @property
    def ok(self) -> bool:
        """Whether the status is not an error (``< 400``)."""
        return self.status_code < 400

    @property
    def encoding(self) -> str:
        """Character set from the ``Content-Type`` header, defaulting to UTF-8."""
        content_type = self.headers.get("Content-Type", "")
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("charset="):
                return part.split("=", 1)[1].strip('"') or "utf-8"
        return "utf-8"

    @property
    def text(self) -> str:
        """The body decoded as text; undecodable bytes are replaced, never raised."""
        return self.content.decode(self.encoding, errors="replace")

    def json(self) -> typing.Any:
        """Parse the body as JSON.

        Returns
        -------
        object
            Whatever the body decodes to.

        Raises
        ------
        json.JSONDecodeError
            If the body is not JSON.
        """
        return _json.loads(self.text)

    def raise_for_status(self) -> Response:
        """Raise :class:`HTTPStatusError` on a 4xx/5xx status.

        Returns
        -------
        Response
            This response, so calls can be chained.
        """
        if not self.ok:
            raise HTTPStatusError(self)
        return self

    def __repr__(self) -> str:
        """Return a short debugging representation."""
        return f"<Response [{self.status_code}] {self.url}>"


def request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    json: typing.Any = None,
    data: bytes | None = None,
    params: dict | None = None,
    timeout: float | None = None,
) -> Response:
    """Perform an HTTP request and return the :class:`Response`.

    Parameters
    ----------
    method : str
        HTTP method, e.g. ``"GET"`` or ``"POST"``.
    url : str
        Target URL.
    headers : dict, optional
        Request headers. A ``User-Agent`` and, for ``json``, a
        ``Content-Type: application/json`` are filled in when absent.
    json : object, optional
        Body to serialise as JSON. Mutually exclusive with ``data``.
    data : bytes, optional
        Raw request body.
    params : dict, optional
        Query parameters appended to the URL.
    timeout : float, optional
        Seconds to wait for the response.

    Returns
    -------
    Response
        The response, including 4xx and 5xx ones.

    Raises
    ------
    ValueError
        If both ``json`` and ``data`` are given.
    RequestError
        If the URL is not ``http``/``https``, or no response was produced at all.
    """
    if json is not None and data is not None:
        raise ValueError("pass either json= or data=, not both")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise RequestError(
            f"{method.upper()} {url} refused: "
            f"{parsed.scheme.lower() or 'relative'} is not one of {sorted(ALLOWED_SCHEMES)}"
        )

    if params:
        separator = "&" if parsed.query else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(params)}"

    sent = {"User-Agent": USER_AGENT}
    sent.update(headers or {})
    body = data
    if json is not None:
        body = _json.dumps(json).encode("utf-8")
        if not any(key.lower() == "content-type" for key in sent):
            sent["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=sent, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as raw:
            return Response(raw.status, dict(raw.headers), raw.read(), url)
    except urllib.error.HTTPError as error:
        # An error status is a response -- the body usually says what went wrong.
        with error:
            return Response(error.code, dict(error.headers or {}), error.read(), url)
    except urllib.error.URLError as error:
        raise RequestError(f"{method.upper()} {url} failed: {error.reason}") from error
    except (TimeoutError, OSError) as error:  # socket timeouts, connection resets
        raise RequestError(f"{method.upper()} {url} failed: {error}") from error


def get(url: str, **kwargs) -> Response:
    """Perform a GET request; see :func:`request` for the parameters."""
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> Response:
    """Perform a POST request; see :func:`request` for the parameters."""
    return request("POST", url, **kwargs)
