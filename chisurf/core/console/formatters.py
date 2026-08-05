"""Turn a Python object into a MIME bundle the console can draw.

The protocol is the ``_repr_*_`` family every scientific Python library already
implements, so a pandas DataFrame arrives as an HTML table and a matplotlib
figure as a PNG without either library knowing chinsole exists.

The truncation in :func:`format_text` is not a nicety. ``repr()`` of a ten
million element list produces a string large enough to wedge a text widget for
minutes -- harder than any ``print`` loop, because it arrives as one insert that
cannot be interrupted between chunks.
"""

from __future__ import annotations

import reprlib
import typing

__all__ = ["DisplayFormatter", "format_text", "MAX_REPR_CHARS"]

#: Longest ``text/plain`` repr rendered in full.
MAX_REPR_CHARS = 100_000

#: ``_repr_*_`` methods, in the order the console prefers to render them.
_REPR_METHODS = (
    ("_repr_html_", "text/html"),
    ("_repr_svg_", "image/svg+xml"),
    ("_repr_png_", "image/png"),
    ("_repr_jpeg_", "image/jpeg"),
    ("_repr_latex_", "text/latex"),
    ("_repr_markdown_", "text/markdown"),
)

_BIG_CONTAINERS = (list, tuple, set, frozenset, dict)


def format_text(value: typing.Any) -> str:
    """Return a bounded ``text/plain`` representation of *value*.

    Parameters
    ----------
    value : object

    Returns
    -------
    str
    """
    try:
        if isinstance(value, _BIG_CONTAINERS) and len(value) > 1000:
            limited = reprlib.Repr()
            limited.maxlist = limited.maxtuple = limited.maxset = 200
            limited.maxdict = 100
            limited.maxstring = 200
            limited.maxother = 200
            text = limited.repr(value)
        else:
            text = repr(value)
    except Exception as exc:  # noqa: BLE001 - a broken __repr__ is the user's
        return f"<unprintable {type(value).__name__}: {exc!r}>"

    if len(text) > MAX_REPR_CHARS:
        dropped = len(text) - MAX_REPR_CHARS
        text = text[:MAX_REPR_CHARS] + f"\n... (repr truncated, {dropped} more characters)"
    return text


class DisplayFormatter:
    """Builds MIME bundles from Python objects."""

    def format(self, value: typing.Any) -> tuple[dict, dict]:
        """Return ``(data, metadata)`` for *value*.

        Parameters
        ----------
        value : object

        Returns
        -------
        tuple of dict
            *data* always carries a ``text/plain`` entry, so a console that can
            render nothing rich still shows something.
        """
        data: dict[str, typing.Any] = {}
        metadata: dict[str, typing.Any] = {}

        bundle = getattr(value, "_repr_mimebundle_", None)
        if callable(bundle):
            try:
                result = bundle(include=None, exclude=None)
            except TypeError:
                result = None
            except Exception:
                result = None
            if isinstance(result, tuple) and len(result) == 2:
                data.update(result[0] or {})
                metadata.update(result[1] or {})
            elif isinstance(result, dict):
                data.update(result)

        for attribute, mime in _REPR_METHODS:
            if mime in data:
                continue
            method = getattr(value, attribute, None)
            if not callable(method):
                continue
            try:
                payload = method()
            except Exception:
                continue
            if payload is None:
                continue
            if isinstance(payload, tuple) and len(payload) == 2:
                payload, extra = payload
                if isinstance(extra, dict):
                    metadata[mime] = extra
            data[mime] = payload

        data.setdefault("text/plain", format_text(value))
        return data, metadata
