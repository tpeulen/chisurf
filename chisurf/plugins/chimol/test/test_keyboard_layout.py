"""Typing respects the system keyboard layout, not a US one.

The bug
-------
On a German keyboard the viewport's prompt typed US letters: the physical key
labelled Z produced ``y``, and every shifted symbol was wrong.

It is the backend's documented behaviour, not a mystery. glfw's key event
carries **its own keycode**, which is a US-QWERTY position, and rendercanvas
turns that into a name with ``chr(key)``; its source says so in a comment --
holding shift and pressing 5 reports ``"5"``, not ``"%"``. Chimol then used
that name as the typed character and applied shift through a **US** table. No
shift table can fix this: the mapping is per layout and per locale, and dead
keys and composed characters have no keycode at all.

The fix is to stop deriving text from the key event where the backend offers a
``char`` event, which carries what the operating system actually produced.
``key_down`` still supplies the keys that *act* -- Return, arrows, Escape --
because those are positions and not characters.

Where it is pinned
------------------
The toolkit-free window's translation is emtk's now
(:class:`emtk.native.CanvasEvents`), and the German case -- the ``y``/``z``
swap, a shifted symbol, an umlaut, fed as the pair of events glfw emits -- is
pinned there, in ``emtk/tests/test_native_events.py``. What stays here is
the page, which must pass on the character the layout produced, untouched.
(The Qt widget's case went with the Qt host, retired 2026-10-13.)
"""

from __future__ import annotations



def test_the_browser_host_passes_the_character_the_page_produced():
    """The browser path. `KeyboardEvent.key` is layout-aware and already
    shifted, so the page's text reaches the renderer untouched -- through
    emtk's page, which translates the key, and chimol's surface.
    """
    from chimol.hosts.web.page import Page
    from emtk.web.page import WebPage

    seen = []

    class _Sink:
        # The page routes keys through the *renderer* (`on_key_press`), so
        # the viewer's own keys and the prompt's share one path; the text
        # must arrive there exactly as the page produced it.
        def on_key_press(self, key, text="", modifiers=0):
            seen.append(text)
            return True

    surface = object.__new__(Page)
    surface.sink = _Sink()
    page = object.__new__(WebPage)
    page.surface = surface
    page._pressed_keys = {}  # object.__new__ skips __init__; the page tracks the keys it has seen go down
    page.key(name="y", text="z")
    assert seen == ["z"], f"the browser host typed {seen!r}"
