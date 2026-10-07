import numpy as np
from qtpy import QtCore, QtWidgets

import chisurf.core.fio
import chisurf.core.support.decorators
import chisurf.gui.decorators


class PDBSelector(QtWidgets.QWidget):
    """ """

    @chisurf.gui.decorators.init_with_ui(ui_filename="pdb_widget.ui")
    def __init__(self, show_labels: bool = True, update=None):
        """

        :param show_labels:
        :param update:
        """
        self._pdb = None
        self._chain_combo = self.comboBox
        self._residue_combo = self.comboBox_2
        self._atom_combo = self.comboBox_3
        self.comboBox.currentIndexChanged[int].connect(self.onChainChanged)
        self.comboBox_2.currentIndexChanged[int].connect(self.onResidueChanged)
        if not show_labels:
            self.label.hide()
            self.label_2.hide()
            self.label_3.hide()
        if update is not None:
            self.comboBox_2.currentIndexChanged[int].connect(update)
            self.comboBox_2.currentIndexChanged[int].connect(update)

    @property
    def chain_combo(self):
        return self._chain_combo

    @property
    def residue_combo(self):
        return self._residue_combo

    @property
    def atom_combo(self):
        return self._atom_combo

    def set_atom_index(self, index: int) -> None:
        """Set the selection to the atom at the given index in the atoms array.

        Parameters
        ----------
        index : int
            Index into the atoms array.
        """
        if self._pdb is None or index < 0 or index >= len(self._pdb):
            return

        atom = self._pdb[index]
        chain = str(atom["chain"])
        residue_id = int(atom["res_id"])
        atom_name = str(atom["atom_name"])

        self._chain_combo.blockSignals(True)
        self._residue_combo.blockSignals(True)
        self._atom_combo.blockSignals(True)

        try:
            chain_index = self._chain_combo.findText(chain, QtCore.Qt.MatchFixedString)
            if chain_index >= 0:
                self._chain_combo.setCurrentIndex(chain_index)
            else:
                self.update_chain()
                chain_index = self._chain_combo.findText(chain, QtCore.Qt.MatchFixedString)
                if chain_index >= 0:
                    self._chain_combo.setCurrentIndex(chain_index)

            residue_index = self._residue_combo.findText(
                str(residue_id), QtCore.Qt.MatchFixedString
            )
            if residue_index >= 0:
                self._residue_combo.setCurrentIndex(residue_index)
            else:
                self.onChainChanged()
                residue_index = self._residue_combo.findText(
                    str(residue_id), QtCore.Qt.MatchFixedString
                )
                if residue_index >= 0:
                    self._residue_combo.setCurrentIndex(residue_index)

            atom_index = self._atom_combo.findText(atom_name, QtCore.Qt.MatchFixedString)
            if atom_index >= 0:
                self._atom_combo.setCurrentIndex(atom_index)
            else:
                self.onResidueChanged()
                atom_index = self._atom_combo.findText(atom_name, QtCore.Qt.MatchFixedString)
                if atom_index >= 0:
                    self._atom_combo.setCurrentIndex(atom_index)

        finally:
            self._chain_combo.blockSignals(False)
            self._residue_combo.blockSignals(False)
            self._atom_combo.blockSignals(False)

    @property
    def atoms(self):
        return self._pdb

    @atoms.setter
    def atoms(self, v):
        self._pdb = v
        self.update_chain()

    @property
    def chain_id(self) -> str:
        return str(self.comboBox.currentText())

    @chain_id.setter
    def chain_id(self, v: str):
        pass

    @property
    def residue_name(self) -> str:
        try:
            return str(self.atoms[self.atom_number]["res_name"])
        except ValueError:
            return "NA"

    @property
    def residue_id(self) -> int:
        try:
            return int(self.comboBox_2.currentText())
        except ValueError:
            return 0

    @residue_id.setter
    def residue_id(self, v: int):
        pass

    @property
    def atom_name(self) -> str:
        return str(self.comboBox_3.currentText())

    @atom_name.setter
    def atom_name(self, v: str):
        pass

    @property
    def atom_number(self) -> int:
        residue_key = self.residue_id
        atom_name = self.atom_name
        chain = self.chain_id

        w = chisurf.core.fio.structure.coordinates.get_atom_index(
            self.atoms, chain, residue_key, atom_name, None
        )
        return w

    def onChainChanged(self):
        chisurf.logging.info("PDBSelector:onChainChanged")
        self.comboBox_2.clear()
        pdb = self._pdb
        chain = str(self.comboBox.currentText())
        atom_ids = np.where(pdb["chain"] == chain)[0]
        residue_ids = list(set(self.atoms["res_id"][atom_ids]))
        residue_ids_str = [str(x) for x in residue_ids]
        self.comboBox_2.addItems(residue_ids_str)

    def onResidueChanged(self):
        self.comboBox_3.clear()
        pdb = self.atoms
        chain = self.chain_id
        residue = self.residue_id
        chisurf.logging.info(f"onResidueChanged: {residue}")
        atom_ids = np.where((pdb["res_id"] == residue) & (pdb["chain"] == chain))[0]
        atom_names = [atom["atom_name"] for atom in pdb[atom_ids]]
        self.comboBox_3.addItems(atom_names)

    def update_chain(self):
        self.comboBox.clear()
        chain_ids = list(set(self.atoms["chain"][:]))
        self.comboBox.addItems(chain_ids)
