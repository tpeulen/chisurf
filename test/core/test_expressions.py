"""Tests for the safe, policy-driven expression engine."""
import numpy as np
import pytest

from chisurf.core.expressions import (
    DEFAULT_POLICY,
    NDX_POLICY,
    ExpressionError,
    compile_expression,
    evaluate_expression,
    function_signatures,
    resolve_name,
    validate_expression,
)

# -- parsing / whitelist -------------------------------------------------------

def test_arithmetic_compiles_and_evaluates():
    r = evaluate_expression("2 * a + b", {"a": 3.0, "b": 4.0})
    assert r == pytest.approx(10.0)


def test_bare_names_become_refs():
    c = compile_expression("x + y * 2")
    assert set(c.refs) == {"x", "y"}


def test_functions_and_constants_resolve():
    r = evaluate_expression("sqrt(x) + pi", {"x": 4.0})
    assert r == pytest.approx(2.0 + np.pi)


def test_arrays_evaluate_elementwise():
    x = np.array([1.0, 4.0, 9.0])
    r = evaluate_expression("sqrt(x)", {"x": x})
    np.testing.assert_allclose(r, [1.0, 2.0, 3.0])


def test_where_with_comparison():
    x = np.array([-1.0, 2.0, -3.0])
    r = evaluate_expression("where(x < 0, 0.0, x)", {"x": x})
    np.testing.assert_allclose(r, [0.0, 2.0, 0.0])


def test_bitop_combines_conditions():
    x = np.array([0.0, 5.0, 10.0])
    r = evaluate_expression("where((x > 1) & (x < 8), 1.0, 0.0)", {"x": x})
    np.testing.assert_allclose(r, [0.0, 1.0, 0.0])


def test_unknown_function_is_rejected():
    with pytest.raises(ExpressionError):
        compile_expression("os_system('x')")


def test_attribute_access_is_rejected():
    with pytest.raises(ExpressionError):
        compile_expression("x.__class__")


def test_keyword_arguments_are_rejected():
    with pytest.raises(ExpressionError):
        compile_expression("clip(x, a_min=0, a_max=1)")


def test_subscript_is_rejected():
    with pytest.raises(ExpressionError):
        compile_expression("x[0]")


def test_empty_expression_errors():
    with pytest.raises(ExpressionError):
        compile_expression("   ")


def test_syntax_error_message():
    res = validate_expression("x +", ["x"])
    assert not res.ok and "syntax" in res.message.lower()


# -- validation ----------------------------------------------------------------

def test_validate_ok_bare():
    res = validate_expression("a + b", ["a", "b"])
    assert res.ok and res.message is None
    assert set(res.refs) == {"a", "b"}


def test_validate_unknown_name():
    res = validate_expression("a + zzz", ["a"])
    assert not res.ok
    assert "zzz" in res.message
    assert res.unresolved == ("zzz",)


def test_validate_extra_names_forward_reference():
    res = validate_expression("E + 1", known_names=[], extra_names=["E"])
    assert res.ok


def test_validation_result_is_falsey_on_error():
    assert not validate_expression("nope", [])


# -- NDX policy (ndxplorer parity) ---------------------------------------------

def test_ndx_policy_quoted_names_only():
    res = validate_expression("'Sg' - 'Bg'", ["Sg"], policy=NDX_POLICY, extra_names=["Bg"])
    assert res.ok


def test_ndx_policy_rejects_bare_names():
    # Bare identifiers are not allowed under the ndX quoted-name convention.
    res = validate_expression("Sg - Bg", ["Sg", "Bg"], policy=NDX_POLICY)
    assert not res.ok


def test_ndx_policy_case_insensitive_and_pipe():
    # 'green count rate' resolves to a "Name | unit" column, case-insensitively.
    res = validate_expression(
        "'green count rate' * 2", ["Green Count Rate | kHz"], policy=NDX_POLICY
    )
    assert res.ok


def test_ndx_policy_rejects_non_abs_function():
    res = validate_expression("sqrt('x')", ["x"], policy=NDX_POLICY)
    assert not res.ok


def test_ndx_policy_allows_abs():
    res = validate_expression("abs('x')", ["x"], policy=NDX_POLICY)
    assert res.ok


def test_ndx_policy_rejects_comparisons():
    res = validate_expression("'x' < 1", ["x"], policy=NDX_POLICY)
    assert not res.ok


# -- name resolution helper ----------------------------------------------------

def test_resolve_name_pipe_and_case():
    assert resolve_name("green count rate", ["Green Count Rate | kHz"], NDX_POLICY) == \
        "Green Count Rate | kHz"


def test_resolve_name_exact_default():
    assert resolve_name("Sg", ["Sg", "Sr"], DEFAULT_POLICY) == "Sg"
    assert resolve_name("sg", ["Sg"], DEFAULT_POLICY) is None  # case-sensitive default


# -- introspection -------------------------------------------------------------

def test_function_signatures_lists_defaults():
    sigs = function_signatures(DEFAULT_POLICY)
    assert "sqrt" in sigs and "where" in sigs


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
