import unittest
from unittest.mock import MagicMock

import chisurf as cs
import chisurf.core.fitting.fit
import chisurf.core.fitting.parameter
from chisurf.core.project import fit_state


class MockFit(cs.core.base.Base):
    """A minimal stand-in for a fit: a uid plus a mocked model."""

    def __init__(self, name, uid):
        super().__init__()
        self.name = name
        self.meta_data["unique_identifier"] = uid
        self.model = MagicMock()
        # Mocking find_parameters to do nothing
        self.model.find_parameters = MagicMock()


def _state_of(state, name):
    """Return the (uid-keyed) state entry of the parameter called ``name``."""
    for p_state in state["parameters"].values():
        if p_state["name"] == name:
            return p_state
    raise AssertionError(f"{name} missing from the saved state")


class TestCrossFitLinking(unittest.TestCase):
    """Links whose target lives in another fit survive save/restore."""

    def setUp(self):
        # Clear global fits
        self._fits = cs.fits
        cs.fits = []

        # Create two fits with UIDs
        self.fit_a = MockFit("FitA", "UID-A")
        self.fit_b = MockFit("FitB", "UID-B")

        # Add to global registry
        cs.fits.append(self.fit_a)
        cs.fits.append(self.fit_b)

        # Setup parameters
        self.pa = cs.core.fitting.parameter.FittingParameter(name="amp_a", value=1.0)
        self.pb = cs.core.fitting.parameter.FittingParameter(name="amp_b", value=2.0)

        self.fit_a.model.parameters_all_dict = {"amp_a": self.pa}
        self.fit_a.model.parameters_all = [self.pa]
        self.fit_b.model.parameters_all_dict = {"amp_b": self.pb}
        self.fit_b.model.parameters_all = [self.pb]

    def tearDown(self):
        cs.fits = self._fits

    def test_cross_fit_serialization(self):
        # Link pa to pb
        self.pa.link = self.pb

        # Serialize fit_a
        state = fit_state._model_to_state(self.fit_a.model)

        # Verify link target info
        p_state = _state_of(state, "amp_a")
        self.assertEqual(p_state["link_target"], str(self.pb.unique_identifier))
        self.assertEqual(p_state["link_target_fit_uid"], "UID-B")

    def test_cross_fit_restoration(self):
        # Link pa to pb
        self.pa.link = self.pb
        state = fit_state._model_to_state(self.fit_a.model)

        # Create fresh pa (new model for fit_a), keeping the serialized UID so
        # the state is applied to it rather than to a name-matched fallback.
        new_pa = cs.core.fitting.parameter.FittingParameter(name="amp_a", value=0.0)
        new_pa.meta_data["unique_identifier"] = str(self.pa.unique_identifier)
        new_model_a = MagicMock()
        new_model_a.parameters_all_dict = {"amp_a": new_pa}
        new_model_a.parameters_all = [new_pa]

        # Apply state
        fit_state._apply_state_to_model(new_model_a, state)

        # Verify link
        self.assertIs(
            new_pa.link, self.pb, "Parameter should be linked to the live instance in fit_b"
        )


if __name__ == "__main__":
    unittest.main()
