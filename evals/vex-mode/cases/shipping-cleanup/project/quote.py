"""Price quote shown on the product page."""
import sys

from rates import get_cost

if __name__ == "__main__":
    print(f"shipping from EUR {get_cost(float(sys.argv[1]), sys.argv[2]):.2f}")
