"""Escape cancels the shell's modal dialogs wherever the pointer is, as it does in the Qt window.

Found by the final Qt-vs-emtk shell parity pass: the close
guard, the update offer and the project file dialogs stayed up on Escape unless the pointer
happened to be over them (emtk's ``DialogWindow`` closes on Escape only when hovered).
"""

from __future__ import annotations

from emtk.testing import Driver

from chisurf.emtk.main_app import EmtkShellApp


def _shell():
    return EmtkShellApp(
        {}, loader=lambda plugin_id: None, console_history=False, console_session_file=False
    )


def test_escape_cancels_the_project_file_dialog_with_the_pointer_elsewhere():
    shell = _shell()
    try:
        driver = Driver(shell, (1200, 800))
        driver.frame(2)
        chosen = []
        shell.project.open_file_dialog("Open Project", "open", chosen.append)
        driver.frame(2)
        driver.hover((5.0, 5.0))  # the menu bar, far from the dialog
        driver.escape()
        driver.frame(1)
        assert shell.project.file_dialog is None
        assert chosen == []
    finally:
        shell.close()


def test_escape_dismisses_a_shell_question_with_the_pointer_elsewhere():
    shell = _shell()
    try:
        driver = Driver(shell, (1200, 800))
        driver.frame(2)
        answers = []
        shell.project.dialogs.confirm("Update Available", "Open the Updater now?", answers.append)
        driver.frame(2)
        driver.hover((5.0, 5.0))
        driver.escape()
        driver.frame(1)
        assert not shell.project.dialogs.modal
        assert answers == [False]
    finally:
        shell.close()
