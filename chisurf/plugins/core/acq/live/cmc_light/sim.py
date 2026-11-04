"""In-process simulated instrument: the real SCPI logic on fake hardware."""

import time

try:
    from .instrument import Instrument
except (ImportError, ValueError):
    from cmc_light.instrument import Instrument

DEFAULT_LASERS = [
    dict(name="blue", gpio=5, wavelength=0, color="#3a6bff"),
    dict(name="green", gpio=4, wavelength=0, color="#2fd05a"),
    dict(name="red", gpio=0, wavelength=0, color="#ff3b30"),
]


class SimHardware:
    """Records what the instrument asks for; counts cycles from the wall clock."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.levels = 0
        self.prog = None
        self.cycles = 0
        self.t0 = None
        self.log = []
        self.monitor_mode, self.monitor_gain = "HIGH", 69
        self.i2c_pins = "13,15"  # D7 (SDA), D8 (SCL)

    def static(self, set_mask, clr_mask):
        self.t0 = None
        self.levels = (self.levels & ~clr_mask) | set_mask
        self.log.append(("static", set_mask, clr_mask))

    def play(self, prog, cycles):
        self.prog = prog
        self.cycles = cycles
        self.t0 = self.clock()
        self.levels = (self.levels & ~prog["start_clr"]) | prog["start_set"]
        self.log.append(("play", prog, cycles))

    def stop(self):
        if self.prog:
            self.levels = (self.levels & ~self.prog["idle_clr"]) | self.prog["idle_set"]
        self.t0 = None
        self.log.append(("stop",))

    def _done(self):
        if self.t0 is None or not self.prog:
            return 0
        return int((self.clock() - self.t0) * 1e6 // self.prog["period"])

    # the instrument's power monitor; no I2C here, so the instrument fills in the value
    def monitor(self):
        return dict(present=True, simulated=True, lux=0.0, raw=0, age_ms=0,
                    mode=self.monitor_mode, gain=self.monitor_gain, pins=self.i2c_pins,
                    addresses="0x23")

    def monitor_set(self, mode, gain):
        self.monitor_mode, self.monitor_gain = mode, int(gain)
        return True

    def i2c_configure(self, sda, scl):
        self.i2c_pins = "%d,%d" % (sda, scl)
        return True

    def status(self):
        done = self._done()
        running = self.t0 is not None and not (self.cycles and done >= self.cycles)
        if self.cycles:
            done = min(done, self.cycles)
        return running, done, 0


def make_instrument(lasers=None, sync_gpio=14):
    return Instrument(SimHardware(), lasers or DEFAULT_LASERS, serial="SIM",
                      sync_gpio=sync_gpio, model="LIGHT-3-SIM")
