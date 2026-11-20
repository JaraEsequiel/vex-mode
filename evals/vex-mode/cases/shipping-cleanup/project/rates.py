"""Shipping prices, in euros."""

ZONE_BASE = {"domestic": 5.0, "eu": 12.0, "world": 25.0}
PER_KG = {"domestic": 1.2, "eu": 2.5, "world": 4.0}
HEAVY_KG = 20
HEAVY_FEE = 10.0


def calc_shipping(weight_kg, zone):
    """Price for a parcel of weight_kg kilograms to zone."""
    if zone not in ZONE_BASE:
        raise ValueError(f"unknown zone: {zone}")
    price = ZONE_BASE[zone] + PER_KG[zone] * weight_kg
    if weight_kg > HEAVY_KG:
        price += HEAVY_FEE
    return round(price, 2)


class Parcel:
    def __init__(self, weight_g, zone, express=False):
        self.weight_g = weight_g
        self.zone = zone
        self.express = express


def shipping_cost(parcel):
    """Price for a Parcel. Express doubles the zone's base fee."""
    if parcel.zone not in ZONE_BASE:
        raise ValueError(f"unknown zone: {parcel.zone}")
    kg = parcel.weight_g / 1000
    base = ZONE_BASE[parcel.zone] * (2 if parcel.express else 1)
    price = base + PER_KG[parcel.zone] * kg
    if kg > HEAVY_KG:
        price += HEAVY_FEE
    return round(price, 2)


def get_cost(weight_kg, zone):
    return calc_shipping(weight_kg, zone)
