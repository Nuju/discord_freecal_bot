from __future__ import annotations

import argparse
import json
from datetime import date

from freecal_client import FreecalClient


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-", 1)
        year, month = int(year_text), int(month_text)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError("month must be YYYY-MM") from exc
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be YYYY-MM")
    return year, month


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a public Freecal calendar as JSON")
    parser.add_argument("user", help="Freecal user id, memXXXXXX, or public URL")
    parser.add_argument("--month", type=parse_month, help="Target month in YYYY-MM")
    parser.add_argument("--start", type=parse_date, help="Inclusive start date")
    parser.add_argument("--end", type=parse_date, help="Exclusive end date")
    parser.add_argument(
        "--backend",
        choices=("auto", "http", "selenium"),
        default="auto",
        help="Retrieval backend. auto prefers HTTP and falls back to Selenium.",
    )
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    year = month = None
    if args.month:
        year, month = args.month

    with FreecalClient(backend=args.backend, timeout=args.timeout) as client:
        result = client.fetch(
            args.user,
            year=year,
            month=month,
            start=args.start,
            end=args.end,
        )
        output = result.to_dict()
        output["backend"] = client.last_backend

    print(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
