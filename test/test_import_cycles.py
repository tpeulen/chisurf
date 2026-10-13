"""Guard: chisurf's modules import each other without cycles, and their top level neither imports
by name nor blocks.

Why this matters: a cross-thread import deadlock (``_DeadlockError: deadlock detected by
_ModuleLock('chisurf.server')``) needs two things at once -- a **cycle** between modules that two
threads first-import from opposite ends, and **top-level code that imports** behind the ``import``
statements' back (``resources.files("chisurf.server")`` in a module body re-imported its own
half-initialised package). :mod:`chisurf._import_gate` closes the class today by serialising every
first import, and :mod:`chisurf.emtk.frame_modules` pre-imports what the frame loop would otherwise
wait for. Both are workarounds; with no cycle and no import-by-side-effect at module level, two
threads can never hold each other's module locks, and both can be deleted. The resume point and
exit criterion are in ``okf/subsystems/qt-retirement.md`` item 5.

**Rule 1 -- no import cycles.** The graph is built statically with :mod:`ast` over ``chisurf/**``
(test directories excluded). An edge ``a -> b`` is a *module-level* ``import b`` /
``from b import x`` in ``a`` (inside ``if``/``try``/``class`` bodies too, which run at import).
Imports inside a function are not edges: they run after the package is loaded. ``if
TYPE_CHECKING:`` and ``if __name__ == "__main__":`` blocks are skipped. ``import a.b.c`` is an edge to ``a.b.c``; ``import a.b.c as d`` also to ``a.b`` (the
binding looks ``b`` up on ``a``, and a package still initialising does not have it yet, so CPython
waits on its lock). ``from pkg import x``
is an edge to ``pkg`` -- CPython takes ``pkg``'s module lock while another thread is still
initialising it -- and to ``pkg.x`` when that is a submodule. Importing ``pkg.sub`` from outside
``pkg`` runs ``pkg/__init__`` first, so it is an edge to ``pkg`` as well; from inside ``pkg`` it is
not (``pkg`` is already in ``sys.modules`` and CPython skips its lock). An edge is *on a cycle* when both ends are
in the same strongly connected component.

**Rule 2 -- no module-level side effect that imports or blocks.** A call at module level (same scope
as rule 1) to ``importlib.import_module``, ``__import__``, ``importlib.reload``,
``importlib.util.find_spec``, ``resources.files`` / ``resources.as_file`` / the old
``read_text``-family, ``pkg_resources``, ``pkgutil.walk_packages`` / ``iter_modules``,
``threading.Thread``, ``.start()`` / ``.join()`` / ``.submit()`` / ``.result()`` / ``.wait()``,
``time.sleep``, ``subprocess``, ``urlopen`` / ``requests`` or ``parse_args``.

Both rules hold with no exceptions (2026-10-13: 17 cyclic components with 56 cycle edges and 11
side effects at the start, 0 and 0 after). Fix a failure at the root -- import the names from the
submodule that defines them (``from pkg.sub import name``, the one spelling that never waits on
``pkg``'s lock), import inside the function that needs it, move the shared definition down into a
leaf module, or invert the dependency. Never add an allow-list: these two rules are what lets the
import gate go (``okf/subsystems/qt-retirement.md`` item 5).

Measure::

    python test/test_import_cycles.py          # counts and the biggest components
"""

from __future__ import annotations

import ast
import functools
import pathlib
from collections import defaultdict

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PKG = _ROOT / "chisurf"

_SKIP_DIRS = {"test", "tests", "__pycache__"}


def _module_files(root: pathlib.Path = _ROOT, package: str = "chisurf") -> dict[str, pathlib.Path]:
    """Map every shipped module's dotted name to its file.

    Parameters
    ----------
    root : pathlib.Path
        Directory holding the top-level package.
    package : str
        Top-level package name.

    Returns
    -------
    dict of str to pathlib.Path
    """
    out = {}
    for path in sorted((root / package).rglob("*.py")):
        rel = path.relative_to(root)
        if _SKIP_DIRS.intersection(rel.parts[:-1]):
            continue
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if not all(p.isidentifier() for p in parts):
            continue
        out[".".join(parts)] = path
    return out


def _is_type_checking(test: ast.expr) -> bool:
    """Whether an ``if`` test is ``TYPE_CHECKING`` (bare or qualified)."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _is_main_guard(test: ast.expr) -> bool:
    """Whether an ``if`` test is ``__name__ == "__main__"``."""
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators)
    )


def _top_level_nodes(body: list[ast.stmt]):
    """Yield every node that runs when the module body runs (not inside a def or lambda).

    Parameters
    ----------
    body : list of ast.stmt
        A module body.

    Yields
    ------
    ast.AST
    """
    stack: list[ast.AST] = list(reversed(body))
    while stack:
        node = stack.pop()
        if isinstance(node, ast.If):
            if _is_type_checking(node.test) or _is_main_guard(node.test):
                stack.extend(reversed(node.orelse))
                continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorators and defaults run at definition time; the body does not.
            yield from (n for d in node.decorator_list for n in ast.walk(d))
            args = node.args
            for d in [*args.defaults, *args.kw_defaults]:
                if d is not None:
                    yield from ast.walk(d)
            continue
        if isinstance(node, ast.Lambda):
            continue
        yield node
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


@functools.cache
def _parse(path: pathlib.Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _resolve(module: str, is_pkg: bool, level: int, target: str | None) -> str:
    """Absolute name of a (possibly relative) import target."""
    if not level:
        return target or ""
    base = module.split(".")
    if not is_pkg:
        base = base[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join(base + ([target] if target else []))


@functools.cache
def _graph() -> dict[str, frozenset[str]]:
    return {m: frozenset(v) for m, v in import_graph().items()}


def import_graph(files: dict[str, pathlib.Path] | None = None) -> dict[str, set[str]]:
    """Return chisurf's module-level import graph, restricted to chisurf modules.

    Parameters
    ----------
    files : dict of str to pathlib.Path, optional
        Modules to analyse (default: all of chisurf).

    Returns
    -------
    dict of str to set of str
        ``module -> modules it imports at module level``.
    """
    files = _module_files() if files is None else files
    known = set(files)
    graph: dict[str, set[str]] = {m: set() for m in files}
    for mod, path in files.items():
        tree = _parse(path)
        if tree is None:
            continue
        is_pkg = path.name == "__init__.py"
        for node in _top_level_nodes(tree.body):
            targets = []
            if isinstance(node, ast.Import):
                for a in node.names:
                    targets.append(a.name)
                    if a.asname:
                        # ``import a.b.c as d`` binds through attribute lookups; a package still
                        # initialising has no attribute for its child yet, so CPython falls back
                        # to ``PyImport_GetModule``, which waits on that package's lock.
                        parts = a.name.split(".")
                        targets.extend(".".join(parts[:i]) for i in range(2, len(parts)))
            elif isinstance(node, ast.ImportFrom):
                base = _resolve(mod, is_pkg, node.level, node.module)
                # ``from pkg import x`` imports ``pkg`` itself (and waits on its lock while another
                # thread is still initialising it), then ``pkg.x`` when that is a submodule.
                targets.append(base)
                for a in node.names:
                    sub = f"{base}.{a.name}"
                    if sub in known:
                        targets.append(sub)
            for t in targets:
                # ``import a.b.c`` of a name that is not a module: walk up to the module it names.
                while t and t not in known and "." in t:
                    t = t.rsplit(".", 1)[0]
                if t in known and t != mod:
                    graph[mod].add(t)
                # Importing ``pkg.sub`` runs ``pkg/__init__`` first unless the importer is inside
                # ``pkg`` (then ``pkg`` is already being imported): that is an edge too.
                parent = t.rsplit(".", 1)[0] if "." in t else ""
                while parent and not (mod == parent or mod.startswith(parent + ".")):
                    if parent in known:
                        graph[mod].add(parent)
                    parent = parent.rsplit(".", 1)[0] if "." in parent else ""
    return graph


def _sccs(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components of size > 1 (iterative Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter(sorted(graph[root])))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(graph[w]))))
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == v:
                            break
                    if len(comp) > 1:
                        out.append(sorted(comp))
    return out


def cycle_edges(graph: dict | None = None) -> set[str]:
    """Every import edge that lies on a cycle, as ``"a -> b"``.

    Returns
    -------
    set of str
    """
    graph = _graph() if graph is None else graph
    comp_of = {}
    for i, comp in enumerate(_sccs(graph)):
        for m in comp:
            comp_of[m] = i
    return {
        f"{a} -> {b}"
        for a, bs in graph.items()
        for b in bs
        if a in comp_of and comp_of.get(b) == comp_of[a]
    }


#: Calls whose dotted name ends like this import (or read a package's files, which imports it).
_IMPORTING_CALLS = (
    "importlib.import_module",
    "import_module",
    "__import__",
    "importlib.reload",
    "find_spec",
    "resources.files",
    "resources.as_file",
    "resources.read_text",
    "resources.read_binary",
    "resources.open_text",
    "resources.open_binary",
    "resources.path",
    "resources.contents",
    "importlib_resources.files",
    "pkg_resources.resource_filename",
    "pkg_resources.resource_string",
    "pkg_resources.resource_stream",
    "pkg_resources.require",
    "pkgutil.walk_packages",
    "pkgutil.iter_modules",
    "walk_packages",
)
#: Calls that start or wait for another thread or process. Making an executor is not one: it
#: starts no thread until something is submitted (and ``.submit`` is caught below).
_BLOCKING_CALLS = (
    "threading.Thread",
    "Thread",
    "time.sleep",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
    # Network and the command line: a module body that waits on a server or reads ``sys.argv``
    # is a script missing its ``if __name__ == "__main__":``.
    "urlopen",
    "requests.get",
    "requests.post",
    "parse_args",
)
#: Method calls that start or wait (on anything; a module body has no business doing either).
_BLOCKING_METHODS = ("start", "join", "submit", "result", "wait")


def _dotted(node: ast.expr) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append(_dotted(node.func) + "()")
    else:
        return ""
    return ".".join(reversed(parts))


def _matches(name: str, patterns: tuple[str, ...]) -> str | None:
    for p in patterns:
        if name == p or name.endswith("." + p):
            return p
    return None


@functools.cache
def side_effects() -> frozenset[str]:
    """Every module-level call that imports or blocks, as ``"path: call"``.

    Returns
    -------
    frozenset of str
    """
    found = set()
    for _mod, path in _module_files().items():
        tree = _parse(path)
        if tree is None:
            continue
        rel = path.relative_to(_ROOT).as_posix()
        for node in _top_level_nodes(tree.body):
            if not isinstance(node, ast.Call):
                continue
            name = _dotted(node.func)
            hit = _matches(name, _IMPORTING_CALLS) or _matches(name, _BLOCKING_CALLS)
            if hit is None and isinstance(node.func, ast.Attribute):
                # ``t.start()`` / ``t.join()`` / ``t.join(5)``; not ``", ".join(x)`` nor
                # ``os.path.join(a, b)``, which take the parts as arguments.
                waits = (
                    node.func.attr == "submit"
                    or not node.args
                    or (
                        len(node.args) == 1
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, (int, float))
                    )
                )
                if node.func.attr in _BLOCKING_METHODS and waits:
                    hit = "." + node.func.attr + "()"
            if hit is not None:
                found.add(f"{rel}: {hit}")
    return frozenset(found)


def test_no_import_cycles():
    """No module-level import edge lies on a cycle."""
    edges = sorted(cycle_edges())
    assert not edges, (
        "These module-level imports close an import cycle, which two threads can deadlock on. "
        "Import the names from the submodule that defines them (`from pkg.sub import name`), "
        "import inside the function that needs it, or move the shared definition into a leaf "
        "module:\n  " + "\n  ".join(edges)
    )


def test_no_module_level_import_side_effects():
    """No module body imports by name, reads package resources, starts or waits for a thread."""
    hits = sorted(side_effects())
    assert not hits, (
        "Module-level code must not import by name or block: move the call into the function that "
        "needs it (a resource path can be built from __file__; a script needs "
        '`if __name__ == "__main__":`):\n  ' + "\n  ".join(hits)
    )


#: ``top/pkg/a.py`` bodies; ``top/pkg/__init__`` imports ``a``, ``top/pkg/sib.py`` defines ``X``
#: (``top`` stands for ``chisurf``, which is loaded before anything else). Whether CPython waits
#: on ``top.pkg``'s lock while ``a`` runs decides whether ``a -> top.pkg`` is an edge.
_SPELLINGS = {
    "from . import sib": True,
    "from top.pkg import sib": True,
    "import top.pkg.sib as s": True,
    "import top.pkg.sib": False,
    "from .sib import X": False,
    "from top.pkg.sib import X": False,
}

_PROBE = """
import _frozen_importlib as B, sys
sys.path.insert(0, sys.argv[1])
asked = []
original = B._find_and_load, B._lock_unlock_module

def initialising():
    m = sys.modules.get("top.pkg")
    return m is not None and getattr(getattr(m, "__spec__", None), "_initializing", False)

def from_a():
    f = sys._getframe(2)
    while f is not None:
        if f.f_code.co_filename.endswith("a.py"):
            return True
        f = f.f_back
    return False

def find_and_load(name, import_):
    if name == "top.pkg" and initialising() and from_a():
        asked.append(name)
    return original[0](name, import_)

def lock_unlock(name):
    if name == "top.pkg" and initialising() and from_a():
        asked.append(name)
    return original[1](name)

import top
B._find_and_load, B._lock_unlock_module = find_and_load, lock_unlock
import top.pkg
print(bool(asked))
"""


def test_the_graph_model_matches_cpythons_module_locks(tmp_path):
    """Each import spelling is an edge to its package exactly when CPython waits on that lock.

    The guard is only as good as this model: ``import top.pkg.sib as s`` *looks* lock-free and is
    not (3.12 binds it through ``PyImport_GetModule``, which waits on a package still
    initialising), while ``from top.pkg.sib import X`` never waits on ``top.pkg``. A new CPython that changes either
    shows up here.
    """
    import subprocess
    import sys

    for i, (spelling, waits) in enumerate(_SPELLINGS.items()):
        root = tmp_path / f"case{i}"
        pkg = root / "top" / "pkg"
        pkg.mkdir(parents=True)
        (root / "top" / "__init__.py").write_text("")
        (pkg / "__init__.py").write_text("from . import a\n")
        (pkg / "sib.py").write_text("X = 1\n")
        (pkg / "a.py").write_text(spelling + "\n")
        graph = import_graph(_module_files(root, "top"))
        assert ("top.pkg" in graph["top.pkg.a"]) is waits, spelling
        out = subprocess.run(
            [sys.executable, "-I", "-c", _PROBE, str(root)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert out == str(waits), f"{spelling}: CPython waits on top.pkg: {out}"


def test_graph_sees_a_known_edge():
    """The graph builder is not silently empty: chisurf.emtk.session imports chisurf.core.api."""
    graph = _graph()
    assert len(graph) > 1000
    assert "chisurf.core.api" in graph["chisurf.emtk.session"]


def _report() -> None:
    graph = import_graph()
    comps = _sccs(graph)
    edges = cycle_edges(graph)
    print(f"modules: {len(graph)}, edges: {sum(map(len, graph.values()))}")
    print(
        f"cyclic components: {len(comps)}, modules on a cycle: {sum(map(len, comps))}, "
        f"cycle edges: {len(edges)}"
    )
    for comp in sorted(comps, key=len, reverse=True)[:15]:
        print(f"  {len(comp):4d}  {', '.join(comp[:6])}{' ...' if len(comp) > 6 else ''}")
    effects = side_effects()
    print(f"module-level side effects: {len(effects)}")
    by_kind = defaultdict(int)
    for e in effects:
        by_kind[e.split(": ", 1)[1]] += 1
    for k, v in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")


if __name__ == "__main__":
    _report()
