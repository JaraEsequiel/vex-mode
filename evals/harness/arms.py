"""The three fixed arms of every eval (design §8.2, cursor/plugins#1178): one lever per comparison."""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "checks"))

from _util import model_family  # noqa: E402


@dataclass(frozen=True)
class Arm:
    label: str
    plugin_ref: str | None  # None: no plugin at all (calibration)
    model: str


def build_arms(case: dict, base_ref: str, variant_ref: str, judge: str) -> list[Arm]:
    candidate, upgrade = case["candidate_model"], case["upgrade_model"]
    taken = {model_family(candidate), model_family(upgrade)}
    if model_family(judge) in taken:
        raise ValueError(f"judge {judge} shares a model family with a candidate ({sorted(taken)})")
    return [
        Arm("A", base_ref, candidate),
        Arm("B", variant_ref, candidate),
        Arm("C", base_ref, upgrade),
    ]


def calibration_arms(case: dict, base_ref: str, judge: str) -> list[Arm]:
    """The base plugin against no plugin on the same model: does the case measure the plugin at all?"""
    candidate = case["candidate_model"]
    if model_family(judge) == model_family(candidate):
        raise ValueError(f"judge {judge} shares a model family with the candidate ({candidate})")
    return [Arm("A", base_ref, candidate), Arm("N", None, candidate)]
