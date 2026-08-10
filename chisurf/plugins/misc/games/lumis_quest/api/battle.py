"""Turn-based combat, built out of photophysics.

Every mechanic here is a real thing a fluorophore does, which is what stops this
being a reskinned damage race:

* **Photobleaching is the cost of attacking.** Emitting costs the emitter HP,
  and a high quantum yield cycles harder, so the brightest creature hits hardest
  and burns out soonest. That trade is the whole tactical layer.
* **Spectral overlap is the type chart** -- measured, not designed. See
  :func:`..roster.effectiveness`.
* **Crosstalk is friendly fire.** If your own two creatures emit into each
  other's absorption band, part of your shot is absorbed by your own team.
* **FRET is a combo.** A partner whose absorption sits under the active
  creature's emission relays the shot and adds to it.
* **The triplet state stuns.** A creature that pushes too hard shelves itself
  for a turn: real dyes do this, and it stops "attack every turn" being the
  only strategy.

Qt-free and engine-free, so the whole fight steps in a test with no window.
"""

from __future__ import annotations

import dataclasses
import random

from .roster import Creature, effectiveness, overlap

#: Global damage scale. Raw brightness against raw photostability settles a
#: fight in two hits, which leaves no room for swapping, combos or the triplet
#: state to matter -- the tactics only exist if the fight lasts long enough to
#: use them. Tuned for roughly five to eight exchanges.
DAMAGE_SCALE = 0.42

#: Fraction of an emitter's max HP burned by one attack, before quantum yield.
BLEACH_BASE = 0.045

#: Chance per attack of dropping into the triplet state, scaled by quantum
#: yield. Bright dyes intersystem-cross more.
TRIPLET_BASE = 0.10

#: How much a FRET partner adds, at full overlap.
COMBO_GAIN = 0.55

#: How much crosstalk with your own bench costs, at full overlap.
CROSSTALK_COST = 0.35


@dataclasses.dataclass
class Fighter:
    """A creature in a fight, with its running state.

    Attributes
    ----------
    creature : chisurf.plugins.misc.games.lumis_quest.api.roster.Creature
        The fluorophore itself.
    hp : int, optional
        Remaining photons before it bleaches. ``None`` means full health; zero
        means already bleached, and the two must not be confused -- a sentinel
        of ``0`` made it impossible to construct a spent creature, which is
        exactly what a saved team between fights is full of.
    stunned : bool
        Whether it is shelved in the triplet state this turn.
    """

    creature: Creature
    hp: int | None = None
    stunned: bool = False

    def __post_init__(self) -> None:
        """Start at full health only when no HP was given at all."""
        if self.hp is None:
            self.hp = self.creature.max_hp
        self.hp = max(0, int(self.hp))

    @property
    def alive(self) -> bool:
        """Whether it can still fight.

        Returns
        -------
        bool
            False once fully bleached.
        """
        return self.hp > 0

    @property
    def bleached(self) -> float:
        """How far through its photon budget it is.

        Returns
        -------
        float
            0 fresh, 1 spent.
        """
        return 1.0 - self.hp / max(self.creature.max_hp, 1)


@dataclasses.dataclass
class Turn:
    """What happened on one exchange, for the log and the UI.

    Attributes
    ----------
    text : str
        One line describing it.
    damage : int
        Damage dealt.
    multiplier : float
        Spectral effectiveness applied.
    combo : bool
        Whether a FRET partner relayed the shot.
    crosstalk : bool
        Whether the team absorbed part of its own shot.
    """

    text: str
    damage: int = 0
    multiplier: float = 1.0
    combo: bool = False
    crosstalk: bool = False


class Battle:
    """One encounter: your bench against a single opponent.

    Parameters
    ----------
    team : list of Fighter
        Your creatures. The first alive one is active.
    opponent : Fighter
        What you are fighting.
    rng : random.Random, optional
        Supply one for a reproducible fight; tests do.
    opponent_power : float, optional
        Multiplier on the opponent's damage. It fights alone, with no bench to
        relay or absorb, so parity on paper is a walkover in practice.
    """

    def __init__(self, team: list[Fighter], opponent: Fighter,
                 rng: random.Random | None = None, opponent_power: float = 1.6) -> None:
        if not team:
            raise ValueError("a battle needs at least one creature")
        self.team = team
        self.opponent = opponent
        # A wild creature has no bench and no combo, so it hits harder per shot
        # to make up for it; without this the player simply cannot lose.
        self.opponent_power = opponent_power
        self.rng = rng or random.Random()
        self.active_index = 0
        self.log: list[Turn] = []
        self.finished = False
        self.won = False
        self.fled = False

    @property
    def active(self) -> Fighter:
        """The creature currently in play.

        Returns
        -------
        Fighter
            The active fighter.
        """
        return self.team[self.active_index]

    @property
    def bench(self) -> list[Fighter]:
        """Everyone except the active creature.

        Returns
        -------
        list of Fighter
            May be empty.
        """
        return [f for index, f in enumerate(self.team) if index != self.active_index]

    def _record(self, turn: Turn) -> Turn:
        """Append a turn to the log.

        Parameters
        ----------
        turn : Turn
            What happened.

        Returns
        -------
        Turn
            The same turn, for the caller to return.
        """
        self.log.append(turn)
        return turn

    def attack(self) -> Turn:
        """Emit at the opponent, and take the cost of having emitted.

        Returns
        -------
        Turn
            What happened.
        """
        if self.finished:
            return self._record(Turn("The encounter is already over."))
        attacker = self.active
        if attacker.stunned:
            attacker.stunned = False
            turn = self._record(
                Turn(f"{attacker.creature.name} is stuck in a triplet state.")
            )
            self._opponent_turn()
            return turn

        multiplier = effectiveness(attacker.creature, self.opponent.creature)

        # A partner whose absorption sits under the active creature's emission
        # relays the shot: that is FRET, and it is why a team is not just a
        # queue of replacements.
        combo = 0.0
        for mate in self.bench:
            if mate.alive:
                combo = max(combo, overlap(attacker.creature, mate.creature))
        # ...and the same overlap in the other direction is your own team
        # absorbing your shot. The bench cuts both ways.
        crosstalk = 0.0
        for mate in self.bench:
            if mate.alive:
                crosstalk = max(crosstalk, overlap(mate.creature, attacker.creature))

        gain = 1.0 + COMBO_GAIN * combo - CROSSTALK_COST * crosstalk
        spread = self.rng.uniform(0.85, 1.15)
        damage = max(
            1,
            int(round(attacker.creature.attack * multiplier * gain * spread * DAMAGE_SCALE)),
        )
        self.opponent.hp = max(0, self.opponent.hp - damage)

        # Emitting costs photons, and a high quantum yield costs more.
        bleach = BLEACH_BASE * (0.6 + attacker.creature.quantum_yield)
        attacker.hp = max(0, attacker.hp - max(1, int(round(attacker.creature.max_hp * bleach))))

        if self.rng.random() < TRIPLET_BASE * attacker.creature.quantum_yield:
            attacker.stunned = True

        note = "super effective" if multiplier > 1.4 else (
            "barely couples" if multiplier < 0.8 else "transfers"
        )
        text = f"{attacker.creature.name} emits -- {note} for {damage}."
        if combo > 0.35:
            text += " Relayed by the bench."
        if crosstalk > 0.35:
            text += " Some was absorbed by your own team."

        # Recorded before the reply, or the log reads backwards: the opponent's
        # answer was landing in the log ahead of the shot that provoked it.
        turn = self._record(Turn(text, damage=damage, multiplier=multiplier,
                                 combo=combo > 0.35, crosstalk=crosstalk > 0.35))
        self._settle()
        if not self.finished:
            self._opponent_turn()
        return turn

    def swap(self, index: int) -> Turn:
        """Bring another creature forward. Costs the turn.

        Parameters
        ----------
        index : int
            Position in the team.

        Returns
        -------
        Turn
            What happened.
        """
        if self.finished:
            return self._record(Turn("The encounter is already over."))
        if not 0 <= index < len(self.team):
            return self._record(Turn("Nobody there."))
        if index == self.active_index:
            return self._record(Turn("Already out."))
        if not self.team[index].alive:
            return self._record(Turn(f"{self.team[index].creature.name} is fully bleached."))
        self.active_index = index
        turn = self._record(Turn(f"{self.active.creature.name} steps forward."))
        self._opponent_turn()
        return turn

    def flee(self) -> Turn:
        """Leave. Nothing is gained and nothing is lost.

        Returns
        -------
        Turn
            What happened.
        """
        self.finished = True
        self.fled = True
        return self._record(Turn("You withdraw."))

    def _opponent_turn(self) -> None:
        """Let the opponent emit back."""
        if self.finished or not self.opponent.alive:
            return
        multiplier = effectiveness(self.opponent.creature, self.active.creature)
        spread = self.rng.uniform(0.85, 1.15)
        damage = max(
            1,
            int(round(self.opponent.creature.attack * multiplier * spread
                      * DAMAGE_SCALE * self.opponent_power)),
        )
        self.active.hp = max(0, self.active.hp - damage)
        bleach = BLEACH_BASE * (0.6 + self.opponent.creature.quantum_yield)
        self.opponent.hp = max(
            0, self.opponent.hp - max(1, int(round(self.opponent.creature.max_hp * bleach)))
        )
        self.log.append(
            Turn(f"{self.opponent.creature.name} emits back for {damage}.", damage=damage,
                 multiplier=multiplier)
        )
        self._settle()

    def _settle(self) -> None:
        """Check whether the fight is over, and pick a replacement if not."""
        if not self.opponent.alive:
            self.finished = True
            self.won = True
            return
        if not self.active.alive:
            for index, fighter in enumerate(self.team):
                if fighter.alive:
                    self.active_index = index
                    return
            self.finished = True
            self.won = False


def wild_opponent(seed_text: str, difficulty: float, roster_pool, rng=None) -> Fighter:
    """Pick the creature guarding a room.

    Seeded by the room's own address, so the same page always holds the same
    opponent -- a wild encounter that reshuffles every visit is a slot machine,
    not a place.

    Parameters
    ----------
    seed_text : str
        Usually the page address.
    difficulty : float
        0..1, from the room's remoteness. Scales the opponent's HP.
    roster_pool : sequence of Creature
        Creatures to choose from.
    rng : random.Random, optional
        Ignored; kept so callers can pass one uniformly.

    Returns
    -------
    Fighter
        The opponent, at full health.

    Raises
    ------
    ValueError
        If the pool is empty.
    """
    if not roster_pool:
        raise ValueError("no creatures available")
    level = max(0.0, min(difficulty, 1.0))

    # Difficulty picks *which* creature, not merely how much HP it has. Scaling
    # HP alone left remote pages guarded by whatever weakling came up, which
    # made the reward gradient point somewhere the danger did not.
    ranked = sorted(roster_pool, key=lambda creature: creature.attack)
    span = max(1, len(ranked) // 4)
    top = int(round(level * (len(ranked) - 1)))
    window = ranked[max(0, top - span // 2): max(1, top + span // 2 + 1)] or ranked

    picker = random.Random(seed_text)
    creature = picker.choice(window)
    hp = int(round(creature.max_hp * (0.7 + 0.9 * level)))
    return Fighter(creature=creature, hp=max(12, hp))
