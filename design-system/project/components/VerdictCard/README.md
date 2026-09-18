# VerdictCard

The standard container for a single result, shaped so the four-part answer is the path of least
resistance.

The four parts, in order: **state** (the chip), **meaning** (one plain sentence), **action**
(what to do, with a time frame), **evidence** (the provenance line). A card missing the meaning
or the action is not finished - it has handed the reader a number and left the interpretation to
them, which is exactly what this console exists to avoid.

## Rules

- `meaning` contains no metric names. Not "anomaly score 0.87" but "running 4.2 degrees above its
  setpoint while the others hold theirs". Name the physical thing that is wrong.
- `action` is imperative and time-bounded. "Inspect at next depot visit", not "consider
  investigating".
- `evidence` is set in mono and carries the score, **the split method**, and the model version.
  The split method is not optional: a number without its protocol is a claim the interface cannot
  support.
- `figure` takes any of the signature visuals. One figure per card. A result needing two figures
  needs two cards.

## What the consumer provides

All four strings and, optionally, a figure element. The card owns layout, spacing and the chip.
Do not put a second status inside the body - a card has exactly one verdict.
