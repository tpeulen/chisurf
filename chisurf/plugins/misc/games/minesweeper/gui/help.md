# Minesweeper

Reveal safe cells without exposing a mine. Adjacent counts describe the game
board; detector-array language is a visual theme, not a classification of real
pixels or a measurement of detector defects. The board is generated locally
and needs no acquisition file.

## Controls

- Use the arrow keys to move the selected cell; held directions repeat.
- Enter or Space reveals the selected cell. F toggles its flag.
- Left-click a cell to reveal it; right-click it to toggle a flag.
- M toggles the sound preference (audible only with an effects callback).
- Q/E selects the previous or next board preset. Clicking the preset name also
  cycles the difficulty. Changing the preset starts a new board.
- R, Esc or Restart in the header resets the round (the board is discarded). There is no pause control in
  this turn-based game.

## Reading the round

A revealed number counts adjacent mines. A flag is your annotation, not proof
that a cell contains a mine. Reveal the safe cells to finish; exposing a mine
ends the round. Guide points at Restart and Help and waits for your actions;
starting a tour does not reveal a cell or reset the board.

## State and sound

The native host can retain the board, revealed cells, flags, selection and
window size. The Games window keeps this round while you visit another game.
Losing focus clears repeated cursor movement. Native Minesweeper does not
create an audio output. A caller may supply an effects callback; it is not a
music backend and the guide does not activate it.

## Further reading

[Games: controls, native windows and saved rounds](docs/guides/95_games.md).
