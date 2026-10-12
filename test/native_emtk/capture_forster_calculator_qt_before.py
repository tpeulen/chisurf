"""Capture the before-half of the Förster radius calculator migration (Qt -> emtk).

Builds the two-dye scratch MMFDB of :mod:`forster_spectra_fixture`, points the
Qt ``ForsterCalculatorWidget`` at it, picks donor ``Dye488`` and acceptor
``Dye594`` (QY and ε_max fill in from the database), lets it compute, and writes
``qt_forster_calculator.png`` and ``qt_forster_calculator.json``
(:func:`migration_parity.control_inventory`) to ``$CHISURF_FORSTER_BEFORE_DIR``
(``/tmp/w9_s2c``). ``test_forster_calculator_dialog.py`` compares the emtk
dialog's controls against that inventory.

Not a test. Run from the repository root::

    QT_QPA_PLATFORM=offscreen python test/native_emtk/capture_forster_calculator_qt_before.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "test" / "gui"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    from forster_spectra_fixture import make_spectra_db, opener
    from migration_parity import control_inventory
    from qtpy import QtWidgets

    out = Path(os.environ.get("CHISURF_FORSTER_BEFORE_DIR", "/tmp/w9_s2c"))
    out.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    db_path = Path(tempfile.mkdtemp()) / "spectra.sqlite"
    ids = make_spectra_db(db_path)

    import chisurf.gui.widgets.models.tcspc.forster_calculator_dialog as dialog

    # The baseline (2026-10-11) was taken before the widget took ``open_database``,
    # by patching its module-level opener; the inventory is the same either way.
    widget = dialog.ForsterCalculatorWidget(open_database=opener(db_path))
    widget.donor_combo.setCurrentIndex(widget.donor_combo.findData(ids["Dye488"]))
    widget.acceptor_combo.setCurrentIndex(widget.acceptor_combo.findData(ids["Dye594"]))
    widget._debounce.stop()
    widget._compute()
    widget.resize(720, 330)
    widget.show()
    app.processEvents()
    widget.grab().save(str(out / "qt_forster_calculator.png"))
    inventory = control_inventory(widget)
    inventory["state"] = {
        "donor": widget.donor_combo.currentText(),
        "acceptor": widget.acceptor_combo.currentText(),
        "result": widget.result_label.text(),
        "apply_enabled": widget.apply_btn.isEnabled(),
        "donor_options": [
            widget.donor_combo.itemText(i) for i in range(widget.donor_combo.count())
        ],
        "acceptor_options": [
            widget.acceptor_combo.itemText(i) for i in range(widget.acceptor_combo.count())
        ],
    }
    (out / "qt_forster_calculator.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False)
    )
    print(json.dumps(inventory, indent=2, ensure_ascii=False))
    widget.close()


if __name__ == "__main__":
    main()
