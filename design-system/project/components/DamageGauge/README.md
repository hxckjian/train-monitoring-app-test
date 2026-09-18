# DamageGauge

A single cumulative-damage value against the scale that gives it meaning.

Fatigue damage is only interpretable against failure. Under the linear cumulative-damage rule,
failure is defined at `D = 1.0`, so the gauge always draws that threshold as a hard rule rather
than letting the bar float on an arbitrary axis. A reader who does not know what 0.412 means can
still see that it is not yet half way.

## Rules

- The fill uses the **sequential ramp**, not a status colour. Damage is a magnitude, not a state.
  If a value crosses an operational limit, put a `StatusChip` beside the gauge - do not recolour
  the bar and lose the ordering.
- `max` defaults to 1 and should stay there. Changing it silently rescales every gauge on screen
  and breaks comparison between files.
- The value is set in `metric-xl` mono so a live-updating figure does not reflow.
- The caption carries the validation protocol. Always.

## What the consumer provides

`value`, `max`, and the caption text. The gauge owns the ramp step, the threshold rule and the
scale labels.
