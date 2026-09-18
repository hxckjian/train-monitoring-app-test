"""The subsystem registry - the one place the app learns what exists.

Adding a fifth subsystem is one SubsystemSpec entry plus a package under
subsystems/ exposing predict(uploaded_files) and analyze(uploaded_files). No
page, route or schema elsewhere needs to change.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "repo" / "PS3" / "02_Datasets"


@dataclass(frozen=True)
class SubsystemSpec:
    key: str
    name: str
    question: str          # what it answers, in plain English
    predicts: str          # the unit of prediction
    method: str            # one line, for the model card
    accepts: tuple[str, ...]
    multi_file: bool
    package: str | None    # e.g. "subsystems.door"; None = not built yet
    test_glob: str         # relative to DATA_ROOT

    @property
    def artifact_dir(self) -> Path | None:
        if not self.package:
            return None
        return PROJECT_ROOT / Path(*self.package.split(".")) / "artifacts"

    @property
    def available(self) -> bool:
        d = self.artifact_dir
        return bool(d and (d / "config.json").exists())

    @cached_property
    def module(self) -> ModuleType | None:
        if not self.available:
            return None
        return importlib.import_module(f"{self.package}.predict")

    def model_card(self) -> dict | None:
        if not self.available:
            return None
        return json.loads((self.artifact_dir / "config.json").read_text(encoding="utf-8"))

    def test_inputs(self) -> list[Path]:
        return sorted(DATA_ROOT.glob(self.test_glob),
                      key=lambda p: (len(p.stem), p.stem))


SUBSYSTEMS: dict[str, SubsystemSpec] = {s.key: s for s in [
    SubsystemSpec(
        key="door", name="Door",
        question="Is any door opening or closing against abnormal resistance?",
        predicts="one verdict per detected door cycle",
        method="gap segmentation + random forest on per-cycle motor load",
        accepts=("csv",), multi_file=False, package="subsystems.door",
        test_glob="Door/Test.csv"),
    SubsystemSpec(
        key="shm", name="Structural health",
        question="How much fatigue damage has this structure accumulated?",
        predicts="cumulative damage per stress file (1.0 = end of fatigue life)",
        method="rainflow counting + Miner's rule, S-N constants fitted to labels",
        accepts=("csv",), multi_file=True, package="subsystems.shm",
        test_glob="SHM/Test/test*.csv"),
    SubsystemSpec(
        key="rail", name="Rail corrugation",
        question="Is either rail corrugated, and on which side?",
        predicts="Normal / Side I / Side II per 1-second recording",
        method="planned: wavelength-domain band energy per side, speed-normalised",
        accepts=("csv",), multi_file=True, package=None,
        test_glob="Rail_Corrugation/Test/Test*.csv"),
    SubsystemSpec(
        key="acv", name="Air conditioning",
        question="Which car's air conditioning is leaking refrigerant?",
        predicts="all 8 cars ranked from most to least likely faulty",
        method="planned: cooling-setpoint drift relative to the other cars",
        accepts=("xlsx",), multi_file=False, package=None,
        test_glob="ACV/Test/*.xlsx"),
]}
