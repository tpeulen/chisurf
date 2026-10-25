"""The agent panel: the same AI Assistant the code editor hosts.

The assistant UI (streaming, tool badges, provider settings, the agent
session with the full tool registry) lives in the code editor plugin's
``chat_app``; this panel does not duplicate it. Opening Agent from the Tools
menu constructs that very application, so the assistant behaves identically
wherever it is opened from.
"""

from __future__ import annotations


def make_app(**kwargs):
    """The plugin's entrypoint: the code editor's AI Assistant application.

    Parameters
    ----------
    **kwargs
        Forwarded to :class:`ChatApp` (``model``, ``editor_ref``) — absent
        when opened from the Tools menu, where the assistant runs standalone.
    """
    from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp

    return ChatApp(**kwargs)
