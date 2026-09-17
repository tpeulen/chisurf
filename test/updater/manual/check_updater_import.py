import pathlib
import sys

# Add the parent directory to the Python path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# Try importing the updater module
try:
    from chisurf.plugins.core.updater import UpdaterWidget

    print("Successfully imported UpdaterWidget from chisurf.plugins.core.updater")
except ImportError as e:
    print(f"Import error: {e}")

print("Test completed")
