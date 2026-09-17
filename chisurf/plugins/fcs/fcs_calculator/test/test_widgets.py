from qtpy import QtWidgets


def test_confocal_calc_widget(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_calculator.wizard import ConfocalCalcWidget

    widget = ConfocalCalcWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    assert "FCS Confocal Calculator" in widget.windowTitle()


def _looks_computed(sb):
    """Return the pair (background colour, has step arrows) of a spin box."""
    return (
        sb.palette().base().color().name(),
        sb.buttonSymbols() != QtWidgets.QAbstractSpinBox.NoButtons,
    )


def test_a_computed_field_does_not_look_like_an_input(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_calculator.wizard import ConfocalCalcWidget

    widget = ConfocalCalcWidget()
    qtbot.addWidget(widget)

    # Default constraint is "Fix D": D is typed in, r_h and Veff are derived.
    input_look = _looks_computed(widget.D_um2_s)
    assert input_look[1] is True
    for sb in (widget.rh_nm, widget.veff_fL):
        assert sb.isReadOnly()
        assert _looks_computed(sb) != input_look
        assert _looks_computed(sb)[1] is False

    # Switching the constraint moves the marking rather than accumulating it:
    # Veff becomes the input and D becomes derived.
    widget.rb_fix_V.setChecked(True)
    assert _looks_computed(widget.veff_fL) == input_look
    assert _looks_computed(widget.D_um2_s) != input_look

    # ... and switching back restores D exactly, so the marking is reversible.
    widget.rb_fix_D.setChecked(True)
    assert _looks_computed(widget.D_um2_s) == input_look
    assert _looks_computed(widget.veff_fL) != input_look


def test_the_aspect_box_is_disabled_for_the_default_sphere(qapp, qtbot):
    from chisurf.plugins.fcs.fcs_calculator.wizard import ConfocalCalcWidget

    widget = ConfocalCalcWidget()
    qtbot.addWidget(widget)

    # "Sphere" is index 0, so currentIndexChanged never fires for it: the state
    # has to be established at construction, not on the first user change.
    assert widget.shape_combo.currentText() == "Sphere"
    assert widget.shape_aspect.isEnabled() is False

    widget.shape_combo.setCurrentText("Ellipsoid")
    assert widget.shape_aspect.isEnabled() is True

    widget.shape_combo.setCurrentText("Sphere")
    assert widget.shape_aspect.isEnabled() is False
