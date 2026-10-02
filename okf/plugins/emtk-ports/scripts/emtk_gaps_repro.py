"""Five emtk gaps the trajectory tools' click tests found, each a self-contained reproduction (run from any directory
with PYTHONPATH=~/dev/emtk; each prints what it saw and what it expected). Not edited into emtk: reported.

1. the wheel does not reach a field inside a DockManager window (plain window: works)
2. Enter in a text field that was just emptied is not seen as Enter (the click-away commit is)
3. a widget drawn after a window, over one of its inputs, loses the press to the input (tour card buttons)
4. a text field keeps the keyboard after a click on a checkbox elsewhere
5. ``kind: text`` (multi-line) is not drawn by ``draw_form`` (one-line field instead) -- by reading view_form.py
"""


# ---- 1 ----
from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region
from emtk.view_form import FormState, draw_form
from emtk.testing import RecordingPainter
class M:
    n = 5
spec = {"sections": [{"type": "value", "attr": "n", "label": "n", "kind": "int", "style": "spin", "minimum": 0, "maximum": 99}]}
m, form = M(), FormState()
def body(box=None):
    form.rects.clear(); draw_form(spec, m, form)
docks = DockManager(Region("main")); docks.add_window("main", "T", lambda box: body(), dock="main", closable=False)
def gui():
    vp = im.get_main_viewport(); box = (*vp.pos, *vp.size)
    if MODE == "docked": docks.draw(box)
    else:
        if im.begin("W", box): body()
        im.end()
for MODE in ("plain", "docked"):
    m.n = 5
    app = ImApp(gui)
    for _ in range(2): app.draw(RecordingPainter(), 0, 0, 400, 300)
    x, y, w, h = form.rects["n"]
    app.pointer_move(x + w / 2, y + h / 2)
    for _ in range(2): app.draw(RecordingPainter(), 0, 0, 400, 300)
    app.wheel(x + w / 2, y + h / 2, 3)
    for _ in range(3): app.draw(RecordingPainter(), 0, 0, 400, 300)
    print(MODE, "n after wheel +3:", m.n)


# ---- 2 ----
from emtk import im, keys
from emtk.app import ImApp
from emtk.testing import RecordingPainter
state = {"text": "ab", "enters": 0}
def gui():
    if im.begin("W", (0, 0, 300, 100)):
        e, state["text"] = im.input_text("##f", state["text"], "", im.InputTextFlags.ENTER_RETURNS_TRUE)
        state["enters"] += bool(e)
    im.end()
app = ImApp(gui); d = lambda: app.draw(RecordingPainter(), 0, 0, 300, 100)
d(); d(); app.press(60, 20); d(); app.release(); d()
app.key(0x41, "a", 0x04000000); d(); app.key(keys.KEY_BACKSPACE, ""); d()
app.key(keys.KEY_RETURN, "\r"); d()
print("text", repr(state["text"]), "Enter reported", state["enters"], "(expected text '' and 1)")


# ---- 3 ----
from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter
pressed = []
def gui():
    if im.begin("W", (0, 0, 400, 200)):                    # a window with an input field...
        im.input_text("##f", "abc")
    im.end()
    im.set_cursor_screen_pos((20, 8))                      # ...and a button drawn afterwards, over the field
    if im.button("Overlay##o"):
        pressed.append(1)
app = ImApp(gui); d = lambda: app.draw(RecordingPainter(), 0, 0, 400, 200)
d(); d(); app.pointer_move(40, 18); d(); app.press(40, 18); d(); app.release(); d(); d()
print("overlay button pressed:", bool(pressed), "| input field has the keyboard:", app.io.want_capture_keyboard)


# ---- 4 ----
from emtk import im
from emtk.app import ImApp
from emtk.testing import RecordingPainter
state = {"text": "ab", "on": False}
def gui():
    if im.begin("W", (0, 0, 400, 100)):
        _, state["text"] = im.input_text("##f", state["text"])
        _, state["on"] = im.checkbox("box##c", state["on"])
    im.end()
app = ImApp(gui); d = lambda: app.draw(RecordingPainter(), 0, 0, 400, 100)
d(); d(); app.press(60, 18); d(); app.release(); d(); print("typing field has the keyboard:", app.io.want_capture_keyboard)
app.press(12, 42); d(); app.release(); d(); d()   # click the checkbox
print("checkbox toggled:", state["on"], "| keyboard still captured:", app.io.want_capture_keyboard, "(expected False)")
