"""The ChiSurf agent plugin: drive the running application in plain words.

The panel is the GUI surface of ``chisurf.core.agent`` — the same session,
tool registry and clarification loop the command line drives, attached to the
live application so the tools act on the session the user sees (loaded
datasets, fits, the working directory). Spectroscopic judgment stays with the
user: when a request is ambiguous the agent asks (``ask_user``) instead of
guessing, and anything destructive needs the safety tier the user allowed.
"""

from __future__ import annotations
