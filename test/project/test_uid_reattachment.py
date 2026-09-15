import unittest
from unittest.mock import MagicMock
import numpy as np
import chisurf as cs
import chisurf.core.data
from chisurf.core.project import fit_state

class TestUIDReattachment(unittest.TestCase):
    """
    Test that IRF and Background curves are correctly re-attached via UID
    during project state restoration.
    """

    def setUp(self):
        # Clear imported datasets
        cs.imported_datasets = cs.core.data.DataGroup([], name="Datasets")
        
        # Create mock data curves with UIDs
        self.irf_curve = cs.core.data.DataCurve(
            x=np.arange(10, dtype=float),
            y=np.random.rand(10),
            name="TestIRF",
            unique_identifier="UID-IRF-123"
        )
        self.bg_curve = cs.core.data.DataCurve(
            x=np.arange(10, dtype=float),
            y=np.random.rand(10),
            name="TestBG",
            unique_identifier="UID-BG-456"
        )
        
        # Add to global registry
        cs.imported_datasets.append(self.irf_curve)
        cs.imported_datasets.append(self.bg_curve)

    def test_tcspc_uid_roundtrip(self):
        # 1. Setup a "live" model with external curve links
        model = MagicMock()
        model.parameters_all_dict = {}
        
        model.generic = MagicMock()
        model.generic.background_curve = self.bg_curve
        model.generic.get_state.return_value = {}
        
        model.convolve = MagicMock()
        model.convolve._irf = self.irf_curve
        model.convolve.get_state.return_value = {}
        
        # 2. Serialize to state
        state = fit_state._model_to_state(model)
        
        # Verify UIDs are captured in the state
        tcspc_extra = state.get("extra", {}).get("tcspc", {})
        self.assertEqual(tcspc_extra.get("generic", {}).get("background_curve_uid"), "UID-BG-456")
        self.assertEqual(tcspc_extra.get("convolve", {}).get("irf_uid"), "UID-IRF-123")
        
        # 3. Restore into a NEW model instance
        new_model = MagicMock()
        new_model.parameters_all_dict = {}
        new_model.generic = MagicMock()
        new_model.convolve = MagicMock()
        
        fit_state._apply_state_to_model(new_model, state)
        
        # 4. Verify reattachment via call recording
        # Property assignment is recorded as a call to the mock attribute if it's not a real object.
        # But for MagicMock, it's safer to check the attribute value if it was a real assignment.
        # Since we use `new_model.generic.background_curve = ...`, 
        # new_model.generic.background_curve should be the mock object representing the curve.
        
        # In fit_state.py: generic.background_curve = target_bg
        # If generic is a MagicMock, then generic.background_curve should be set to target_bg.
        self.assertIs(new_model.generic.background_curve, self.bg_curve)
        self.assertIs(new_model.convolve._irf, self.irf_curve)
        print("UID Reattachment verified for mocks.")

if __name__ == "__main__":
    unittest.main()
