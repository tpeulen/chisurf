import os
import pathlib
import unittest

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import copy
import glob
import tempfile

import numpy as np

import chisurf.core.data
import chisurf.core.experiments
import chisurf.core.fitting
import chisurf.core.fitting.fit
import chisurf.core.models
import chisurf.core.models.parse


def get_data_values(c_value: float = 3.1, a_value: float = 1.2, n_points: int = 32):
    x_data = np.linspace(0, 32, n_points)
    y_data = c_value + a_value * x_data**2.0
    return x_data, y_data


class FitTests(unittest.TestCase):
    def test_data_group(self):
        a_value = 1.2
        c_value = 3.1
        x_data, y_data = get_data_values(a_value=a_value, c_value=c_value)
        data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))
        data2 = copy.copy(data)
        self.assertEqual(np.allclose(data2.y, data.y), True)
        self.assertEqual(np.allclose(data2.x, data.x), True)
        return data, data2

    def test_fit_parse(self):
        test = True
        a_value = 1.2
        c_value = 3.1

        x_data, y_data = get_data_values(a_value=a_value, c_value=c_value)
        data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))
        fit = chisurf.core.fitting.fit.FitGroup(
            data=chisurf.core.data.DataGroup([data]),
            model_class=chisurf.core.models.parse.ParseModel,
        )
        model = fit.model
        model.func = "c+a*x**2"
        if test:
            self.assertEqual(len(model.parameters), 2)
            self.assertSetEqual(set(model.parameter_names), {"a", "c"})
            self.assertEqual(np.allclose(model.y, np.zeros_like(model.y)), True)
        fit_range = 0, len(model.y) - 1
        fit.fit_range = fit_range
        y_model = model.parameter_dict["c"].value + model.parameter_dict["a"].value * x_data**2.0
        fit.model.update()
        if test:
            self.assertEqual(np.allclose(y_model, model.y), True)
            self.assertTupleEqual(fit.fit_range, fit_range)

        # The fit range is bounded to the size of the data
        fit.fit_range = -10, len(model.y) + 30
        if test:
            self.assertTupleEqual(fit.fit_range, fit_range)
            self.assertAlmostEqual(fit.chi2, 248125.85601591066)
            self.assertEqual(
                np.allclose(
                    fit.weighted_residuals.y,
                    np.array(
                        [
                            2.1,
                            2.31311134,
                            2.95244537,
                            4.01800208,
                            5.50978148,
                            7.42778356,
                            9.77200832,
                            12.54245578,
                            15.73912591,
                            19.36201873,
                            23.41113424,
                            27.88647242,
                            32.7880333,
                            38.11581686,
                            43.8698231,
                            50.05005203,
                            56.65650364,
                            63.68917794,
                            71.14807492,
                            79.03319459,
                            87.34453694,
                            96.08210198,
                            105.2458897,
                            114.8359001,
                            124.85213319,
                            135.29458897,
                            146.16326743,
                            157.45816857,
                            169.1792924,
                            181.32663892,
                            193.90020812,
                        ]
                    ),
                ),
                True,
            )
        fit.run()
        chi2 = fit.chi2
        chi2r = chi2 / float(model.n_points - model.n_free - 1.0)
        if test:
            self.assertAlmostEqual(fit.chi2r, chi2r)
        fit.run()
        if test:
            self.assertAlmostEqual(fit.chi2r, 0.0)
            self.assertAlmostEqual(model.parameter_dict["a"].value, a_value)
            self.assertAlmostEqual(model.parameter_dict["c"].value, c_value)
            # The number of "free" parameters corresponds to the number
            # of fitting parameters
            self.assertEqual(fit.n_free, len(fit.model.parameters))

        fit.get_curves()

    def test_fit_save_full_length_curves_have_nan_padding(self):
        a_value = 1.2
        c_value = 3.1

        x_data, y_data = get_data_values(a_value=a_value, c_value=c_value)
        data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))
        fit = chisurf.core.fitting.fit.FitGroup(
            data=chisurf.core.data.DataGroup([data]),
            model_class=chisurf.core.models.parse.ParseModel,
        )
        fit.model.func = "c+a*x**2"

        # Use a fit range that exercises the xmax-exclusive behaviour
        fit.fit_range = 0, len(fit.model.y) - 1
        fit.model.update()

        # Full-length curves should match the original data length and contain NaNs outside the fit range.
        curves_full = fit.get_curves(full_length=True)
        self.assertIn("model", curves_full)
        self.assertIn("weighted residuals", curves_full)
        self.assertEqual(len(curves_full["model"].y), len(data.x))
        self.assertEqual(len(curves_full["weighted residuals"].y), len(data.x))

        # Outside of the fit window, values should be NaN (no shifts / no length changes)
        self.assertTrue(np.all(np.isnan(curves_full["model"].y[fit.xmax :])))
        self.assertTrue(np.all(np.isnan(curves_full["weighted residuals"].y[fit.xmax :])))

        # Inside the fit window, values should match the cropped arrays used for fitting
        expected_wres = fit.get_wres(model=fit.model, xmin=fit.xmin, xmax=fit.xmax)
        expected_wres = np.asarray(expected_wres, dtype=float)
        self.assertTrue(
            np.allclose(
                curves_full["weighted residuals"].y[fit.xmin : fit.xmin + expected_wres.size],
                expected_wres,
                equal_nan=False,
            )
        )
        self.assertTrue(
            np.allclose(
                curves_full["model"].y[fit.xmin : fit.xmax],
                fit.model.y[fit.xmin : fit.xmax],
                equal_nan=False,
            )
        )

        # Saving should write the full-length model and wres curves to disk as CSV.
        with tempfile.TemporaryDirectory() as td:
            base = os.path.join(td, "fit")
            fit.save(base, "csv", save_curves=True)

            # A FitGroup derives one filename per member, so the base picks up
            # a member suffix ("fit_00_model.csv"). Match on the curve name
            # rather than the naming convention: what this test is about is the
            # padding inside the file, not how the file got named.
            import glob

            models = glob.glob(os.path.join(td, "*_model.csv"))
            wres = glob.glob(os.path.join(td, "*_weighted residuals.csv"))
            self.assertEqual(len(models), 1, f"expected one model curve, got {models}")
            self.assertEqual(len(wres), 1, f"expected one residual curve, got {wres}")
            fn_model, fn_wres = models[0], wres[0]

            arr_model = np.loadtxt(fn_model)
            arr_wres = np.loadtxt(fn_wres)
            self.assertEqual(arr_model.shape[0], len(data.x))
            self.assertEqual(arr_wres.shape[0], len(data.x))
            self.assertTrue(np.all(np.isnan(arr_model[fit.xmax :, 1])))
            self.assertTrue(np.all(np.isnan(arr_wres[fit.xmax :, 1])))

    def test_fit_data_setter(self):
        c_value = 3.1
        a_value = 1.2
        x_data, y_data = get_data_values(a_value=a_value, c_value=c_value)

        data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))
        fit = chisurf.core.fitting.fit.FitGroup(
            data=chisurf.core.data.DataGroup([data]),
            model_class=chisurf.core.models.parse.ParseModel,
        )

        self.assertIs(fit.data, data)

        data_2 = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))

        self.assertIsNot(data, data_2)

        fit.data = data_2
        self.assertIs(fit.data, data_2)

    def test_fit_sample(self):
        import chisurf.core.fitting
        import chisurf.core.fitting.fit
        import chisurf.core.models
        import chisurf.core.models.parse

        c_value = 3.1
        a_value = 1.2
        x_data, y_data = get_data_values(a_value=a_value, c_value=c_value)

        data = chisurf.core.data.DataCurve(x=x_data, y=y_data, ey=np.ones_like(y_data))
        fit = chisurf.core.fitting.fit.FitGroup(
            data=chisurf.core.data.DataGroup([data]),
            model_class=chisurf.core.models.parse.ParseModel,
        )
        fit.fit_range = 0, len(fit.model.y)

        model = fit.model
        model.func = "c+a*x**2"
        fit.model.find_parameters()
        r = chisurf.core.fitting.sample.sample_ensemble(fit=fit, steps=100, nwalkers=5, thin=10)
        # ``lnprior`` is reported next to ``chi2r`` so the data misfit and the
        # prior stay separable in the stored chain (PRD-68); ``chains`` and
        # ``acceptance_rate`` carry the convergence evidence (PRD-69). Asserted
        # as a subset so adding further diagnostics is not a breaking change.
        self.assertLessEqual(
            {
                "chi2r",
                "lnprior",
                "parameter_values",
                "parameter_names",
                "chains",
                "acceptance_rate",
            },
            set(r.keys()),
        )
        self.assertEqual(len(r["chi2r"]), 50)
        self.assertEqual(len(r["lnprior"]), len(r["chi2r"]))
        # One chain per walker, each of the recorded length.
        self.assertEqual(r["chains"].shape[0], 5)
        self.assertEqual(r["chains"].shape[2], len(r["parameter_names"]))

        # There is an alternative sampler that directly saves to files. It
        # creates a timestamped sub-directory holding the chains.
        target_directory = tempfile.mkdtemp()
        n_runs = 5
        sampling_method = "ensemble"
        chisurf.core.fitting.fit.sample_fit(
            fit=fit,
            target_directory=target_directory,
            steps=10,
            thin=1,
            n_runs=n_runs,
            method=sampling_method,
        )

        # Every run is a file. Test if all the runs are written out
        chain_files = glob.glob(os.path.join(target_directory, "*", "chains", "*.er4"))
        self.assertEqual(len(chain_files), n_runs)

        fit.run()
        r = chisurf.core.fitting.sample.walk_mcmc(
            fit=fit, steps=50, step_size=0.1, chi2max=10, temp=1, thin=1
        )
        self.assertEqual(len(r["chi2r"]), 50)

        sampling_method = "mcmc"
        n_runs = 1
        fit.run()
        mcmc_directory = tempfile.mkdtemp()
        chisurf.core.fitting.fit.sample_fit(
            fit=fit,
            target_directory=mcmc_directory,
            steps=50,
            thin=1,
            n_runs=n_runs,
            method=sampling_method,
        )
        self.assertEqual(
            len(glob.glob(os.path.join(mcmc_directory, "*", "chains", "*.er4"))), n_runs
        )

        fit.run()

        import chisurf.core.fitting.support_plane

        r = chisurf.core.fitting.support_plane.scan_parameter(
            fit=fit, parameter_name="c", rel_range=0.2, n_steps=20
        )
        self.assertEqual(len(r["chi2r"]), 20)

    def test_sample_fit_rejects_non_curve_model(self):
        """sample_fit must raise ValueError for models lacking curve interface."""
        from types import SimpleNamespace

        from chisurf.core.fitting.fit import sample_fit

        class NonCurveModel:
            pass

        fit = SimpleNamespace(model=NonCurveModel())
        target_dir = tempfile.mkdtemp()
        with self.assertRaises(ValueError):
            sample_fit(
                fit,
                target_dir,
                steps=10,
                n_runs=1,
            )

    def test_support_plane_confidence_intervals(self):
        """Support-plane scans calculate all displayed p-value ranges."""
        import chisurf.core.fitting.support_plane

        intervals = chisurf.core.fitting.support_plane.confidence_intervals_from_scan_result(
            {
                "parameter_values": np.array([-3.0, -1.0, 0.0, 1.0, 3.0]),
                "chi2r": np.array([10.0, 2.0, 1.0, 2.0, 10.0]),
                "chi2r_min": 1.0,
                "v0": 0.0,
                "nu": 100,
                "n_extra_params": 1,
            },
            p_values=(0.68, 0.95, 0.99),
        )
        self.assertEqual([i["p_value"] for i in intervals], [0.68, 0.95, 0.99])
        for interval in intervals:
            lower, upper = interval["crossings"]
            self.assertLess(lower, 0.0)
            self.assertGreater(upper, 0.0)
            self.assertGreater(interval["threshold"], 1.0)
