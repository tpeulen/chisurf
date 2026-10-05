"""The correlator step's settings and computation, Qt-free: what the Qt AutoForm panel and the native app both edit.

The Qt sections (preset/channel combos, lifetime-filter buttons, Correlate) live in :mod:`.correlator_panel`; the
native drawers in :mod:`.gui.steps`.
"""

from __future__ import annotations

import pathlib
import typing

import numpy as np
import tttrlib

import chisurf as cs
from chisurf.core.dataspec import load_view_spec
from chisurf.core.fluorescence.fcs.channel_setups import load_fcs_channel_setups

_GUI_DIR = pathlib.Path(__file__).resolve().parent


def parse_microtime_ranges(
    s: str,
) -> list[tuple[int, int]] | None:
    if not s:
        return None
    text = str(s).strip()
    if not text:
        return None
    segments = []
    for item in text.replace(",", ";").split(";"):
        item = item.strip()
        if item:
            segments.append(item)
    if not segments:
        return None
    ranges: list[tuple[int, int]] = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if ":" in seg:
            a_txt, b_txt = seg.split(":", 1)
        else:
            pos = seg.rfind("-")
            if pos <= 0:
                a_txt = seg
                b_txt = seg
            else:
                a_txt = seg[:pos]
                b_txt = seg[pos + 1 :]
        a = int(a_txt.strip())
        b = int(b_txt.strip())
        if a <= b:
            ranges.append((a, b))
        else:
            ranges.append((b, a))
    return ranges if ranges else None


def parse_channels(s: str) -> list[int]:
    if not s:
        return []
    return [int(x) for x in s.replace(",", " ").split()]


#: The correlation algorithms tttrlib offers, in the order the form lists them.
METHODS = ("laurence", "wahl", "felekyan")


class CorrelatorSettingsModel:
    def __init__(self):
        self.n_bins = int(cs.core.settings.cs_settings.get("correlator", {}).get("B", 3))
        self.n_casc = int(
            cs.core.settings.cs_settings.get("correlator", {}).get("number_of_cascades", 20)
        )
        self.n_splits = int(cs.core.settings.cs_settings.get("correlator", {}).get("split", 1))
        self.make_fine = bool(cs.core.settings.cs_settings.get("correlator", {}).get("fine", False))
        #: The tttrlib correlation algorithm. ``laurence`` (symmetric, Schätzel normalization) is
        #: the default: it normalizes each lag by the count rate in the overlapping sub-intervals,
        #: which removes the long-lag upturn near the chunk duration.
        self.method = str(cs.core.settings.cs_settings.get("correlator", {}).get("method", "laurence"))
        self.microtime_binning = int(
            cs.core.settings.cs_settings.get("correlator", {}).get("microtime_binning", 1)
        )
        self.channel_a = ""
        self.channel_b = ""
        self.microtime_range_a = ""
        self.microtime_range_b = ""

        self._tttr: tttrlib.TTTR | None = None
        self._correlations: list[dict] = []
        self._channel_defs: dict = {}
        self._analysis_folder = pathlib.Path()
        self._output_subdir = pathlib.Path("cr5")

        self._fcs_presets: list[dict] = []
        self._fcs_preset_detectors: dict = {}
        self._fcs_preset_corr: dict = {}

        # Optional lifetime-filter (FLCS) weight source: when set, correlation
        # switches from binary channel/micro-time masks to species auto/cross
        # correlations weighted by the loaded filters (see set_lifetime_filters).
        # In this mode the A/B selectors pick *species* (filter rows) instead of
        # detector channels; ``_species_a``/``_species_b`` hold those indices.
        self._lifetime_filters: typing.Any = None
        self._filter_labels: list[str] | None = None
        self._filter_source: str = ""
        self._species_a: int = 0
        self._species_b: int = 0

        self._form: typing.Any = None

    @property
    def filter_mode(self) -> bool:
        """True when lifetime filters are loaded (species-correlation mode)."""
        return self._lifetime_filters is not None

    def view_spec(self):
        return load_view_spec(_GUI_DIR / "correlator.view.json")

    def get_correlation_settings(self) -> dict:
        return {
            "n_bins": self.n_bins,
            "n_casc": self.n_casc,
            "make_fine": self.make_fine,
        }

    def correlation_series(self):
        from chisurf.gui import chiplot as cp

        n = len(self._correlations)
        return [
            {
                "x": c["x"],
                "y": c["y"],
                "name": c.get("name", f"chunk {i}"),
                "color": cp.int_color(i, count=max(n, 6)).as_tuple(),
            }
            for i, c in enumerate(self._correlations)
        ]

    def set_lifetime_filters(self, filters, labels=None) -> None:
        """Enable lifetime-filter (FLCS) correlation from a computed filter set.

        Parameters
        ----------
        filters : array_like or dict or None
            Lifetime filters — a 2-D ``(n_species, n_bins)`` matrix, a
            ``{routing_channel: (n_species, n_bins)}`` channel-aware table (e.g.
            from ``FilterResultMFD.to_channel_filters``), or ``None`` to return
            to plain channel/micro-time-mask correlation.
        labels : sequence of str, optional
            Species labels used to name the emitted correlation datasets.
        """
        self._lifetime_filters = filters
        self._filter_labels = list(labels) if labels is not None else None
        # Reset the species selection to the first (auto-correlation) species.
        self._species_a = 0
        self._species_b = 0

    def load_lifetime_filter_file(self, path) -> int:
        """Load lifetime filters from a file and switch to species mode.

        Supported formats:

        * ``.json`` — an fFCS ``FilterResult`` written by the FCS Filter
          Calculator (``to_json``); the ``(n_species, n_bins)`` correlation
          filter matrix (nuisance filters excluded) and species labels are used.
        * ``.npy`` — a 2-D ``(n_species, n_bins)`` filter matrix.
        * ``.npz`` — an archive with a ``filters`` array and optional ``labels``.

        Returns
        -------
        int
            The number of species (filter rows) loaded.
        """
        p = pathlib.Path(path)
        suffix = p.suffix.lower()
        labels: list[str] | None = None
        if suffix == ".json":
            from chisurf.plugins.fcs.fcs_filter_calculator.api import FilterResult

            result = FilterResult.from_json(p)
            filters = np.asarray(result.to_channel_filters(), dtype=float)
            meta = result.metadata or {}
            for key in ("species_labels", "labels", "component_labels"):
                val = meta.get(key)
                if isinstance(val, (list, tuple)) and len(val) >= filters.shape[0]:
                    labels = [str(x) for x in val[: filters.shape[0]]]
                    break
        elif suffix == ".npz":
            data = np.load(p, allow_pickle=True)
            filters = np.asarray(data["filters"], dtype=float)
            if "labels" in data:
                labels = [str(x) for x in list(data["labels"])]
        else:  # .npy or raw array
            filters = np.asarray(np.load(p), dtype=float)
        if filters.ndim != 2:
            raise ValueError(
                f"Expected a 2-D (n_species, n_bins) filter matrix, got shape {filters.shape}"
            )
        if labels is None:
            labels = [f"Species {k + 1}" for k in range(filters.shape[0])]
        self.set_lifetime_filters(filters, labels)
        self._filter_source = p.name
        return filters.shape[0]

    def clear_lifetime_filter(self) -> None:
        """Unload lifetime filters and return to detector-channel correlation."""
        self.set_lifetime_filters(None, None)
        self._filter_source = ""

    @staticmethod
    def _subset_species(filters, indices):
        """Return ``filters`` restricted to the given species (filter rows)."""
        if isinstance(filters, dict):
            return {ch: np.asarray(f)[indices] for ch, f in filters.items()}
        arr = np.asarray(filters, dtype=float)
        if arr.ndim == 3:  # (n_channels, n_species, n_bins)
            return arr[:, indices, :]
        return arr[indices]

    def correlate_data(self, progress=None) -> str:
        """Correlate the loaded photons; the message to show (an empty selection says so, nothing raises).

        Parameters
        ----------
        progress : callable, optional
            ``progress(done, total) -> bool`` after each chunk; ``False`` stops (the chunks done are kept).
        """
        if self._tttr is None or len(self._tttr) == 0:
            return "No photons selected for correlation. Please load data."
        if self._lifetime_filters is not None:
            self._correlate_lifetime_filtered()
            return f"{len(self._correlations)} species correlation(s)."

        n_chunks = self.n_splits
        ch1 = parse_channels(self.channel_a)
        ch2 = parse_channels(self.channel_b)
        if not ch1 or not ch2:
            used = list(map(int, self._tttr.get_used_routing_channels()))
            if not ch1:
                ch1 = used
            if not ch2:
                ch2 = used

        settings = self.get_correlation_settings()
        self._correlations.clear()
        for i, chunk in enumerate(self._split_array(self._tttr, n_chunks)):
            if chunk is None or len(chunk.macro_times) == 0:
                continue
            result = self._correlate_one(chunk, ch1, ch2, settings, i)
            if result is not None:
                self._correlations.append(result)
            if progress is not None and progress(i + 1, n_chunks) is False:
                break
        n = len(self._correlations)
        return f"{n} chunk(s) correlated." if n else "Correlation empty."

    def _split_array(self, tttr, n):
        chunk_size = max(1, len(tttr) // n)
        return [tttr[i * chunk_size : (i + 1) * chunk_size] for i in range(n)]

    def _correlate_lifetime_filtered(self) -> None:
        """Compute the selected species auto-/cross-correlation from the filters.

        In filter mode the A/B selectors pick species (filter rows): equal
        indices give that species' auto-correlation, distinct indices give the
        A×B cross-correlation. Delegates to the Qt-free entrypoint
        :func:`chisurf.plugins.fcs.fcs_correlator.core.filtered_correlation_from_tttr`.
        """
        from chisurf.plugins.fcs.fcs_correlator.core import filtered_correlation_from_tttr

        self._correlations.clear()
        labels = self._filter_labels or []
        i, j = int(self._species_a), int(self._species_b)
        if i == j:
            indices = [i]
            want_cross = False
        else:
            indices = [i, j]
            want_cross = True
        sub_filters = self._subset_species(self._lifetime_filters, indices)
        sub_labels = [labels[k] for k in indices] if len(labels) > max(indices) else None
        datasets = filtered_correlation_from_tttr(
            self._tttr,
            sub_filters,
            self.get_correlation_settings(),
            labels=sub_labels,
        )
        for d in datasets:
            is_cross = d["species_a"] != d["species_b"]
            if is_cross != want_cross:
                continue
            self._correlations.append(
                {
                    "x": d["x"],
                    "y": d["y"],
                    "correlation_settings": self.get_correlation_settings(),
                    "chunk": 0,
                    "duration": 0.0,
                    "name": d["name"],
                    "channel_a": {"species": i},
                    "channel_b": {"species": j},
                }
            )

    def _correlate_one(self, tttr, ch1, ch2, settings, idx):
        t = tttr.macro_times
        mask_a = tttrlib.TTTRMask()
        mask_b = tttrlib.TTTRMask()
        mask_a.select_channels(tttr, ch1, mask=True)
        mask_b.select_channels(tttr, ch2, mask=True)
        m_a = mask_a.mask.astype(bool)
        m_b = mask_b.mask.astype(bool)

        mta = parse_microtime_ranges(self.microtime_range_a)
        mtb = parse_microtime_ranges(self.microtime_range_b)
        if mta:
            mm_a = tttrlib.TTTRMask()
            mm_a.select_microtime_ranges(tttr, mta)
            mm_a.flip()
            m_a = np.logical_and(m_a, mm_a.mask.astype(bool))
        if mtb:
            mm_b = tttrlib.TTTRMask()
            mm_b.select_microtime_ranges(tttr, mtb)
            mm_b.flip()
            m_b = np.logical_and(m_b, mm_b.mask.astype(bool))

        w1 = np.array(m_a, dtype=np.float64)
        w2 = np.array(m_b, dtype=np.float64)
        sw1 = w1.sum()
        sw2 = w2.sum()
        if sw1 <= 0.0 or sw2 <= 0.0:
            return None

        dT = tttr.header.macro_time_resolution * 1000.0
        if len(t) > 100:
            t_start = np.percentile(t, 0.1)
            t_end = np.percentile(t, 99.9)
        else:
            t_start = t[0] if len(t) > 0 else 0.0
            t_end = t[-1] if len(t) > 0 else 0.0
        dur = (t_end - t_start) * dT

        correlator = tttrlib.Correlator(**settings)
        if self.method not in METHODS:
            raise ValueError(f"Unknown correlation method {self.method!r}; choose one of {', '.join(METHODS)}.")
        correlator.method = self.method
        correlator.set_macrotimes(t, t)
        correlator.set_weights(w1, w2)
        if self.make_fine:
            b = self.microtime_binning
            n_mt = tttr.get_number_of_micro_time_channels()
            mt = tttr.micro_times
            if b > 1:
                mt = mt // b
                n_mt = (n_mt + b - 1) // b
            correlator.set_microtimes(mt, mt, n_mt)
            dt = tttr.header.micro_time_resolution * b * 1000.0
        else:
            dt = dT
        x = correlator.x_axis * dt
        y = np.asarray(correlator.correlation, dtype=float)
        # Multi-tau produces lag times set by the cascade count, which can run
        # past the chunk's actual measured duration. Correlation values at lags
        # beyond the duration are meaningless (ever fewer photon pairs). Keep the
        # lag grid intact (so chunks stay averageable) but flatten those points to
        # the uncorrelated baseline G=1 (zero correlation amplitude). ``dur`` and
        # ``x`` are both in milliseconds.
        if dur > 0.0:
            y[x > dur] = 1.0
        return {
            "x": x.tolist(),
            "y": y.tolist(),
            "correlation_settings": {**settings, "method": self.method},
            "chunk": idx,
            "duration": dur / 1000.0,
            "channel_a": {
                "channels": ch1,
                "microtime_range": mta,
                "counts": sw1,
            },
            "channel_b": {
                "channels": ch2,
                "microtime_range": mtb,
                "counts": sw2,
            },
        }

    def load_fcs_presets(self, setup_name, detectors) -> None:
        cfg = load_fcs_channel_setups()
        setups = cfg.get("setups", {}) if isinstance(cfg, dict) else {}
        block = setups.get(setup_name or "", {}) if isinstance(setups, dict) else {}
        pairs = block.get("pairs", []) if isinstance(block, dict) else []
        if not isinstance(pairs, list):
            pairs = []
        if not pairs and detectors:
            # No FCS preset block for this setup: derive sensible defaults from
            # the detectors — an ACF per detector plus a CCF for each pair.
            pairs = self._default_pairs_from_detectors(detectors)
        self._fcs_presets = pairs
        self._fcs_preset_detectors = detectors or {}
        self._fcs_preset_corr = block.get("correlator", {}) if isinstance(block, dict) else {}

    @staticmethod
    def _default_pairs_from_detectors(detectors: dict) -> list[dict]:
        names = [n for n in detectors if isinstance(n, str) and n.strip()]
        pairs: list[dict] = []
        for n in names:
            pairs.append({"name": f"{n} ACF", "channel_a": n, "channel_b": n, "kind": "ACF"})
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                pairs.append(
                    {"name": f"{a}×{b} CCF", "channel_a": a, "channel_b": b, "kind": "CCF"}
                )
        return pairs

    def apply_preset(self, index: int) -> bool:
        if index <= 0 or not self._fcs_presets:
            return False
        try:
            pair = self._fcs_presets[index - 1]
        except Exception:
            return False
        dets = self._fcs_preset_detectors or {}
        try:
            cha_name = str(pair.get("channel_a", ""))
            chb_name = str(pair.get("channel_b", ""))
        except Exception:
            return False
        da = dets.get(cha_name, {}) if isinstance(dets, dict) else {}
        db = dets.get(chb_name, {}) if isinstance(dets, dict) else {}
        chs_a = da.get("chs", []) or []
        chs_b = db.get("chs", []) or chs_a
        if chs_a:
            self.channel_a = ",".join(map(str, chs_a))
        if chs_b:
            self.channel_b = ",".join(map(str, chs_b))
        mta = da.get("micro_time_ranges", []) or []
        mtb = db.get("micro_time_ranges", []) or []
        if mta:
            self.microtime_range_a = ";".join(f"{a}-{b}" for a, b in mta)
        if mtb:
            self.microtime_range_b = ";".join(f"{a}-{b}" for a, b in mtb)
        corr = dict(self._fcs_preset_corr)
        pc = pair.get("correlator")
        if isinstance(pc, dict):
            corr.update(pc)
        if "n_bins" in corr:
            self.n_bins = int(corr["n_bins"])
        if "n_casc" in corr:
            self.n_casc = int(corr["n_casc"])
        if "make_fine" in corr:
            self.make_fine = bool(corr["make_fine"])
        if "microtime_binning" in corr:
            self.microtime_binning = int(corr["microtime_binning"])
        if corr.get("method") in METHODS:
            self.method = str(corr["method"])
        return True


def preset_names(model: CorrelatorSettingsModel) -> list[str]:
    """The FCS preset combo's entries after the empty one: each pair's name, else ``AxB`` / ``A_ACF``."""
    names = []
    for p in model._fcs_presets:
        try:
            cha, chb, nm = str(p.get("channel_a", "")), str(p.get("channel_b", "")), str(p.get("name", ""))
        except Exception:  # noqa: BLE001 - a malformed preset is skipped, as in the Qt combo
            continue
        names.append(nm or (f"{cha}x{chb}" if cha != chb else f"{cha}_ACF" if cha else "(unnamed)"))
    return names


def apply_channel_key(model: CorrelatorSettingsModel, side: str, key: str) -> None:
    """A logical channel picked for side ``"a"`` / ``"b"``: its routing channels and micro-time ranges into the fields."""
    entries = model._channel_defs.get(key)
    if not entries:
        return
    uniq: list = []
    for e in entries:
        for c in e.get("detector_chs", []) or []:
            if c not in uniq:
                uniq.append(c)
    setattr(model, "channel_a" if side == "a" else "channel_b", ",".join(str(c) for c in uniq))
    segs = [
        f"{int(r[0])}-{int(r[1])}"
        for r in (e.get("micro_time_range") for e in entries)
        if isinstance(r, (list, tuple)) and len(r) >= 2
    ]
    setattr(model, "microtime_range_a" if side == "a" else "microtime_range_b", ";".join(segs))
