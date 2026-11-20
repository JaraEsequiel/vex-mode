"""Points line printed on the till receipt."""
import sys

from points import points_for

if __name__ == "__main__":
    total, tier = float(sys.argv[1]), sys.argv[2]
    print(f"you earned {points_for(total, tier)} points")
