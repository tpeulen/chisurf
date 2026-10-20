"""Reserve application shortcuts while letting shifted game keys through."""

from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER


def blocked(modifiers: int) -> bool:
    """Return whether a key belongs to an application shortcut."""
    return bool(modifiers & (CONTROL_MODIFIER | ALT_MODIFIER | META_MODIFIER))
