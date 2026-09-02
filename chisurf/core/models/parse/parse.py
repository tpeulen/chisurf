from __future__ import annotations

import pathlib

import numpy
from numpy import *
from re import Scanner

import chisurf.logging
from chisurf import typing

import chisurf.core.fio
import chisurf.core.decorators
import chisurf.core.parameter
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.catalogue import EquationCatalogueMixin
from chisurf.core.models.model import ModelCurve


class ParseModel(EquationCatalogueMixin, ModelCurve, FittingParameterGroup):

    name = "Parse-Model"

    @property
    def func(self) -> str:
        """The equation string that defines the model."""
        return self._func

    @func.setter
    def func(self, v):
        """Set the equation string and trigger parsing."""
        self._func = v
        self.parse_code()

    def parse_code(self):
        """Parse the equation string and create fitting parameters for variables."""
        def var_found(scanner, name: str):
            """Handle a variable name found by the scanner.

            Parameters
            ----------
            scanner : Scanner
                The scanner instance.
            name : str
                The variable name found.

            Returns
            -------
            str
                The replacement token (``a[index]``) or the original name.
            """
            if 'scipy' in name:
                return name
            elif 'numpy' in name:
                return name
            elif 'np' in name:
                return name
            elif name in ('pi', 'e'):
                # Mathematical constants, not fittable parameters. Left alone
                # so `eval()` picks them up from the `from numpy import *` at
                # the top of this module, which is also how the C++ engine
                # resolves them -- both reserve `pi` and `e`.
                #
                # They were previously rewritten to `a[i]` like any other free
                # name, which made `pi` a **fit parameter initialised to 1.0**.
                # Three shipped equations use it (the dye-diffusion quenching
                # models, `...-4*pi*Rdye*Ddye*Nq**2/Vav*x*...`), so those were
                # computing with pi = 1 unless a user noticed the stray
                # parameter and typed 3.14159 into it. models.yaml gives it no
                # `initial:`, so nothing corrected it.
                #
                # Found by test/fitting/test_parse_uses_bff.py, which compares
                # the names this scanner finds against the ones the engine
                # finds -- a disagreement there means the two evaluators bind
                # different things and quietly return different curves.
                return name
            elif name not in self._keys:
                self._keys.append(name)
                ret = 'a[%d]' % self._count
                self._count += 1
            else:
                ret = 'a[%d]' % (self._keys.index(name))
            return ret

        code = self._func
        scanner = Scanner([
            # `x(?!\w)` and not `x`: the bare rule matched the leading
            # character of any name beginning with x, so `xD` was split into
            # the axis `x` and a parameter `D`, and the generated code read
            # `xa[1]` -- an undefined name. The shipped two-state quenching
            # model `p0*((1-xD)*(...)+xD*(...))` therefore failed with
            # `NameError: name 'xa' is not defined` on every evaluation.
            # Found by comparing the names this scanner finds against the ones
            # the C++ engine finds (test/fitting/test_parse_uses_bff.py).
            (r"x(?!\w)", lambda y, x: x),
            (r"[a-zA-Z]+\.", lambda y, x: x),
            (r"[a-z]+\(", lambda y, x: x),
            (r"[a-zA-Z_]\w*", var_found),
            (r"\d+\.\d*", lambda y, x: x),
            (r"\d+", lambda y, x: x),
            (r"\+|-|\*|/", lambda y, x: x),
            (r"\s+", None),
            (r"\)+", lambda y, x: x),
            (r"\(+", lambda y, x: x),
            (r",", lambda y, x: x),
        ])
        self._count = 0
        self._keys = list()
        parsed, rubbish = scanner.scan(code)
        parsed = ''.join(parsed)
        if rubbish != '':
            raise Exception('parsed: %s, rubbish %s' % (parsed, rubbish))
        self.code = parsed

        # Compile the equation in C++ as well, and prefer it. `eval()` is an
        # interpreter round trip on every fit iteration, which for a cheap
        # model is most of the iteration; `IMP.bff.Expression` compiles the
        # string once and evaluates it over the curve in C++.
        #
        # The ORIGINAL equation is compiled, not `parsed`: bff binds variables
        # by name, so the `a[0]`/`a[1]` rewrite the scanner does for `eval()`
        # is not needed and would only hide the names from it.
        #
        # `None` means fall back to `eval()`. That is not a failure path to be
        # tidied away later -- an equation may legitimately use a numpy or
        # scipy function the engine does not implement, and refusing it would
        # be a regression against a model a user already has.
        self._expression = None
        try:
            import IMP.bff as bff
        except ImportError as e:
            # A real deployment problem, not an expected fallback: chisurf
            # already imports IMP.bff in several core modules, so if it is
            # missing here every parse model silently drops onto the
            # interpreter and only a profiler would ever show it.
            chisurf.logging.warning(
                f"ParseModel: IMP.bff unavailable ({e}); every equation will "
                f"be evaluated by eval() instead of in C++")
        else:
            try:
                candidate = bff.Expression("parse")
                candidate.set_expression(self._func)
                self._expression = candidate
            except Exception:
                # Expected: the equation uses something the engine does not
                # implement, e.g. a numpy or scipy function. eval() handles it.
                self._expression = None

        # Define parameters. A name the selected catalogue entry has an
        # ``initial:`` value for starts there rather than at 1.0.
        #
        # Seeded here rather than assigned afterwards because *any* re-parse
        # rebuilds these objects -- and the editor triggers one while it builds, so
        # values applied after selection were silently replaced by 1.0 and the
        # table opened on defaults the catalogue had overridden. Doing it at
        # creation makes the result independent of who re-parses, and when.
        initial = (self.catalogue.get(self.model_name) or {}).get("initial") or {}
        self._parameters_equation.clear()
        for key in self._keys:
            value = 1.0
            if key in initial:
                try:
                    value = float(initial[key])
                except (TypeError, ValueError):
                    chisurf.logging.warning(
                        f"ParseModel: initial value {initial[key]!r} for {key!r} is not a number"
                    )
            p = FittingParameter(name=key, value=value)
            self._parameters_equation.append(p)
        self.find_parameters()

        # Resolve the name -> slot binding ONCE, now that the parameter list
        # is final. A fit changes only the values, so passing the names on
        # every iteration means SWIG rebuilds a std::vector<std::string> --
        # allocating and copying every name -- per step, for ~0.1 us a name.
        # Binding once removes 26-30% of a 512-point evaluation, which is the
        # length an FCS curve actually has.
        #
        # Bound against `_parameters_equation`, not `_keys`: the values array
        # in update_model() is built from that list, so binding to the same
        # source makes the two impossible to get out of order. The C++ side
        # refuses a call whose parameter count disagrees with the binding
        # rather than reading the right equation from the wrong slots.
        if self._expression is not None:
            try:
                self._expression.bind_parameters(
                    [p.name for p in self._parameters_equation], "x")
                # Filled in place each iteration rather than rebuilt: a fresh
                # `numpy.array([...])` per step cost 1.18 us of a 9 us
                # evaluation, for an array whose size never changes.
                self._values = numpy.empty(
                    len(self._parameters_equation), dtype=float)
            except Exception as e:
                chisurf.logging.warning(
                    f"ParseModel: could not bind parameters ({e}); "
                    f"falling back to eval() for {self._func!r}")
                self._expression = None

    def __init__(
            self,
            fit: chisurf.core.fitting.fit.Fit = None,
            *args,
            **kwargs,
    ):
        """Initialize the ParseModel.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit, optional
            Fit object this model is attached to.
        """
        super().__init__(fit,*args, **kwargs)
        self._keys = list()
        self._count = 0
        self._func = "x*0"
        self._parameters_equation = list()
        self._func_listeners = []
        self._expression = None
        # Which evaluator actually ran, counted rather than assumed. The whole
        # shipped catalogue is expected to evaluate in C++, and a test pins
        # that -- so a change which quietly drops every model back onto the
        # interpreter fails the suite rather than merely running slower, which
        # is the kind of regression nobody notices for months.
        self._n_eval_cpp = 0
        self._n_eval_python = 0
        self._values = None
        self._axis = None
        self._axis_source = None
        self.code = self._func
        # Open on a real equation. The default ``x*0`` has no free names, so an
        # unselected parse model computes a flat zero and its parameter table is
        # empty -- the hand-written editor never showed that because its combo box
        # applied entry 0 on construction. Selecting here means a script gets the
        # same starting point as the GUI.
        self.select_first_catalogue_entry()

    @property
    def evaluates_in_cpp(self) -> bool:
        """Whether this model's equation compiled for the C++ engine.

        False means :meth:`update_model` runs Python's ``eval`` instead --
        correct, but an interpreter round trip per fit iteration. Every
        equation ChiSurf ships compiles, so a False here is either a new
        equation using something the engine lacks, or a regression.
        """
        return getattr(self, "_expression", None) is not None

    @property
    def evaluation_counts(self) -> tuple:
        """``(in C++, in Python)`` -- how :meth:`update_model` has evaluated."""
        return (getattr(self, "_n_eval_cpp", 0),
                getattr(self, "_n_eval_python", 0))

    def _update_model(self, **kwargs):
        """Evaluate the parsed equation and update the model curve."""
        super()._update_model(**kwargs)
        x = self.fit.data.x
        if not hasattr(self, "_n_eval_cpp"):
            self._n_eval_cpp = 0
            self._n_eval_python = 0
        if getattr(self, "_values", None) is None or \
                len(self._values) != len(self._parameters_equation):
            self._values = numpy.empty(
                len(self._parameters_equation), dtype=float)
            self._axis_source = None
        expression = getattr(self, "_expression", None)
        if expression is not None:
            # Scalars stay scalars and the axis is read where it lies:
            # `compute_curve` is the only entry point shaped like a fit.
            # Passing the axis through `compute()` would convert it to a
            # Python list per call, and materialising the parameters as
            # full-length columns for `compute_columns()` costs a memcpy per
            # operand -- both measured slower than the `eval()` below.
            try:
                values = self._values
                for i, p in enumerate(self._parameters_equation):
                    values[i] = p.value
                # The axis is the same object for the life of a fit, so the
                # contiguity check is done once and remembered rather than on
                # every step.
                if x is not self._axis_source:
                    self._axis = numpy.ascontiguousarray(x, dtype=float)
                    self._axis_source = x
                # No names cross the boundary: the binding was resolved in
                # parse_code() and only the values change during a fit.
                self.y = expression.compute_curve_bound(values, self._axis)
                self._n_eval_cpp += 1
                return
            except Exception as e:
                # Never let the fast path break a fit that the interpreter
                # can still run: fall through, but say so once rather than
                # silently degrading on every iteration.
                chisurf.logging.warning(
                    f"ParseModel: C++ evaluation failed ({e}); "
                    f"falling back to eval() for {self._func!r}")
                self._expression = None

        a = [p.value for p in self._parameters_equation]
        # TODO: better evaluate when the func is set
        y = eval(self.code)
        self.y = y
        self._n_eval_python += 1

