from __future__ import annotations

import pathlib

from chisurf import typing
import numpy as np
import yaml

import chisurf.core.base
import chisurf.core.curve
import chisurf.core.fio
import chisurf.core.fio.ascii
from chisurf.core.fio.pto import SUFFIX, is_measurement as _is_measurement
from chisurf.core.fio.staging import CONTAINER_SELECTOR


def _is_container(filename) -> bool:
    """Whether *filename* names a photon container, member selector and all."""
    path, _, _ = str(filename).partition(CONTAINER_SELECTOR)
    return _is_measurement(path)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chisurf.core.experiments.core.experiment import Experiment
    from chisurf.core.experiments.core.reader import ExperimentReader


class ExperimentalData(chisurf.core.base.Data):
    """Base class for experimental datasets in ChiSurf.

    Extends :class:`chisurf.core.base.Data` with optional links to an
    experiment reader and an experiment description. Concrete curve
    types such as :class:`DataCurve` derive from this class.
    """

    meta_data: typing.Dict = None
    data_reader: "ExperimentReader" = None
    _experiment: "Experiment" = None

    @property
    def experiment(self) -> "Experiment":
        """Return the experiment associated with this dataset.

        If ``_experiment`` is not set, attempts to retrieve it from the
        associated :attr:`data_reader`.
        """
        if self._experiment is None:
            try:
                from chisurf.core.experiments.core.reader import ExperimentReader
            except Exception:
                ExperimentReader = None
            if ExperimentReader is not None and isinstance(self.data_reader, ExperimentReader):
                return self.data_reader.experiment
        else:
            return self._experiment

    @experiment.setter
    def experiment(
            self,
            v: "Experiment"
    ) -> None:
        """Set the experiment associated with this dataset."""
        self._experiment = v

    def __getstate__(self):
        """Return the instance ``__dict__`` for pickling/serialization."""
        state = self.__dict__.copy()
        return state

    def __init__(
            self,
            data_reader: "ExperimentReader" = None,
            experiment: "Experiment" = None,
            filename: str = "None",
            data: bytes = None,
            embed_data: bool = None,
            read_file_size_limit: int = None,

            name: object = None,
            verbose: bool = False,
            unique_identifier: str = None,
            **kwargs
    ):
        super().__init__(
            filename=filename,
            data=data,
            embed_data=embed_data,
            read_file_size_limit=read_file_size_limit,
            name=name,
            verbose=verbose,
            unique_identifier=unique_identifier,
            **kwargs
        )
        self._experiment = experiment
        self.data_reader = data_reader

    def to_dict(
            self,
            remove_protected: bool = True,
            copy_values: bool = True,
            convert_values_to_elementary: bool = False,
        skip_qt_widgets: bool = False
    ):
        """Serialize this dataset, including its reader and experiment, to a dict.

        Parameters
        ----------
        remove_protected : bool
            Whether to omit protected (underscore-prefixed) attributes.
        copy_values : bool
            Whether to copy values instead of returning references.
        convert_values_to_elementary : bool
            If True, convert compound types to elementary Python types.

        Returns
        -------
        dict
            A dictionary representation of the dataset.
        """
        d = super().to_dict(
            remove_protected=remove_protected,
            copy_values=copy_values,
            convert_values_to_elementary=convert_values_to_elementary,
            skip_qt_widgets=skip_qt_widgets
        )
        try:
            d['data_reader'] = self.data_reader.to_dict(
                remove_protected=remove_protected,
                copy_values=copy_values,
                convert_values_to_elementary=convert_values_to_elementary
            )
        except AttributeError:
            import logging
            logging.debug(f"data_reader has no to_dict method")
            d['data_reader'] = None
        try:
            d['experiment'] = self.experiment.to_dict(
                remove_protected=remove_protected,
                copy_values=copy_values,
                convert_values_to_elementary=convert_values_to_elementary
            )
        except AttributeError:
            import logging
            logging.debug(f"experiment has no to_dict method")
            d['experiment'] = None
        return d


class DataCurve(chisurf.core.curve.Curve, ExperimentalData):
    """One-dimensional experimental curve with error estimates.

    Combines :class:`chisurf.core.curve.Curve` with :class:`ExperimentalData`
    and adds error arrays ``ex`` and ``ey`` for the x- and y-values.

    For flattened multi-dimensional datasets (e.g. 2D histograms or images
    represented as 1D arrays), experiment readers may populate the generic
    grid description ``meta_data['grid']`` with a dictionary containing
    fields such as::

        {
            'ndim': 2,
            'shape': (ny, nx),
            'order': 'C' or 'F',  # NumPy-style memory order for flattening
            # optional sparse/indexed representations:
            'row_indices': np.ndarray,
            'col_indices': np.ndarray,
            'size': int,
        }

    GUI components (e.g. the fitting range controller and 2D residual plots)
    can use this metadata to reconstruct logical grid coordinates and build
    selection masks without needing experiment-specific knowledge.

    Examples
    --------
    >>> import numpy as np
    >>> from chisurf.core.data import DataCurve
    >>> dc = DataCurve(x=np.array([0.0, 1.0]), y=np.array([1.0, 2.0]))
    >>> dc.data.shape
    (5, 2)

    Notes
    -----
    ``ex``, ``ey`` and ``mask`` are per-sample arrays and are write-locked
    alongside ``x`` and ``y``; see :class:`chisurf.core.curve.NCurve`. Use
    ``with curve.unlocked('ey'): ...`` to edit one in place.
    """

    array_attributes = chisurf.core.curve.Curve.array_attributes + (
        "ex", "ey", "mask"
    )

    @property
    def data(self) -> np.ndarray:
        """Return a stacked 5-row array ``(x, y, ex, ey, mask)``."""
        return np.vstack(
            [
                self.x,
                self.y,
                self.ex,
                self.ey,
                self.mask if self.mask is not None else np.ones_like(self.y)
            ]
        )

    @data.setter
    def data(self, v: np.ndarray):
        """Set the curve data from a stacked array ``(x, y, ex, ey, mask)``.

        Parameters
        ----------
        v : np.ndarray
            Array where each row corresponds to x, y, ex, ey, mask.
        """
        self.set_data(*v)

    def __init__(
            self,
            x: np.ndarray = None,
            y: np.ndarray = None,
            ex: np.ndarray = None,
            ey: np.ndarray = None,
            mask: np.ndarray = None,
            copy_array: bool = True,
            filename: str = '',
            data_reader: "ExperimentReader" = None,
            experiment: "Experiment" = None,
            load_filename_on_init: bool = True,
            *args,
            **kwargs
    ):
        super().__init__(
            x=x,
            y=y,
            copy_array=copy_array,
            filename=filename,
            data_reader=data_reader,
            experiment=experiment,
            *args,
            **kwargs
        )
        # The companions are initialised *before* the file is read, because
        # `load` writes the file's own `ex`/`ey`/`mask` columns and they must
        # survive. Doing it the other way round overwrites a 3-, 4- or 5-column
        # file's uncertainties with the argument defaults (`ex`/`ey`/`mask` are
        # `None` for every caller that passes a filename), leaving unit weights.
        # A file therefore wins over the passed arrays, exactly as it already
        # does for `x` and `y`.
        if not isinstance(ex, np.ndarray):
            ex = np.zeros_like(self.x)
        if not isinstance(ey, np.ndarray):
            ey = np.ones_like(self.y)
        if not isinstance(mask, np.ndarray):
            mask = np.ones_like(self.y)
        self.ex: np.ndarray = np.copy(ex) if copy_array else ex
        self.ey: np.ndarray = np.copy(ey) if copy_array else ey
        self.mask: np.ndarray = np.copy(mask) if copy_array else mask

        # `filename` is empty for every curve built in-memory (model decays,
        # shifted IRFs, arithmetic results), and Path('').is_file() is still a
        # filesystem stat. Curves are constructed inside the fit's hot loop, so
        # skip the syscall when there is obviously nothing to load.
        if load_filename_on_init and filename:
            if pathlib.Path(filename).is_file():
                self.load(filename, **kwargs)

    def _resize_companions(self, size: int) -> None:
        """Keep ``ex``, ``ey`` and ``mask`` at the curve's number of samples.

        :meth:`chisurf.core.curve.Curve._set_axis` resizes the 2×N storage
        whenever an axis is assigned a different length. Without this the error
        and mask arrays would keep the previous length, and ``data``,
        ``__getitem__`` and ``to_dict`` would describe a dataset whose columns
        disagree about how many samples it has.

        Parameters
        ----------
        size : int
            The curve's new number of samples.
        """
        # `ex`/`ey`/`mask` are assigned in __init__, after `super().__init__`
        # has already written the axes, so a companion may not exist yet.
        for name, fill in (("ex", 0.0), ("ey", 1.0), ("mask", 1.0)):
            previous = getattr(self, name, None)
            if not isinstance(previous, np.ndarray) or previous.size == size:
                continue
            resized = np.full(size, fill, dtype=previous.dtype)
            kept = min(previous.size, size)
            resized[:kept] = previous[:kept]
            setattr(self, name, resized)

    def __str__(self):
        """Return a human-readable summary of the dataset (head/tail values)."""
        s = "Dataset:\n"
        try:
            s += "filename: " + self.filename + "\n"
            s += "length  : %s\n" % len(self)
            s += "x\ty\terror-x\terror-y\n"

            if len(self.x) > 10:
                lx = self.x[:4]
                ly = self.y[:4]
                lex = self.ex[:4]
                ley = self.ey[:4]
                for i in range(3):
                    x, y, ex, ey = lx[i], ly[i], lex[i], ley[i]
                    s += "{0:<12.3e}\t".format(x)
                    s += "{0:<12.3e}\t".format(y)
                    s += "{0:<12.3e}\t".format(ex)
                    s += "{0:<12.3e}\t".format(ey)
                    s += "\n"
                s += "....\n"
                ux = self.x[-4:]
                uy = self.y[-4:]
                uex = self.ex[-4:]
                uey = self.ey[-4:]
                for i in range(2):
                    x, y, ex, ey = ux[i], uy[i], uex[i], uey[i]
                    s += "{0:<12.3e}\t".format(x)
                    s += "{0:<12.3e}\t".format(y)
                    s += "{0:<12.3e}\t".format(ex)
                    s += "{0:<12.3e}\t".format(ey)
                    s += "\n"
            else:
                for i in range(len(self.x)):
                    x, y, ex, ey = self.x[i], self.y[i], self.ex[i], self.ey[i]
                    s += "{0:<12.3e}\t".format(x)
                    s += "{0:<12.3e}\t".format(y)
                    s += "{0:<12.3e}\t".format(ex)
                    s += "{0:<12.3e}\t".format(ey)
        except (AttributeError, KeyError) as e:
            import logging
            logging.debug(f"Error in Dataset.__str__: {e}")
            s += "This curve does not have complete data..."
        return s

    def to_dict(
            self,
            remove_protected: bool = False,
            copy_values: bool = True,
            convert_values_to_elementary: bool = False,
        skip_qt_widgets: bool = False
    ) -> typing.Dict:
        """Serialize the curve to a dict, including error arrays and mask.

        Parameters
        ----------
        remove_protected : bool
            Whether to omit protected attributes.
        copy_values : bool
            Whether to copy values.
        convert_values_to_elementary : bool
            Whether to convert to elementary types.

        Returns
        -------
        dict
            Dictionary with keys ``'ex'``, ``'ey'``, ``'mask'`` plus
            keys from the parent :meth:`chisurf.core.curve.Curve.to_dict`.
        """
        d = super().to_dict(
            remove_protected=remove_protected,
            copy_values=copy_values,
            convert_values_to_elementary=convert_values_to_elementary,
            skip_qt_widgets=skip_qt_widgets
        )
        d['ex'] = self.ex.tolist()
        d['ey'] = self.ey.tolist()
        d['mask'] = self.mask.tolist()
        return d

    def from_dict(
            self,
            v: typing.Dict
    ) -> None:
        """Restore curve state from a dictionary produced by :meth:`to_dict`.

        Parameters
        ----------
        v : dict
            Dictionary containing ``'ex'``, ``'ey'``, and optionally ``'mask'``
            keys with list-of-float values.
        """
        super().from_dict(v)
        self.ex = np.array(v['ex'], dtype=np.float64)
        self.ey = np.array(v['ey'], dtype=np.float64)
        if 'mask' in v:
            self.mask = np.array(v['mask'], dtype=np.float64)

    def load(
            self,
            filename: str,
            skiprows: int = 0,
            file_type: str = 'csv',
            **kwargs
    ) -> None:
        """Load curve data from a file.

        Supports CSV files with 1–5 columns (x, y, ex, ey, mask).
        Delegates to the parent class for other file types.

        Parameters
        ----------
        filename : str
            Path to the file.
        skiprows : int
            Number of header rows to skip.
        file_type : str
            File format (``'csv'`` or any format supported by the parent).
        **kwargs
            Additional arguments passed to the file reader.
        """
        if _is_container(filename):
            self._load_container(filename)
            return
        if file_type == 'csv':
            csv = chisurf.core.fio.ascii.Csv()
            csv.load(
                filename=filename,
                skiprows=skiprows,
                file_type=file_type,
                **kwargs
            )
            n_col, _ = csv.data.shape
            if n_col == 1:
                self.x = csv.data[0]
                self.y = np.ones_like(self.x)
                self.ex = np.zeros_like(self.x)
                self.ey = np.ones_like(self.y)
            elif n_col == 2:
                self.x = csv.data[0]
                self.y = csv.data[1]
                self.ex = np.zeros_like(self.x)
                self.ey = np.ones_like(self.y)
            elif n_col == 3:
                self.x = csv.data[0]
                self.y = csv.data[1]
                self.ex = np.zeros_like(self.x)
                self.ey = csv.data[2]
            elif n_col == 4:
                self.x = csv.data[0]
                self.y = csv.data[1]
                self.ex = csv.data[2]
                self.ey = csv.data[3]
                self.mask = np.ones_like(self.x)
            elif n_col == 5:
                self.x = csv.data[0]
                self.y = csv.data[1]
                self.ex = csv.data[2]
                self.ey = csv.data[3]
                self.mask = csv.data[4]
            else:
                self.x = np.ones(1)
                self.y = np.ones(1)
                self.ex = np.ones(1)
                self.ey = np.ones(1)
        else:
            super().load(
                filename=filename,
                file_type=file_type,
                **kwargs
            )

    def save(
            self,
            filename: str,
            file_type: str = 'yaml',
            verbose: bool = False,
            xmin: int = None,
            xmax: int = None
    ) -> None:
        """Save the curve data to a file.

        Parameters
        ----------
        filename : str
            Output file path.
        file_type : str
            Output format (``'csv'`` or ``'yaml'``).
        verbose : bool
            If True, print progress information.
        xmin : int, optional
            Start index for a slice of the data to save.
        xmax : int, optional
            End index for a slice of the data to save.
        """
        self.filename = filename
        if file_type in ("pto", "container") or str(filename).endswith(SUFFIX):
            self._save_container(filename, xmin=xmin, xmax=xmax)
        elif file_type == "csv":
            csv = chisurf.core.fio.ascii.Csv()
            # self[xmin:xmax] now returns (x, y, ex, ey, mask)
            x, y, ex, ey, mask = self[xmin:xmax]
            csv.save(
                data=np.vstack([x, y, ex, ey, mask]),
                filename=filename
            )
        else:
            super().save(
                filename=filename,
                file_type=file_type,
                verbose=verbose
            )

    #: What this curve *is*, as an ``_mmfdb_artifact.artifact_kind`` term, and
    #: what produced it, as an ``_mmfdb_operation.operation_type`` term.
    #:
    #: The honest general pair. A subclass that knows better — a decay, a
    #: correlation, an anisotropy — should say so, because that is the field a
    #: reader consults to know what it is looking at.
    ARTIFACT_KIND = "model_curve"
    OPERATION_TYPE = "analysis"

    #: Units of the two axes, as ``_mmfdb_column.units`` terms.
    #:
    #: Empty means *unknown*, which is the truthful default: an FCS lag axis is
    #: milliseconds and a TCSPC axis is nanoseconds, nothing about the numbers
    #: says which, and guessing is a mistake that never shows up as an error.
    X_UNITS = ""
    Y_UNITS = ""

    def _save_container(self, filename, *, xmin=None, xmax=None) -> None:
        """Write this curve into a container as a ``curve_point`` artifact.

        One shape for every curve ChiSurf writes, in the same file as the
        measurement it came from. What this replaces is five ChiSurf-authored
        ways to write the same five arrays — CSV, YAML, ``save_xy``, the vv/vh
        stack and the FCS writers — none of which could say what the x axis was
        in, and only one of which kept the mask.
        """
        from chisurf.core.fio.pto import Measurement, is_measurement

        x, y, ex, ey, mask = self[xmin:xmax]
        path = pathlib.Path(filename)
        opener = (
            Measurement.open(path, writable=True) if is_measurement(path)
            else Measurement.create_empty(path)
        )
        with opener as m:
            m.put_curve(
                self.name or path.stem,
                x, y,
                artifact_kind=self.ARTIFACT_KIND,
                operation_type=self.OPERATION_TYPE,
                # Written only when they carry information. A curve whose ex is
                # all zeros is saying "no x uncertainty", and a curve that never
                # had one should not say that.
                ex=ex if np.any(ex) else None,
                ey=ey if np.any(ey) else None,
                mask=mask if not np.all(mask) else None,
                x_units=self.X_UNITS,
                y_units=self.Y_UNITS,
            )

    def _load_container(self, filename) -> None:
        """Read this curve back out of a container."""
        from chisurf.core.fio.pto import Measurement

        path, _, member = str(filename).partition(CONTAINER_SELECTOR)
        with Measurement.open(path) as m:
            names = [o.name for o in m.artifacts()
                     if m.tag(o.uid, "_mmfdb_artifact.row_grain") == "curve_point"]
            if not names:
                raise ValueError(f"{path} holds no curve")
            if member and member not in names:
                raise ValueError(
                    f"{path} has no curve {member!r}; it holds {', '.join(names)}"
                )
            curve = m.get_curve(member or names[0])
        self.set_data(
            x=curve["x"],
            y=curve["y"],
            ex=curve.get("ex"),
            ey=curve.get("ey"),
            mask=curve.get("mask"),
        )

    def set_data(
            self,
            x: np.array,
            y: np.array,
            ex: np.array = None,
            ey: np.array = None,
            mask: np.array = None,
    ) -> None:
        """Assign x, y, error, and mask arrays to the curve.

        Parameters
        ----------
        x : np.ndarray
            X-values.
        y : np.ndarray
            Y-values.
        ex : np.ndarray, optional
            X-errors (default: ones).
        ey : np.ndarray, optional
            Y-errors (default: ones).
        mask : np.ndarray, optional
            Fit mask (default: ones).
        """
        self.x = x
        self.y = y
        if ex is None:
            ex = np.ones_like(x)
        if ey is None:
            ey = np.ones_like(y)
        if mask is None:
            mask = np.ones_like(y)
        self.ex = ex
        self.ey = ey
        self.mask = mask

    def set_weights(self, w: np.array):
        """Set y-weights (inverse of y-errors).

        Parameters
        ----------
        w : np.ndarray
            Weight values; ``ey`` is set to ``1 / w``.
        """
        self.ey = 1. / w

    def __getitem__(self, key: typing.Union[slice, int, np.ndarray, str]) -> typing.Tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray
    ]:
        """Index or slice the curve columns ``(x, y, ex, ey, mask)``.

        Parameters
        ----------
        key : slice, int, np.ndarray, or str
            Index used to slice each column.

        Returns
        -------
        tuple of np.ndarray
            Five-element tuple ``(x, y, ex, ey, mask)``.
        """
        return self.x[key], self.y[key], self.ex[key], self.ey[key], self.mask[key]


class DataGroup(list, chisurf.core.base.Base):
    """Container for multiple experimental datasets.

    Behaves like a list but tracks a *current* dataset and provides
    helpers to export the group to YAML.
    """

    @property
    def names(self) -> typing.List[str]:
        """Return the names of all datasets in this group."""
        return [d.name for d in self]

    @property
    def current_dataset(self) -> chisurf.core.base.Data:
        """Return the currently selected dataset.

        Raises
        ------
        IndexError
            If the group is empty.
        """
        if len(self) == 0:
            raise IndexError("Empty DataGroup has no current dataset")
        return self[self._current_dataset]

    @current_dataset.setter
    def current_dataset(self, i: int):
        """Set the index of the current (active) dataset.

        Parameters
        ----------
        i : int
            Index into this group.
        """
        self._current_dataset = i

    @property
    def name(self) -> str:
        """Return the group name, falling back to the current dataset's name.

        The fallback was unreachable: ``Base.__init__`` stamps
        ``self.__class__.__name__`` into ``__dict__['name']`` whenever no name
        is passed, so the ``KeyError`` branch could never be taken and every
        unnamed group called itself ``ExperimentDataCurveGroup``. That is what
        the dataset list showed after loading an FCS file. A stamped class name
        is not a name anyone chose, so it counts as absent here.
        """
        name = self.__dict__.get('name')
        if name and name != type(self).__name__:
            return name
        if len(self) == 0:
            # Nothing to fall back to, so the stamp stands.
            return name or "Empty group"
        return self.names[self._current_dataset]

    @name.setter
    def name(self, v: str) -> None:
        """Name the group explicitly, overriding the fallback.

        The getter reads ``self.__dict__['name']`` first, so a group is meant to
        carry a name of its own; without a setter nothing could ever put one
        there and ``group.name = ...`` raised ``AttributeError: can't set
        attribute`` — which is what grouping datasets does.
        """
        self.__dict__['name'] = str(v)

    @property
    def filename(self) -> str:
        """Return the filename of the first dataset in the group."""
        if len(self) == 0:
            return "Empty group"
        first = self[0]
        fn = getattr(first, '_filename', None)
        if fn:
            return fn
        return getattr(first, 'filename', str(first.name))

    def to_yaml(
            self,
            remove_protected: bool = False,
            convert_values_to_elementary: bool = True,
            skip_qt_widgets: bool = False
    ):
        """Serialize the group (including all contained datasets) to a YAML string.

        Parameters
        ----------
        remove_protected : bool
            Whether to omit protected attributes.
        convert_values_to_elementary : bool
            Whether to convert compound types to elementary types.
        skip_qt_widgets : bool
            If True, skip Qt widgets during serialization.

        Returns
        -------
        str
            YAML-formatted string.
        """
        d = self.to_dict(
            remove_protected=remove_protected,
            convert_values_to_elementary=convert_values_to_elementary,
            skip_qt_widgets=skip_qt_widgets
        )
        data = [
            d.to_dict(
                remove_protected=remove_protected,
                convert_values_to_elementary=convert_values_to_elementary,
                skip_qt_widgets=skip_qt_widgets
            ) for d in self
        ]
        d['data'] = data
        return yaml.dump(data=d)

    def append(self, dataset: chisurf.core.base.Data):
        """Append a dataset (or list of datasets) to the group.

        Only :class:`ExperimentalData` instances are accepted; others
        are silently ignored.

        Parameters
        ----------
        dataset : ExperimentalData or list
            Dataset(s) to append.
        """
        if isinstance(dataset, ExperimentalData):
            list.append(self, dataset)
        if isinstance(dataset, list):
            for d in dataset:
                if isinstance(d, ExperimentalData):
                    list.append(self, d)

    def __init__(
            self,
            seq: typing.Sequence,
            *args,
            **kwargs
    ):
        self._current_dataset: int = 0
        list.__init__(self, seq)
        chisurf.core.base.Base.__init__(self, *args, **kwargs)


class DataCurveGroup(DataGroup):
    """Data group whose elements are :class:`DataCurve` instances.

    Convenience properties proxy ``x``, ``y``, ``ex`` and ``ey`` to the
    current dataset.
    """

    @property
    def x(self) -> np.array:
        """Return the x-values of the current dataset."""
        return self.current_dataset.x

    @x.setter
    def x(self,
          v: np.array):
        """Set the x-values of the current dataset."""
        self.current_dataset.x = v

    @property
    def y(self) -> np.array:
        """Return the y-values of the current dataset."""
        return self.current_dataset.y

    @y.setter
    def y(self,
          v: np.array):
        """Set the y-values of the current dataset."""
        self.current_dataset.y = v

    @property
    def ex(self) -> np.array:
        """Return the x-errors of the current dataset."""
        return self.current_dataset.ex

    @ex.setter
    def ex(self, v: np.array):
        """Set the x-errors of the current dataset."""
        self.current_dataset.ex = v

    @property
    def ey(self) -> np.array:
        """Return the y-errors of the current dataset."""
        return self.current_dataset.ey

    @ey.setter
    def ey(self, v: np.array):
        """Set the y-errors of the current dataset."""
        self.current_dataset.ey = v

    @property
    def mask(self) -> np.array:
        """Return the fit mask of the current dataset."""
        return self.current_dataset.mask

    @mask.setter
    def mask(self, v: np.array):
        """Set the fit mask of the current dataset."""
        self.current_dataset.mask = v

    def __str__(self):
        """Return a list of string summaries for each dataset."""
        return [str(d) + "\n------\n" for d in self]

    def __getitem__(self, key):
        """Index or slice the group, returning 5-tuple for slices.

        Parameters
        ----------
        key : slice, int, np.ndarray, or str
            Index or slice.

        Returns
        -------
        tuple or DataCurve
            A 5-tuple ``(x, y, ex, ey, mask)`` for slices, or a
            :class:`DataCurve` for integer/string keys.
        """
        if isinstance(key, slice):
            return self.x[key], self.y[key], self.ex[key], self.ey[key], self.mask[key]
        return super().__getitem__(key)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ExperimentDataGroup(DataGroup):
    """Data group specialized for experiment-based datasets."""

    @property
    def setup(self):
        """Return the setup of the current dataset."""
        return self[self._current_dataset].setup

    @setup.setter
    def setup(self, v):
        # TODO: needs docstring — setter is a no-op; unclear why it exists
        pass

    @property
    def experiment(self):
        """Return the experiment of the current dataset."""
        return self[self._current_dataset].experiment

    @experiment.setter
    def experiment(self, v):
        # TODO: needs docstring — setter is a no-op; unclear why it exists
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ExperimentDataCurveGroup(ExperimentDataGroup, DataCurveGroup):
    """Hybrid group combining experimental metadata and curve access."""

    @property
    def setup(self):
        """Return the setup of the first dataset in the group."""
        return self[0].setup

    @setup.setter
    def setup(self, v):
        # TODO: needs docstring — setter is a no-op; unclear why it exists
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def get_data(
        curve_type: str = 'experiment',
        data_set: typing.List[
            chisurf.core.data.ExperimentalData
        ] = None,
        excludes_names: typing.List[str] = None
) -> typing.List[
    chisurf.core.data.ExperimentalData
]:
    """Return experimental datasets, optionally excluding some by name.

    Parameters
    ----------
    curve_type : str
        if this value is set to `experiment` only curves
        that are experimental curves, i.e., curves that inherit from
        `experiments.data.ExperimentalData` are returned.
    data_set : list
        A list containing the
    excludes_names : list
        A list containing names that should be excluded (default:
        ["Global-fit"]).

    Returns
    -------
    list
        A list containing datasets. If ``curve_type`` is ``'experiment'``
        only objects inheriting from :class:`ExperimentalData` or
        :class:`ExperimentDataGroup` are returned.

    Examples
    --------
    >>> from chisurf.core.data import ExperimentalData, get_data
    >>> d1 = ExperimentalData(name='A')
    >>> d2 = ExperimentalData(name='Global-fit')
    >>> [d.name for d in get_data(curve_type='experiment', data_set=[d1, d2])]
    ['A']

    """
    if excludes_names is None:
        excludes_names = ["Global-fit"]
    if curve_type == 'experiment':
        return [
            d for d in data_set if (
                    (
                            isinstance(d, ExperimentalData) or
                            isinstance(d, ExperimentDataGroup)
                    ) and
                    d.name not in excludes_names
            )
        ]
    else: #elif curve_type == 'all':
        return [
            d for d in data_set if
            isinstance(d, ExperimentalData) or
            isinstance(d, ExperimentDataGroup)
        ]
