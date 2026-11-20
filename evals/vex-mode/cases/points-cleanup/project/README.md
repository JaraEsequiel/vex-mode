# loyalty

Loyalty points for the store. `points.py` holds the rules. `points_for` is the original function (order total in euros); `Order` and `order_points` (total in cents, promo option) came later for the monthly statements, and `earned` is a shortcut the banner uses. The nightly export picks its function by name from `export.json` (`points_fn`).

```bash
python3 receipt.py 42.50 silver           # till receipt
python3 statement.py 15000 gold promo     # monthly statement line
python3 banner.py 99.90 basic             # product page banner
python3 export.py orders.csv              # nightly CRM export
python3 points_spec.py                    # specs
```
