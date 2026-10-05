from __future__ import annotations

import hashlib
import inspect
import types
from functools import wraps
from typing import TYPE_CHECKING

import numpy as np

import chisurf.core.models
import chisurf.core.parameter
import chisurf.core.support.decorators
from chisurf import typing
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models import model
from chisurf.core.models.catalogue import EquationCatalogueMixin

if TYPE_CHECKING:
    from chisurf.core.fitting.fit import Fit


class ParameterTransformModel(EquationCatalogueMixin, model.Model):
    """A model that wraps an arbitrary Python function as a parameter transform.

    The function is provided as a string, compiled, and used to define input
    and output parameters. The model evaluates the function and makes its
    outputs available as fixed parameters for linking.
    """

    name = "Parameter Transform"
    model_name: str

    #: Its catalogue entries hold a Python ``code:`` block assigned to
    #: :attr:`function`, where a parse model holds an ``equation:`` for ``func``.
    catalogue_file = "models.yaml"
    catalogue_source_key = "code"
    catalogue_target_attr = "function"
    view_spec_file = "parameter_transform.view.json"

    def finalize(self):
        """Evaluate the model and finalize all parameter controllers."""
        self._update_model()
        for i, p in enumerate(self.parameters_all):
            if hasattr(p, "controller") and p.controller is not None:
                p.controller.finalize()

    def _update_model(self, **kwargs):
        """Evaluate the parameter transform node and lock output parameters.

        Outputs are temporarily unlocked for evaluation, then re-locked so
        they remain fixed for linking purposes.
        """
        # Temporarily unlock outputs for evaluation
        for output in self._model._node.outputs.values():
            output.fixed = False

        try:
            self._model._node.evaluate()
        finally:
            for output in self._model._node.outputs.values():
                output.fixed = True

    def update(self, **kwargs):
        """Evaluate the single wrapped graph and propagate scientific failures."""
        if self.__dict__.get("_frozen_structure") is None:
            self.find_parameters()
        self._update_model(**kwargs)

    @property
    def n_points(self):
        """Number of data points; always 1 for a parameter transform."""
        return 1

    @property
    def n_free(self):
        """Number of free parameters (inputs that are not fixed or linked)."""
        return len(self.parameters)

    @property
    def weighted_residuals(self) -> np.ndarray:
        """Weighted residuals are not applicable; returns an empty array."""
        return np.array([], dtype=np.float64)

    @property
    def function(self) -> str:
        """The Python function string used for the parameter transform."""
        return self._function

    @function.setter
    def function(self, fun: str):
        """Compile and set the function, creating a wrapped model node.

        Parameters
        ----------
        fun : str
            The Python function definition as a string.
        """
        # Validate the function string before using it
        # Try to compile the function to check for syntax errors
        code_obj = compile(fun, "<string>", "exec")
        function_obj = None

        # Extract the function object from the compiled code
        for o in code_obj.co_consts:
            if isinstance(o, types.CodeType):
                function_obj = types.FunctionType(o, globals())
                break

        if function_obj is None:
            raise ValueError("No function found in the provided code")

        # Get the function signature
        sig = inspect.signature(function_obj)

        # Create default arguments for all parameters
        default_args = {}
        for param_name, param in sig.parameters.items():
            if param.default is not inspect.Parameter.empty:
                default_args[param_name] = param.default
            elif param.annotation == "int":
                default_args[param_name] = 1
            elif param.annotation == "float":
                default_args[param_name] = 1.0
            else:
                default_args[param_name] = 0.0

        # Call the function with default arguments, but catch any errors
        try:
            function_obj(**default_args)
        except Exception as e:
            # Log the error but continue with model creation
            import logging

            logging.warning(f"Error evaluating function with default parameters: {str(e)}")
            # Create a dummy result with expected output keys
            # This allows the model to be created even if evaluation fails

        self._function = fun
        m = chisurf.core.models.function_to_model_decorator(name=self.name)

        @wraps(function_obj)
        def scalar_function(**arguments):
            """Convert native scalar-port buffers to the declared scalar inputs."""
            return function_obj(
                **{name: np.asarray(value).item() for name, value in arguments.items()}
            )

        # Create the model class with the function
        model_class = m(scalar_function)

        if self.fit is None:
            raise ValueError("Fit object cannot be None")

        self._model = model_class(self.fit)
        node = self._model._node
        # Document inputs are independent ports. Linking two inputs of the
        # same native node creates a node self-edge in the installed runtime's
        # cross-node cycle check. The node consumes the document ports instead,
        # so both local aliases and cross-fit dependencies form a real DAG.
        parameters = []
        for parameter in self._model.parameters_all:
            name = parameter.name
            if name in node.inputs:
                document_parameter = FittingParameter(name=name, value=parameter.value)
                node.inputs[name].link = document_parameter._port
                parameters.append(document_parameter)
            else:
                parameter.is_output = True
                parameters.append(parameter)
        self._model.node_parameters = parameters
        self._model.find_parameters()

    @property
    def parameters_all(self):
        """Expose the wrapped native ports without recursive attribute discovery."""
        return self._model.parameters_all

    def find_parameters(self, *args, **kwargs):
        """Refresh the wrapped model's inventory after selecting a definition."""
        self._model.find_parameters(*args, **kwargs)

    def apply_initial_values(self, name=None):
        """Apply the transform catalogue's declared numeric values and bounds."""
        entry = self.catalogue.get(name or self.model_name) or {}
        for key, setting in (entry.get("initial") or {}).items():
            parameter = self.parameters_all_dict.get(key)
            if parameter is None:
                continue
            if isinstance(setting, dict):
                parameter.value = float(setting["value"])
                if "bounds" in setting:
                    parameter.bounds = tuple(float(v) for v in setting["bounds"])
                    parameter.bounds_on = True
            else:
                parameter.value = float(setting)

    def get_state(self) -> dict:
        """Declare a shipped definition and native node without saving executable code."""
        entry = self.catalogue.get(self.model_name)
        if not entry or self.function != str(entry.get("code", "")):
            raise ValueError("Only unchanged shipped catalogue transforms support snapshots")
        node = self._model._node
        return {
            "catalogue_name": self.model_name,
            "definition_sha256": hashlib.sha256(self.function.encode("utf-8")).hexdigest(),
            "node_uid": str(node.get_uid()),
            "input_names": list(node.inputs),
            "input_port_uids": {name: str(port.get_uid()) for name, port in node.inputs.items()},
            "output_names": list(node.outputs),
        }

    def get_session_native_nodes(self) -> list:
        """Declare the selected transform node, excluding superseded constructors."""
        return [self._model._node]

    def _verified_session_source(self, state: dict) -> str:
        """Validate the declaration before constructing any scientific native graph."""
        keys = {
            "catalogue_name",
            "definition_sha256",
            "node_uid",
            "input_names",
            "input_port_uids",
            "output_names",
        }
        if not isinstance(state, dict) or set(state) != keys:
            raise ValueError("Invalid parameter transform snapshot")
        entry = self.catalogue.get(state["catalogue_name"])
        if entry is None:
            raise ValueError("Unknown shipped parameter transform")
        source = str(entry.get("code", ""))
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != state["definition_sha256"]:
            raise ValueError("Shipped parameter transform definition changed")
        if not isinstance(state["node_uid"], str) or not state["node_uid"]:
            raise ValueError("Missing parameter transform native node UID")
        return source

    def set_state(self, state: dict) -> None:
        """Configure the trusted definition before the codec routes exact scalar UIDs."""
        source = self._verified_session_source(state)
        if self.model_name != state["catalogue_name"] or self.function != source:
            self.model_name = state["catalogue_name"]
        node = self._model._node
        if list(node.inputs) != state["input_names"] or list(node.outputs) != state["output_names"]:
            raise ValueError("Parameter transform native topology changed")
        input_uids = state["input_port_uids"]
        if (
            not isinstance(input_uids, dict)
            or list(input_uids) != list(node.inputs)
            or any(not isinstance(uid, str) or not uid for uid in input_uids.values())
        ):
            raise ValueError("Invalid parameter transform native input identities")
        node.set_uid(state["node_uid"])
        for name, port in node.inputs.items():
            port.set_uid(input_uids[name])

    @property
    def _parameters(self) -> typing.List[chisurf.core.fitting.parameter.FittingParameter]:
        """List of all parameters from the wrapped model node."""
        return self._model.parameters_all

    @_parameters.setter
    def _parameters(self, v):
        """No-op setter to satisfy the read-only property protocol."""
        pass

    @classmethod
    def from_session_state(cls, fit: Fit, state: dict):
        """Construct only the saved trusted definition in a staged session."""
        return cls(fit, session_state=state)

    def __init__(
        self,
        fit: Fit,
        function: str | None = None,
        *args,
        session_state: dict | None = None,
        **kwargs,
    ):
        """Initialize the parameter transform model.

        Parameters
        ----------
        fit : Fit
            The fit object this model is attached to.
        function : str, optional
            Python function definition string. Defaults to the first shipped definition.
        session_state : dict, optional
            Saved declaration to validate before constructing only its definition.
        """
        self.fit = fit
        if session_state is not None:
            if function is not None:
                raise ValueError("A session definition cannot be combined with a user function")
            self._verified_session_source(session_state)
            self.model_name = session_state["catalogue_name"]
        elif function is None:
            self.select_first_catalogue_entry()
            if not self.model_name:
                self.function = "def f(x): return x"
        else:
            self.function = function
        super().__init__(fit, *args, **kwargs)
        if session_state is not None:
            self.set_state(session_state)

    def __str__(self):
        """Return a string summary of the model function and parameters."""
        s = "\n"
        s += "Model: Parameter transform\n"
        s += "\n"
        s += "Function:\n"
        s += str(self._function)
        s += "\n"
        s += "Parameter \t Value \t Bounds \t Output \t Linked\n"
        for p in self.parameters_all:
            s += f"{p.name} \t {p.value:.4f} \t {p.bounds} \t {p.fixed} \t {p.is_linked} \n"
        s += "\n"
        return s

    def __getitem__(self, key):
        """Return a slice of the model curve as ``(x, y)``.

        Parameters
        ----------
        key : slice
            Slice object specifying start/stop/step.

        Returns
        -------
        tuple of numpy.ndarray
            Sliced ``(x, y)`` arrays.
        """
        start = key.start
        stop = key.stop
        step = 1 if key.step is None else key.step
        return self.x[start:stop:step], self.y[start:stop:step]
