from qtpy import QtWidgets

import chisurf.core.fitting
import chisurf.core.fluorescence
import chisurf.core.structure
import chisurf.gui.widgets
from chisurf.core.structure.av.parameters import Dye, ProteinQuenching, Sticking
from chisurf.core.support.i18n import tr
from chisurf.gui.widgets.fitting import FittingParameterWidget
from chisurf.gui.widgets.fitting.parameter_widgets import make_fitting_parameter_widget


class ProteinQuenchingWidget(ProteinQuenching, QtWidgets.QGroupBox):
    @property
    def quencher(self):
        p = dict()
        for qn in str(self.lineEdit_3.text()).split():
            p[qn] = ["CB"]
        return p

    @quencher.setter
    def quencher(self, v):
        s = ""
        for resID in list(v.keys()):
            s += " " + resID
        self.lineEdit_3.setText(s)

    @property
    def all_atoms_quench(self):
        return not bool(self.groupBox.isChecked())

    @all_atoms_quench.setter
    def all_atoms_quench(self, v):
        self._all_atoms_quench = bool(v)
        self.groupBox.setChecked(not self._all_atoms_quench)

    @property
    def excluded_atoms(self):
        """Return atom names from the existing exclusion editor."""
        return str(self.lineEdit_6.text()).split()

    @excluded_atoms.setter
    def excluded_atoms(self, value):
        """Set excluded atom names in the model and its existing editor."""
        atoms = value.split() if isinstance(value, str) else list(value)
        self._excluded_atoms = atoms
        self.lineEdit_6.setText(" ".join(atoms))

    def __init__(self, **kwargs):

        QtWidgets.QGroupBox.__init__(self)
        self.setTitle("Quenching")
        self.lineEdit_6 = QtWidgets.QLineEdit()
        self.lineEdit_6.setText("CA C HA N")
        self.lineEdit_6.setToolTip(
            tr("Atom names excluded when choosing quenching atoms from residue rate settings.")
        )
        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)
        self.lineEdit_3 = QtWidgets.QLineEdit()
        lab = QtWidgets.QLabel("Quenching AA")
        ProteinQuenching.__init__(self, **kwargs)
        self.excluded_atoms = kwargs.get("excluded_atoms", self.excluded_atoms)
        self.quencher = kwargs.get(
            "quenching_amino_acids", {"TRP": ["CB"], "TYR": ["CB"], "HIS": ["CB"], "PRO": ["CB"]}
        )
        # The canonical scale wins over the historical GUI alias. When
        # neither was supplied, retain the scientific model's default.
        if "quench_scale" not in kwargs and "k_quench_protein" in kwargs:
            self.kQ_scale = kwargs["k_quench_protein"]
        if not self._k_quench_scale.description:
            self._k_quench_scale.description = tr(
                "Multiplier applied to the quenching rates assigned to each residue type."
            )
        self._k_quench_editor = make_fitting_parameter_widget(
            self._k_quench_scale, label_text="kQ"
        )

        self.groupBox = QtWidgets.QGroupBox()
        self.groupBox.setCheckable(True)
        self.groupBox.setDisabled(True)
        self.all_atoms_quench = self._all_atoms_quench
        self.groupBox.setTitle("Exclude atoms")
        self.groupBox.setToolTip(
            tr("Checked: use CB atoms. Unchecked: use all atoms except the exclusions "
               "in the selected residue types.")
        )
        layout.addWidget(self._k_quench_editor, 0, 0, 1, 2)
        layout.addWidget(self.lineEdit_3, 1, 1)
        layout.addWidget(lab, 1, 0)
        layout.addWidget(self.groupBox, 2, 0, 1, 2)

        gl = QtWidgets.QVBoxLayout()
        self.groupBox.setLayout(gl)
        gl.addWidget(self.lineEdit_6)


class DyeWidget(Dye, QtWidgets.QGroupBox):
    @property
    def dye_name(self):
        return str(self.dye_select.currentText())

    @dye_name.setter
    def dye_name(self, v):
        if isinstance(v, str):
            v = 0
        self.dye_select.setCurrentIndex(v)
        self.update_parameter()

    def __init__(
        self,
        critical_distance: float = 7.0,
        diffusion_coefficient: float = 5.0,
        tau0: float = 4.0,
        title: str = "",
        **kwargs,
    ):
        QtWidgets.QGroupBox.__init__(self)
        self.dye_select = QtWidgets.QComboBox()
        self.dye_select.addItems(chisurf.core.structure.av.dye_names)
        Dye.__init__(self, **kwargs)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        gb = QtWidgets.QGroupBox()
        gb.setTitle(title)
        layout.addWidget(gb)

        gl = QtWidgets.QGridLayout()
        gb.setLayout(gl)

        self.critical_distance = critical_distance
        self.diffusion_coefficient = diffusion_coefficient
        self.tau0 = tau0

        gl.addWidget(self.dye_select, 0, 0, 1, 2)

        gl.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(
                self._critical_distance
            ),
            1,
            0,
        )
        gl.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(
                self._diffusion_coefficient
            ),
            2,
            0,
        )
        gl.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(self._tau0), 3, 0
        )

        gl.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(self._av_length), 1, 1
        )
        gl.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(self._av_width), 2, 1
        )
        gl.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(self._av_radius), 3, 1
        )
        self.dye_select.currentIndexChanged[int].connect(self.update_parameter)
        self.update_parameter()


class StickingWidget(Sticking, QtWidgets.QGroupBox):
    @property
    def sticky_mode(self):
        if self.radioButton.isChecked():
            return "surface"
        elif self.radioButton_2.isChecked():
            return "quencher"

    @sticky_mode.setter
    def sticky_mode(self, v):
        if v == "surface":
            self.radioButton.setChecked(True)
            self.radioButton_2.setChecked(False)
        elif v == "quencher":
            self.radioButton.setChecked(False)
            self.radioButton_2.setChecked(True)

    def __init__(
        self,
        fit: "chisurf.core.fitting.fit.Fit",
        structure: "chisurf.core.structure.Structure",
        **kwargs,
    ):
        super().__init__(fit, structure, **kwargs)

        self.setTitle("Sticking")
        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)
        self.radioButton = QtWidgets.QRadioButton("Surface")
        self.radioButton_2 = QtWidgets.QRadioButton("Quencher")

        layout.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(self._slow_radius),
            0,
            1,
        )
        layout.addWidget(
            chisurf.gui.widgets.fitting.widgets.make_fitting_parameter_widget(self._slow_fact), 1, 1
        )

        layout.addWidget(self.radioButton, 0, 0)
        layout.addWidget(self.radioButton_2, 1, 0)
