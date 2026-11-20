"""Specs for the points rules. Run: python3 points_spec.py"""
import sys

from points import Order, earned, order_points, points_for


def spec_whole_euros_times_tier_rate():
    assert points_for(42.5, "basic") == 42
    assert points_for(42.5, "gold") == 126


def spec_bonus_only_above_100():
    assert points_for(100, "silver") == 200
    assert points_for(100.01, "silver") == 250


def spec_unknown_tier():
    try:
        points_for(10, "platinum")
    except ValueError:
        return
    raise AssertionError("unknown tier accepted")


def spec_promo_doubles_the_rate():
    assert order_points(Order(4250, "silver")) == 84
    assert order_points(Order(4250, "silver", promo=True)) == 168


def spec_bonus_is_not_doubled():
    assert order_points(Order(20000, "basic", promo=True)) == 450


def spec_earned_matches_points_for():
    assert earned(77.7, "gold") == points_for(77.7, "gold")


if __name__ == "__main__":
    specs = [f for name, f in list(globals().items()) if name.startswith("spec_")]
    failed = 0
    for spec in specs:
        try:
            spec()
        except Exception as e:  # report every failing spec, not just the first
            failed += 1
            print(f"FAILED {spec.__name__}: {type(e).__name__}: {e}")
    print(f"{len(specs) - failed} of {len(specs)} specs passed")
    sys.exit(1 if failed else 0)
