# Pong

Return the ball with a paddle and score when the other side misses. The colour
and wavelength cues are game mechanics, not a fluorescence measurement or an
analysis result. The game supplies the court and round without external data.

## Controls

- Hold Up/Down (or Left/Right) to move the first paddle.
- Press M to switch between the computer opponent and two-player mode. In
  two-player mode, W/S moves the second paddle.
- Drag inside the appropriate half of the court to move that paddle; the second
  paddle is controlled this way only in two-player mode.
- P pauses or resumes; R or Esc restarts (Esc discards the current round, like R). After a winner is declared, Enter or Space
  starts another round.
- N changes the game's mute flag. Sound in the header controls a supplied audio
  output, when one is available.

## Reading the round

The score and rally describe this round only. Changing the opponent mode changes
who controls the second paddle; it does not load a different dataset. Restart
starts a fresh round. Guide waits for your Restart and Help clicks rather than
pressing them for you.

## State and sound

The native host can restore the saved round and window size. The Games window
keeps the round while you visit another game. Focus loss clears both players'
held and pending input. Sound is unavailable without an optional supplied audio
output. If one is supplied through Python, losing focus silences it without
changing the saved Sound preference; closing the game releases it once.

## Further reading

[Games: controls, native windows and saved rounds](docs/guides/95_games.md).
