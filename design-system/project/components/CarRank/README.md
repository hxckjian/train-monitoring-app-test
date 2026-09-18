# CarRank

Eight cars ordered from most to least likely to carry the fault, with the evidence behind the
ordering visible as bar length.

## Why a ranking and not a single answer

The scoring gives partial credit for being close: the true car ranked second still earns 0.875 of
the available credit, and a car left out of the ranking earns nothing. So the interface shows the
whole ordering, and the user can see the gap between first and second - a narrow gap is a
genuinely different message from a wide one, and highlighting a single car hides it.

## Rules

- **Every car is listed.** Omitting a car scores zero if it turns out to be the faulty one. The
  component draws what it is given, so give it all of them.
- Rank 1 takes `status-alert`; the rest take `series-1`. This is the one place a status colour
  meets a ranking, and it is deliberate: the top row is a verdict, the rows beneath are
  supporting evidence.
- Bars normalise to the top score, so the shape shows *relative* confidence. A near-tie looks
  like a near-tie.
- Car ids are the two-digit identifiers from the file's own headers - `03`, never `Car 3` and
  never an index. The submission format requires the same strings, so using them here keeps the
  screen and the CSV honest with each other.
- The caption should carry the random baseline. With eight cars a random ordering already scores
  0.5625, and a reader who does not know that will over-read the number.

## What the consumer provides

`cars` as `{id, score}`, already sorted best-first. The component does not sort - sorting is a
modelling decision and belongs upstream where it can be tested.
