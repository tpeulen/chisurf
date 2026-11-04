"""Excitation sequence compiler, shared by the firmware and the host.

Runs unchanged on MicroPython (ESP8266) and CPython, so the host can draw
exactly the timing the instrument will play.

Model
-----
A *sequence* is a list of steps ``(duration_us, channel_mask)``; bit ``k`` of
the mask means channel ``k`` may emit during that step. The steps are played
back to back and the whole list repeats (one repeat = one *period*). Bit
``n_channels`` drives the sync output high for the whole step; it is ORed with
the sync pulse at the start of every period (see sync_intervals).

Relative power ``p`` (0..1) is realised by pulse-width modulation of the TTL
line: every on-window is divided into sub-periods of about ``pwm_period_us``
and the laser is on for the first ``p`` of each. ``p == 1`` is a solid window.

With ``power_mode="cycles"`` (cycle dithering) windows are never cut: a channel
with ``0 < p < 1`` is fully lit in ``round(M * p)`` of ``M`` sequence periods,
spread evenly (Bresenham), and dark in the others. The program then spans ``M``
base periods, ``M`` being the largest of CYCLE_FACTORS that fits the player.
"""

MAX_EDGES = 1024  # edges per period (the C++ firmware allocates this many)
MAX_STEPS = 512  # steps per sequence
# Timer-interrupt limit of the ESP8266 player, measured on the board: edges less
# than DENSE_GAP_US apart are busy-waited inside one interrupt. A stretch of such
# edges longer than DENSE_RUN_MAX_US starves WiFi/watchdog, so the player would
# pause ~1 ms every few ms. Such programs are rejected instead of stuttering.
DENSE_GAP_US = 12
DENSE_RUN_MAX_US = 3000
DENSE_FOREVER = 1 << 30
POWER_MODES = ("pwm", "cycles")
CYCLE_FACTORS = (100, 50, 20, 10)  # base periods per program in "cycles" mode, preferred first


def alex_steps(n_channels, on_us, gap_us=0, order=None):
    """Alternating excitation: each channel in turn, optional dark gap after each."""
    if order is None:
        order = range(n_channels)
    steps = []
    for ch in order:
        steps.append((int(on_us), 1 << ch))
        if gap_us:
            steps.append((int(gap_us), 0))
    return steps


def period_us(steps):
    return sum(d for d, _ in steps)


def _merge(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def _pwm_width(p, sub, min_pulse_us):
    """On-time for one PWM sub-period, respecting the shortest edge spacing."""
    w = int(p * sub + 0.5)
    if w <= 0:
        return 0
    if w < min_pulse_us:
        return min_pulse_us if 2 * p * sub >= min_pulse_us else 0
    off = sub - w
    if off < min_pulse_us:
        return sub if 2 * off < min_pulse_us else sub - min_pulse_us
    return w


def _clamp(p):
    return min(1.0, max(0.0, float(p)))


def dithered(enabled, powers, power_mode):
    """True for every channel whose power is realised by cycle dithering."""
    return [power_mode == "cycles" and bool(enabled[ch]) and 0.0 < _clamp(powers[ch]) < 1.0
            for ch in range(len(enabled))]


def cycle_lit(c, count, cycles):
    """Cycle ``c`` (0-based) of ``cycles`` is one of the ``count`` lit ones (Bresenham)."""
    return (c + 1) * count // cycles > c * count // cycles


def channel_intervals(steps, enabled, powers, pwm_period_us=1000, min_pulse_us=20,
                      cycles=1, power_mode="pwm"):
    """On-intervals of every channel within one program period.

    The program spans ``cycles`` sequence periods (1 unless cycle dithering is
    used, see compile_program). Returns ``(period, intervals, duty)`` where
    ``period`` is ``cycles`` times the sequence period, ``intervals[k]`` is a
    sorted list of ``(start_us, end_us)`` and ``duty[k]`` is the achieved
    fraction of on-time inside the windows the sequence grants channel ``k``
    (the *effective* relative power after quantisation).
    """
    base = period_us(steps)
    if base <= 0:
        raise ValueError("sequence is empty")
    cycles = max(1, int(cycles))
    period = base * cycles
    pwm_period_us = max(1, int(pwm_period_us))
    dith = dithered(enabled, powers, power_mode)
    intervals = []
    duty = []
    for ch in range(len(enabled)):
        iv = []
        granted = 0
        lit = 0
        t = 0
        p = _clamp(powers[ch])
        count = int(round(cycles * p)) if dith[ch] else 0
        for c in range(cycles):
            pc = (1.0 if cycle_lit(c, count, cycles) else 0.0) if dith[ch] else p
            for dur, mask in steps:
                if (mask >> ch) & 1:
                    granted += dur
                    if enabled[ch] and pc > 0:
                        if pc >= 1.0:
                            iv.append((t, t + dur))
                            lit += dur
                        else:
                            nsub = max(1, (dur + pwm_period_us // 2) // pwm_period_us)
                            for k in range(nsub):
                                s = t + k * dur // nsub
                                e = t + (k + 1) * dur // nsub
                                w = _pwm_width(pc, e - s, min_pulse_us)
                                if w > 0:
                                    iv.append((s, s + w))
                                    lit += w
                t += dur
        intervals.append(_merge(iv))
        duty.append(lit / granted if granted and enabled[ch] else 0.0)
    return period, intervals, duty


def sync_intervals(steps, n_channels, sync_us=0):
    """High intervals of the sync output within ONE sequence period.

    The union of the ``sync_us`` pulse at the start of the period (clipped to
    period - 1) and every step whose mask has bit ``n_channels`` set, merged
    (touching intervals join, empty ones are dropped). Sorted ``(start, end)``.
    """
    base = period_us(steps)
    iv = []
    w = min(int(sync_us), base - 1)
    if w > 0:
        iv.append((0, w))
    t = 0
    for dur, mask in steps:
        if (mask >> n_channels) & 1 and dur > 0:
            iv.append((t, t + dur))
        t += dur
    return _merge(iv)


def dense_run_us(times, period, gap=DENSE_GAP_US):
    """Longest stretch (us) of consecutive edges at most *gap* apart, over the
    periodic program. Returns DENSE_FOREVER if there is no larger gap at all
    (the dense pattern repeats without end)."""
    n = len(times)
    if n == 0:
        return 0
    gaps = [times[i + 1] - times[i] for i in range(n - 1)] + [times[0] + period - times[-1]]
    if all(g <= gap for g in gaps):
        return DENSE_FOREVER
    start = max(range(n), key=lambda i: gaps[i])  # begin right after a big gap
    longest = run = 0
    for k in range(1, n + 1):
        g = gaps[(start + k) % n]
        if g <= gap:
            run += g
            if run > longest:
                longest = run
        else:
            run = 0
    return longest


def compile_program(steps, gpios, enabled, powers, pwm_period_us=1000,
                    min_pulse_us=20, active_high=True, sync_gpio=None, sync_us=0,
                    power_mode="pwm"):
    """Compile a sequence to a periodic edge program for the GPIO player.

    Returns a dict with ``period`` (us), ``times`` (sorted edge times within
    the period), ``sets``/``clrs`` (GPIO bit masks written at each edge),
    ``start_set``/``start_clr`` (levels at t=0), ``idle_set``/``idle_clr``
    (all outputs off), ``duty`` (effective relative power per channel) and
    ``cycle_factor``: the number of sequence periods the program spans
    (``period`` = cycle_factor * sequence period).

    ``power_mode`` "pwm": power < 1 is PWM inside every window. "cycles": cycle
    dithering (see the module doc); the sync pulse marks every sequence period.
    The largest factor of CYCLE_FACTORS whose program fits MAX_EDGES and the
    dense-edge rule is used; 1 if no channel needs dithering.
    """
    if power_mode not in POWER_MODES:
        raise ValueError("unknown power mode %r" % (power_mode,))
    factors = CYCLE_FACTORS if any(dithered(enabled, powers, power_mode)) else (1,)
    err = None
    for m in factors:
        try:
            return _compile(steps, gpios, enabled, powers, pwm_period_us, min_pulse_us,
                            active_high, sync_gpio, sync_us, power_mode, m)
        except ValueError as e:
            err = e
    raise err


def _compile(steps, gpios, enabled, powers, pwm_period_us, min_pulse_us, active_high,
             sync_gpio, sync_us, power_mode, cycles):
    period, intervals, duty = channel_intervals(
        steps, enabled, powers, pwm_period_us, min_pulse_us, cycles, power_mode)
    base = period // cycles
    on_ev = {}
    off_ev = {}
    start_on = 0
    all_bits = 0

    def add(table, t, bit):
        table[t % period] = table.get(t % period, 0) | bit

    for ch, iv in enumerate(intervals):
        g = gpios[ch]
        if not 0 <= g <= 15:
            raise ValueError("GPIO%d cannot be driven by the player" % g)
        bit = 1 << g
        all_bits |= bit
        for s, e in iv:
            if s == 0:
                start_on |= bit
            if e - s >= period:
                continue  # solid for the whole period: level only, no edges
            add(on_ev, s, bit)
            add(off_ev, e, bit)
    sync_bit = 0
    if sync_gpio is not None:
        sync_bit = 1 << sync_gpio
        # the same pattern in every sequence period (never dithered)
        one = sync_intervals(steps, len(enabled), sync_us)
        iv = _merge([(c * base + s, c * base + e) for c in range(cycles) for s, e in one])
        for s, e in iv:
            if s == 0:
                start_on |= sync_bit
            if e - s >= period:
                continue  # solid for the whole period: level only, no edges
            add(on_ev, s, sync_bit)
            add(off_ev, e, sync_bit)

    times = sorted(set(on_ev) | set(off_ev))
    if len(times) > MAX_EDGES:
        # no exact count in the text: the firmware stops counting at the limit
        raise ValueError("sequence needs more than %d edges: lengthen the PWM "
                         "period or shorten the sequence" % MAX_EDGES)
    sets = []
    clrs = []
    for t in times:
        on = on_ev.get(t, 0)
        off = off_ev.get(t, 0)
        both = on & off  # off at the period end meets on at the start: stays on
        on &= ~both
        off &= ~both
        if active_high:
            s, c = on, off
        else:
            s, c = off & ~sync_bit, on & ~sync_bit
            s |= on & sync_bit
            c |= off & sync_bit
        sets.append(s)
        clrs.append(c)
    keep = [i for i in range(len(times)) if sets[i] or clrs[i]]
    times = [times[i] for i in keep]
    sets = [sets[i] for i in keep]
    clrs = [clrs[i] for i in keep]
    run = dense_run_us(times, period)
    if run > DENSE_RUN_MAX_US:
        raise ValueError("edges closer than %d us for %s: the player cannot keep up; use a "
                         "longer PWM period, equal powers, or a larger min pulse"
                         % (DENSE_GAP_US + 1, "the whole period" if run >= DENSE_FOREVER else
                            "more than %d us" % DENSE_RUN_MAX_US))

    if active_high:
        start_set, start_clr = start_on, (all_bits | sync_bit) & ~start_on
        idle_set, idle_clr = 0, all_bits | sync_bit
    else:
        lasers_on = start_on & all_bits
        start_set = (all_bits & ~lasers_on) | (start_on & sync_bit)
        start_clr = lasers_on | (sync_bit & ~start_on)
        idle_set, idle_clr = all_bits, sync_bit
    return {
        "period": period, "times": times, "sets": sets, "clrs": clrs,
        "start_set": start_set, "start_clr": start_clr,
        "idle_set": idle_set, "idle_clr": idle_clr, "duty": duty,
        "cycle_factor": cycles,
    }
