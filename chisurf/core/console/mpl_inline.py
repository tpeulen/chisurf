"""Inline matplotlib figures in the console, without ipykernel.

A console has no window to put a figure in; a figure belongs in the transcript,
under the cell that drew it, as a notebook shows it. :func:`install` arranges
that when the console starts -- the user writes ``import pylab as plt;
plt.plot(x, y)`` and sees the plot, with no ``%matplotlib`` line first. The
shipped ``console_init`` used to carry ``%matplotlib inline``; it was dropped
with matplotlib as a ChiSurf dependency, and a console that shows nothing for
``plt.plot`` until the user knows a magic is a broken console.

The mechanism is ``matplotlib_inline``'s: the console's backend
(:mod:`chisurf.core.console.mpl_backend`) draws to Agg; after each cell the
figure registry is swept, every figure is published as a PNG and closed;
``plt.show()`` and ``fig.show()`` publish at once. ``%matplotlib inline`` selects
the same backend (older settings files still start with it), ``%matplotlib qt``
opens windows instead.

matplotlib is not a ChiSurf dependency. Nothing here imports it unless the
user's code did or it is installed and the console is starting; without it the
console is unchanged.
"""

from __future__ import annotations

import os
import sys
import typing

__all__ = [
    "BACKEND",
    "GUIS",
    "enable",
    "figure_bundle",
    "flush_figures",
    "install",
    "publish_figure",
]

#: The console's own backend: Agg, published into the transcript.
BACKEND = "module://chisurf.core.console.mpl_backend"

#: Accepted ``%matplotlib`` arguments and the matplotlib backend each selects.
GUIS = {
    "inline": BACKEND,
    "agg": "agg",
    "qt": "qtagg",
    "qt5": "qt5agg",
    "widget": "qtagg",
    "notebook": BACKEND,
}

#: Backends after which the console publishes figures itself.
_INLINE = ("inline", "agg", "notebook")


def _figure_managers():
    """Return the currently open matplotlib figure managers.

    Returns
    -------
    list
        Empty when matplotlib is not imported, so nothing here imports it as a
        side effect of running an unrelated cell.
    """
    helpers = sys.modules.get("matplotlib._pylab_helpers")
    if helpers is None:
        return []
    return list(helpers.Gcf.get_all_fig_managers())


def _figure_format(shell: typing.Any) -> tuple[str, float, str]:
    """Return the inline figure format, dpi and bbox setting.

    Read from ``shell.config.InlineBackend`` so ``%config InlineBackend.
    figure_format = 'svg'`` works, which is the spelling people already know.

    Parameters
    ----------
    shell : Shell or None

    Returns
    -------
    tuple
        ``(format, dpi, bbox_inches)``.
    """
    backend = shell.config.InlineBackend if shell is not None else {}
    fmt = str(backend.get("figure_format", "png") or "png").lower()
    dpi = backend.get("figure_dpi")
    bbox = backend.get("bbox_inches", "tight")
    if fmt == "retina":
        fmt, dpi = "png", dpi or 144
    return fmt, float(dpi or 100), str(bbox or "tight")


def figure_bundle(figure: typing.Any, shell: typing.Any = None) -> tuple[dict, dict]:
    """Render a matplotlib figure as a MIME bundle.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
    shell : Shell, optional
        Supplies ``InlineBackend`` format, dpi and bbox settings.

    Returns
    -------
    tuple of dict
        ``(data, metadata)``; *data* carries the image and a ``text/plain``.
    """
    import io

    fmt, dpi, bbox = _figure_format(shell)
    mime = {"png": "image/png", "svg": "image/svg+xml", "jpeg": "image/jpeg"}.get(fmt, "image/png")
    buffer = io.BytesIO()
    figure.savefig(buffer, format=fmt if mime != "image/png" else "png", dpi=dpi, bbox_inches=bbox)
    payload: typing.Any = buffer.getvalue()
    if mime == "image/svg+xml":
        payload = payload.decode("utf-8", errors="replace")
    width, height = figure.get_size_inches()
    text = f"<Figure size {width * dpi:g}x{height * dpi:g} with {len(figure.get_axes())} Axes>"
    return {mime: payload, "text/plain": text}, {mime: {"width": int(width * dpi)}}


def _target(shell: typing.Any) -> typing.Any:
    """Return *shell*, or the console running a cell when it is ``None``."""
    if shell is not None:
        return shell
    from chisurf.core.console.shell import running_shell

    return running_shell()


def publish_figure(figure: typing.Any, shell: typing.Any = None) -> bool:
    """Publish one figure into a console's transcript.

    Parameters
    ----------
    figure : matplotlib.figure.Figure
    shell : Shell, optional
        Defaults to the console running the current cell.

    Returns
    -------
    bool
        Whether a console received it.
    """
    shell = _target(shell)
    if shell is None:
        return False
    try:
        data, metadata = figure_bundle(figure, shell)
    except Exception as exc:  # noqa: BLE001 - a figure that cannot draw is the user's error
        shell.write_err(f"could not render figure: {exc!r}\n")
        return False
    shell.display_data(data, metadata)
    return True


def flush_figures(shell: typing.Any = None, *, close: bool = True) -> None:
    """Publish every open matplotlib figure, then close them.

    Parameters
    ----------
    shell : Shell, optional
        Defaults to the console running the current cell.
    close : bool, optional
        Close the figures afterwards, so the next cell starts a new one (as
        a notebook does); ``plt.show(close=False)`` keeps them.
    """
    managers = _figure_managers()
    if not managers:
        return
    shell = _target(shell)
    if shell is None or getattr(shell, "_matplotlib_backend", None) not in _INLINE:
        return
    for manager in managers:
        figure = manager.canvas.figure
        # A figure with no content is one the user created and never drew on;
        # publishing an empty white rectangle after every cell is noise.
        if figure.get_axes():
            publish_figure(figure, shell)
    if close:
        import matplotlib.pyplot as pyplot

        pyplot.close("all")


def _register_flush(shell: typing.Any) -> None:
    """Run :func:`flush_figures` after each of *shell*'s cells."""
    if getattr(shell, "_flush_figures_hook", None) is not None:
        return

    def hook() -> None:
        flush_figures(shell)

    shell._flush_figures_hook = hook
    shell.register_post_execute(hook)


def _unregister_flush(shell: typing.Any) -> None:
    hook = getattr(shell, "_flush_figures_hook", None)
    if hook is not None:
        shell.unregister_post_execute(hook)
        shell._flush_figures_hook = None


def install(shell: typing.Any) -> bool:
    """Show *shell*'s matplotlib figures inline from its first cell on.

    Called when a console starts. Cheap when matplotlib was not imported yet:
    the backend is chosen through ``MPLBACKEND``, which matplotlib reads on
    first import, as ipykernel does; only an already-imported matplotlib is
    switched directly. An ``MPLBACKEND`` naming an interactive backend is the
    user's choice and is kept (figures then open windows, as they asked).

    Parameters
    ----------
    shell : Shell

    Returns
    -------
    bool
        False when matplotlib is not installed or the user chose another
        backend.
    """
    import importlib.util

    try:
        if "matplotlib" not in sys.modules and importlib.util.find_spec("matplotlib") is None:
            return False
    except (ImportError, ValueError):
        return False
    chosen = os.environ.get("MPLBACKEND", "").strip()
    if chosen and chosen.lower() not in ("agg", BACKEND.lower()):
        return False
    matplotlib = sys.modules.get("matplotlib")
    if matplotlib is None:
        os.environ["MPLBACKEND"] = BACKEND
    else:
        current = (
            str(matplotlib.rcParams._get_backend_or_none() or "").lower()
            if hasattr(matplotlib.rcParams, "_get_backend_or_none")
            else ""
        )
        if current != BACKEND.lower():
            matplotlib.use(BACKEND, force=True)
    shell._matplotlib_backend = "inline"
    _register_flush(shell)
    return True


def enable(shell: typing.Any, gui: str | None = None) -> tuple[str, str]:
    """Select a matplotlib backend for the console.

    Parameters
    ----------
    shell : Shell
    gui : str, optional
        One of :data:`GUIS`, or ``None`` to report the current backend.

    Returns
    -------
    tuple of str
        ``(requested, backend)``.
    """
    try:
        import matplotlib
    except ImportError:
        # ChiSurf itself does not use matplotlib; this magic serves the user's
        # own plotting code, so its absence is a message, not a traceback.
        shell.write_err(
            "matplotlib is not installed; install it into this environment to "
            "plot from the console (ChiSurf's own plots do not need it)\n"
        )
        return (gui or "").strip().lower().lstrip("-"), ""

    if gui is None:
        return "", matplotlib.get_backend()

    requested = gui.strip().lower().lstrip("-")
    if requested not in GUIS:
        known = ", ".join(sorted(GUIS))
        shell.write_err(f"unknown matplotlib backend {gui!r}; known: {known}\n")
        return requested, matplotlib.get_backend()

    if requested == "widget":
        shell.write_err(
            "the 'widget' backend needs Jupyter's ipywidgets, which ChiSurf "
            "does not use; falling back to 'qt'\n"
        )
        requested = "qt"

    _unregister_flush(shell)
    matplotlib.use(GUIS[requested], force=True)
    import matplotlib.pyplot as pyplot

    if requested in _INLINE:
        pyplot.ioff()
        shell._matplotlib_backend = requested
        _register_flush(shell)
    else:
        pyplot.ion()
        shell._matplotlib_backend = requested
    return requested, matplotlib.get_backend()
