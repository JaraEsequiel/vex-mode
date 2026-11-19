"""One blinded judge pass over every run (pstack eval playbook, lines 12-13): sanitized labels, never a model name."""
import json

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


def compliance(verdict: dict, label: str) -> float | None:
    for run in verdict.get("runs", []):
        if run.get("label") == label:
            criteria = run.get("criteria") or []
            if not criteria:
                return None
            return sum(1 for c in criteria if c.get("pass") is True) / len(criteria)
    return None


def parse_output(stdout: str) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        return None, f"judge output is not JSON ({e})"
    verdict = data.get("structured_output")
    if not isinstance(verdict, dict) or not isinstance(verdict.get("runs"), list):
        return None, f"judge returned no structured_output (status {data.get('status')})"
    return verdict, None
