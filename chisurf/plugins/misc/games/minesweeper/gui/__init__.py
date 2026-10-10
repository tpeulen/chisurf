"""Qt interface for Minesweeper."""


def __getattr__(name):
    """Keep legacy widget imports lazy so native factories never import Qt."""
    if name == "MinesweeperWidget":
        from .tool import MinesweeperWidget

        return MinesweeperWidget
    raise AttributeError(name)


__all__ = ["MinesweeperWidget"]
