from qtpy import QtCore, QtWidgets

class M:
    def __init__(self):
        self.alpha=0.0; self.gamma=1.0; self.polarized=False; self.n_bins=256
        self.changed=0
    def field_changed(self): self.changed+=1

def _w(qtbot, **opts):
    from chisurf.gui.autoform.sections.scalar_table_section import ScalarTableWidget
    m=M(); w=ScalarTableWidget(m, **opts); qtbot.addWidget(w); return m,w

def test_registered():
    from chisurf.gui.autoform.sections import get_section_factory
    assert get_section_factory("scalar_table") is not None

def test_rows_and_edit(qapp, qtbot):
    m,w=_w(qtbot, title="X", call="field_changed", rows=[
        {"attr":"alpha","label":"α leakage"},{"attr":"gamma","label":"γ detection"}])
    assert w.table.rowCount()==2
    assert w.table.item(0,0).text()=="α leakage"
    w.table.item(1,1).setText("2.5")
    assert m.gamma==2.5
    assert m.changed>=1

def test_bool_and_int(qapp, qtbot):
    m,w=_w(qtbot, rows=[{"attr":"polarized","kind":"bool","label":"Pol"},
                         {"attr":"n_bins","kind":"int","label":"Bins"}])
    w.table.item(0,1).setCheckState(QtCore.Qt.Checked)
    assert m.polarized is True
    w.table.item(1,1).setText("512")
    assert m.n_bins==512

def test_monospace(qapp, qtbot):
    from qtpy import QtGui
    m,w=_w(qtbot, rows=[{"attr":"alpha","label":"a"}])
    assert QtGui.QFont(w.table.font()).styleHint()==QtGui.QFont.Monospace
