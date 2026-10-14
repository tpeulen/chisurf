import os
import sys
import unittest

# Add the parent directory of 'chisurf' to sys.path
sys.path.append(os.getcwd())


class TestPluginStructure(unittest.TestCase):
    def test_imports(self):
        print("Testing plugin imports...")
        try:
            import chisurf.plugins.fcs.flc_2d  # noqa: F401

            print("Successfully imported chisurf.plugins.fcs.flc_2d")
        except ImportError as e:
            self.fail(f"Failed to import the plugin package: {e}")

    def test_gui_package(self):
        print("Testing gui package structure...")
        try:
            from chisurf.plugins.fcs.flc_2d.gui.app import make_app

            self.assertTrue(callable(make_app))
            print("Successfully imported the emtk app factory")
        except ImportError as e:
            self.fail(f"Failed to import gui components: {e}")

    def test_fit_package(self):
        print("Testing fit package structure...")
        try:
            from chisurf.plugins.fcs.flc_2d.fit import OneDMEMFitter, TwoDMEMFitter  # noqa: F401

            print("Successfully imported fit components")
        except ImportError as e:
            self.fail(f"Failed to import fit components: {e}")


if __name__ == "__main__":
    unittest.main()
