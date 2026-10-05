"""The ribbon renders the layout ``plugin_layout`` computes — panel for panel."""

from __future__ import annotations


def _plugin_ribbon():
    """Build the ribbon's plugin tabs over the real discovered plugins, as the main window does."""
    from qtpy import QtWidgets

    from chisurf import logging
    from chisurf.gui.widgets.ribbon.ribbon_plugins import PluginMethodsMixin
    from chisurf.gui.widgets.ribbon.ribbonbar import RibbonBar

    class _Main(QtWidgets.QMainWindow):
        def load_and_show_plugin(self, *args, **kwargs):
            """Stand in for the main window's plugin launcher."""

        def onRunMacro(self, *args, **kwargs):
            """Stand in for the macro executor older launch paths call."""

    class _Host(PluginMethodsMixin):
        def __init__(self, bar):
            self.ribbon_bar = bar
            self.categories = {}
            self.main_window = _Main()
            self.logger = logging.getLogger("test-ribbon-layout")

    bar = RibbonBar()
    _Host(bar)._create_plugins_category()
    return bar


def test_every_tab_and_panel_of_the_layout_is_built(qapp):
    import chisurf.core.settings as settings_module
    import chisurf.plugins
    from chisurf.gui.widgets.ribbon.layout import plugin_layout

    settings = settings_module.cs_settings
    expected = plugin_layout(
        chisurf.plugins.iter_plugins(),
        settings.get("plugins", {}),
        settings.get("enable_experimental", False),
    )
    expected = {t: g for t, g in expected.items() if t not in ("File", "Main")}  # built elsewhere

    bar = _plugin_ribbon()
    built = {title: list(cat.panels()) for title, cat in bar.categories().items()}
    for tab, groups in expected.items():
        assert tab in built, (tab, sorted(built))
        for group, records in groups.items():
            assert group in built[tab], (tab, group, built[tab])
            assert len(records) <= 8  # one panel; a longer group continues in "Group 2"
