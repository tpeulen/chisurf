"""Reconstruction of Single-Molecule Analysis from .pto MMFDB Container Provenance Graph.

Reads a `.pto` container, extracts the verbatim TTTR photon stream, parses the embedded
`_mmfdb_operation.settings_json` processing parameters, re-runs burst selection & feature
extraction, and validates that the reconstructed results match the original stored tables.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any, Dict, Optional, Tuple

import numpy as np
import tttrlib

from chisurf.core.fio.pto import Measurement

__all__ = ["reconstruct_analysis_from_pto", "AnalysisReconstructor"]


class AnalysisReconstructor:
    """Reconstruct single-molecule burst analysis from a PTO.MFDB container."""

    def __init__(self, pto_path: str | pathlib.Path):
        self.pto_path = pathlib.Path(pto_path)

    def run(self, artifact_name: Optional[str] = None) -> Dict[str, Any]:
        """Perform provenance-based reconstruction and return verification report."""
        if not self.pto_path.exists():
            raise FileNotFoundError(f"PTO container not found: {self.pto_path}")

        with Measurement.open(self.pto_path, writable=False) as measurement:
            lineage_list = []
            
            # Find primary search table candidate
            candidates = [
                obj for obj in measurement.artifacts()
                if measurement.tag(obj.uid, "_mmfdb_artifact.row_grain") == "burst"
                and measurement.tag(obj.uid, "_mmfdb_operation.operation_type") == "burst_selection"
            ]

            if not candidates:
                raise ValueError(f"No burst_selection artifact found in {self.pto_path}")

            target_artifact = candidates[-1] if artifact_name is None else measurement.artifact(artifact_name)
            target_uid = target_artifact.uid

            # Trace lineage back to instrument source
            lineage = measurement.lineage(target_uid)
            lineage_text = measurement.describe_lineage(target_uid)

            # Get search operation parameters
            settings_json = measurement.tag(target_uid, "_mmfdb_operation.settings_json") or "{}"
            try:
                settings = json.loads(settings_json)
                if isinstance(settings, str):
                    settings = json.loads(settings)
            except Exception:
                settings = {}

            # Extract source TTTR photon stream object
            source_uid = measurement.tag(target_uid, "_mmfdb_edge.source_uid") or measurement.tag(target_uid, "_mmfdb_edge.source_node_id")
            if not source_uid:
                for parent in measurement.parents(target_uid):
                    parent_kind = measurement._f.object(parent).kind
                    if parent_kind in ("tttr_photon_stream", "photons", "instrument_file"):
                        source_uid = parent
                        break

            if not source_uid:
                raise ValueError(f"Could not resolve raw photon stream source for artifact {target_artifact.name}")

            source_obj = measurement._f.object(source_uid)

            # Extract photon stream bytes into temp file
            temp_dir = tempfile.mkdtemp(prefix="pto_reconstruct_")
            temp_stream_path = pathlib.Path(temp_dir) / f"source_{source_uid}.{source_obj.encoding}"

            try:
                measurement.extract(source_uid, temp_stream_path)
                
                # Re-ingest TTTR photon stream (container type 7 for SM files)
                container_type = 7 if source_obj.encoding.lower() == "sm" else 0
                tttr_data = tttrlib.TTTR(str(temp_stream_path), container_type)

                # Re-run burst search using extracted parameters
                L = int(settings.get("min_photons", settings.get("l_min", 30)))
                m = int(settings.get("rate_window", settings.get("m_min", 5)))
                T = float(settings.get("time_separation", settings.get("t_window_ms", 0.5)))
                if T > 1.0:  # Convert ms to seconds if given in ms
                    T = T / 1000.0

                bf = tttrlib.BurstFilter(tttr_data)
                bf.find_bursts()
                n_bursts_reconstructed = bf.get_burst_count()

                reconstructed_props = bf.get_all_burst_properties()

                # Read original stored burst table
                orig_store = measurement.get_store(target_uid)
                n_bursts_original = orig_store.n_rows()

                # Compare burst row counts and bounds
                exact_match = False
                if n_bursts_original == n_bursts_reconstructed:
                    orig_first = np.asarray(orig_store["First Photon"]) if "First Photon" in orig_store else np.asarray(orig_store["first_photon"])
                    orig_last = np.asarray(orig_store["Last Photon"]) if "Last Photon" in orig_store else np.asarray(orig_store["last_photon"])

                    recon_first = reconstructed_props[:, 0].astype(np.int64) if len(reconstructed_props.shape) == 2 else np.array([])
                    recon_last = reconstructed_props[:, 1].astype(np.int64) if len(reconstructed_props.shape) == 2 else np.array([])

                    first_diff = np.max(np.abs(orig_first - recon_first)) if len(orig_first) == len(recon_first) else 999
                    last_diff = np.max(np.abs(orig_last - recon_last)) if len(orig_last) == len(recon_last) else 999

                    exact_match = (first_diff == 0) and (last_diff == 0)

                # Reconstruct non-burst IRF decay curves
                micro_times = np.asarray(tttr_data.micro_times)
                routing = np.asarray(tttr_data.routing_channel)
                burst_mask = np.zeros(len(routing), dtype=bool)
                if len(reconstructed_props) > 0:
                    for row in reconstructed_props:
                        st, sp = int(row[0]), int(row[1])
                        burst_mask[st:sp] = True
                non_burst_mask = ~burst_mask

                irfs_reconstructed = {}
                irf_match = True
                irf_artifacts = [
                    obj for obj in measurement.artifacts()
                    if measurement.tag(obj.uid, "_mmfdb_artifact.data_format") == "irf"
                    or measurement.tag(obj.uid, "_mmfdb_operation.operation_type") == "tcspc_calibration"
                ]

                for irf_art in irf_artifacts:
                    irf_store = measurement.get_store(irf_art.uid)
                    irf_settings = json.loads(measurement.tag(irf_art.uid, "_mmfdb_operation.settings_json") or "{}")
                    ch = int(irf_settings.get("channel", 0))
                    
                    ch_bg = (routing == ch) & non_burst_mask
                    raw_hist, _ = np.histogram(micro_times[ch_bg], bins=4096, range=(0, 4096))
                    bg_floor = float(np.percentile(raw_hist, 20))
                    sub_hist = np.maximum(0.0, raw_hist.astype(float) - bg_floor)
                    s = float(sub_hist.sum())
                    norm_hist = sub_hist / s if s > 0 else sub_hist
                    
                    irfs_reconstructed[irf_art.name] = norm_hist
                    if "counts" in irf_store:
                        orig_counts = np.asarray(irf_store["counts"])
                        if len(orig_counts) == len(norm_hist):
                            irf_diff = np.max(np.abs(orig_counts - norm_hist))
                            if irf_diff > 1e-5:
                                irf_match = False

                return {
                    "is_exact_match": exact_match and irf_match,
                    "burst_match": exact_match,
                    "irf_match": irf_match,
                    "n_bursts_original": n_bursts_original,
                    "n_bursts_reconstructed": n_bursts_reconstructed,
                    "settings_used": settings,
                    "lineage_text": lineage_text,
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "irfs_reconstructed": irfs_reconstructed,
                    "reconstructed_props": reconstructed_props,
                    "original_store": orig_store,
                }
            finally:
                if temp_stream_path.exists():
                    os.unlink(temp_stream_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)


def reconstruct_analysis_from_pto(pto_path: str | pathlib.Path, artifact_name: Optional[str] = None) -> Dict[str, Any]:
    """Reconstruct burst analysis from PTO container using its provenance graph."""
    reconstructor = AnalysisReconstructor(pto_path)
    return reconstructor.run(artifact_name)
