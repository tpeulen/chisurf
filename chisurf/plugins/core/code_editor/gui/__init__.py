"""EMTK GUI components for the ChiSurf Code Editor and AI Agent."""

from .chat_app import ChatApp, ChatGui, ChatModel
from .editor_app import CodeEditorApp, CodeEditorGui, EditorModel

__all__ = [
    "ChatApp",
    "ChatGui",
    "ChatModel",
    "CodeEditorApp",
    "CodeEditorGui",
    "EditorModel",
    "CodeEditorEmtkTool",
    "AgentChatEmtkTool",
]


def __getattr__(name):
    """Load optional Qt hosting adapters only when explicitly requested."""
    if name in ["CodeEditorEmtkTool", "AgentChatEmtkTool"]:
        from . import tool

        return getattr(tool, name)
    raise AttributeError(name)
