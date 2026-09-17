"""A named catalogue of model sources, shared by every model that offers one.

A model that lets the user pick from a list of equations (or of code blocks) is a
*catalogue* plus whichever entry is selected. That was implemented inside the Qt
widget for every such model, which is why the compute side could not select an
entry and a view spec could not offer the picker: the catalogue is **data**, so it
belongs here.

With this mixin the picker needs no bespoke widget -- a ``choice`` over
:attr:`~EquationCatalogueMixin.catalogue_names` writing
:attr:`~EquationCatalogueMixin.model_name` is enough.
"""

from __future__ import annotations

import pathlib

import chisurf.logging
from chisurf import typing


class EquationCatalogueMixin:
    """Selectable catalogue of model sources loaded from a YAML/JSON file.

    State is created on first use rather than in an ``__init__``: the mixin is added
    to models with their own constructors (and their own ``__getattr__``), so
    depending on a cooperative ``super().__init__`` chain meant a host that did not
    call it raised ``AttributeError`` on the first catalogue access.
    """

    def _catalogue_state(self) -> dict:
        """Return the mixin's own state, creating it on first access."""
        state = self.__dict__.get("_catalogue_state_dict")
        if state is None:
            state = {"models": {}, "path": None, "name": ""}
            self.__dict__["_catalogue_state_dict"] = state
        return state

    #: Default equation catalogue, resolved next to the module declaring it.
    #:
    #: Every parse model is a *catalogue* of equations plus whichever one is
    #: selected, and the catalogue was read, held and applied entirely by the Qt
    #: widget -- so the compute model had `_models = dict()` that nothing ever
    #: filled, and picking a model was not something a script or a view spec could
    #: do. It is data (a YAML file), so it belongs here.
    catalogue_file: typing.Optional[str] = None

    #: Catalogue entry key holding the source, and the model property it is assigned
    #: to. A parse model stores an ``equation:`` in ``func``; a parameter transform
    #: stores a Python ``code:`` block in ``function``. Same catalogue, same picker,
    #: different payload -- so the difference is two strings rather than a second
    #: implementation.
    catalogue_source_key: str = "equation"
    catalogue_target_attr: str = "func"

    @property
    def catalogue_path(self) -> typing.Optional[pathlib.Path]:
        """Absolute path of the catalogue currently loaded (or the declared default)."""
        path = self._catalogue_state()["path"]
        if path is not None:
            return path
        return self._default_catalogue_path()

    def _default_catalogue_path(self) -> typing.Optional[pathlib.Path]:
        """Resolve :attr:`catalogue_file` against the module that declares it."""
        import inspect

        for cls in type(self).__mro__:
            name = cls.__dict__.get("catalogue_file")
            if name:
                try:
                    return pathlib.Path(inspect.getfile(cls)).parent / name
                except TypeError:  # pragma: no cover - builtins have no file
                    return None
        return None

    @property
    def catalogue(self) -> dict:
        """The catalogue: ``{name: {<source key>, initial, description}}``.

        Loaded lazily from :attr:`catalogue_path` so a model that declares one
        needs no explicit load, and an unreadable file degrades to an empty
        catalogue rather than breaking construction.
        """
        state = self._catalogue_state()
        if not state["models"]:
            path = self.catalogue_path
            if path is not None:
                self.load_catalogue(path)
        return state["models"]

    @property
    def catalogue_names(self) -> list:
        """Names in the catalogue, in file order -- an ``options_source`` for a choice."""
        return list(self.catalogue.keys())

    def load_catalogue(self, path) -> None:
        """Read an equation catalogue from a YAML file.

        Parameters
        ----------
        path : str or pathlib.Path
            YAML mapping of model name to ``{equation, initial, description}``.
        """
        import yaml

        path = pathlib.Path(path)
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception as exc:
            chisurf.logging.warning(f"ParseModel: cannot read catalogue {path} ({exc})")
            data = {}
        state = self._catalogue_state()
        state["models"] = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        state["path"] = path

    @property
    def model_name(self) -> str:
        """Name of the selected catalogue entry (empty when none is selected)."""
        return self._catalogue_state()["name"]

    @model_name.setter
    def model_name(self, v: str) -> None:
        """Select a catalogue entry: set its equation *and* its initial values."""
        name = str(v or "")
        entry = self.catalogue.get(name)
        if entry is None:
            chisurf.logging.warning(f"ParseModel: no catalogue entry named {name!r}")
            return
        self._catalogue_state()["name"] = name
        setattr(self, self.catalogue_target_attr, str(entry.get(self.catalogue_source_key, "x*0")))
        self.apply_initial_values(name)

    @property
    def description(self) -> str:
        """Description of the selected catalogue entry, for the editor to show."""
        entry = self.catalogue.get(self._catalogue_state()["name"]) or {}
        return str(entry.get("description", "") or "")

    def select_first_catalogue_entry(self) -> None:
        """Select entry 0 unless something is selected already.

        A model with a catalogue and nothing selected has no source at all -- a
        parse model computes a flat zero, a parameter transform has no function --
        so every editor opened on an empty picker. The hand-written widgets hid this
        by defaulting their combo box to index 0; hosts call this instead.
        """
        if not self.model_name and self.catalogue_names:
            self.model_name = self.catalogue_names[0]

    def apply_initial_values(self, name: str = None) -> None:
        """Set the parsed parameters to the catalogue entry's ``initial:`` values.

        A name in ``initial:`` that the equation does not use is skipped rather
        than raising -- a catalogue is hand-edited, and one stale key should not
        stop the rest of the entry being applied.

        Parameters
        ----------
        name : str, optional
            Catalogue entry; the selected one when omitted.
        """
        entry = self.catalogue.get(name or self._catalogue_state()["name"]) or {}
        # ``parameter_dict`` is the usual index, but a model may hold its parameters
        # elsewhere (a parameter transform keeps them on its node), so fall back to
        # naming them from whatever list it does expose.
        params = dict(getattr(self, "parameter_dict", {}) or {})
        if not params:
            for p in getattr(self, "_parameters", None) or []:
                name_ = str(getattr(p, "name", "") or "")
                if name_:
                    params.setdefault(name_, p)
        for key, value in (entry.get("initial") or {}).items():
            target = params.get(str(key))
            if target is None:
                chisurf.logging.warning(
                    f"ParseModel: initial value for unknown parameter {key!r} ignored"
                )
                continue
            try:
                target.value = float(value)
            except (TypeError, ValueError):
                chisurf.logging.warning(
                    f"ParseModel: initial value {value!r} for {key!r} is not a number"
                )
