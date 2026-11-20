"""Monthly statement line for one order."""
import sys

from points import Order, order_points


def line(cents, tier, promo):
    order = Order(cents, tier, promo)
    flag = " (promo x2)" if promo else ""
    return f"{tier.upper()} order {cents / 100:.2f} EUR: {order_points(order)} pts{flag}"


if __name__ == "__main__":
    print(line(int(sys.argv[1]), sys.argv[2], len(sys.argv) > 3 and sys.argv[3] == "promo"))
