"""The Device Setup cards are declared: ``bh_setup``, ``picoquant_setup`` and ``brickmic_setup.view.json``.

The specs and the Qt-free contracts of ``setup_models`` must agree (labels, bounds, options), every binding of a
spec must resolve on its form (``setup_forms``), and the declared controls must do what the hand-drawn cards did.
"""

from __future__ import annotations

import json
from pathlib import Path

from chisurf.plugins.core.acq.gui.setup_forms import (
    SPECS,
    BHSetupForm,
    BrickMicSetupForm,
    PicoQuantSetupForm,
)
from chisurf.plugins.core.acq.gui.setup_models import (
    BH_PARAMETERS,
    BHSetupModel,
    BrickMicSetupModel,
    PicoQuantSetupModel,
)
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

from .test_emtk_acq_native import FakeBHSetupAdapter, FakeBrickMicAdapter

GUI = Path(__file__).parents[1] / "gui"


def spec(model_type) -> dict:
    return json.loads((GUI / SPECS[model_type]).read_text(encoding="utf-8"))


def leaves(sections):
    for section in sections:
        if isinstance(section.get("sections"), list):
            yield from leaves(section["sections"])
        else:
            yield section


def test_the_bh_spec_declares_every_retained_parameter_with_its_bounds_and_options():
    declared = {
        s["attr"]: s
        for s in leaves(spec(BHSetupModel)["sections"])
        if s.get("attr") in {p.name for p in BH_PARAMETERS}
    }
    assert list(declared) == [p.name for p in BH_PARAMETERS]
    for p in BH_PARAMETERS:
        section = declared[p.name]
        assert section["label"] == p.label
        if p.options:
            assert section["type"] == "choice" and section["options"] == list(p.options)
            assert section["labels"] == list(p.options.values())
        else:
            assert (section["minimum"], section["maximum"]) == (p.minimum, p.maximum)
            assert section["kind"] == ("int" if p.integer else "float")


def test_the_brickmic_spec_declares_the_five_settings_with_their_bounds():
    declared = [s for s in leaves(spec(BrickMicSetupModel)["sections"]) if s.get("type") == "value"]
    assert [(s["attr"], s["label"], s["minimum"], s["maximum"]) for s in declared] == [
        (key, label, lo, hi) for key, label, lo, hi, _ in BrickMicSetupModel.FIELDS
    ]


def test_every_binding_of_every_card_resolves_on_its_form():
    forms = {
        BHSetupModel: BHSetupForm(
            BHSetupModel(FakeBHSetupAdapter()), lambda: None, lambda k: None, lambda ok: None
        ),
        PicoQuantSetupModel: PicoQuantSetupForm(
            PicoQuantSetupModel(None, 5000), lambda: None, object()
        ),
        BrickMicSetupModel: BrickMicSetupForm(
            BrickMicSetupModel(FakeBrickMicAdapter()), lambda: None
        ),
    }
    for model_type, form in forms.items():
        for section in leaves(spec(model_type)["sections"]):
            assert section.get("description"), section
            if section.get("attr"):
                assert hasattr(form, section["attr"]), section["attr"]
            if section.get("source"):
                assert callable(getattr(form, section["source"])), section["source"]
            for key in ("source", "edited_call"):
                options = section.get("options")
                name = options.get(key) if isinstance(options, dict) else None
                if name:
                    assert callable(getattr(form, name)), name
            for button in section.get("buttons", []):
                assert callable(getattr(form, button["action"])), button["action"]


def test_a_bh_parameter_field_writes_the_model_value_with_its_type():
    setup = BHSetupModel(FakeBHSetupAdapter())
    form = BHSetupForm(setup, lambda: None, lambda k: None, lambda ok: None)
    form.SYNC_FREQ_DIV = 3.6
    form.TAC_RANGE = 12.5
    assert setup.values["SYNC_FREQ_DIV"] == 4 and setup.values["TAC_RANGE"] == 12.5


def test_the_module_table_ticks_the_active_cards_as_the_checkboxes_did():
    setup = BHSetupModel(FakeBHSetupAdapter())
    setup.cards = [
        {"module_number": 0, "status": "Initialized"},
        {"module_number": 1, "status": "Free"},
    ]
    setup.active_cards = [0]
    form = BHSetupForm(setup, lambda: None, lambda k: None, lambda ok: None)
    rows = form.card_rows()
    assert [(r["label"], r["status"], r["use"]) for r in rows] == [
        ("Module 0", "Initialized", True),
        ("Module 1", "Free", False),
    ]
    form.set_card_use(rows[1], "use", True)
    form.set_card_use(rows[0], "use", False)
    assert setup.active_cards == [1]


def open_card(kind, device):
    from chisurf.plugins.core.acq.gui.app import AcquisitionApp, AcquisitionNativeModel

    app = AcquisitionApp(AcquisitionNativeModel(device_factory=lambda _kind: device))
    ui = Driver(app, (1200, 800))
    ui.draw(3)
    app.model.device_type = kind
    app.model.device = device
    app._open_device_setup()
    ui.draw(3)
    return app, ui


def test_bh_save_and_load_json_ask_the_window_for_a_file_and_ok_closes_the_card():
    app, ui = open_card("BH_SPC", FakeBHSetupAdapter())
    try:
        ui.click("setup_save_json")
        ui.draw(1)
        assert app.dialog_action == "bh_save" and app.dialog.title == "Save BH settings"
        app.dialog = None
        app.file_window.hide()
        ui.draw(2)
        ui.click("setup_load_json")
        ui.draw(1)
        assert app.dialog_action == "bh_load" and app.dialog.title == "Load BH settings"
        app.dialog = None
        app.file_window.hide()
        ui.draw(2)
        ui.click("setup_ok")
        assert app.setup_open is False
    finally:
        app.close()


def test_brickmic_typed_counter_window_applies_with_derived_channels():
    fake = FakeBrickMicAdapter()
    app, ui = open_card("BRICKMIC", fake)
    try:
        ui.type_into("setup_start_ctr", "1")
        ui.type_into("setup_end_ctr", "4")
        ui.click("setup_apply")
        assert (fake.start_ctr, fake.end_ctr, fake.channels) == (1, 4, 4)
        assert "Channels (derived): 4" in ui.draw(2).strings
    finally:
        app.close()


def test_picoquant_maximum_photons_is_clamped_to_the_qt_range_and_applied_as_the_stop_limit():
    app, ui = open_card("PICOQUANT", None)
    try:
        ui.type_into("setup_max_photons", "50")
        assert app.setup_model.max_photons == 1000  # the Qt spin box's minimum
        ui.click("setup_apply")
        assert app.model.photon_limit == 1000
    finally:
        app.close()
