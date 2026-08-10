---
type: Guide
title: Reviewing the documentation as a game (Lumis Quest)
description: A top-down RPG whose map is ChiSurf's own documentation, whose creatures are real fluorophores, and whose expert mode signs pages off through the review gate.
tags: [guides, documentation, review, games, fluorophores, spectra]
---

# Reviewing the documentation as a game

Documentation review is a thankless job with no feedback loop: you read a page,
you tick a box, nothing happens. The queue sits stale and the docs drift.

**Lumis Quest** is that job with a game around it. The map *is* this
documentation — every building is a page, every walled compound a section — and
the creatures are real fluorophores read from the spectra database ChiSurf
ships. It teaches spectroscopy whether or not you ever review anything, and in
expert mode it signs pages off through ChiSurf's own review gate.

Open it from **Tools → Miscellaneous → Games → Lumis Quest**. The game opens
on a title screen: **Continue** resumes a saved run, **New Journey** starts
over (it asks before erasing a run), and the controls scheme can be switched
right there.

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

You play **Iris**, a probe photon; **Lumi**, a dog, trots behind her. You will
meet them again — they are the ball in Pong and the probe in Breakout.

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

The arc continues past the opening: pledge to an order, then **do its work** —
clear rooms in your order's own lands — and the run ends on a dawn told in
your doctrine's voice.

The villages are inhabited. **Keepers** stand outside pages somebody has
reviewed — that population *is* the review state. Around them live townsfolk
who are not a metric at all, a **recovery warden** at the pad inside every
gate, and — in three particular lands — the emissaries of the orders.

## The three orders

Three orders disagree about what the Fading is, and choosing one decides what
counts as winning your run. You choose by **meeting them**, not from a menu:

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
2. **Fight it.** Damage is the real spectral overlap of your creature's emission
   with the target's absorption, so a green donor is devastating against
   something absorbing at 560 nm and nearly useless against a blue absorber.
   Emitting **bleaches you**, and a high quantum yield costs more — the
   brightest creature hits hardest and burns out soonest.
3. **Collect it** once it is worn down. A dye driven into its dark state is
   easier to capture, and you cannot collect what your filter cannot see.
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
