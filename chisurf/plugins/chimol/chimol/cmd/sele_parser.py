"""Parsing and evaluating PyMOL selection expressions.

The keyword vocabulary is **not** defined here — it lives in
:mod:`.sele_keywords`, transcribed from PyMOL's ``Keyword[]`` table, and both the
parser and the evaluator consult that one table. Before that split the parser
carried its own hand-maintained tuple of property names, which had drifted:
``resn`` was evaluated correctly but never *parsed*, so ``resn NAG`` fell through
to an implicit ``AND`` of two bare identifiers and quietly matched nothing.

Operator fixity follows the ``STYP_`` codes in ``layer3/Selector.cpp``, which the
stack reducer at the bottom of ``SelectorSelect`` spells out:

* ``STYP_PRP1`` reduces ``LIST PRP1 PVAL`` — ``around``/``expand``/``extend``/``gap``
  are **postfix**: ``name CA around 5``.
* ``STYP_OP22`` reduces ``LIST OP22 VALU VALU LIST`` — ``within``/``near_to``/
  ``beyond`` are **infix** with a distance: ``name CA within 5 of resn ALA``.

Distances arrive in Angstrom and the viewer's coordinate arrays are in scene
units, so every distance operator scales before comparing. Getting that wrong is
invisible on screen and turns ``within 5`` into ``within 0.5``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .sele_keywords import Arity, Keyword, lookup, split_keyword


#: PyMOL names secondary structure ``H``/``S``/``L``; chimol's assigner emits the
#: DSSP-flavoured ``H``/``E``/``C``. Both spellings map here so ``ss S`` and
#: ``ss E`` select the same strands whichever a script was written against.
_PYMOL_SS_ALPHABET = {"e": "s", "s": "s", "c": "l", "l": "l", "h": "h", "g": "h"}


def _map_values(node, mapping: dict[str, str]):
    """Rewrite the literals of a value list through ``mapping``.

    Used where chimol and PyMOL spell the same thing differently, so the
    translation happens once at the edge instead of in every comparison.
    """
    if isinstance(node, ValueNode):
        key = str(node.value).lower()
        return ValueNode(mapping.get(key, key))
    if isinstance(node, ListNode):
        return ListNode([_map_values(item, mapping) for item in node.items])
    return node


def _first_value(node) -> str:
    """The first literal in a value list, for properties that take exactly one."""
    while isinstance(node, ListNode):
        if not node.items:
            return ""
        node = node.items[0]
    if isinstance(node, RangeNode):
        node = node.start
    return str(getattr(node, "value", "")).strip()

# Tokenizer

@dataclass
class Token:
    type: str
    value: str
    start: int
    end: int

    def __repr__(self):
        return f"Token({self.type}, {self.value!r})"


# Keyword patterns are matched case-insensitively via the re.IGNORECASE flag on
# the compiled regex below.  Inline ``(?i)`` flags must NOT be used here: once the
# per-token patterns are joined with ``|`` the flag lands mid-expression, which
# Python 3.11+ rejects ("global flags not at the start of the expression").
TOKEN_TYPES = [
    ("SPACE", r"\s+"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    # `and`/`or`/`not`/`of` stay dedicated tokens because they are structural --
    # they decide the shape of the tree rather than naming a property. Every other
    # keyword lexes as IDENT and is resolved against the keyword table, so the
    # tokenizer cannot fall behind the vocabulary the way it used to: `byres`,
    # `within` and `around` each had their own token type, which meant a keyword
    # absent from *this* list was unreachable however well the evaluator knew it.
    ("AND", r"\band\b|&"),
    ("OR", r"\bor\b|\|"),
    ("NOT", r"\bnot\b|!"),
    ("OF", r"\bof\b"),
    ("TO", r"\bto\b"),
    # Comparison operators, for `b < 30` and friends. `<=`/`>=`/`==` must precede
    # the single characters or they lex as two tokens.
    ("CMP", r"<=|>=|==|<|>|="),
    # An identifier may *start* with a digit as long as it is not a pure number:
    # PDB entries are named like `1dg3`, and lexing that as INT + IDENT made every
    # selection naming such an object a parse error ("Unexpected token INT '1'").
    # The alternation order matters -- FLOAT and INT must come first so that
    # `12` and `1.5` still lex as numbers, and the digit-led identifier pattern
    # requires at least one letter or underscore to disambiguate.
    ("FLOAT", r"\d+\.\d+"),
    ("INT", r"\d+(?![a-zA-Z_0-9])"),
    # A **quoted** name, lexed as one identifier whatever is inside it. Object
    # names are not chosen by this grammar -- an EMDB map arrives called
    # `EMD-3061`, and a hyphen is `MINUS` here because `resi 1-40` needs it, so
    # the name split into `EMD`, `-`, `3061` and every menu command on that
    # object was a parse error. Quoting is the unambiguous spelling, and PyMOL
    # accepts it too; the menus now emit it for any name that is not a bare
    # identifier. Bare `EMD-3061` stays ambiguous with a range on purpose.
    ("QUOTED", r'"[^"]*"' + r"|'[^']*'"),
    # `.` and `;` are part of an identifier so that PyMOL's abbreviations survive
    # lexing: `c.A`, `n.CA`, `bb.`, and dotted names like `polymer.protein`. A
    # bare `%` names a selection. `*` is `all`, and resolves through the table.
    # A *leading* `?` is PyMOL's "undefined is allowed here" mark (`?sele`), so
    # it must reach the evaluator attached to the name rather than being dropped
    # as an unmatched character -- which would turn `?sele` into `sele` and make
    # the one spelling that suppresses the error raise it.
    (
        "IDENT",
        r"\??[a-zA-Z_%*][a-zA-Z0-9_*?]*(?:[.;][a-zA-Z0-9_'*?]*)*"
        r"|\d[a-zA-Z0-9_]*[a-zA-Z_][a-zA-Z0-9_]*",
    ),
    ("PLUS", r"\+"),
    ("MINUS", r"-"),
    ("COLON", r":"),
    ("SLASH", r"/"),
]

TOKEN_REGEX = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_TYPES),
    re.IGNORECASE,
)


def tokenize(expr: str) -> list[Token]:
    tokens = []
    for match in TOKEN_REGEX.finditer(expr):
        kind = match.lastgroup
        value = match.group()
        if kind == "SPACE":
            continue
        if kind == "QUOTED":
            # Becomes an ordinary name token with the quotes taken off, so the
            # whole parser treats it as one identifier and nothing downstream
            # has to learn a second spelling for a name.
            kind, value = "IDENT", value[1:-1]
        tokens.append(Token(kind, value, match.start(), match.end()))
    return tokens


# AST Nodes

class ASTNode:
    pass

@dataclass
class AllNode(ASTNode):
    pass

@dataclass
class NoneNode(ASTNode):
    pass

@dataclass
class IdentNode(ASTNode):
    value: str

@dataclass
class ValueNode(ASTNode):
    value: int | float | str

@dataclass
class UnaryOpNode(ASTNode):
    op: str
    expr: ASTNode

@dataclass
class BinaryOpNode(ASTNode):
    left: ASTNode
    op: str
    right: ASTNode

@dataclass
class ListNode(ASTNode):
    items: list[ASTNode]

@dataclass
class RangeNode(ASTNode):
    start: ASTNode
    end: ASTNode

@dataclass
class PropertyOpNode(ASTNode):
    prop: str
    values: ASTNode

@dataclass
class PrefixSelectNode(ASTNode):
    prefix: str
    values: ASTNode

@dataclass
class DistanceOpNode(ASTNode):
    """A postfix distance operator: ``sele around 5``.

    ``target`` is the *left* operand, matching PyMOL's ``STYP_PRP1`` reduction of
    ``LIST PRP1 PVAL``.
    """

    op: str
    dist: float
    target: ASTNode

@dataclass
class BinaryDistanceNode(ASTNode):
    """An infix distance operator: ``s1 within 5 of s2`` (``STYP_OP22``)."""

    op: str
    dist: float
    left: ASTNode
    right: ASTNode

@dataclass
class FlagNode(ASTNode):
    """A class of atoms taking no argument: ``hetatm``, ``solvent``, ``backbone``."""

    name: str

@dataclass
class NumericOpNode(ASTNode):
    """A numeric property compared against a value: ``b < 30``."""

    prop: str
    op: str
    value: float

@dataclass
class CustomPropNode(ASTNode):
    """A named custom property: ``p.foo = 1``."""

    name: str
    op: str = "="
    value: object = None

@dataclass
class MacroNode(ASTNode):
    obj: str
    chain: str
    resi: str
    name: str

# Parser

class ParserError(Exception):
    pass


class UnsupportedSelection(Exception):
    """A keyword PyMOL has that chimol cannot evaluate on the data it holds.

    Raised rather than quietly returning nothing, because an empty selection and
    an unimplemented keyword look identical to a user and only one of them is
    their fault. Working rule: a gap that is shown beats a gap that is hidden.
    """


class UnknownSelectionName(ParserError):
    """A bare word that names no object, group or stored selection.

    PyMOL's selector ends the same walk with ``Invalid selection name "x"``
    (``Selector.cpp``, ``SelectorSelect0``): a name it cannot resolve is an
    error, not an empty answer. Carrying that here is the difference between
    ``count_atoms lgi`` reporting a typo and reporting ``0``.

    Parameters
    ----------
    name : str
        The word as the user typed it.
    """

    def __init__(self, name: str):
        self.name = str(name)
        super().__init__(f'Invalid selection name "{self.name}".')


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self) -> Token | None:
        if self.pos < len(self.tokens):
            token = self.tokens[self.pos]
            self.pos += 1
            return token
        return None

    def match(self, *expected_types) -> Token | None:
        token = self.peek()
        if token and token.type in expected_types:
            return self.advance()
        return None

    def expect(self, expected_type) -> Token:
        token = self.advance()
        if not token or token.type != expected_type:
            raise ParserError(f"Expected {expected_type}, got {token.type if token else 'EOF'}")
        return token

    def parse(self) -> ASTNode:
        if not self.tokens:
            return AllNode()
        node = self.parse_expr()
        if self.pos < len(self.tokens):
            raise ParserError(f"Unexpected token {self.peek()} at end of expression")
        return node

    #: Token types that can begin a selection term, and therefore make the space
    #: between two terms an implicit ``and``.
    _PRIMARY_STARTS = ("IDENT", "LPAREN", "NOT", "SLASH")

    def parse_expr(self) -> ASTNode:
        return self.parse_or()

    def parse_or(self) -> ASTNode:
        left = self.parse_and()
        while self.match("OR"):
            right = self.parse_and()
            left = BinaryOpNode(left, "OR", right)
        return left

    def parse_and(self) -> ASTNode:
        """Explicit ``and``, PyMOL's ``-`` subtract, ``in``/``like``, or a bare space."""
        left = self.parse_infix_distance()
        while True:
            if self.match("AND"):
                left = BinaryOpNode(left, "AND", self.parse_infix_distance())
                continue
            # PyMOL added `-` as the natural complement of `+`: an AND NOT. Any
            # `-` that belonged to a numeric range was consumed inside the value
            # list, so one reaching here is a subtraction.
            if self.match("MINUS"):
                left = BinaryOpNode(left, "subtract", self.parse_infix_distance())
                continue
            binary = self._peek_keyword(Arity.BINARY)
            if binary is not None and binary.canonical in ("in", "like"):
                self.advance()
                left = BinaryOpNode(
                    left, binary.canonical, self.parse_infix_distance()
                )
                continue
            token = self.peek()
            if token and token.type in self._PRIMARY_STARTS:
                left = BinaryOpNode(left, "AND", self.parse_infix_distance())
                continue
            break
        return left

    def parse_infix_distance(self) -> ASTNode:
        """``s1 within 5 of s2`` — PyMOL's ``STYP_OP22``, infix with a distance."""
        left = self.parse_postfix_distance()
        while True:
            keyword = self._peek_keyword(Arity.DIST_OF)
            if keyword is None:
                break
            self.advance()
            dist = self._expect_number(keyword.canonical)
            self.expect("OF")
            right = self.parse_postfix_distance()
            left = BinaryDistanceNode(keyword.canonical, dist, left, right)
        return left

    def parse_postfix_distance(self) -> ASTNode:
        """``sele around 5`` — PyMOL's ``STYP_PRP1``, postfix with a value."""
        node = self.parse_not()
        while True:
            keyword = self._peek_keyword(Arity.DIST)
            if keyword is None:
                break
            self.advance()
            dist = self._expect_number(keyword.canonical)
            node = DistanceOpNode(keyword.canonical, dist, node)
        return node

    def parse_not(self) -> ASTNode:
        if self.match("NOT"):
            expr = self.parse_not()
            return UnaryOpNode("NOT", expr)
        return self.parse_primary()

    def _peek_keyword(self, arity: Arity) -> Keyword | None:
        """The next token as a keyword of ``arity``, without consuming it."""
        token = self.peek()
        if not token or token.type != "IDENT":
            return None
        keyword = lookup(token.value)
        if keyword is not None and keyword.arity is arity:
            return keyword
        return None

    def _expect_number(self, what: str) -> float:
        """Consume a numeric literal, as every distance operator requires."""
        negative = bool(self.match("MINUS"))
        token = self.advance()
        if not token or token.type not in ("FLOAT", "INT"):
            raise ParserError(f"Expected a number after '{what}'")
        value = float(token.value)
        return -value if negative else value

    def parse_primary(self) -> ASTNode:
        token = self.peek()
        if not token:
            raise ParserError("Unexpected end of expression")

        if self.match("LPAREN"):
            node = self.parse_expr()
            self.expect("RPAREN")
            return node

        if token.type == "IDENT":
            ident = self.advance().value
            split = split_keyword(ident)
            if split is not None:
                keyword, glued = split
                return self.parse_keyword(keyword, glued)
            return IdentNode(ident)

        # Macro syntax /obj/chain/res/name
        if self.match("SLASH"):
            return self.parse_macro()

        raise ParserError(f"Unexpected token {token}")

    def parse_keyword(self, keyword: Keyword, glued: str) -> ASTNode:
        """Build the node one keyword calls for, given what its arity says it takes.

        Parameters
        ----------
        keyword : Keyword
            The keyword, already resolved from the table.
        glued : str
            Text that arrived attached to an abbreviation, as in ``c.A``. Empty
            when the value follows as its own token.
        """
        canonical = keyword.canonical

        if keyword.arity is Arity.FLAG:
            if canonical == "all":
                return AllNode()
            if canonical == "none":
                return NoneNode()
            return FlagNode(canonical)

        if keyword.arity is Arity.STRING:
            values = ValueNode(glued) if glued else self.parse_value_list()
            return PropertyOpNode(canonical, values)

        if keyword.arity is Arity.NUMERIC:
            op_token = self.match("CMP")
            op = op_token.value if op_token else "="
            return NumericOpNode(canonical, op, self._expect_number(canonical))

        if keyword.arity is Arity.UNARY:
            return UnaryOpNode(canonical, self.parse_not())

        if keyword.arity is Arity.PROP:
            op_token = self.match("CMP")
            op = op_token.value if op_token else "="
            value = self.parse_value() if op_token else None
            return CustomPropNode(glued, op, getattr(value, "value", None))

        if keyword.arity in (Arity.DIST, Arity.DIST_OF):
            # Reachable only when one leads the expression, which PyMOL also
            # rejects: both are operators on a selection to their left.
            raise ParserError(
                f"'{canonical}' needs a selection before it, "
                f"e.g. 'name CA {canonical} 5'"
            )

        if keyword.arity is Arity.BINARY:
            raise ParserError(f"'{canonical}' needs a selection on both sides")

        raise ParserError(f"Cannot parse '{canonical}'")

    def parse_value_list(self) -> ASTNode:
        items = []
        items.append(self.parse_value_range())
        while self.match("PLUS"):
            items.append(self.parse_value_range())
        if len(items) == 1:
            return items[0]
        return ListNode(items)

    def parse_value_range(self) -> ASTNode:
        start = self.parse_value()
        is_range = False
        if self.match("MINUS") or self.match("TO"):
             end = self.parse_value()
             return RangeNode(start, end)
        if self.match("COLON"):
             end = self.parse_value()
             return RangeNode(start, end)
        return start

    def parse_value(self) -> ASTNode:
        if self.match("MINUS"):
             token = self.advance()
             if not token: raise ParserError("Unexpected end of expression after '-'")
             if token.type == "INT":
                  return ValueNode(-int(token.value))
             elif token.type == "FLOAT":
                  return ValueNode(-float(token.value))
             raise ParserError(f"Expected number after '-' but got {token.type}")

        token = self.advance()
        if not token: raise ParserError("Unexpected end of expression")
        if token.type in ("INT", "FLOAT"):
             return ValueNode(float(token.value) if token.type == "FLOAT" else int(token.value))
        if token.type == "IDENT":
             return ValueNode(token.value)
        raise ParserError(f"Expected value, got {token.type}")

    def parse_macro(self) -> ASTNode:
        # Simplified macro parsing obj/chain/res/name
        parts = ["", "", "", ""]
        part_idx = 0
        while part_idx < 4:
            token = self.peek()
            if not token: break
            if token.type == "SLASH":
                self.advance()
                part_idx += 1
                continue

            # accumulate until slash
            val = ""
            while True:
                t = self.peek()
                if not t or t.type == "SLASH" or t.type == "SPACE" or t.type == "RPAREN":
                    break
                val += self.advance().value
            parts[part_idx] = val
        return MacroNode(obj=parts[0], chain=parts[1], resi=parts[2], name=parts[3])

# Evaluator

class Evaluator:
    def __init__(self, viewer, default_object_id=None, named_selections=None):
        self.viewer = viewer
        self.default_object_id = default_object_id
        self._class_cache: dict[str, object] = {}
        self._typing_cache: dict[str, object] = {}
        self._ring_cache: dict[str, object] = {}
        #: Named selections, ``{name: {"object_id", "mask", ...}}``. A bare name
        #: in an expression resolves to the atoms it captured, exactly as a PyMOL
        #: selection object does -- ``show sticks, mysel and resi 10`` is
        #: meaningful because ``mysel`` is a name with atoms behind it, not just
        #: an expression that happened to be evaluated once.
        self._named_selections = named_selections or {}

    def evaluate(self, expr: str, object_id=None) -> np.ndarray:
        tokens = tokenize(expr)
        parser = Parser(tokens)
        ast = parser.parse()
        obj_id = object_id or self.default_object_id
        return self.eval_node(ast, obj_id)

    def eval_node(self, node: ASTNode, object_id: str) -> np.ndarray:
        if isinstance(node, AllNode):
            return self._get_all_mask(object_id)
        elif isinstance(node, NoneNode):
            return self._get_none_mask(object_id)
        elif isinstance(node, FlagNode):
            return self._eval_flag(node.name, object_id)
        elif isinstance(node, IdentNode):
            # `water` is not a PyMOL selection keyword, but it is what everyone
            # types; accepting it costs nothing and no PyMOL script can break on
            # a name PyMOL itself rejects.
            if node.value.lower() in ("water", "waters", "hetero"):
                return self._eval_flag(
                    "solvent" if node.value.lower() != "hetero" else "hetatm",
                    object_id,
                )
            return self._get_ident_mask(node.value, object_id)
        elif isinstance(node, UnaryOpNode):
            if node.op == "NOT":
                return ~self.eval_node(node.expr, object_id)
            return self._eval_expansion(node.op, node.expr, object_id)
        elif isinstance(node, BinaryOpNode):
            left = self.eval_node(node.left, object_id)
            right = self.eval_node(node.right, object_id)
            if node.op == "AND":
                return left & right
            elif node.op == "OR":
                return left | right
            elif node.op == "subtract":
                return left & ~right
            elif node.op == "in":
                # PyMOL: atoms in `left` whose identifiers also appear in `right`.
                return self._eval_in(node.left, node.right, object_id, like=False)
            elif node.op == "like":
                return self._eval_in(node.left, node.right, object_id, like=True)
        elif isinstance(node, PropertyOpNode):
            return self._eval_property(node.prop, node.values, object_id)
        elif isinstance(node, NumericOpNode):
            return self._eval_numeric(node, object_id)
        elif isinstance(node, CustomPropNode):
            raise UnsupportedSelection(
                f"custom property 'p.{node.name}' is not stored by chimol"
            )
        elif isinstance(node, PrefixSelectNode):
             # map 'c' -> chain, 'r' -> resi, etc.
             prop_map = {'c': 'chain', 'r': 'resn', 'n': 'name', 'e': 'elem', 'i': 'resi', 's': 'segi', 'o': 'object'}
             prop = prop_map.get(node.prefix, "unknown")
             return self._eval_property(prop, node.values, object_id)
        elif isinstance(node, DistanceOpNode):
             return self._eval_distance(node.op, node.dist, node.target, object_id)
        elif isinstance(node, BinaryDistanceNode):
             return self._eval_binary_distance(node, object_id)
        elif isinstance(node, MacroNode):
             return self._eval_macro(node, object_id)

        raise NotImplementedError(f"Evaluation of {type(node)} not implemented")

    def _get_all_mask(self, object_id: str) -> np.ndarray:
        try:
             entry = self.viewer._objects.get(object_id)
             n_atoms = entry.state.atoms.shape[0]
             return np.ones(n_atoms, dtype=bool)
        except Exception:
             return np.zeros(0, dtype=bool)

    def _get_none_mask(self, object_id: str) -> np.ndarray:
        try:
             entry = self.viewer._objects.get(object_id)
             n_atoms = entry.state.atoms.shape[0]
             return np.zeros(n_atoms, dtype=bool)
        except Exception:
             return np.zeros(0, dtype=bool)

    #: Flags PyMOL derives per residue from the atoms present. Values name the
    #: field of :class:`~..analysis.atom_classes.AtomClasses` that answers them.
    _CLASS_FLAGS: dict[str, str] = {
        "polymer": "polymer",
        "polymer.protein": "protein",
        "polymer.nucleic": "nucleic",
        "organic": "organic",
        "inorganic": "inorganic",
        "solvent": "solvent",
        "guide": "guide",
        "backbone": "backbone",
        "sidechain": "sidechain",
        "hydro": "hydrogen",
        "metals": "metal",
    }

    #: Keywords PyMOL answers from chemistry or editor state that chimol does not
    #: model. Reported by name rather than silently returning nothing, so an
    #: unimplemented keyword cannot be mistaken for an empty selection.
    _UNSUPPORTED_FLAGS: dict[str, str] = {
        "delocalized": "delocalised charge needs assigned chemistry",
        "fixed": "chimol has no sculpting flags",
        "restrained": "chimol has no sculpting flags",
        "masked": "chimol has no picking mask",
        "protected": "chimol has no editor protection flags",
        "center": "chimol has no pseudo-atom for the scene centre",
        "origin": "chimol has no pseudo-atom for the rotation origin",
    }

    #: PyMOL's `don.`/`acc.`. These were listed
    #: as unsupported -- "need assigned chemistry" -- while
    #: :func:`~..analysis.hbonds.type_atoms` was already assigning exactly that
    #: chemistry for the polar-contact search, from the residue templates and
    #: the bond angles. The keyword was the only missing piece, and its absence
    #: took the object menu's **hydrogens > add polar** with it.
    _CHEMISTRY_FLAGS: dict[str, str] = {
        "donors": "donor",
        "acceptors": "acceptor",
    }

    def _typing(self, object_id: str):
        """Donor/acceptor chemistry for an object, cached like the classes.

        Typing walks every atom and its neighbours, so a selection naming both
        `donors` and `acceptors` would otherwise do it twice.
        """
        cache = self._typing_cache
        if object_id in cache:
            return cache[object_id]
        from ..analysis.hbonds import type_atoms

        entry = self.viewer._objects.get(object_id)
        state = getattr(entry, "state", None)
        atoms = getattr(state, "atoms", None)
        if atoms is None:
            raise UnsupportedSelection(
                "this object carries raw coordinates, with no atom names to "
                "type as donors or acceptors"
            )
        typing = type_atoms(atoms, getattr(state, "bond_pairs", None))
        cache[object_id] = typing
        return typing

    def _classes(self, object_id: str):
        """Classify an object's atoms, caching per object.

        Classification walks every residue, so a selection like
        ``backbone and sidechain around 5`` would otherwise redo it for each term.
        """
        cache = self._class_cache
        if object_id in cache:
            return cache[object_id]
        from ..analysis.atom_classes import classify_atoms

        entry = self.viewer._objects.get(object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            raise UnsupportedSelection(
                "this object carries raw coordinates, with no atom names to "
                "classify"
            )
        classes = classify_atoms(atoms)
        cache[object_id] = classes
        return classes

    def _eval_flag(self, name: str, object_id: str) -> np.ndarray:
        """Evaluate a no-argument atom class: ``hetatm``, ``solvent``, ``backbone``."""
        if len(self._get_none_mask(object_id)) == 0:
            return self._get_none_mask(object_id)

        if name in self._UNSUPPORTED_FLAGS:
            raise UnsupportedSelection(
                f"'{name}' is not supported: {self._UNSUPPORTED_FLAGS[name]}"
            )

        if name in self._CHEMISTRY_FLAGS:
            typing = self._typing(object_id)
            return np.asarray(
                getattr(typing, self._CHEMISTRY_FLAGS[name]), dtype=bool
            )

        if name == "hetatm":
            return self._get_hetero_mask(object_id)
        if name == "present":
            # One coordinate set per object, so every atom is present in it.
            return self._get_all_mask(object_id)
        if name in ("visible", "enabled"):
            return self._get_visible_mask(object_id, name)
        if name == "bonded":
            return self._get_bonded_mask(object_id)

        field = self._CLASS_FLAGS.get(name)
        if field is None:
            raise UnsupportedSelection(f"unknown selection keyword '{name}'")
        return np.asarray(getattr(self._classes(object_id), field), dtype=bool)

    def _get_visible_mask(self, object_id: str, keyword: str) -> np.ndarray:
        """Atoms in an enabled object — the object-level half of ``visible``.

        PyMOL's ``visible`` is per atom and per representation. chimol's
        visibility is per object and per representation, not per atom, so this
        answers the part it can answer honestly: every atom of an enabled object,
        none of a disabled one.
        """
        try:
            for obj in self.viewer.list_objects():
                if str(obj.get("id", "")) != str(object_id):
                    continue
                enabled = obj.get("visible", obj.get("enabled", True))
                return (
                    self._get_all_mask(object_id)
                    if bool(enabled)
                    else self._get_none_mask(object_id)
                )
        except Exception:
            pass
        return self._get_all_mask(object_id)

    def _get_bonded_mask(self, object_id: str) -> np.ndarray:
        """Atoms with at least one bond, when the object carries a bond list."""
        entry = self.viewer._objects.get(object_id)
        bonds = getattr(getattr(entry, "state", None), "bond_pairs", None)
        if bonds is None:
            raise UnsupportedSelection(
                "'bonded' needs a bond list, which this object does not carry"
            )
        mask = self._get_none_mask(object_id)
        pairs = np.asarray(bonds, dtype=int).reshape(-1, 2)
        if pairs.size:
            mask[np.unique(pairs)] = True
        return mask

    def _get_hetero_mask(self, object_id: str) -> np.ndarray:
        """Atoms in residues the backbone trace never visits.

        Defined by absence from the trace rather than by a residue-name table,
        which is the same rule the viewer uses to decide what to draw as
        nonbonded, so a selection and the picture agree.
        """
        try:
            entry = self.viewer._objects.get(object_id)
            atoms = getattr(entry.state, "atoms", None)
            if atoms is None:
                return self._get_none_mask(object_id)
            mask = self.viewer._hetero_atom_mask(atoms, len(atoms))
            return np.asarray(mask, dtype=bool)
        except Exception:
            return self._get_none_mask(object_id)

    def _get_ident_mask(self, name: str, object_id: str) -> np.ndarray:
        """Resolve a bare name to an object's atoms, as PyMOL does.

        ``solvent and 1dg3`` is the ordinary way to scope a selection to one
        molecule, and it is what the object menus generate. Returning nothing
        here made every such selection silently empty.

        Four kinds of name resolve, in PyMOL's own order (``SelectorSelect0``):
        an **object**, a stored **selection**, a **group** -- which is every one
        of its members, so ``show sticks, ligands`` reaches all of them -- and
        finally nothing, which is an *error* rather than an empty answer. A
        leading ``?`` is PyMOL's mark for "undefined is allowed here" and
        suppresses that error.

        The evaluator is scoped to one object, so a name belonging to a
        *different* object contributes nothing here; the caller walks the
        objects and unions the results.

        Raises
        ------
        UnknownSelectionName
            When the word names nothing the viewer knows and is not ``?``-marked.
        """
        raw = (name or "").strip()
        undefined_ok = raw.startswith("?")
        target = raw.lstrip("?").lower()
        if not target:
            return self._get_none_mask(object_id)

        try:
            objects = self.viewer.list_objects()
        except Exception:
            objects = []
        for obj in objects:
            oid = str(obj.get("id", ""))
            oname = str(obj.get("name", ""))
            if target not in (oid.lower(), oname.lower()):
                continue
            # Within one object every atom matches; across objects the caller
            # evaluates per object, so a different object contributes nothing.
            return (
                self._get_all_mask(object_id)
                if oid == str(object_id)
                else self._get_none_mask(object_id)
            )

        # A stored named selection resolves to the atoms it captured. PyMOL's
        # `sele` works exactly like this: a bare name in an expression is a
        # selection object. A selection may span objects, so the per-object
        # masks are consulted first and the legacy single-object keys second.
        sel = self._named_selections.get(target)
        if isinstance(sel, dict):
            for part in self._selection_parts(sel):
                if str(part.get("object_id", "")) != str(object_id):
                    continue
                arr = np.asarray(part.get("mask"), dtype=bool)
                if arr.shape == self._get_none_mask(object_id).shape:
                    return arr
            return self._get_none_mask(object_id)

        # A group is not an object -- it is a row that owns objects -- so it
        # resolves to *all* of a member's atoms and to nothing in a non-member.
        if self._is_group_member(target, object_id):
            return self._get_all_mask(object_id)
        if self._group_exists(target):
            return self._get_none_mask(object_id)

        if undefined_ok:
            return self._get_none_mask(object_id)
        raise UnknownSelectionName(raw)

    @staticmethod
    def _selection_parts(entry: dict) -> list[dict]:
        """Per-object ``{"object_id", "mask"}`` records of a stored selection.

        A selection written before selections could span objects carries the
        single-object keys at the top level; both spellings are read so an old
        session keeps working.
        """
        parts = entry.get("objects")
        if isinstance(parts, list) and parts:
            return [p for p in parts if isinstance(p, dict)]
        if entry.get("mask") is not None:
            return [{"object_id": entry.get("object_id", ""), "mask": entry.get("mask")}]
        return []

    def _group_exists(self, name: str) -> bool:
        """Whether the viewer has a group by this (lower-cased) name."""
        try:
            return any(str(g).lower() == name for g in self.viewer.group_names())
        except Exception:
            return False

    def _is_group_member(self, group: str, object_id: str) -> bool:
        """Whether ``object_id`` belongs to the group named ``group``."""
        try:
            for name in self.viewer.group_names():
                if str(name).lower() != group:
                    continue
                if str(object_id) in {
                    str(m) for m in self.viewer.group_members(str(name))
                }:
                    return True
        except Exception:
            return False
        return False

    def _object_name(self, object_id: str) -> str | None:
        """Display name of ``object_id``, when the viewer knows it."""
        try:
            for obj in self.viewer.list_objects():
                if str(obj.get("id", "")) == str(object_id):
                    return str(obj.get("name", "")) or None
        except Exception:
            pass
        return None

    #: Value-list property -> the atom field that answers it, when one does.
    #: A property absent from this table is handled specially in
    #: :meth:`_eval_property` or reported as unsupported; nothing falls through
    #: to an empty mask, which is how ``resn`` came to look implemented for years
    #: while matching nothing.
    _STRING_FIELDS: dict[str, str] = {
        "name": "atom_name",
        "resn": "res_name",
        "chain": "chain",
        "segi": "segi",
        "alt": "altloc",
        "id": "i",
    }

    #: Properties PyMOL stores per atom that chimol has no equivalent for.
    _UNSUPPORTED_PROPERTIES: dict[str, str] = {
        "numeric_type": "chimol does not carry force-field atom types",
        "text_type": "chimol does not carry force-field atom types",
        "custom": "chimol does not carry a custom per-atom field",
        "cartoon_color": "per-atom cartoon colour is not stored separately",
        "ribbon_color": "per-atom ribbon colour is not stored separately",
        "stereo": "chimol does not assign stereochemistry",
        "state": "chimol holds a single coordinate set per object",
        "flag": "chimol has no per-atom flag field",
    }

    def _eval_property(
        self, prop: str, values_node: ASTNode, object_id: str
    ) -> np.ndarray:
        """Evaluate a value-list property such as ``resn ALA+GLY`` or ``resi 10-20``."""
        none_mask = self._get_none_mask(object_id)
        if len(none_mask) == 0:
            return none_mask

        prop = (prop or "").lower()
        if prop in self._UNSUPPORTED_PROPERTIES:
            raise UnsupportedSelection(
                f"'{prop}' is not supported: {self._UNSUPPORTED_PROPERTIES[prop]}"
            )

        entry = self.viewer._objects.get(object_id)
        state = getattr(entry, "state", None)
        atoms = getattr(state, "atoms", None)

        # Properties that are not a plain atom field.
        if prop in ("object", "selection"):
            return self._get_ident_mask(_first_value(values_node), object_id)
        if prop == "resi":
            return self._match_values(
                self._residue_id_strings(state, atoms, object_id), values_node
            )
        if prop == "elem":
            return self._match_values(
                self._element_strings(atoms, object_id), values_node
            )
        if prop == "ss":
            return self._match_values(
                self._ss_strings(state, object_id),
                _map_values(values_node, _PYMOL_SS_ALPHABET),
            )
        if prop in ("index", "rank"):
            # `index` is 1-based in PyMOL, `rank` 0-based.
            offset = 1 if prop == "index" else 0
            values = np.arange(len(none_mask), dtype=np.int64) + offset
            return self._match_values(values.astype(str), values_node)
        if prop == "rep":
            return self._eval_rep(_first_value(values_node), object_id)
        if prop == "color":
            return self._eval_color(values_node, object_id)
        if prop == "label":
            return self._eval_label_property(values_node, object_id)
        if prop == "pepseq":
            return self._eval_pepseq(_first_value(values_node), state, atoms, object_id)

        field = self._STRING_FIELDS.get(prop)
        if field is None:
            raise UnsupportedSelection(f"unknown selection property '{prop}'")
        if atoms is None or field not in (atoms.dtype.names or ()):
            raise UnsupportedSelection(
                f"'{prop}' needs a per-atom '{field}', which this structure does "
                "not carry"
            )
        strings = np.char.lower(np.char.strip(atoms[field].astype(str)))
        return self._match_values(strings, values_node)

    def _residue_id_strings(
        self, state, atoms, object_id: str
    ) -> np.ndarray:
        """Residue numbers per atom, as strings, for ``resi``.

        The atom array is preferred over the per-residue trace arrays: the trace
        visits only polymer residues, so reading residue numbers from it makes
        ``resi`` blind to every ligand and water.
        """
        if atoms is not None and "res_id" in (atoms.dtype.names or ()):
            return np.asarray(atoms["res_id"]).astype(str)
        res_ids = getattr(state, "all_atom_res_ids", None)
        if res_ids is not None:
            return np.asarray(res_ids).astype(str)
        raise UnsupportedSelection(
            "'resi' needs residue numbers, which this object does not carry"
        )

    def _element_strings(self, atoms, object_id: str) -> np.ndarray:
        """Element symbols per atom, guessed from the name when the field is empty."""
        if atoms is None:
            raise UnsupportedSelection(
                "'elem' needs atom records, which this object does not carry"
            )
        names = atoms.dtype.names or ()
        if "element" in names:
            symbols = np.char.lower(np.char.strip(atoms["element"].astype(str)))
            if np.any(symbols != ""):
                return symbols
        if "atom_name" in names:
            stripped = np.char.strip(atoms["atom_name"].astype(str))
            return np.char.lower(np.array([n[:1] for n in stripped], dtype="U2"))
        raise UnsupportedSelection("'elem' needs element symbols or atom names")

    def _ss_strings(self, state, object_id: str) -> np.ndarray:
        """Secondary-structure code per atom, for ``ss H+S``.

        Codes are per residue in the viewer, so they are broadcast out to atoms
        through the residue index. PyMOL spells a strand ``S``; chimol's assigner
        emits ``E``, and both are accepted so a script written either way works.
        """
        codes = getattr(state, "secondary_structure", None)
        res_ids = getattr(state, "all_atom_res_ids", None)
        if codes is None:
            raise UnsupportedSelection(
                "no secondary structure has been assigned for this object"
            )
        codes = np.asarray(
            [_PYMOL_SS_ALPHABET.get(str(c).lower(), str(c).lower()) for c in codes]
        )
        if res_ids is None:
            raise UnsupportedSelection(
                "'ss' needs a per-atom residue index to broadcast codes"
            )
        indices = np.asarray(res_ids, dtype=int)
        # The assignment covers traced residues only, and the residue index space
        # includes ligands and solvent past the end of the chain. Those have no
        # secondary structure by definition, so they read as loop rather than
        # making the whole selection fail.
        needed = int(indices.max(initial=-1)) + 1
        if needed > len(codes):
            codes = np.concatenate(
                [codes, np.full(needed - len(codes), "l", dtype="U1")]
            ).astype("U1")
        return codes[indices]

    def _eval_rep(self, value: str, object_id: str) -> np.ndarray:
        """``rep cartoon`` — atoms shown in a representation.

        chimol's representation visibility is per object, not per atom, so this
        answers at the granularity it has: all of the object's atoms when that
        representation is on, none when it is off.
        """
        wanted = (value or "").strip().lower()
        try:
            for obj in self.viewer.list_objects():
                if str(obj.get("id", "")) != str(object_id):
                    continue
                reps = obj.get("representations") or obj.get("reps") or {}
                if wanted in reps:
                    return (
                        self._get_all_mask(object_id)
                        if bool(reps[wanted])
                        else self._get_none_mask(object_id)
                    )
        except Exception:
            pass
        raise UnsupportedSelection(
            f"'rep {wanted}' cannot be answered: chimol tracks representation "
            "visibility per object, and this object does not report it"
        )

    def _eval_color(self, values_node: ASTNode, object_id: str) -> np.ndarray:
        """``color red`` — atoms currently carrying a colour.

        Compares against the per-atom colours the viewer actually holds, so it
        reflects whatever the last ``color`` command did rather than a stored
        colour name.
        """
        from ..colors import get_pymol_color

        name = _first_value(values_node)
        wanted = get_pymol_color(name)
        if wanted is None:
            raise UnsupportedSelection(f"unknown colour '{name}'")
        entry = self.viewer._objects.get(object_id)
        colors = getattr(
            getattr(entry, "state", None), "colors_per_atom_override", None
        )
        if colors is None:
            raise UnsupportedSelection(
                "this object has no per-atom colours to compare against; "
                "'color' matches what a 'color' command actually set"
            )
        rgb = np.asarray(colors, dtype=float)[:, :3]
        target = np.asarray(wanted, dtype=float)[:3]
        return np.all(np.isclose(rgb, target, atol=2.0 / 255.0), axis=1)

    def _eval_label_property(
        self, values_node: ASTNode, object_id: str
    ) -> np.ndarray:
        """``label foo`` — atoms whose label text matches."""
        entry = self.viewer._objects.get(object_id)
        labels = getattr(getattr(entry, "state", None), "labels", None)
        mask = self._get_none_mask(object_id)
        if not labels:
            return mask
        texts = np.full(len(mask), "", dtype=object)
        for index, text in dict(labels).items():
            if 0 <= int(index) < len(texts):
                texts[int(index)] = str(text)
        return self._match_values(np.char.lower(texts.astype(str)), values_node)

    def _eval_pepseq(
        self, pattern: str, state, atoms, object_id: str
    ) -> np.ndarray:
        """``pepseq KAEL`` — residues whose one-letter sequence matches a pattern.

        PyMOL matches a regular expression against the one-letter sequence of each
        chain and selects the residues the match covers, which is what makes it
        useful for finding a motif rather than a residue range.
        """
        import re as _re

        from ..analysis.labels import _ONE_LETTER

        if atoms is None or "res_name" not in (atoms.dtype.names or ()):
            raise UnsupportedSelection(
                "'pepseq' needs residue names, which this object does not carry"
            )
        res_ids = self._residue_id_strings(state, atoms, object_id)
        chains = (
            np.char.strip(atoms["chain"].astype(str))
            if "chain" in (atoms.dtype.names or ())
            else np.full(len(atoms), "")
        )
        names = np.char.upper(np.char.strip(atoms["res_name"].astype(str)))

        mask = self._get_none_mask(object_id)
        try:
            regex = _re.compile(str(pattern).upper())
        except _re.error as exc:
            raise UnsupportedSelection(f"'pepseq' pattern is not valid: {exc}") from exc

        for chain in np.unique(chains):
            in_chain = np.nonzero(chains == chain)[0]
            # One entry per residue, in file order, with the atoms behind each.
            keys, first = np.unique(
                np.char.add(np.char.add(res_ids[in_chain], "|"), names[in_chain]),
                return_index=True,
            )
            order = in_chain[np.sort(first)]
            letters = "".join(
                _ONE_LETTER.get(str(names[i]), "X") for i in order
            )
            for match in regex.finditer(letters):
                for residue_index in range(match.start(), match.end()):
                    anchor = order[residue_index]
                    mask |= (chains == chain) & (res_ids == res_ids[anchor]) & (
                        names == names[anchor]
                    )
        return mask

    def _match_values(self, arr: np.ndarray, values_node: ASTNode) -> np.ndarray:
         mask = np.zeros(arr.shape, dtype=bool)

         def _match_single(node: ASTNode):
             if isinstance(node, ValueNode):
                 val = str(node.value).lower()
                 if any(ch in val for ch in "*?"):
                     # PyMOL matches wildcards, so `name C*` picks up every carbon
                     # position rather than an atom literally called "C*".
                     import fnmatch

                     mask[...] |= np.array(
                         [fnmatch.fnmatchcase(str(a), val) for a in arr], dtype=bool
                     )
                 else:
                     mask[...] |= (arr == val)
             elif isinstance(node, RangeNode):
                 # Convert array to numeric if possible
                 try:
                     num_arr = arr.astype(float) # handle both ints and floats
                     start_val = float(node.start.value)
                     end_val = float(node.end.value)
                     if start_val > end_val:
                         start_val, end_val = end_val, start_val
                     mask[...] |= (num_arr >= start_val) & (num_arr <= end_val)
                 except Exception:
                     pass # Not numeric
             elif isinstance(node, ListNode):
                 for item in node.items:
                     _match_single(item)

         _match_single(values_node)
         return mask

    # ----------------------------------------------------------------- expansion
    #: ``byres``-family keywords and the atom fields whose shared values define one
    #: group. PyMOL grows a selection to every atom in the same group.
    #:
    #: A residue is chain plus number plus segment, not the number alone: two
    #: chains both numbered 10 are two residues, and expanding one to the other is
    #: a bug users notice immediately on a dimer.
    _EXPANSION_FIELDS: dict[str, tuple[str, ...]] = {
        "byres": ("segi", "chain", "res_id"),
        "bychain": ("chain",),
        "bysegment": ("segi",),
    }

    def _eval_expansion(self, op: str, expr: ASTNode, object_id: str) -> np.ndarray:
        """Evaluate a ``byres``-style operator, which grows a selection to a group."""
        mask = self.eval_node(expr, object_id)

        if op == "byobject":
            # Every atom evaluated here belongs to one object already.
            return (
                self._get_all_mask(object_id)
                if np.any(mask)
                else self._get_none_mask(object_id)
            )
        if op == "bymolecule":
            return self._expand_to_molecules(mask, object_id)
        if op == "bycalpha":
            grown = self._expand_by_field(
                mask, object_id, self._EXPANSION_FIELDS["byres"]
            )
            return grown & np.asarray(self._classes(object_id).guide, dtype=bool)
        if op in ("first", "last"):
            return self._first_or_last(mask, op)
        if op == "bound_to":
            return self._eval_bound_to(mask, object_id)
        if op == "byring":
            return self._expand_to_rings(mask, object_id)
        if op == "bycell":
            raise UnsupportedSelection(
                "'bycell' needs the crystal cell's contents as a selection"
            )

        fields = self._EXPANSION_FIELDS.get(op)
        if fields is None:
            raise UnsupportedSelection(f"unknown expansion operator '{op}'")
        return self._expand_by_field(mask, object_id, fields)

    def _expand_to_rings(self, mask: np.ndarray, object_id: str) -> np.ndarray:
        """PyMOL's ``byring``: grow to every ring containing a selected atom.

        The rings are the ones :func:`~..analysis.interactions.find_rings`
        finds -- PyMOL's own bounded walk, up to seven atoms. This was refused
        as "needing ring perception, which chimol does not compute" until the
        pi-interaction work computed it.

        **Every** ring, not only the planar ones: `byring` is a question about
        connectivity, and a proline or a sugar is as much a ring as a
        phenylalanine. The planar filter belongs to the pi finder, which is
        asking a different question.
        """
        if not np.any(mask):
            return mask
        from ..analysis.interactions import find_rings

        entry = self.viewer._objects.get(object_id)
        state = getattr(entry, "state", None)
        atoms = getattr(state, "atoms", None)
        if atoms is None:
            raise UnsupportedSelection(
                "this object carries raw coordinates, with no bonds to walk"
            )

        cache = self._ring_cache
        rings = cache.get(object_id)
        if rings is None:
            rings = find_rings(len(atoms), getattr(state, "bond_pairs", None))
            cache[object_id] = rings

        # Only the rings. PyMOL clears the mask before its ring finder runs
        # (`std::fill_n(base[0].sele_data(), n_atom, 0)` in `SELE_RING`), so a
        # selected atom that is in no ring is **dropped** rather than kept --
        # `byring (name CA)` answers "the prolines", not "every CA plus the
        # prolines", which is what keeping the mask would give.
        selected = np.asarray(mask, dtype=bool)
        grown = np.zeros_like(selected)
        for ring in rings:
            if selected[ring].any():
                grown[ring] = True
        return grown

    def _expand_by_field(
        self, mask: np.ndarray, object_id: str, fields: tuple[str, ...]
    ) -> np.ndarray:
        """Grow ``mask`` to every atom whose ``fields`` all match a selected atom."""
        if not np.any(mask):
            return mask
        entry = self.viewer._objects.get(object_id)
        state = getattr(entry, "state", None)
        atoms = getattr(state, "atoms", None)
        present = [f for f in fields if f in ((atoms.dtype.names or ()) if atoms is not None else ())]

        if present:
            keys = np.asarray(atoms[present[0]]).astype(str)
            for extra in present[1:]:
                keys = np.char.add(
                    np.char.add(keys, "|"), np.asarray(atoms[extra]).astype(str)
                )
        else:
            # A residue index is the one grouping the viewer keeps outside the atom
            # array, so it can still answer `byres` for a trace-only object.
            fallback = getattr(state, "all_atom_res_ids", None)
            if fallback is None or fields != self._EXPANSION_FIELDS["byres"]:
                raise UnsupportedSelection(
                    f"this object carries no {'/'.join(fields)}, so the "
                    "selection cannot be expanded"
                )
            keys = np.asarray(fallback).astype(str)

        if keys.shape[0] != mask.shape[0]:
            raise UnsupportedSelection(
                "the grouping field does not cover every atom"
            )
        return np.isin(keys, np.unique(keys[mask]))

    def _expand_to_molecules(self, mask: np.ndarray, object_id: str) -> np.ndarray:
        """Grow ``mask`` to whole bonded molecules — PyMOL's ``bymol``.

        A molecule is a connected component of the bond graph, so this is not a
        chain: a ligand covalently attached to a protein is one molecule with it,
        and two chains that only touch are two. Falls back to the chain when the
        object has no bonds, which is the closest honest grouping available.
        """
        if not np.any(mask):
            return mask
        entry = self.viewer._objects.get(object_id)
        bonds = getattr(getattr(entry, "state", None), "bond_pairs", None)
        if bonds is None:
            return self._expand_by_field(mask, object_id, ("chain",))

        pairs = np.asarray(bonds, dtype=int).reshape(-1, 2)
        # Label propagation: every atom starts as its own component and repeatedly
        # takes the smallest label across each bond until nothing changes. Simple,
        # allocation-light, and converges in the graph's diameter.
        labels = np.arange(mask.shape[0], dtype=np.int64)
        if pairs.size:
            for _ in range(mask.shape[0]):
                lo = np.minimum(labels[pairs[:, 0]], labels[pairs[:, 1]])
                updated = labels.copy()
                np.minimum.at(updated, pairs[:, 0], lo)
                np.minimum.at(updated, pairs[:, 1], lo)
                updated = updated[updated]
                if np.array_equal(updated, labels):
                    break
                labels = updated
        return np.isin(labels, np.unique(labels[mask]))

    @staticmethod
    def _first_or_last(mask: np.ndarray, op: str) -> np.ndarray:
        """PyMOL's ``first``/``last``: one atom out of a selection."""
        hits = np.nonzero(mask)[0]
        out = np.zeros_like(mask)
        if hits.size:
            out[hits[0] if op == "first" else hits[-1]] = True
        return out

    def _eval_bound_to(self, mask: np.ndarray, object_id: str) -> np.ndarray:
        """Atoms directly bonded to the selection, plus the selection itself."""
        entry = self.viewer._objects.get(object_id)
        bonds = getattr(getattr(entry, "state", None), "bond_pairs", None)
        if bonds is None:
            raise UnsupportedSelection(
                "'bound_to' needs a bond list, which this object does not carry"
            )
        pairs = np.asarray(bonds, dtype=int).reshape(-1, 2)
        out = np.asarray(mask, dtype=bool).copy()
        if pairs.size:
            out[pairs[mask[pairs[:, 0]], 1]] = True
            out[pairs[mask[pairs[:, 1]], 0]] = True
        return out

    # ------------------------------------------------------- numeric properties
    #: Comparison spellings PyMOL's ``AtOper[]`` accepts, and what each means.
    _COMPARISONS = {
        ">": np.greater,
        "<": np.less,
        ">=": np.greater_equal,
        "<=": np.less_equal,
        "=": np.isclose,
        "==": np.isclose,
    }

    #: Numeric selection keyword -> the atom field that answers it.
    _NUMERIC_FIELDS = {
        "b": "bfactor",
        "q": "occupancy",
        "partial_charge": "partial_charge",
        "formal_charge": "formal_charge",
    }

    def _eval_numeric(self, node: NumericOpNode, object_id: str) -> np.ndarray:
        """Evaluate ``b < 30`` and its relatives."""
        if len(self._get_none_mask(object_id)) == 0:
            return self._get_none_mask(object_id)

        compare = self._COMPARISONS.get(node.op)
        if compare is None:
            raise UnsupportedSelection(f"unknown comparison '{node.op}'")

        if node.prop in ("x", "y", "z"):
            values = self._coordinates_angstrom(object_id)[
                :, "xyz".index(node.prop)
            ]
        else:
            field = self._NUMERIC_FIELDS[node.prop]
            entry = self.viewer._objects.get(object_id)
            atoms = getattr(getattr(entry, "state", None), "atoms", None)
            if atoms is None or field not in (atoms.dtype.names or ()):
                raise UnsupportedSelection(
                    f"'{node.prop}' needs a per-atom '{field}', which this "
                    "structure does not carry"
                )
            values = np.asarray(atoms[field], dtype=float)

        return np.asarray(compare(values, float(node.value)), dtype=bool)

    # ------------------------------------------------------------------ in / like
    #: What ``in`` and ``like`` compare atoms by. PyMOL's ``in`` matches on the
    #: full identifier; ``like`` ignores the object and segment, so it can match
    #: the same residue across two structures.
    _IN_FIELDS = ("chain", "res_id", "res_name", "atom_name")
    _LIKE_FIELDS = ("res_id", "atom_name")

    def _eval_in(
        self, left: ASTNode, right: ASTNode, object_id: str, *, like: bool
    ) -> np.ndarray:
        """``s1 in s2`` — atoms of ``s1`` whose identifiers also occur in ``s2``."""
        left_mask = self.eval_node(left, object_id)
        right_mask = self.eval_node(right, object_id)
        if not np.any(left_mask) or not np.any(right_mask):
            return self._get_none_mask(object_id)

        entry = self.viewer._objects.get(object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            raise UnsupportedSelection(
                "'in' and 'like' compare atom identifiers, which this object "
                "does not carry"
            )
        fields = [
            f
            for f in (self._LIKE_FIELDS if like else self._IN_FIELDS)
            if f in (atoms.dtype.names or ())
        ]
        if not fields:
            raise UnsupportedSelection(
                "'in' and 'like' need atom identifiers to compare"
            )
        keys = np.array(
            [
                "|".join(str(atoms[f][i]).strip() for f in fields)
                for i in range(len(atoms))
            ]
        )
        return left_mask & np.isin(keys, np.unique(keys[right_mask]))

    # ------------------------------------------------------------------ distance
    def _coordinates_angstrom(self, object_id: str) -> np.ndarray:
        """Atom coordinates in Angstrom.

        The viewer holds scene units — Angstrom times ``_scale_factor`` — and a
        selection distance is always in Angstrom. Comparing the two directly is
        the unit bug that made ``within 5`` mean ``within 0.5``.
        """
        entry = self.viewer._objects.get(object_id)
        state = getattr(entry, "state", None)
        atoms = getattr(state, "atoms", None)
        if atoms is not None and "xyz" in (atoms.dtype.names or ()):
            # The atom array is the authority: it is kept in Angstrom precisely so
            # that anything leaving the viewer does not have to unscale.
            return np.asarray(atoms["xyz"], dtype=float)
        coords = getattr(state, "all_atom_coords", None)
        if coords is None:
            raise UnsupportedSelection(
                "this object has no coordinates to measure distances against"
            )
        scale = float(getattr(self.viewer, "_scale_factor", 1.0) or 1.0)
        return np.asarray(coords, dtype=float) / scale

    def _within_mask(
        self, coords: np.ndarray, target: np.ndarray, distance: float
    ) -> np.ndarray:
        """Which of ``coords`` lie within ``distance`` of any of ``target``."""
        from chisurf.plugins.chimol.chimol.geometry.neighbors import (
            within_distance_mask,
        )

        return np.asarray(
            within_distance_mask(coords, target, float(distance)), dtype=bool
        )

    def _eval_distance(
        self, op: str, dist: float, target_node: ASTNode, object_id: str
    ) -> np.ndarray:
        """Evaluate a postfix distance operator (``STYP_PRP1``).

        ``around`` excludes the selection it grew from; ``expand`` keeps it. That
        difference is the whole reason PyMOL has both.
        """
        selection = self.eval_node(target_node, object_id)
        if not np.any(selection):
            return self._get_none_mask(object_id)

        if op == "extend":
            return self._extend_by_bonds(selection, object_id, int(round(dist)))

        coords = self._coordinates_angstrom(object_id)

        if op == "gap":
            return self._eval_gap(selection, coords, dist, object_id)

        near = self._within_mask(coords, coords[selection], dist)
        if op == "around":
            return near & ~selection
        if op == "expand":
            return near | selection
        raise UnsupportedSelection(f"unknown distance operator '{op}'")

    def _eval_gap(
        self,
        selection: np.ndarray,
        coords: np.ndarray,
        dist: float,
        object_id: str,
    ) -> np.ndarray:
        """``sele gap d`` — atoms whose vdW shell clears the selection's by ``d``.

        PyMOL measures surface to surface rather than centre to centre, so the
        radii of both atoms enter. Without per-atom radii there is no honest
        answer, so this reports rather than silently measuring centres.
        """
        radii = self._vdw_radii(object_id)
        reach = float(dist) + float(np.max(radii[selection])) + float(np.max(radii))
        candidates = self._within_mask(coords, coords[selection], reach)
        out = np.zeros_like(selection)
        target_xyz = coords[selection]
        target_r = radii[selection]
        for i in np.nonzero(candidates & ~selection)[0]:
            surface = (
                np.linalg.norm(target_xyz - coords[i], axis=1)
                - target_r
                - radii[i]
            )
            if np.min(surface) >= float(dist):
                out[i] = True
        return out

    def _vdw_radii(self, object_id: str) -> np.ndarray:
        """Per-atom van der Waals radii in Angstrom."""
        entry = self.viewer._objects.get(object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is not None and "radius" in (atoms.dtype.names or ()):
            radii = np.asarray(atoms["radius"], dtype=float)
            if np.any(radii > 0):
                return radii
        raise UnsupportedSelection(
            "'gap' measures van der Waals surfaces, and this structure carries "
            "no per-atom radii"
        )

    def _extend_by_bonds(
        self, selection: np.ndarray, object_id: str, steps: int
    ) -> np.ndarray:
        """``sele extend n`` — grow by ``n`` bonds, not by distance."""
        out = np.asarray(selection, dtype=bool).copy()
        for _ in range(max(0, steps)):
            out = self._eval_bound_to(out, object_id)
        return out

    def _eval_binary_distance(
        self, node: BinaryDistanceNode, object_id: str
    ) -> np.ndarray:
        """Evaluate ``s1 within d of s2`` and its relatives (``STYP_OP22``).

        ``within`` admits coincident atoms, ``near_to`` excludes them (so an atom
        never selects itself), and ``beyond`` is the complement of ``within``
        restricted to the left operand.
        """
        left = self.eval_node(node.left, object_id)
        right = self.eval_node(node.right, object_id)
        if not np.any(left):
            return self._get_none_mask(object_id)
        if not np.any(right):
            # Nothing to be near: `beyond` is then vacuously true of everything.
            return left if node.op == "beyond" else self._get_none_mask(object_id)

        coords = self._coordinates_angstrom(object_id)
        near = self._within_mask(coords, coords[right], node.dist)

        if node.op == "within":
            return left & near
        if node.op == "beyond":
            return left & ~near
        if node.op == "near_to":
            # Distance strictly greater than zero: an atom of the right-hand
            # selection must not select itself.
            return left & near & ~right
        raise UnsupportedSelection(f"unknown distance operator '{node.op}'")

    def _eval_macro(self, node: MacroNode, object_id: str) -> np.ndarray:
         mask = self._get_all_mask(object_id)
         if node.chain:
             mask &= self._eval_property("chain", ValueNode(node.chain), object_id)
         if node.resi:
             mask &= self._eval_property("resi", ValueNode(node.resi), object_id)
         if node.name:
             mask &= self._eval_property("name", ValueNode(node.name), object_id)
         return mask

