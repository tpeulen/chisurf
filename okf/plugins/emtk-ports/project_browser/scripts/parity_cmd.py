"""Run `python -m test.gui.emtk_port_parity <phase> project_browser --out <dir>` on temporary HOME, settings and a scratch database
(the browser lists and, on first use, authenticates against the project database: never the user's own)."""
import os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
tmp = pathlib.Path(tempfile.mkdtemp(prefix="pb_"))
os.environ.update(HOME=str(tmp / "home"), CHISURF_SETTINGS_DIR=str(tmp / "s"), MMFDB_SETTINGS_DIR=str(tmp / "m"), MMFDB_DATABASE_PATH=str(tmp / "projects.sqlite"))
(tmp / "home").mkdir()
from test.gui.emtk_port_parity import main
sys.exit(main(sys.argv[1:]))
