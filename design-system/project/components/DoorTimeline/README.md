# DoorTimeline

The Door subsystem is handed one continuous stream, not pre-cut examples, so the first thing the
interface must show is **where the model decided the cycles were**. This component is that
answer.

## Why the gaps matter

The empty track between segments is data, not padding. It is the time the door spent doing
nothing, and it is what the segmenter used to find boundaries in the first place. Never stretch
segments to fill the track and never draw them evenly spaced - a reader checking for
over-segmentation needs to see the real spacing.

## Rules

- Segments take **status** colours, because normal versus abnormal resistance is a state.
- Each segment carries a 2px `surface-plot` stroke so two adjacent cycles never merge into one
  block. This is the standard surface gap from the chart rules.
- Hover gives the segment id, its label and its time range. This is the primary way a user checks
  a suspicious cycle, so it is not optional.
- Show the count in the label. "7 cycles found in 180 s" is the single most useful sanity check a
  user can perform on a segmenter, and it costs one string.

## What the consumer provides

`segments` as `{id, start, end, status}` in seconds from the stream origin, plus `duration`. The
component owns scaling, colour and the axis. It draws every segment it is given, so reduce
upstream if the stream is long.
