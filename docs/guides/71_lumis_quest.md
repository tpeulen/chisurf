---
type: Guide
title: Reviewing the documentation as a game (Lumis Quest)
description: A top-down RPG whose map is ChiSurf's own documentation, whose creatures are real animals with real fluorophores fixed into them, and whose expert mode signs pages off through the review gate.
tags: [guides, documentation, review, games, fluorophores, spectra, bestiary]
---

# Reviewing the documentation as a game (Lumis Quest)

Documentation review is a thankless job with no feedback loop: you read a page,
you tick a box, nothing happens. The queue sits stale and the docs drift.

**Lumis Quest** is that job with a game around it. The map *is* this
documentation — every building is a page, every walled compound a settlement —
and what you meet out in the grass is a **real animal with a real fluorophore
fixed into it**, read from the spectra database ChiSurf ships. It teaches
spectroscopy whether or not you ever review anything, and in expert mode it
signs pages off through ChiSurf's own review gate.

**It is not in a menu.** Lumis Quest is an easter egg: with the ChiSurf main
window focused, enter

> ↑ ↑ ↓ ↓ ← → ← → B A

and the game opens. (A game listed beside the fitting tools reads as one of the
tools, which is the wrong thing to say about it — so it is hidden, and the code
is the way in.) The game opens on a title screen: **Continue** resumes a saved
run, **New Journey** starts over (it asks before erasing a run), and the
controls scheme can be switched right there.

## The world you are looking at

The map is generated from the documentation's own `toctree` blocks, so it is
always the corpus as it actually is. Adding a page puts a new building where
there was none; it does not reshuffle the ones around it.

Three states, and they are three different things:

| On the map | Means |
|---|---|
| A dark building | Nobody has read this page |
| A **withered**, brown building | It *was* signed off — then the page changed underneath. Doc rot, visible. |
| A faintly lit building | An agent scouted it; **no human has confirmed it** |
| A warm, glowing building | Settled — a person read it and vouched for it |

That middle band is the frontier the game exists to work. A village's ground
brightens as its pages are settled, so a neglected section is visibly a ghost
town from across the map.

```{figure} figures/lumis_town.png
:name: fig-lumis-town
:width: 90%

A settlement. Each building is a documentation page and the compound is a
`toctree`; the plaque names the section you are standing in rather than a file
path. The bar along the top is the party, the line at the bottom is the game
telling you what to do next, and the figure on the left is another agent going
about the town's day — not scenery, and not waiting for you.
```

You play **Iris**, a probe photon; **Lumi**, a dog, trots behind her. You will
meet them again — they are the ball in Pong and the probe in Breakout.

The whole cast is drawn from **Ninja Adventure** by pixel-boy (CC0, credited
with the shipped art): every figure walks a four-direction animation, shows
its attack pose mid-swing, and carries its weapon on the same sheets. Your
life reads as quarter-step **hearts**; the sky answers the land — rain and
cloud over a withered section, drifting leaves in wild country, fog in the
dark manifold.

Each land has a **biome** — meadowland, deep wood, marsh, highland, coast —
which decides its ground cover, how many lakes it grows, and which animals are
at home in it. Every land also has cliffs with a **cave** in them, and the cave
goes somewhere.

## What you fight

Not dyes. A fluorophore is not an organism; it is something you attach to one.
So the thing in the long grass is a **body** with a **label** fixed into it:

- the **body** is a real animal — hare, heron, boar, moth, olm, crystal jelly —
  and it brings stamina, speed and one behaviour of its own (a hare bolts, a
  beetle is armoured, a crow copies your band so you are never strong against
  it);
- the **label** is a real fluorophore, and it brings everything else: what the
  animal emits, how hard it hits, how fast it burns out, and what it is strong
  against.

A far-red dye in a heron is a different creature from the same dye in a boar,
and both are different from the same body wearing a blue protein. Every feature
a label grants is a real property of the molecule — a high quantum yield hits
harder and bleaches sooner, a protein barrel shields, a wide Stokes shift is
hard to jam, far-red moves first against anything bluer.

The name tells you the band: a **Verdant Hare** emits around 520 nm, a **Garnet
Hare** around 640. You learn to read the spectrum without ever being shown a
number.

**Somebody is doing this to the wild**, and that is the story.

```{figure} figures/lumis_battle.png
:name: fig-lumis-battle
:width: 90%

A body-and-label encounter. The **Cyan Crow** names its band and the panel gives
the number — 503 nm — so the naming convention teaches itself; **T3** is the
label's tier and the bar is how much of it is left to wear down. The log is the
mechanic stated plainly: one emits, the other *transfers*, and the amount
depends on the two spectra rather than on a damage table. **Unbind** carries its
odds (14%) instead of hiding them.
```

## Unbinding, not catching

You do not collect animals. You wear the label down until it lets go and then
**take it off**: the animal walks away free and the dye is yours to fit to
somebody who agreed to carry it. If you did it quickly and did not grind the
animal down, it may decide to come with you.

So bodies and labels are collected **separately**, and the **PARTY** tab is
where you put them together — pick a slot, pick an animal, pick a dye. Nothing
is consumed doing it.

## The ladder

Five **Wardens** hold five seals, and each teaches one real thing before making
you use it: what shining costs, what colour is for, what the glass decides,
what is underneath, and where any of this light came from in the first place.

Your **licence** is how many seals you carry, and it caps what you may unbind —
a beast above it simply shrugs the trap off and the game says whose seal you are
missing. The wild scales to your licence, so a land does not open with something
you cannot answer.

## The town's day

The people in a settlement are not scenery. Each has **drives** that rise on
their own — rest, trade, worship, work, gossip — and walks to a real place to
spend them: the tavern, the supply house, the shrine, the garden beds, the well.
Two who end up in the same place **start a conversation**, and what they talk
about is read off your run — the Marking once you have met a marked animal, the
Wardens once you carry a seal, *you* once you have started taking labels off.

Walk close enough and you can read it over their heads. Press **Q** and you
**drop into it**: you get the exchange in full and they tell you what they meant.

The simulation is entirely offline and deterministic. With a model configured
(**MODE** tab), it writes the *words* and nothing else — and the authored
exchange stands until it lands, so nothing ever waits on a network call.

## The dark manifold

A label pushed too hard does not stop. It **crosses** — into the state
underneath this one, where it is still there and no longer shining. That is the
triplet manifold, it is where a bleaching dye actually goes, and in this world
you can walk into it: down through any **cave mouth**, back up through a
**rift**.

It is the same country with the light taken out. Ash where the grass was, tar
where the water was, dead wood, ruins where people lived — and your own roads,
going the same way they always did. Everything that was ever driven all the way
down is standing in it, still shaped like the animal it used to be.

There are three things to do down there. A shelved animal can be
**rekindled** — give it one of your labels back and it comes up out of the
ash with you, at the cost of the gentlest label you carry. And every **ruin**
was a premises someone kept stocked on the lit side: press the action key at
one and you **salvage** what is left in it — a bench reagent for the crafting
shelf, weighted toward the ones the lit world drops rarely. Each ruin gives
up its find once, ever; which reagent it holds is fixed by where it stands, so
reloading a save cannot reroll it.

The third is the reason to go down at all: **ferals**. Beasts that crossed
with their labels still burning hunt the ash, and the lit world's licence
means nothing to them — their tiers run one step hotter than the same land's
wild, so a label you cannot yet unbind in the meadows can be taken down here,
if you survive the dive. The dark bleeds your photon budget the whole time
you are under (the **dark drain** setting sets how fast), and when the
photons are gone it starts on Iris herself, down to one vitality and no
further. There is no recovery station down there because nobody down there is
keeping anything: what you bring is what you have.

## Controls

Everything is on nine actions, because the game is meant to be playable on a
gamepad. There is no typing anywhere.

| Action | Keyboard | Does |
|---|---|---|
| Move | Arrows / WASD | Walk |
| Confirm | Space | Run; select |
| Shoulder L | Q | Start an encounter; flag a problem |
| Shoulder R | E | Zoom in; next menu tab |
| Cancel | Backspace | Zoom out; back |
| Menu | Tab | Open the pack (MAP, RIG, PARTY, LAB, MODE, OPTIONS) |

### Settings

**OPTIONS** and **GAMELOGIC** are the settings tabs. Up/Down chooses a row,
Left/Right steps it, Confirm activates it — a switch flips, a choice advances,
a button fires. What each row *is* — a slider with its range, a set of choices,
a switch, an action — is declared once in
`chisurf/plugins/misc/games/lumis_quest/api/settings.py`, and the menu draws
whatever is declared: nothing about a setting is written into the menu. The
controls are the same ImGui-style ones the molecular viewer's settings panel is
drawn from.

Settings are part of the run. They are written into the save file and come back
with it, including from a save with no party in it — turning the music down and
then starting over does not turn it back up.

## Your first minutes

A new journey opens like a story: five cards of what the Fading is, and then
you **wake in the grass** with Bram, the last keeper, standing over you. He
points you at two things — a dim hound lying where the road bends, and the
village gate. Find the hound and speak to it (**Q**) and **Lumi joins you**;
your companion is met, not issued.

From there the run teaches itself: a gold line along the bottom of the screen
names the next real thing to do — walk, speak to someone, find a gate, stand
on the recovery pad, open your pack (**Tab**), face a beast, take a turn,
answer the page — and waits for you to actually do it. The banners never press
anything for you, and once a lesson is learned it never comes back; the
sequence is stored with your run, not with the session.

The arc continues past the opening: face a marked animal, take your first
label off one, climb the Warden ladder, pledge to an order, **do its work** —
clear rooms in your order's own lands — go down through a cave, and find what
is at the middle of the dark. The run ends on a dawn told in your doctrine's
voice.

Every one of those beats completes because the run or the corpus says so, and
every one of them is written down in `data/story.json` rather than in code.

The settlements are inhabited and laid out like places rather than stamped like
tables. A section of two or three pages is a fenced **hamlet**; a middling one
is a walled **village** with a square, a well and a tavern; a large one — or any
Warden's seat — is a **town** with a market row, a lens-grinder, a shrine and
garden beds. Each has a place name of its own (Candlemere, Emberford) and is
known *for* its section.

**Keepers** stand outside pages somebody has reviewed — that population *is* the
review state. Around them live townsfolk who are not a metric at all, an
innkeeper who has heard things, a supplier with glass, a lens-grinder who will
narrow what you are wearing, a shrine-keeper who restores your team and writes
the day down, a **recovery warden** at the pad inside every gate, and — in three
particular lands — the emissaries of the orders.

## The three orders

Three orders disagree about what the **Marking** is, and choosing one decides
what counts as winning your run. You choose by **meeting them**, not from a
menu — and they will not take you seriously until you carry three seals:

- **Merel, Voice of Rigour** stands at a gate in The Great Library. Rigour
  holds that light which misleads is worse than dark.
- **Halden, Voice of Clarity** waits on The Pilgrim Road. Clarity holds that
  the light is fine and the doors have closed.
- **Sable, Voice of Discovery** keeps to the unlinked places. Discovery holds
  that the worst dark was never lit at all.

Talk to one (**Q**), hear their case out, and you will be asked to pledge.
Cancel walks away with the choice still open.

## Playing

1. **Walk to a dark building** and press **Q**. Only unread pages have guardians.
2. **Fight it.** Damage is the real spectral overlap of your beast's emission
   with the target's absorption, so a green donor is devastating against
   something absorbing at 560 nm and nearly useless against a blue absorber.
   Emitting **bleaches you**, and a high quantum yield costs more — the
   brightest label hits hardest and burns out soonest. **Who moves first is the
   animal's**: a hare goes before a boar whatever either of them is wearing.
3. **Unbind it** once it is worn down. A dye driven into its dark state comes
   away; a fresh one is welded in. You cannot unbind what your filter cannot
   see, and you cannot unbind above your licence.
4. **Answer the page's question.** Beating the guardian is spectroscopy; it says
   nothing about whether you read the page.
5. **Recover** at the station just inside any village gate — the warden there
   will tell you the same. Photon budgets carry between fights, so attrition
   across a run is the real difficulty. Beasts never pass a village wall: inside
   the gate, nothing fights you.

## Training mode and expert mode

The **MODE** tab carries the one switch that matters.

- **Training** — nothing is ever signed off. You are learning fluorescence, and
  answering a question about a page is not the same as having reviewed it.
- **Expert** — a correct answer marks the page reviewed, by you, as a human,
  through {doc}`the review system </development/documentation_maintenance>` rather
  than through anything the game invents.

Expert mode refuses in exactly the cases the review gate already refuses: a
wrong answer signs nothing, an unanswered question signs nothing, and a page
that **changed while you were in the encounter** is refused outright, because
signing off text nobody has now read is the stale approval the gate exists to
prevent.

## Saying what is wrong

Signing off says *this is fine*. In expert mode, **Q** at the question screen
says what is not: pick the sentence at fault, then one of eight faults —
undefined symbol, wrong units, missing citation, contradicts another page, stale
screenshot, dead link, unstated assumption, notation drift.

There is no typing, and that is deliberate. A span plus a category is *more*
useful than prose: it points at an exact sentence, it is machine-checkable, and
two people flagging the same problem file the same record.

**Nothing is ever written into `docs/`.** Findings pool in your own
`~/.chisurf` directory until you export them, and export refuses any finding
whose page has changed since you made it.

## Gear

Clearing a room yields a real optical part — a Chroma or Thorlabs filter with
its measured transmission curve. Fit it from the **RIG** tab, which assembles an
excitation filter, dichroic, emission filter and detector into a path whose
Förster radius is computed by the same
{doc}`light-path simulator </reference/plugins/lightpath_simulator>` the
instrument tools use.

A filter is not "+3 damage". It decides **what you can see**: a creature whose
band it blocks is not drawn on the map at all. Swap filters, walk back through
ground you have already cleared, and things appear that were always there.

## The lab bench

Dyes are cultured, not only caught. The **LAB** tab plants a collected
creature as a culture, and the culture matures on a **real-world clock** —
fluorescent-protein maturation genuinely takes tens of minutes to hours, so
the growth timer is a physical property, not an invented wait. Come back
later (the clock runs across sessions), harvest, and a fresh, unbleached copy
joins your collection. Planting never consumes the original: a creature is a
template, not an ingredient.

The other half of the farm is the map itself: a page that changes under its
sign-off **withers** — the brown, rotten building — and stays withered until
somebody re-tends it. Doc rot is crop rot, and it is visible from across the
world.

## Voices, questions, and why you can trust them

Every question is **grounded**: it quotes a sentence, and that sentence is
checked against the page before you are ever shown it. A quote that is not in
the source is discarded.

That check matters most when the questions come from a language model, which
will quote a page confidently and inaccurately — so the verification is code
rather than trust. The AI writer is **off by default**; turn it on in the
**MODE** tab. With it off, questions are generated from the page's own prose
with no model at all, so the game works offline.

Questions are cached under the page's content hash, so a page asks the same
thing every visit and asks something new the moment it changes.

Even with the model off, a page's keeper does not make small talk: after their
greeting they speak **from the page they keep** — its opening claim, then a
"Did you know?" sentence picked by the page's own address. No network, no
model; the lines are read straight out of the page's prose, so what a keeper
tells you is always something their page actually says.

The same switch also gives the inhabitants **voices**: with the model on, a
keeper speaks as someone who has read and vouched for their own page, an
emissary argues their doctrine, a smith complains about glass — each character
voiced from their own backstory. The same discipline applies as for
questions: every reply passes a gate in code (line count, length, no breaking
character), a refused reply falls back to the authored lines, voices are
fetched once and cached, and **nothing ever blocks a frame on the network** —
the first conversation uses the authored lines while the voice is found in
the background. The scripted opening (Bram, the dim hound) is never
model-voiced, so the story cannot drift.

## See also

- {doc}`Ask the documentation </guides/70_ask_the_documentation>` — the same
  corpus, queried instead of played.
- {doc}`FRET </concepts/fret>` — the physics the combat is built out of.
