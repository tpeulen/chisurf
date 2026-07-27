# Talking to the user: message boxes and progress

Two things every long-running or fallible piece of ChiSurf has to do — tell the
user something went wrong, and show how far the work has got — used to be done
four different ways each. This page is the one way.

Both APIs share a rule: **the caller says what happened, not where it is shown.**
Where it lands is resolved from context, so the same code works in a docked
panel, in a standalone tool window, and in a headless run with no display at all.

## Message boxes — `chisurf.gui.dialogs`

```python
from chisurf.gui import dialogs

dialogs.warning(self, "Cannot split", "Load a TTTR file first.")
dialogs.error(self, "Read failed", str(exc), detail=traceback.format_exc())

if dialogs.confirm(self, "Delete fit", "Delete the selected fit?"):
    ...
```

Never call `QMessageBox.critical(...)` (or build a `QMessageBox` by hand). A
modal box spins its own event loop until a button is pressed; under
`QT_QPA_PLATFORM=offscreen` — every headless test, every CI job, every
screenshot script — no button can ever be pressed. A dialog on an `except`
branch then does not report the error, it **wedges the process**, and a hung run
looks exactly like a slow one. A `question` box is worse: the answer it never
gets is the one deciding whether a file is overwritten or a record deleted.

`ChiSurfMessageBox` fixes both: it logs every box at a matching level whether or
not it is shown, raises the window only when a person could dismiss it, and
otherwise returns the answer the caller declared safe. A guard test
(`test/test_headless_dialog_seam.py`) fails the build if a raw `QMessageBox`
reappears anywhere outside `chisurf/gui/dialogs.py`.

| Call | Returns | Headless |
| --- | --- | --- |
| `error(parent, title, message)` (alias `critical`) | `bool` — was it shown | logs at ERROR |
| `warning(...)` / `information(...)` / `about(...)` | `bool` | logs at WARNING / INFO |
| `question(parent, title, message, buttons, default)` | `QMessageBox.StandardButton` | returns `default` |
| `confirm(parent, title, message, default=False)` | `bool` | returns `default` |
| `choice(parent, title, message, options, default=None)` | `Answer(key, checked)` | returns `Answer(default, …)` |
| `report_exception(parent, title, exc)` | `bool` | logs with traceback |

Shared keyword options: `informative` (second-tier text), `detail` (long text
folded behind *Show Details* — tracebacks and file lists belong here, not in the
body), `text_format` (`"plain"` / `"rich"` / `"markdown"`).

`choice` replaces the hand-built boxes: it takes custom-labelled buttons and an
optional tick box, and reports both.

```python
answer = dialogs.choice(
    self, "Folder exists", f"'{path}' already exists.",
    {"overwrite": "Overwrite", "skip": "Skip", "cancel": "Cancel"},
    default="skip",                       # what an unattended run does
    checkbox="Don't ask again",
)
if answer.key == "overwrite":
    ...
if answer.checked:
    ...
```

**Choose the default carefully.** It is what an unattended run does. Name the
answer that declines — skip rather than overwrite, keep rather than delete.

**`buttons` is a mask, not a button.** Under PyQt4 the last two arguments of
`question` were *two buttons*; under Qt5 the 4th became a button mask and the
5th the default. So the old spelling

```python
dialogs.question(self, "Message", "Are you sure to quit?",
                 QMessageBox.Yes, QMessageBox.No)      # WRONG
```

asks for a box offering **only Yes**, with a default that is not on it — the
question answers itself, and the program quits whatever the user clicks. Write

```python
dialogs.question(self, "Message", "Are you sure to quit?",
                 buttons=QMessageBox.Yes | QMessageBox.No,
                 default=QMessageBox.No)
```

or just `confirm(...)`, which takes no buttons at all. A default that is not
among the offered buttons is repaired (it gets offered) and logged as a warning,
and a test rejects the two-button spelling anywhere in the tree.

### Testing a path guarded by a dialog

```python
with dialogs.auto_answer(question=dialogs.ChiSurfMessageBox.Yes):
    tool.delete_selected()          # the confirmation answers itself
```

`auto_answer` short-circuits the named box kinds for the duration of the block,
without showing anything. Alternatively patch the method on
`ChiSurfMessageBox`; the module-level functions delegate at call time, so
patching the class also intercepts the `dialogs.warning(...)` spelling.

### Running it off the GUI thread

`ChiSurfProgress` answers *where* progress shows up; it does not run anything.
`ChiSurfProgress.run(...)` (i.e. `chisurf.gui.task.run_in_background`) is the
other half, so a long operation stops freezing the window without each tool
growing its own executor, cancel flag and result-delivery scheme:

```python
def correlate_all(paths, task):              # the handle is the LAST argument
    out = []
    for i, path in enumerate(paths):
        if task.is_cancelled:                # cooperative: nothing interrupts you
            break
        out.append(correlate(path))
        task.set_progress(i + 1, f"Correlating {path.name}")
        task.set_partial(out[-1])            # the plot fills in as it goes
    return out

ChiSurfProgress.run(
    self, "Correlating…", correlate_all, args=(paths,), maximum=len(paths),
    on_partial=self._append_curve,
    on_result=self._show_result,
    on_error=self.Error.correlation_failed,   # a declared message fits exactly
    on_done=lambda: self.action_run.setEnabled(True),
)
```

Rules worth knowing:

* **Read the widgets before you call it.** Only plain values may cross into the
  worker; the worker must touch neither widgets nor plots. Every callback is
  delivered back **on the GUI thread**, so they may.
* **One run per owner** (the owner defaults to `parent`). Starting a task
  cancels the owner's previous one, and a superseded run's result is dropped —
  double-clicking Compute cannot make the older answer win. Pass a distinct
  `owner=` for two operations in one panel that may legitimately overlap.
* **Cancellation is pushed, not polled**: the display's Cancel sets the flag the
  worker checks. `task.raise_if_cancelled()` is the terse form; the resulting
  `CancelledError` is not reported as an error.
* **Headless runs inline.** With no `QApplication` the work runs on the calling
  thread and the callbacks fire in order, so a CLI or a test exercises the real
  call site. `task.wait()` blocks until the callbacks have been delivered.
* Starting a task from `on_result`/`on_error`/`on_done` raises — the teardown
  still running would cancel it. Use `QTimer.singleShot(0, ...)`.

A standalone tool window renders the run in **its own status bar** (message,
bar, and a ✕ that cancels), not in a modal dialog — a modal would take back
exactly what moving the work off the GUI thread bought. Embedded panels still
prefer an inline AutoForm `progress` section, and headless still logs.

## Conditions, not events — `chisurf.gui.widgets.messages`

A dialog is the wrong shape for most of what a tool has to say. "Load a file
first", "this dataset has no error column", "the fit did not converge" are
*states the tool is in*: they arise, they persist while their cause persists,
and they go away when it is fixed. A modal box stops the user's work, says the
thing once, and leaves nothing behind — so the tool looks ready while still
being unusable.

Declare those conditions on the widget class and raise them by name:

```python
from chisurf.gui.widgets.messages import MessagesMixin, Msg

class MyTool(ChisurfDockTool):              # the base already mixes it in

    class Error(ChisurfDockTool.Error):
        no_file = Msg("Load a TTTR file first.")
        unreadable = Msg("Cannot read {}: {}")

    class Warning(ChisurfDockTool.Warning):
        no_irf = Msg("No IRF selected — the decay is fitted unconvolved.")

    def compute(self):
        if self.path is None:
            self.Error.no_file()             # raise it
            return
        self.Error.no_file.clear()           # retract it
        ...
```

The messages appear in the tool's own status bar — most severe first, the rest
counted and listed in the tooltip — and the bar hides itself when nothing is
active, so a tool with no complaints looks exactly as it did before. Any
`QMainWindow` gets the bar automatically the first time it raises a message; a
plain `QWidget` places it with `install_message_bar(layout)`.

Three things follow from *declaring* a condition, and none of them are available
to a dialog:

* the set of things a tool can complain about is enumerable — reviewable, and
  translatable (the extractor picks up `Msg("…")` the same way it picks up
  `i18n.tr("…")`, and the text is translated when it is rendered, so a language
  change re-renders what is already on screen);
* a message can be **retracted** when its cause is fixed;
* a test just looks:

```python
tool._on_compute()
assert tool.Error.no_file.is_shown
assert tool.Error.no_file.text == "Load a TTTR file first."
```

Use `dialogs` for the other kind of message: a **question**, or an event the
user must acknowledge before anything else happens.

## Progress — `chisurf.gui.progress`

```python
from chisurf.gui.progress import ChiSurfProgress

with ChiSurfProgress(self, "Correlating…", len(files)) as bar:
    for i, path in enumerate(files):
        if bar.wasCanceled():
            break
        correlate(path)
        bar.update_progress(i + 1, f"Correlating {path.name}")
```

or, letting it count:

```python
for path in ChiSurfProgress(self, "Correlating…").iterate(files):
    correlate(path)
```

The first argument is the widget the work was started from. From it the display
is resolved, nearest first:

1. an inline AutoForm [`progress` section](#the-autoform-progress-section) in the
   same panel — the bar appears where the work was started;
2. the navigation shell's shared status bar, when the tool is embedded in one;
3. a modal progress dialog, when the tool runs standalone in its own window;
4. plain logging (one line per 10 % of the work), when there is no GUI.

The handle duck-types both `QProgressDialog` (`setValue`, `setLabelText`,
`setRange`, `wasCanceled`, `close`, `finish(final_text=…, auto_close=…,
close_delay_ms=…)`, `finalize(force_auto_close=…)`) and the status-bar task
(`set_value`, `update_progress`, `finish`), so migrating an old call site is a
one-line change of where the handle comes from. `maximum=0` renders a busy
indicator for work of unknown length.

### Cancelling

Cancellation is cooperative — nothing is interrupted behind the work:

* a loop **on the GUI thread** polls `bar.wasCanceled()` each iteration and
  breaks (`iterate()` does this for you);
* work **in a thread** cannot poll, so pass the stop in:

  ```python
  stop = threading.Event()
  bar = ChiSurfProgress(self, "Fitting…", 100, cancel=stop.set)
  ```

  Fitting, FRET docking, H2MM and staged loading all take this form. Without
  `cancel=` the button would set a flag nobody reads and the run would continue
  to the end.

Do not construct `EnhancedProgressDialog` (the modal backend) yourself: that
pins the work to a popup even when it is embedded in a panel or running
headless, which is what this class exists to prevent. The guard test rejects it.

### The AutoForm `progress` section

Declare a bar in any `.view.json`:

```json
{"type": "custom", "key": "progress", "title": "Progress",
 "options": {"cancellable": true, "hide_when_idle": true}}
```

That widget *is* a progress host, so a button in the same form needs no wiring at
all — `ChiSurfProgress(self._button, …)` finds it. Note the bar is usually a
**sibling** of the button, not an ancestor; resolution looks inside each ancestor
as it climbs, which is what makes the run-button-plus-bar row work.

Options: `cancellable` (default `true`), `hide_when_idle` (default `true`),
`show_text` (default `true`), `handle` (publish the widget on the model under
this attribute name), and `target` — a model attribute holding a completion
fraction (0–1) or percent (0–100), polled on every AutoForm refresh, for progress
a *model* owns rather than a GUI loop drives.

Set `show_text: false` when the surrounding tool already prints the running
message in its own status label — otherwise the message appears twice.

### Tools whose layout comes from a `.ui` file

Qt Designer cannot declare an `InlineProgressWidget` without a promotion, so
those tools swap theirs at construction:

```python
uic.loadUi(ui_file, self)
adopt_progress_bar(self)          # replaces the child named "progressBar"
...
self.progressBar.setValue(40)     # unchanged: the shared bar answers this too
```

The swap keeps the widget's place in the layout (including grid cells and their
spans) and its attribute name, and the replacement answers the plain
`QProgressBar` calls — so nothing else in the tool changes. It also becomes a
progress host, so `ChiSurfProgress` started anywhere in that window renders
there.
