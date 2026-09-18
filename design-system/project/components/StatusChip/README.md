# StatusChip

The atom every result is built from: a state rendered as colour, shape and word together.

Four states exist and no more: `ok`, `watch`, `alert`, `unknown`. If a subsystem seems to need a
fifth, it needs a second chip or a detail string, not a new state.

## Why the glyph is not decoration

Colour alone fails three ways this console actually meets: a reader with colour-vision
deficiency, a projected demo, and a printed or photographed screen. The glyph and the word each
carry the full meaning on their own, so any one of the three can be lost without losing the
result. Do not hide the word to save space - shorten the detail instead.

## Usage

- Pass `state`. Everything else is optional; the default word comes from the state.
- `label` overrides the word only when the subsystem has a better one. `Fault` is the default for
  `alert`, but Door says `Abnormal resistance` because that is the term used in the data.
- `detail` names the object, not the reasoning: `Car 03`, `Cycle 41`. One or two words.
- `unknown` is a real answer. Use it when a file could not be parsed or no model is loaded. Never
  fall back to `ok`.

## What the consumer provides

The state string, and any label or detail. The chip owns its colour, glyph, padding and shape,
and all of those come from tokens - do not restyle it locally.
