"""?app=<plugin> presents the tool standalone: the app alone, no shell chrome.

The page's ``?app=`` factory is the shell underneath (the services are the
tool's), but what it draws is the tool and nothing else -- no menu bar, no
ribbon, no docks, no status strip. This pins that contract on the desktop
driver, where the boxes are measurable: a presented tool starts at the very
top of the canvas and spans it; a shell-opened one sits under the chrome.
"""
from emtk.testing import Driver

from chisurf.emtk.background_build import join_all

from chisurf.emtk.main_app import EmtkShellApp
from chisurf.emtk.plugins import manifests


def _shell() -> EmtkShellApp:
    catalog = {k: v for k, v in manifests().items() if k == "fret_check"}
    return EmtkShellApp(catalog, console_history=False, console_session_file=False)


def test_a_presented_tool_is_the_whole_window():
    """present_tool: the tool builds, draws, and its box is the full canvas."""
    shell = _shell()
    try:
        driver = Driver(shell, (1200, 800))
        shell.present_tool("fret_check")
        join_all()
        driver.frame(5)
        hosted = shell.hosted["fret_check"]
        assert hosted.app is not None and not hosted.error
        assert hosted.box is not None
        x, y, w, h = hosted.box
        # No menu bar, no ribbon, no status strip: the tool starts at the top
        # and fills the viewport the driver sized.
        assert y == 0, f"the presented tool sits under chrome at y={y}"
        assert x == 0
        assert w >= 1190 and h >= 790, f"the presented tool is boxed to {w}x{h}"
    finally:
        shell.close()


def test_a_shell_opened_tool_sits_under_the_chrome():
    """The control: open_plugin in the ordinary shell leaves room for the chrome."""
    shell = _shell()
    try:
        driver = Driver(shell, (1200, 800))
        shell.open_plugin("fret_check")
        join_all()
        driver.frame(5)
        hosted = shell.hosted["fret_check"]
        assert hosted.app is not None and not hosted.error
        assert hosted.box is not None
        x, y, w, h = hosted.box
        assert y > 0, "the shell-opened tool should sit under the menu bar and ribbon"
    finally:
        shell.close()
