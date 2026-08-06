"""Atomic masses in daltons. **Generated -- do not edit by hand.**

Transcribed from PyMOL's ``modules/chempy/__init__.py::atomic_mass`` by
``analysis/make_elements.py``. PyMOL's values are the IUPAC standard atomic
weights, and taking them rather than an independent list is deliberate: a
molecular weight that disagrees with PyMOL's by a rounding convention is a
support question nobody can answer.

Lookup is **case-insensitive**, because a PDB element column is written both
``Fe`` and ``FE`` and a table that knows only one of them silently drops every
metal in half the files in the world.
"""

from __future__ import annotations

__all__ = ["ATOMIC_MASS", "mass_of", "masses_for"]


ATOMIC_MASS: dict[str, float] = {
    "B": 10.811,
    "C": 12.0107,
    "F": 18.9984032,
    "H": 1.00794,
    "I": 126.90447,
    "K": 39.0983,
    "N": 14.0067,
    "O": 15.9994,
    "P": 30.973761,
    "S": 32.065,
    "U": 238.02891,
    "V": 50.9415,
    "W": 183.84,
    "Y": 88.90585,
    "AC": 227.03,
    "AG": 107.8682,
    "AL": 26.981538,
    "AM": 243.06,
    "AR": 39.948,
    "AS": 74.9216,
    "AT": 209.99,
    "AU": 196.96655,
    "BA": 137.327,
    "BE": 9.012182,
    "BH": 264.12,
    "BI": 208.98038,
    "BK": 247.07,
    "BR": 79.904,
    "CA": 40.078,
    "CD": 112.411,
    "CE": 140.116,
    "CF": 251.08,
    "CL": 35.453,
    "CM": 247.07,
    "CO": 58.9332,
    "CR": 51.9961,
    "CS": 132.90545,
    "CU": 63.546,
    "DB": 262.11,
    "DY": 162.5,
    "ER": 167.259,
    "ES": 252.08,
    "EU": 151.964,
    "FE": 55.845,
    "FM": 257.1,
    "FR": 223.02,
    "GA": 69.723,
    "GD": 157.25,
    "GE": 72.64,
    "HE": 4.002602,
    "HF": 178.49,
    "HG": 200.59,
    "HO": 164.93032,
    "HS": 269.13,
    "IN": 114.818,
    "IR": 192.217,
    "KR": 83.8,
    "LA": 138.9055,
    "LI": 6.941,
    "LR": 262.11,
    "LU": 174.967,
    "MD": 258.1,
    "MG": 24.305,
    "MN": 54.938049,
    "MO": 95.94,
    "MT": 268.14,
    "NA": 22.98977,
    "NB": 92.90638,
    "ND": 144.24,
    "NE": 20.1797,
    "NI": 58.6934,
    "NO": 259.1,
    "NP": 237.05,
    "OS": 190.23,
    "PA": 231.03588,
    "PB": 207.2,
    "PD": 106.42,
    "PM": 145.0,
    "PO": 208.98,
    "PR": 140.90765,
    "PT": 195.078,
    "PU": 244.06,
    "RA": 226.03,
    "RB": 85.4678,
    "RE": 186.207,
    "RF": 261.11,
    "RH": 102.9055,
    "RN": 222.02,
    "RU": 101.07,
    "SB": 121.76,
    "SC": 44.95591,
    "SE": 78.96,
    "SG": 266.12,
    "SI": 28.0855,
    "SM": 150.36,
    "SN": 118.71,
    "SR": 87.62,
    "TA": 180.9479,
    "TB": 158.92534,
    "TC": 98.0,
    "TE": 127.6,
    "TH": 232.0381,
    "TI": 47.867,
    "TL": 204.3833,
    "TM": 168.93421,
    "XE": 131.293,
    "YB": 173.04,
    "ZN": 65.39,
    "ZR": 91.224,
}


def mass_of(symbol: str) -> float | None:
    """Mass of one element in daltons, or ``None`` when it is not a symbol.

    Parameters
    ----------
    symbol : str
        Element symbol in any case, with or without surrounding blanks.

    Returns
    -------
    float or None
        ``None`` rather than a guess: an unknown symbol in a molecular weight
        has to be *reported*, not quietly counted as zero or as carbon.
    """
    return ATOMIC_MASS.get(str(symbol).strip().upper())


def masses_for(symbols) -> tuple["numpy.ndarray", int]:  # noqa: F821
    """Masses for a sequence of symbols, and how many were not recognised.

    Returns
    -------
    tuple
        ``(masses, unknown)``. Unknown symbols get ``0.0`` so array arithmetic
        still works, and the count is returned so the caller can say so --
        which is the whole point of not defaulting them to something plausible.
    """
    import numpy as np

    values = np.zeros(len(symbols), dtype=float)
    unknown = 0
    for index, symbol in enumerate(symbols):
        mass = mass_of(symbol)
        if mass is None:
            unknown += 1
        else:
            values[index] = mass
    return values, unknown

