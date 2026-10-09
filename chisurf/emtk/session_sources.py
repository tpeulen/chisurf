"""Explicit in-process native source discovery without toolkit window scanning.

ndX sources expose get_burst_columns() and apply_fret_calibration(calibration),
or their existing data_source/constants bridge. Register when a native source
opens and unregister on close. Weak references prevent a closed tool surviving
solely because another plugin can discover it.
"""

import weakref

_sources = {}


def register_source(kind, source):
    kind = str(kind)
    refs = _sources.setdefault(kind, [])
    if not any(reference() is source for reference in refs):
        refs.append(weakref.ref(source))
    return source


def unregister_source(kind, source):
    kind = str(kind)
    _sources[kind] = [
        reference
        for reference in _sources.get(kind, [])
        if reference() is not None and reference() is not source
    ]


def sources(kind):
    live = [reference for reference in _sources.get(str(kind), []) if reference() is not None]
    _sources[str(kind)] = live
    return [reference() for reference in live]
