"""Try the ledger from text, no Gnani calls.

Usage:
  uv run python scripts/ledger.py add "Rameshbhai ne be lakh chaalis hazaar nu maal aapyu, saath divas"
  uv run python scripts/ledger.py list
  uv run python scripts/ledger.py balances
"""

import argparse
import sys

from ugharani import db
from ugharani.extract import parse


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Gujarati + ₹ on Windows consoles
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="parse a transcript and save it if complete")
    add.add_argument("text")
    add.add_argument("--dry-run", action="store_true", help="parse only, don't save")
    sub.add_parser("list")
    sub.add_parser("balances")
    args = parser.parse_args()

    conn = db.connect()
    if args.cmd == "add":
        entry = parse(args.text)
        print(f"kind={entry.kind} buyer={entry.buyer} amount={entry.amount} "
              f"due={entry.due_date} ({entry.due_days} days)")
        if entry.missing:
            raise SystemExit(f"Not saved, missing: {', '.join(entry.missing)}")
        if not args.dry_run:
            print(f"Saved entry #{db.add_entry(conn, entry, args.text)}")
    elif args.cmd == "list":
        for r in db.list_entries(conn):
            print(f"#{r['id']} {r['entry_date']} {r['kind']:<7} {r['buyer']:<15} ₹{r['amount']:>10,} "
                  f"due {r['due_date'] or '-'}")
    else:
        for r in db.balances(conn):
            print(f"{r['buyer']:<15} ₹{r['balance']:>10,}  earliest due {r['earliest_due'] or '-'}")


if __name__ == "__main__":
    main()
