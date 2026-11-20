"""Shipping label line for the warehouse printer."""
import sys

from rates import Parcel, shipping_cost


def label(weight_g, zone, express):
    parcel = Parcel(weight_g, zone, express)
    kind = "EXPRESS" if express else "STANDARD"
    return f"{kind} {zone.upper()} {weight_g}g EUR {shipping_cost(parcel):.2f}"


if __name__ == "__main__":
    print(label(int(sys.argv[1]), sys.argv[2], len(sys.argv) > 3 and sys.argv[3] == "express"))
