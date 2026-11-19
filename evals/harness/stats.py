"""Numbers with their spread (principle-explain-the-number): a gap within the spread is noise."""


def summarize(xs: list[float]) -> dict:
    if not xs:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "spread": 0.0}
    lo, hi = min(xs), max(xs)
    return {"mean": sum(xs) / len(xs), "min": lo, "max": hi, "spread": hi - lo}


def signal(a: dict, b: dict) -> str:
    """Direction of b against a; higher is better. Pass negated values for costs."""
    gap = b["mean"] - a["mean"]
    if abs(gap) <= max(a["spread"], b["spread"]):
        return "noise"
    return "better" if gap > 0 else "worse"
