# Breakout

Keep the ball in play with the paddle and clear the coloured bricks. The
spectrum and colour effects are game rules: they do not measure a sample or
analyse experimental photons. A round is generated inside the game; no file or
external data is needed.

## Controls

- Hold Left/Right to move the paddle. Release the key to stop movement.
- Press Space or Enter to launch a ball that is resting on the paddle.
- Drag inside the playfield to move the paddle; a resting ball moves with it.
- Press P to pause or resume, R to restart, and M to change the game's mute flag.
- Restart in the header starts a fresh round through the same reset behavior.

## Reading the round

Score, level and remaining lives describe progress in this game. Losing a ball
costs a life; clearing bricks advances play. The wavelength colours and brick
health are part of the challenge, not calibrated intensity or lifetime results.
Help explains the controls; Guide points at Restart and Help and waits for you
to press them. Starting the guide does not start a new round.

## State and sound

The native host can retain the round and window size. Moving to another game
in the Games window keeps this game instance alive. Losing focus clears held
movement, so the paddle does not keep moving after switching windows.
The native Breakout surface does not provide audio output; changing its mute
flag does not create an audio backend.

## Further reading

[Games: controls, native windows and saved rounds](docs/guides/95_games.md).
