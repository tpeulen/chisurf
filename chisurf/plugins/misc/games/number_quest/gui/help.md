# Number Quest

Choose a hidden integer from 1 to 100 in at most seven guesses. The lifetime
dial displays the estimate multiplied by 0.1 ns, and the curve is generated
from that estimate. It is a teaching game: there is no measured decay, fitted
lifetime, uncertainty estimate or experimental input file.

## Controls

- Hold Left/Right for fine steps of one; Q/E gives steps of ten. Release a key
  to stop its repeat.
- Click the decay plot to dial an estimate between 0.1 and 10.0 ns.
- Enter or Space submits the estimate. The left half of the lower footer also
  submits it; the right half starts a new round.
- R or Restart in the header starts a new round. The upper footer explains
  movement and provides hover help; it is not a pair of click buttons.
- Sound only works when an optional audio output has been supplied.

## Reading the round

The hint tells you whether to choose a longer or shorter lifetime. Turns left,
score and previous curves describe guesses in this round. After a win or loss,
submitting again starts another round. Opening Guide leaves the current round
alone; its steps wait for your Restart and Help clicks.

## State and sound

The native host can restore the hidden target, estimate, guess history and
window size. Switching games keeps the round; losing focus clears held keys
and repeat timing. The native game opens no audio output. A Python-supplied
output is silenced on focus loss without changing the saved Sound preference,
and released once when the game closes.

## Further reading

[Games: controls, native windows and saved rounds](docs/guides/95_games.md).
