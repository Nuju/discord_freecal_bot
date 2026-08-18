from __future__ import annotations

import argparse
import calendar
import json
import sys
import urllib.parse
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from freecal_core import build_public_url, normalize_user_id, split_event_text


INITIAL_VERSION = "1602144014"
DATA_URL = "https://freecalend.com/open/data"


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-", 1)
        year, month = int(year_text), int(month_text)
    except (AttributeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("month must be YYYY-MM") from exc
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be YYYY-MM")
    return year, month


def build_keys(user_id: str, year: int, month: int) -> dict:
    permission_name = f"ok-{user_id}-all-r-cald"

    def item(key: str, *, permitted: bool = False) -> list:
        permissions = [[permission_name, True]] if permitted else []
        return [key, INITIAL_VERSION, INITIAL_VERSION, permissions, []]

    values = [
        item("message-0-oto"),
        item(f"ng-{user_id}-all-r-cald-{user_id}-{year}-{month}"),
        item(f"cald-{user_id}-{year}-{month}", permitted=True),
    ]
    last_day = calendar.monthrange(year, month)[1]
    values.extend(
        item(f"cald-{user_id}-{year}-{month}-{day}", permitted=True)
        for day in range(1, last_day + 1)
    )
    return {"data": values}


def parse_response(payload: object, user_id: str, year: int, month: int) -> list[dict]:
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected Freecal response shape")

    prefix = f"cald-{user_id}-{year}-{month}-"
    events: list[dict] = []

    for operation in payload:
        if not isinstance(operation, list) or len(operation) < 2 or operation[0] != "set":
            continue
        raw_record = operation[1]
        if not isinstance(raw_record, str):
            continue
        try:
            record = json.loads(raw_record)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, list) or len(record) < 4:
            continue

        key = record[2]
        value = record[3]
        if not isinstance(key, str) or not key.startswith(prefix):
            continue

        suffix = key[len(prefix) :]
        if not suffix.isdigit():
            continue
        day = int(suffix)
        try:
            event_date = date(year, month, day)
        except ValueError:
            continue

        if not isinstance(value, list) or len(value) < 2:
            continue
        text = value[1]
        if not isinstance(text, str) or not text.strip():
            continue

        for time_value, title in split_event_text(text):
            events.append(
                {
                    "date": event_date.isoformat(),
                    "time": time_value,
                    "title": title,
                }
            )

    unique = {
        (event["date"], event["time"], event["title"]): event for event in events
    }
    return sorted(
        unique.values(),
        key=lambda event: (event["date"], event["time"] or "00:00", event["title"]),
    )


def fetch_direct(user: str, year: int, month: int, timeout: float = 15.0) -> dict:
    user_id = normalize_user_id(user)
    public_url = build_public_url(user_id, year, month)
    keys_object = build_keys(user_id, year, month)
    encoded_keys = urllib.parse.quote(
        json.dumps(keys_object, ensure_ascii=False, separators=(",", ":")),
        safe="",
    )

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/151.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
            }
        )
        landing = session.get(public_url, timeout=timeout)
        landing.raise_for_status()

        response = session.post(
            DATA_URL,
            data={
                "target_mem_no": user_id,
                "version": "3",
                "mem_no": "0",
                "keys": encoded_keys,
                "dokisuru": "true",
                "fversion": "-1",
            },
            headers={
                "Referer": public_url,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()

    events = parse_response(payload, user_id, year, month)
    return {
        "user_id": user_id,
        "source_url": public_url,
        "data_url": DATA_URL,
        "request_key_count": len(keys_object["data"]),
        "response_operation_count": len(payload) if isinstance(payload, list) else None,
        "event_count": len(events),
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Freecal's public /open/data endpoint without Selenium."
    )
    parser.add_argument("user")
    parser.add_argument("--month", required=True, type=parse_month)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    year, month = args.month
    result = fetch_direct(args.user, year, month)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
