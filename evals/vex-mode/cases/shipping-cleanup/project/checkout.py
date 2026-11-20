"""Order total at checkout: items plus shipping."""
import sys

from rates import calc_shipping


def order_total(items_total, weight_kg, zone):
    return round(items_total + calc_shipping(weight_kg, zone), 2)


if __name__ == "__main__":
    items, weight, zone = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    print(f"total: {order_total(items, weight, zone):.2f}")
