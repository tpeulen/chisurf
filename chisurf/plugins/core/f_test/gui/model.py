"""Qt-free statistical state shared by the native and reference F-test tools."""

from pathlib import Path
from typing import Any

from chisurf.core.dataspec import load_view_spec
from chisurf.core.math.statistics import chi2_max, f_test_chi2r, f_test_confidence

_GUI_DIR = Path(__file__).parent

#: Edited attr -> the recompute method it triggers (mirrors the legacy slots).
_CONF_ATTRS = frozenset({"chi2_2", "n1", "n2"})
_CHI2_2_ATTRS = frozenset({"chi2_1", "conf_level"})
_CHI2_MAX_ATTRS = frozenset({"chi2_min", "npars", "dof", "conf_level_2"})


class FTestModel:
    """Backing model for the F-test / χ²-max calculator; fields in ftest.view.json."""

    def __init__(self) -> None:
        # F-test: compare two nested models. The defaults describe a plausible
        # pair -- the extra parameters of model 2 buy a 10% lower reduced χ².
        self.chi2_1 = 1.1
        self.n1 = 100
        self.chi2_2 = 1.0
        self.n2 = 98
        self.conf_level = 0.95
        self.recompute_conf()
        # χ²-max: upper χ² limit from a single fit.
        self.chi2_min = 1.0
        self.npars = 1
        self.dof = 100
        self.conf_level_2 = 0.95
        self.chi2_max = 0.0
        self.recompute_chi2_max()

    def view_spec(self):
        return load_view_spec(_GUI_DIR / "ftest.view.json")

    def recompute_conf(self, _value=None) -> None:
        """Confidence that model 2 is justified: ``F.cdf(χ²₁/χ²₂, n₁, n₂)``."""
        try:
            self.conf_level = f_test_confidence(
                chi2r_1=self.chi2_1, chi2r_2=self.chi2_2, nu_1=self.n1, nu_2=self.n2
            )
        except (ZeroDivisionError, ValueError):
            pass

    def recompute_chi2_2(self, _value=None) -> None:
        """χ²(2) threshold for the current confidence: ``χ²₁ / F.ppf(conf, n₁, n₂)``."""
        try:
            self.chi2_2 = f_test_chi2r(
                chi2r_1=self.chi2_1, conf_level=self.conf_level, nu_1=self.n1, nu_2=self.n2
            )
        except (ZeroDivisionError, ValueError):
            pass

    def recompute_chi2_max(self, _value=None) -> None:
        """Upper χ² limit of a fit at ``conf_level_2`` for ``npars`` parameters and ``dof``."""
        self.chi2_max = float(
            chi2_max(
                chi2_value=self.chi2_min,
                number_of_parameters=max(1, int(self.npars)),
                nu=max(1, int(self.dof)),
                conf_level=self.conf_level_2,
            )
        )


    def edit_field(self, attr: str, value: Any) -> None:
        """Apply an edited statistic using the reference tool's coupling rules."""
        if attr not in _CONF_ATTRS | _CHI2_2_ATTRS | _CHI2_MAX_ATTRS:
            raise ValueError(f"Unknown editable statistic: {attr}")
        setattr(self, attr, value)
        self.field_edited(attr)

    def field_edited(self, attr: str) -> None:
        if attr in _CONF_ATTRS:
            self.recompute_conf()
        elif attr in _CHI2_2_ATTRS:
            self.recompute_chi2_2()
        if attr in _CHI2_MAX_ATTRS:
            self.recompute_chi2_max()

    def load_fit(self, fit: Any, target: str) -> None:
        """Copy fit statistics into one of the reference tool's three targets."""
        n_points = int(fit.model.n_points)
        n_free = int(fit.model.n_free)
        chi2r = float(fit.chi2r)
        if target == "model1":
            self.chi2_1, self.n1 = chi2r, max(1, n_points - n_free)
            self.recompute_chi2_2()
        elif target == "model2":
            self.chi2_2, self.n2 = chi2r, max(1, n_points - n_free)
            self.recompute_conf()
        elif target == "chi2max":
            self.chi2_min, self.npars, self.dof = chi2r, n_free, max(1, n_points - n_free)
            self.recompute_chi2_max()
        else:
            raise ValueError(f"Unknown fit load target: {target}")
