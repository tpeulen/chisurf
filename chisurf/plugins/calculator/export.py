"""Nonmodal EMTK CSV export shared by calculator factories."""

from pathlib import Path

from emtk import im
from emtk.file_dialog import FileDialog


def install_csv_export(app, filename, write):
    dialog = None
    error = ""
    render = app.gui

    def request():
        nonlocal dialog, error
        error = ""
        dialog = FileDialog("Export CSV", mode="save", filename=filename, filters="CSV (*.csv)")

    def draw():
        nonlocal dialog, error
        render()
        if dialog is not None:
            im.set_next_window_size((640, 520), im.Cond.FIRST_USE_EVER)
            if im.begin("Export CSV"):
                result = dialog.draw()
                if result:
                    try:
                        path = Path(result[0])
                        if path.suffix.lower() != ".csv":
                            path = path.with_suffix(".csv")
                        write(path)
                        dialog = None
                    except Exception as exc:
                        error = str(exc)
                elif result is False:
                    dialog = None
                if error:
                    im.text_wrapped(error)
            im.end()

    app.gui = draw
    return request
