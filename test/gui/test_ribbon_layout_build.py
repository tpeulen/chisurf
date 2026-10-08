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
            """Record the real button route without opening another window."""
            self.route_calls.append((args, kwargs))

        def onRunMacro(self, *args, **kwargs):
            """Stand in for the macro executor older launch paths call."""

    class _Host(PluginMethodsMixin):
        def __init__(self, bar):
            self.ribbon_bar = bar
            self.categories = {}
            self.main_window = _Main()
            self.main_window.route_calls = []
            self.logger = logging.getLogger("test-ribbon-layout")

    bar = RibbonBar()
    host = _Host(bar)
    host._create_plugins_category()
    bar.test_host = host
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
            from qtpy import QtWidgets

            from chisurf.gui.widgets.ribbon.layout import split_address

            for start in range(0, len(records), 8):
                number = start // 8 + 1
                title = group if number == 1 else f"{group} {number}"
                panel = bar.categories()[tab].panels()[title]
                labels = [
                    button.text()
                    for button in panel.findChildren(QtWidgets.QToolButton)
                    if button.text()
                ]
                from chisurf.gui.widgets.navigation import maturity_markers

                expected_labels = []
                for record in records[start : start + 8]:
                    name = split_address(record["plugin_name"])[2]
                    markers = maturity_markers(record)
                    expected_labels.append(name + (" " + " ".join(markers) if markers else ""))
                assert labels == expected_labels


def test_ribbon_screenshot_folds_imaging_into_spectroscopy(qapp, tmp_path):
    """The real Image Tools button moves tabs while retaining its module route."""
    from qtpy import QtCore, QtWidgets

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
    QtCore.QSettings.setPath(
        QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, str(tmp_path / "qt")
    )
    bar = _plugin_ribbon()
    try:
        assert "Imaging" not in bar.categories()
        category = bar.categories()["Spectroscopy"]
        assert "Imaging" in category.panels()
        bar.resize(1400, 170)
        bar.show()
        bar.setCurrentCategory(category)
        bar.showRibbon()
        for _ in range(4):
            qapp.processEvents()
        assert bar.grab().save(str(tmp_path / "ribbon_spectroscopy.png"))
        button = next(
            button
            for button in category.findChildren(QtWidgets.QToolButton)
            if button.text() == "Image Tools"
        )
        button.click()
        args, _kwargs = bar.test_host.main_window.route_calls[-1]
        assert args[0] == "chisurf.plugins.microscopy.imaging_tools"
    finally:
        bar.close()


def test_long_imaging_groups_keep_all_buttons_and_last_panel_reachable(qapp):
    """Production continuation panels and scrolling preserve every plugin button."""
    import logging

    from qtpy import QtWidgets

    from chisurf.gui.widgets.ribbon.ribbon_plugins import PluginMethodsMixin
    from chisurf.gui.widgets.ribbon.ribbonbar import RibbonBar

    class Host(PluginMethodsMixin):
        pass

    bar = RibbonBar()
    host = Host()
    host.ribbon_bar, host.categories = bar, {}
    host.logger = logging.getLogger("ribbon-overflow-test")
    records = [
        {
            "plugin_name": f"Spectroscopy:Imaging:Long tool {i:02}",
            "label": f"Long tool {i:02}",
            "icon": None,
            "enabled": True,
            "description": "An imaging tool in the complete inventory.",
            "callback": lambda: None,
        }
        for i in range(32)
    ]
    try:
        host._create_plugin_tabs(records)
        category = bar.categories()["Spectroscopy"]
        assert list(category.panels()) == ["Imaging", "Imaging 2", "Imaging 3", "Imaging 4"]
        labels = [
            button.text()
            for button in category.findChildren(QtWidgets.QToolButton)
            if button.text().startswith("Long tool ")
        ]
        assert labels == [record["label"] for record in records]
        bar.resize(640, 170)
        bar.show()
        bar.setCurrentCategory(category)
        bar.showRibbon()
        for _ in range(4):
            qapp.processEvents()
        scrollbar = category._categoryScrollArea.horizontalScrollBar()
        assert scrollbar.maximum() > 0
        for _ in range(100):
            category.scrollNext()
        qapp.processEvents()
        assert scrollbar.value() == scrollbar.maximum()
        last = next(
            button
            for button in category.findChildren(QtWidgets.QToolButton)
            if button.text() == "Long tool 31"
        )
        viewport = category._categoryScrollArea.viewport()
        from qtpy import QtCore

        last_box = QtCore.QRect(last.mapTo(viewport, QtCore.QPoint(0, 0)), last.size())
        assert viewport.rect().intersects(last_box)
    finally:
        bar.close()
