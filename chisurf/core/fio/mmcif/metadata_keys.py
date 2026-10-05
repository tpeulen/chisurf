"""The metadata key catalogue: common fluorescence keys plus the mmCIF/PDBx ones (Qt-free).

What a key/value metadata editor offers as keys, and the one-line description of
each. Used by the Qt :class:`~chisurf.gui.widgets.metadata_editor.MetadataEditor`
and by the native emtk editors (MMFDB Admin's Sample Metadata).
"""

from __future__ import annotations

# Called through the module, so a test (or a host) that swaps the dictionary
# loader before the first use is honoured.
from chisurf.core.fio.mmcif import pdbx_metadata

COMMON_METADATA_KEYS = [
    "pH",
    "temperature",
    "ionic_strength",
    "buffer_composition",
    "solvent_phase",
    "labeling_efficiency",
    "donor_only_fraction",
    "acceptor_only_fraction",
    "dye_ratio",
    "quencher_concentration",
    "time_resolution",
    "excitation_wavelength",
    "emission_wavelength",
    "power",
    "temperature_control",
    "data_notes",
    "_exptl_crystal_grow.ph",
    "_exptl_crystal_grow.temp",
    "_exptl_crystal_grow.method",
    "_exptl_crystal_grow.comp_details",
    "_diffrn_radiation_wavelength.wavelength",
    "_diffrn_radiation.monochromator",
    "_diffrn_detector.detector",
    "_diffrn_detector.type",
    "_diffrn_standards.number",
    "_diffrn_standards.interval_count",
    "pdbx.sample_type",
    "pdbihm.entry_id",
    "flrcif.sample_class",
    "flrcif.experiment_type",
    "flrcif.data_type",
]

_ALL_KEYS: list[str] | None = None


def all_metadata_keys() -> list[str]:
    """Every key: the common ones first, then the PDBx dictionary's (loaded once)."""
    global _ALL_KEYS
    if _ALL_KEYS is None:
        try:
            pdbx_keys = pdbx_metadata.get_pdbx_metadata_keys()
        except Exception:
            pdbx_keys = []
        _ALL_KEYS = COMMON_METADATA_KEYS + [k for k in pdbx_keys if k not in COMMON_METADATA_KEYS]
    return _ALL_KEYS


_PDBX_DESCRIPTIONS: dict[str, str] | None = None

_COMMON_DESCRIPTIONS: dict[str, str] = {
    "pH": "Solution pH",
    "temperature": "Temperature in Kelvin",
    "ionic_strength": "Ionic strength (mM or M)",
    "buffer_composition": "Buffer composition and concentration",
    "solvent_phase": "Solvent phase (liquid, solid, gas)",
    "labeling_efficiency": "Fraction of labeled molecules",
    "donor_only_fraction": "Fraction of donor-only molecules",
    "acceptor_only_fraction": "Fraction of acceptor-only molecules",
    "dye_ratio": "Dye stoichiometry ratio",
    "quencher_concentration": "Quencher concentration",
    "time_resolution": "Time resolution of the measurement",
    "excitation_wavelength": "Excitation wavelength in nm",
    "emission_wavelength": "Emission wavelength in nm",
    "power": "Excitation power",
    "temperature_control": "Temperature control method",
    "data_notes": "Free-form data notes",
    "pdbx.sample_type": "PDBx sample type",
    "pdbihm.entry_id": "PDB-IHM entry identifier",
    "flrcif.sample_class": "FLR-CIF sample class",
    "flrcif.experiment_type": "FLR-CIF experiment type",
    "flrcif.data_type": "FLR-CIF data type",
}


def key_description(key: str) -> str:
    """One-line description of *key* (common keys first, then the PDBx dictionary)."""
    global _PDBX_DESCRIPTIONS
    desc = _COMMON_DESCRIPTIONS.get(key)
    if desc:
        return desc
    if _PDBX_DESCRIPTIONS is None:
        try:
            _PDBX_DESCRIPTIONS = pdbx_metadata.get_pdbx_metadata_descriptions()
        except Exception:
            _PDBX_DESCRIPTIONS = {}
    return _PDBX_DESCRIPTIONS.get(key, "")
