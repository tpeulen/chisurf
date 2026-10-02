from qtpy import QtWidgets


def test_package_manager_widget_creation(qapp, qtbot):
    from chisurf.plugins.core.updater.package_widget import PackageManagerWidget

    widget = PackageManagerWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert hasattr(widget, "tabs")
    assert widget.tabs.count() == 4


def test_package_manager_dialog_creation(qapp, qtbot):
    from chisurf.plugins.core.updater.package_widget import (
        PackageManagerDialog,
        PackageManagerWidget,
    )

    dialog = PackageManagerDialog()
    qtbot.addWidget(dialog)
    assert isinstance(dialog, QtWidgets.QDialog)
    assert "Package" in dialog.windowTitle()
    # The dialog now wraps the reusable PackageManagerWidget.
    assert isinstance(dialog.widget, PackageManagerWidget)
    assert hasattr(dialog.widget, "tabs")


def test_a_failed_operation_reports_one_error_and_one_log_line(qapp, qtbot, monkeypatch):
    """The completion handler ran its body twice (two error boxes, two log lines, two refreshes)."""
    from chisurf.gui import dialogs
    from chisurf.plugins.core.updater.package_widget import PackageManagerWidget

    errors = []
    monkeypatch.setattr(dialogs, "error", lambda parent, title, text, **k: errors.append((title, text)))
    widget = PackageManagerWidget()
    qtbot.addWidget(widget)
    qtbot.wait(200)
    widget.log_text.clear()
    widget._on_operation_finished(False, None, "solver said no")
    assert errors == [("Error", "The operation failed:\nsolver said no")]
    assert widget.log_text.toPlainText().count("Operation failed: solver said no") == 1


def test_a_widget_deleted_while_its_worker_runs_does_not_abort_the_process(qapp):
    """A ``QThread`` destroyed while it runs aborts Python; the module keeps a running worker alive until it has finished."""
    import time

    from chisurf.plugins.core.updater import package_widget as pw

    worker = pw.PackageWorker(lambda: time.sleep(0.3) or (True, [], ""))
    worker.start()
    assert worker in pw._ALIVE
    del worker                                   # the starter lets go of it at once
    deadline = time.time() + 5
    while any(not w.isFinished() for w in pw._ALIVE) and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert all(w.isFinished() for w in pw._ALIVE)
