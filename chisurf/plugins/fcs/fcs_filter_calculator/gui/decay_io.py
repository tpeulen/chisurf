from __future__ import annotations

import pathlib
from typing import Any

import numpy as np

import chisurf as cs


def load_vector(
    path: pathlib.Path,
    chs: list[str] | None = None,
    detector_settings: dict[str, Any] | None = None,
) -> np.ndarray:
    ext = path.suffix.lower()

    if ext in (".spc", ".ptu", ".ht3", ".tttr"):
        import tttrlib

        try:
            # tttrlib.TTTR handles most formats automatically
            if ext == ".spc":
                try:
                    data = tttrlib.TTTR(str(path), "SPC-130")
                except Exception:
                    data = tttrlib.TTTR(str(path))
            else:
                data = tttrlib.TTTR(str(path))

            header = data.get_header()
            n_tac = header.number_of_micro_time_channels
            hist = np.zeros(n_tac, dtype=np.float64)

            # Get microtimes and routing channels
            microtimes = data.micro_times
            routing = data.routing_channels

            # If chs (detector names) provided, we need to map them back to routing channels
            if chs is not None and len(chs) > 0:
                mask = np.zeros_like(routing, dtype=bool)
                for ch_name in chs:
                    if ch_name.startswith("routing_"):
                        try:
                            ch_idx = int(ch_name.split("_")[1])
                            mask |= routing == ch_idx
                        except Exception:
                            pass
                    elif detector_settings:
                        # Map from detector name to routing channel index using settings
                        try:
                            det_config = detector_settings.get("detectors", {}).get(ch_name, {})
                            # Check for 'chs' (from detector wizard), 'channels', or 'channel'
                            det_chs = det_config.get("chs") or det_config.get("channels")
                            if det_chs:
                                for c in det_chs:
                                    mask |= routing == int(c)
                            else:
                                det_ch = det_config.get("channel")
                                if det_ch is not None:
                                    mask |= routing == int(det_ch)
                        except Exception:
                            pass

                # If no channels matched (mask is all False), use all photons as fallback
                if not mask.any():
                    cs.logging.warning(
                        f"No detector channels matched for {path.name}, using all photons"
                    )
                    valid = (microtimes >= 0) & (microtimes < n_tac)
                else:
                    valid = (microtimes >= 0) & (microtimes < n_tac) & mask
            else:
                valid = (microtimes >= 0) & (microtimes < n_tac)

            np.add.at(hist, microtimes[valid], 1)
            return hist.ravel()
        except Exception as e:
            cs.logging.error(f"tttrlib failed to load {path}: {e}")
            return np.fromfile(path, dtype=np.float64).ravel().astype(float)


    else:
        # Default text loading
        try:
            data = np.loadtxt(path)
            return data.ravel().astype(float)
        except (UnicodeDecodeError, ValueError):
            # Fallback for unexpected binary files
            data = np.fromfile(path, dtype=np.float64)
            return data.ravel().astype(float)
