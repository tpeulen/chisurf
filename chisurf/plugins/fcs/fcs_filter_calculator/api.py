"""
Core API for filtered FCS filter computation.

This module provides a clean programmatic interface for computing lifetime
filters for filtered FCS/FLCS analysis. It can be used independently of the
GUI or CLI.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List
from dataclasses import dataclass
from enum import Enum

import numpy as np


@dataclass
class UnmixResult:
    """Non-negative decomposition of a mixed decay into known patterns."""

    component_counts: np.ndarray
    fractions: np.ndarray
    component_decays: List[np.ndarray]
    reconstruction: np.ndarray
    weighted_residuals: np.ndarray
    background_counts: float = 0.0
    nuisance_counts: np.ndarray | None = None
    nuisance_labels: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_counts": self.component_counts.tolist(),
            "fractions": self.fractions.tolist(),
            "component_decays": [decay.tolist() for decay in self.component_decays],
            "reconstruction": self.reconstruction.tolist(),
            "weighted_residuals": self.weighted_residuals.tolist(),
            "background_counts": self.background_counts,
            "nuisance_counts": np.asarray(
                self.nuisance_counts if self.nuisance_counts is not None else [],
                dtype=float,
            ).tolist(),
            "nuisance_labels": list(self.nuisance_labels or []),
        }


class DetectionMode(Enum):
    """Detection mode for filter computation."""
    SINGLE = "single"  # Single channel (standard)
    MFD = "mfd"  # Multi-parameter Fluorescence Detection (parallel + perpendicular)


# The canonical synthetic-decay generator lives in the core fluorescence layer;
# re-export it here so existing Filter-Calculator imports keep working.
from chisurf.core.fluorescence.decay import (  # noqa: E402,F401
    synthetic_component_decay,
    synthetic_decay,
)


def unmix_decay(
    total_decay: np.ndarray,
    component_decays: List[np.ndarray],
    *,
    fit_background: bool = False,
    poisson_weighted: bool = True,
    nuisance_decays: List[np.ndarray] | None = None,
    nuisance_labels: List[str] | None = None,
) -> UnmixResult:
    """Fit a mixed decay as a non-negative sum of known component patterns.

    The component patterns are normalized before fitting, so fitted coefficients
    are integrated component counts and fractions are directly interpretable.
    This deliberately does not attempt an unconstrained multi-exponential fit:
    one mixed histogram is only identifiable after the component shapes (for
    example synthetic lifetimes or measured references) have been specified.
    """
    from scipy.optimize import lsq_linear

    total = np.asarray(total_decay, dtype=float)
    if total.ndim != 1 or total.size == 0:
        raise ValueError("total_decay must be a non-empty 1D array")
    if np.any(~np.isfinite(total)) or np.any(total < 0.0):
        raise ValueError("total_decay must be finite and non-negative")
    if not component_decays:
        raise ValueError("at least one component decay is required")

    def normalized_patterns(decays, argument_name):
        normalized = []
        for index, component in enumerate(decays):
            pattern = np.asarray(component, dtype=float)
            if pattern.ndim != 1 or pattern.size != total.size:
                raise ValueError(f"{argument_name}[{index}] must match total_decay")
            if np.any(~np.isfinite(pattern)) or np.any(pattern < 0.0) or pattern.sum() <= 0.0:
                raise ValueError(
                    f"{argument_name}[{index}] must be finite, non-negative, and non-zero"
                )
            normalized.append(pattern / pattern.sum())
        return normalized

    patterns = normalized_patterns(component_decays, "component_decays")
    nuisance = normalized_patterns(nuisance_decays or [], "nuisance_decays")
    labels = list(nuisance_labels or [])
    if len(labels) != len(nuisance):
        raise ValueError("nuisance_labels must match nuisance_decays")
    if fit_background:
        from chisurf.core.fluorescence.decay import afterpulse_decay_pattern

        nuisance.append(afterpulse_decay_pattern(total.size))
        labels.append("Background / constant")

    design_patterns = patterns + nuisance
    design = np.column_stack(design_patterns)

    if poisson_weighted:
        scale = np.sqrt(np.maximum(total, 1.0))
        fitted = lsq_linear(design / scale[:, None], total / scale, bounds=(0.0, np.inf))
    else:
        fitted = lsq_linear(design, total, bounds=(0.0, np.inf))
    if not fitted.success:
        raise RuntimeError(f"decay unmixing failed: {fitted.message}")

    n_components = len(patterns)
    counts = fitted.x[:n_components]
    nuisance_counts = fitted.x[n_components:]
    background_counts = float(nuisance_counts[-1]) if fit_background else 0.0
    scaled_components = [pattern * count for pattern, count in zip(patterns, counts)]
    reconstruction = design @ fitted.x
    residuals = (total - reconstruction) / np.sqrt(np.maximum(total, 1.0))
    count_sum = counts.sum()
    fractions = counts / count_sum if count_sum > 0.0 else np.zeros_like(counts)
    return UnmixResult(
        component_counts=counts,
        fractions=fractions,
        component_decays=scaled_components,
        reconstruction=reconstruction,
        weighted_residuals=residuals,
        background_counts=background_counts,
        nuisance_counts=nuisance_counts,
        nuisance_labels=labels,
    )


def compute_synthetic_filters(
    total_decay: np.ndarray,
    lifetimes: List[float] | np.ndarray,
    *,
    bin_width: float = 1.0,
    start_bin: int = 0,
    irf: np.ndarray | List[float] | None = None,
    fit_background: bool = False,
    metadata: Dict[str, Any] | None = None,
) -> FilterResult:
    """Generate lifetime components, unmix ``total_decay``, and compute filters."""
    total = np.asarray(total_decay, dtype=float)
    taus = np.atleast_1d(np.asarray(lifetimes, dtype=float))
    patterns = [
        synthetic_decay(
            total.size,
            tau,
            bin_width=bin_width,
            start_bin=start_bin,
            irf=irf,
        )
        for tau in taus
    ]
    unmixing = unmix_decay(total, patterns, fit_background=fit_background)
    result_metadata = dict(metadata or {})
    result_metadata.update({
        "synthetic_components": [
            {"lifetime": float(tau), "bin_width": float(bin_width), "start_bin": int(start_bin)}
            for tau in taus
        ],
        "unmixing": unmixing.to_dict(),
    })
    return compute_filters(total, patterns, metadata=result_metadata)


@dataclass
class FilterResult:
    """Result container for fFCS filter computation (single channel).
    
    Attributes
    ----------
    filters : np.ndarray
        Filter matrix with shape (n_species, n_bins). Each row is a filter
        for one species.
    reconstruction : np.ndarray
        Reconstructed total decay from the normalized patterns.
    weighted_residuals : np.ndarray
        Weighted residuals: (total - reconstruction) / sqrt(total).
    total_decay : np.ndarray
        Original total decay histogram.
    species_decays : List[np.ndarray]
        Original species decay histograms.
    metadata : dict
        Additional metadata (file paths, parameters, etc.).
    mode : DetectionMode
        Detection mode (always SINGLE for this class).
    total_path : str | None
        Path to the total decay file used.
    species_patterns : list, optional
        File lists or synthetic source descriptors for each species pattern.
    """
    filters: np.ndarray
    reconstruction: np.ndarray
    weighted_residuals: np.ndarray
    total_decay: np.ndarray
    species_decays: List[np.ndarray]
    metadata: Dict[str, Any]
    mode: DetectionMode = DetectionMode.SINGLE
    total_path: str | List[str] | None = None
    species_patterns: List[Any] | None = None
    nuisance_count: int = 0
    nuisance_labels: List[str] | None = None
    
    @property
    def n_species(self) -> int:
        """Number of correlation species (excluding nuisance filters)."""
        return self.filters.shape[0] - int(self.nuisance_count)

    @property
    def n_filters(self) -> int:
        """Total filter count, including nuisance-rejection filters."""
        return self.filters.shape[0]
    
    @property
    def n_bins(self) -> int:
        """Number of TAC bins."""
        return self.filters.shape[1]

    def to_channel_filters(self):
        """Return the channel-agnostic ``(n_species, n_bins)`` filter matrix.

        A single-detector result applies one filter set to all photons; the
        2-D matrix is exactly what the correlator's single-axis weighting takes.
        """
        return self.filters[:self.n_species]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "mode": self.mode.value,
            "metadata": self.metadata,
            "total_path": self.total_path,
            "species_patterns": self.species_patterns,
            "nuisance_count": int(self.nuisance_count),
            "nuisance_labels": list(self.nuisance_labels or []),
            "filters": self.filters.tolist(),
            "reconstruction": self.reconstruction.tolist(),
            "weighted_residuals": self.weighted_residuals.tolist(),
            "total_decay": self.total_decay.tolist(),
            "species_decays": [s.tolist() for s in self.species_decays],
        }
    
    def to_json(self, path: str | pathlib.Path, **kwargs) -> None:
        """Save result to JSON file."""
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, **kwargs)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FilterResult:
        """Load from dictionary."""
        mode_str = data.get("mode", "single")
        mode = DetectionMode(mode_str) if isinstance(mode_str, str) else DetectionMode.SINGLE
        
        return cls(
            filters=np.array(data["filters"]),
            reconstruction=np.array(data["reconstruction"]),
            weighted_residuals=np.array(data["weighted_residuals"]),
            total_decay=np.array(data["total_decay"]),
            species_decays=[np.array(s) for s in data["species_decays"]],
            metadata=data.get("metadata", {}),
            mode=mode,
            total_path=data.get("total_path"),
            species_patterns=data.get("species_patterns"),
            nuisance_count=int(data.get("nuisance_count", 0)),
            nuisance_labels=list(data.get("nuisance_labels", [])),
        )
    
    @classmethod
    def from_json(cls, path: str | pathlib.Path) -> FilterResult:
        """Load from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class FilterResultMFD:
    """Result container for MFD filter computation."""
    filters_par: np.ndarray
    filters_perp: np.ndarray
    reconstruction_par: np.ndarray
    reconstruction_perp: np.ndarray
    weighted_residuals_par: np.ndarray
    weighted_residuals_perp: np.ndarray
    total_decay_par: np.ndarray
    total_decay_perp: np.ndarray
    species_decays_par: List[np.ndarray]
    species_decays_perp: List[np.ndarray]
    metadata: Dict[str, Any]
    mode: DetectionMode = DetectionMode.MFD
    nuisance_count: int = 0
    nuisance_labels: List[str] | None = None
    
    @property
    def n_species(self) -> int:
        return self.filters_par.shape[0] - int(self.nuisance_count)

    @property
    def n_filters(self) -> int:
        return self.filters_par.shape[0]
    
    @property
    def n_bins(self) -> int:
        return self.filters_par.shape[1]

    def to_channel_filters(self, par_channels, perp_channels) -> dict:
        """Map parallel/perpendicular routing channels to their filter matrices.

        Returns a ``{routing_channel: (n_species, n_bins)}`` table for the
        channel-aware correlator: parallel detectors get ``filters_par``,
        perpendicular detectors get ``filters_perp`` (mirroring PAM's per-photon
        par/perp filter application).
        """
        table = {int(ch): self.filters_par[:self.n_species] for ch in par_channels}
        table.update({int(ch): self.filters_perp[:self.n_species] for ch in perp_channels})
        return table

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "metadata": self.metadata,
            "filters_par": self.filters_par.tolist(),
            "filters_perp": self.filters_perp.tolist(),
            "reconstruction_par": self.reconstruction_par.tolist(),
            "reconstruction_perp": self.reconstruction_perp.tolist(),
            "weighted_residuals_par": self.weighted_residuals_par.tolist(),
            "weighted_residuals_perp": self.weighted_residuals_perp.tolist(),
            "total_decay_par": self.total_decay_par.tolist(),
            "total_decay_perp": self.total_decay_perp.tolist(),
            "species_decays_par": [s.tolist() for s in self.species_decays_par],
            "species_decays_perp": [s.tolist() for s in self.species_decays_perp],
            "nuisance_count": int(self.nuisance_count),
            "nuisance_labels": list(self.nuisance_labels or []),
        }
    
    def to_json(self, path: str | pathlib.Path, **kwargs) -> None:
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, **kwargs)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FilterResultMFD:
        return cls(
            filters_par=np.array(data["filters_par"]),
            filters_perp=np.array(data["filters_perp"]),
            reconstruction_par=np.array(data["reconstruction_par"]),
            reconstruction_perp=np.array(data["reconstruction_perp"]),
            weighted_residuals_par=np.array(data["weighted_residuals_par"]),
            weighted_residuals_perp=np.array(data["weighted_residuals_perp"]),
            total_decay_par=np.array(data["total_decay_par"]),
            total_decay_perp=np.array(data["total_decay_perp"]),
            species_decays_par=[np.array(s) for s in data["species_decays_par"]],
            species_decays_perp=[np.array(s) for s in data["species_decays_perp"]],
            metadata=data.get("metadata", {}),
            nuisance_count=int(data.get("nuisance_count", 0)),
            nuisance_labels=list(data.get("nuisance_labels", [])),
        )
    
    @classmethod
    def from_json(cls, path: str | pathlib.Path) -> FilterResultMFD:
        with open(path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)


def compute_filters(
    total_decay: np.ndarray,
    species_decays: List[np.ndarray],
    metadata: Dict[str, Any] | None = None,
    total_path: List[str] | None = None,
    species_patterns: List[Any] | None = None,
    nuisance_decays: List[np.ndarray] | None = None,
    nuisance_labels: List[str] | None = None,
    reject_nuisance: bool = True,
) -> FilterResult:
    """Compute fFCS lifetime filters.
    
    Implements the weighted least-squares filter computation of PAM's
    BurstBrowser ``Calc_fFCS_Filters`` (see ``calc_ffcs_filters``).
    
    Algorithm
    ---------
    1. Normalize species decay patterns: D = D / sum(D, axis=0)
    2. Create weight matrix: W = diag(1 / max(total_decay, 1))
    3. Compute filter matrix: F = (D^T W D)^(-1) D^T W
    4. Reconstruction: sum((D^T W D)^(-1) D^T, axis=0)
    5. Weighted residuals: (total - reconstruction) / sqrt(max(total, 1))
    
    Parameters
    ----------
    total_decay : array_like
        Total fluorescence decay histogram (1D array, one value per TAC bin).
    species_decays : list of array_like
        List of species-specific decay histograms. Each must have the same
        length as total_decay.
    metadata : dict, optional
        Additional metadata to store with the result.
    total_path : str, optional
        Absolute path to the total decay file for project persistence.
    species_patterns : list, optional
        File lists or synthetic source descriptors for each species pattern.
    
    Returns
    -------
    FilterResult
        Result object containing filters, reconstruction, residuals, and metadata.
    """
    # Import here to avoid circular dependencies
    from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters
    
    # Validate inputs
    total = np.asarray(total_decay, dtype=float)
    if total.ndim != 1:
        raise ValueError("total_decay must be a 1D array")
    
    species = [np.asarray(s, dtype=float) for s in species_decays]
    nuisance = [np.asarray(s, dtype=float) for s in (nuisance_decays or [])]
    basis = species + nuisance
    for i, s in enumerate(basis):
        if s.ndim != 1:
            raise ValueError(f"species_decays[{i}] must be a 1D array")
        if s.size != total.size:
            raise ValueError(
                f"species_decays[{i}] has {s.size} bins, "
                f"but total_decay has {total.size} bins"
            )
    
    # Compute filters (calc_ffcs_filters implements the core PAM logic)
    filters, recon, wres = calc_ffcs_filters(total, basis)
    labels = list(nuisance_labels or [])
    if len(labels) != len(nuisance):
        raise ValueError("nuisance_labels must match nuisance_decays")
    nuisance_count = len(nuisance) if reject_nuisance else 0
    
    # Build metadata
    if metadata is None:
        metadata = {}
    
    metadata.update({
        "description": "Filtered FCS lifetime filters computed by ChiSurf",
        "n_species": int(len(species)),
        "n_filters": int(filters.shape[0]),
        "nuisance_labels": labels,
        "reject_nuisance": bool(reject_nuisance),
        "n_bins": int(filters.shape[1]),
    })
    
    return FilterResult(
        filters=filters,
        reconstruction=recon,
        weighted_residuals=wres,
        total_decay=total,
        species_decays=basis,
        metadata=metadata,
        total_path=total_path,
        species_patterns=species_patterns,
        nuisance_count=nuisance_count,
        nuisance_labels=labels,
    )


def load_histogram(path: str | pathlib.Path) -> np.ndarray:
    """Load a 1D decay histogram from a text file."""
    path = pathlib.Path(path)
    data = np.loadtxt(path, ndmin=1)
    if data.ndim != 1:
        data = np.asarray(data).ravel()
    if data.size == 0:
        raise ValueError(f"Histogram file '{path.name}' is empty.")
    return data.astype(float)


def compute_filters_from_files(
    total_path: str | pathlib.Path,
    species_paths: List[str | pathlib.Path],
) -> FilterResult:
    """Compute filters from histogram files."""
    total_path = pathlib.Path(total_path)
    species_path_objects = [pathlib.Path(p) for p in species_paths]
    total = load_histogram(total_path)
    species = [load_histogram(p) for p in species_path_objects]
    metadata = {
        "total_decay_file": str(total_path.absolute()),
        "species_files": [str(p.absolute()) for p in species_path_objects],
    }
    return compute_filters(total, species, metadata=metadata)


def compute_filters_mfd(
    total_decay_par: np.ndarray,
    total_decay_perp: np.ndarray,
    species_decays_par: List[np.ndarray],
    species_decays_perp: List[np.ndarray],
    metadata: Dict[str, Any] | None = None,
    nuisance_decays_par: List[np.ndarray] | None = None,
    nuisance_decays_perp: List[np.ndarray] | None = None,
    nuisance_labels: List[str] | None = None,
    reject_nuisance: bool = True,
) -> FilterResultMFD:
    """Compute fFCS lifetime filters for MFD data."""
    from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters
    
    total_par = np.asarray(total_decay_par, dtype=float)
    total_perp = np.asarray(total_decay_perp, dtype=float)
    
    if total_par.ndim != 1 or total_perp.ndim != 1:
        raise ValueError("total_decay_par and total_decay_perp must be 1D arrays")
    
    if total_par.size != total_perp.size:
        raise ValueError("Parallel and perpendicular decays must have the same size.")
    
    species_par = [np.asarray(s, dtype=float) for s in species_decays_par]
    species_perp = [np.asarray(s, dtype=float) for s in species_decays_perp]
    nuisance_par = [np.asarray(s, dtype=float) for s in (nuisance_decays_par or [])]
    nuisance_perp = [np.asarray(s, dtype=float) for s in (nuisance_decays_perp or [])]
    
    if len(species_par) != len(species_perp):
        raise ValueError("Number of species must match between channels.")
    if len(nuisance_par) != len(nuisance_perp):
        raise ValueError("Number of nuisance patterns must match between channels.")
    labels = list(nuisance_labels or [])
    if len(labels) != len(nuisance_par):
        raise ValueError("nuisance_labels must match nuisance decays")

    basis_par = species_par + nuisance_par
    basis_perp = species_perp + nuisance_perp

    filters_par, recon_par, wres_par = calc_ffcs_filters(total_par, basis_par)
    filters_perp, recon_perp, wres_perp = calc_ffcs_filters(total_perp, basis_perp)
    
    if metadata is None:
        metadata = {}
    
    metadata.update({
        "description": "Filtered FCS MFD lifetime filters computed by ChiSurf",
        "mode": "mfd",
        "n_species": int(len(species_par)),
        "n_filters": int(filters_par.shape[0]),
        "nuisance_labels": labels,
        "reject_nuisance": bool(reject_nuisance),
        "n_bins": int(filters_par.shape[1]),
    })
    
    return FilterResultMFD(
        filters_par=filters_par,
        filters_perp=filters_perp,
        reconstruction_par=recon_par,
        reconstruction_perp=recon_perp,
        weighted_residuals_par=wres_par,
        weighted_residuals_perp=wres_perp,
        total_decay_par=total_par,
        total_decay_perp=total_perp,
        species_decays_par=basis_par,
        species_decays_perp=basis_perp,
        metadata=metadata,
        nuisance_count=(len(nuisance_par) if reject_nuisance else 0),
        nuisance_labels=labels,
    )


def compute_filters_mfd_from_files(
    total_par_path: str | pathlib.Path,
    total_perp_path: str | pathlib.Path,
    species_par_paths: List[str | pathlib.Path],
    species_perp_paths: List[str | pathlib.Path],
) -> FilterResultMFD:
    """Compute MFD filters from histogram files."""
    total_par_path = pathlib.Path(total_par_path)
    total_perp_path = pathlib.Path(total_perp_path)
    total_par = load_histogram(total_par_path)
    total_perp = load_histogram(total_perp_path)
    species_par = [load_histogram(p) for p in [pathlib.Path(p) for p in species_par_paths]]
    species_perp = [load_histogram(p) for p in [pathlib.Path(p) for p in species_perp_paths]]
    
    metadata = {
        "total_decay_par_file": str(total_par_path.absolute()),
        "total_decay_perp_file": str(total_perp_path.absolute()),
    }
    
    return compute_filters_mfd(total_par, total_perp, species_par, species_perp, metadata=metadata)
