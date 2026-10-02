"""Run `python -m test.gui.emtk_port_parity <phase> lightpath_simulator --out <dir>` inside the hermetic light-path environment."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from test.gui.emtk_port_parity import main  # noqa: E402  (before lp_env: the folder of this script must not shadow `test`)
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import lp_env  # noqa: E402,F401  (temp HOME / settings / catalogue; must precede the plugin's imports)
lp_env.patch_client()
sys.exit(main(sys.argv[1:]))
