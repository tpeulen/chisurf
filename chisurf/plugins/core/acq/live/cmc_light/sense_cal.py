"""Calibration of the cmc-sense camera into an absolute light detector, using the laser.

The laser is the light source; the camera's integration time is the reference: with
steady light the collected light is proportional to the exposure. (Pulsed light is not
a linear reference: the laser drivers need 90..180 us before they emit, and exposures
shorter than the pulse period alias with the rolling shutter.) Three measurements:

1. **Response** (per colour channel): the brightest pixel's raw code against the
   exposure time (with steady laser light) gives the pixel response curve. Its inverse is uploaded to the
   firmware as a response table (``CAL:LUT``), so every pixel value -- and with it every
   sum, profile and centroid -- is proportional to the light.
2. **Gain**: at a fixed light level, the linearised spot signal against the gain setting
   gives the effective gain factors (the exposure is the reference, so it stays nominal).
3. **Absolute**: one reference reading (a power meter at the sensor position) gives
   watts per unit of calibrated signal, per laser (the sensor's colour response differs
   between wavelengths).

The calibrated signal of a reading is ``spot_sum / (exposure_eff(lines) * gain_eff(g))``,
comparable over the whole exposure x gain range; times the laser's absolute factor it is
a power in watts.
"""

from __future__ import annotations

import bisect
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field

LUT_MAX = 1023
LUT_SIZE = {"R": 32, "G": 64, "B": 32}
PIXEL_UM_UXGA = 2.2  # OV2640 pixel pitch; frames are downscaled from 1600 px wide


def default_lut(channel):
    n = LUT_SIZE[channel]
    return [int((i * 255 + (n - 1) // 2) // (n - 1)) for i in range(n)]


@dataclass
class Calibration:
    sensor: str = ""
    response: dict = field(default_factory=dict)       # channel -> LUT (raw code -> linear)
    response_report: dict = field(default_factory=dict)
    exposure_table: list = field(default_factory=list)  # [(lines, effective)], effective == lines if ideal
    gain_table: dict = field(default_factory=dict)      # "g" -> effective factor (1.0 at g = 0)
    absolute: dict = field(default_factory=dict)        # laser name -> {"w_per_unit": .., "channel": .., "when": ..}
    crosstalk: dict = field(default_factory=dict)      # laser name -> {channel: share of its signal}
    background: dict = field(default_factory=dict)     # channel -> signal with every laser off
    created: str = ""

    # -- use ---------------------------------------------------------------- #
    def exposure_eff(self, lines):
        t = sorted(self.exposure_table)
        if len(t) < 2:
            return float(lines)
        xs = [math.log(max(1e-9, a)) for a, _ in t]
        ys = [math.log(max(1e-12, b)) for _, b in t]
        x = math.log(max(1.0, float(lines)))
        i = min(max(1, bisect.bisect_left(xs, x)), len(xs) - 1)
        x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
        return math.exp(y0 + (y1 - y0) * (x - x0) / (x1 - x0 if x1 != x0 else 1.0))

    def gain_eff(self, gain, nominal):
        v = self.gain_table.get(str(int(gain)))
        return float(v) if v else float(nominal)

    def signal(self, reading, channel="S", spot=True):
        value = reading.ch[channel]["spot_sum" if spot else "sum"]
        return value / max(1e-12, self.exposure_eff(reading.exposure) * self.gain_eff(reading.gain, reading.gain_x))

    # -- background and crosstalk ------------------------------------------- #
    def background_signal(self, channel):
        """Signal seen with every laser off (stray light, dark current), per unit exposure x gain."""
        return float(self.background.get(channel, 0.0))

    def corrected(self, reading, spot=True, nonneg=True):
        """Per-laser signals, background subtracted and crosstalk removed.

        Each colour channel sees a mixture of the lasers:
        ``s_c = bg_c + sum_k x_k * A[k][c]`` with the crosstalk matrix ``A`` (rows: the
        lasers = sources, columns: the channels = detectors; each row measured with only
        that laser on and normalised to sum 1 - the convention of imp.bff's
        PhotophysicsCrosstalkMatrix). The mixture is solved for the lasers by least
        squares, non-negative by default. ``{}`` while no matrix is set.
        """
        lasers = [k for k in self.crosstalk if any(self.crosstalk[k].get(c) for c in "RGB")]
        if not lasers:
            return {}
        s = [self.signal(reading, c, spot) - self.background_signal(c) for c in "RGB"]
        A = [[float(self.crosstalk[k].get(c, 0.0)) for k in lasers] for c in "RGB"]
        x = _solve_least_squares(A, s, nonneg=nonneg)
        return {k: x[i] for i, k in enumerate(lasers)}

    def power_w(self, reading, laser):
        a = self.absolute.get(laser)
        if not a:
            return None
        return self.signal(reading, a.get("channel", "S")) * a["w_per_unit"]

    @staticmethod
    def pixel_um(width):
        return PIXEL_UM_UXGA * 1600.0 / max(1, width)

    # -- files -------------------------------------------------------------- #
    def save(self, path):
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=1)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            d = json.load(f)
        c = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        c.exposure_table = [tuple(x) for x in c.exposure_table]
        return c


def calibration_path(folder, identity):
    serial = identity.split(",")[2] if identity.count(",") >= 2 else "sensor"
    return os.path.join(folder, "sensor-calibration-%s.json" % serial)


# --------------------------------------------------------------------------- #
# fitting (pure functions, unit-tested)

def response_lut(points, channel, lut_max=LUT_MAX):
    """Response table from (relative light, raw 8-bit code of the brightest pixel) pairs.

    The table maps every raw code to linear light, scaled so the highest measured
    unsaturated code maps to ``lut_max * code / 255`` (keeps the numbers on the scale
    of the default table). Codes outside the measured range are extrapolated linearly
    from the nearest segment. Needs at least 4 distinct codes.
    """
    pts = sorted((c, l) for l, c in points if 0 < c < 250 and l > 0)
    merged = []
    for c, l in pts:  # monotone: one light level per code (median), light rising with code
        if merged and merged[-1][0] == c:
            merged[-1][1].append(l)
        else:
            merged.append((c, [l]))
    curve = []
    for c, ls in merged:
        ls.sort()
        l = ls[len(ls) // 2]
        if not curve or l > curve[-1][1]:
            curve.append((c, l))
    if len(curve) < 4:
        raise ValueError("response: only %d distinct codes measured (need 4): widen the light range"
                         % len(curve))
    curve = [(0.0, 0.0)] + curve  # dark is zero light (codes are background-free at the peak)

    def light_at(code8):
        j = min(max(1, bisect.bisect_left([c for c, _ in curve], code8)), len(curve) - 1)
        (c0, l0), (c1, l1) = curve[j - 1], curve[j]
        return l0 + (l1 - l0) * (code8 - c0) / (c1 - c0 if c1 != c0 else 1.0)

    # full scale: the light at code 255, extrapolated from the last measured segment
    scale = lut_max / max(1e-12, light_at(255.0))
    n = LUT_SIZE[channel]
    lut = [int(max(0, min(lut_max, round(light_at(i * 255.0 / (n - 1)) * scale)))) for i in range(n)]
    for i in range(1, n):  # strictly usable: never decreasing
        lut[i] = max(lut[i], lut[i - 1])
    return lut


def _solve_least_squares(a, b, nonneg=False):
    """Least-squares solution of a x = b for a small matrix (normal equations, no numpy).

    ``nonneg``: negative components (physically impossible light) are dropped and the
    rest re-solved, the small-problem version of a non-negative least squares.
    """
    if nonneg:
        keep = list(range(len(a[0]) if a else 0))
        for _ in range(len(keep)):
            sub = [[row[i] for i in keep] for row in a]
            x = _solve_least_squares(sub, b)
            if all(v >= 0 for v in x):
                out = [0.0] * (len(a[0]) if a else 0)
                for i, col in enumerate(keep):
                    out[col] = x[i]
                return out
            keep = [col for col, v in zip(keep, x) if v > 0]
            if not keep:
                return [0.0] * (len(a[0]) if a else 0)
        return [0.0] * (len(a[0]) if a else 0)
    rows, cols = len(a), len(a[0]) if a else 0
    ata = [[sum(a[r][i] * a[r][j] for r in range(rows)) for j in range(cols)] for i in range(cols)]
    atb = [sum(a[r][i] * b[r] for r in range(rows)) for i in range(cols)]
    for i in range(cols):  # Gauss-Jordan with partial pivoting
        p = max(range(i, cols), key=lambda r: abs(ata[r][i]))
        if abs(ata[p][i]) < 1e-12:
            return [0.0] * cols
        ata[i], ata[p] = ata[p], ata[i]
        atb[i], atb[p] = atb[p], atb[i]
        d = ata[i][i]
        ata[i] = [v / d for v in ata[i]]
        atb[i] /= d
        for r in range(cols):
            if r == i:
                continue
            f = ata[r][i]
            if f:
                ata[r] = [v - f * w for v, w in zip(ata[r], ata[i])]
                atb[r] -= f * atb[i]
    return atb


def crosstalk_matrix(per_laser_signals):
    """Crosstalk matrix from readings with one laser on at a time.

    ``per_laser_signals``: ``{laser name: {channel: signal}}`` (background already
    subtracted). Each laser's column is normalised to its total over R, G, B, so the
    unmixed values are in units of that laser's total signal.
    """
    matrix = {}
    for name, sig in per_laser_signals.items():
        total = sum(max(0.0, sig.get(c, 0.0)) for c in "RGB")
        if total <= 0:
            continue
        matrix[name] = {c: max(0.0, sig.get(c, 0.0)) / total for c in "RGB"}
    return matrix


def linear_fit(xs, ys):
    """Least squares through the origin: slope and worst relative deviation."""
    sxx = sum(x * x for x in xs)
    if sxx <= 0:
        return 0.0, float("inf")
    k = sum(x * y for x, y in zip(xs, ys)) / sxx
    worst = max(abs(y - k * x) / max(1e-12, abs(k * x)) for x, y in zip(xs, ys))
    return k, worst


# --------------------------------------------------------------------------- #
# procedures (run on the sensor worker thread; the laser is driven directly)
#
# The reference for the pixel response is the exposure time: with steady light the
# collected light is proportional to the integration time, which the sensor sets in
# whole lines. The laser is kept continuous (one laser, its power setting) so no
# pulse timing enters; the laser drivers need 90..180 us before they emit at all, so
# short pulses are not a linear light source.

class OneLaser:
    """Only laser *k* on, continuous, at *power*; the previous laser state restored after."""

    def __init__(self, laser, k, power=None):
        self.laser, self.k, self.power = laser, k, power
        self._saved = None

    def __enter__(self):
        src = self.laser
        n = src.n_channels
        self._saved = dict(on=[src.emission(i + 1) for i in range(n)], power=[src.power(i + 1) for i in range(n)],
                           source=src.source())
        src.abort()
        src.set_source("CW")
        if self.power is not None:
            src.set_power(self.k + 1, self.power)
        src.set_emissions({i + 1: i == self.k for i in range(n)})
        time.sleep(0.2)
        return self

    def __exit__(self, *exc):
        src, s = self.laser, self._saved
        try:
            src.abort()
            for i, p in enumerate(s["power"]):
                src.set_power(i + 1, p)
            src.set_emissions({i + 1: on for i, on in enumerate(s["on"])})
            src.set_source(s["source"])
        except Exception:
            src.all_off()
            raise
        return False


def _readings(sensor, n=3, skip=2):
    for _ in range(skip):
        sensor.measure()
    return [sensor.measure() for _ in range(n)]


def _median(values):
    v = sorted(values)
    return v[len(v) // 2] if v else 0.0


EXPOSURE_STEPS = (2, 3, 5, 8, 12, 18, 27, 40, 60, 90, 135, 200, 300, 450)


LADDER_POWERS = (1.0, 0.5, 0.25, 0.125)  # PWM duty; below ~0.1 the drivers do not fire at all
LADDER_EXPOSURES = (90, 135, 200, 300, 450)  # lines; >= 18 ms, several PWM periods
PWM_PERIOD_US = 2000  # so that even the lowest power's pulses clear the drivers' turn-on time


def largest_unsaturated_exposure(sensor, exposures=LADDER_EXPOSURES):
    for e in reversed(exposures):
        sensor.set_exposure(e)
        if max(r.saturated for r in _readings(sensor, 2)) == 0:
            return e
    return None


def usable_powers(sensor, laser, k, progress=print):
    """The laser powers whose dimmest level still fits the exposure range.

    The light must be weak enough that the longest exposures of the ladder are not
    saturated (below that the drivers' turn-on time makes PWM dimming useless, and
    exposures shorter than the PWM period alias with the rolling shutter).
    """
    for p in sorted(LADDER_POWERS):
        laser.set_power(k + 1, p)
        time.sleep(0.15)
        e = largest_unsaturated_exposure(sensor)
        progress("power %.3f: longest unsaturated exposure %s lines" % (p, e or "< %d" % LADDER_EXPOSURES[0]))
        if e is not None and e >= LADDER_EXPOSURES[1]:
            return [q for q in sorted(LADDER_POWERS) if q >= p]
    raise ValueError(
        "the spot is too bright to calibrate: even at %.0f %% laser power it saturates at %d exposure "
        "lines (%.0f ms). Attenuate it by about %dx more (another diffuser layer, an ND filter, or more "
        "distance) so that the spot peaks around 200 counts at ~300 lines."
        % (100 * min(LADDER_POWERS), LADDER_EXPOSURES[0], 0.2 * LADDER_EXPOSURES[0], 30))


def response_ladder(levels):
    """Stitch light levels into one response curve: [(code, relative light), ...].

    ``levels`` is a list (dimmest first) of lists of ``(relative light within the level,
    code)``; the levels overlap in code, and the overlap fixes each level's scale.
    """
    curve = []  # (code, light), increasing in both

    def add(points):
        for code, light in sorted(points):
            if not curve or (code > curve[-1][0] and light > curve[-1][1]):
                curve.append((code, light))

    def light_of(code):
        if len(curve) < 2 or code < curve[0][0] or code > curve[-1][0]:
            return None
        j = min(max(1, bisect.bisect_left([c for c, _ in curve], code)), len(curve) - 1)
        (c0, l0), (c1, l1) = curve[j - 1], curve[j]
        return l0 + (l1 - l0) * (code - c0) / (c1 - c0 if c1 != c0 else 1.0)

    scale = 1.0
    for i, level in enumerate(levels):
        pts = [(c, l) for l, c in level if c > 0]
        if not pts:
            continue
        if curve:
            factors = [known / (l * 1.0) for c, l in pts for known in [light_of(c)] if known and l > 0]
            if not factors:
                raise ValueError("response: light levels do not overlap in code; use smaller power steps")
            scale = _median(factors)
        add([(c, l * scale) for c, l in pts])
    if len(curve) < 4:
        raise ValueError("response: only %d points on the curve (need 4)" % len(curve))
    return curve


def measure_response(sensor, laser, k, progress=print, keep=None):
    """Response tables of the colour channels from a light ladder with laser *k*.

    The camera's integration time is the reference within one laser power; several
    powers (PWM duty, period long enough for the drivers) extend the range, stitched
    where they overlap in code. The effective exposure (the OV2640 stops integrating
    longer above ~300 lines) is measured first, at the dimmest level.
    """
    sensor.write("CAL:LUT:RES")
    sensor.set_auto_range(False)
    sensor.set_gain(0)
    report = {"laser": k, "method": "light ladder: laser power x exposure"}
    luts = dict(keep or {})
    levels = {c: [] for c in "RGB"}
    rows = []
    with OneLaser(laser, k):
        laser.set_pwm_period(PWM_PERIOD_US)
        laser.set_power_mode("PWM")
        powers = usable_powers(sensor, laser, k, progress=progress)
        report["powers"] = powers
        for p in powers:  # dimmest first
            laser.set_power(k + 1, p)
            time.sleep(0.15)
            level = {c: [] for c in "RGB"}
            for e in LADDER_EXPOSURES:
                sensor.set_exposure(e)
                rs = _readings(sensor)
                sat = max(r.saturated for r in rs)
                codes = {c: _median([r.ch[c]["peak"] + r.ch[c]["bg"] for r in rs]) for c in "RGB"}
                spots = {c: _median([r.ch[c]["spot_sum"] for r in rs]) for c in "RGB"}
                rows.append(dict(power=p, exposure=e, saturated=sat, codes=codes, spots=spots))
                progress("power %.3f, exposure %3d lines: codes R%.0f G%.0f B%.0f%s"
                         % (p, e, codes["R"], codes["G"], codes["B"], ", saturated" if sat else ""))
                if sat:
                    break
                for c in "RGB":
                    level[c].append((float(e), codes[c]))
            for c in "RGB":
                levels[c].append(level[c])
        # effective exposure: the dimmest level, where the response is still near linear
        dim = [r for r in rows if r["power"] == min(LADDER_POWERS) and not r["saturated"]]
        best_c = max("RGB", key=lambda c: max([r["codes"][c] for r in dim] or [0]))
        table = [(float(r["exposure"]), r["spots"][best_c]) for r in dim if r["spots"][best_c] > 0]
        if len(table) >= 3:
            ref_e, ref_v = min(table, key=lambda ev: abs(ev[0] - 200))
            report["exposure_table"] = [(e, ref_e * v / ref_v) for e, v in table]
        errors, measured = {}, []
        for c in "RGB":
            top = max([code for lvl in levels[c] for _e, code in lvl] or [0])
            if top < 100:
                errors[c] = "only reaches code %.0f: calibrate this channel with its own laser" % top
                continue
            try:
                curve = response_ladder(levels[c])
                luts[c] = response_lut([(l, code) for code, l in curve], c)
                measured.append(c)
                report.setdefault("curves", {})[c] = curve
            except ValueError as e:
                errors[c] = str(e)
        if not measured:
            raise ValueError("no usable response curve: %s" % "; ".join("%s: %s" % kv for kv in errors.items()))
        for c, lut in luts.items():
            sensor.write("CAL:LUT %s,%s" % (c, ",".join(str(v) for v in lut)))
        # check: with the tables, the signal follows light (exposure) at a fixed power
        ch = measured[0]
        laser.set_power(k + 1, max(LADDER_POWERS) if max(levels[ch][-1], default=None) else 1.0)
        check = []
        for e in LADDER_EXPOSURES:
            sensor.set_exposure(e)
            rs = _readings(sensor)
            if max(r.saturated for r in rs) == 0:
                check.append((float(e), _median([r.ch[ch]["spot_sum"] for r in rs])))
    if len(check) >= 3:
        eff = dict(report.get("exposure_table", []))
        xs = [eff.get(e, e) for e, _ in check]
        report["linearity_worst"] = linear_fit(xs, [v for _, v in check])[1]
        report["linearity_channel"] = ch
    report.update(levels=levels, rows=rows, luts=luts, measured=measured, errors=errors, check=check)
    return report


def measure_gain(sensor, laser, k, progress=print):
    """Effective gain factors (1.0 at setting 0) with laser *k* continuous, response tables applied."""
    sensor.set_auto_range(False)
    sensor.set_gain(0)
    gains = {}
    with OneLaser(laser, k):
        # an exposure that leaves a clear but dim spot at gain 0
        chosen = None
        for e in EXPOSURE_STEPS:
            sensor.set_exposure(e)
            rs = _readings(sensor, 2)
            top = max(r.ch[c]["peak"] + r.ch[c]["bg"] for r in rs for c in "RGB")
            if max(r.saturated for r in rs) == 0 and top > 12:
                chosen = e
                break
        if chosen is None:
            raise ValueError("no exposure gives an unsaturated spot: attenuate the beam")
        base = None
        for g in range(0, 31):
            sensor.set_gain(g)
            rs = _readings(sensor)
            if max(r.saturated for r in rs) > 0:
                break
            v = _median([r.ch["S"]["spot_sum"] for r in rs])
            base = base if base is not None else v
            if base > 0:
                gains[str(g)] = v / base
            progress("gain %d: x%.2f" % (g, gains.get(str(g), 0.0)))
    return gains


def measure_pulse_response(sensor, laser, k, period_us=4000, exposure=100, progress=print):
    """Light against programmed TTL pulse length (laser *k*, sequence mode): the driver's
    turn-on threshold and slope. Exposure covers several periods."""
    sensor.set_auto_range(False)
    sensor.set_gain(0)
    sensor.set_exposure(exposure)
    rows = []
    src = laser
    n = src.n_channels
    saved = [src.emission(i + 1) for i in range(n)], [src.power(i + 1) for i in range(n)], src.source()
    try:
        src.abort()
        src.set_power_mode("PWM")
        src.set_power(k + 1, 1.0)
        src.set_emissions({i + 1: i == k for i in range(n)})
        for on in (50, 100, 150, 200, 300, 500, 800, 1200, 2000):
            if on >= period_us:
                break
            src.load_steps([(on, 1 << k), (period_us - on, 0)])
            src.set_cycles(0)
            src.set_sync_width(0)
            src.start()
            time.sleep(0.15)
            rs = _readings(sensor)
            rows.append((on, _median([r.ch["S"]["spot_sum"] for r in rs]), max(r.saturated for r in rs)))
            progress("pulse %d us: spot %.0f, saturated px %d" % rows[-1])
    finally:
        src.abort()
        for i, p in enumerate(saved[1]):
            src.set_power(i + 1, p)
        src.set_emissions({i + 1: on for i, on in enumerate(saved[0])})
        src.set_source(saved[2])
    good = [(on, v) for on, v, sat in rows if sat == 0 and v > 0]
    threshold = None
    if len(good) >= 3:  # light = slope * (on - threshold), fitted on the lit, unsaturated points
        lit = [(on, v) for on, v in good if v > 0.05 * max(v for _, v in good)]
        if len(lit) >= 2:
            xs, ys = [a for a, _ in lit], [b for _, b in lit]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxx = sum((x - mx) ** 2 for x in xs)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
            threshold = mx - my / slope if slope > 0 else None
    return dict(rows=rows, threshold_us=threshold)


def set_absolute(cal, reading, laser_name, power_w, channel="S"):
    """Watts per unit of calibrated signal for *laser_name* from a reference power."""
    sig = cal.signal(reading, channel)
    if sig <= 0:
        raise ValueError("no signal to calibrate against")
    cal.absolute[laser_name] = dict(w_per_unit=power_w / sig, channel=channel, reference_w=power_w,
                                    when=time.strftime("%Y-%m-%d %H:%M"))
    return cal.absolute[laser_name]


def d4sigma_um(reading, channel="S"):
    """ISO 11146 second-moment beam diameters (4 sigma) along the principal axes, in um."""
    st = reading.ch[channel]
    px = Calibration.pixel_um(reading.width)
    return 4.0 * st["sx"] * px, 4.0 * st["sy"] * px
