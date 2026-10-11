# Audio credits

The music and sound effects chigame ships are by **Juhani Junkala**
(SubspaceAudio), released under **CC0 1.0 Universal (public domain)**.

CC0 requires nothing of us. This file exists anyway: a package that
redistributes somebody's work should say whose it is, in their own words, and
keep the licence statement it was given under next to the files.

## The author's statement, as shipped with the music

> Hi, I'm Juhani Junkala, the author of this music collection. I'm a
> classically trained composer, producer and a sound designer with over 20
> years of experience.
>
> These music tracks have been released under CC0 creative commons license.
> You can do anything you want with these tunes.
>
> Check out my game music portfolio: https://www.youtube.com/watch?v=dbACpSy9FWY
>
> If you need music or sound effects for your game, contact me:
> juhani.junkala@musician.org

## What is here

| File | Contents | Source |
|---|---|---|
| `music.zip` | 5 seamlessly looping tracks -- Level 1, Level 2, Level 3, Title Screen, Ending | [5 Chiptunes (Action)](https://opengameart.org/content/5-chiptunes-action) |
| `sfx.zip` | 512 retro sound effects in five categories: death screams, explosions, general, movement, weapons | [512 Sound Effects (8-bit style)](https://opengameart.org/content/512-sound-effects-8-bit-style) |

Both are CC0 on OpenGameArt. The author's wider catalogue is at
<https://opengameart.org/users/subspaceaudio>.

## What we changed

The sources are 44.1 kHz 16-bit WAV, 27 MB in total. They are shipped here as
mono, 22.05 kHz, IMA ADPCM (see `chisurf/gui/chigame/adpcm.py`), which is
**6.7 MB** -- the difference between a soundtrack that lives in the repository
and one that is a download step. The conversion is
`build_tools/dev_utils/pack_game_audio.py`; nothing was edited musically.
