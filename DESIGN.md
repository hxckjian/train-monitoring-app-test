# Design method and architecture

How the console is organised, which products it borrows from, and why.

## 1. The shape of the product

One screen answers "is this train healthy, and what do I do next"; every other
screen is a drill-down from it.

```
Dashboard  ──►  Fleet view  ──►  Subsystem page  ──►  Inspector  ──►  Raw table / CSV
(status strip,  (map + live      (verdict card,       (one cycle,     (download passes the
 top events,     alerts)          evidence charts)     file or car)    schema validator)
 trends, zones)
```

This is the same ladder that fleet-maintenance products use. Alstom's HealthHub
presents a real-time fleet condition board and then drills into each asset
([Alstom](https://www.alstom.com/press-releases-news/2023/2/healthhub-intelligent-way-improve-maintenance)).
Siemens describes Railigent as one dashboard to manage the fleet and the depot
across a region, with per-bogie health states beneath it
([Siemens](https://www.siemens.com/en-us/company/insights/rxx-ai/)).

## 2. Three interface rules

Taken from Apple's Human Interface Guidelines
([design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles))
and applied literally:

| Rule | What it means here |
|---|---|
| **Clarity** | A verdict is a sentence, not a number. Colour never carries state alone: chip = colour + glyph + word. |
| **Deference** | Chrome is quiet (hairline borders, one accent per subsystem). Data and the map carry the visual weight. |
| **Depth via progressive disclosure** | Status strip → verdict → evidence → inspector → table. Nothing advanced is visible until the previous layer is understood ([progressive disclosure](https://en.wikipedia.org/wiki/Progressive_disclosure)). |

Two rules of our own:

- **Every number regenerates from data.** Scores on screen are read from each
  model's `artifacts/config.json`, which the training script wrote. Nothing is typed.
- **Live context stays outside the models.** LTA DataMall and the SGMRT channel
  inform the maintenance decision; they never feed a prediction.

## 3. Architecture

```
design-system/tokens.json ──► app/theme.py ──► CSS + chart palette
app/streamlit_app.py   pages only, no modelling
   ├── core/registry.py           what exists, SubsystemSpec per subsystem
   │     └── subsystems/<key>/    predict() · analyze() · artifacts/{model, config.json}
   ├── core/submission.py         official schemas, validator, zip builder
   ├── app/insight.py             zones, line paths, events, trends (pure functions)
   ├── app/livemap.py             station GeoJSON, LTA + SGMRT feeds (fail-soft)
   └── subsystems/generic/        label-free parameter monitor for new datasets
scoring/metrics.py                 the four official formulas, tested against Info Kit examples
```

Adding a subsystem is one `SubsystemSpec` plus a package with the two functions.
The dashboard, validation, fleet and submission pages discover it.

## 4. Validation discipline (what "accuracy" means on this console)

| Subsystem | Split | Why that split |
|---|---|---|
| Door | 5 contiguous time blocks | rows inside a cycle are near-duplicates; random rows would leak |
| SHM | 5-fold by file, S-N constants fitted inside each fold | the fit is the model; fitting on all files then scoring is leakage |
| Rail | 5 stratified grouped folds, duplicate feature rows grouped | two files are identical; augmentation applied inside training folds only |
| ACV | leave-one-case-out | six cases; a fixed rule with no parameters cannot be tuned to them |

Reported as mean ± standard deviation across folds, next to a naive baseline
and, where a fit exists, the in-sample score. The Validation page draws all four.
Model changes go through a pre-registered experiment
(`scripts/rail_wavelength_experiment.py` is the template): the decision rule is
written before the run and a null result is kept as a null result.

## 5. Colour and zones

- Status: ok / watch / alert / unknown from the design system, validated for
  colour-vision deficiency (the alert is a true red for that reason).
- Lines: official MRT line colours for paths on the map.
- Zones: five planning regions (Central, North, North-East, East, West), a
  distinct categorical palette, approximated from station coordinates.
- Magnitude (damage, energy) uses the sequential ramp, never a status colour.

## 6. Sources

- Alstom HealthHub: https://www.alstom.com/press-releases-news/2023/2/healthhub-intelligent-way-improve-maintenance
- Siemens Railigent / Railigent X: https://www.siemens.com/en-us/company/insights/rxx-ai/
- Apple Human Interface Guidelines, design principles: https://developer.apple.com/design/human-interface-guidelines/design-principles
- Progressive disclosure: https://en.wikipedia.org/wiki/Progressive_disclosure
- Condition monitoring of railway infrastructure (review): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10857274/

## 7. What the fleet products do, and what this console took from them

A short review of the commercial fleet-health platforms, and the features adopted.

| Product | Idea | Adopted here |
|---|---|---|
| Alstom HealthHub ([source](https://www.alstom.com/press-releases-news/2023/2/healthhub-intelligent-way-improve-maintenance)) | one real-time fleet board, drill-down per asset, predicts component failures to raise availability | Dashboard → Fleet view → subsystem page ladder; SHM remaining-life forecast |
| Siemens Railigent X ([source](https://www.siemens.com/en-us/company/insights/rxx-ai/)) | health states per bogie, one dashboard for fleet and depot across a region | health index per train with a Door/Structure/Rail/Air-con cell strip; zones on the map |
| Hitachi Rail with Perpetuum ([source](https://railway-news.com/hitachi-rail-completes-acquisition-of-perpetuum/)) | on-board sensor data turned into maintenance work, availability and reliability | every verdict becomes a logged event with time, train and place; work queue with acknowledge / close |
| Predictive-maintenance practice ([source](https://railwayacademy.org/digital-transformation-in-rolling-stock-maintenance-from-reactive-to-predictive/)) | move from reactive to condition-based maintenance: alarms with ownership, trends, thresholds | open / acknowledged / closed workflow, time-range trends, watch and alert bands stated on screen |
| Commuter-facing SG apps on DataMall ([sg-rail-crowd](https://github.com/cheeaun/sg-rail-crowd), [MRTracker](https://github.com/umiyuikaiteitan/Singapore-MRTracker)) | live platform crowd density and service alerts drawn on the network | DataMall PCDRealTime crowd rings and TrainServiceAlerts station rings on the fleet map, given the user's AccountKey |

The one idea deliberately not copied is a single opaque "AI health score" with no
trail. The health index here is an arithmetic of logged events, each of which
links back to the file, the verdict and the model card that produced it.

**"New data" menu.** The parameter-monitor page is the on-ramp for a subsystem
that has no model yet: the same peer-comparison and robust-drift screens the
validated models rest on, applied to any export, with the recipe for promoting
it to a full subsystem once labels exist.


## 8. Operator UX: what the standards say, and what changed

Sources: [EEMUA 191 / ISA-18.2 alarm management](https://industrialmonitordirect.com/blogs/knowledgebase/industrial-alarm-system-standards-iec-62682-isa-182-and-eemua-191),
[ISA-18.2 vs EEMUA 191](https://www.merobix.com/blog/isa-18-2-vs-eemua-191),
[High Performance HMI principles](https://industrialmonitordirect.com/blogs/knowledgebase/high-performance-hmi-design-principles-and-implementation-guide),
[Honeywell ASM: operator situation awareness](https://process.honeywell.com/content/dam/process/en/documents/document-lists/doc_asm-consortium/white-papers/March%2031%202015%20-%20Operator%20Situation%20Awareness%20and%20Delivering%20ASM%20compliant%20High%20Performance%20HMIs%20Failure%20Modes%20and%20Success%20Factors.pdf),
[dashboard design principles](https://uxpilot.ai/blogs/dashboard-design-principles).

| Principle | Applied as |
|---|---|
| Every alarm has a defined operator response, prioritised by consequence and time to act (ISA-18.2) | `core/decisions.py`: each verdict maps to one action with Now / Today / This week / Routine, a reason and an owner |
| Acknowledge, shelve for a bounded time, keep shelved alarms visible and logged (EEMUA 191, 4 h) | work queue: Acknowledge, Shelve 4 h (auto-unshelve, listed under Shelved), Close; every action timestamped |
| Alarm load should stay under about 10 new alarms per 10 minutes (EEMUA 191) | the queue shows new alarms in the last 10 minutes and flags the guideline when exceeded; duplicates are never logged |
| Level 1 overview for situation awareness, Level 2 to act, Level 3 for detail (High Performance HMI) | Dashboard → subsystem page → per-item inspector; navigation grouped as Overview / Check a train / Evidence |
| Perception, comprehension, projection (ASM) | status pills, plain-language reasons, SHM remaining-life and "getting worse" insights |
| Top row KPIs, trends in the middle, tables at the bottom; operational dashboards serve immediate decisions | dashboard order: hero verdict → actions → work queue → map and trends → tables |
| Reduce cognitive load; hide detail until needed | Operator view hides evidence charts; Engineer view shows them; "How to read this" on every subsystem |
