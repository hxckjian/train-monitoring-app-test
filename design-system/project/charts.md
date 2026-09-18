# Charts

The console shows four unrelated subsystems. If each one invents its own chart conventions, the
product reads as four notebooks. These rules are what make eight visuals look like one system.

## Pick the form from the job, not the data type

| The reader needs to... | Form |
|---|---|
| know one number, and whether it is bad | a stat tile or `DamageGauge` — not a chart |
| compare magnitude across a few named things | horizontal bars, sorted by value |
| see where events fall in a stream | `DoorTimeline` |
| find which of many cells is hot | `AxleGrid` heatmap |
| see a signal over time | line, downsampled |
| see energy across frequency or wavelength | line or area, log x |

Ask whether it needs to be a chart at all. "MAPE 8.1%" is a sentence, not a bar.

## One axis, always

Never two y-scales. Two measures of different scale become two stacked charts sharing an x-axis,
or one chart with both series indexed to a common base. Motor current and door position are the
standing temptation here — plot them as two aligned panels, not one chart with a right-hand axis.

## Colour

Follow the four jobs in the README. Inside a chart:

- **Categorical** — `series-1`…`series-4` in fixed order, assigned to the entity and never to its
  rank. A filter that removes a series must not repaint the survivors.
- **Sequential** — `ramp-1`…`ramp-5`. One hue, ordered by lightness, for magnitude only.
- **Status** — reserved. A series is never coloured `status-alert` because it happens to be the
  bad one; if a mark encodes state, it is a status mark, and it carries a label too.
- **Text wears ink tokens.** Values, axis labels and legend text take `ink-primary`,
  `ink-secondary` or `ink-muted` — never the series colour. The mark beside the label carries
  identity.

There is no fifth categorical colour. A fifth series folds into "Other", becomes small multiples,
or the chart is answering too many questions at once.

## Marks

- Lines at `stroke-mark` (2px); the one emphasised series at `stroke-emph`.
- Bars get a `radius-sm` cap on the data end only, square at the baseline.
- Markers at least 8px so they are reachable on a tablet.
- **A 2px `surface-plot` gap between adjacent fills** — stacked segments, neighbouring bars,
  heatmap cells, timeline segments. Without it, two adjacent same-ish values merge into one shape
  and the reader loses the count.
- A 2px `surface-plot` ring on any mark that overlaps another.

## Grid and axes

Recessive. `line-hairline` at `stroke-hairline`, and only on the axis the reader must measure
against. No box frame, no vertical and horizontal grid together unless the chart is genuinely a
matrix. Tick labels in `axis` mono, `ink-muted`.

Start bar axes at zero. Line axes may be cropped, but say so in the caption.

## Labels

Selective direct labels, never a number on every point. Label the first, the last, the extreme,
and anything the prose refers to. Two or more series always get a legend; four or fewer also get
direct labels, so identity never rests on colour alone. A single series needs no legend — the
title names it.

## Interaction

Hover is not an enhancement here, it is how a 64-cell grid or a 110-segment timeline is read.

- Line and area: crosshair plus tooltip.
- Bar, dot, cell, segment: per-mark tooltip naming the entity, its value and its units.
- Hit targets larger than the mark.
- Filters in one row above the chart, never inside it.

Every chart also has a table view. It is the fallback for screen readers, for anyone who needs
the exact number, and for the print case.

## Long signals

Nothing here is small. The Door stream is 18,037 rows; a single Rail file is 10,000 samples
across 128 channels; an SHM file is over half a million rows. Never hand raw arrays to a chart.

Downsample to a reduced envelope — min and max per pixel column, so spikes survive — before
rendering, and say in the caption that the view is reduced. A chart that silently drops the peak
of a stress signal is worse than no chart.

## Captions carry provenance

Every figure that shows a model output carries a `caption` line in mono: the score, **the split
method**, and the model version.

> `macro F1 0.79 ± 0.06, stratified repeated CV grouped by file · model rail-v5`

The spread is not optional. A single fold number over 14 rare-class files is noise, and a caption
that hides that is the interface telling a lie on the model's behalf.

## Dark mode is chosen, not flipped

Every palette in this system has its own dark steps, validated against `surface-page` in dark —
not lightened automatically. When adding a colour, validate both themes before shipping either.
