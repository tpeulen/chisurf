"""Parse a shared detector-setup payload into MLE fit inputs.

Every polarisation-resolved MLE consumer (the pixel-wise and molecule-wise
imaging tools, and the burst wizard) receives the *same* detector-definition
payload from the shared setup (`DetectorWizardPage` /
:class:`~...setup_client.DetectorSetupClient`): a mapping of detector name to
``{"chs", "micro_time_ranges"/"mtr", "g_factor", "l1", "l2", ...}``.

Each tool used to re-parse that payload by hand and, crucially, each imaging
tool dropped ``g_factor``/``l1``/``l2`` on the floor — reading only ``chs`` and
the micro-time range — so the polarisation corrections entered in the setup
never reached the fit (it silently ran at ``g=1, l1=l2=0``). This module is the
one parser they share, so the channels, fit window **and** the polarisation
corrections are extracted identically and in one place.
"""

from __future__ import annotations

import dataclasses
import typing


@dataclasses.dataclass
class DetectorSetup:
    """Fit-ready view of a detector-setup payload.

    Attributes
    ----------
    channels : list[int]
        All routing channels, in first-seen order.
    channels_parallel, channels_perpendicular : list[int]
        ``channels`` split by the interleaved convention: within each detector's
        ``chs`` list the **even positions** are parallel (VV) and the odd ones
        perpendicular (VH) — position in the list, not the parity of the channel
        number. Explicit ``ch_p`` / ``ch_s`` on a detector override it. Tools
        that keep a single channel list use ``channels``; tools that need the
        VV/VH split use these.
    micro_range : tuple[int, int] | None
        The first detector's micro-time range, or ``None`` if none was given.
    g_factor, l1, l2 : float | None
        Polarisation corrections from the first detector that supplies them,
        or ``None`` when the payload does not carry them (so callers can keep
        their own default rather than forcing one).
    polarization_resolved : bool
        The setup-level ``polarization_resolved`` flag (default ``True``). When
        it is ``False`` the detectors are not split: every channel is returned in
        ``channels_parallel`` as a single unpolarised stream and
        ``channels_perpendicular`` is empty, matching the micro-time histogram
        wizard. Callers should branch on this rather than inferring "no
        polarisation" from an empty perpendicular list, which is also what a
        one-channel detector produces.
    """

    channels: list[int] = dataclasses.field(default_factory=list)
    channels_parallel: list[int] = dataclasses.field(default_factory=list)
    channels_perpendicular: list[int] = dataclasses.field(default_factory=list)
    micro_range: tuple[int, int] | None = None
    g_factor: float | None = None
    l1: float | None = None
    l2: float | None = None
    polarization_resolved: bool = True


def _first_float(det: typing.Mapping, key: str) -> float | None:
    value = det.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_detector_setup(payload: typing.Mapping | None) -> DetectorSetup:
    """Extract channels, micro-time range and polarisation corrections.

    Parameters
    ----------
    payload : mapping or None
        The shared setup payload, expected to hold ``payload["detectors"]`` as a
        mapping of detector name to its definition dict. A falsy payload yields
        an empty :class:`DetectorSetup`.

    Returns
    -------
    DetectorSetup
    """
    result = DetectorSetup()
    if not payload:
        return result
    # Setup-level flag: whether the detectors are polarisation-resolved at all.
    # A non-resolved setup has no VV/VH split, so the channels stay as one
    # unpolarised stream instead of being alternated into two.
    flag = payload.get("polarization_resolved")
    result.polarization_resolved = True if flag is None else bool(flag)

    detectors = payload.get("detectors") or {}
    for det in detectors.values():
        if not isinstance(det, typing.Mapping):
            continue

        # Parallel/perpendicular follows the *interleaved* convention: the
        # detector's ``chs`` list alternates VV, VH, VV, VH, … so the split is by
        # POSITION IN THE LIST, not by whether the channel number is even.
        #
        # This used to test ``ich % 2 == 0``. The two agree only when the channel
        # numbers happen to be consecutive from an even start; for a detector
        # such as ``chs = [8, 0, 3]`` parity gives parallel ``[8, 0]`` whereas
        # the interleaving actually recorded is parallel ``[8, 3]``. The
        # docstring already described the interleaved rule, and the imaging path
        # (``pixel_maps.detector_ps_channels``) and the micro-time histogram
        # wizard both use ``chs[::2]`` / ``chs[1::2]`` — so this was the odd one
        # out, silently swapping VV and VH channels in the MLE fits.
        chs = [int(ch) for ch in (det.get("chs", []) or [])]
        explicit_p = [int(ch) for ch in (det.get("ch_p") or [])]
        explicit_s = [int(ch) for ch in (det.get("ch_s") or [])]
        if not result.polarization_resolved:
            # Not polarisation-resolved: one unpolarised stream, no VV/VH split.
            parallel, perpendicular = chs, []
        elif explicit_p or explicit_s:
            # An explicit assignment always wins, as in detector_ps_channels.
            parallel, perpendicular = explicit_p, explicit_s
        else:
            parallel, perpendicular = chs[::2], chs[1::2]

        for ich in chs:
            if ich not in result.channels:
                result.channels.append(ich)
        for ich in parallel:
            if ich not in result.channels_parallel:
                result.channels_parallel.append(ich)
        for ich in perpendicular:
            if ich not in result.channels_perpendicular:
                result.channels_perpendicular.append(ich)
        if result.micro_range is None:
            ranges = det.get("mtr") or det.get("microtime_ranges") or det.get("micro_time_ranges")
            if ranges:
                first = ranges[0]
                if first is not None and len(first) == 2:
                    result.micro_range = (int(first[0]), int(first[1]))
        # Polarisation corrections: take them from the first detector that
        # actually carries them, so a later detector left at defaults cannot
        # blank a real calibration.
        if result.g_factor is None:
            result.g_factor = _first_float(det, "g_factor")
        if result.l1 is None:
            result.l1 = _first_float(det, "l1")
        if result.l2 is None:
            result.l2 = _first_float(det, "l2")
    return result
