from chisurf import logging
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models import global_model
from chisurf.core.models.model import Model

from .model import *


def _join_bff_session(node):
    """Register a parse-built node with bff's default session.

    chinet's global object database picked up every constructed node,
    which is what let a project save find it; bff's Session is the
    registry and registers nothing by construction (see
    :mod:`chisurf.core.parameter`), so the node is added explicitly,
    keyed by its uid (adding the same key twice is idempotent).
    """
    try:
        import IMP.bff as bff
    except ImportError:
        return
    bff.get_session().add_node(node.get_uid(), node)


def function_to_model_decorator(**kws):
    """Create a decorator that wraps a callable into a `Model` subclass.

    The returned decorator turns a Python callable into a
    :class:`chisurf.core.models.Model` subclass that is backed by a
    :class:`chisurf.core.nodes.PythonNode` (an ``IMP.bff`` node). Keyword arguments passed to this factory are forwarded to the
    model constructor.

    Parameters
    ----------
    **kws
        Keyword arguments forwarded to :class:`chisurf.core.models.Model` when the
        generated class is instantiated.

    Returns
    -------
    callable
        A decorator. When applied to a function it returns a new
        :class:`chisurf.core.models.Model` subclass.

    Examples
    --------
    Create a model class from a simple callback function. The resulting
    class can later be instantiated by the fitting framework.

    >>> def callback():
    ...     pass
    >>> ModelClass = function_to_model_decorator()(callback)
    >>> isinstance(ModelClass, type)
    True
    """

    def decorator(func):
        """Wrap ``func`` in a ``ModelDecorator`` class and return it.

        Parameters
        ----------
        func : callable
            The Python callable to wrap.

        Returns
        -------
        ModelDecorator
            A dynamically created :class:`chisurf.core.models.Model` subclass.
        """

        class ModelDecorator(Model):
            def __init__(self, *args, **kwargs):
                """Initialize the model decorator with a bff node and parameters.

                Parameters
                ----------
                *args
                    Positional arguments forwarded to the parent Model.
                **kwargs
                    Keyword arguments forwarded to the parent Model, updated
                    with the factory-level keyword arguments from
                    :func:`function_to_model_decorator`.
                """
                logging.info("ModelDecorator.__init__")
                logging.debug(f"args: {args}")
                logging.debug(f"kwargs: {kwargs}")
                logging.debug(f"kws: {kws}")
                logging.debug("updating kwargs with kws")
                kwargs.update(kws)
                logging.debug("updating kwargs finished")
                super().__init__(*args, **kwargs)
                logging.debug("super called.")
                import chisurf.core.nodes as cn_nodes

                self._node = cn_nodes.function_to_node(func)
                # chinet registered every constructed node with its global
                # database; bff's session is the registry, so the node is
                # added here (its ports join through the FittingParameters
                # below and deduplicate with the node on save).
                _join_bff_session(self._node)
                logging.debug(f"_node: {self._node}")
                logging.debug(f"func: {func}")
                self.node_parameters = list()
                logging.debug(f"node_parameters: {self.node_parameters}")
                self.make_parameters()
                logging.debug("make_parameters finished.")

            def make_parameters(self):
                """Create FittingParameters from the node's ports."""
                ports = self._node.get_ports()
                logging.debug(f"ports: {ports}")
                logging.debug(f"ports.keys(): {ports.keys()}")
                logging.debug(f"ports.values(): {ports.values()}")
                for port_key in ports:
                    logging.debug(f"port_key: {port_key}")
                    port = ports[port_key]
                    logging.debug(f"port: {port}")
                    p = FittingParameter(port=port, name=port_key)
                    logging.debug(f"p: {p}")
                    logging.debug(f"p.name: {p.name}")
                    self.node_parameters.append(p)
                    logging.debug(f"node_parameters: {self.node_parameters}")
                self.find_parameters()
                logging.debug("find_parameters finished.")

                # output ports act as fixed parameters
                logging.debug(f"outputs: {self._node.outputs}")
                logging.debug("fixing output ports")
                for port_key in self._node.outputs:
                    logging.debug(f"port_key: {port_key}")
                    self.parameters_all_dict[port_key].fixed = True
                    logging.debug(f"fixed: {self.parameters_all_dict[port_key].fixed}")
                logging.debug("fixed output ports finished.")

            def _update_model(self, **kwargs):
                """Evaluate the bff node to compute the model output."""
                logging.debug("update_model called.")
                logging.debug("evaluating")
                self._node.evaluate()
                logging.debug("evaluate finished.")

            def update(self, **kwargs) -> None:
                """Refresh parameters and re-evaluate the model."""
                # Values-only inside a freeze, as Model.update: the
                # structure walk is a contracted no-op there.
                if self.__dict__.get("_frozen_structure") is None:
                    self.find_parameters()
                self._update_model()

        return ModelDecorator

    return decorator


def inject_user_models():
    import importlib
    import os
    import sys

    from chisurf import logging
    from chisurf.core.settings.path_utils import get_path

    models_dir = get_path("settings") / "models"
    if not models_dir.exists():
        return

    overrides = {}
    for filename in os.listdir(models_dir):
        if not filename.endswith(".py"):
            continue
        if "__override__" in filename:
            parts = filename.replace(".py", "").split("__override__")
            if len(parts) == 2:
                module_name, timestamp = parts
                if module_name not in overrides or overrides[module_name]["timestamp"] < timestamp:
                    overrides[module_name] = {"timestamp": timestamp, "path": models_dir / filename}

    for module_name, info in overrides.items():
        try:
            logging.info(f"Injecting user model override for {module_name} from {info['path']}")
            # Import original module
            module = importlib.import_module(module_name)
            # Exec the override code in the module's dict
            with open(info["path"]) as f:
                code = f.read()
            exec(code, module.__dict__)
        except Exception as e:
            logging.error(f"Failed to inject model override for {module_name}: {e}")


# Run injection on startup
inject_user_models()
