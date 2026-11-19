"""The three fixed arms of every eval (design §8.2, cursor/plugins#1178): one lever per comparison."""
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "checks"))

from _util import model_family  # noqa: E402


@dataclass(frozen=True)
class Arm:
    label: str
    plugin_ref: str
    model: str


def build_arms(case: dict, base_ref: str, variant_ref: str) -> list[Arm]:
    candidate, upgrade, judge = case["candidate_model"], case["upgrade_model"], case["judge_model"]
    taken = {model_family(candidate), model_family(upgrade)}
    if model_family(judge) in taken:
        raise ValueError(f"judge {judge} shares a model family with a candidate ({sorted(taken)})")
    return [
        Arm("A", base_ref, candidate),
        Arm("B", variant_ref, candidate),
        Arm("C", base_ref, upgrade),
    ]
