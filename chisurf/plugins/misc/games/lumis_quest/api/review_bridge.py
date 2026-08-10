"""Where the game touches the documentation.

Everything else in Lumis Quest is a game about the corpus. This is the one
module that changes it, so it is the one that has to be careful.

Three rules, and none of them is optional:

* **Training mode never signs anything off.** Learning fluorescence and
  clearing review debt are different jobs. A player who answered a question
  about a page has not reviewed it, and letting that count would make the gate
  meaningless -- which is the thing the gate exists to prevent.
* **Expert mode signs off only after a grounded challenge is answered.** A win
  in combat is spectroscopy; it says nothing about whether anyone read the
  page. Clearing a room without answering is a rubber stamp, and rubber stamps
  are exactly the failure mode here.
* **The page must not have moved.** The challenge is generated against a
  content hash; if the file changed between generating it and answering it,
  the sign-off is refused. The hash is the review system's own, so this is the
  same rule that already downgrades a stale review rather than a second
  invented one.

The game never writes to ``docs/`` itself. It calls the existing review API,
which owns the sidecars.
"""

from __future__ import annotations

import dataclasses
import pathlib

from chisurf.plugins.core.help.api import review

from .challenge import Challenge, generate

#: The two ways to play.
TRAINING = "training"
EXPERT = "expert"


@dataclasses.dataclass
class Verdict:
    """What came of trying to clear a page.

    Attributes
    ----------
    signed_off : bool
        Whether the review sidecar was updated.
    message : str
        One line for the player.
    reason : str
        Machine-readable outcome: ``signed``, ``training``, ``wrong``,
        ``stale``, ``untracked`` or ``unavailable``.
    """

    signed_off: bool
    message: str
    reason: str


def challenge_for(path, count: int = 1) -> tuple[list[Challenge], str]:
    """Build the challenge a page puts to the player.

    Parameters
    ----------
    path : pathlib.Path or str
        The page.
    count : int, optional
        How many questions.

    Returns
    -------
    tuple
        ``(challenges, content_hash)``. The list is empty for a page with too
        little prose to ask about, or one that cannot be read.
    """
    source = pathlib.Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return [], ""
    content_hash = review.content_hash(text)
    return generate(text, content_hash, count=count), content_hash


def clear_page(
    path,
    mode: str,
    challenge: Challenge | None,
    choice: int | None,
    content_hash: str,
    reviewer: str = "",
) -> Verdict:
    """Try to sign a page off, having cleared its room.

    Parameters
    ----------
    path : pathlib.Path or str
        The page.
    mode : str
        :data:`TRAINING` or :data:`EXPERT`.
    challenge : Challenge or None
        The question that was asked. ``None`` means none was asked, which can
        never sign off.
    choice : int or None
        The option chosen.
    content_hash : str
        The hash the challenge was generated against.
    reviewer : str, optional
        Who is signing. Defaults to the review system's own idea of the user.

    Returns
    -------
    Verdict
        What happened, and why.
    """
    source = pathlib.Path(path)

    if mode != EXPERT:
        return Verdict(
            False,
            "Training run -- nothing signed off.",
            "training",
        )
    if challenge is None or choice is None:
        return Verdict(False, "No challenge was answered.", "wrong")
    if not challenge.is_correct(choice):
        return Verdict(False, "That is not what the page says.", "wrong")

    try:
        current = review.content_hash(source.read_text(encoding="utf-8"))
    except OSError:
        return Verdict(False, "The page could not be read.", "unavailable")
    if current != content_hash:
        # Somebody edited it while the encounter was open. Signing off text
        # nobody has now read is precisely the stale approval the review system
        # already guards against.
        return Verdict(False, "The page changed under you -- not signed off.", "stale")

    if not review.is_tracked(source):
        return Verdict(
            False,
            "This page is outside the reviewed directories.",
            "untracked",
        )

    ok = review.set_status(
        source, review.STATUS_REVIEWED, reviewer=reviewer, reviewer_kind="human"
    )
    if not ok:
        return Verdict(False, "The review system refused the sign-off.", "unavailable")
    return Verdict(True, "Signed off. The ground settles.", "signed")
