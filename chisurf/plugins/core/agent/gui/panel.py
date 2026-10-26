"""The agent panel: the same AI Assistant the code editor hosts.

The assistant UI (streaming, tool badges, provider settings, the agent
session with the full tool registry) lives in the code editor plugin's
``chat_app``; this panel does not duplicate it. Opening Agent from the Tools
menu constructs that very application, so the assistant behaves identically
wherever it is opened from.
"""

from __future__ import annotations

import pathlib

from emtk.i18n import tr


def make_app(**kwargs):
    """The plugin's entrypoint: the code editor's AI Assistant application.

    Parameters
    ----------
    **kwargs
        Forwarded to :class:`ChatApp` (``model``, ``editor_ref``) — absent
        when opened from the Tools menu, where the assistant runs standalone.
    """
    from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
    from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp

    app = ChatApp(**kwargs)
    here = pathlib.Path(__file__).resolve().parent
    tour = EmTkGuidedTour(
        steps=here / "guide.json",
        owner=app,
        wait_for_controls=True,
        get_target_rect=lambda key: app.item_rects.get(key),
    )
    help_window = EmTkHelpWindow(
        title=tr("Agent — Help"), resource=here / "help.md", owner=app, on_start_guide=tour.start
    )
    app.attach_help(help_window, tour)
    return app
