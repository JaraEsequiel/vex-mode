"""The quality judge (design §8.2.1): one isolated call per dimension (Anthropic, "Demystifying evals"; RuVerBench:
batching rubrics hurts), 3 votes each (RuVerBench: gains mostly within 3-5 votes), pass/fail/unknown."""
import json
import random
from pathlib import Path

from . import judges

DIMENSIONS = {
    "reuse": "Does the patch reuse what the project already had (functions, helpers, constants) instead of "
             "duplicating that logic?",
    "simplicity": "Is the patch the simplest change that solves the request, with no abstraction, configuration or "
                  "generality nobody asked for?",
    "contract": "Do existing callers of what the patch changed keep working (signatures, accepted types, return "
                "types), unless the request required otherwise?",
}
VOTES = 3
SCHEMA = {
    "type": "object",
    "properties": {"runs": {"type": "array", "items": {
        "type": "object",
        "properties": {"label": {"type": "string"},
                       "vote": {"type": "string", "enum": ["pass", "fail", "unknown"]},
                       "note": {"type": "string"}},
        "required": ["label", "vote", "note"]}}},
    "required": ["runs"],
}
HEADER = (
    "You are reviewing {n} anonymous patches. Each one tried to solve the same request in its own copy of a small "
    "project. Answer the one question below for every patch, judging each on its own. Vote pass or fail, or unknown "
    "when the material is not enough to decide, and add a one-sentence note that cites what you saw. Do not use "
    "tools.\n\n# Question\n\n{question}\n\n# Context\n\n{context}\n\n# Patches\n"
)


def tally(votes: list[str | None]) -> float | None:
    """1.0 or 0.0 when at least 2 votes agree on pass or fail; None otherwise (unknown counts for nothing)."""
    for vote, value in (("pass", 1.0), ("fail", 0.0)):
        if votes.count(vote) >= 2:
            return value
    return None


def _prompt(question: str, context: str, items: list[tuple[str, str]]) -> str:
    body = "".join(f"\n## {label}\n\n```diff\n{patch}\n```\n" for label, patch in items)
    return HEADER.format(n=len(items), question=question, context=context.strip()) + body


def grade(patches: dict[int, str], context: str, cfg: dict, run_dir: Path,
          rng: random.Random) -> tuple[dict[int, dict[str, float | None]], list[str], dict]:
    """Per run, judge_<dimension> -> 1.0, 0.0 or None; plus every vote's error and the summed token usage."""
    values = {slot: {} for slot in patches}
    errors: list[str] = []
    usage: dict[str, int] = {}
    for dim, question in DIMENSIONS.items():
        votes = {slot: [] for slot in patches}
        for n in range(1, VOTES + 1):
            order = list(patches)
            rng.shuffle(order)
            labels = {f"Q{i}": slot for i, slot in enumerate(order, 1)}
            prompt = _prompt(question, context, [(label, patches[slot]) for label, slot in labels.items()])
            cwd = run_dir / "quality-judge" / f"{dim}-{n}"
            cwd.mkdir(parents=True, exist_ok=True)
            (cwd / "prompt.md").write_text(prompt)
            (cwd / "labels.json").write_text(json.dumps(labels))
            verdict, error, used = judges.judge(prompt, SCHEMA, cfg, cwd)
            (cwd / "verdict.json").write_text(json.dumps(verdict, indent=2) if verdict else "null")
            for k, v in used.items():
                usage[k] = usage.get(k, 0) + (v or 0)
            got: dict[str, list[str]] = {}
            for run in (verdict or {}).get("runs", []):
                got.setdefault(run["label"], []).append(run["vote"])
            problems = [f"{l}: no vote" for l in labels if l not in got]
            problems += [f"{l}: voted {len(v)} times" for l, v in got.items() if l in labels and len(v) > 1]
            problems += [f"unknown label {l}" for l in got if l not in labels]
            if error or problems:
                errors.append(f"judge_{dim} vote {n}: {error or '; '.join(problems)}")
            for label, slot in labels.items():
                ok = not error and len(got.get(label, [])) == 1
                votes[slot].append(got[label][0] if ok else None)
        for slot in patches:
            values[slot][f"judge_{dim}"] = tally(votes[slot])
    return values, errors, usage
