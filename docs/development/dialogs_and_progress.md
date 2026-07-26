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

### Testing a path guarded by a dialog

```python
with dialogs.auto_answer(question=dialogs.ChiSurfMessageBox.Yes):
    tool.delete_selected()          # the confirmation answers itself
```

`auto_answer` short-circuits the named box kinds for the duration of the block,
without showing anything. Alternatively patch the method on
`ChiSurfMessageBox`; the module-level functions delegate at call time, so
patching the class also intercepts the `dialogs.warning(...)` spelling.

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
`setRange`, `wasCanceled`, `close`) and the status-bar task (`set_value`,
`update_progress`, `finish`), so migrating an old call site is a one-line change
of where the handle comes from. `maximum=0` renders a busy indicator for work of
unknown length. Cancellation is cooperative: `wasCanceled()` becomes true and the
loop is expected to break — nothing is interrupted behind it.

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
