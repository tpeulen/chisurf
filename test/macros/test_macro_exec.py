import pytest
from qtpy import QtWidgets

# Building the ChiSurf main window needs a running QApplication: without one
# Qt does not raise, it aborts the whole process and takes the test session
# with it. The non-GUI suite has no application, so skip at import time.
if QtWidgets.QApplication.instance() is None:
    pytest.skip(
        "the ChiSurf main window needs a QApplication", allow_module_level=True
    )


import sys
import pathlib
import importlib
import chisurf as cs
from chisurf.gui.main import Main

# Create a Main instance
main = Main()

# Path to the pong plugin's __init__.py file
plugin_path = pathlib.Path(cs.plugins.__file__).parent / "misc" / "games" / "pong" / "__init__.py"
print(f"Testing macro execution with file: {plugin_path}")

try:
    # Run the macro using the 'exec' executor
    main.onRunMacro(filename=plugin_path, executor='exec')
    print("Macro executed successfully!")
except Exception as e:
    print(f"Error executing macro: {e}")
    import traceback
    traceback.print_exc()