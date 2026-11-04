"""emtk dialogs for the control panel: file browser, About, Help, Tutorial.

Everything is drawn with emtk (no native dialogs), as immediate-mode windows
over the panel.
"""

from __future__ import annotations

import os

from emtk import im

SETTINGS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "cmc-light")


def _center_box(w, h, bw, bh):
    return ((w - bw) / 2.0, max(30.0, (h - bh) / 2.0), bw, bh)


def _dialog_flags():
    return (im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_COLLAPSE
            | im.WindowFlags.NO_SAVED_SETTINGS | im.WindowFlags.NO_MOVE)


TITLE_H = 24.0


def begin_dialog(title, box):
    """A emtk window with an opaque panel, border and title strip."""
    im.begin(title, box, _dialog_flags())
    x, y, w, h = box
    dl = im.get_window_draw_list()
    dl.add_rect_filled((x - 1, y - 1), (x + w + 1, y + h + 1), (0, 0, 0, 150), 6.0)
    dl.add_rect_filled((x, y), (x + w, y + h), (40, 43, 52, 255), 5.0)
    dl.add_rect_filled((x, y), (x + w, y + TITLE_H), (58, 78, 120, 255), 5.0)
    dl.add_rect((x, y), (x + w, y + h), (95, 110, 150, 255), 5.0)
    dl.add_text((x + 10, y + 5), (240, 240, 245, 255), title)
    im.dummy(w - 20, TITLE_H - 4)


# --------------------------------------------------------------------------- #
class FileDialog:
    """Minimal emtk file browser for one file type (*.json settings, *.csv sequences).

    ``draw()`` returns the chosen path once (Save/Load pressed), ``False`` when
    cancelled, and ``None`` while still open.
    """

    def __init__(self, mode, directory=None, filename="settings.json", ext=".json",
                 what="settings", purpose="settings"):
        self.mode = mode  # "save" | "load"
        self.what = what
        self.purpose = purpose
        self.dir = os.path.abspath(directory or SETTINGS_DIR)
        if not os.path.isdir(self.dir):
            self.dir = os.path.expanduser("~")
        self.filename = filename if mode == "save" else ""
        self.ext = ext
        self.error = ""
        self._listing_for = None
        self._listing = []
        self.page = 0
        self._page_for = None

    def _entries(self):
        if self._listing_for != self.dir:
            dirs, files = [], []
            try:
                for name in sorted(os.listdir(self.dir), key=str.lower):
                    if name.startswith("."):
                        continue
                    full = os.path.join(self.dir, name)
                    if os.path.isdir(full):
                        dirs.append(name)
                    elif name.lower().endswith(self.ext):
                        files.append(name)
            except OSError as e:
                self.error = str(e)
            self._listing = [(d, True) for d in dirs] + [(f, False) for f in files]
            self._listing_for = self.dir
        return self._listing

    def path(self):
        name = self.filename.strip()
        if name and not name.lower().endswith(self.ext):
            name += self.ext
        return os.path.join(self.dir, name)

    @property
    def title(self):
        return ("Save " if self.mode == "save" else "Load ") + self.what

    def draw(self, w, h):
        result = None
        im.text("folder:")
        im.same_line()
        im.text_disabled(self.dir)
        if im.small_button("up"):
            self.dir = os.path.dirname(self.dir) or self.dir
        im.same_line()
        if im.small_button("home"):
            self.dir = os.path.expanduser("~")
        im.same_line()
        if im.small_button("cmc-light folder"):
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            self.dir = SETTINGS_DIR
        im.separator()
        entries = self._entries()
        if not entries:
            im.text_disabled("(no folders or %s files here)" % self.ext)
        per_page = 11
        pages = max(1, (len(entries) + per_page - 1) // per_page)
        if self._page_for != self.dir:
            self.page, self._page_for = 0, self.dir
        self.page = min(self.page, pages - 1)
        start = self.page * per_page
        for name, is_dir in entries[start:start + per_page]:
            label = ("[%s]" % name) if is_dir else name
            if im.selectable(label, (not is_dir) and name == self.filename):
                if is_dir:
                    self.dir = os.path.join(self.dir, name)
                else:
                    self.filename = name
        if pages > 1:
            if im.small_button("< prev") and self.page > 0:
                self.page -= 1
            im.same_line()
            im.text_disabled("page %d / %d" % (self.page + 1, pages))
            im.same_line()
            if im.small_button("next >") and self.page < pages - 1:
                self.page += 1
        im.separator()
        im.text("file name:")
        im.same_line()
        im.set_next_item_width(360)
        _, name, entered = im.input_text("##fname", self.filename, "name" + self.ext) + (False,)
        entered = "\r" in name or "\n" in name
        self.filename = name.replace("\r", "").replace("\n", "")
        ok_label = "Save" if self.mode == "save" else "Load"
        if im.button(ok_label, (90, 0)) or entered:
            if not self.filename.strip():
                self.error = "enter a file name"
            elif self.mode == "load" and not os.path.isfile(self.path()):
                self.error = "no such file: %s" % self.path()
            else:
                result = self.path()
        im.same_line()
        if im.button("Cancel", (90, 0)):
            result = False
        if self.error:
            im.text_colored((255, 110, 110, 255), self.error)
        return result


# --------------------------------------------------------------------------- #
def draw_about(w, h, identity, version):
    """Returns False when closed."""
    im.text("cmc-light - ALEX laser source control")
    im.text_disabled("GUI version %s, drawn with emtk" % version)
    im.separator()
    im.text_wrapped(
        "Three TTL-modulated lasers driven by an ESP8266 running the cmc-light "
        "SCPI firmware. The computer either switches the lasers live, or uploads "
        "an excitation sequence (e.g. ALEX for smFRET) that the microcontroller "
        "plays with microsecond timing.")
    im.separator()
    im.text("instrument: %s" % (identity or "not connected"))
    im.text_disabled("SCPI over USB serial (115200) or WiFi (TCP 5025, cmc-light.local)")
    im.text_disabled("command reference: docs/SCPI.md")
    keep = not im.button("Close", (90, 0))
    return keep


HELP_FILE = os.path.join(os.path.dirname(__file__), "help.md")


def help_text():
    with open(HELP_FILE, encoding="utf-8") as f:
        return f.read()


class HelpViewer:
    """Help dialog: formatted Markdown or its source, both painter-level controls.

    The im window draws the frame and the view switch; the App draws
    ``self.view`` into ``self.content_box`` and routes the wheel to it.
    """

    def __init__(self):
        from emtk.widgets.text_editor import Language, TextEditor

        from cmc_light.markdown_view import MarkdownView

        text = help_text()
        self.formatted = MarkdownView(text)
        self.source = TextEditor(text, Language.markdown(), read_only=True)
        self.mode = 0  # 0 formatted, 1 markdown source
        self.content_box = None

    @property
    def view(self):
        return self.formatted if self.mode == 0 else self.source

    def draw(self, w, h):
        """Returns False when closed."""
        if im.radio_button("formatted##helpfmt", self.mode == 0):
            self.mode = 0
        im.same_line()
        if im.radio_button("markdown source##helpsrc", self.mode == 1):
            self.mode = 1
        im.same_line()
        if im.small_button("page up"):
            self.scroll_pages(-1)
        im.same_line()
        if im.small_button("page down"):
            self.scroll_pages(1)
        im.same_line()
        keep = not im.small_button("Close")
        _, cy = im.get_cursor_screen_pos()
        self.content_top = cy + 4.0  # the App draws the view below this line
        return keep

    def place(self, body):
        """Content box inside the window body, below the toolbar row."""
        x, y, w, h = body
        top = max(y, getattr(self, "content_top", y + 30.0))
        self.content_box = (x + 6.0, top, w - 12.0, max(10.0, y + h - top - 6.0))
        return self.content_box

    def scroll_pages(self, pages):
        if self.mode == 0:
            self.formatted.scroll_pages(pages)
        else:
            self.source.scroll(int(pages * 20))


TUTORIAL = [
    ("Welcome", "This tour walks you through a first ALEX measurement setup. Lasers will "
     "only switch on at the step that says so. Use Next / Back; Close ends the tour."),
    ("1. Connect", "Pick the ESP8266 port (marked [LIGHT-3 ...]) in the device list and "
     "press Connect. No hardware at hand? Pick 'Simulator'. The header turns green and "
     "shows the instrument identity."),
    ("2. Safety first", "Put on laser safety glasses and block or dump the beams. The red "
     "OFF button at the top switches everything off at any time; ON brings back what was on."),
    ("3. Set relative powers", "In 'Lasers', drag the power sliders: e.g. blue 60 %, green "
     "100 %, red 35 %. Leave PWM period at 1000 us to start with."),
    ("4. Try computer-driven mode", "Select 'computer-driven' and tick 'on' for one laser: "
     "it lights immediately. Untick it again."),
    ("5. Build an ALEX sequence", "Select 'programmed sequence'. In the Sequence programmer set "
     "the ALEX on-window (e.g. 500 us) and dark gap (e.g. 50 us): the Sequence table follows "
     "every change at once, and the timing preview shows exactly what will be played."),
    ("6. Sync and run time", "To trigger or tag your detector on output D5, tick the 'sync' "
     "column for the steps where it should be high. Set a run time in seconds (0 = endless)."),
    ("7. Enable the lasers", "Tick 'on' for the lasers that take part. The table is sent to "
     "the MCU and played by itself - there is nothing to press. The status line shows "
     "RUNNING, cycles and 'late max'; the red OFF button stops everything."),
    ("8. Edit the table", "Click cells in the Sequence table, drag bars in the timing preview, "
     "or type a text form such as '1000 B+S; 100 -; 500 G+R' and press 'apply text'."),
    ("9. Save your settings", "File > Save settings stores everything except the laser "
     "'on' state. File > Load settings brings it back next time."),
    ("Done", "Press Stop or OFF when finished. Help > Help has the details for every "
     "control."),
]


class Tutorial:
    def __init__(self):
        self.step = 0

    def draw(self, w, h):
        """Returns False when closed."""
        title, text = TUTORIAL[self.step]
        im.text_disabled("step %d of %d" % (self.step + 1, len(TUTORIAL)))
        im.text(title)
        im.separator()
        im.text_wrapped(text)
        im.spacing()
        keep = True
        if im.button("Back", (80, 0)) and self.step > 0:
            self.step -= 1
        im.same_line()
        last = self.step == len(TUTORIAL) - 1
        if im.button("Finish" if last else "Next", (80, 0)):
            if last:
                keep = False
            else:
                self.step += 1
        im.same_line()
        if im.button("Close", (80, 0)):
            keep = False
        return keep
