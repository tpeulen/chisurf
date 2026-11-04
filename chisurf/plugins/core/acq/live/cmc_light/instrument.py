"""SCPI instrument model of the 3-laser ALEX source.

Pure logic, shared by the firmware (MicroPython, ESP8266) and the host
simulator (CPython). It owns the settings and turns them into edge programs;
the hardware object only plays them:

    hw.static(set_mask, clr_mask)      drive levels, stop any playback
    hw.play(program, cycles)           start periodic playback
    hw.stop()                          stop playback, outputs idle
    hw.status() -> (running, cycles_done, late_max_us)

IEEE 488.2 / SCPI syntax; the SOURce/SYSTem layout follows the OBIS-style
laser convention. See docs/SCPI.md for the command reference.
Kept lean: the ESP8266 has ~35 kB of heap.
"""

try:
    from . import seqcore
except (ImportError, ValueError):
    try:
        import seqcore
    except ImportError:  # host package
        from cmc_light import seqcore

try:
    from gc import collect as _gc
except ImportError:
    def _gc():
        pass

VERSION = "2.0"
VENDOR = "CMC"

ERRORS = {
    -100: "Command error",
    -109: "Missing parameter",
    -113: "Undefined header",
    -221: "Settings conflict",
    -222: "Data out of range",
    -224: "Illegal parameter value",
    -241: "Hardware missing",
    -350: "Queue overflow",
}

# Header words, SCPI style: capitals = short form, whole word = long form.
WORDS = ("SYSTem ERRor NEXT VERSion CHANnels INFormation MODel WAVelength COLor "
         "SOURce AM STATe POWer LIMit LOW HIGH NOMinal DUTY LEVel IMMediate AMPLitude "
         "PWM PERiod MINimum SEQuence CLEar STEP APPend COUNt LIST ALEX CYCLes SYNC "
         "WIDTh STARt ABORt TIMing COMMunicate WLAN SSID PASSword APPLy ADDRess MODE "
         "SENSe RAW PRESent AGE GAIN I2C SCAN PINS EXCLusive").split()
# short and long spellings -> short form
LOOKUP = {}
for _w in WORDS:
    _s = "".join(c for c in _w if not c.islower())
    LOOKUP[_s] = _s
    LOOKUP[_w.upper()] = _s
del WORDS
NUMBERED = ("SYST", "SOUR", "SENS")  # take a channel suffix, e.g. SOURce2
OPTIONAL = {"POW": ("LEV", "IMM", "AMPL"), "ERR": ("NEXT",)}

# canonical header -> handler method name (without the leading underscore)
COMMANDS = {
    "*IDN": "idn", "*RST": "rst", "*CLS": "cls", "*OPC": "opc", "*TST": "tst",
    "SYST#:ERR": "err", "SYST#:VERS": "version", "SYST#:CHAN": "nchan",
    "SYST#:INF:MOD": "info_model", "SYST#:INF:WAV": "info_wavelength",
    "SYST#:INF:COL": "info_color",
    "SOUR#:AM:STAT": "am_state", "SOUR#:AM:SOUR": "am_source",
    "SOUR#:POW:LIM:LOW": "pow_low", "SOUR#:POW:LIM:HIGH": "pow_high",
    "SOUR#:POW:NOM": "pow_high", "SOUR#:POW:DUTY": "pow_duty",
    "SOUR#:POW": "power",
    "SOUR#:PWM:PER": "pwm_period", "SOUR#:PWM:MIN": "pwm_min", "SOUR#:PWM:MODE": "pwm_mode",
    "SEQ:CLE": "seq_clear", "SEQ:STEP:APP": "seq_append",
    "SEQ:STEP:COUN": "seq_nsteps", "SEQ:STEP:LIST": "seq_list",
    "SEQ:ALEX": "seq_alex", "SEQ:PER": "seq_period", "SEQ:CYCL": "seq_cycles",
    "SEQ:SYNC:WIDT": "seq_sync", "SEQ:STAR": "seq_start", "SEQ:ABOR": "abort",
    "ABOR": "abort", "SEQ:STAT": "seq_state", "SEQ:COUN": "seq_count",
    "SEQ:TIM": "seq_timing",
    "SYST#:COMM:WLAN:SSID": "wlan_ssid", "SYST#:COMM:WLAN:PASS": "wlan_pass",
    "SYST#:COMM:WLAN:APPL": "wlan_apply", "SYST#:COMM:WLAN:ADDR": "wlan_addr",
    "SYST#:COMM:WLAN:MODE": "wlan_mode",
    # the internal power monitor: a light sensor on the I2C bus
    "SENS#:POW": "mon_power", "SENS#:POW:RAW": "mon_raw", "SENS#:POW:PRES": "mon_present",
    "SENS#:POW:AGE": "mon_age", "SENS#:POW:MODE": "mon_mode", "SENS#:POW:GAIN": "mon_gain",
    "SYST#:I2C:SCAN": "i2c_scan", "SYST#:I2C:PINS": "i2c_pins",
    "SOUR#:EXCL": "exclusive",
}


class ScpiError(Exception):
    def __init__(self, code, detail=""):
        Exception.__init__(self, code, detail)
        self.code = code
        self.detail = detail


def parse_header(head):
    """'SOURce2:POWer:LEVel:IMMediate:AMPLitude' -> ('SOUR#:POW', [2])"""
    if head[:1] == "*":
        return head, []
    keys = []
    nums = []
    for tok in head.split(":"):
        k = len(tok)
        while k > 0 and tok[k - 1].isdigit():
            k -= 1
        short = LOOKUP.get(tok[:k])
        if short is None:
            raise ScpiError(-113, head)
        if keys and short in OPTIONAL.get(keys[-1].rstrip("#"), ()):
            continue
        if short in NUMBERED and not keys:  # only the root node takes a channel
            nums.append(int(tok[k:]) if k < len(tok) else 1)
            short += "#"
        elif k < len(tok):
            raise ScpiError(-113, head)
        keys.append(short)
    return ":".join(keys), nums


def _arg(args, i, kind, lo, hi):
    if len(args) <= i:
        raise ScpiError(-109)
    try:
        v = int(float(args[i])) if kind is int else float(args[i])
    except (ValueError, OverflowError):  # nan, inf for integers
        raise ScpiError(-224, args[i])
    if v < lo or v > hi:
        raise ScpiError(-222, args[i])
    return v


def _string(s, maxlen):
    """SCPI string parameter: "text" or 'text' (doubled quotes escape), or bare text."""
    if not s:
        raise ScpiError(-109)
    q = s[0]
    if q in "\"'":
        if len(s) < 2 or s[-1] != q:
            raise ScpiError(-224, s)
        s = s[1:-1].replace(q + q, q)
    if len(s.encode()) > maxlen:
        raise ScpiError(-222, "longer than %d bytes" % maxlen)
    return s


def _bool(args):
    v = args[0].upper() if args else ""
    if v in ("ON", "1"):
        return True
    if v in ("OFF", "0"):
        return False
    raise ScpiError(-224 if args else -109)


class Instrument:
    """channels: list of dicts with name, gpio, wavelength (nm), color (#rrggbb)."""

    def __init__(self, hw, channels, serial="0", active_high=True, sync_gpio=None,
                 model="LIGHT-3"):
        self.hw = hw
        self.channels = channels
        self.gpios = [c["gpio"] for c in channels]
        self.serial = serial
        self.model = model
        self.active_high = active_high
        self.sync_gpio = sync_gpio
        self.errors = []
        self.rest = ""
        # WiFi settings: persistent on the device, so *RST keeps them
        self.ssid = ""
        self.password = ""
        self._reset()

    # ------------------------------------------------------------ state
    def _reset(self):
        n = len(self.channels)
        self.enabled = [False] * n
        # One laser at a time: off in normal operation (the monitor diode then reads the
        # total power); switched on while a single laser's power is measured.
        self.exclusive = False
        self.powers = [1.0] * n
        self.source = "CW"  # CW: AM:STATe drives lasers; SEQ: the sequence does
        self.pwm_period = 1000
        self.min_pulse = 20
        self.power_mode = "PWM"  # PWM: inside every window; CYCL: cycle dithering (SEQ only)
        self.steps = seqcore.alex_steps(n, 1000)
        self.cycles = 0
        self.sync_us = 0
        self.running = False
        self.duty = [0.0] * n
        self.edges = 0
        self.period = 0  # sequence (base) period of the current program
        self.cycle_factor = 1  # base periods per program period (cycle dithering)
        self.play_factor = 1  # cycle_factor of the program last handed to the player
        self._apply()

    def _check_exclusive(self, steps):
        """Reject a sequence that would light more than one laser at the same time."""
        if not self.exclusive:
            return
        n = len(self.channels)
        for dur, mask in steps:
            lit = bin(mask & ((1 << n) - 1)).count("1")
            if lit > 1:
                raise ScpiError(-221, "only one laser at a time (SOURce:EXCLusive OFF allows more)")

    def _apply(self):
        """Push the current settings to the hardware."""
        n = len(self.channels)
        seq = self.source == "SEQ"
        steps = self.steps if seq else [(self.pwm_period, (1 << n) - 1)]
        self.hw.stop()
        if seq and not self.running and not steps:
            # idle sequence mode with no steps yet: valid, outputs off
            self._outputs_off()
            self.duty = [0.0] * n
            self.edges = 0
            self.period = 0
            self.cycle_factor = 1
            return
        _gc()
        prog = seqcore.compile_program(
            steps, self.gpios, self.enabled, self.powers, self.pwm_period,
            self.min_pulse, self.active_high, self.sync_gpio,
            self.sync_us if seq else 0,
            "cycles" if seq and self.power_mode == "CYCL" else "pwm")
        m = prog["cycle_factor"]
        self.duty = prog["duty"]
        self.edges = len(prog["times"])
        self.period = prog["period"] // m
        self.cycle_factor = m
        if seq and not self.running:
            self.hw.static(prog["idle_set"], prog["idle_clr"])
        elif self.edges:
            # SEQ:CYCLes counts sequence periods: play at least that many
            self.play_factor = m
            self.hw.play(prog, (self.cycles + m - 1) // m if seq else 0)
        else:
            self.hw.static(prog["start_set"], prog["start_clr"])
        prog = None
        _gc()

    def _outputs_off(self):
        lasers = 0
        for g in self.gpios:
            lasers |= 1 << g
        sync = (1 << self.sync_gpio) if self.sync_gpio is not None else 0
        if self.active_high:
            self.hw.static(0, lasers | sync)
        else:
            self.hw.static(lasers, sync)

    def _chan(self, nums):
        k = nums[0] if nums else 1
        if not 1 <= k <= len(self.channels):
            raise ScpiError(-222, "channel %d" % k)
        return k - 1

    # ------------------------------------------------------------ I/O
    def handle(self, line):
        """Process one line (commands may be joined with ';'). Returns the reply or None."""
        replies = []
        for cmd in line.strip().split(";"):
            cmd = cmd.strip()
            if not cmd:
                continue
            snap = self._snapshot()
            try:
                r = self._one(cmd)
            except ScpiError as e:
                self._push(e.code, e.detail)
                r = None
            except (ValueError, MemoryError) as e:
                # the new settings cannot be played: keep the previous, working ones
                self._restore(snap)
                self._push(-221, str(e))
                r = None
            if r is not None:
                replies.append(r)
        return ";".join(replies) if replies else None

    def _snapshot(self):
        return (list(self.enabled), list(self.powers), self.source, self.pwm_period,
                self.min_pulse, self.cycles, self.sync_us, self.running, self.power_mode)

    def _restore(self, snap):
        (enabled, powers, self.source, self.pwm_period, self.min_pulse, self.cycles,
         self.sync_us, self.running, self.power_mode) = snap
        self.enabled = list(enabled)
        self.powers = list(powers)
        try:
            self._apply()
        except (ValueError, MemoryError):
            self.running = False  # last resort: everything off
            self.hw.stop()
            self.enabled = [False] * len(self.channels)
            try:
                self._apply()
            except (ValueError, MemoryError):
                # e.g. a sync pulse alone breaks the dense-edge rule: nothing stays lit
                # (the firmware's apply() does the same on a failed compile)
                self._outputs_off()

    def _push(self, code, detail=""):
        if len(self.errors) >= 10:
            self.errors[-1] = (-350, "")
        else:
            self.errors.append((code, detail))

    def _one(self, cmd):
        parts = cmd.split(" ", 1)  # no str.partition on ESP8266 MicroPython
        head = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        self.rest = rest
        query = head[-1:] == "?"
        head = head.rstrip("?").lstrip(":").upper()
        args = [a.strip() for a in rest.split(",")] if rest else []
        key, nums = parse_header(head)
        name = COMMANDS.get(key)
        if name is None:
            raise ScpiError(-113, head)
        return getattr(self, "_" + name)(query, args, nums)

    # ------------------------------------------------------------ commands
    def _idn(self, q, a, n):
        return "%s,%s,%s,%s" % (VENDOR, self.model, self.serial, VERSION)

    def _rst(self, q, a, n):
        self._reset()

    def _cls(self, q, a, n):
        self.errors = []

    def _opc(self, q, a, n):
        return "1"

    def _tst(self, q, a, n):
        return "0"

    def _err(self, q, a, n):
        if not self.errors:
            return '0,"No error"'
        code, detail = self.errors.pop(0)
        msg = ERRORS.get(code, "Error")
        if detail:
            msg += "; " + detail
        return '%d,"%s"' % (code, msg)

    def _version(self, q, a, n):
        return "1999.0"

    def _nchan(self, q, a, n):
        return str(len(self.channels))

    def _info_model(self, q, a, n):
        return self.channels[self._chan(n)]["name"]

    def _info_wavelength(self, q, a, n):
        return str(self.channels[self._chan(n)].get("wavelength", 0))

    def _info_color(self, q, a, n):
        return self.channels[self._chan(n)].get("color", "#ffffff")

    def _am_state(self, q, a, n):
        k = self._chan(n)
        if q:
            return "ON" if self.enabled[k] else "OFF"
        on = _bool(a)
        if on and self.exclusive:  # one laser at a time: switching one on switches the others off
            self.enabled = [False] * len(self.channels)
        self.enabled[k] = on
        self._apply()

    def _exclusive(self, q, a, n):
        """One laser at a time: for measuring a single laser's power, where the others
        must be dark. Off in normal operation, where several lasers may run together."""
        if q:
            return "ON" if self.exclusive else "OFF"
        self.exclusive = _bool(a)
        if self.exclusive:
            self._check_exclusive(self.steps)
            if sum(1 for e in self.enabled if e) > 1:
                first = self.enabled.index(True)
                self.enabled = [i == first for i in range(len(self.channels))]
            self._apply()

    def _am_source(self, q, a, n):
        if q:
            return self.source
        v = a[0].upper() if a else ""
        if v in ("CW", "CWP"):
            self.source = "CW"
            self.running = False
        elif v in ("SEQ", "SEQUENCE"):
            self.source = "SEQ"
        else:
            raise ScpiError(-224 if a else -109)
        self._apply()

    def _pow_low(self, q, a, n):
        self._chan(n)
        return "0.0000"

    def _pow_high(self, q, a, n):
        self._chan(n)
        return "1.0000"

    def _pow_duty(self, q, a, n):
        return "%.4f" % self.duty[self._chan(n)]

    def _power(self, q, a, n):
        k = self._chan(n)
        if q:
            return "%.4f" % self.powers[k]
        self.powers[k] = _arg(a, 0, float, 0.0, 1.0)
        self._apply()

    def _pwm_period(self, q, a, n):
        if q:
            return str(self.pwm_period)
        self.pwm_period = _arg(a, 0, int, 20, 1000000)
        self._apply()

    def _pwm_min(self, q, a, n):
        if q:
            return str(self.min_pulse)
        self.min_pulse = _arg(a, 0, int, 1, 100000)
        self._apply()

    def _pwm_mode(self, q, a, n):
        if q:
            return self.power_mode
        v = a[0].upper() if a else ""
        if v == "PWM":
            self.power_mode = "PWM"
        elif v in ("CYCL", "CYCLES"):
            self.power_mode = "CYCL"
        else:
            raise ScpiError(-224 if a else -109)
        if self.source == "SEQ":  # CW always uses PWM
            self._apply()

    def _halt(self):
        if self.running:
            self.running = False
            self._apply()

    def _seq_clear(self, q, a, n):
        self._halt()
        self.steps = []

    def _seq_append(self, q, a, n):
        self._halt()
        # mask bit N (N = number of lasers) drives the sync output, if there is one
        bits = len(self.channels) + (self.sync_gpio is not None)
        step = (_arg(a, 0, int, 1, 60000000), _arg(a, 1, int, 0, (1 << bits) - 1))
        self._check_exclusive([step])
        if len(self.steps) >= seqcore.MAX_STEPS:
            raise ScpiError(-221, "too many steps (max %d)" % seqcore.MAX_STEPS)
        self.steps.append(step)

    def _seq_nsteps(self, q, a, n):
        return str(len(self.steps))

    def _seq_list(self, q, a, n):
        return ";".join("%d,%d" % s for s in self.steps)

    def _seq_alex(self, q, a, n):
        self._halt()
        on = _arg(a, 0, int, 1, 60000000)
        gap = _arg(a, 1, int, 0, 60000000) if len(a) > 1 else 0
        self.steps = seqcore.alex_steps(len(self.channels), on, gap)

    def _seq_period(self, q, a, n):
        return str(seqcore.period_us(self.steps))

    def _seq_cycles(self, q, a, n):
        if q:
            return str(self.cycles)
        self.cycles = _arg(a, 0, int, 0, 1 << 30)

    def _seq_sync(self, q, a, n):
        if q:
            return str(self.sync_us)
        if self.sync_gpio is None:
            raise ScpiError(-221, "no sync output")
        self.sync_us = _arg(a, 0, int, 0, 60000000)
        if self.running:
            self._apply()

    def _seq_start(self, q, a, n):
        if not self.steps:
            raise ScpiError(-221, "sequence is empty")
        self.source = "SEQ"
        self.running = True
        self._apply()

    def _abort(self, q, a, n):
        self.running = False
        if self.source == "SEQ":
            self._apply()

    def _seq_state(self, q, a, n):
        if self.running and not self.hw.status()[0]:
            self.running = False  # finished its cycles
            self._apply()
        if q:
            return "RUN" if self.running else "IDLE"
        if _bool(a):
            self._seq_start(False, [], n)
        else:
            self._abort(False, [], n)

    def _seq_count(self, q, a, n):
        return str(self.hw.status()[1] * self.play_factor)

    def _seq_timing(self, q, a, n):
        return "%d,%d,%d" % (self.hw.status()[2], self.edges, self.period)

    # WLAN (simulated here; the C++ firmware stores them in flash and joins the network)
    def _wlan_ssid(self, q, a, n):
        if q:
            return '"%s"' % self.ssid.replace('"', '""')
        self.ssid = _string(self.rest, 32)

    def _wlan_pass(self, q, a, n):
        if q:
            return '"***"' if self.password else '""'
        p = _string(self.rest, 63)
        if 0 < len(p) < 8:
            raise ScpiError(-222, "password needs 8 to 63 characters")
        self.password = p

    def _wlan_apply(self, q, a, n):
        pass

    def _wlan_addr(self, q, a, n):
        return "0.0.0.0"

    def _wlan_mode(self, q, a, n):
        return "AP"

    # -- power monitor (light sensor on I2C) ------------------------------- #
    def _monitor(self):
        state = self.hw.monitor() if hasattr(self.hw, "monitor") else None
        if not state or not state.get("present"):
            raise ScpiError(-241, "no light sensor on the I2C bus")
        if state.get("simulated"):  # no real sensor: read back what the lasers are set to
            state = dict(state, lux=1000.0 * sum(self.duty), age_ms=0)
            state["raw"] = int(state["lux"] * 1.2 + 0.5)
        return state

    def _absent_or(self, read, fallback, raw=False):
        """A monitor reading, or *fallback* with the error queued: a query always answers."""
        try:
            value = read(self._monitor())
        except ScpiError as e:
            self._push(e.code, e.detail)
            return fallback
        return value if raw else value

    def _mon_power(self, q, a, n):
        return self._absent_or(lambda st: "%.3f" % st["lux"], "nan", raw=True)

    def _mon_raw(self, q, a, n):
        return self._absent_or(lambda st: str(int(st["raw"])), "nan", raw=True)

    def _mon_present(self, q, a, n):
        state = self.hw.monitor() if hasattr(self.hw, "monitor") else None
        return "1" if state and state.get("present") else "0"

    def _mon_age(self, q, a, n):
        return self._absent_or(lambda st: str(int(st["age_ms"])), "nan", raw=True)

    def _mon_mode(self, q, a, n):
        if q:
            return self._absent_or(lambda st: st["mode"], "HIGH", raw=True)
        state = self._monitor()
        mode = (a[0] if a else "").upper()
        if mode not in ("HIGH", "HIGH2", "LOW"):
            raise ScpiError(-109 if not a else -224, a[0] if a else "")
        if not self.hw.monitor_set(mode, state["gain"]):
            raise ScpiError(-241, "no light sensor on the I2C bus")

    def _mon_gain(self, q, a, n):
        if q:
            return self._absent_or(lambda st: str(int(st["gain"])), "nan", raw=True)
        state = self._monitor()
        gain = _arg(a, 0, int, 31, 254)
        if not self.hw.monitor_set(state["mode"], gain):
            raise ScpiError(-241, "no light sensor on the I2C bus")

    def _i2c_scan(self, q, a, n):
        state = self.hw.monitor() if hasattr(self.hw, "monitor") else None
        return (state or {}).get("addresses", "")

    def _i2c_pins(self, q, a, n):
        state = self.hw.monitor() if hasattr(self.hw, "monitor") else None
        if q:
            return (state or {}).get("pins", "")
        sda = _arg(a, 0, int, 0, 16)
        scl = _arg(a, 1, int, 0, 16)
        if not self.hw.i2c_configure(sda, scl):
            raise ScpiError(-241, "no sensor answered on those pins")
