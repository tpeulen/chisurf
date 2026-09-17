# classic_editor first: fret_structure's class body calls
# chisurf.core.models.description.for_family(), which (depending on the
# family's layout) imports chisurf.core.models.tcspc.classic_editor -- while
# this package's own __init__ is still on its first line. Importing
# classic_editor here first means it is already in sys.modules by the time
# that recursive call needs it, instead of racing this package's own
# not-yet-finished initialization (real failure: "ModuleNotFoundError: No
# module named 'chisurf.core.models.tcspc.classic_editor'", not because the
# file is missing, but because the circular re-entry couldn't resolve it).
import chisurf.core.models.tcspc.classic_editor
import chisurf.core.models.tcspc.fret_structure
