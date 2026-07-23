"""RPC contract for the LUT tools: method names + JSON-Schemas.

Each schema's ``description`` fields become tooltips when a form is rendered with
:meth:`chisurf.gui.autoform.AutoForm.from_rpc_method`. The backend
(``backend/services.py``) registers handlers under these names; the GUI client
and CLI call them.
"""

from __future__ import annotations

from typing import Any


# ── service envelope helpers ───────────────────────────────────────────────
def service_success(result: dict[str, Any]) -> dict[str, Any]:
    """Wrap an API result in the standard JSON-RPC service envelope."""
    return {"ok": True, "result": result}


def service_error(message: str) -> dict[str, Any]:
    """Wrap an error message in the standard JSON-RPC service envelope."""
    return {"ok": False, "error": str(message)}


# ── method names ──────────────────────────────────────────────────────────
METHOD_AUTODETECT = "lut.autodetect_region"
METHOD_COMPUTE = "lut.compute"
METHOD_APPLY_PREVIEW = "lut.apply_preview"
METHOD_SETTINGS_BUILD = "lut.settings_build"
METHOD_SETTINGS_LOAD = "lut.settings_load"

# ── JSON-Schemas (params) — descriptions surface as tooltips ───────────────
COMPUTE_PARAMS = {
    "type": "object",
    "title": "Compute microtime LUT",
    "description": (
        "Stage ① — build a TAC-linearization LUT from a uniform-illumination "
        "(uncorrelated-light) measurement. The LUT remaps raw micro-times onto a "
        "corrected, equal-width axis."
    ),
    "properties": {
        "files": {
            "type": "array",
            "items": {"type": "string"},
            "description": "TTTR file(s) of a flat / uniform-illumination measurement.",
        },
        "routine": {
            "type": "string",
            "description": "tttrlib reading routine (e.g. SPC-130); blank = auto-detect.",
        },
        "channel": {
            "type": "integer",
            "description": "Routing channel to compute the LUT for (per-channel; recommended).",
        },
        "n_bins": {
            "type": "integer",
            "description": "TAC histogram bin count; 0 = infer from the data.",
        },
        "linear_start": {
            "type": "integer",
            "description": "First bin of the flat linear region; blank = auto-detect.",
        },
        "linear_stop": {
            "type": "integer",
            "description": "First bin after the linear region; blank = auto-detect.",
        },
        "ntac_required": {
            "type": "integer",
            "description": "Target number of corrected NTAC bins; 0 = same as input.",
        },
        "noffset": {
            "type": "integer",
            "description": "Offset subtracted from corrected NTAC indices.",
        },
    },
    "required": ["files"],
}

APPLY_PREVIEW_PARAMS = {
    "type": "object",
    "title": "Preview corrected histogram",
    "description": "Apply a LUT to one channel and return its corrected micro-time histogram.",
    "properties": {
        "path": {"type": "string", "description": "TTTR file to preview."},
        "channel": {"type": "integer", "description": "Routing channel to histogram."},
        "routine": {"type": "string", "description": "tttrlib reading routine (blank = auto)."},
        "coarsening": {"type": "integer", "description": "Histogram coarsening factor (>=1)."},
    },
    "required": ["path", "channel"],
}

SETTINGS_BUILD_PARAMS = {
    "type": "object",
    "title": "Build settings.tttr.json",
    "description": (
        "Stage ② — assemble the portable settings bundle from per-channel LUTs and "
        "shifts. The channel-definition editor imports these channel_luts into the setup."
    ),
    "properties": {
        "channel_luts": {
            "type": "object",
            "description": "Mapping {routing_channel: NTAC_fract list} to assign.",
        },
        "channel_shifts": {
            "type": "object",
            "description": "Mapping {routing_channel: integer} photon-level shifts.",
        },
        "reading_routine": {"type": "string", "description": "tttrlib reading routine."},
        "out_path": {"type": "string", "description": "Where to write settings.tttr.json."},
    },
    "required": ["channel_luts"],
}
