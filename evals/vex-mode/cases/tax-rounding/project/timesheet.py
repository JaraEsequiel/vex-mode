"""Monthly consulting statement from an hours export (CSV: price = hourly rate, quantity = hours)."""
import sys

from invoices import invoice_total, line_total, read_lines


def statement(entries):
    out = [f"{rate:.2f}/h x {hours:g} h = {line_total(rate, hours):.2f}" for rate, hours in entries]
    hours = sum(h for _, h in entries)
    average = sum(rate * h for rate, h in entries) / hours
    out.append(f"{hours:g} h at {average:.2f}/h on average")
    out.append(f"total with tax: {invoice_total(entries):.2f}")
    return "\n".join(out)


if __name__ == "__main__":
    print(statement(read_lines(sys.argv[1])))
