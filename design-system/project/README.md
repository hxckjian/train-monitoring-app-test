# Nebula Wayside

The design system for a train condition-monitoring console. It covers four unrelated
subsystems — structural fatigue, door mechanisms, rail corrugation and air conditioning — that
must read as one product rather than four notebooks stitched together.

*Wayside* is the rail term for trackside equipment that watches passing trains. That is what
this interface is: something that observes, reports what it saw, and says what to do about it.

## Who reads this

A maintenance planner, not a data scientist. They are deciding whether to pull a car out of
service tonight. They will not read a confusion matrix and they should not have to.

Everything here follows from that one fact.

---

## Content fundamentals

### Every result answers four questions, in this order

1. **What is the state?** A status word: *Normal*, *Watch*, *Fault*, *Unknown*.
2. **What does that mean?** One sentence of plain English. No metric names.
3. **What should I do?** A recommended action with a time frame.
4. **Why should I believe it?** The evidence — the signal, the score, the split method.

A screen that shows a number and stops has not delivered a result. `VerdictCard` exists to make
the four-part answer the path of least resistance.

### Say the thing, then qualify it

> **Fault — Car 03 air conditioning**
> Car 03 has been running 4.2 °C above its cooling setpoint while the other seven cars hold
> theirs. That pattern is consistent with a refrigerant leak.
> **Inspect Car 03 refrigerant charge at next depot visit.**

Not: *"Anomaly score 0.87 exceeds threshold 0.5 for unit index 2."*

### Numbers carry their uncertainty, always

A cross-validated score appears with the protocol that produced it, in `caption`:

> Damage 0.412 · MAPE 8.1% on 5-fold CV, constants fitted in-fold · model `shm-v3`

An unqualified number is a claim the interface cannot support. If the protocol is weak, say so
in the caption rather than omitting it — this system treats a visible limitation as a feature,
because a reviewer who can see the protocol can trust the number.

### Words this system uses

| Use | Not |
|---|---|
| Fault | Anomaly, outlier, positive |
| Watch | Warning, caution, yellow |
| Normal | Healthy, negative, OK (in body text) |
| Unknown | N/A, null, error |
| Car 03 | Unit 2, index 2, car_03 |
| Cycle | Segment, window, event (in user-facing text) |

`Unknown` is a real state, not a failure to render. A file that could not be parsed, a model
that is not loaded, a case out of scope — all are `Unknown`, in `status-unknown` grey, with the
reason given. Never show a default `Normal` for something the system did not actually assess.

---

## Visual foundations

### Colour has exactly four jobs

Each job has one ramp and they never borrow from each other.

| Job | Tokens | Rule |
|---|---|---|
| **State** | `status-ok` `status-watch` `status-alert` `status-unknown` | Reserved. Never reused as a chart series. |
| **Identity** | `series-1`…`series-4` | Fixed order, never cycled. No fifth. |
| **Magnitude** | `ramp-1`…`ramp-5` | One hue, ordered by lightness. |
| **Structure** | surfaces, lines, ink | Carries no data meaning at all. |

`subsystem-shm`, `subsystem-door`, `subsystem-rail` and `subsystem-acv` alias the series tokens
for navigation and page headers. They are branding, not encoding — a subsystem colour must never
appear inside a chart that encodes severity, or the reader will read identity as state.

### The palette is computed, not chosen

Every value above was checked with the same six-check validator, against
`surface-page` in both themes: OKLCH lightness band, chroma floor, CVD separation under
Machado-Oliveira-Fernandes protan and deutan simulation, a normal-vision floor, and WCAG contrast.

Two results are worth recording, because they overrode the obvious choice:

- **The alert colour is a true red, not an orange.** A green/amber/orange traffic light — the
  instinctive choice — separates by only ΔE 1.2 under simulated CVD between amber and orange,
  and only 8.4 even in full colour vision. That is a hard failure: roughly 1 in 12 men could not
  read the difference between *Watch* and *Fault*, and nor could anyone else at a glance.
  Moving alert to `#b3121f` lifts the worst pair to 20.8.
- **Amber is darker than it looks like it should be.** `status-watch` was pushed to `#bb8000`
  to clear 3:1 against white. The brighter amber everyone reaches for sits at 2.25:1.

Re-run the validator before adding any colour. Do not reason about ΔE by eye.

### Colour is never the only signal

Every status carries **a shape and a word** alongside its colour: a filled dot, an open ring, a
cross, a dash. `StatusChip` enforces this. A chart with two or more series has a legend, and
four or fewer are also directly labelled. This is not only an accessibility rule — a console
gets photographed, projected, and printed in black and white, and it has to survive all three.

### Typography

Two families. **IBM Plex Sans** for everything a person reads, **IBM Plex Mono** for everything
a machine produced. The split is the point: a reader can tell at a glance which numbers came out
of a model and which are labels.

Mono is not a style choice for figures — a live damage value that updates every second must not
reflow the layout as digits change width. All numbers in tables use `tabular` and are
right-aligned so decimal points line up.

### Density

The console is read at arm's length on a laptop, sometimes on a tablet in a depot. `space-4` is
the minimum side gutter at any width. Cards use `space-5`. Nothing smaller than `body-sm` is
used for anything a decision depends on; `caption` is for provenance only.

### Elevation

Prefer a `line-hairline` border to a shadow. `shadow-card` is a whisper; `shadow-pop` is for
things that genuinely float — tooltips and menus. A flat, bordered interface photographs better
and reads more like instrumentation than like marketing.

---

## Charts

Full rules in **`charts.md`**. The short version:

- **One axis.** Never two y-scales. Two measures of different scale become two charts or one
  indexed to a common base.
- **Thin marks, recessive grid.** `stroke-mark` for lines, `line-hairline` for grid.
- **A 2px `surface-*` gap** between adjacent fills and a 2px ring on overlapping marks, so
  neighbouring segments never merge into one block.
- **Selective direct labels.** Never a number on every point.
- **Text wears ink tokens, never the series colour.** The mark beside the label carries identity.
- **Hover by default.** A crosshair and tooltip on line and area, per-mark tooltip on bar and
  cell. A bare stat tile is the only thing that skips it.
- **Downsample long signals** before plotting. The Door stream is 18,037 rows and a single Rail
  file is 10,000 samples across 128 channels — plot a reduced envelope, not every point.

---

## Iconography

Line icons, 1.5px stroke on a 20px grid, drawn from the same geometry as the components — the
radii are `radius-sm` and `radius-md`, the terminals are square. Icons take `ink-secondary`
unless they sit inside a status chip, where they take that status token.

The system ships no icon set yet. Until it does, use text labels rather than approximating
marks — an invented icon is worse than a word.

---

## Components

| Component | What it is for |
|---|---|
| `StatusChip` | State as colour **plus** shape **plus** word. The atom every result is built from. |
| `VerdictCard` | The four-part answer: state, meaning, action, evidence. |
| `DamageGauge` | A single magnitude against a scale, for SHM cumulative damage. |
| `DoorTimeline` | A continuous stream cut into classified segments. |
| `AxleGrid` | 8 cars × 8 axle-box positions, split Side I / Side II. |
| `CarRank` | Eight cars ranked by likelihood, for ACV fault localisation. |

Each has a preview and its own guidelines. Read a component's page before using it.

---

## Adding to this system

- A new colour is validated before it is added, in both themes.
- A new component states what the **consumer** provides and what the component owns.
- Every token carries a usage note. A token without one is undocumented, and an undocumented
  token gets misused within a week.
- A new subsystem should need a new `subsystem-*` alias and nothing else. If it needs new
  structural tokens, the system is wrong, not the subsystem.
