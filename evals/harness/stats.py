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


ALPHA = 0.05


def fisher_p(a: list[int], b: list[int]) -> float:
    """One-sided Fisher exact test on pass/fail runs: the chance of b passing at least as often as it did
    if both arms passed at the same rate."""
    from math import comb

    n1, n2, k1, k2 = len(b), len(a), sum(b), sum(a)
    total, passes = n1 + n2, k1 + k2
    if n1 == 0 or n2 == 0:
        return 1.0
    hits = sum(comb(passes, x) * comb(total - passes, n1 - x) for x in range(k1, min(passes, n1) + 1))
    return hits / comb(total, n1)


def outcome_signal(a: list[int], b: list[int]) -> tuple[str, float]:
    """Direction of b's pass rate against a's, with its p-value. A pass/fail outcome has no useful spread
    (one pass and one fail make it 1), so it gets an exact test instead of the spread rule."""
    better, worse = fisher_p(a, b), fisher_p(b, a)
    if better <= ALPHA:
        return "better", round(better, 3)
    if worse <= ALPHA:
        return "worse", round(worse, 3)
    return "noise", round(min(better, worse, 1.0), 3)
