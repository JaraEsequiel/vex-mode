"""One blinded judge pass over every run (pstack eval playbook, lines 12-13): sanitized labels, never a model name."""
import json
import re

SCHEMA = {
    "type": "object",
    "properties": {
        "runs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "pass": {"type": "boolean"},
                                "note": {"type": "string"},
                            },
                            "required": ["name", "pass", "note"],
                        },
                    },
                },
                "required": ["label", "criteria"],
            },
        }
    },
    "required": ["runs"],
}

HEADER = (
    "You are grading {n} anonymous agent runs. Each run got the same user request in its own copy of a small "
    "project. For every run, decide pass or fail on each criterion below, with a one-sentence note that cites "
    "what you saw in that run's material. Grade each run on its own; do not use tools.\n\n"
    "# Criteria\n\n{rubric}\n\n# Runs\n"
)


def build_prompt(rubric: str, items: list[tuple[str, str]]) -> str:
    body = "".join(f"\n## {label}\n\n{material}\n" for label, material in sorted(items, key=lambda i: int(i[0][1:])))
    return HEADER.format(n=len(items), rubric=rubric.strip()) + body


def criteria_count(rubric: str) -> int:
    return sum(1 for line in rubric.splitlines() if re.match(r"\s*\d+\.\s", line))


def compliance(verdict: dict, label: str) -> float | None:
    for run in verdict.get("runs", []):
        if run.get("label") == label:
            criteria = run.get("criteria") or []
            if not criteria:
                return None
            return sum(1 for c in criteria if c.get("pass") is True) / len(criteria)
    return None


def label_problems(verdict: dict, labels: list[str], n_criteria: int) -> dict[str, str]:
    """Per expected label, why its grade cannot be trusted (missing, duplicated, wrong criterion count)."""
    seen: dict[str, int] = {}
    problems = {}
    for run in verdict.get("runs", []):
        label = run.get("label")
        seen[label] = seen.get(label, 0) + 1
        if label in labels and len(run.get("criteria") or []) != n_criteria:
            problems[label] = f"{len(run.get('criteria') or [])} criteria, expected {n_criteria}"
    for label in labels:
        if seen.get(label, 0) == 0:
            problems[label] = "no grade"
        elif seen[label] > 1:
            problems[label] = "graded twice"
    return problems


def check_verdict(verdict: dict, labels: list[str], n_criteria: int) -> str | None:
    problems = label_problems(verdict, labels, n_criteria)
    unknown = sorted({str(r.get("label")) for r in verdict.get("runs", [])} - set(labels))
    parts = [f"{l}: {why}" for l, why in sorted(problems.items(), key=lambda i: int(i[0][1:]))]
    if unknown:
        parts.append(f"unknown labels {unknown}")
    return "; ".join(parts) or None


def parse_output(stdout: str, schema: dict = SCHEMA) -> tuple[dict | None, str | None]:
    from .judges import conforms
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        return None, f"judge output is not JSON ({e})"
    if not isinstance(data, dict):
        return None, "judge output is not a JSON object"
    verdict = data.get("structured_output")
    if not isinstance(verdict, dict):
        return None, f"judge returned no structured_output (status {data.get('status')})"
    if not conforms(verdict, schema):
        return None, "judge returned a malformed run entry"
    return verdict, None
