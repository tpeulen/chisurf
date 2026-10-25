"""FRET check -- the single-button smFRET measurement check.

Drop a TTTR file, get a verdict: is the measurement usable (burst density,
multi-molecule events, stability, background), and which bursts are suspicious.
Simple mode is one drop-zone and the verdict; advanced mode exposes the
editable detection, burst search and corrections, with the burst table and the
ndX hand-off. Works with or without ALEX/PIE; cw two-colour is a full citizen.

Ported from smfret-web (peulen.xyz/smfret) into ChiSurf.
"""
from __future__ import annotations

__version__ = "1.0.0"
