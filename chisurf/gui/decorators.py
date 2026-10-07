import pathlib

import chisurf as cs
from chisurf import typing


# reference taken from : http://stackoverflow.com/questions/11872141/drag-a-file-into-qtgui-qlineedit-to-set-url-text
# https://stackoverflow.com/questions/11872141/drag-a-file-into-qtgui-qlineedit-to-set-url-text
class lineEdit_dragFile_injector:
    def __init__(
        self,
        lineEdit,
        auto_inject=True,
        call=None,
        target: typing.List[pathlib.Path] = None,
        sorted: bool = True,
    ):
        self.lineEdit = lineEdit
        self.call = call
        self.sorted = sorted
        self.target = target if target is not None else []
        if auto_inject:
            self.inject_dragFile()

    def inject_dragFile(self):
        self.lineEdit.setDragEnabled(True)
        self.lineEdit.dragEnterEvent = self._dragEnterEvent
        self.lineEdit.dragMoveEvent = self._dragMoveEvent
        self.lineEdit.dropEvent = self._dropEvent

    def _dragEnterEvent(self, event):
        data = event.mimeData()
        urls = data.urls()
        if urls and urls[0].scheme() == "file":
            event.acceptProposedAction()

    def _dragMoveEvent(self, event):
        data = event.mimeData()
        urls = data.urls()
        if urls and urls[0].scheme() == "file":
            event.acceptProposedAction()

    def _dropEvent(self, event):
        data = event.mimeData()
        if isinstance(self.target, list):
            for url in data.urls():
                if url.scheme() == "file":
                    filepath = str(url.toLocalFile())
                    filepath = pathlib.Path(filepath).as_posix()
                    cs.logging.log(0, f"lineEdit_dragFile_injector::_dropEvent: {filepath}")
                    self.target.append(filepath)

            # Sort the target list of file paths
            if self.sorted:
                self.target.sort()

        if data.urls()[0].scheme() == "file":
            filepath = str(data.urls()[0].toLocalFile())
            filepath = pathlib.Path(filepath).as_posix()
            self.lineEdit.setText(filepath)

        if callable(self.call):
            self.call()
