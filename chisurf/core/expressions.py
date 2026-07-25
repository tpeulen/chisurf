"""Safe, policy-driven arithmetic expression engine.

A small AST-whitelist evaluator for *user-entered* expressions — the kind typed
into an equation editor, a derived-column formula, or an analytical parameter
relation. It exists because the ad-hoc alternatives scattered through the code
base (``eval`` under ``from numpy import *``, a ``re.Scanner`` tokeniser) run
arbitrary Python and give no structured feedback.

The engine does three things, all governed by an :class:`ExpressionPolicy`:

1. **Parse + whitelist.** The expression is parsed to a Python AST; only a fixed
   set of node types survives (arithmetic, optional comparisons/bit-ops, calls
   to whitelisted functions). Attribute access, comprehensions, lambdas,
   subscripts, keyword arguments, dunder access — none can appear, so nothing
   but the allowed maths can ever run.
2. **Resolve references.** Names in the expression become *references* to a
   caller-supplied symbol table. Two reference styles are supported and toggled
   by the policy: **quoted** names (``'Green Count Rate'`` — a string literal,
   so names may contain spaces) and **bare** identifiers (``tau`` — a normal
   Python name). Matching is optionally case-insensitive and optionally on the
   part of a name left of a ``|`` (column-header ``"Name | unit"`` convention).
   A caller symbol always wins over a named constant of the same name: a column
   called ``e`` is that column, not Euler's number, and the constant is only the
   fallback when no such symbol exists.
3. **Evaluate on scalars or NumPy arrays.** References resolve to their values
   once and the compiled code runs against them.

The public surface is :func:`validate_expression` (for GUI ✓/✗ feedback),
:func:`compile_expression`, and :func:`evaluate_expression`. :data:`DEFAULT_POLICY`
is a rich, Python-like policy (bare names, full maths library); :data:`NDX_POLICY`
mirrors the ndXplorer burst-column convention (quoted names, arithmetic + ``abs``,
case-insensitive, left-of-``|`` matching).
"""

from __future__ import annotations

import ast
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

__all__ = [
    "ExpressionError",
    "ExpressionPolicy",
    "CompiledExpression",
    "ValidationResult",
    "DEFAULT_FUNCTIONS",
    "DEFAULT_CONSTANTS",
    "DEFAULT_POLICY",
    "NDX_POLICY",
    "PARSE_MODEL_POLICY",
    "compile_expression",
    "validate_expression",
    "evaluate_expression",
    "discover_parameters",
    "resolve_name",
    "function_signatures",
]


class ExpressionError(ValueError):
    """Raised when an expression violates the policy (bad node, unknown call)."""


# -- default symbol libraries ---------------------------------------------------

#: Element-wise NumPy functions offered by :data:`DEFAULT_POLICY`. Everything is
#: array-safe (ufuncs or ufunc-like), so the same expression works on a scalar or
#: a whole column.
DEFAULT_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": np.abs,
    "sqrt": np.sqrt,
    "cbrt": np.cbrt,
    "square": np.square,
    "exp": np.exp,
    "expm1": np.expm1,
    "log": np.log,
    "log2": np.log2,
    "log10": np.log10,
    "log1p": np.log1p,
    "power": np.power,
    "hypot": np.hypot,
    "sign": np.sign,
    "mod": np.mod,
    "fmod": np.fmod,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "arcsin": np.arcsin,
    "arccos": np.arccos,
    "arctan": np.arctan,
    "arctan2": np.arctan2,
    "sinh": np.sinh,
    "cosh": np.cosh,
    "tanh": np.tanh,
    "deg2rad": np.deg2rad,
    "rad2deg": np.rad2deg,
    "floor": np.floor,
    "ceil": np.ceil,
    "trunc": np.trunc,
    "round": np.round,
    "clip": np.clip,
    "where": np.where,
    "minimum": np.minimum,
    "maximum": np.maximum,
    "heaviside": np.heaviside,
    "nan_to_num": np.nan_to_num,
    "sinc": np.sinc,
    "erf": getattr(np, "erf", None),  # numpy>=2 has no erf; filtered below
}
# Drop any names numpy does not actually provide on this build.
DEFAULT_FUNCTIONS = {k: v for k, v in DEFAULT_FUNCTIONS.items() if v is not None}

#: Named numeric constants offered by :data:`DEFAULT_POLICY`. Deliberately does
#: *not* include ``tau`` — ``tau`` is the near-universal name for a fluorescence
#: lifetime parameter, and binding it to 2π would silently corrupt parse-model
#: formulas. Write ``2*pi`` for the circle constant.
DEFAULT_CONSTANTS: dict[str, float] = {
    "pi": float(np.pi),
    "e": float(np.e),
    "inf": float(np.inf),
    "nan": float(np.nan),
}


@dataclass(frozen=True)
class ExpressionPolicy:
    """What an expression is allowed to contain and how names resolve.

    Parameters
    ----------
    functions
        Mapping of allowed function name to a callable. A call to any other name
        is rejected at parse time.
    constants
        Named numeric constants (``pi``, ``e``, …) that resolve to a fixed value
        when the caller's symbol table has no symbol of that name. A symbol
        always shadows the constant, so a data column called ``e`` is reachable.
    quoted_names
        Allow string literals (``'name'``) as references. Enables names that are
        not valid Python identifiers (spaces, punctuation).
    bare_names
        Allow bare identifiers (``tau``) that are neither a function nor a
        constant to be references.
    case_insensitive
        Match references to symbol names ignoring case.
    split_on_pipe
        Also match a reference against the part of a symbol name left of the
        first ``|`` (the ``"Name | unit"`` column-header convention).
    allow_comparisons
        Permit comparison operators (``< <= > >= == !=``) — useful inside
        ``where(cond, a, b)``.
    allow_bitops
        Permit element-wise boolean combination (``& | ~ ^``) of comparison
        results, and integer bit operations.
    """

    functions: Mapping[str, Callable[..., Any]] = field(default_factory=dict)
    constants: Mapping[str, float] = field(default_factory=dict)
    quoted_names: bool = True
    bare_names: bool = True
    case_insensitive: bool = False
    split_on_pipe: bool = False
    allow_comparisons: bool = True
    allow_bitops: bool = True

    def with_functions(self, functions: Mapping[str, Callable[..., Any]]) -> ExpressionPolicy:
        """Return a copy of this policy with a different function table."""
        return replace(self, functions=dict(functions))


#: Rich, Python-like default: bare identifiers, the full maths library, and
#: comparison/bit operators. Case-sensitive.
DEFAULT_POLICY = ExpressionPolicy(
    functions=DEFAULT_FUNCTIONS,
    constants=DEFAULT_CONSTANTS,
    quoted_names=True,
    bare_names=True,
    case_insensitive=False,
    split_on_pipe=False,
    allow_comparisons=True,
    allow_bitops=True,
)

#: ndXplorer burst-column convention: quoted references only, arithmetic +
#: ``abs`` (matching ``ndxplorer.core.equation_graph``), case-insensitive, and
#: left-of-``|`` matching. No comparisons/bit-ops.
NDX_POLICY = ExpressionPolicy(
    functions={"abs": np.abs},
    constants={},
    quoted_names=True,
    bare_names=False,
    case_insensitive=True,
    split_on_pipe=True,
    allow_comparisons=False,
    allow_bitops=False,
)

#: Parse-model convention (`ParseModel`, TCSPC/FCS/PCF formula catalogues): a
#: single ``y = f(x, …)`` expression in bare identifiers over the rich maths
#: library, where any name that is not the independent variable, a function or a
#: constant is a **free fitting parameter**. Callers validate with
#: ``allow_unknown=True`` (unknown names are parameters, not errors) and read the
#: parameters back with :func:`discover_parameters`.
PARSE_MODEL_POLICY = ExpressionPolicy(
    functions=DEFAULT_FUNCTIONS,
    constants=DEFAULT_CONSTANTS,
    quoted_names=False,
    bare_names=True,
    case_insensitive=False,
    split_on_pipe=False,
    allow_comparisons=True,
    allow_bitops=True,
)


# -- node whitelist -------------------------------------------------------------

# Always-allowed structural / arithmetic nodes.
_BASE_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
)
_COMPARISON_NODES: tuple[type, ...] = (
    ast.Compare,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
)
_BITOP_NODES: tuple[type, ...] = (
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
    ast.Invert,
)


def _allowed_nodes(policy: ExpressionPolicy) -> tuple[type, ...]:
    nodes = _BASE_NODES
    if policy.allow_comparisons:
        nodes = nodes + _COMPARISON_NODES
    if policy.allow_bitops:
        nodes = nodes + _BITOP_NODES
    return nodes


def _normalize_left(name: str) -> str:
    """Return the part of a name before the first ``|``, stripped."""
    return str(name).split("|", 1)[0].strip()


class _RefRewriter(ast.NodeTransformer):
    """Rewrite reference names to ``_r{i}`` variables, collecting their originals.

    Quoted string literals and (optionally) bare identifiers become numbered
    ``_r{i}`` variables; a named constant becomes a ``_c{j}`` variable so that a
    caller symbol of the same name can shadow it at evaluation time. Function
    names are left in place. A call to a non-whitelisted function raises
    :class:`ExpressionError`.
    """

    def __init__(self, policy: ExpressionPolicy) -> None:
        self.policy = policy
        self.refs: list[str] = []
        self.constants: list[str] = []

    def _add_ref(self, name: str, node: ast.AST) -> ast.AST:
        idx = len(self.refs)
        self.refs.append(name)
        return ast.copy_location(ast.Name(id=f"_r{idx}", ctx=ast.Load()), node)

    def _add_constant(self, name: str, node: ast.AST) -> ast.AST:
        """Bind a named constant to a ``_c{j}`` slot filled at evaluation time."""
        if name in self.constants:
            idx = self.constants.index(name)
        else:
            idx = len(self.constants)
            self.constants.append(name)
        return ast.copy_location(ast.Name(id=f"_c{idx}", ctx=ast.Load()), node)

    def visit_Constant(self, node: ast.Constant):  # noqa: N802 (ast naming)
        if isinstance(node.value, str):
            if not self.policy.quoted_names:
                raise ExpressionError("quoted names are not allowed here")
            return self._add_ref(node.value, node)
        return node

    def visit_Name(self, node: ast.Name):  # noqa: N802
        name = node.id
        if name in self.policy.functions:
            return node  # a whitelisted function — leave as-is
        if name in self.policy.constants:
            return self._add_constant(name, node)  # shadowable by a caller symbol
        if not self.policy.bare_names:
            raise ExpressionError(f"unknown name: {name!r} (quote it as '{name}'?)")
        return self._add_ref(name, node)

    def visit_Call(self, node: ast.Call):  # noqa: N802
        fn = node.func.id if isinstance(node.func, ast.Name) else None
        if fn is None or fn not in self.policy.functions:
            raise ExpressionError(f"unknown function: {fn!r}")
        if node.keywords:
            raise ExpressionError("keyword arguments are not allowed")
        node.args = [self.visit(a) for a in node.args]  # func name left untouched
        return node


@dataclass(frozen=True)
class CompiledExpression:
    """A parsed, whitelisted expression ready to evaluate.

    Attributes
    ----------
    source
        The original expression text.
    code
        The compiled code object (evaluated with ``_r{i}`` reference variables
        and ``_c{j}`` constant variables plus the policy's functions in scope).
    refs
        The ordered original reference names; index ``i`` maps to ``_r{i}``.
    constants
        The ordered named constants the expression uses; index ``j`` maps to
        ``_c{j}``. Each resolves to the caller's symbol of that name when there
        is one and to the policy's constant value otherwise.
    """

    source: str
    code: Any
    refs: tuple[str, ...]
    constants: tuple[str, ...] = ()


# expr text + policy identity -> compiled result. Parsing/compiling is the
# expensive step and depends only on the text and the policy's rules.
_CACHE: dict[tuple[str, int], CompiledExpression] = {}
_CACHE_LOCK = threading.Lock()


def _policy_key(policy: ExpressionPolicy) -> int:
    return hash((
        frozenset(policy.functions),
        frozenset(policy.constants),
        policy.quoted_names,
        policy.bare_names,
        policy.allow_comparisons,
        policy.allow_bitops,
    ))


def compile_expression(
    expr: str,
    policy: ExpressionPolicy = DEFAULT_POLICY,
) -> CompiledExpression:
    """Parse and whitelist ``expr``; return a :class:`CompiledExpression`.

    Parameters
    ----------
    expr
        The expression text.
    policy
        Rules governing allowed nodes/functions and reference styles.

    Returns
    -------
    CompiledExpression
        The compiled expression and its ordered references.

    Raises
    ------
    ExpressionError
        If the expression is empty, does not parse, or contains a node/function
        the policy forbids.
    """
    text = "" if expr is None else str(expr).strip()
    if not text:
        raise ExpressionError("empty expression")

    cache_key = (text, _policy_key(policy))
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"syntax error: {exc.msg}") from exc

    rewriter = _RefRewriter(policy)
    new_tree = rewriter.visit(tree)
    ast.fix_missing_locations(new_tree)

    allowed = _allowed_nodes(policy)
    for node in ast.walk(new_tree):
        if not isinstance(node, allowed):
            raise ExpressionError(f"disallowed expression element: {type(node).__name__}")

    code = compile(new_tree, "<expression>", "eval")
    result = CompiledExpression(
        source=text,
        code=code,
        refs=tuple(rewriter.refs),
        constants=tuple(rewriter.constants),
    )
    with _CACHE_LOCK:
        _CACHE[cache_key] = result
    return result


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of :func:`validate_expression`.

    Truthy when ``ok``; ``message`` is a short reason on failure and ``refs`` are
    the reference names the expression uses (whether or not they all resolved).
    """

    ok: bool
    message: str | None = None
    refs: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """Return True when the expression is valid."""
        return self.ok


def resolve_name(
    ref: str,
    known: Sequence[str],
    policy: ExpressionPolicy = DEFAULT_POLICY,
) -> str | None:
    """Return the symbol in ``known`` that ``ref`` resolves to, or ``None``.

    Honours the policy's case-insensitivity and left-of-``|`` matching.
    """
    known = list(known)
    # Exact match first.
    if ref in known:
        return ref
    if policy.case_insensitive:
        low = {str(k).lower(): k for k in known}
        hit = low.get(str(ref).lower())
        if hit is not None:
            return hit
    if policy.split_on_pipe:
        rl = _normalize_left(ref)
        for k in known:
            kl = _normalize_left(k)
            if kl == rl or (policy.case_insensitive and kl.lower() == rl.lower()):
                return k
    return None


def validate_expression(
    expr: str,
    known_names: Sequence[str] = (),
    policy: ExpressionPolicy = DEFAULT_POLICY,
    extra_names: Sequence[str] = (),
    allow_unknown: bool = False,
) -> ValidationResult:
    """Validate a single expression for a GUI editor.

    Checks the expression parses under ``policy`` and (unless ``allow_unknown``)
    that every reference resolves to a name in ``known_names`` or ``extra_names``
    (e.g. earlier equation outputs).

    Parameters
    ----------
    expr
        The expression text.
    known_names
        Valid reference names (columns, parameters, constants).
    policy
        The expression policy.
    extra_names
        Additional valid names not in ``known_names`` (e.g. forward references
        to other outputs the caller will provide).
    allow_unknown
        When True, only the safe-parse check runs; unresolved names are *not* an
        error (they are free parameters, as in a parse model). ``refs`` still
        reports every referenced name.

    Returns
    -------
    ValidationResult
        ``ok`` with a ``message`` reason on failure and the resolved/unresolved
        reference lists.
    """
    try:
        compiled = compile_expression(expr, policy)
    except ExpressionError as exc:
        return ValidationResult(False, str(exc))

    pool = list(known_names) + list(extra_names)
    unresolved = tuple(
        dict.fromkeys(r for r in compiled.refs if resolve_name(r, pool, policy) is None)
    )
    if unresolved and not allow_unknown:
        pretty = ", ".join(repr(u) for u in unresolved)
        return ValidationResult(
            False, f"unknown name(s): {pretty}", refs=compiled.refs, unresolved=unresolved
        )
    return ValidationResult(True, None, refs=compiled.refs, unresolved=unresolved)


def discover_parameters(
    expr: str,
    reserved: Sequence[str] = (),
    policy: ExpressionPolicy = PARSE_MODEL_POLICY,
) -> list[str]:
    """Return the free names in ``expr`` (its fitting parameters).

    Every reference that is not a function, a named constant, or listed in
    ``reserved`` (e.g. the independent variable ``x``) is a parameter. Names are
    returned in first-appearance order; an unparseable expression yields ``[]``.
    """
    try:
        compiled = compile_expression(expr, policy)
    except ExpressionError:
        return []
    reserved_set = {str(r) for r in reserved}
    out: list[str] = []
    for ref in compiled.refs:
        if ref in reserved_set or ref in out:
            continue
        out.append(ref)
    return out


def evaluate_expression(
    expr: str,
    symbols: Mapping[str, Any],
    policy: ExpressionPolicy = DEFAULT_POLICY,
) -> Any:
    """Compile and evaluate ``expr`` against a symbol table.

    Parameters
    ----------
    expr
        The expression text (or a :class:`CompiledExpression`).
    symbols
        Mapping of reference name to value (scalar or NumPy array). Resolution
        honours the policy's case-insensitivity / ``|`` matching. A symbol whose
        name is also a named constant shadows that constant.
    policy
        The expression policy.

    Returns
    -------
    Any
        The evaluated result (scalar or array).

    Raises
    ------
    ExpressionError
        On a disallowed expression or an unresolved reference.
    """
    compiled = expr if isinstance(expr, CompiledExpression) else compile_expression(expr, policy)
    keys = list(symbols.keys())
    ns: dict[str, Any] = dict(policy.functions)
    for i, ref in enumerate(compiled.refs):
        key = resolve_name(ref, keys, policy)
        if key is None:
            raise ExpressionError(f"unresolved name: {ref!r}")
        ns[f"_r{i}"] = symbols[key]
    for j, name in enumerate(compiled.constants):
        key = resolve_name(name, keys, policy)
        ns[f"_c{j}"] = symbols[key] if key is not None else policy.constants[name]
    with np.errstate(all="ignore"):
        return eval(compiled.code, {"__builtins__": {}}, ns)  # noqa: S307 (whitelisted AST)


def function_signatures(policy: ExpressionPolicy = DEFAULT_POLICY) -> dict[str, str]:
    """Return ``{name: doc-summary}`` for the policy's functions (for a help panel)."""
    out: dict[str, str] = {}
    for name, fn in sorted(policy.functions.items()):
        doc = (getattr(fn, "__doc__", "") or "").strip().splitlines()
        summary = doc[0].strip() if doc else ""
        out[name] = summary
    return out
