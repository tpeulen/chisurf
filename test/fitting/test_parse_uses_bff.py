"""ChiSurf's parse models must evaluate in C++, not in `eval()`.

`ParseModel` compiles its equation with `IMP.bff.Expression` and evaluates it
through `compute_curve`. It keeps `eval()` as a fallback on purpose -- an
equation may use a numpy or scipy function the engine does not implement, and
refusing it would break a model a user already has.

That fallback is the hazard these tests exist for. It is silent by design, so
a change that stops the C++ path compiling -- a renamed method, a missing
`IMP.bff`, a new engine that rejects a spelling the old one took -- would not
break anything. Every fit would simply go back to an interpreter round trip
per iteration, and nobody would find out except by profiling.

So the property is asserted rather than assumed: **every equation ChiSurf
ships compiles for the engine, and `update_model` actually takes that path.**
"""

import pathlib
import unittest

import numpy as np
import yaml

MODELS = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "core" / "models"


def catalogue_equations():
    """Every ``equation:`` ChiSurf ships, deduplicated.

    Parsed as YAML rather than line by line: several equations wrap across
    lines, and a line reader truncates them into unbalanced expressions that
    then look like engine gaps.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "equation" and isinstance(value, str):
                    found.append(" ".join(value.split()))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in sorted(MODELS.rglob("*.yaml")):
        try:
            walk(yaml.safe_load(path.read_text()))
        except Exception:
            continue
    return sorted(set(found))


class BffIsAvailableTests(unittest.TestCase):
    """The dependency itself, checked separately so its failure is legible."""

    def test_imp_bff_imports(self):
        import IMP.bff  # noqa: F401

    def test_the_engine_exposes_the_entry_point_the_model_uses(self):
        """`compute_curve` is the only entry point shaped like a fit.

        `compute()` converts the axis to a Python list per call and measured
        four times slower than `eval()`; `compute_columns()` needs every
        operand the same length, so each scalar parameter is materialised as
        a full column and the memcpy costs more than the arithmetic. If this
        attribute ever disappears, the model must not quietly use one of those.
        """
        import IMP.bff as bff
        self.assertTrue(hasattr(bff.Expression, "compute_curve"))


class CatalogueCompilesForTheEngineTests(unittest.TestCase):
    """Every shipped equation, compiled by the same call ParseModel makes."""

    @classmethod
    def setUpClass(cls):
        cls.equations = catalogue_equations()

    def test_the_catalogue_is_not_empty(self):
        """Guards the tests below: an empty catalogue would pass vacuously."""
        self.assertGreater(len(self.equations), 20,
                           f"found only {len(self.equations)} equations under {MODELS}")

    def test_every_shipped_equation_compiles_for_the_engine(self):
        import IMP.bff as bff
        refused = []
        for equation in self.equations:
            try:
                ex = bff.Expression("parse")
                ex.set_expression(equation)
            except Exception as e:
                refused.append((equation, str(e)[:80]))
        self.assertEqual(
            refused, [],
            f"{len(refused)} of {len(self.equations)} shipped equations no "
            f"longer compile for the C++ engine, so those models have fallen "
            f"back to eval():\n" +
            "\n".join(f"  {q}\n    {why}" for q, why in refused[:10]))

    def test_the_engine_agrees_with_the_interpreter(self):
        """Compiling is not enough -- it has to give the same curve."""
        import IMP.bff as bff
        env = {"__builtins__": {}, "exp": np.exp, "sqrt": np.sqrt,
               "abs": np.abs, "log": np.log, "log10": np.log10,
               "sin": np.sin, "cos": np.cos, "tan": np.tan,
               "pi": np.pi, "e": np.e, "pow": np.power,
               "min": np.minimum, "max": np.maximum}
        x = np.linspace(0.01, 10.0, 512)
        checked = 0
        for equation in self.equations:
            try:
                ex = bff.Expression("parse")
                ex.set_expression(equation)
            except Exception:
                continue
            names = [v for v in ex.get_variable_names() if v != "x"]
            values = np.array([1.3 + 0.1 * i for i in range(len(names))],
                              dtype=float)
            scope = dict(env, x=x, **dict(zip(names, values)))
            try:
                want = np.atleast_1d(eval(equation, {"__builtins__": {}}, scope))
            except Exception:
                continue  # no interpreter oracle for this one
            got = ex.compute_curve(names, values, "x", x)
            np.testing.assert_allclose(got, want, rtol=1e-10, equal_nan=True,
                                       err_msg=equation)
            checked += 1
        self.assertGreater(checked, 20, "too few equations had an oracle")


class ParseModelTakesTheCppPathTests(unittest.TestCase):
    """The model's own parsing, not just the engine underneath it.

    These drive the real `ParseModel.parse_code()` -- the method the `func`
    setter calls -- rather than reaching past it, so a change to how the model
    compiles its equation is caught here and not only in the engine tests.

    `update_model()` itself is deliberately not driven: assigning `self.y`
    goes through the model's data machinery, which needs a real `Fit`. That
    belongs in an integration test, and its absence is why the counters below
    exist -- they let one be written without reaching into private state.
    """

    def bare_model(self, equation):
        """A ParseModel far enough constructed to parse, and no further."""
        from chisurf.core.models.parse.parse import ParseModel
        m = ParseModel.__new__(ParseModel)
        m._keys = []
        m._count = 0
        m._parameters_equation = []
        m._func_listeners = []
        m._expression = None
        m._n_eval_cpp = 0
        m._n_eval_python = 0
        m._func = equation
        return m

    def test_every_shipped_equation_parses_onto_the_cpp_engine(self):
        """The assertion this file exists for.

        Not "the engine can compile these" -- that is the previous class --
        but "the model, parsing exactly as it does in a fit, ends up with a
        compiled expression". A fallback to `eval()` for any shipped equation
        is a performance regression that nothing else would report.
        """
        equations = catalogue_equations()
        self.assertGreater(len(equations), 20)
        fell_back = []
        for equation in equations:
            m = self.bare_model(equation)
            m.parse_code()
            if not m.evaluates_in_cpp:
                fell_back.append(equation)
        self.assertEqual(
            fell_back, [],
            f"{len(fell_back)} of {len(equations)} shipped equations fall back "
            f"to eval() after parse_code(), so those fits pay an interpreter "
            f"round trip per iteration:\n" +
            "\n".join(f"  {q}" for q in fell_back[:10]))

    def test_parsing_finds_the_same_names_the_engine_does(self):
        """The model passes `_keys` to `compute_curve`, which binds by name.

        If the scanner and the engine ever disagreed about the free names, the
        model would bind the right equation to the wrong columns -- a wrong
        curve, not an error. `x` is the axis and belongs to neither list.
        """
        for equation in catalogue_equations():
            m = self.bare_model(equation)
            m.parse_code()
            if not m.evaluates_in_cpp:
                continue
            engine_names = {v for v in m._expression.get_variable_names()
                            if v != "x"}
            with self.subTest(equation):
                self.assertEqual(set(m._keys), engine_names)

    def test_a_model_with_no_compiled_expression_says_so(self):
        """The property must report the fallback honestly, not optimistically."""
        m = self.bare_model("b+a1*exp(-x/t1)")
        m._expression = None
        self.assertFalse(m.evaluates_in_cpp)

    def test_an_equation_the_engine_cannot_take_falls_back_rather_than_raising(self):
        """The fallback still has to work: it is why it is kept."""
        m = self.bare_model("scipy.special.erf(x)")
        try:
            m.parse_code()
        except Exception:
            self.skipTest("the scanner itself rejects this spelling")
        self.assertFalse(m.evaluates_in_cpp)

    def test_the_counters_distinguish_the_two_paths(self):
        m = self.bare_model("b+a1*exp(-x/t1)")
        self.assertEqual(m.evaluation_counts, (0, 0))
        m._n_eval_cpp += 1
        self.assertEqual(m.evaluation_counts, (1, 0))
        m._n_eval_python += 1
        self.assertEqual(m.evaluation_counts, (1, 1))


class ScannerDefectsFoundByTheComparisonTests(unittest.TestCase):
    """Two bugs the name comparison above turned up, pinned so they stay dead.

    Both were pre-existing and neither was caused by moving evaluation into
    C++. They surfaced because the engine parses the same string and the two
    disagreed -- which is the whole reason to compare rather than trust.
    """

    def bare_model(self, equation):
        from chisurf.core.models.parse.parse import ParseModel
        m = ParseModel.__new__(ParseModel)
        m._keys, m._count = [], 0
        m._parameters_equation, m._func_listeners = [], []
        m._expression = None
        m._n_eval_cpp = m._n_eval_python = 0
        m._func = equation
        return m

    def test_pi_is_a_constant_not_a_fit_parameter(self):
        """`pi` used to become a free parameter initialised to 1.0.

        Three shipped dye-diffusion models multiply by `4*pi*Rdye*Ddye`, so
        they computed with pi = 1 -- a factor of pi wrong in the quenching
        term -- unless a user noticed the stray "pi" parameter in the table
        and typed 3.14159 into it. models.yaml gives it no initial value.
        """
        m = self.bare_model("a0*4*pi*Rdye*x")
        m.parse_code()
        self.assertNotIn("pi", m._keys)
        self.assertNotIn("pi", [p.name for p in m._parameters_equation])

    def test_a_name_beginning_with_x_is_not_split(self):
        """`xD` used to be read as the axis `x` followed by a parameter `D`.

        The generated code then said `xa[1]`, and the shipped two-state
        quenching model failed outright with
        `NameError: name 'xa' is not defined` on every single evaluation.
        """
        m = self.bare_model("p0*(1-xD)+xD*a1")
        m.parse_code()
        self.assertIn("xD", m._keys)
        self.assertNotIn("D", m._keys)
        self.assertNotIn("xa[", m.code)

    def test_the_axis_itself_is_still_the_axis(self):
        """The narrowed rule must not stop `x` being recognised alone."""
        m = self.bare_model("a0*exp(-x/t1)")
        m.parse_code()
        self.assertNotIn("x", m._keys)
        self.assertIn("x", m.code)

    def test_the_repaired_model_now_evaluates(self):
        """End to end for the equation that used to raise: it produces a curve."""
        import IMP.bff as bff
        eq = ("p0*((1-xD)*(a1*exp(-x*(1/tau1+kQ))+a2*exp(-x*(1/tau2+kQ)))"
              "+xD*(a1*exp(-x*(1/tau1))+a2*exp(-x*(1/tau2))))")
        m = self.bare_model(eq)
        m.parse_code()
        self.assertTrue(m.evaluates_in_cpp)
        names = list(m._keys)
        values = np.array([0.5 + 0.1 * i for i in range(len(names))])
        x = np.linspace(0.1, 5.0, 64)
        y = m._expression.compute_curve(names, values, "x", x)
        self.assertEqual(len(y), len(x))
        self.assertTrue(np.all(np.isfinite(y)))


class UpdateModelRunsInCppTests(unittest.TestCase):
    """`update_model()` itself, through a real `Fit`.

    The classes above stop at `parse_code()`, which proves the equation
    *compiled* for the engine. This proves the fit actually *uses* it: a model
    could compile fine and still fall back on every iteration if
    `compute_curve` threw -- the fallback catches that and logs, so nothing
    else would fail.

    A `ModelCurve` is constructed by a `Fit` and reads its axis from
    `fit.data`; it cannot be instantiated bare, which is why these build the
    real object rather than a stub.
    """

    def build(self, equation, n=256):
        from chisurf.core.data import DataCurve
        from chisurf.core.fitting.fit import Fit
        from chisurf.core.models.parse.parse import ParseModel
        x = np.linspace(0.1, 10.0, n)
        fit = Fit(model_class=ParseModel, data=DataCurve(x=x, y=np.zeros_like(x)))
        model = fit.model
        model.func = equation
        return model, x

    def test_one_update_evaluates_in_cpp_and_not_in_python(self):
        model, _ = self.build("b+a1*exp(-x/t1)")
        self.assertEqual(model.evaluation_counts, (0, 0))
        model.update()
        self.assertEqual(
            model.evaluation_counts, (1, 0),
            "_update_model() did not take the C++ path; the counters say "
            f"{model.evaluation_counts} (cpp, python)")

    def test_repeated_iterations_stay_in_cpp(self):
        """A fit is thousands of these. None may drift onto the interpreter."""
        model, _ = self.build("b+a1*exp(-x/t1)+a2*exp(-x/t2)")
        for _ in range(50):
            model.update()
        cpp, python = model.evaluation_counts
        self.assertEqual(python, 0, f"{python} of 50 iterations fell back to eval()")
        self.assertEqual(cpp, 50)

    def test_the_curve_is_the_one_numpy_computes(self):
        """Fast is worthless if it is wrong."""
        model, x = self.build("b+a1*exp(-x/t1)")
        values = {"b": 0.3, "a1": 2.0, "t1": 1.5}
        for p in model._parameters_equation:
            p.value = values[p.name]
        model.update()
        want = 0.3 + 2.0 * np.exp(-x / 1.5)
        np.testing.assert_allclose(np.asarray(model.y), want, rtol=1e-12)

    def test_the_model_that_used_to_raise_now_produces_a_curve(self):
        """End to end for the `xD` defect: it failed on every evaluation.

        Before the scanner's `x` rule was narrowed, this equation generated
        `xa[1]` and raised `NameError: name 'xa' is not defined`.
        """
        model, _ = self.build(
            "p0*((1-xD)*(a1*exp(-x*(1/tau1+kQ))+a2*exp(-x*(1/tau2+kQ)))"
            "+xD*(a1*exp(-x*(1/tau1))+a2*exp(-x*(1/tau2))))")
        self.assertIn("xD", model._keys)
        model.update()
        self.assertEqual(model.evaluation_counts, (1, 0))
        y = np.asarray(model.y)
        self.assertTrue(np.all(np.isfinite(y)))

    def test_the_counters_would_catch_a_regression(self):
        """The guard has to bite, or the tests above pass vacuously.

        Drops the compiled expression the way a regression would -- a renamed
        method, an engine that stopped accepting a spelling -- and checks the
        counters report the interpreter, rather than the model carrying on
        looking healthy.
        """
        model, _ = self.build("b+a1*exp(-x/t1)")
        model._expression = None
        model.update()
        self.assertEqual(model.evaluation_counts, (0, 1))
        self.assertFalse(model.evaluates_in_cpp)
        # and the fallback still has to produce a curve; that is its job
        self.assertTrue(np.all(np.isfinite(np.asarray(model.y))))

    def test_every_shipped_equation_evaluates_in_cpp_through_a_real_fit(self):
        """The whole catalogue, driven the way a fit drives it.

        Slower than the `parse_code()` sweep above and deliberately kept
        separate from it: this one can only fail for a reason that sweep
        cannot see, namely `compute_curve` throwing at evaluation time.
        """
        equations = catalogue_equations()
        self.assertGreater(len(equations), 20)
        fell_back = []
        for equation in equations:
            try:
                model, _ = self.build(equation, n=64)
                model.update()
            except Exception as e:
                fell_back.append((equation, f"raised {type(e).__name__}: {e}"))
                continue
            cpp, python = model.evaluation_counts
            if python or not cpp:
                fell_back.append((equation, f"counts {(cpp, python)}"))
        self.assertEqual(
            fell_back, [],
            f"{len(fell_back)} of {len(equations)} shipped equations do not "
            f"evaluate in C++ through a real fit:\n" +
            "\n".join(f"  {q}\n    {why}" for q, why in fell_back[:10]))


class NoStringsCrossTheBoundaryPerIterationTests(unittest.TestCase):
    """A fit must not re-pass the variable names on every iteration.

    The names cannot change while a fit runs, but `compute_curve()` takes
    them per call, so SWIG rebuilds a `std::vector<std::string>` -- allocating
    and copying each one -- every step. Measured at ~0.1 us a name, which is
    26-30% of a 512-point evaluation for a typical model. `bind_parameters()`
    resolves the mapping once and `compute_curve_bound()` passes only values.
    """

    def build(self, equation, n=128):
        from chisurf.core.data import DataCurve
        from chisurf.core.fitting.fit import Fit
        from chisurf.core.models.parse.parse import ParseModel
        x = np.linspace(0.1, 10.0, n)
        fit = Fit(model_class=ParseModel, data=DataCurve(x=x, y=np.zeros_like(x)))
        model = fit.model
        model.func = equation
        return model, x

    def test_parsing_establishes_the_binding(self):
        model, _ = self.build("b+a1*exp(-x/t1)")
        self.assertTrue(model.evaluates_in_cpp)
        self.assertTrue(model._expression.has_parameter_binding())

    def test_every_shipped_equation_is_bound(self):
        """An unbound model would still work -- and silently pay per step."""
        unbound = []
        for equation in catalogue_equations():
            model, _ = self.build(equation, n=32)
            if model.evaluates_in_cpp and \
                    not model._expression.has_parameter_binding():
                unbound.append(equation)
        self.assertEqual(unbound, [],
                         f"{len(unbound)} equations compiled but were not bound")

    def test_the_bound_call_agrees_with_the_named_one(self):
        """Binding is an optimisation; it may not change a single value."""
        import IMP.bff as bff
        x = np.linspace(0.01, 10.0, 512)
        for equation, names in [("b+a1*exp(-x/t1)", ["b", "a1", "t1"]),
                                ("b+1/N*(1+x/td)**(-1)/sqrt(1+1/s**2*x/td)",
                                 ["b", "N", "td", "s"])]:
            ex = bff.Expression("m")
            ex.set_expression(equation)
            ex.bind_parameters(names, "x")
            values = np.arange(1.0, len(names) + 1.0)
            with self.subTest(equation):
                np.testing.assert_allclose(
                    ex.compute_curve_bound(values, x),
                    ex.compute_curve(names, values, "x", x), rtol=1e-15)

    def test_a_binding_that_no_longer_matches_is_refused(self):
        """Wrong slots would give a wrong curve, not an error, so it throws."""
        import IMP.bff as bff
        ex = bff.Expression("m")
        ex.set_expression("b+a1*exp(-x/t1)")
        ex.bind_parameters(["b", "a1", "t1"], "x")
        x = np.linspace(0.1, 5.0, 16)
        with self.assertRaises(ValueError):
            ex.compute_curve_bound(np.array([1.0, 2.0]), x)   # two, not three

    def test_evaluating_before_binding_is_refused(self):
        import IMP.bff as bff
        ex = bff.Expression("m")
        ex.set_expression("b+a1*exp(-x/t1)")
        with self.assertRaises(ValueError):
            ex.compute_curve_bound(np.array([1.0, 2.0, 3.0]),
                                   np.linspace(0.1, 5.0, 16))

    def test_a_new_equation_drops_the_old_binding(self):
        """Reusing it would evaluate the new equation from the old slots."""
        import IMP.bff as bff
        ex = bff.Expression("m")
        ex.set_expression("b+a1*exp(-x/t1)")
        ex.bind_parameters(["b", "a1", "t1"], "x")
        ex.set_expression("p+q*x")
        with self.assertRaises(ValueError):
            ex.compute_curve_bound(np.array([1.0, 2.0, 3.0]),
                                   np.linspace(0.1, 5.0, 16))


if __name__ == "__main__":
    unittest.main()
