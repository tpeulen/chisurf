
import chisurf as cs


def test_chisurf_import():
    # Basic import test
    assert cs.__version__ is not None


def test_parameter_no_gui():
    # Ensure core fitting parameters work without a GUI loop
    from chisurf.core.fitting.parameter import FittingParameter

    p = FittingParameter(name="test", value=1.23)
    assert p.value == 1.23
    p.value = 4.56
    assert p.value == 4.56
