"""Python-callback nodes on IMP.bff, chinet's ``Node`` ergonomics.

chinet's :class:`chinet.Node` accepted a plain Python callable through
``set_python_callback_function``: it inspected the function's signature,
made an input port per parameter (defaulting to the parameter's default),
probed the function with those defaults to learn its output ports (a dict
return names them; anything else gets a single ``out_00``), and
``evaluate()`` called the function with the input-port values.

bff's :class:`IMP.bff.GraphNode` is a SWIG director, so a Python subclass
overrides ``evaluate()`` and every C++ path into it -- a reactive port
write, a linked follower's ``update()``, a session-registered node --
crosses into Python. This module is that subclass plus the
signature-inspection factory, the chisurf-side half of chinet parity
(stage B of removing chinet from chisurf); bff itself stays C++-minimal.

The import of IMP.bff is guarded the way :mod:`chisurf.core.parameter`
guards it: this module imports cleanly in an environment without IMP and
the first use says what is missing.
"""

from __future__ import annotations

import inspect

try:
    import IMP.bff as _bff
    if not hasattr(_bff, "GraphPort"):
        raise ImportError("IMP.bff is present but carries no Port runtime")
except ImportError as _exc:  # pragma: no cover - env without IMP
    _bff = None
    _bff_import_error = _exc


__all__ = ["PythonNode", "function_to_node"]


if _bff is not None:

    class PythonNode(_bff.GraphNode):
        """A bff :class:`~IMP.bff.GraphNode` whose callback is a Python function.

        Use :meth:`set_python_callback_function` (or
        :func:`function_to_node`) to adopt a callable; ``evaluate()`` then
        runs it with the input-port values and writes the outputs, exactly
        as chinet's Node did: a dict return is written port by port, a
        tuple/list return goes to ``out_00``, ``out_01``, ..., anything
        else to ``out_00``, and a ``TypeError`` falls back to the
        ports-maps convention ``func(inputs, outputs)``.
        """

        def __init__(self, func=None, name=""):
            super().__init__(name)
            self._callback = None
            if func is not None:
                self.set_python_callback_function(func)

        def set_python_callback_function(self, func):
            """Adopt ``func`` as this node's callback, inferring its ports.

            An input port is made per function parameter (defaulting to the
            parameter's default, 0.0 without one). The function is then
            called with those defaults: a dict return names the output
            ports, anything else gets a single ``out_00`` output port. A
            function that raises on its defaults still gets its output
            port -- ``out_00`` -- as chinet's did, so a model can be built
            even when its function needs live inputs to run.
            """
            self._callback = func
            # Auto-infer ports from the signature, chinet's defaults
            # (0.0 for a parameter without one).
            sig = inspect.signature(func)
            for pname, param in sig.parameters.items():
                default = 0.0
                if param.default is not inspect.Parameter.empty:
                    default = param.default
                self.add_input_port(
                    pname, _bff.GraphPort(value=default, name=pname)
                )

            # Evaluate with default arguments to see whether the function
            # returns a dictionary of named output ports.
            default_args = {}
            for pname, param in sig.parameters.items():
                if param.default is not inspect.Parameter.empty:
                    default_args[pname] = param.default
                else:
                    default_args[pname] = 0.0
            try:
                res = func(**default_args)
            except Exception:
                res = None

            if isinstance(res, dict):
                for k in res.keys():
                    self.add_output_port(
                        k, _bff.GraphPort(value=0.0, name=k, is_output=True)
                    )
            else:
                self.add_output_port(
                    "out_00",
                    _bff.GraphPort(value=0.0, name="out_00", is_output=True),
                )

        def evaluate(self):
            """Run the callback over the input ports, chinet's evaluate."""
            if self._callback is None:
                # chinet: a node with neither a callback object nor an
                # operator does nothing and stays invalid.
                return
            args = {k: p.value for k, p in self.inputs.items()}
            outs = self.outputs
            try:
                res = self._callback(**args)
            except TypeError:
                # chinet's second calling convention: the port maps.
                self._callback(self.inputs, self.outputs)
            else:
                if isinstance(res, dict):
                    for k, val in res.items():
                        if k in outs:
                            outs[k].value = val
                elif isinstance(res, (tuple, list)) and len(res) > 1:
                    for i, val in enumerate(res):
                        oname = "out_%02d" % i
                        if oname in outs:
                            outs[oname].value = val
                else:
                    if "out_00" in outs:
                        outs["out_00"].value = res
            # Every other node sharing one of our output ports now reads
            # a stale result (Node::evaluate's tail, done here because a
            # director subclass replaces the C++ body outright). The uid
            # comparison stands in for the identity check chinet could do
            # with ``is``: the proxy SWIG hands back for the same C++
            # node is not guaranteed to be the same Python object.
            for p in outs.values():
                n = p.get_node()
                if n is not None and n.get_uid() != self.get_uid():
                    n.set_valid(False)
            self.set_valid(True)

else:  # pragma: no cover - env without IMP

    class PythonNode:
        """Import-time stub: IMP.bff is missing, see :mod:`parameter`."""

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "chisurf.core.nodes requires IMP.bff, the node runtime "
                "that replaced chinet (stage B of removing chinet), but "
                f"importing it failed: {_bff_import_error}"
            )


def function_to_node(func, name=""):
    """Return a :class:`PythonNode` running ``func``, chinet parity.

    Parameters
    ----------
    func : callable
        The Python callable the node evaluates. Its signature names the
        input ports; a dict return value names the output ports.
    name : str, optional
        The node's name.

    Returns
    -------
    PythonNode
    """
    return PythonNode(func, name=name)
