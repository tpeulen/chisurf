"""Menu Switch is a contextual host action, not a standalone window factory."""

from chisurf.core.api.context import PluginContext
from chisurf.plugins.core.menu_switch.action import switch_interface


def test_missing_main_window_is_explicitly_unavailable():
    """A standalone invocation neither guesses a global host nor reports success."""
    result = switch_interface(PluginContext())
    assert result["ok"] is False and result["available"] is False
    assert "main window" in result["error"]


def test_host_without_toggle_capability_is_explicitly_unavailable():
    """A context with an unrelated host cannot masquerade as a completed switch."""
    result = switch_interface(PluginContext(main_window=object()))
    assert result["ok"] is False and result["available"] is False
