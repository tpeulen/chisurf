"""PDBx/mmCIF metadata key suggestions for the GUI metadata editors.

The keys and their descriptions come from the bundled mmCIF dictionaries parsed
by :class:`mmfdb.schema.pdbx_metadata.MmcifDictionary` — the single dictionary
authority. This module is only the small chisurf-side facade that the metadata
editor and the burst-selection export dialog use to seed their completers.
"""

from __future__ import annotations

import logging

from mmfdb.schema.pdbx_metadata import MmcifDictionary

logger = logging.getLogger(__name__)

_cache_keys: list[str] | None = None
_cache_descriptions: dict[str, str] | None = None


def _load() -> None:
    """Fill the module caches from the bundled dictionaries.

    Parsing is done once per process by ``MmcifDictionary.load_bundled()``; an
    empty result means the shipped dictionaries are missing, which silently
    empties every metadata completer, so it is logged rather than swallowed.
    """
    global _cache_keys, _cache_descriptions
    dictionary = MmcifDictionary.load_bundled()
    _cache_keys = dictionary.item_names()
    _cache_descriptions = dictionary.item_descriptions()
    if not _cache_keys:
        logger.warning(
            "The bundled mmCIF dictionaries yielded no metadata keys; the metadata "
            "editors will offer no key completions."
        )


def get_pdbx_metadata_keys() -> list[str]:
    """Return the ``_category.attribute`` keys of the bundled dictionaries.

    Returns
    -------
    list of str
        Sorted item names. Cached after the first call.
    """
    if _cache_keys is None:
        _load()
    return list(_cache_keys)


def get_pdbx_metadata_descriptions() -> dict[str, str]:
    """Return the dictionary descriptions of the metadata keys.

    Returns
    -------
    dict
        Key -> description text, for the keys that define one. Cached after the
        first call.
    """
    if _cache_descriptions is None:
        _load()
    return dict(_cache_descriptions)
