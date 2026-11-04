"""cmc-light: SCPI-controlled 3-laser source for ALEX smFRET, on an ESP8266."""

import sys

# Register 'cmc_light' in sys.modules if not present, pointing to this in-tree package
_self = sys.modules.get(__name__)
if _self is not None and "cmc_light" not in sys.modules:
    sys.modules["cmc_light"] = _self

try:
    from .client import LaserSource, ScpiError, find_instruments  # noqa: F401
    from .seqcore import alex_steps  # noqa: F401
    from .instrument import Instrument  # noqa: F401
    from .sim import SimHardware, make_instrument  # noqa: F401
    from .steps_text import parse as parse_steps, format_steps, format_csv  # noqa: F401
    from .preview_edit import laser_windows, boundaries, drag_boundary, merge_windows  # noqa: F401
    from .units import fmt_power  # noqa: F401
    from .sense import Sensor, find_sensors, Reading, SenseError  # noqa: F401
    from .sense_cal import Calibration  # noqa: F401
except (ImportError, ValueError):
    from cmc_light.client import LaserSource, ScpiError, find_instruments  # noqa: F401
    from cmc_light.seqcore import alex_steps  # noqa: F401
    from cmc_light.instrument import Instrument  # noqa: F401
    from cmc_light.sim import SimHardware, make_instrument  # noqa: F401
    from cmc_light.steps_text import parse as parse_steps, format_steps, format_csv  # noqa: F401
    from cmc_light.preview_edit import laser_windows, boundaries, drag_boundary, merge_windows  # noqa: F401
    from cmc_light.units import fmt_power  # noqa: F401
    from cmc_light.sense import Sensor, find_sensors, Reading, SenseError  # noqa: F401
    from cmc_light.sense_cal import Calibration  # noqa: F401
