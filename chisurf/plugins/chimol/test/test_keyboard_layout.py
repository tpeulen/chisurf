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

What this pins
--------------
The German case exactly: the ``y``/``z`` swap, a shifted symbol, and an umlaut,
each fed as the pair of events glfw emits. Plus the property underneath: with a
char-capable backend, a key event **never** contributes text -- which is what
stops every character being typed twice.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rendercanvas")


class _Canvas:
    """A canvas that reports the events, and the backend, we want to test."""

    def __init__(self, module: str):
        self.handlers: dict[str, list] = {}
        type(self).__module__ = module

    def add_event_handler(self, callback, *event_types):
        for name in event_types:
            self.handlers.setdefault(name, []).append(callback)

    def emit(self, name: str, event: dict):
        for callback in self.handlers.get(name, ()):
            callback({**event, "event_type": name})


@pytest.fixture
def typed():
    """A viewport wired for the two handlers, collecting what it typed.

    Built with ``__new__``: a real one needs a GPU device, and what is under
    test is the translation from events to text, not the canvas.
    """
    from chimol.hosts.native.canvas import CanvasView

    seen: list[tuple[int, str]] = []
    view = object.__new__(CanvasView)
    view._typed_via_char = True
    view._canvas = None
    view.on_key_press = lambda key, text="", modifiers=0: seen.append((key, text)) or True
    view._start_key_repeat = lambda *a, **k: None
    return view, seen


#: (what glfw reports as the key, what the OS produced) for a German layout.
#: The first is the US position of the physical key, which is the whole bug.
GERMAN = [
    ("y", "z", "the Z key: US position Y"),
    ("z", "y", "the Y key: US position Z"),
    ("7", "/", "shift+7 is / on German and & on US"),
    ("'", "ä", "an umlaut, which has no US keycode at all"),
    ("-", "ß", "eszett"),
]


@pytest.mark.parametrize("reported, produced, why", GERMAN, ids=[c[2] for c in GERMAN])
def test_the_character_the_os_produced_is_what_gets_typed(typed, reported, produced, why):
    """The key event is ignored for text; the char event decides."""
    view, seen = typed
    view._on_key_down({"key": reported, "modifiers": ()})
    view._on_char({"data": produced, "modifiers": ()})

    text = "".join(t for _key, t in seen)
    assert text == produced, f"{why}: typed {text!r} instead of {produced!r}"


def test_a_key_event_contributes_no_text_on_a_char_backend(typed):
    """Otherwise every character arrives twice -- once wrong, once right."""
    view, seen = typed
    view._on_key_down({"key": "y", "modifiers": ()})
    assert all(text == "" for _key, text in seen), (
        f"the key event typed {seen!r}; the char event is the only text source"
    )


def test_shift_is_not_applied_twice(typed):
    """The OS already applied it. Upper-casing again would be harmless for a
    letter and wrong for every symbol.
    """
    view, seen = typed
    view._on_key_down({"key": "7", "modifiers": ("Shift",)})
    view._on_char({"data": "/", "modifiers": ("Shift",)})
    assert "".join(t for _k, t in seen) == "/"


def test_a_backend_without_char_events_still_types(typed):
    """The browser reports a layout-aware ``KeyboardEvent.key`` and has no
    ``char`` event, so that path must keep working.
    """
    view, seen = typed
    view._typed_via_char = False
    view._on_key_down({"key": "z", "modifiers": ()})
    assert "".join(t for _k, t in seen) == "z"


def test_a_glfw_canvas_is_recognised_as_char_capable():
    """The flag is set from the backend, not from the first keystroke.

    Deciding on the first char event would mis-handle exactly one character and
    be impossible to reproduce.
    """
    from chimol.hosts.native.canvas import _event_types

    assert "char" in _event_types(_Canvas("rendercanvas.glfw"))
    assert "char" not in _event_types(_Canvas("rendercanvas.offscreen"))


def test_a_control_character_is_not_typed(typed):
    """A char event for Return or a tab must not insert a glyph."""
    view, seen = typed
    view._on_char({"data": "\r", "modifiers": ()})
    view._on_char({"data": "\x00", "modifiers": ()})
    assert seen == [], f"control characters reached the editor: {seen!r}"


# --------------------------------------------------------------- every host


def test_the_backend_list_matches_what_the_backends_do():
    """The list of char-capable backends is checked against their source.

    rendercanvas publishes no event inventory in this version, so the list is
    written down -- and a written-down list of someone else's behaviour is
    exactly the thing that falls behind. This reads the installed backends and
    fails when one starts or stops emitting `char`.
    """
    import pathlib as _pathlib

    import rendercanvas
    from chimol.hosts.native.canvas import _CHAR_BACKENDS

    base = _pathlib.Path(rendercanvas.__file__).parent
    emitting = set()
    for module in base.glob("*.py"):
        text = module.read_text(encoding="utf-8", errors="ignore")
        if "set_char_callback" in text or "_char_input_event(" in text:
            emitting.add(module.stem)

    assert emitting, "found no backend emitting char; has rendercanvas changed?"
    assert emitting == set(_CHAR_BACKENDS), (
        f"_CHAR_BACKENDS is out of date: {emitting ^ set(_CHAR_BACKENDS)}"
    )


def test_the_qt_host_passes_the_character_qt_produced():
    """The Qt widget path, which never had the bug and must not acquire it.

    `QKeyEvent.text()` is what the layout produced; `key()` is a virtual key.
    Taking text from `key()` here would reintroduce the same defect in the
    other host.
    """
    pytest.importorskip("qtpy")
    from chimol.hosts.qt.wgpu_view import WgpuRenderer

    seen = []

    class _Event:
        """A German Z press: virtual key Y, text 'z'."""

        def key(self):
            return 0x59  # Qt.Key_Y

        def text(self):
            return "z"

        def modifiers(self):
            return 0

        def accept(self):
            pass

    # A QWidget cannot be built with `object.__new__`, and building a real one
    # needs a GPU device -- so the method is called against a stand-in that
    # carries only what it touches. What is under test is which of the event's
    # two accessors it reads, and that is visible from here.
    class _Host:
        on_key_press = staticmethod(lambda key, text="", modifiers=0: seen.append(text) or True)

        def __init__(self):
            pass

    _Host.keyPressEvent = WgpuRenderer.keyPressEvent
    _Host.super_called = False
    try:
        _Host().keyPressEvent(_Event())
    except AttributeError:
        # `super().keyPressEvent` is only reached when the engine declines the
        # key; it accepted, so this must not happen.
        pytest.fail("the Qt host fell through to Qt instead of consuming the key")
    assert seen == ["z"], f"the Qt host typed {seen!r} instead of the layout's 'z'"


def test_the_browser_host_passes_the_character_the_page_produced():
    """The browser path. `KeyboardEvent.key` is layout-aware and already
    shifted, so the page's text is passed through untouched.
    """
    from chimol.hosts.web import page as web_demo

    seen = []

    class _Sink:
        # The page routes keys through the *renderer* (`on_key_press`), so
        # the viewer's own keys and the prompt's share one path; the text
        # must arrive there exactly as the page produced it.
        def on_key_press(self, key, text="", modifiers=0):
            seen.append(text)
            return True

    viewer = object.__new__(web_demo.Page)
    viewer.sink = _Sink()
    viewer.key(name="y", text="z")
    assert seen == ["z"], f"the browser host typed {seen!r}"
