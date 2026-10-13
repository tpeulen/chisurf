"""What the editor's assistant may do in each mode, what it says, and what it shows of a tool run.

Toolkit-free (moved out of the retired Qt agent panel); the emtk assistant (``gui/chat_app.py``)
uses it. ``CHAT_ONLY`` has no tools and writes code into the editor; ``CHISURF_TOOLS`` loads
data, creates and runs fits, edits parameters and exports results; ``FULL_CONTROL`` may also run
Python in the session and write files, each after the user confirms.
"""

from __future__ import annotations

import enum
import pathlib
from typing import Any

from chisurf.core.agent import SAFETY_DANGEROUS, SAFETY_WRITE

__all__ = ["AgentMode", "greeting_for", "provider_status", "tool_highlight"]


class AgentMode(enum.Enum):
    """How much of ChiSurf the assistant may touch."""

    CHAT_ONLY = "chat_only"
    CHISURF_TOOLS = "chisurf_tools"
    FULL_CONTROL = "full_control"

    @property
    def safety(self) -> str:
        """Return the highest tool-safety tier this mode allows."""
        return SAFETY_DANGEROUS if self is AgentMode.FULL_CONTROL else SAFETY_WRITE


def greeting_for(mode: AgentMode) -> str:
    """The opening message for *mode*: the only text that says what the assistant is for.

    It follows the mode: telling someone to select code in the editor is wrong advice in a mode
    whose point is that the assistant loads data and runs fits by itself.
    """
    if mode is AgentMode.CHAT_ONLY:
        return (
            "👋 I'm an AI coding assistant. Select code in the editor and ask me to:\n"
            "- 🔍 Explain the selected code\n"
            "- 🔧 Refactor or improve it\n"
            "- 🐛 Find bugs or issues\n"
            "- 🧪 Write tests\n"
            "- 📝 Add documentation\n\n"
            "📚 Use 'Wiki' to feed the current codebase to the LLM Wiki."
        )
    extra = (
        "\n- ⚠️ run Python in this session and write files — each asks you first"
        if mode is AgentMode.FULL_CONTROL
        else ""
    )
    return (
        "👋 I operate ChiSurf for you. Describe what you want in ordinary words and I will:\n"
        "- 📂 Load data from a file or a folder\n"
        "- 📈 Add fits, choose models and set parameters\n"
        "- ▶️ Run the fits and judge the result\n"
        f"- 💾 Export the numbers{extra}\n"
        "- 🗂️ Everything I create appears in your windows and is saved in your project"
    )


def tool_highlight(data: dict[str, Any]) -> str:
    """A short summary of a tool result: only the numbers a user watches for.

    Parameters
    ----------
    data : dict
        Payload of a ``tool.completed`` event.

    Returns
    -------
    str
        ``"→ ..."`` or empty.
    """
    result = data.get("result") or {}
    if not isinstance(result, dict):
        return ""
    if "n_loaded" in result:
        return f"→ {result['n_loaded']} dataset(s)"
    if "n_created" in result:
        return f"→ {result['n_created']} fit(s)"
    if "n_components" in result:
        return f"→ {result['n_components']} component(s)"
    if isinstance(result.get("irf"), dict):
        return f"→ IRF: {result['irf'].get('name', '')}"
    if isinstance(result.get("assessment"), dict):
        assessment = result["assessment"]
        return f"→ chi2r {assessment.get('chi2r')} ({assessment.get('quality')})"
    if "results" in result and isinstance(result["results"], list):
        values = [
            str(entry.get("chi2r"))
            for entry in result["results"][:6]
            if isinstance(entry, dict) and entry.get("chi2r") is not None
        ]
        return "→ chi2r " + ", ".join(values) if values else ""
    if "path" in result:
        return f"→ {pathlib.Path(str(result['path'])).name}"
    return ""


def provider_status(provider: str) -> tuple[bool, str]:
    """Whether *provider* is usable now, and the sentence that says why (the status dot's tooltip)."""
    if provider == "acp":
        return True, "ACP Agent ready over stdio"
    try:
        from chisurf.core.agent import LLMSettings

        settings = LLMSettings.from_provider(provider)
        settings.validate()
        ready = bool(settings.api_key) or "localhost" in settings.base_url
    except Exception:
        return False, "AI provider is not configured — set a base URL, model and API key."
    if ready:
        return True, f"AI provider ready: {settings.model} at {settings.base_url}"
    return False, "AI provider is not configured — set a base URL, model and API key."
