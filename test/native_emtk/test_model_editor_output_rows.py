"""An output parameter (a derived quantity) has no Fixed / Bounds controls in the emtk model editor.

Found 2026-10-11 in the FCS/lifetime QA walk: the derived rows (``s``, ``ε``, the MDF outputs)
showed a ticked *Fixed* box and a *Bounds* box; the Qt editor shows none for outputs, and neither
means anything for a quantity that is computed, never fitted.
"""

from __future__ import annotations

from chisurf.emtk.model_editor import _paired, _row

OUTPUT = {"uid": "u-s", "name": "s", "label": "s", "value": 0.4, "fixed": True,
          "lo": 0.0, "hi": 1.0, "bounds_on": False, "is_output": True}
FREE = {"uid": "u-t", "name": "t0", "label": "τ", "value": 4.0, "fixed": False,
        "lo": 0.0, "hi": 10.0, "bounds_on": True}


def test_an_output_row_has_empty_fixed_and_bounds_cells():
    row = _row(OUTPUT)
    # None draws as an empty cell; a bool would draw a check box
    assert row["fixed"] is None and row["bounds_on"] is None
    assert row["lo"] is None and row["hi"] is None
    assert row["value"] == 0.4 and row["output"] and row["muted"]


def test_a_fitted_row_keeps_its_check_boxes_and_bounds():
    row = _row(FREE)
    assert row["fixed"] is False and row["bounds_on"] is True
    assert (row["lo"], row["hi"]) == (0.0, 10.0)


def test_a_paired_table_blanks_the_output_slots_only():
    rows, _columns = _paired([FREE, OUTPUT], 2, {"key": "lifetimes"})
    assert rows[0]["fixed0"] is False and rows[0]["bounds_on0"] is True
    assert rows[0]["fixed1"] is None and rows[0]["bounds_on1"] is None


def test_the_shell_editor_shows_no_fixed_or_bounds_for_a_lifetime_fits_outputs(tmp_path):
    """The real editor over a real fit: every output row of its tables has empty Fixed / Bounds cells."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    import test_emtk_shell_model_sections as shell_test
    from emtk.testing import Driver

    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    state = SessionState()
    session = start_session(state=state)
    shell = EmtkShellApp({}, loader=lambda plugin_id: None)
    shell.data.adopt(session)
    shell.state = state
    try:
        driver = Driver(shell, size=(1600, 1000))
        driver.frame(2)
        _prompt, decay = shell_test._tcspc(driver, shell)
        uid = shell_test._add_fit(driver, shell, decay, "Lifetime")
        shell_test._show(driver, shell, uid)
        rows = [r for rows in shell.data.editor._sources.values() for r in rows if r.get("output")]
        assert rows, "the lifetime fit lists its derived outputs"
        for row in rows:
            assert row["fixed"] is None and row["bounds_on"] is None, row["name"]
        fitted = [r for rows in shell.data.editor._sources.values() for r in rows
                  if "output" in r and not r["output"]]
        assert fitted and all(isinstance(r["fixed"], bool) for r in fitted)
        (tmp_path / "editor.png").write_bytes(driver.screenshot())
    finally:
        shell.close()
