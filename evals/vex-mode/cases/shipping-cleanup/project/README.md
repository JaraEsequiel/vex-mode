# shipping

Shipping prices for the shop. `rates.py` holds the price rules. `calc_shipping` is the original function (weight in kg); `shipping_cost` and `Parcel` (weight in grams, express option) came later for the warehouse labels.

```bash
python3 checkout.py 40.00 2.5 eu      # order total
python3 labels.py 2500 eu express     # warehouse label
python3 quote.py 2.5 eu               # product page quote
```
