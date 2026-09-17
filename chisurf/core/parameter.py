from __future__ import annotations
from chisurf import typing

import abc
import inspect
import json
import math

import numpy as np

import chisurf.core.base
import chisurf.core.support.decorators

# The parameter runtime is IMP.bff's Port (phase 3 of removing chinet from
# chisurf: bff absorbed chinet's Port/Node/Session and reads/writes chinet's
# session format, so old projects open unchanged). The vendored chinet module
# is gone; every layer that used it -- the node editor, the graph layer, the
# model decorator, the parameter transform and the macros -- runs on bff now,
# and a :class:`Parameter`'s backing port is an ``IMP.bff.GraphPort``.
#
# IMP.bff is not a dependency of an environment that never fits anything,
# so the import is guarded rather than hard: this module imports cleanly
# without it and the first Parameter that needs a port says what is missing
# (the same try/except ImportError discipline project.py applies to its
# optional session persistence).
try:
    import IMP.bff as _bff
    # A partial IMP install (data-only directories, a namespace-package stub)
    # imports but has no runtime in it; that is "absent" for this module's
    # purposes, not a working IMP.bff that will fail one attribute later.
    if not hasattr(_bff, "GraphPort"):
        raise ImportError("IMP.bff is present but carries no Port runtime")
except ImportError as _exc:  # pragma: no cover - env without IMP
    # ``except ... as`` deletes its binding at the end of the block, so the
    # error is kept under its own name for the message raised at first use.
    _bff = None
    _bff_import_error = _exc


T = typing.TypeVar('T', bound='Parameter')


def _bump_fit_structure_version() -> None:
    """Invalidate cached fit factor graphs after a structural change.

    Linking, unlinking, fixing and freeing a parameter all change *which*
    variables a fit has and which datasets they reach, so any
    :class:`~chisurf.core.fitting.factorgraph.FactorGraph` built earlier no
    longer describes the fit. The import is deferred because the fitting package
    imports this module.
    """
    try:
        from chisurf.core.fitting import factorgraph
    except Exception:
        # Parameters are usable without the fitting stack (bare tools, tests);
        # nothing caches a graph in that case, so there is nothing to invalidate.
        return
    factorgraph.bump_structure_version()


def _owning_class_name() -> typing.Optional[str]:
    """Best-effort class name of the object constructing the current ``Parameter``.

    Walks caller frames looking for the first ``self`` local that is *not* a
    ``Parameter`` instance — i.e. past ``Parameter.__init__`` and any
    subclass ``__init__`` (e.g. ``FittingParameter``) that simply forwards to
    it, up to the model/group whose ``__init__`` body actually wrote
    ``self._x = FittingParameter(name="x", ...)``. This mirrors the "class"
    context ``build_tools/dev_utils/export_fitting_parameters.py`` records for
    the same call site, so the two agree on what a parameter is scoped to.
    """
    frame = inspect.currentframe()
    try:
        f = frame.f_back if frame else None
        for _ in range(8):
            if f is None:
                return None
            owner = f.f_locals.get("self")
            if owner is not None and not isinstance(owner, Parameter):
                return type(owner).__name__
            f = f.f_back
    finally:
        del frame
    return None


@chisurf.core.support.decorators.register
class Parameter(chisurf.core.base.Base):
    """Scalar parameter backed by a low-level :mod:`IMP.bff` port.

    A :class:`Parameter` represents a single scalar value used in a model
    or fit. The value can be

    - stored directly in an underlying :class:`IMP.bff.GraphPort`,
    - computed dynamically from a Python callable, or
    - linked to another :class:`Parameter`.

    Bounds and a fixed flag are forwarded to the underlying port.

    Examples
    --------
    Create a simple parameter and use it in arithmetic expressions:

    >>> from chisurf.core.parameter import Parameter
    >>> p = Parameter(name="amp", value=1.5)
    >>> float(p)
    1.5
    >>> q = p + 2.0
    >>> float(q)
    3.5
    """

    @staticmethod
    def check_recursive_link(current, target):
        """Return ``True`` if linking *target* as a follower of *current* would
        break the directed-acyclic-graph (DAG) invariant of the link graph.

        The proposed assignment ``target.link = current`` adds the dependency
        edge ``target -> current``; it is rejected when *current* can already
        reach *target* through existing links.

        The cycle detection itself lives in the port runtime -- the
        underlying :class:`IMP.bff.GraphPort` enforces the DAG with Kahn's
        algorithm whenever a link is created (see
        :meth:`IMP.bff.GraphPort.would_create_cycle`). This
        method simply delegates to it on the backing ports so the logic is
        defined once. It is retained as a side-effect-free predicate for GUI
        call sites that want to validate a link *before* attempting it.
        Parameters
        ----------
        current : Parameter
            The prospective master (link target).
        target : Parameter
            The follower whose ``.link`` would be set to *current*.

        Returns
        -------
        bool
            ``True`` if the assignment would introduce a cycle, else ``False``.
        """
        if current is None or target is None:
            return False
        # target.link = current  <=>  target._port.set_link(current._port)
        return bool(target._port.would_create_cycle(current._port))

    @property
    def fit_idx(self):
        """Find the fitting index of this parameter, or -1 if it is not used in a fit."""
        import chisurf.core.fitting
        idxs = chisurf.core.fitting.find_fit_idx_of_parameter(self)
        if len(idxs) == 0:
            return -1
        if len(idxs) > 1:
            chisurf.logging.warning("Ambiguous link call. Fitting parameter used in multiple fits")
        fit_idx_self = idxs[0]
        return fit_idx_self

    @property
    def name(self) -> str:
        """Parameter name."""
        return self._name

    @name.setter
    def name(self, v: str):
        """Set the parameter name and update the underlying port."""
        self._port.name = v
        self._name = v

    @property
    def bounds(self) -> typing.Tuple[float, float]:
        """Lower and upper bounds of the parameter as a 2-tuple.

        The values are stored on the underlying :class:`IMP.bff.GraphPort`.
        ``(None, None)`` is reported while enforcement is off, as chinet's
        port did -- bff's port reports ``(nan, nan)`` there, and the
        difference is adapted here so consumers (and :meth:`get_state`'s
        ``None`` -> +/-inf normalisation) never see a NaN.
        """
        if not self._port.bounded:
            return (None, None)
        lb, ub = self._port.bounds
        return (None if lb != lb else float(lb),
                None if ub != ub else float(ub))

    @bounds.setter
    def bounds(self, b: typing.Tuple[float, float]):
        """Set the lower and upper bounds."""
        self._port.bounds = np.array(b, dtype=np.float64)

    def _stored_bound(self, i: int, default: float) -> float:
        """Return bound *i* as stored on the port, enforced or not."""
        # bff's port stores lb/ub whether or not enforcement is on and
        # reports them through get_lower_bound()/get_upper_bound(). A NaN
        # is bff's "not a bound" marker, so treat it as unset.
        stored = float(self._port.get_lower_bound() if i == 0
                       else self._port.get_upper_bound())
        return default if stored != stored else stored

    @property
    def lb(self) -> float:
        """Lower bound.

        ``__init__`` has always accepted ``lb``/``ub`` (158 call sites pass them),
        but there were no matching properties — so ``p.lb = 0.01`` silently
        created a dead instance attribute and the bound was never applied, while
        ``p.lb`` raised ``AttributeError``. These accessors close that gap; the
        bounds themselves live on the underlying :class:`IMP.bff.GraphPort`.
        """
        # Port.bounds reports (None, None) while enforcement is OFF even though
        # the values are stored, which would make lb/ub a lossy round-trip. Read
        # the stored bound so `p.lb = x; p.lb == x` holds regardless of
        # bounds_on; whether it is *enforced* is bounds_on's job.
        return self._stored_bound(0, float("-inf"))

    @lb.setter
    def lb(self, v: float):
        """Set the lower bound, leaving the upper bound untouched."""
        self.bounds = (float(v), self.ub)

    @property
    def ub(self) -> float:
        """Upper bound. See :attr:`lb`."""
        return self._stored_bound(1, float("inf"))

    @ub.setter
    def ub(self, v: float):
        """Set the upper bound, leaving the lower bound untouched."""
        self.bounds = (self.lb, float(v))

    @property
    def bounds_on(self):
        """Whether bounds are currently enforced on the parameter."""
        return self._port.bounded

    @bounds_on.setter
    def bounds_on(self, v):
        """Enable or disable bound enforcement."""
        self._port.bounded = bool(v)

    @property
    def value(self) -> float:
        """Current scalar value of the parameter.

        If a callable was passed at construction time, it is evaluated each
        time this property is accessed. The result is clamped to bounds (if
        enabled) and, when the parameter is not fixed, written back to the
        underlying port.

        If the parameter is linked to another :class:`Parameter`, the link
        takes precedence and the callable is ignored.
        """
        # Inside a fit or sampling run every flag consulted below is fixed by
        # contract (see factorgraph.frozen_structure), so the six property
        # dispatches -- three at this level, three more into the port -- that a
        # read otherwise costs collapse to one dict lookup. Reads outnumber
        # writes by orders of magnitude and this is the single largest cost of a
        # decay model evaluation, above the convolution itself.
        frozen = self.__dict__.get("_frozen_flags")
        if frozen is not None:
            linked, callable_, bounded, lb, ub, fixed_ = frozen
            if linked:
                # A follower is written through its *port* when the master
                # moves, which never reaches this object, so it is read fresh.
                pv = self._port.value
                return pv if type(pv) is float else float(np.atleast_1d(pv)[0])
            if callable_ is None:
                # Most of a model's parameters -- instrument response, detection
                # geometry, background, everything not being optimised -- hold
                # the same value for the entire run and are re-read on every
                # evaluation. The value setter drops this entry, so a cached
                # read can only ever be one nothing has written since.
                cached = self.__dict__.get("_frozen_value")
                if cached is not None:
                    return cached
                pv = self._port.value
                v = pv if type(pv) is float else float(np.atleast_1d(pv)[0])
                if not bounded:
                    self.__dict__["_frozen_value"] = v
                    return v
                raw = v
                if lb == lb and v < lb:
                    v = lb
                if ub == ub and v > ub:
                    v = ub
                if v != raw and not self.fixed:
                    f = self._port.fixed
                    self._port.fixed = False
                    self._port.value = v
                    self._port.fixed = f
                    # The write-back cleared the entry; the clamped value is
                    # what every later read must see.
                    self.__dict__["_frozen_flags"] = frozen
                self.__dict__["_frozen_value"] = v
                return v

        # If linked, defer entirely to linked parameter's port value.
        if self.is_linked:
            pv = self._port.value
            # Port.value already returns a Python float for scalar ports; only
            # pay for atleast_1d when it does not.
            return pv if type(pv) is float else float(np.atleast_1d(pv)[0])

        # Compute from callable if available.
        if self._callable:
            try:
                v = float(np.atleast_1d(self._callable())[0])
            except Exception:
                v = float(np.atleast_1d(self._port.value)[0])
            raw = None  # callable result always differs from the stored value
        else:
            pv = self._port.value
            v = pv if type(pv) is float else float(np.atleast_1d(pv)[0])
            raw = v

        # Apply bounds on read for both callable and non-callable parameters
        # if bounds are enabled. This matches the behaviour expected in the
        # unit tests (``test_bounds``), where reading ``value`` after an
        # out-of-bounds assignment should return the clamped value.
        if self.bounds_on:
            lb, ub = self.bounds
            # An unset side is None -- one bound can be edited while the other
            # has not been given -- and None is unbounded, not an error.
            if lb is not None and np.isfinite(lb):
                v = max(lb, v)
            if ub is not None and np.isfinite(ub):
                v = min(ub, v)

        # Write the clamped value back to the port when the parameter is not
        # fixed, so subsequent reads remain consistent.
        #
        # Only write when the value actually changed. `Port.value`'s setter is
        # expensive (atleast_1d + three np.where sanitisation passes + astype +
        # clip) and, worse, calls update_attached_node(), so an unconditional
        # write made every parameter *read* invalidate the node graph. In a fit
        # this dominated: reads outnumber writes by orders of magnitude and the
        # value is unchanged unless a bound actually clamped it.
        # ``v != raw`` is a float compare; ``self.fixed`` crosses into the port.
        # Testing the cheap one first skips the port read entirely whenever no
        # bound clamped the value, which is nearly every read.
        if v != raw and not self.fixed:
            f = self._port.fixed
            self._port.fixed = False
            self._port.value = v
            self._port.fixed = f

        return v

    @value.setter
    def value(self, value: float):
        """Set the parameter value.

        When the parameter was constructed from a callable, the setter is
        ignored to ensure that the callable remains the single source of
        truth.
        """
        # Any write invalidates the read cache a freeze may have populated. This
        # is the single point at which a parameter's value changes -- models
        # write through here, never into the backing port -- which is what makes
        # caching reads inside a run sound.
        if "_frozen_value" in self.__dict__:
            del self.__dict__["_frozen_value"]

        # Inside a run the structure is fixed and only values change, so the
        # dispatches that decide *how* to write are answered once at freeze
        # time rather than on every iteration. An optimiser writes each free
        # parameter every step; this was costing four calls across the binding
        # (read `fixed`, clear it, write, restore it) plus a property lookup
        # for `_callable`, where a free parameter needs exactly one write.
        #
        # A *fixed* parameter still takes the long way below: it is written
        # rarely, and forcing the value past its own fixedness is deliberate
        # behaviour that is not worth duplicating here.
        frozen = self.__dict__.get("_frozen_flags")
        if frozen is not None and frozen[1] is None and not frozen[5]:
            try:
                self._port.value = float(value)
            except (TypeError, ValueError):
                import chisurf.logging
                chisurf.logging.error(
                    f"Cannot set parameter '{self.name}' value to "
                    f"{type(value)}: {value}")
            return

        if self._callable:
            return
        
        # Ensure value is a float before passing to the low-level port.
        # This prevents access violations if a Python object (e.g. another
        # Parameter) is accidentally assigned to this property.
        try:
            val_float = float(value)
        except (TypeError, ValueError):
            import chisurf.logging
            chisurf.logging.error(f"Cannot set parameter '{self.name}' value to {type(value)}: {value}")
            return

        f = self._port.fixed
        self._port.fixed = False
        self._port.value = val_float
        self._port.fixed = f

    @property
    def link(self) -> chisurf.core.parameter.Parameter:
        """Return the linked parameter, or None if this parameter is not linked."""
        return self._link

    @link.setter
    def link(self, link: Parameter|None):
        """Link this parameter to another, or break the link by passing None.

        Parameters
        ----------
        link : Parameter or None
            The target parameter to follow, or None to unlink.
        """
        if isinstance(link, Parameter):
            if Parameter.check_recursive_link(link, self):
                raise ValueError("Cannot create a recursive link between parameters.")
            # This parameter becomes a follower (slave) of the target.
            self._link = link
            self.is_link_master = False
            if self.controller is not None:
                # Followers show the partially-checked link state.
                self.controller.set_linked(True)
            self._port.link = link._port
        elif link is None:
            # Unlink this parameter from any target. The is_link_master flag
            # is *not* modified here so that higher-level helpers (such as
            # fit-group linking) can control master semantics explicitly.
            self._link = None
            self._port.unlink()
            if self.controller is not None:
                self.controller.set_linked(False)
        # Linking rewires which datasets a parameter reaches, so every cached
        # factor graph describing this fit is now stale.
        _bump_fit_structure_version()

    @property
    def is_linked(self) -> bool:
        """Whether this parameter is linked to another parameter."""
        return bool(self._port.is_linked())

    @property
    def prior(self):
        """Prior probability distribution attached to this parameter.

        A parameter's prior generalises its bounds. The prior specification is
        stored on the underlying :class:`IMP.bff.GraphPort` (as a JSON-serialisable
        dict), so it travels with the port through pickling and JSON. When no
        smooth prior is set but a bound is active, the bound is reported as the
        equivalent :class:`~chisurf.core.fitting.priors.UniformPrior`, so a hard
        box constraint and a soft prior are described through a single concept.
        Returns ``None`` for an unbounded parameter with no prior (an improper
        flat prior).

        Setting a :class:`UniformPrior` is equivalent to setting the bounds and
        enabling them. Setting any other prior stores its spec on the port and
        updates the port's hard bounds to the prior's
        :meth:`~chisurf.core.fitting.priors.Prior.support` (so a truncated prior
        also constrains the optimiser). Setting ``None`` clears both the prior
        and the active bound.

        Returns
        -------
        chisurf.core.fitting.priors.Prior or None
            The effective prior, or ``None``.
        """
        from chisurf.core.fitting.priors import prior_from_state, UniformPrior
        # A live prior object (e.g. a callback prior that cannot be serialised)
        # takes precedence; otherwise rebuild from the port's persisted spec.
        # ``getattr`` guards the pickle path, where ``__setstate__`` bypasses
        # ``__init__`` and the slot may not exist yet.
        live = getattr(self, "_prior", None)
        if live is not None:
            return live
        spec = getattr(self._port, "prior", None)
        pr = prior_from_state(spec) if spec else None
        if pr is not None:
            return pr
        if self.bounds_on:
            lb, ub = self.bounds
            return UniformPrior(float(lb), float(ub))
        return None

    @prior.setter
    def prior(self, value):
        """Attach, replace or clear this parameter's prior (see :attr:`prior`)."""
        from chisurf.core.fitting.priors import Prior, UniformPrior, as_prior
        # Accept a Prior, a state dict, or a bare callable (the most general
        # prior form) -- callables are wrapped as a CallablePrior by as_prior.
        if value is not None and not isinstance(value, Prior):
            value = as_prior(value)
        if value is None:
            self._prior = None
            self._port.prior = None
            self.bounds_on = False
            return
        if not isinstance(value, Prior):
            raise TypeError("prior must be a Prior, a callable, a state dict, or None")
        if isinstance(value, UniformPrior):
            # A box prior *is* a bound: fold it back onto the port so existing
            # bounds machinery (optimiser transforms, GUI) keeps working.
            self._prior = None
            self._port.prior = None
            self.bounds = (value.lb, value.ub)
            self.bounds_on = True
            return
        # Smooth prior. Keep the live object (needed for callback priors, which
        # cannot round-trip through JSON) and mirror a serialisable spec onto
        # the port so distribution priors persist. Mirror the prior's hard
        # support onto the port bounds so a truncated support also constrains
        # the optimiser while the residual term supplies the soft pull.
        self._prior = value
        spec = value.get_state()
        # A callback (or a product containing one) is runtime-only: its spec
        # cannot be reconstructed, so it is not written to the port.
        from chisurf.core.fitting.priors import prior_from_state
        self._port.prior = spec if prior_from_state(spec) is not None else None
        lb, ub = value.support()
        if math.isfinite(lb) or math.isfinite(ub):
            self.bounds = (lb, ub)
            self.bounds_on = True
        else:
            self.bounds_on = False


    @property
    def fixed(self):
        """Boolean flag indicating whether the parameter is fixed."""
        return self._port.fixed

    @fixed.setter
    def fixed(self, v: bool):
        """Freeze or unfreeze the parameter value."""
        was = bool(self._port.fixed)
        self._port.fixed = bool(v)
        if was != bool(v):
            # A freeze stamps `fixed` into `_frozen_flags` so the write path
            # need not ask the port on every iteration. Dropping the stamp
            # here is what makes that sound by construction rather than by
            # convention: every caller that toggles fixedness today does so
            # outside a frozen block (support_plane and the evidence
            # conditioning in engine.py both re-enter `fit.run()`, which
            # re-freezes), but a future one that does it inside would
            # otherwise leave the write path believing a fixed parameter is
            # free -- and the port would then silently refuse the write.
            self.__dict__.pop("_frozen_flags", None)
            self.__dict__.pop("_frozen_value", None)
            # Freezing or freeing a parameter adds or removes a variable, so
            # cached factor graphs no longer describe this fit.
            _bump_fit_structure_version()

    def __add__(self, other: T) -> T:
        """Return a new parameter whose value is ``self + other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a + b)
        )

    def __mul__(self, other: T) -> T:
        """Return a new parameter whose value is ``self * other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a * b)
        )

    def __truediv__(self, other: T) -> T:
        """Return a new parameter whose value is ``self / other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a / b)
        )

    def __floordiv__(self, other: T) -> T:
        """Return a new parameter whose value is ``self // other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a // b)
        )

    def __sub__(self, other: T) -> T:
        """Return a new parameter whose value is ``self - other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a - b)
        )

    def __mod__(self, other: T) -> T:
        """Return a new parameter whose value is ``self % other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a % b)
        )

    def __pow__(self, other: T) -> T:
        """Return a new parameter whose value is ``self ** other``."""
        a = self.value
        b = other.value if isinstance(other, Parameter) else other
        return self.__class__(
            value=(a ** b)
        )

    def __invert__(self) -> T:
        """Return a new parameter whose value is ``1.0 / self``."""
        a = self.value
        return self.__class__(
            value=(1./a)
        )

    def __float__(self):
        """Convert the parameter value to a Python float."""
        return float(self.value)

    def __repr__(self):
        """Return a compact string representation of the parameter value.

        For integer-like values we avoid a trailing ``.0`` so that tests
        expecting ``"22"`` rather than ``"22.0"`` continue to pass.
        """

        v = float(self.value)
        if v.is_integer():
            return str(int(v))
        return repr(v)

    def __abs__(self):
        """Return a new parameter whose value is ``abs(self)``."""
        return self.__class__(
            value=self.value.__abs__()
        )

    def __getstate__(self):
        """Return the underlying port state for pickling."""
        d = json.loads(self._port.get_json())
        return {
            'port': d
        }

    def __setstate__(self, state):
        """Restore parameter state from :meth:`__getstate__` output."""
        s = json.dumps(state['port'])
        self._port.read_json(s)
        fixed = self._port.fixed
        self._port.fixed = False
        self._port.value = state['port']['value']
        self._port.fixed = fixed

    def __round__(self, n=None):
        """Return a new parameter whose value is ``round(self)``."""
        return self.__class__(
            value=self.value.__round__()
        )

    @abc.abstractmethod
    def update(self):
        """Hook for subclasses to react to external changes.

        The base :class:`Parameter` does not define an update strategy; this
        method primarily exists so GUI-aware subclasses can synchronize their
        controllers.
        """
        pass

    def __init__(self, value: float = 1.0, link: 'Parameter' = None,
                 lb: float = float("-inf"), ub: float = float("inf"),
                 bounds_on: bool = False, *args, **kwargs):
        """Initialize a :class:`Parameter` instance.

        Parameters
        ----------
        value : float or callable
            Initial value of the parameter, or a callable computing it
            dynamically.
        link : Parameter, optional
            Another parameter this one should be linked to.
        lb, ub : float, optional
            Lower and upper bounds for the value stored on the underlying
            :class:`IMP.bff.GraphPort`.
        bounds_on : bool, optional
            If *True*, the bounds are enforced on the port.
        """
        super().__init__(*args, **kwargs)
        self._name = kwargs.pop('name', '')
        self.is_output = bool(kwargs.pop('is_output', False))
        # Hint for GUIs: parameters that serve as link targets for other
        # parameters within a fit group are marked as "link masters".
        # This is purely a visual/UI role and does not affect the core
        # numerical behaviour of links handled by the underlying port.
        self.is_link_master = bool(kwargs.pop('is_link_master', False))
        # Optional free-form description used by fitting GUIs to show
        # human-readable details for a parameter.
        desc = kwargs.pop('description', "")
        registry_id = kwargs.pop('registry_id', None)
        if not desc:
            # Enrich from the shared parameter registry so the same description
            # surfaces here and in AutoForm fields. The owning class scopes the
            # lookup so two unrelated classes reusing a bare name (e.g. FRET's
            # Forster-radius "R0" vs. an unrelated model's own "R0") never
            # cross-contaminate.
            try:
                desc = chisurf.core.settings.describe_parameter(
                    self._name,
                    owner=_owning_class_name(),
                    registry_id=registry_id,
                ) or desc
            except Exception:
                pass
        self.description = desc
        port = kwargs.pop('port', None)
        if port is not None:
            self._port = port
            self._callable = None
        else:
            if _bff is None:
                raise ImportError(
                    "chisurf.core.parameter requires IMP.bff, the port "
                    "runtime that replaced chinet (phase 3 of removing "
                    "chinet), but importing it failed: "
                    f"{_bff_import_error}"
                )
            if callable(value):
                self._callable = value
                self._port = _bff.GraphPort(
                    value=np.atleast_1d(0.0).astype(np.float64),
                    name=self._name, lb=lb, ub=ub, is_bounded=bounds_on
                )
            else:
                self._callable = None
                self._port = _bff.GraphPort(
                    value=np.atleast_1d(value).astype(np.float64),
                    name=self._name, lb=lb, ub=ub, is_bounded=bounds_on
                )
        # chinet registered every constructed port with its global database,
        # which is what made project saves pick parameters up. bff's Session
        # is the registry and registers nothing by construction, so the port
        # is added here explicitly (adding twice is a no-op; a port owned by
        # a node is persisted with its node and deduplicated on save).
        if _bff is not None and isinstance(self._port, _bff.GraphPort):
            _bff.get_session().add_port(self._port)
        self._link = link
        if isinstance(link, Parameter):
            self._port.link = link._port
        self.controller = None
        # Live prior object. Serialisable priors also mirror their spec onto the
        # port (so they persist); callback priors live only here. Box
        # bounds are surfaced as a UniformPrior by the :attr:`prior` property,
        # so both this slot and the port spec stay empty for pure bounds.
        self._prior = None
        prior = kwargs.pop('prior', None)
        if prior is not None:
            self.prior = prior

    def get_state(self) -> dict:
        """Return a JSON-serializable snapshot of this parameter's state.

        The state is intentionally lightweight and focuses on the
        high-level attributes expected to round-trip in tests and project
        save/load: ``value``, ``bounds_on``, ``bounds`` and ``fixed``.
        """

        try:
            lb, ub = self.bounds
        except Exception:
            lb, ub = float("-inf"), float("inf")
        # An unbounded port reports ``None`` bounds; normalise to +/-inf so the
        # state stays a pair of plain floats.
        lb = float("-inf") if lb is None else float(lb)
        ub = float("inf") if ub is None else float(ub)
        try:
            desc = getattr(self, "description", "")
        except Exception:
            desc = ""
        state = {
            "value": float(self.value),
            "bounds_on": bool(self.bounds_on),
            "bounds": [lb, ub],
            "fixed": bool(self.fixed),
            "description": str(desc),
        }
        # Serialise a smooth prior when present. Pure box bounds are already
        # captured by ``bounds``/``bounds_on`` (the UniformPrior case), so only
        # a non-uniform prior spec (stored on the port) needs an explicit entry.
        spec = getattr(self._port, "prior", None)
        if isinstance(spec, dict) and spec:
            state["prior"] = dict(spec)
        return state

    def set_state(self, state: dict) -> None:
        """Restore parameter state from :meth:`get_state` output.

        After restoring the core scalar attributes, :meth:`update` is called
        so any attached GUI controller can refresh itself.
        """

        if not isinstance(state, dict):
            return

        try:
            if "bounds" in state:
                b = state["bounds"]
                if isinstance(b, (list, tuple)) and len(b) == 2:
                    self.bounds = (float(b[0]), float(b[1]))
            if "bounds_on" in state:
                self.bounds_on = bool(state["bounds_on"])
            if "fixed" in state:
                self.fixed = bool(state["fixed"])
            if "value" in state:
                self.value = float(state["value"])
            if "description" in state:
                try:
                    self.description = str(state["description"])
                except Exception:
                    pass
            # Restore a smooth prior if one was serialised. Assigning through
            # the ``prior`` setter also re-establishes the port bounds derived
            # from the prior's support.
            if "prior" in state:
                try:
                    self.prior = state["prior"]
                except Exception:
                    self._port.prior = None
        except Exception:
            return

        try:
            self.update()
        except Exception:
            # Parameters without a concrete update hook simply ignore this.
            pass


#: Sentinel distinguishing "not looked up yet" from "looked up, not a property".
_UNRESOLVED = object()

#: ``(class, attribute) -> property or None`` for
#: :meth:`ParameterGroup.__setattr__`, which would otherwise walk the whole MRO
#: on every attribute write.
_SETATTR_PROPERTY_CACHE: typing.Dict[typing.Tuple[type, str], typing.Any] = {}


class ParameterGroup(chisurf.core.base.Base):
    """Container for a list of :class:`Parameter` objects.

    The group behaves like a light-weight collection that forwards attribute
    access to contained parameters when appropriate. It is mainly used to
    manage related parameters in a convenient way.

    Examples
    --------
    >>> from chisurf.core.parameter import Parameter, ParameterGroup
    >>> p1 = Parameter(name="a", value=1.0)
    >>> p2 = Parameter(name="b", value=2.0)
    >>> group = ParameterGroup(parameters=[p1, p2])
    >>> group.parameter_names
    ['a', 'b']
    >>> sum(group.values)
    3.0
    """

    def __init__(
            self,
            parameters: typing.List[Parameter] = None,
            *args,
            **kwargs
    ):
        """Initialize a ParameterGroup with an optional list of parameters."""
        super().__init__(*args, **kwargs)
        if parameters is None:
            parameters = list()
        self._parameter = parameters

    def get_state(self) -> dict:
        """Return a JSON-serializable snapshot of all contained parameters.

        The structure mirrors :meth:`to_dict` but is intended specifically for
        lightweight state transfer and testing.
        """

        try:
            return self.to_dict()
        except Exception:
            return {}

    def set_state(self, state: dict) -> None:
        """Restore group/parameter state from :meth:`get_state` output.

        This forwards to :meth:`from_dict` and then asks each contained
        parameter to :meth:`update`, allowing any associated UI controllers to
        refresh.
        """

        if not isinstance(state, dict):
            return
        try:
            self.from_dict(state)
        except Exception:
            return
        try:
            for p in getattr(self, "parameters", []):
                upd = getattr(p, "update", None)
                if callable(upd):
                    upd()
        except Exception:
            pass

    def __setattr__(
            self,
            k: str,
            v: object
    ):
        """Route attribute writes to contained Parameter objects when possible.

        If *k* names an existing :class:`Parameter` in the group, the
        value is forwarded to that parameter's *value* setter.
        """
        # Check instance __dict__ first — avoids triggering __getattr__
        # (and its Base-level ERROR log) for every attribute during init.
        try:
            existing = self.__dict__.get(k)
        except AttributeError:
            existing = None
        if existing is not None and isinstance(existing, chisurf.core.parameter.Parameter):
            existing.value = v
            return

        # Check MRO for class-level properties / descriptors. The lookup is
        # memoised per (class, attribute): the walk is over a deep MRO and this
        # runs on every attribute write, including the bookkeeping a global
        # fit's objective does thousands of times per sampling run. Classes and
        # their properties do not change at runtime, so the answer is stable.
        cls_type = type(self)
        key = (cls_type, k)
        descriptor = _SETATTR_PROPERTY_CACHE.get(key, _UNRESOLVED)
        if descriptor is _UNRESOLVED:
            descriptor = None
            for cls in cls_type.__mro__:
                if k in cls.__dict__:
                    found = cls.__dict__[k]
                    if isinstance(found, property):
                        descriptor = found
                    break  # found but not a property — treat as normal attribute
            _SETATTR_PROPERTY_CACHE[key] = descriptor
        if descriptor is not None:
            if descriptor.fset is None:
                raise AttributeError("can't set attribute")
            descriptor.fset(self, v)
            return

        try:
            super().__setattr__(k, v)
        except KeyError:
            super().__setattr__(k, v)

    def __getattr__(self, key: str):
        """Return a contained Parameter's float value when accessed by name."""
        v = super().__getattr__(key=key)
        if isinstance(v, chisurf.core.parameter.Parameter):
            return v.value
        return v

    def append(self,
            parameter: Parameter,
            **kwargs
    ):
        """Append a :class:`Parameter` to the group."""
        self._parameter.append(parameter)

    def clear(self):
        """Remove all parameters from the group."""
        self._parameter = list()

    @property
    def parameters(self) -> typing.List[Parameter]:
        """Return the list of contained parameters."""
        return self._parameter

    @property
    def parameter_names(self) -> typing.List[str]:
        """Return the names of all contained parameters."""
        return [p.name for p in self.parameters]

    @property
    def values(self) -> np.array:
        """Return the current values of all contained parameters."""
        return [p.value for p in self.parameters]

    # def save_txt(
    #         self,
    #         filename: str,
    #         sep: str = '\t'
    # ):
    #     with open(filename, 'w') as fp:
    #         s = ""
    #         for ph in self.parameter_names:
    #             s += ph + sep
    #         s += "\n"
    #         for l in self.values:
    #             for p in l:
    #                 s += "%.5f%s" % (p, sep)
    #             s += "\n"
    #         fp.write(s)
    #
