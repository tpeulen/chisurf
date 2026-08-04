"""Write a decoded H2MM state assignment back into the photon stream.

An H2MM run ends with one state per photon. That assignment is the input to
everything downstream — per-state decays, per-state FCS, per-state burst
statistics — and none of those tools want to be taught about H2MM. So it is
written back into the data itself, two ways:

**State-encoded routing channels.** Each ``(stream, state)`` pair gets its own
routing-channel id and one PTU is written holding every photon of the source
measurement. Self-describing: a per-state decay becomes an ordinary channel
selection in any tool that reads a PTU.

**A msgpack state sidecar.** The source file is left untouched and the per-photon
assignment travels beside it, with the model, the decoder, its seed and the
channel map. Nothing is altered and there is no channel-id budget.

Both come from the same per-photon array and agree photon for photon; the
allocation and the sidecar format are tttrlib's
(:class:`tttrlib.HmmChannelMap`, :class:`tttrlib.HmmStateSidecar`) rather than
re-implemented here, so a file this writes is the same file tttrlib writes.

Why this matters more with a sampling decoder
---------------------------------------------
Viterbi answers *"what is the single most likely state sequence"*. A per-state
decay asks a different question — *"which photons belong to this state"* — and
the argmax answers it with a one-directional bias: photons whose posterior is
(0.7, 0.3) all land in state 0, so state 1's decay is built from too few photons
and the ones it does get are the unrepresentative extremes. Decoding with
``jitter`` and writing *that* gives each state a photon set whose size and
composition match the posterior. See the tttrlib ``h2mm-state-decoding`` guide.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field

import numpy as np
import tttrlib

from chisurf.core.fluorescence.burst.photons import PhotonMeta

logger = logging.getLogger(__name__)

#: Value marking a photon no decoder assigned (outside every burst, or matching
#: no stream). Mirrors ``tttrlib.HMM_UNASSIGNED``.
UNASSIGNED = 255

#: Container written for the split photon stream. PTU's HydraHarp records carry
#: six channel bits (0..63); narrower containers truncate an out-of-range id
#: silently, which would merge two states without a word of warning.
CONTAINER = "PTU"


@dataclass
class StateTttrOutput:
    """What :func:`write_state_tttr` produced, per source measurement."""

    #: ``{measurement stem: written PTU path}``
    tttr_paths: dict[str, str] = field(default_factory=dict)
    #: ``{measurement stem: written msgpack sidecar path}``
    sidecar_paths: dict[str, str] = field(default_factory=dict)
    #: ``{measurement stem: {(stream, state): routing channel id}}``
    channel_maps: dict[str, dict] = field(default_factory=dict)
    #: Photons that no decoder assigned, per measurement.
    n_unassigned: dict[str, int] = field(default_factory=dict)

    def as_output_paths(self) -> dict[str, str]:
        """Flatten into the ``{key: path}`` shape the result summary carries."""
        out: dict[str, str] = {}
        for stem, p in self.tttr_paths.items():
            out[f"state_tttr[{stem}]"] = p
        for stem, p in self.sidecar_paths.items():
            out[f"state_sidecar[{stem}]"] = p
        return out


def _per_file_photons(meta: PhotonMeta, burst_rows, burst_files):
    """Group analysed photons by the measurement they came from.

    Yields ``(stem, tttr_key, photon_index, position)`` where ``photon_index``
    indexes the source measurement's raw arrays and ``position`` indexes the
    concatenated analysis arrays (so a decoded path can be sliced with it).
    """
    if meta.photon_index is None:
        raise ValueError(
            "state TTTR output needs PhotonMeta.photon_index, which maps each "
            "analysed photon back to its position in the raw file; extract the "
            "bursts with return_meta=True"
        )
    burst_id = np.asarray(meta.burst_id, dtype=np.int64)
    photon_index = np.asarray(meta.photon_index, dtype=np.int64)
    rows = np.asarray(burst_rows, dtype=np.int64)

    # Which source file each analysed burst came from, then broadcast to photons.
    file_of_burst = np.asarray([burst_files[int(r)] for r in rows], dtype=object)
    file_of_photon = file_of_burst[burst_id]

    for key in dict.fromkeys(file_of_photon.tolist()):
        sel = np.flatnonzero(file_of_photon == key)
        yield str(pathlib.Path(str(key)).stem), key, photon_index[sel], sel


def write_state_tttr(
    meta: PhotonMeta,
    path: np.ndarray,
    stream_index: np.ndarray,
    tttrs: dict,
    burst_rows,
    burst_files,
    out_dir: str | pathlib.Path,
    *,
    model=None,
    decoder: str = "viterbi",
    seed: int = 0,
    n_states: int | None = None,
    write_tttr: bool = True,
    write_sidecar: bool = True,
    max_channel: int = 63,
) -> StateTttrOutput:
    """Write the decoded state assignment beside each source measurement.

    One PTU and one msgpack sidecar per source measurement, named after its stem
    (``<stem>_h2mm_states.ptu`` / ``<stem>_h2mm_states.msgpack``). Photons of the
    measurement that were never analysed — outside every burst, or matching no
    stream — are kept, on the compressed form of their original channel, so the
    written file still holds the complete measurement.

    Parameters
    ----------
    meta : PhotonMeta
        Per-photon metadata aligned with ``path`` (needs ``photon_index``).
    path : numpy.ndarray
        Per-photon state, length ``n_photons`` (from any decoder).
    stream_index : numpy.ndarray
        Per-photon stream index, same length as ``path``
        (``BurstPhotons.streams``).
    tttrs : dict
        ``{burst-table file key: tttrlib.TTTR}`` for the source measurements.
    burst_rows : array_like
        Burst-table row each analysed burst came from.
    burst_files : sequence
        The burst table's per-row file key (its ``First File`` column).
    out_dir : path
        Directory to write into.
    model : optional
        Fitted model, recorded in the sidecar for reproducibility.
    decoder : str
        Which decoder produced ``path`` — recorded in the sidecar.
    seed : int
        Seed of the draw, recorded in the sidecar.
    n_states : int, optional
        State count; inferred from ``path`` when omitted.
    write_tttr, write_sidecar : bool
        Which outputs to produce. Both default on: they answer different needs
        (self-describing versus non-destructive) and cost one pass each.
    max_channel : int
        Largest routing-channel id the target container can hold.

    Returns
    -------
    StateTttrOutput
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = np.asarray(path, dtype=np.int64)
    stream_index = np.asarray(stream_index, dtype=np.int64)
    if path.shape != stream_index.shape:
        raise ValueError(
            f"path has {path.size} entries but stream_index has "
            f"{stream_index.size}; both are one per analysed photon")
    n_states = int(n_states if n_states is not None else (path.max() + 1 if path.size else 1))
    n_streams = int(stream_index.max() + 1) if stream_index.size else 1
    if n_states > UNASSIGNED:
        raise ValueError(
            f"{n_states} states does not fit the per-photon uint8 state array "
            f"(255 marks 'unassigned')")

    result = StateTttrOutput()

    for stem, key, photon_index, position in _per_file_photons(meta, burst_rows, burst_files):
        src = tttrs.get(key)
        if src is None:
            logger.warning("state TTTR output: no TTTR loaded for %r - skipped", key)
            continue
        n_src = int(src.size())

        # Spread the decode over the whole measurement; everything not analysed
        # stays UNASSIGNED rather than being quietly folded into state 0.
        states = np.full(n_src, UNASSIGNED, dtype=np.uint8)
        streams = np.full(n_src, UNASSIGNED, dtype=np.uint8)
        states[photon_index] = path[position].astype(np.uint8)
        streams[photon_index] = stream_index[position].astype(np.uint8)
        n_unassigned = int(np.count_nonzero(states == UNASSIGNED))
        result.n_unassigned[stem] = n_unassigned

        src_channels = np.asarray(src.routing_channels, dtype=np.int64)
        # tttrlib owns the id layout -- source channels compressed to 0..k-1,
        # (stream, state) pairs densely after -- so a file written here is the
        # same file tttrlib's own split writes.
        cmap = tttrlib.HmmChannelMap.allocate(
            sorted({int(c) for c in np.unique(src_channels)}),
            n_streams, n_states, int(max_channel),
        )
        result.channel_maps[stem] = {
            "source": cmap.source_map,
            "states": cmap.channels_np.tolist(),
            "highest": int(cmap.highest_channel()),
        }

        if write_tttr:
            # Lookup over the whole signed-char domain, so the rewrite is one
            # vectorised take rather than a per-photon search.
            compress = np.full(256, -1, dtype=np.int64)
            for original, new in cmap.source_map.items():
                compress[int(original) & 0xFF] = int(new)
            new_ch = compress[src_channels & 0xFF]
            if (new_ch < 0).any():
                raise RuntimeError(
                    f"{stem}: routing channel(s) "
                    f"{sorted(set(src_channels[new_ch < 0].tolist()))} are not in "
                    f"the channel map - the TTTR changed under the analysis")
            assigned = states != UNASSIGNED
            if assigned.any():
                new_ch[assigned] = cmap.channels_np[
                    streams[assigned].astype(np.int64), states[assigned].astype(np.int64)
                ]

            out = tttrlib.TTTR(src)
            out.set_routing_channel(new_ch.astype(np.int8))
            ptu = out_dir / f"{stem}_h2mm_states.ptu"
            out.write(str(ptu), CONTAINER)
            result.tttr_paths[stem] = str(ptu)

        if write_sidecar:
            sc = tttrlib.HmmStateSidecar()
            sc.set_arrays(states, streams)
            sc.n_states = n_states
            sc.n_streams = n_streams
            sc.decoder = str(decoder)
            sc.seed = int(seed)
            if model is not None:
                sc.model = _to_engine_model(model)
            sc.channel_map = cmap
            sc.has_channel_map = True
            side = out_dir / f"{stem}_h2mm_states.msgpack"
            sc.write(str(side))
            result.sidecar_paths[stem] = str(side)

    return result


def _to_engine_model(model):
    """Convert the plugin's ``H2mmModel`` to tttrlib's, for the sidecar."""
    return tttrlib.HmmModel(
        [float(x) for x in np.asarray(model.prior).ravel()],
        [float(x) for x in np.asarray(model.trans).ravel()],
        [float(x) for x in np.asarray(model.obs).ravel()],
    )
