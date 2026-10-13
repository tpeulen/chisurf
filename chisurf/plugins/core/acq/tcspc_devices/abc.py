"""
Abstract Base Class for TCSPC Device Wrappers

This module defines the common interface that all TCSPC device wrappers must implement.
"""

from abc import abstractmethod
from collections.abc import Callable


class _BoundSignal:
    """One instance's signal: ``connect`` callbacks, ``emit`` calls them in the emitting thread."""

    def __init__(self) -> None:
        self._slots: list[Callable] = []

    def connect(self, slot: Callable) -> None:
        """Register *slot*; it is called with the emitted arguments."""
        self._slots.append(slot)

    def disconnect(self, slot: Callable | None = None) -> None:
        """Remove *slot*, or every slot when none is given."""
        if slot is None:
            self._slots.clear()
        elif slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args) -> None:
        """Call every connected slot with *args*."""
        for slot in list(self._slots):
            slot(*args)


class Signal:
    """Qt-free signal descriptor with the ``connect`` / ``emit`` surface of a Qt signal.

    Parameters
    ----------
    *types : type
        Accepted for spelling parity with a Qt signal; not enforced.
    """

    def __init__(self, *types: type) -> None:
        self._name = ""

    def __set_name__(self, owner: type, name: str) -> None:
        """Remember the attribute name the per-instance signal is stored under."""
        self._name = "_signal_" + name

    def __get__(self, instance, owner=None):
        """Return the instance's own signal (created on first access)."""
        if instance is None:
            return self
        bound = instance.__dict__.get(self._name)
        if bound is None:
            bound = instance.__dict__[self._name] = _BoundSignal()
        return bound


class TCSPCDeviceABC:
    """Abstract Base Class for TCSPC device wrappers."""

    # Signal emitted when a message is logged
    message_logged = Signal(str)

    @abstractmethod
    def log_message(self, message):
        """Log a message and emit the message_logged signal."""
        pass

    @abstractmethod
    def detect_cards(self, simulation=False):
        """Detect available TCSPC cards/devices."""
        pass

    @abstractmethod
    def set_active_cards(self, card_numbers):
        """Set the active cards/devices."""
        pass

    @abstractmethod
    def get_active_cards(self):
        """Get the active cards/devices."""
        pass

    @abstractmethod
    def initialize(self, simulation=True):
        """Initialize the TCSPC device."""
        pass

    @abstractmethod
    def start_measurement(self):
        """Start measurement."""
        pass

    @abstractmethod
    def stop_measurement(self):
        """Stop measurement."""
        pass

    @abstractmethod
    def read_fifo(self, max_words=32768):
        """Read data from FIFO."""
        pass

    @abstractmethod
    def get_fifo_usage(self):
        """Get FIFO usage."""
        pass

    @abstractmethod
    def close(self):
        """Close the device."""
        pass
