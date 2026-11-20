# invoices

Prints the total due for an invoice exported as CSV (`price,quantity` per line), including 8.25% sales tax.

```bash
python3 invoices.py inv-1042.csv
```

`timesheet.py` bills consulting hours from the same CSV format (price = hourly rate, quantity = hours, often fractional):

```bash
python3 timesheet.py hours-2026-11.csv
```
