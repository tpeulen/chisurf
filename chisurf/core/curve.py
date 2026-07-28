from __future__ import annotations
from chisurf import typing

import abc
import contextlib
import logging

import numpy as np

import chisurf.core.fio
import chisurf.core.fio.ascii
import chisurf.core.base
import chisurf.core.decorators
import chisurf.core.math


logger = logging.getLogger(__name__)

T = typing.TypeVar('T', bound='Curve')


class NCurve(chisurf.core.base.Base):
    """Base class for 1D numeric arrays.

    This class stores a single NumPy array ``d`` and provides basic
    slicing/serialization support. Subclasses such as :class:`Curve`
    interpret the array in more structured ways.

    Notes
    -----
    **The sample arrays are write-locked.** A curve is routinely handed to
    several consumers at once — a fit, a plot, a plugin, a node in a pipeline —
    and any one of them writing into it in place changes everyone else's result
    silently. Every array listed in :attr:`array_attributes` is therefore
    flagged non-writeable when it is assigned, and so is every view taken from
    it (``curve.x`` and ``curve.y`` are views into ``d``). Replacing an array
    wholesale through its setter stays allowed — that rebinds the curve's own
    state rather than the buffer a consumer is holding.

    Writing in place is not forbidden, only made explicit:

    >>> import numpy as np
    >>> from chisurf.core.curve import Curve
    >>> c = Curve(x=np.arange(3.0), y=np.zeros(3))
    >>> c.y[0] = 1.0                                # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    ValueError: assignment destination is read-only
    >>> with c.unlocked():
    ...     c.y[0] = 1.0
    >>> float(c.y[0])
    1.0

    Assigning an array to a curve transfers ownership of that buffer: the curve
    locks the object it was given, so a caller that keeps writing to the array
    it passed in will now see the same error. An array that does **not** own its
    data — a row of a larger array, which is what a CSV reader hands out — is
    copied on the way in, because locking a view leaves the underlying buffer
    writable and the guarantee would be empty.
    """

    #: Names of the per-sample arrays this class write-locks. Subclasses that
    #: carry further arrays beside ``d`` extend the tuple.
    array_attributes: typing.Tuple[str, ...] = ("d",)

    #: Friendly names accepted by :meth:`unlocked`, mapped to the array that
    #: actually stores them.
    _array_aliases: typing.Dict[str, str] = {"x": "d", "y": "d"}

    #: Nesting depth of :meth:`unlocked`. A class attribute so that it is
    #: readable before ``__init__`` has assigned anything.
    _unlock_depth: int = 0

    def __init__(
            self,
            d: np.ndarray = None,
            copy_array: bool = True,
            *args,
            **kwargs
    ):
        """Initialize an NCurve with an optional 1D numpy array.

        Parameters
        ----------
        d : np.ndarray, optional
            Data array.
        copy_array : bool
            If True (default), the array is copied.
        """
        if d is None:
            self.d = np.array(list(), dtype=np.float64)
        elif copy_array:
            self.d = np.atleast_1d(np.copy(d))
        else:
            self.d = d
        super().__init__(*args, **kwargs)

    def __setattr__(self, key: str, value: object):
        """Lock every per-sample array on its way into the curve.

        Doing it here rather than at the handful of sites that currently assign
        one is what makes the guarantee hold: a future assignment cannot forget
        to lock, because there is nowhere else for an array to enter.
        """
        if key in self.array_attributes and isinstance(value, np.ndarray):
            if not value.flags.owndata:
                # A row of somebody else's array -- `self.ey = csv.data[3]` in
                # `DataCurve.load`, or any caller passing a slice to `set_data`.
                # `setflags` would lock the *view* and leave the buffer writable,
                # so the caller who still holds the source could write straight
                # through the "locked" curve; and the view could not be unlocked
                # again, because writing it would reach data the curve does not
                # own. A curve owns its arrays, exactly as it already owns the
                # 2xN storage that every path rebuilds with `np.vstack`.
                value = np.array(value)
            if not self._unlock_depth:
                value.setflags(write=False)
        super().__setattr__(key, value)

    def __setstate__(self, state: dict):
        """Restore from pickle/deepcopy and re-lock the arrays.

        Neither pickling nor :func:`copy.deepcopy` goes through
        :meth:`__setattr__`, and NumPy's own copy comes back writeable — so the
        restored curve would otherwise be the one unlocked object in the tree.
        """
        self.__dict__.update(state)
        self.lock()

    def __deepcopy__(self, memodict=None):
        """Deep-copy the curve and re-lock the copy's arrays.

        :meth:`chisurf.core.base.Base.__deepcopy__` rebuilds ``__dict__``
        directly, and NumPy hands back a writeable array from its own deep copy.
        """
        c = super().__deepcopy__(memodict)
        c.lock()
        return c

    def lock(self) -> None:
        """Flag every per-sample array non-writeable."""
        for name in self.array_attributes:
            array = self.__dict__.get(name)
            if isinstance(array, np.ndarray):
                array.setflags(write=False)

    @staticmethod
    def _can_unlock(array: np.ndarray) -> bool:
        """Whether ``array`` may be made writeable without corrupting a source.

        A view into another array shares that array's buffer; writing through it
        would silently modify data the curve does not own.
        """
        return bool(array.flags.writeable or array.flags.owndata or array.size == 0)

    @contextlib.contextmanager
    def unlocked(self, *names: str):
        """Temporarily allow in-place writes to the curve's arrays.

        Parameters
        ----------
        *names : str
            Arrays to unlock, by attribute name (``'d'``, and on subclasses
            ``'ex'``, ``'ey'``, ``'mask'``); ``'x'`` and ``'y'`` are accepted as
            aliases for the storage that holds them. With no argument every
            per-sample array is unlocked.

        Raises
        ------
        KeyError
            If a name is not one of the curve's arrays.
        ValueError
            If an array is a view into another array, where an in-place write
            would reach through to data the curve does not own. Assignment
            copies such an array, so this is a backstop for state that reached
            ``__dict__`` some other way (an old pickle, say), not something a
            caller can normally trip.

        Examples
        --------
        >>> import numpy as np
        >>> from chisurf.core.curve import Curve
        >>> c = Curve(x=np.arange(3.0), y=np.zeros(3))
        >>> with c.unlocked('y'):
        ...     c.y[:] = 2.0
        >>> c.y.flags.writeable
        False
        """
        if names:
            resolved = []
            for name in names:
                target = self._array_aliases.get(name, name)
                if target not in self.array_attributes:
                    raise KeyError(
                        f"{type(self).__name__} has no per-sample array {name!r}; "
                        f"expected one of {self.array_attributes + tuple(self._array_aliases)}"
                    )
                if target not in resolved:
                    resolved.append(target)
        else:
            resolved = list(self.array_attributes)

        arrays = []
        for name in resolved:
            array = self.__dict__.get(name)
            if not isinstance(array, np.ndarray):
                continue
            if not self._can_unlock(array):
                raise ValueError(
                    f"{type(self).__name__}.{name} is a view into another array "
                    "and cannot be unlocked; write to a copy instead"
                )
            arrays.append(array)

        depth = self._unlock_depth
        self._unlock_depth = depth + 1
        for array in arrays:
            array.setflags(write=True)
        try:
            yield self
        finally:
            self._unlock_depth = depth
            if not depth:
                self.lock()

    def __getstate__(self):
        """Return the instance ``__dict__`` for pickling."""
        state = self.__dict__.copy()
        return state

    def __getitem__(self, key) -> typing.Tuple[np.ndarray, np.ndarray]:
        """Index into the flattened data array.

        Both members of the returned pair are indexed by the *same* ``key``, so
        they always have matching shapes — the contract :class:`Curve` and
        :class:`~chisurf.core.data.DataCurve` implement over their own ``x`` and
        ``y``. A bare :class:`NCurve` carries no abscissa, so the position
        within the flattened array stands in for it.

        Parameters
        ----------
        key : int, slice, or np.ndarray
            Index.

        Returns
        -------
        tuple
            ``(x, y)`` where *x* holds the selected positions within the
            flattened array and *y* the selected data values.

        Examples
        --------
        >>> import numpy as np
        >>> from chisurf.core.curve import NCurve
        >>> x, y = NCurve(d=np.arange(6.0))[1:4]
        >>> x
        array([1, 2, 3])
        >>> y
        array([1., 2., 3.])
        """
        d = self.d.flatten()
        return np.arange(d.size).__getitem__(key), d.__getitem__(key)


class Curve(NCurve):
    """Simple 1D curve represented by paired ``(x, y)`` arrays.

    The underlying storage ``d`` is a 2×N array with ``d[0] = x`` and
    ``d[1] = y``. The class provides basic arithmetic, slicing and
    (de-)serialization helpers.

    Examples
    --------
    Construct a small curve and access its data:

    >>> import numpy as np
    >>> from chisurf.core.curve import Curve
    >>> x = np.array([0.0, 1.0, 2.0])
    >>> y = np.array([1.0, 2.0, 3.0])
    >>> c = Curve(x=x, y=y)
    >>> len(c)
    3
    >>> float(c.y[0])
    1.0
    """

    @property
    def fwhm(self) -> float:
        """Full width at half maximum of the curve.

        The calculation is delegated to
        :func:`chisurf.core.math.signal.calculate_fwhm`.
        """
        v, _, _ = chisurf.core.math.signal.calculate_fwhm(
            x_values=self.x,
            y_values=self.y
        )
        return v

    @property
    def cdf(self) -> Curve:
        """Return the cumulative distribution function of ``y``.

        The returned object is a new :class:`Curve` with the same ``x``
        grid and ``y`` replaced by ``np.cumsum(self.y)``.

        Examples
        --------
        >>> import numpy as np
        >>> from chisurf.core.curve import Curve
        >>> c = Curve(x=np.array([0., 1., 2.]), y=np.array([1., 2., 3.]))
        >>> float(c.cdf.y[-1])
        6.0
        """
        return self.__class__(
            x=self.x,
            y=np.cumsum(self.y)
        )

    @property
    def x(self) -> np.ndarray:
        """Abscissa array of the curve."""
        return self.d[0]

    @x.setter
    def x(self, v):
        """Set the curve's x-values, resizing the storage when the length changes."""
        self._set_axis(0, v)

    @property
    def y(self) -> np.ndarray:
        """Ordinate array of the curve."""
        return self.d[1]

    @y.setter
    def y(self, v):
        """Set the curve's y-values, resizing the storage when the length changes."""
        self._set_axis(1, v)

    def _set_axis(self, index: int, values) -> None:
        """Write one axis of the 2×N storage, growing or shrinking it as needed.

        Assigning into the existing array is the fast path and covers the common
        case of replacing values on a fixed grid. It cannot serve the equally
        ordinary case of filling an empty curve — ``c = Curve(); c.x = x; c.y = y``
        — where the new length simply differs, and a plain broadcast raises
        instead. A differing length therefore *resizes the whole curve*: the
        other axis keeps whatever still fits and is zero-padded beyond that, and
        :meth:`_resize_companions` brings any per-sample arrays a subclass keeps
        alongside the storage to the same length. Setting one axis alone can only
        ever leave a curve whose columns all describe the same samples.

        Parameters
        ----------
        index : int
            ``0`` for x, ``1`` for y.
        values : array_like
            The new values for that axis.
        """
        values = np.atleast_1d(np.asarray(values, dtype=np.float64))
        storage = self.d
        if storage.ndim == 2 and storage.shape[0] == 2 and storage.shape[1] == values.size:
            # Replacing a whole axis through its setter is the sanctioned way to
            # write a curve, so the lock is lifted for the assignment itself.
            with self.unlocked('d'):
                self.d[index] = values
            return
        other = np.zeros(values.size, dtype=np.float64)
        if storage.ndim == 2 and storage.shape[0] == 2:
            previous = np.asarray(storage[1 - index], dtype=np.float64)
            kept = min(previous.size, values.size)
            other[:kept] = previous[:kept]
        rows = [values, other] if index == 0 else [other, values]
        self.d = np.vstack(rows)
        self._resize_companions(values.size)

    def _resize_companions(self, size: int) -> None:
        """Bring per-sample arrays held beside the storage to ``size`` samples.

        A :class:`Curve` keeps nothing but the 2×N array, so this is a no-op
        here. Subclasses that carry one value per sample outside ``d`` — errors,
        masks — override it so that a length change through :meth:`_set_axis`
        cannot leave those arrays at the previous length.

        Parameters
        ----------
        size : int
            The curve's new number of samples.
        """

    @property
    def dx(self) -> np.ndarray:
        """First differences of the ``x`` array (``np.diff(self.x)``)."""
        return np.diff(self.x)

    def save(
            self,
            filename: str,
            file_type: str = 'yaml',
            verbose: bool = False,
            x_min: int = None,
            x_max: int = None
    ) -> None:
        """Save the curve to disk via :mod:`chisurf.core.fio`.

        When ``file_type == 'csv'`` the data are written as two rows
        ``[x, y]`` using :class:`chisurf.core.fio.ascii.Csv`.
        """
        super().save(
            filename=filename,
            file_type=file_type,
            verbose=verbose
        )
        if file_type == "csv":
            csv = chisurf.core.fio.ascii.Csv()
            x, y = self[x_min:x_max]
            csv.save(
                data=np.vstack([x, y]),
                filename=filename
            )

    def load(
            self,
            filename: str,
            file_type: str = 'csv',
            skiprows: int = 0,
            **kwargs
    ) -> None:
        """Load curve data from disk.

        For ``file_type == 'csv'`` the first two rows are interpreted
        as ``x`` and ``y``.
        """
        super().load(
            filename=filename,
            file_type=file_type
        )
        if file_type == 'csv':
            csv = chisurf.core.fio.ascii.Csv()
            csv.load(
                filename=filename,
                skiprows=skiprows,
                file_type=file_type,
                **kwargs
            )
            try:
                self.x = csv.data[0]
                self.y = csv.data[1]
            except IndexError:
                self.x = csv.data[0]
                self.y = csv.data[1]

    def to_dict(
            self,
            remove_protected: bool = True,
            copy_values: bool = True,
            convert_values_to_elementary: bool = False,
            skip_qt_widgets: bool = False
    ) -> typing.Dict:
        """Serialize the curve to a dictionary.

        Depending on ``convert_values_to_elementary`` the arrays are stored
        as plain Python lists or NumPy arrays. ``skip_qt_widgets`` is part of
        :meth:`chisurf.core.base.Base.to_dict`'s contract and must be accepted
        here too — an override that drops it turns every caller that serializes
        a curve without its widgets into a ``TypeError``.
        """
        d = super().to_dict(
            remove_protected=remove_protected,
            copy_values=copy_values,
            convert_values_to_elementary=convert_values_to_elementary,
            skip_qt_widgets=skip_qt_widgets
        )
        if convert_values_to_elementary:
            d['x'] = self.x.tolist()
            d['y'] = self.y.tolist()
        else:
            if copy_values:
                d['x'] = np.copy(self.x)
                d['y'] = np.copy(self.y)
            else:
                d['x'] = self.x
                d['y'] = self.y
        return d

    def from_dict(self, v: dict):
        """Restore a curve from :meth:`to_dict` output."""
        super().from_dict(v)
        y = np.array(v['y'], dtype=np.float64)
        x = np.array(v['x'], dtype=np.float64)
        d = np.vstack([x, y])
        self.d = d

    def __init__(
            self,
            x: np.ndarray = None,
            y: np.ndarray = None,
            *args,
            **kwargs
    ):
        """Create a curve from x/y arrays.

        Parameters
        ----------
        x, y : array_like, optional
            Arrays of identical length defining the abscissa and ordinate of
            the curve. Omitting one fills it with zeros; omitting both gives an
            empty curve.

        Notes
        -----
        The arrays are coerced to ``float64`` here. ``np.vstack([None, None])``
        yields ``array([[None], [None]], dtype=object)``, so a default-built
        curve used to carry an object array holding ``None`` — which propagates
        silently until some arithmetic far away fails or, worse, quietly returns
        an object array.

        A curve always **owns** its storage. ``copy_array=False`` is a
        copy-avoidance hint honoured by :class:`NCurve` when it is handed a ready
        2×N array; it cannot be honoured for two separate ``x`` and ``y`` arrays,
        because a single 2×N block cannot alias two independent buffers. Writing
        to a curve therefore never writes through to the arrays it was built
        from.
        """
        x = np.array([], dtype=np.float64) if x is None else np.atleast_1d(
            np.asarray(x, dtype=np.float64))
        y = np.array([], dtype=np.float64) if y is None else np.atleast_1d(
            np.asarray(y, dtype=np.float64))
        if x.size != y.size:
            if x.size == 0:
                x = np.zeros_like(y)
            elif y.size == 0:
                y = np.zeros_like(x)
        d = np.vstack([x, y])
        super().__init__(*args, d=d, **kwargs)

    def normalize(
            self,
            mode: str = "max",
            curve: chisurf.core.curve.Curve = None,
            inplace: bool = True
    ) -> float:
        """Calculates a scaling parameter for the Curve object and (optionally)
        scales the Curve object.

        :param mode: either 'max' to normalize the maximum to one, or 'sum' to
        normalize to sum to one
        :param curve:
        :param inplace: if True the Curve object is modified in place. Otherwise, only the scaling parameter
        is returned
        :return: the parameter that scales the Curve object

        An all-zero or empty curve has no scale to normalize against. Dividing
        by the zero factor filled the curve with NaN behind a bare
        ``RuntimeWarning`` and still reported success — reachable from the IRF
        path, where a fittable ``lamp_background`` above the whole IRF clips it
        to zero first, and the NaN then propagated into the model and χ² with
        nothing raised or logged anywhere. Such a curve is left alone and ``1.0``
        is returned.
        """
        factor = 1.0
        if self.y.size:
            # `sum`/`max` here are the *builtins* iterating a NumPy array
            # element by element -- two orders of magnitude slower than the
            # NumPy reductions on a 64k-point curve.
            if not isinstance(curve, Curve):
                if mode == "sum":
                    factor = float(np.sum(self.y))
                elif mode == "max":
                    factor = float(np.max(self.y))
            else:
                if mode == "sum":
                    factor = float(np.sum(self.y) * np.sum(curve.y))
                elif mode == "max":
                    factor = float(np.max(self.y) * np.max(curve.y))
        if factor == 0.0 or not np.isfinite(factor):
            logger.warning(
                "Cannot normalize a curve whose %s is %s; leaving it unscaled.",
                mode, factor
            )
            return 1.0
        if inplace:
            # Not `self.y /= factor`: augmented assignment divides the view in
            # place before the setter ever runs, which the lock rejects.
            self.y = self.y / factor
        return factor

    def __add__(self, c: T) -> Curve:
        """Return the pointwise sum of two curves or curve and array."""
        if isinstance(c, Curve):
            if not np.array_equal(self.x, c.x):
                raise ValueError("The x-axis differ")
            c = c.y
        return self.__class__(
            x=self.x,
            y=self.y.__add__(c)
        )

    def __sub__(self, c: T) -> Curve:
        """Return the pointwise difference between two curves or curve and array."""
        if isinstance(c, Curve):
            if not np.array_equal(self.x, c.x):
                raise ValueError("The x-axis differ")
            c = c.y
        return self.__class__(
            x=self.x,
            y=self.y.__sub__(c)
        )

    def __mul__(self, c: T) -> Curve:
        """Return the pointwise product of two curves or curve and array."""
        if isinstance(c, Curve):
            if not np.array_equal(self.x, c.x):
                raise ValueError("The x-axis differ")
            c = c.y
        return self.__class__(
            x=self.x,
            y=self.y.__mul__(c)
        )

    def __truediv__(self, c: T) -> Curve:
        """Return the pointwise ratio of two curves or curve and array."""
        if isinstance(c, Curve):
            if not np.array_equal(self.x, c.x):
                raise ValueError("The x-axis differ")
            c = c.y
        return self.__class__(
            x=self.x,
            y=self.y.__truediv__(c)
        )

    def __lshift__(self, shift: float) -> Curve:
        """Return a copy with ``y`` shifted by ``shift`` samples."""
        return self.__class__(
            x=self.x,
            y=chisurf.core.math.signal.shift_array(self.y, shift),
            copy_array=False
        )
    def __len__(self) -> int:
        """Number of points in the curve (length of ``y``)."""
        return len(self.y)

    def __getitem__(self, key: typing.Union[slice, int, np.ndarray, str]) -> typing.Tuple[np.ndarray, np.ndarray]:
        """Return a slice of curve as (x, y)."""
        return self.x[key], self.y[key]


class CurveGroup(object):
    """Light-weight container for a sequence of :class:`Curve` objects.

    The default implementation simply stores a list of curves and provides

    Examples
    --------
    >>> import numpy as np
    >>> from chisurf.core.curve import Curve, CurveGroup
    >>> c1 = Curve(x=np.array([0., 1.]), y=np.array([1., 2.]))
    >>> group = CurveGroup([c1])
    >>> len(group.get_data_curves())
    1
    """

    _curves: typing.List[chisurf.core.curve.Curve]

    def __init__(
            self,
            seq: typing.List[chisurf.core.curve.Curve] = None
    ):
        """Initialize a CurveGroup with an optional list of curves.

        Parameters
        ----------
        seq : list of Curve, optional
            Initial curve list.
        """
        if seq is None:
            seq = []
        self._curves = seq

    def clear_curves(self):
        """Remove all curves from the group."""
        self._curves.clear()

    def get_data_curves(
            self,
            *args,
            **kwargs
    ) -> typing.List[chisurf.core.curve.Curve]:
        """Return the list of curves stored in the group."""
        return self._curves

    @abc.abstractmethod
    def remove_curve(
            self,
            selected_index: typing.List[int] = None
    ):
        """Remove curves whose indices are listed in ``selected_index``."""
        if selected_index is None:
            selected_index = list()
        curve_list = list()
        for i, c in enumerate(self._curves):
            if i not in selected_index:
                curve_list.append(c)
        self._curves = curve_list

    @abc.abstractmethod
    def add_curve(
            self,
            *args,
            v: chisurf.core.curve.Curve = None,
            **kwargs
    ):
        """Append a new curve ``v`` to the group if it is not ``None``."""
        if v is not None:
            self._curves.append(v)

