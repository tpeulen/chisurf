"""FRET-line GUI entrypoints resolved lazily for native runtimes."""

def __getattr__(attribute):
    if attribute == 'FRETLineTool':
        from .tool import FRETLineTool
        return FRETLineTool
    raise AttributeError(attribute)
