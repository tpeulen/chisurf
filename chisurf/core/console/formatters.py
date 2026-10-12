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
import sys
import typing

__all__ = ["DisplayFormatter", "format_text", "image_array_png", "MAX_REPR_CHARS"]

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


def _matplotlib_figure(value: typing.Any) -> typing.Any:
    """Return the matplotlib figure *value* is, or ``None``.

    matplotlib figures carry no ``_repr_png_`` (IPython registers a formatter
    for them instead), so the console recognises them by type -- without
    importing matplotlib when the user has not.
    """
    if "matplotlib" not in sys.modules:
        return None
    try:
        from matplotlib.figure import Figure
    except Exception:  # noqa: BLE001 - a broken matplotlib is not ours
        return None
    return value if isinstance(value, Figure) else None


def image_array_png(value: typing.Any) -> bytes | None:
    """Encode a numpy array shaped like an image as PNG, else ``None``.

    ``(h, w)`` is a grey image stretched from its minimum to its maximum (what
    ``imshow`` does), ``(h, w, 3)`` / ``(h, w, 4)`` are RGB / RGBA -- floats in
    0..1, integers in 0..255.

    Parameters
    ----------
    value : object

    Returns
    -------
    bytes or None
    """
    numpy = sys.modules.get("numpy")
    if numpy is None or not isinstance(value, numpy.ndarray):
        return None
    array = value
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[:, :, 0]
    if (
        not (array.ndim == 2 or (array.ndim == 3 and array.shape[2] in (3, 4)))
        or min(array.shape[:2]) < 1
        or array.dtype.kind not in "biuf"
    ):
        return None
    if array.ndim == 2:
        data = array.astype(float)
        finite = numpy.isfinite(data)
        low = float(data[finite].min()) if finite.any() else 0.0
        high = float(data[finite].max()) if finite.any() else 1.0
        span = high - low or 1.0
        data = numpy.where(finite, (data - low) / span, 0.0)
        pixels = (data * 255.0 + 0.5).astype(numpy.uint8)
    else:
        if array.dtype.kind == "f":
            pixels = (numpy.clip(numpy.nan_to_num(array), 0.0, 1.0) * 255.0 + 0.5).astype(
                numpy.uint8
            )
        else:
            pixels = numpy.clip(array, 0, 255).astype(numpy.uint8)
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.fromarray(numpy.ascontiguousarray(pixels)).save(buffer, format="PNG")
    return buffer.getvalue()


class DisplayFormatter:
    """Builds MIME bundles from Python objects."""

    def format(self, value: typing.Any, *, images: bool = False) -> tuple[dict, dict]:
        """Return ``(data, metadata)`` for *value*.

        Parameters
        ----------
        value : object
        images : bool, optional
            Also draw a numpy array shaped like an image as one (``display``
            asks; a trailing ``arr`` stays text, as it does in IPython).

        Returns
        -------
        tuple of dict
            *data* always carries a ``text/plain`` entry, so a console that can
            render nothing rich still shows something.
        """
        data: dict[str, typing.Any] = {}
        metadata: dict[str, typing.Any] = {}

        figure = _matplotlib_figure(value)
        if figure is not None:
            from chisurf.core.console.mpl_inline import figure_bundle
            from chisurf.core.console.shell import running_shell

            try:
                return figure_bundle(figure, running_shell())
            except Exception:  # noqa: BLE001 - fall back to the repr
                pass
        if images:
            try:
                png = image_array_png(value)
            except Exception:  # noqa: BLE001 - not an image after all
                png = None
            if png is not None:
                height, width = value.shape[:2]
                data["image/png"] = png
                data["text/plain"] = f"<image {width}x{height} {value.dtype}>"
                return data, metadata

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
