"""Turn-based combat against marked animals, built out of photophysics.

What you fight is a **beast**: a real animal with a fluorophore fixed into it
(see :mod:`.bestiary`). The body decides how much punishment it takes and who
moves first; the label decides what it emits, how hard, and how fast it burns
down. Every mechanic below is a real thing one or the other actually does.

* **Photobleaching is the cost of shining.** Emitting costs the emitter its
  own budget, and a high quantum yield cycles harder -- so the brightest label
  hits hardest and burns out soonest. That trade is the tactical layer.
* **Spectral overlap is the type chart** -- measured, not designed. See
  :func:`..roster.effectiveness`.
* **Crosstalk is friendly fire.** If two of your own beasts emit into each
  other's absorption band, part of your shot is absorbed by your own team.
* **FRET is a combo.** A benched partner whose absorption sits under the active
  beast's emission relays the shot and adds to it.
* **The triplet state stuns.** A label pushed too hard shelves itself for a
  turn -- and, in this world, all the way down is where the dark manifold
  starts.
* **Speed is the animal's.** A hare goes before a boar. This is what the old
  fight did not have, and without it every exchange was you-then-them forever.

And the win condition is not a kill. You **unbind**: you take the label off, the
animal walks away, and the dye is yours to fit to somebody who agreed to carry
it. What you may unbind is capped by your Warden seals (:mod:`.tiers`), which is
the ladder the whole map is arranged along.

Qt-free and engine-free, so the whole fight steps in a test with no window.
"""

from __future__ import annotations

import dataclasses
import random

from . import tiers as tiers_api
from .bestiary import BRIGHT_QY, Beast, Species
from .roster import Creature, effectiveness, overlap

#: Global damage scale. Raw brightness against raw photostability settles a
#: fight in two hits, which leaves no room for swapping, combos or the triplet
#: state to matter -- the tactics only exist if the fight lasts long enough to
#: use them. Tuned for roughly five to eight exchanges.
DAMAGE_SCALE = 0.42

#: Chance per attack of dropping into the triplet state, scaled by quantum
#: yield. Bright dyes intersystem-cross more.
TRIPLET_BASE = 0.10

#: How much a FRET partner adds, at full overlap.
COMBO_GAIN = 0.55

#: How much crosstalk with your own bench costs, at full overlap.
CROSSTALK_COST = 0.35

#: Unbinding, at a fresh beast and at one driven all the way down. A label
#: comes off a dye that is already deep in its dark state; a fresh one is
#: welded in.
TAKE_FLOOR = 0.10
TAKE_CEILING = 0.80

#: How readily a freed animal decides to come with you, before anything is
#: taken into account, and how much of that is decided by how long you took.
TRUST_BASE = 0.25
TRUST_GENTLE = 0.50

#: Turns after which a fight counts as having been brute force. A body you
#: ground down for a dozen exchanges does not then follow you home.
GENTLE_TURNS = 12

#: Fraction of max HP that a venomous bite keeps burning, per turn.
VENOM_BLEED = 0.05

#: Fraction of max HP a regrowing body recovers each turn.
REGROWTH = 0.04


@dataclasses.dataclass
class Fighter:
    """A beast in a fight, with its running state.

    Attributes
    ----------
    beast : chisurf.plugins.misc.games.lumis_quest.api.bestiary.Beast
        The animal and its label.
    hp : int, optional
        Remaining photons before it bleaches out. ``None`` means full health;
        zero means already spent, and the two must not be confused -- a
        sentinel of ``0`` made it impossible to construct a spent beast, which
        is exactly what a saved team between fights is full of.
    stunned : bool
        Whether it is shelved in the triplet state this turn.
    bleed : int
        Damage per turn still working from a venomous bite.
    sheltered : bool
        Whether a wellspring body has already spent its one refusal to go out.
    activated : bool
        Whether a ``turn_on`` label has been struck yet -- see ``TRAITS``.
    """

    beast: Beast
    hp: int | None = None
    stunned: bool = False
    bleed: int = 0
    sheltered: bool = False
    activated: bool = False

    def __post_init__(self) -> None:
        """Start at full health only when no HP was given at all."""
        if self.hp is None:
            self.hp = self.beast.max_hp
        self.hp = max(0, int(self.hp))

    @property
    def creature(self) -> Creature | None:
        """The label this beast wears.

        Returns
        -------
        Creature or None
            ``None`` for an unmarked animal.
        """
        return self.beast.label

    @property
    def name(self) -> str:
        """What to call it in the log.

        Returns
        -------
        str
            e.g. ``Verdant Heron``.
        """
        return self.beast.name

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
        return 1.0 - self.hp / max(self.beast.max_hp, 1)

    def has(self, trait: str) -> bool:
        """Whether this beast carries a trait.

        Parameters
        ----------
        trait : str
            A key of :data:`..bestiary.TRAITS`.

        Returns
        -------
        bool
            True when the body or the label grants it.
        """
        return trait in self.beast.traits


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
    """One encounter: your bench against a single marked animal.

    Parameters
    ----------
    team : list of Fighter
        Your beasts. The first alive one is active.
    opponent : Fighter
        What you are fighting.
    rng : random.Random, optional
        Supply one for a reproducible fight; tests do.
    opponent_power : float, optional
        Multiplier on the opponent's damage. It fights alone, with no bench to
        relay or absorb, so parity on paper is a walkover in practice.
    loadout : chisurf.plugins.misc.games.lumis_quest.api.gear.Loadout, optional
        Fitted optics. Omitted means an unfiltered eye: nothing amplified and
        nothing blocked.
    seals : iterable of str, optional
        Warden seals held, which decides what may be unbound.
    """

    def __init__(self, team: list[Fighter], opponent: Fighter,
                 rng: random.Random | None = None, opponent_power: float = 1.6,
                 loadout=None, seals=(), warden_key: str | None = None) -> None:
        if not team:
            raise ValueError("a battle needs at least one beast")
        self.team = team
        self.opponent = opponent
        # A wild beast has no bench and no combo, so it hits harder per shot
        # to make up for it; without this the player simply cannot lose.
        self.opponent_power = opponent_power
        # What is fitted decides how much of your own light is collected. A
        # filter that blocks your beast's band makes it nearly useless --
        # which is what makes gear a choice rather than a stat stick.
        self.loadout = loadout
        self.seals = tuple(seals)
        self.warden_key = warden_key
        self.player_attack_streak = 0
        self.rng = rng or random.Random()
        self.active_index = 0
        self.log: list[Turn] = []
        self.finished = False
        self.won = False
        self.fled = False
        self.rounds = 0
        #: Set when a label is successfully taken off the opponent.
        self.taken: Creature | None = None
        #: Set to the body that walked away free, whether or not it followed.
        self.freed: Species | None = None
        #: Whether the freed animal decided to come with you.
        self.joined = False

    # -- state -------------------------------------------------------------

    @property
    def active(self) -> Fighter:
        """The beast currently in play.

        Returns
        -------
        Fighter
            The active fighter.
        """
        return self.team[self.active_index]

    @property
    def bench(self) -> list[Fighter]:
        """Everyone except the active beast.

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

    # -- turn order --------------------------------------------------------

    def opponent_first(self) -> bool:
        """Whether the wild beast moves before you this round.

        Speed is the *body's*, which is the whole reason bodies matter: a
        far-red label in a hare is a different problem from the same label in a
        boar. Three traits override it, and each is the animal doing what that
        animal does.

        Returns
        -------
        bool
            True when the opponent acts first.
        """
        if self.opponent.has("spearfall") and self.rounds == 0:
            return True
        if self.active.has("silent"):
            return False
        if self.opponent.has("nightsight") and \
                self.opponent.beast.emission_nm > self.active.beast.emission_nm:
            return True
        mine = self.active.beast.speed * self.rng.uniform(0.9, 1.1)
        theirs = self.opponent.beast.speed * self.rng.uniform(0.9, 1.1)
        if self.active.has("bolt") and self.active.bleached > 0.5:
            mine *= 1.15
        return theirs > mine

    # -- actions -----------------------------------------------------------

    def attack(self) -> Turn:
        """Emit at the opponent, and take the cost of having emitted.

        Returns
        -------
        Turn
            What happened.
        """
        return self._round(self._emit)

    def swap(self, index: int) -> Turn:
        """Bring another beast forward. Costs the turn.

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
            return self._record(Turn(f"{self.team[index].name} is fully bleached."))

        def action() -> Turn:
            self.player_attack_streak = 0
            self.active_index = index
            fighter = self.team[index]
            if fighter.has("play"):
                # An otter coming off the bench arrives having enjoyed the wait.
                fighter.hp = min(fighter.beast.max_hp,
                                 fighter.hp + int(round(fighter.beast.max_hp * 0.08)))
            return self._record(Turn(f"{fighter.name} steps forward."))

        return self._round(action)

    def take_chance(self) -> float:
        """Odds of getting the label off right now.

        Three things decide it, and all three are real. A dye driven far into
        its dark state comes away; a fresh one is welded in. You cannot unbind
        what you cannot detect, so a filter that blocks its band collapses the
        odds. And a cunning body of your own knows how to do it.

        Returns
        -------
        float
            0..1.
        """
        if not self.opponent.beast.marked:
            return 0.0
        wear = 1.0 - self.opponent.hp / max(self.opponent.beast.max_hp, 1)
        chance = TAKE_FLOOR + (TAKE_CEILING - TAKE_FLOOR) * max(0.0, min(wear, 1.0))
        if self.loadout is not None:
            seen = min(self.loadout.response(self.opponent.beast.emission_nm), 1.0)
            if self.active.has("echo"):
                # A bat does not need the light to know where the thing is.
                seen = max(seen, 0.85)
            chance *= 0.25 + 0.75 * seen
        if self.active.has("cunning"):
            chance *= 1.5
        return max(0.0, min(chance, 1.0))

    def trust_chance(self) -> float:
        """Odds the freed animal comes with you.

        Nothing about this is combat. A body you ground down over a dozen
        exchanges walks away; one you unbound quickly may not.

        Returns
        -------
        float
            0..1.
        """
        gentle = max(0.0, 1.0 - self.rounds / GENTLE_TURNS)
        chance = TRUST_BASE + TRUST_GENTLE * gentle
        if self.opponent.has("play"):
            chance += 0.2
        if self.opponent.has("bolt"):
            chance -= 0.15
        return max(0.0, min(chance, 1.0))

    def unbind(self) -> Turn:
        """Try to take the label off. Costs the turn either way.

        Returns
        -------
        Turn
            What happened. On success the encounter ends with :attr:`taken` set
            to the label and :attr:`freed` to the body that walked away.
        """
        if self.finished:
            return self._record(Turn("The encounter is already over."))
        if not self.opponent.beast.marked:
            return self._record(Turn("There is nothing fixed into it."))
        refusal = tiers_api.refusal(self.opponent.beast.tier, self.seals)
        if refusal:
            # Not a failed roll: a rule, stated. A player who is told why can
            # go and do something about it.
            return self._round(lambda: self._record(Turn(refusal)))

        def action() -> Turn:
            self.player_attack_streak = 0
            chance = self.take_chance()
            if self.rng.random() >= chance:
                return self._record(
                    Turn(f"The label holds fast ({chance:.0%}).")
                )
            self.taken = self.opponent.beast.label
            self.freed = self.opponent.beast.species
            self.finished = True
            self.won = True
            self.joined = self.rng.random() < self.trust_chance()
            body = self.opponent.beast.species.name
            if self.joined:
                return self._record(Turn(
                    f"The label comes away. The {body} shakes itself -- "
                    f"and follows you."
                ))
            return self._record(Turn(
                f"The label comes away. The {body} goes back into the grass."
            ))

        return self._round(action)

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

    # -- resolution --------------------------------------------------------

    def _round(self, action) -> Turn:
        """Run one exchange, in speed order.

        Parameters
        ----------
        action : callable
            Your half of it, returning the :class:`Turn` to hand back.

        Returns
        -------
        Turn
            Your half's result.
        """
        if self.finished:
            return self._record(Turn("The encounter is already over."))
        first = self.opponent_first()
        if first:
            self._opponent_turn()
            if self.finished:
                return self.log[-1]
        turn = action()
        self._settle()
        if not first and not self.finished:
            self._opponent_turn()
        self.rounds += 1
        self._upkeep()
        return turn

    def _emit(self) -> Turn:
        """Your active beast shines at the opponent.

        Returns
        -------
        Turn
            What happened.
        """
        attacker = self.active
        if attacker.stunned:
            attacker.stunned = False
            return self._record(
                Turn(f"{attacker.name} is stuck in a triplet state.")
            )
        if not attacker.beast.marked:
            return self._record(
                Turn(f"{attacker.name} has no label. It cannot shine at anything.")
            )

        if self.warden_key == "ember":
            self.player_attack_streak += 1
        else:
            self.player_attack_streak = 0

        # Tolm (Warden of Ember) lesson: continuous attacking triggers recoil counter.
        if self.warden_key == "ember" and self.player_attack_streak >= 2:
            self._spend(attacker)
            recoil = max(5, int(attacker.beast.max_hp * 0.28))
            self._apply(attacker, recoil)
            return self._record(
                Turn(f"{attacker.name} emits -- Tolm's boar counters a continuous barrage! (-{recoil} HP recoil)")
            )

        multiplier = self._effectiveness(attacker, self.opponent)

        # A partner whose absorption sits under the active beast's emission
        # relays the shot: that is FRET, and it is why a team is not just a
        # queue of replacements.
        combo = 0.0
        crosstalk = 0.0
        for mate in self.bench:
            if mate.alive and mate.beast.marked:
                combo = max(combo, overlap(attacker.creature, mate.creature))
                # ...and the same overlap the other way is your own team
                # absorbing your shot. The bench cuts both ways.
                crosstalk = max(crosstalk, overlap(mate.creature, attacker.creature))

        gain = 1.0 + COMBO_GAIN * combo - CROSSTALK_COST * crosstalk
        if self.loadout is not None:
            gain *= self.loadout.response(attacker.beast.emission_nm)

        hits = 2 if attacker.has("frenzy") else 1
        total = 0
        for _ in range(hits):
            damage = self._damage(attacker, self.opponent, multiplier, gain)
            if hits > 1:
                damage = max(1, damage // 2)
            total += self._apply(self.opponent, damage)

        self._spend(attacker)
        if self.rng.random() < TRIPLET_BASE * attacker.creature.quantum_yield:
            attacker.stunned = True
        if attacker.has("venom") and total:
            self.opponent.bleed = max(
                self.opponent.bleed,
                max(1, int(round(self.opponent.beast.max_hp * VENOM_BLEED))),
            )
        if attacker.has("discharge") and self.rng.random() < 0.2:
            self.opponent.stunned = True

        note = "super effective" if multiplier > 1.4 else (
            "barely couples" if multiplier < 0.8 else "transfers"
        )
        text = f"{attacker.name} emits -- {note} for {total}."
        if hits > 1:
            text += " Twice."
        if combo > 0.35:
            text += " Relayed by the bench."
        if crosstalk > 0.35:
            text += " Some was absorbed by your own team."
        return self._record(Turn(text, damage=total, multiplier=multiplier,
                                 combo=combo > 0.35, crosstalk=crosstalk > 0.35))

    def _effectiveness(self, attacker: Fighter, defender: Fighter) -> float:
        """Spectral multiplier, after the defender's tricks.

        Parameters
        ----------
        attacker, defender : Fighter
            Who is shining at whom.

        Returns
        -------
        float
            0.5..2.0.
        """
        if not (attacker.beast.marked and defender.beast.marked):
            return 1.0
        multiplier = effectiveness(attacker.creature, defender.creature)
        if defender.has("mimicry"):
            # A crow that has heard what you sound like is never the wrong
            # colour to be hit by.
            multiplier = min(multiplier, 1.0)
        return multiplier

    def _damage(self, attacker: Fighter, defender: Fighter,
                multiplier: float, gain: float) -> int:
        """One hit, with every trait that touches it applied.

        Parameters
        ----------
        attacker, defender : Fighter
            Who is shining at whom.
        multiplier : float
            Spectral effectiveness.
        gain : float
            Bench and optics.

        Returns
        -------
        int
            Damage before the defender's last refusals.
        """
        spread = self.rng.uniform(0.7, 1.3) if attacker.has("unmeasured") \
            else self.rng.uniform(0.85, 1.15)
        power = attacker.beast.attack * multiplier * gain * spread * DAMAGE_SCALE

        if attacker.has("ambush") and self.rounds == 0:
            power *= 2.0
        if attacker.has("charge"):
            power *= 1.4
        if attacker.has("silent"):
            power *= 1.1
        if attacker.has("bloom"):
            power *= 1.2
        if attacker.has("hardlight"):
            power *= 1.25
        if attacker.has("slowburn"):
            power *= 0.9
        if attacker.has("phototaxis") and defender.beast.marked and \
                defender.creature.quantum_yield >= BRIGHT_QY:
            power *= 1.3
        if attacker.has("turn_on") and attacker.activated:
            # Dark until struck: the first hit it takes lights it, and every
            # shot after that is the label doing what it was switched on to
            # do -- the real point of a photoactivatable protein.
            power *= 1.6

        if defender.has("chitin"):
            power *= 0.7
        if defender.has("barrel"):
            power *= 0.85
        if defender.has("mucus") and attacker.beast.marked and \
                attacker.creature.quantum_yield >= BRIGHT_QY:
            power *= 0.75
        if defender.has("burrow") and self.rng.random() < 0.25:
            return 0
        if defender.has("shiftwalk") and self.rng.random() < 0.15:
            return 0

        # Warden-specific distinctiveness rules:
        if self.warden_key == "prism" and defender is self.opponent:
            # Ysolde (Prism): Mantis deflects un-matched spectral emission.
            if multiplier < 1.15:
                return 0
        if self.warden_key == "shutter" and defender is self.opponent:
            # Kestrel (Shutter): Owl is Umbral (far-red) and unseen without tuned filter.
            response = self.loadout.response(defender.beast.emission_nm) if self.loadout is not None else 0.2
            if response < 0.45:
                return 0
        if self.warden_key == "wellspring" and defender is self.opponent:
            # Nera (Wellspring): 50% resistance against artificial high-bleach dyes.
            if attacker.beast.marked and attacker.creature.bleach_rate > 0.08:
                power *= 0.5

        return max(1, int(round(power)))

    def _apply(self, target: Fighter, damage: int) -> int:
        """Take damage off a fighter, respecting what refuses to go out.

        Parameters
        ----------
        target : Fighter
            Who is hit.
        damage : int
            How much.

        Returns
        -------
        int
            Damage actually dealt.
        """
        if damage <= 0:
            return 0
        if target.has("turn_on") and not target.activated:
            # Photoactivation: dark until struck. This hit is what switches
            # it on -- its own next hit is the one that lands harder.
            target.activated = True
        before = target.hp
        target.hp = max(0, target.hp - damage)
        if target.hp == 0 and target.has("wellspring") and not target.sheltered:
            # It was shining before any of this. It does not go out in one blow.
            target.sheltered = True
            target.hp = 1
        return before - target.hp

    def _spend(self, fighter: Fighter) -> None:
        """Charge a beast for having shone.

        Parameters
        ----------
        fighter : Fighter
            Whoever just emitted.
        """
        cost = max(1, int(round(fighter.beast.max_hp * fighter.beast.bleach_rate)))
        fighter.hp = max(0, fighter.hp - cost)

    def _opponent_turn(self) -> None:
        """Let the opponent emit back."""
        if self.finished or not self.opponent.alive:
            return
        if self.opponent.stunned:
            self.opponent.stunned = False
            self.log.append(Turn(f"{self.opponent.name} is shelved, and does nothing."))
            return
        if not self.opponent.beast.marked:
            self.log.append(Turn(f"The {self.opponent.name} keeps its distance."))
            return
        multiplier = self._effectiveness(self.opponent, self.active)
        damage = self._damage(self.opponent, self.active, multiplier, self.opponent_power)
        dealt = self._apply(self.active, damage)
        self._spend(self.opponent)
        if self.opponent.has("venom") and dealt:
            self.active.bleed = max(
                self.active.bleed,
                max(1, int(round(self.active.beast.max_hp * VENOM_BLEED))),
            )
        self.log.append(
            Turn(f"{self.opponent.name} emits back for {dealt}.", damage=dealt,
                 multiplier=multiplier)
        )
        self._settle()

    def _upkeep(self) -> None:
        """End-of-round effects: what is still burning, and what grows back."""
        for fighter in (*self.team, self.opponent):
            if not fighter.alive:
                continue
            if fighter.bleed:
                self._apply(fighter, fighter.bleed)
            if fighter.has("regrowth"):
                fighter.hp = min(
                    fighter.beast.max_hp,
                    fighter.hp + max(1, int(round(fighter.beast.max_hp * REGROWTH))),
                )
        if self.warden_key == "wellspring" and self.opponent.alive:
            # Nera's Jelly rapidly recovers wellspring photons each round.
            self.opponent.hp = min(
                self.opponent.beast.max_hp,
                self.opponent.hp + max(2, int(round(self.opponent.beast.max_hp * 0.12)))
            )
        if self.warden_key == "triplet" and self.opponent.alive and self.opponent.stunned:
            # Ovid's Bat draws dark manifold energy to regenerate while shelved.
            self.opponent.hp = min(
                self.opponent.beast.max_hp,
                self.opponent.hp + max(2, int(round(self.opponent.beast.max_hp * 0.15)))
            )
        self._settle()

    def _settle(self) -> None:
        """Check whether the fight is over, and pick a replacement if not."""
        if self.finished:
            return
        if not self.opponent.alive:
            # Driven all the way down. The label crosses into the dark rather
            # than being destroyed -- which is where the second half of the
            # world comes from, and why this is not the good ending.
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


def wild_encounter(seed_text: str, difficulty: float, labels, terrain: str = "meadow",
                   tier_cap: int = 5) -> Fighter:
    """The marked animal guarding a place.

    Parameters
    ----------
    seed_text : str
        Usually the page address, so the same page always holds the same beast.
    difficulty : float
        0..1, from the room's remoteness.
    labels : sequence of Creature
        Fluorophores the labeller had to hand.
    terrain : str, optional
        Which bodies live on this ground.
    tier_cap : int, optional
        Never produce a beast above this tier.

    Returns
    -------
    Fighter
        The opponent, at full health.

    Raises
    ------
    ValueError
        If there are no labels at all.
    """
    from .bestiary import wild_beast

    beast = wild_beast(seed_text, difficulty, labels, terrain=terrain, tier_cap=tier_cap)
    level = max(0.0, min(difficulty, 1.0))
    hp = int(round(beast.max_hp * (0.7 + 0.9 * level)))
    return Fighter(beast=beast, hp=max(12, hp))
