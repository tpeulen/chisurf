"""The window a finished FRET calibration is read in.

A calibration produces more text than a message box can show: the factor table,
their uncertainties, what each population came out as, what was held fixed and
what this measurement would have given instead, where the backgrounds came
from. That was going into an information dialog whose detail pane is a few
lines tall and cannot be resized, so the part a reader most needs — the held
factors and the population fits at the bottom — was the part behind a scrollbar.

This is a plain resizable window with the whole report in a monospaced view, and
the two actions that belong next to it: keep this calibration, or keep the text.
Saving defaults to the measurement container (see
:mod:`chisurf.plugins.ndxplorer.calibration_io`).
"""

from __future__ import annotations

__all__ = ["show_calibration_report"]


def show_calibration_report(parent, title: str, report: str, *, constants: dict,
                            result: dict | None = None, ndx=None,
                            saved: dict | None = None) -> None:
    """Show *report*, with Save calibration / Save report beside it.

    Parameters
    ----------
    parent : QWidget
    title : str
        Window title.
    report : str
        The whole report, already formatted.
    constants : dict
        The constants the window now carries — what Save writes.
    result : dict, optional
        The optimizer's return value, carried into the saved payload.
    ndx : object, optional
        The window, so Save can find its `.pto` container.
    saved : dict, optional
        The result of an automatic save already done, so the window can say
        where it went instead of offering to do it again silently.
    """
    from qtpy import QtGui, QtWidgets

    from chisurf.plugins.ndxplorer.calibration_io import (
        SUFFIX, container_of, save_calibration,
    )

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle(title)
    # Big enough to read the factor table and the populations without scrolling,
    # and resizable, which is the whole reason this is not a message box.
    dialog.resize(900, 620)
    layout = QtWidgets.QVBoxLayout(dialog)

    header = QtWidgets.QLabel(
        "The correction factors were optimized against the loaded data.")
    header.setWordWrap(True)
    layout.addWidget(header)

    view = QtWidgets.QPlainTextEdit(dialog)
    view.setPlainText(report)
    view.setReadOnly(True)
    view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
    view.setFont(font)
    layout.addWidget(view, 1)

    status = QtWidgets.QLabel(dialog)
    status.setWordWrap(True)
    if saved and saved.get("ok"):
        where = saved.get("where")
        status.setText(
            f"Stored in the measurement: {saved.get('target', '')}"
            if where == "container" else
            f"Saved to {saved.get('target', '')}"
            + (f" — {saved['warning']}" if saved.get("warning") else "")
        )
    elif saved and saved.get("error"):
        status.setText(f"Not stored automatically: {saved['error']}")
    layout.addWidget(status)

    buttons = QtWidgets.QDialogButtonBox(dialog)
    save_cal = buttons.addButton("Save calibration…", QtWidgets.QDialogButtonBox.ActionRole)
    save_txt = buttons.addButton("Save report…", QtWidgets.QDialogButtonBox.ActionRole)
    buttons.addButton(QtWidgets.QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def _save_calibration() -> None:
        """Into the container by default; a file when there is none."""
        container = container_of(ndx)
        if container:
            answer = dialogs.question(
                dialog, "Save calibration",
                "Store the calibration in the measurement?\n\n"
                f"{container}\n\n"
                "Yes keeps it beside the photons and the burst table. "
                "No writes a separate file instead.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                | QtWidgets.QMessageBox.Cancel,
                # Nobody at the keyboard writes nothing.
                QtWidgets.QMessageBox.Cancel,
            )
            if answer == QtWidgets.QMessageBox.Cancel:
                return
            if answer == QtWidgets.QMessageBox.Yes:
                out = save_calibration(constants, ndx=ndx, result=result, embed=True)
                status.setText(
                    f"Stored in the measurement: {out.get('target', '')}"
                    if out.get("ok") else f"Could not store: {out.get('error')}")
                return
        start = (container.rsplit(".", 1)[0] + SUFFIX) if container else ("calibration" + SUFFIX)
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            dialog, "Save calibration", start, f"FRET calibration (*{SUFFIX});;All files (*)")
        if not path:
            return
        out = save_calibration(constants, ndx=ndx, path=path, result=result, embed=False)
        status.setText(f"Saved to {out.get('target', '')}" if out.get("ok")
                       else f"Could not save: {out.get('error')}")

    def _save_report() -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            dialog, "Save report", "fret_calibration.txt",
            "Text (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(report + "\n")
            status.setText(f"Report written to {path}")
        except Exception as exc:                           # noqa: BLE001
            status.setText(f"Could not write the report: {exc}")

    save_cal.clicked.connect(_save_calibration)
    save_txt.clicked.connect(_save_report)
    dialog.exec_()
