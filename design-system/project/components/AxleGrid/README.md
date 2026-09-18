# AxleGrid

Sixty-four axle boxes arranged the way the train actually is: eight cars across, eight positions
down, **split into two bands because the two rails are judged independently**.

Positions 1, 3, 5 and 7 sit on the Side I rail; 2, 4, 6 and 8 on Side II. Drawing them as one
8x8 block would be physically truthful and analytically useless - the whole task is to decide
which *side* is corrugated, so the layout does that grouping for the reader before they think
about it. In the preview above Side I reads hot and Side II cool: that is what a Side I
classification looks like.

## Rules

- Cells take the **sequential ramp**, because band energy is a magnitude. The side label and the
  verdict chip carry the state.
- 2px `surface-plot` stroke between cells, so a hot run of neighbours does not merge into a slab.
- Hover gives car, position, side and value. With 64 cells, hover is the only way to read an
  individual box, so it is mandatory.
- Missing channels draw as `surface-sunken`, not as zero. A dead sensor is not a quiet one, and
  showing it as the lowest ramp step would be a lie.

## What the consumer provides

`cells` as `{car, position, value}` with **value normalised to 0-1**. Normalise for train speed
before passing: raw band energy scales with how fast the train was going, so an unnormalised grid
mostly visualises speed. The component owns the banding, the ramp and the labels.
