"""Banner on the product page: points a purchase would earn."""
import sys

from points import earned

if __name__ == "__main__":
    print(f"buy now and earn {earned(float(sys.argv[1]), sys.argv[2])} points")
