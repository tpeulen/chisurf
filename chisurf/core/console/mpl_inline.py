"""The inline matplotlib backend, without ipykernel.

``%matplotlib inline`` is the first line of ChiSurf's shipped ``console_init``
and is therefore on every existing installation, permanently -- ChiSurf merges
packaged defaults underneath the user's settings file and never overwrites it.
So it has to work, not be tolerated.

The mechanism is the one ``ipykernel.pylab.backend_inline`` uses: draw to Agg,
and after each cell sweep the figure manager registry, publish every figure that
was created as a PNG, and close it. What is *not* copied is the rest of
ipykernel.
"""

from __future__ import annotations

import typing

__all__ = ["enable", "flush_figures", "GUIS"]

#: Accepted ``%matplotlib`` arguments and the matplotlib backend each selects.
GUIS = {
    "inline": "agg",
    "agg": "agg",
    "qt": "qtagg",
    "qt5": "qt5agg",
    "widget": "qtagg",
    "notebook": "agg",
}


def _figure_managers():
    """Return the currently open matplotlib figure managers.

    Returns
    -------
    list
        Empty when matplotlib is not imported, so nothing here imports it as a
        side effect of running an unrelated cell.
    """
    import sys

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
    shell : Shell

    Returns
    -------
    tuple
        ``(format, dpi, bbox_inches)``.
    """
    backend = shell.config.InlineBackend
    fmt = str(backend.get("figure_format", "png") or "png").lower()
    dpi = backend.get("figure_dpi")
    bbox = backend.get("bbox_inches", "tight")
    if fmt == "retina":
        fmt, dpi = "png", dpi or 144
    return fmt, float(dpi or 100), str(bbox or "tight")


def flush_figures(shell: typing.Any) -> None:
    """Publish and close every open matplotlib figure.

    Parameters
    ----------
    shell : Shell
    """
    managers = _figure_managers()
    if not managers:
        return

    import io

    fmt, dpi, bbox = _figure_format(shell)
    mime = {"png": "image/png", "svg": "image/svg+xml", "jpeg": "image/jpeg"}.get(
        fmt, "image/png"
    )

    for manager in managers:
        figure = manager.canvas.figure
        # A figure with no content is one the user created and never drew on;
        # publishing an empty white rectangle after every cell is noise.
        if not figure.get_axes():
            continue
        buffer = io.BytesIO()
        try:
            figure.savefig(buffer, format=fmt, dpi=dpi, bbox_inches=bbox)
        except Exception as exc:  # noqa: BLE001
            shell.write_err(f"could not render figure: {exc!r}\n")
            continue
        payload = buffer.getvalue()
        if mime == "image/svg+xml":
            payload = payload.decode("utf-8", errors="replace")
        shell.display_data(
            {mime: payload, "text/plain": f"<Figure {figure.get_size_inches()}>"},
            {mime: {"width": int(figure.get_size_inches()[0] * dpi)}},
        )

    import matplotlib.pyplot as pyplot

    pyplot.close("all")


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
    import matplotlib

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

    hook = getattr(shell, "_flush_figures_hook", None)
    if hook is not None:
        shell.unregister_post_execute(hook)
        shell._flush_figures_hook = None

    matplotlib.use(GUIS[requested], force=True)
    import matplotlib.pyplot as pyplot

    if requested in ("inline", "agg", "notebook"):
        pyplot.ioff()

        def hook() -> None:
            flush_figures(shell)

        shell._flush_figures_hook = hook
        shell.register_post_execute(hook)
    else:
        pyplot.ion()

    shell._matplotlib_backend = requested
    return requested, matplotlib.get_backend()
