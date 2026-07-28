"""Canonical emoji/glyph registry for ChiSurf UI.

This module is the single source of truth for the small pictographic glyphs
("emoticon icons") used throughout ChiSurf widget labels, actions, menus and
``icon`` metadata. Historically the same concept was drawn with several
different glyphs (delete shown as ``🗑️``/``➖``/``❌``/``✕``, refresh as
``🔄``/``🔁``/``♻️``/``↻`` …). Referencing the constants below keeps every UI
site consistent and lets us restyle the whole app from one place.

Usage
-----
Prefer the named constants in widget labels::

    from chisurf.gui.glyphs import Glyphs

    btn = QtWidgets.QPushButton(f"{Glyphs.DELETE} Delete")
    act = menu.addAction(f"{Glyphs.REFRESH} Refresh")

For JSON manifests / view specs (which cannot import Python) use the *same*
canonical literals listed here so a later normalization pass stays a no-op.

Presentation selectors
----------------------
Text-default symbols (``⚙`` U+2699, ``✏`` U+270F, ``♻`` U+267B, ``⚠`` U+26A0 …)
carry an explicit variation selector ``U+FE0F`` so Qt renders them as colour
emoji rather than monochrome text glyphs. Emoji-default pictographs (``🗑``
family, ``🔄`` …) do not need it. :func:`normalize` rewrites the bare forms and
known synonyms to these canonical values.
"""
from __future__ import annotations

import re

VS16 = "️"  # emoji variation selector (forces colour presentation)


class Glyphs:
    """Canonical glyphs grouped by concept.

    Attributes are plain ``str`` constants; use them directly in f-strings.
    Where two historical glyphs meant the same thing, one is chosen canonical
    and the others are mapped to it in :data:`SYNONYMS`.
    """

    # -- Files / IO --------------------------------------------------------
    SAVE = "💾"
    OPEN = "📂"       # open / browse / load (open folder)
    FOLDER = "📁"     # a directory as a concept (tab, tree node)
    FILE = "📄"
    IMPORT = "📥"     # import / download-into-app
    EXPORT = "📤"     # export / upload-out-of-app
    COPY = "📋"       # copy / clipboard
    DATABASE = "🗄" + VS16
    PACKAGE = "📦"
    NOTE = "📝"
    DOCS = "📚"
    BOOK = "📖"

    # -- Edit actions ------------------------------------------------------
    ADD = "➕"        # add / new row (non-destructive)
    REMOVE = "➖"     # remove a row from a list (non-destructive)
    DELETE = "🗑" + VS16   # destructive delete / trash
    EDIT = "✏" + VS16      # edit / rename
    CLEAR = "🧹"      # clear / clean up
    CLOSE = "✕"       # close / cancel / dismiss (interactive)
    CUT = "✂" + VS16

    # -- Run / playback / flow --------------------------------------------
    RUN = "▶" + VS16       # run / play / start
    STOP = "⏹" + VS16
    PAUSE = "⏸" + VS16
    REFRESH = "🔄"    # refresh / reload / restart
    RECOMPUTE = "⟳"   # redo a computation a cache would otherwise skip
    RESET = "♻" + VS16     # reset to defaults / lifecycle
    LOOP = "🔁"       # repeat / loop semantics (not "refresh")
    SHUFFLE = "🔀"
    SKIP_BACK = "⏮" + VS16
    SKIP_FWD = "⏭" + VS16

    # -- Status ------------------------------------------------------------
    SUCCESS = "✅"    # status: succeeded
    ERROR = "❌"      # status: failed / error
    WARNING = "⚠" + VS16
    INFO = "ℹ" + VS16
    CHECK = "✓"       # inline tick (pass, in tables)
    CROSS = "✗"       # inline ballot-x (fail, in tables)
    CHECKBOX_ON = "☑" + VS16
    CHECKBOX_OFF = "☐"
    PENDING = "⏳"    # busy / waiting
    STAR_ON = "★"     # favourite (filled)
    STAR_OFF = "☆"    # favourite (empty)
    FLAG = "🚩"

    # -- Navigation --------------------------------------------------------
    ARROW_RIGHT = "→"
    ARROW_LEFT = "←"
    ARROW_UP = "↑"
    ARROW_DOWN = "↓"
    UP = "⬆" + VS16
    DOWN = "⬇" + VS16

    # -- Search / view -----------------------------------------------------
    SEARCH = "🔍"     # search / filter / zoom
    EYE = "👁" + VS16      # visibility
    CHART = "📊"
    CHART_UP = "📈"
    CHART_DOWN = "📉"

    # -- Tools / config ----------------------------------------------------
    SETTINGS = "⚙" + VS16
    TOOLS = "🛠" + VS16
    TOOLBOX = "🧰"
    WRENCH = "🔧"
    TARGET = "🎯"
    TEST = "🧪"
    SCIENCE = "🔬"
    LINK = "🔗"
    PLUGIN = "🔌"
    PALETTE = "🎨"
    LABEL = "🏷" + VS16
    PIN = "📌"
    TIMER = "⏱" + VS16
    CLOCK = "🕐"
    ROBOT = "🤖"
    BRAIN = "🧠"
    DNA = "🧬"
    WAVE = "🌊"
    ANTENNA = "📡"
    LOCK = "🔒"
    UNLOCK = "🔓"
    KEY = "🔑"
    USER = "👤"
    USERS = "👥"
    SPARKLE = "✨"
    ROCKET = "🚀"
    CHAIN = "⛓" + VS16
    GRID = "🎛" + VS16


#: Historical / variant glyph -> canonical glyph. Used by :func:`normalize` to
#: rewrite the unambiguous cases (synonyms and missing presentation selectors).
#: Genuinely distinct uses (``🔁`` as a plugin brand icon, ``♻`` as a lifecycle
#: badge) are intentionally *not* listed here and must be wired per-site.
#: Distinct-character synonyms: a glyph that should simply become another
#: glyph (the source and target are different base characters, so replacement
#: is naturally idempotent).
SYNONYMS: dict[str, str] = {
    "🔎": Glyphs.SEARCH,   # zoom / magnifier -> search
    "✎": Glyphs.EDIT,      # light pencil -> edit
    "✖": Glyphs.CLOSE,     # heavy multiply -> close
}

#: Text-default base symbols that must carry a VS16 to render as colour emoji.
#: These are completed in place only when the selector is missing, so the pass
#: is idempotent. Values are the canonical (selector-bearing) form.
VS16_COMPLETE: dict[str, str] = {
    "⚙": Glyphs.SETTINGS,
    "♻": Glyphs.RESET,
    "⏱": Glyphs.TIMER,
    "⚠": Glyphs.WARNING,
    "🗑": Glyphs.DELETE,
    "☑": Glyphs.CHECKBOX_ON,
    "🛠": Glyphs.TOOLS,
    "👁": Glyphs.EYE,
    "🏷": Glyphs.LABEL,
    "⛓": Glyphs.CHAIN,
    "🎛": Glyphs.GRID,
    "🗄": Glyphs.DATABASE,
    "✂": Glyphs.CUT,
    "ℹ": Glyphs.INFO,
    "✏": Glyphs.EDIT,
}

# Precompiled: match each base symbol only when *not* already followed by VS16.
_VS16_RE = {
    base: re.compile(re.escape(base) + r"(?!️)")
    for base in VS16_COMPLETE
}


def normalize(text: str) -> str:
    """Rewrite variant glyphs in ``text`` to their canonical form.

    Only unambiguous synonyms (:data:`SYNONYMS`) and missing presentation
    selectors (:data:`VS16_COMPLETE`) are replaced; directional arrows, tree
    markers and plugin brand icons are left untouched. The transform is
    idempotent.

    Parameters
    ----------
    text : str
        Any string possibly containing glyphs.

    Returns
    -------
    str
        ``text`` with variant glyphs replaced by canonical ones.
    """
    if not text:
        return text
    for variant, canonical in SYNONYMS.items():
        if variant in text:
            text = text.replace(variant, canonical)
    for base, canonical in VS16_COMPLETE.items():
        if base in text:
            text = _VS16_RE[base].sub(canonical, text)
    return text
