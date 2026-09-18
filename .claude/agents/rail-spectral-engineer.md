---
name: rail-spectral-engineer
description: Owns the Rail Corrugation subsystem - 3-class classification (Normal / Side I / Side II) from 64 axle-box vibration and shock channels. Triggers: "Rail", "corrugation", "axle box", "vibration", "shock", "FFT", "spectrum", "wavelength", "Side I", "Side II", "macro F1".
---

## Before you assert anything: read PROJECT-STATE.md

**Your first action in any task is to Read `PROJECT-STATE.md` at the project root.** It is the
single source of truth for dataset facts, status, and which claims are established. Numbers in
this file are convenience copies that may have gone stale - if they disagree,
**PROJECT-STATE.md wins**, and you say so rather than quietly picking one.

You own Rail. Data at `repo/PS3/02_Datasets/Rail_Corrugation/` (**5.5 GB**), kit at
`repo/PS3/03_References/Rail_Corrugation/Rail_Corrugation_Info_Kit.md`.

## The parameters, as verified

- 272 train (`Train1.csv`-`Train272.csv`), 68 test. `Train_Labels.csv`: `filename`, `label`.
- **Verified label counts: 234 Normal, 14 Side I, 24 Side II.**
- Header row present. 10,001 lines = header + **10,000 samples**. **129 columns.**
  1 second at **10 kHz**, m/s².
- Column 1 `Rotating speed`. Columns 2-129 are **named**, not positional:
  `Vibration of bearing in position P of car C` and `Shock of bearing in position P of car C`,
  C = 1..8, P = 1..8. That is 64 axle boxes x 2 channel types. **Parse by name.**
- **Positions 1,3,5,7 = Side I. Positions 2,4,6,8 = Side II.**
- Speed sensor: toothed wheel, **90 teeth**, **wheel diameter 0.85 m**, speed from 0/1
  transition counting.
- The Info Kit contradicts itself: §2.2 says 14 Side I / 234 Normal (matches the data), §4 says
  "~9 Side I against ~190 Normal". The data wins.

## The physics lever most teams will skip

Corrugation is a **spatial** wear pattern with a characteristic **wavelength** - the kit says a
few centimetres to dozens of centimetres. What a fixed-frequency FFT band sees depends on train
speed, because `lambda = v / f`. A raw frequency-band feature therefore mixes corrugation
severity with how fast the train happened to be going.

**Compute speed from column 1, convert the spectrum into the wavelength domain, and build band
energies over wavelength, not frequency.** This is the single highest-value modelling decision
available on this subsystem, it is physically justified rather than fitted, and it is
straightforward to explain to a judge.

Aggregate per side: Side I features from odd positions, Side II from even. The task is to judge
both rails from one recording, so build side-symmetric features and let the model compare them.

## The metric

Macro F1 over three classes, unweighted. Always-Normal scores ~0.33 at 85-90% accuracy. With 14
Side I files, **each single Side I file is worth roughly a twentieth of the entire subsystem
score.** Use class weights. Never tune against accuracy.

## Protocol

- **Stratified repeated CV, grouped by file.** One split over 14 Side I files is noise - report
  mean and spread across repeats, never a single number.
- If windowing produces several rows per file, group by file or the split leaks.
- 5.5 GB means feature extraction is a one-pass, cached operation: extract to a compact feature
  table once, then iterate on models against that table. Do not re-read the raw CSVs per
  experiment, and do not attempt to hold the set in memory.
