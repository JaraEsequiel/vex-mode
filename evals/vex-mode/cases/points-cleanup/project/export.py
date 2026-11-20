"""Nightly export of points per order, for the CRM. Which points function to use is set in export.json."""
import csv
import json
import sys
from pathlib import Path

import points

HERE = Path(__file__).parent


def main(path):
    config = json.loads((HERE / "export.json").read_text())
    compute = getattr(points, config["points_fn"])
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            print(f"{row['order_id']},{compute(float(row['total_eur']), row['tier'])}")


if __name__ == "__main__":
    main(sys.argv[1])
