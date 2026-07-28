from __future__ import annotations
from chisurf import typing

import chisurf.core.base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import chisurf.core.models

from chisurf.core.experiments.core.reader import ExperimentReader, ExperimentReaderController


class Experiment(chisurf.core.base.Base):
    """Lightweight registry of models and readers for a ChiSurf experiment.

    An :class:`Experiment` keeps track of which model classes and
    :class:`chisurf.core.experiments.core.reader.ExperimentReader` instances belong to
    a conceptual experiment type. Higher level GUIs use this information to
    decide which data can be loaded and which models are applicable.

    Attributes
    ----------
    model_classes : list of type[chisurf.core.models.Model]
        Registered model classes associated with the experiment.
    readers : list of chisurf.core.experiments.core.reader.ExperimentReader
        Registered readers (possibly attached via controllers).
    hidden : bool
        If *True*, the experiment is hidden from interactive UIs.

    Examples
    --------
    Create a minimal experiment without models or readers:

    >>> from chisurf.core.experiments.core.experiment import Experiment
    >>> exp = Experiment(name="Test")
    >>> exp.name
    'Test'
    >>> exp.model_classes
    []
    >>> exp.readers
    []
    """

    hidden: bool = False

    @property
    def readers(self) -> typing.List[ExperimentReader]:
        """List of :class:`ExperimentReader` instances registered for this experiment."""
        return self.get_readers()

    @property
    def reader_names(self) -> typing.List[str]:
        """Human-readable names of all registered readers."""
        return self.get_reader_names()

    @property
    def model_classes(self) -> typing.List[typing.Type[chisurf.core.models.Model]]:
        """List of registered model classes."""
        return list(self._model_classes)

    @property
    def model_names(self) -> typing.List[str]:
        """Human-readable names of all registered model classes."""
        return self.get_model_names()

    def add_model_class(self, model: typing.Type[chisurf.core.models.Model]):
        """Register a single model class with this experiment.

        Parameters
        ----------
        model : type
            A :class:`chisurf.core.models.Model` subclass to register.
        """
        if model is None:
            return
        if model not in self.model_classes:
            self._model_classes.append(model)

    def add_model_classes(
            self,
            models: typing.List[
                typing.Type[chisurf.core.models.Model]
            ]
    ):
        """Register multiple model classes at once.

        Parameters
        ----------
        models : list of type
            List of :class:`chisurf.core.models.Model` subclasses.
        """
        for model in models:
            self.add_model_class(model)

    def add_reader(
            self,
            reader: ExperimentReader,
            controller: ExperimentReaderController = None
    ):
        """Register a single reader (optionally with a controller).

        Parameters
        ----------
        reader : ExperimentReader
            The reader instance to register.
        controller : ExperimentReaderController, optional
            Associated controller.
        """
        if reader not in self.readers:
            # Assigning None would discard a controller factory registered by
            # the caller for lazy construction, so only set a real controller.
            if controller is not None:
                reader.controller = controller
            self._readers.append(reader)

    def add_readers(
            self,
            readers: typing.List[
                typing.Tuple[
                    ExperimentReader,
                    ExperimentReaderController
                ]
            ]
    ):
        """Register multiple reader/controller pairs.

        Parameters
        ----------
        readers : list of tuple
            Each element is ``(reader, controller)``.
        """
        for reader, controller in readers:
            self.add_reader(
                reader,
                controller
            )

    def get_readers(self) -> typing.List[ExperimentReader]:
        """Return all :class:`ExperimentReader` instances for this experiment.

        Internally, ``_readers`` may hold either readers directly or
        :class:`ExperimentReaderController` objects; in the latter case the
        underlying :attr:`experiment_reader` is returned.
        """
        readers = list()
        for v in self._readers:
            if isinstance(
                    v,
                    ExperimentReader
            ):
                readers.append(v)
            elif isinstance(
                    v,
                    ExperimentReaderController
            ):
                readers.append(v.experiment_reader)
        return readers

    def get_reader_names(self) -> typing.List[str]:
        """Return the names of all registered readers."""
        names = list()
        for s in self.readers:
            if s is not None:
                names.append(s.name)
        return names

    def get_model_classes(self, data=None) -> typing.List[typing.Type[chisurf.core.models.Model]]:
        """Return the model classes applicable to *data*.

        An experiment may cover datasets of more than one shape — PDA reads
        two-colour S1S2 histograms and three-colour burst tables through the
        same reader — so the model list is filtered by each class'
        :meth:`~chisurf.core.models.model.Model.supports_data`.

        Parameters
        ----------
        data : object, optional
            Dataset a fit would be built on. When omitted, every registered
            model class is returned.

        Returns
        -------
        list of type
            The registered model classes that accept *data*.
        """
        if data is None:
            return self.model_classes
        applicable = list()
        for model_class in self.model_classes:
            if model_class is None:
                continue
            supports = getattr(model_class, "supports_data", None)
            try:
                # A model that cannot answer is kept: the filter exists to hide
                # certain failures, not to hide models with an unusual base.
                if supports is None or supports(data):
                    applicable.append(model_class)
            except Exception:
                applicable.append(model_class)
        return applicable

    def get_model_names(self, data=None) -> typing.List[str]:
        """Return the names of the model classes applicable to *data*.

        Parameters
        ----------
        data : object, optional
            Dataset a fit would be built on; see :meth:`get_model_classes`.
        """
        names = list()
        for s in self.get_model_classes(data):
            if s is not None:
                names.append(str(s.name))
        return names

    def __getstate__(self):
        """Serialize the experiment state for pickling.

        Returns
        -------
        dict
            Pickle-friendly state dictionary.
        """
        state = super().__getstate__()
        state['_model_classes'] = self._model_classes
        state['_readers'] = self._readers
        state['name'] = self.__dict__['name']
        state['hidden'] = self.hidden
        return state

    def __str__(self):
        """Human-readable string representation."""
        return self.__class__.__name__ + "(" + self.name + ")"

    def __init__(
            self,
            name: str = '',
            hidden: bool = False,
            *args,
            **kwargs
    ):
        """Initialize an experiment registry entry.

        Parameters
        ----------
        name : str
            Human-readable experiment name.
        hidden : bool
            If *True*, the experiment is hidden from user interfaces.
        """
        super().__init__(*args, name=name, **kwargs)
        self.hidden = hidden
        self._model_classes = list()
        self._readers = list()
