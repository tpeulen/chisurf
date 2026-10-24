"""Start one plugin's tool as the page itself: ``?app=<plugin id>``.

The page is multi-app: the build names the apps its archive can mount, and
``?app=`` picks one. ndX and ChiMOL are whole standalone apps with their own
factories; chisurf's own tools are plugins of the shell -- ``?app=hmm``
presents the HMM tool as the whole window, standalone: no ChiSurf chrome, no
menu bar, no ribbon, only the tool. Every service the tool expects is still
there, because the shell is -- running underneath, out of sight.

The name is read from the page's own URL, so the apps map can point every
plugin at this one factory; the build decides which plugin ids exist
(:func:`chisurf.web.plugin_apps`).
"""
from __future__ import annotations

from typing import Any

from emtk.i18n import tr

#: The one spec every plugin id maps to.
SPEC = "chisurf.web.plugin_page:make_app"


def requested_app_name() -> str:
    """The ``?app=`` value from the page's URL; ``""`` off a page or without one."""
    try:  # pragma: no cover - exercised on a page (js) and by E2E, not by unit runs
        import js  # noqa: PLC0415 - page-only import
        from urllib.parse import parse_qs, urlparse

        for name in parse_qs(urlparse(str(js.location.href)).query).get("app", ()):
            return str(name)
    except Exception:
        pass
    return ""


def _resolve(app: Any, name: str) -> str | None:
    """The plugin id *name* means: the id, its label, case and punctuation aside.

    A URL someone types is a name (``?app=Trace Browser`` as often as
    ``?app=trace_browser``); the tools answer to both.
    """
    by_id = getattr(app, "by_id", {})
    if name in by_id:
        return name

    def _key(text: str) -> str:
        return "".join(ch.lower() for ch in text if ch.isalnum())

    wanted = _key(name)
    for plugin_id in by_id:
        if _key(plugin_id) == wanted:
            return plugin_id
    for plugin_id, entry in by_id.items():
        if wanted and _key(getattr(entry, "label", "") or "") == wanted:
            return plugin_id
    return None


def make_app() -> Any:
    """The chisurf shell presenting one plugin's tool as the whole window."""
    from chisurf.web import make_app as shell_app  # noqa: PLC0415 - breaks the cycle

    name = requested_app_name()
    app = shell_app()
    if name and name != "chisurf":
        plugin_id = _resolve(app, name)
        if plugin_id is None:
            app.project.dialogs.message(  # the URL named something this page lacks
                tr("?app={name}", domain="chisurf").format(name=name),
                tr("No such plugin on this page; ChiSurf started instead.",
                   domain="chisurf"))
        else:
            # Standalone: the tool fills the window and the shell chrome stays
            # away (EmtkShellApp.present_tool). The URL means the app.
            app.present_tool(plugin_id)
    return app
