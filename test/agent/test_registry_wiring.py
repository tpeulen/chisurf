"""Every registered tool must actually accept the arguments it advertises.

The tests exercise tool functions by importing them, which does not prove the
*registry* points at the right callable. It once did not: a helper defined
between ``@registry.add(name="run_python", ...)`` and ``def run_python`` was
decorated instead, so the catalogue advertised ``run_python`` and dispatched to
a context manager. Every offline test passed; the first real model to call it
got ``working_directory() got an unexpected keyword argument 'code'`` and burnt
its budget retrying.

These checks compare each spec against the signature of the function it is
bound to, which is exactly what that mistake broke.
"""

from __future__ import annotations

import inspect

import pytest

from chisurf.core.agent.tools import build_default_registry as build_registry


@pytest.fixture(scope="module")
def registry():
    """Return the full tool registry."""
    return build_registry()


def specs(registry):
    """Return every registered tool spec."""
    return list(registry.tools.values())


def test_the_registry_is_not_empty(registry):
    assert len(specs(registry)) > 20


def test_a_handler_accepts_every_argument_its_schema_declares(registry):
    """The schema is a promise to the model; the handler has to keep it."""
    problems = []
    for spec in specs(registry):
        signature = inspect.signature(spec.handler)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if accepts_kwargs:
            continue
        declared = set((spec.parameters or {}).get("properties", {}))
        accepted = set(signature.parameters)
        missing = sorted(declared - accepted)
        if missing:
            problems.append(f"{spec.name} ({spec.handler.__name__}) does not accept {missing}")
    assert not problems, "; ".join(problems)


def test_a_handler_takes_the_context_first(registry):
    """Dispatch passes the context positionally, so the name is load-bearing."""
    for spec in specs(registry):
        first = next(iter(inspect.signature(spec.handler).parameters), None)
        assert first == "context", f"{spec.name} takes {first!r} first, not 'context'"


def test_no_handler_is_a_context_manager(registry):
    """The exact shape of the defect: a decorator that bound to the wrong def."""
    for spec in specs(registry):
        handler = spec.handler
        assert not hasattr(handler, "__wrapped__") or not inspect.isgeneratorfunction(
            getattr(handler, "__wrapped__")
        ), f"{spec.name} is bound to a context manager"


def test_every_required_argument_is_declared_in_the_schema(registry):
    """A parameter the model is never told about cannot be supplied."""
    problems = []
    for spec in specs(registry):
        declared = set((spec.parameters or {}).get("properties", {}))
        for name, parameter in inspect.signature(spec.handler).parameters.items():
            if name == "context" or parameter.kind in (
                inspect.Parameter.VAR_KEYWORD,
                inspect.Parameter.VAR_POSITIONAL,
            ):
                continue
            if parameter.default is inspect.Parameter.empty and name not in declared:
                problems.append(f"{spec.name} requires {name!r}, which its schema omits")
    assert not problems, "; ".join(problems)


def test_run_python_is_reachable_through_the_registry(tmp_path, clean_session):
    """The specific regression, end to end through dispatch."""
    from chisurf.core.agent import AgentContext

    context = AgentContext(working_directory=str(tmp_path), allow_code_execution=True)
    spec = build_registry().tools["run_python"]
    result = spec.handler(context, code="result = 6 * 7", purpose="arithmetic")

    assert result["ok"], result
    assert result["result"] == "42"
