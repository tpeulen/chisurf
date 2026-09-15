"""chisurf.core.nodes: the Python-callback node helper on IMP.bff.

chinet's Node accepted Python callables through set_python_callback_function
(signature introspection, ports from parameters, outputs from a dict
return). These tests pin the same contract onto
:class:`chisurf.core.nodes.PythonNode`, a SWIG-director subclass of
``IMP.bff.GraphNode``, the chisurf-side half of stage B of removing chinet
(the raw director mechanics are tested in imp.bff,
test/portnode/test_node_director.py).
"""

import pytest

from chisurf.core import nodes


def test_input_ports_follow_the_signature():
    def f(a=1.0, b=2.0):
        return {"sum": a + b}

    n = nodes.function_to_node(f)
    assert sorted(n.inputs.keys()) == ["a", "b"]
    assert n.inputs["a"].value == pytest.approx(1.0)
    assert n.inputs["b"].value == pytest.approx(2.0)


def test_dict_return_names_the_output_ports():
    def f(a=1.0, b=2.0):
        return {"sum": a + b, "prod": a * b}

    n = nodes.function_to_node(f)
    assert sorted(n.outputs.keys()) == ["prod", "sum"]
    n.inputs["a"].value = 3.0
    n.inputs["b"].value = 4.0
    n.evaluate()
    assert n.outputs["sum"].value == pytest.approx(7.0)
    assert n.outputs["prod"].value == pytest.approx(12.0)
    assert n.is_valid()


def test_scalar_return_gets_out_00():
    n = nodes.function_to_node(lambda x=2.0: x * x)
    assert list(n.outputs.keys()) == ["out_00"]
    n.evaluate()
    assert n.outputs["out_00"].value == pytest.approx(4.0)


def test_function_failing_on_defaults_still_builds_a_node():
    def f(k=0.0):
        raise KeyError("needs live inputs")

    n = nodes.function_to_node(f)
    assert list(n.outputs.keys()) == ["out_00"]


def test_no_callback_evaluate_is_a_no_op_staying_invalid():
    n = nodes.PythonNode(name="empty")
    n.add_input_port("x", nodes._bff.GraphPort(1.0))
    n.add_output_port("out_00", nodes._bff.GraphPort(0.0, False, True))
    n.evaluate()
    assert not n.is_valid()


def test_set_python_callback_function_after_construction():
    # The models/__init__.py pattern: construct, then adopt the callable.
    n = nodes.PythonNode(name="manual")
    n.set_python_callback_function(lambda a=1.0, b=1.0: {"out": a - b})
    assert sorted(n.inputs.keys()) == ["a", "b"]
    n.evaluate()
    assert n.outputs["out"].value == pytest.approx(0.0)


def test_node_joins_the_default_bff_session():
    import IMP.bff as bff

    n = nodes.function_to_node(lambda x=1.0: {"y": x}, name="joiner")
    bff.get_session().add_node("joiner", n)
    n.inputs["x"].value = 41.0
    n.update()
    assert n.outputs["y"].value == pytest.approx(41.0)


def test_ports_write_through_to_fitting_parameters():
    # What function_to_model_decorator relies on: FittingParameter wraps
    # the node's ports, so a parameter write invalidates the node and an
    # evaluate picks it up.
    from chisurf.core.fitting.parameter import FittingParameter

    n = nodes.function_to_node(lambda a=1.0: {"out": 2.0 * a}, name="scaled")
    pa = FittingParameter(port=n.inputs["a"], name="a")
    pa.value = 21.0
    assert not n.is_valid()
    n.evaluate()
    assert n.outputs["out"].value == pytest.approx(42.0)
