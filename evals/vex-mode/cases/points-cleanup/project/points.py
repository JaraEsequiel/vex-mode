"""Loyalty points earned on an order."""

TIER_RATE = {"basic": 1, "silver": 2, "gold": 3}  # points per whole euro
BONUS_OVER_EUR = 100
BONUS = 50


def points_for(total_eur, tier):
    """Points for an order of total_eur euros."""
    if tier not in TIER_RATE:
        raise ValueError(f"unknown tier: {tier}")
    points = int(total_eur) * TIER_RATE[tier]
    if total_eur > BONUS_OVER_EUR:
        points += BONUS
    return points


class Order:
    def __init__(self, cents, tier, promo=False):
        self.cents = cents
        self.tier = tier
        self.promo = promo


def order_points(order):
    """Points for an Order. A promo order earns double the tier rate."""
    if order.tier not in TIER_RATE:
        raise ValueError(f"unknown tier: {order.tier}")
    rate = TIER_RATE[order.tier] * (2 if order.promo else 1)
    points = (order.cents // 100) * rate
    if order.cents > BONUS_OVER_EUR * 100:
        points += BONUS
    return points


def earned(total_eur, tier):
    return points_for(total_eur, tier)
