"""
Plugin entry point for Trace Browser.
This module allows loading via a plugin manager that imports ...trace_browser.__plugin__.
"""


# Note: Do not execute UI code on import. The Plugin Manager may import this module
# during discovery. Creating or showing windows here would cause unwanted popups.


def create_plugin_widget(parent=None):
    """Factory for the native Trace Browser in a Qt host, without side effects on import."""
    from emtk.qt_host import ControlHost

    from chisurf.plugins.tttr.trace_browser.gui.app import make_app

    return ControlHost(make_app())
