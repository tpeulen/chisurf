"""Iris and Lumi — the two characters every game in the hub shares.

They are **photons**, which is why they can appear in all of them without the
conceit straining. A photon is the one thing that legitimately shows up in a
detector array, a spectrometer, a lifetime measurement and a walk across a map.

* **Iris** is the probe: the quantum you send in and follow. She is the ball in
  Pong and Breakout, the walker in Lumis Quest. Her colour is her current
  wavelength, so when something re-emits her she changes -- that is not a
  costume change, it is what happened to her.
* **Lumi** is the companion: a settled emitter that travels with Iris. Lumi is
  the cursor sweeping a detector array, the decay being measured, the small
  light trailing Iris across the world.

Keeping them here rather than in one game is the point: a character who exists
in only one place is a mascot, and a character you meet again somewhere else is
a character.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Character:
    """One of the recurring pair.

    Attributes
    ----------
    key : str
        Stable identifier used in save state.
    name : str
        Display name.
    wavelength_nm : float
        Emission wavelength, which is also the character's colour. Iris' is a
        starting value: it changes when she is re-emitted.
    role : str
        One line on who they are, for tooltips and the guided tour.
    """

    key: str
    name: str
    wavelength_nm: float
    role: str


#: The probe. 488 nm is a real laser line, and unlike the violet end it is
#: bright enough to follow against a dark field -- which matters, because in
#: three of these games she is the thing you are tracking.
IRIS = Character(
    key="iris",
    name="Iris",
    wavelength_nm=488.0,
    role="the probe photon you send in and follow",
)

#: The companion. Green, settled, and never re-emitted: Lumi is the constant the
#: player can orient by while Iris changes.
LUMI = Character(
    key="lumi",
    name="Lumi",
    wavelength_nm=520.0,
    role="the companion emitter that travels with Iris",
)

#: Both, by key.
CHARACTERS = {IRIS.key: IRIS, LUMI.key: LUMI}


def draw(scene, character: Character, at, size: float, wavelength_nm: float | None = None) -> None:
    """Draw a character as the photon they are.

    Parameters
    ----------
    scene : chisurf.gui.chigame.scene.Scene
        Frame under construction.
    character : Character
        Who to draw.
    at : tuple of float
        Centre in world units.
    size : float
        Diameter in world units.
    wavelength_nm : float, optional
        Current wavelength, when it differs from the character's own -- Iris
        takes the colour of whatever last re-emitted her.
    """
    scene.draw(
        "photon",
        character.key,
        at=at,
        size=(size, size),
        emission_nm=character.wavelength_nm if wavelength_nm is None else wavelength_nm,
    )
