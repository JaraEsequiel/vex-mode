"""Habit tracker: add habits, mark them done each day, list current streaks."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path


def data_file() -> Path:
    return Path(os.environ.get("HABITS_DATA", Path.home() / ".habits.json"))


def load() -> dict:
    f = data_file()
    return json.loads(f.read_text()) if f.exists() else {}


def save(habits: dict) -> None:
    data_file().write_text(json.dumps(habits, indent=2, sort_keys=True))


def streak(days: list[str], today: dt.date) -> int:
    done = set(days)
    count, day = 0, today
    while day.isoformat() in done:
        count += 1
        day -= dt.timedelta(days=1)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(prog="habits")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("add").add_argument("name")
    sub.add_parser("done").add_argument("name")
    sub.add_parser("list")
    args = parser.parse_args()
    habits = load()
    today = dt.date.today()
    if args.cmd == "add":
        if args.name in habits:
            print(f"{args.name} already exists")
            return 1
        habits[args.name] = []
    elif args.cmd == "done":
        if args.name not in habits:
            print(f"no habit named {args.name}")
            return 1
        if today.isoformat() not in habits[args.name]:
            habits[args.name].append(today.isoformat())
    else:
        for name in sorted(habits):
            print(f"{name}  {streak(habits[name], today)}")
        return 0
    save(habits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
