"""*calc R0* in the emtk shell: the Förster radius calculator dialog, driven headlessly.

The dialog (:mod:`chisurf.emtk.forster_calculator`) runs over the two-dye
scratch MMFDB of :mod:`forster_spectra_fixture`: pick donor and acceptor in the
choice lists, edit the quantum yield, press *Apply R₀ to model*, and ``on_close``
gets the R0 the spectra give. The parity test compares its controls with the
inventory of the Qt ``ForsterCalculatorWidget`` in the same state
(``forster_calculator_qt_inventory.json``, written by
``capture_forster_calculator_qt_before.py``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("mmfdb.repository")

from emtk.app import ImApp  # noqa: E402
from emtk.testing import Driver  # noqa: E402

from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra  # noqa: E402
from chisurf.emtk.forster_calculator import ForsterCalculatorDialog  # noqa: E402
from test.native_emtk.forster_spectra_fixture import (  # noqa: E402
    DYES,
    WAVELENGTHS,
    gaussian,
    make_spectra_db,
    opener,
)

REPO = Path(__file__).resolve().parents[2]
QT_INVENTORY = Path(__file__).with_name("forster_calculator_qt_inventory.json")
SHOTS = Path(os.environ.get("CHISURF_FORSTER_AFTER_DIR", "/tmp/w9_s2c"))
SIZE = (760, 520)

#: Qt controls the emtk dialog shows differently, and where they went.
DELIBERATE = {
    # The Qt result label is one line; the dialog shows R0 in a read-only field
    # (label "R₀", value "33.1 Å") and J on the line under it.
    "r₀=33.1åj=7.687e+13m⁻¹cm⁻¹nm⁴": ("r₀", "33.1å", "j=7.687e+13m⁻¹cm⁻¹nm⁴"),
    # Qt draws the ε_max subscript as rich text; the canvas writes it with an underscore.
    "acceptorεmax": ("acceptorε_max",),
    # Row numbers of the Qt combo boxes' completer popups (item views), not controls.
    "1": (),
    "2": (),
    "3": (),
}


def _expected_r0(qy: float) -> float:
    donor = DYES["Dye488"]
    acceptor = DYES["Dye594"]
    grid = np.linspace(WAVELENGTHS[0], WAVELENGTHS[-1], 1000)
    absorption = gaussian(acceptor[0], acceptor[2])
    r0, _ = forster_radius_from_spectra(
        grid,
        np.interp(grid, WAVELENGTHS, gaussian(donor[1], donor[2])),
        np.interp(grid, WAVELENGTHS, absorption / absorption.max() * acceptor[4]),
        donor_quantum_yield=qy,
        kappa2=2.0 / 3.0,
        refractive_index=1.33,
    )
    return r0


@pytest.fixture
def calculator(tmp_path):
    """``(driver, dialog, closed)`` over the scratch database; ``closed`` collects ``on_close``."""
    db_path = tmp_path / "spectra.sqlite"
    ids = make_spectra_db(db_path)
    closed: list = []
    dialog = ForsterCalculatorDialog(closed.append, open_database=opener(db_path))
    dialog.ids = ids
    holder: dict = {}

    def gui() -> None:
        dialog.draw((0, 0, *SIZE))
        holder["app"]._item_rects.update(dialog.rects)

    holder["app"] = ImApp(gui)
    driver = Driver(holder["app"], size=SIZE)
    driver.frame(3)
    return driver, dialog, closed


def _pick(driver: Driver, field: str, name: str) -> None:
    """Open the choice *field* and click *name* in its list (below the field)."""
    driver.click(field)
    fx, fy, fw, fh = driver.rect(field)
    entry = next(
        entry[:4]
        for entry in driver.painter.texts
        if entry[5] == name and entry[1] >= fy + fh - 1
    )
    driver.click(entry)
    driver.frame(2)


def _type_into(driver: Driver, field: str, text: str) -> None:
    from emtk.keys import KEY_ENTER

    driver.click(field)
    driver.type(text)
    driver.press(KEY_ENTER)
    driver.frame(2)


def _choose_pair(driver: Driver, dialog) -> None:
    _pick(driver, "donor", "Dye488")
    _pick(driver, "acceptor", "Dye594")


def test_pick_pair_edit_qy_and_apply(calculator):
    driver, dialog, closed = calculator
    assert not dialog.model.enabled("apply")
    driver.click("apply")  # disabled: nothing to apply yet
    assert closed == [] and dialog.window.open

    _choose_pair(driver, dialog)
    model = dialog.model
    assert (model.donor, model.acceptor) == (dialog.ids["Dye488"], dialog.ids["Dye594"])
    assert model.donor_qy == DYES["Dye488"][3], "the donor's QY fills in from MMFDB"
    assert model.acceptor_emax == DYES["Dye594"][4], "the acceptor's ε_max fills in from MMFDB"
    np.testing.assert_allclose(model.r0, _expected_r0(DYES["Dye488"][3]), rtol=1e-12)

    _type_into(driver, "donor_qy", "0.5")
    assert model.donor_qy == 0.5
    np.testing.assert_allclose(model.r0, _expected_r0(0.5), rtol=1e-12)
    assert f"{model.r0:.1f} Å" in driver.painter.strings

    driver.click("apply")
    assert len(closed) == 1
    np.testing.assert_allclose(closed[0], _expected_r0(0.5), rtol=1e-12)
    assert not dialog.window.open


def test_close_hands_over_nothing(calculator):
    driver, dialog, closed = calculator
    _choose_pair(driver, dialog)
    driver.click("close")
    assert closed == [None] and not dialog.window.open


def test_unavailable_mmfdb_is_said_and_blocks_the_choices():
    def missing():
        raise RuntimeError("MMFDB is unavailable; spectra selection requires MMFDB.")

    closed: list = []
    dialog = ForsterCalculatorDialog(closed.append, open_database=missing)
    driver = Driver(ImApp(lambda: dialog.draw((0, 0, *SIZE))), size=SIZE)
    driver.frame(3)
    assert "MMFDB is unavailable; spectra selection requires MMFDB." in driver.painter.strings
    assert not dialog.model.enabled("donor") and not dialog.model.enabled("apply")


def test_control_parity_with_the_qt_calculator(calculator):
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from migration_parity import _normalize_control_text

    driver, dialog, _closed = calculator
    _choose_pair(driver, dialog)
    driver.frame(3)
    SHOTS.mkdir(parents=True, exist_ok=True)
    driver.screenshot(SHOTS / "emtk_forster_calculator.png")

    found = {_normalize_control_text(text) for text in driver.painter.strings}
    for options in (dialog.model.donor_options(), dialog.model.acceptor_options()):
        found |= {_normalize_control_text(label) for _value, label in options}
    found.discard("")

    qt = json.loads(QT_INVENTORY.read_text(encoding="utf-8"))
    missing = []
    for control in qt["controls"]:
        if control in found:
            continue
        if control in DELIBERATE:
            missing += [f"{control} -> {alt}" for alt in DELIBERATE[control] if alt not in found]
            continue
        missing.append(control)
    assert not missing, f"Qt controls absent from the emtk dialog: {missing}; drawn: {sorted(found)}"
    # The state, too: the same pair, the same R0.
    assert qt["state"]["donor"] == "Dye488" and qt["state"]["acceptor"] == "Dye594"
    assert f"{dialog.model.r0:.1f}" in qt["state"]["result"]
