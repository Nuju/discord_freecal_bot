from __future__ import annotations

import calendar
import json
import time
import urllib.parse
from datetime import date, datetime
from typing import Optional

import requests

from freecal_core import (
    FreecalError,
    FreecalEvent,
    FreecalResult,
    build_public_url,
    filter_events,
    months_for_range,
    normalize_user_id,
    split_event_text,
)


DATA_URL = "https://freecalend.com/open/data"
BOOTSTRAP_VERSION = "1602144014"


class FreecalHttpError(FreecalError):
    """Raised when Freecal's public data endpoint cannot be read reliably."""


def build_data_keys(user_id: str, year: int, month: int) -> dict:
    """Build the public calendar keys used by Freecal's own browser client."""
    user_id = normalize_user_id(user_id)
    permission_name = f"ok-{user_id}-all-r-cald"

    def item(key: str, *, permitted: bool = False) -> list:
        permissions = [[permission_name, True]] if permitted else []
        return [key, BOOTSTRAP_VERSION, BOOTSTRAP_VERSION, permissions, []]

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


def parse_data_response(
    payload: object,
    *,
    user_id: str,
    year: int,
    month: int,
) -> list[FreecalEvent]:
    """Parse Freecal `/open/data` operations into structured events."""
    user_id = normalize_user_id(user_id)
    if not isinstance(payload, list):
        raise FreecalHttpError("Unexpected Freecal data response shape")

    prefix = f"cald-{user_id}-{year}-{month}-"
    events: list[FreecalEvent] = []
    seen: set[tuple[date, Optional[str], str]] = set()

    for operation in payload:
        if not isinstance(operation, list) or len(operation) < 2:
            continue
        if operation[0] != "set" or not isinstance(operation[1], str):
            continue

        try:
            record = json.loads(operation[1])
        except json.JSONDecodeError:
            continue
        if not isinstance(record, list) or len(record) < 4:
            continue

        key = record[2]
        value = record[3]
        if not isinstance(key, str) or not key.startswith(prefix):
            continue

        day_text = key[len(prefix) :]
        if not day_text.isdigit():
            continue
        try:
            event_date = date(year, month, int(day_text))
        except ValueError:
            continue

        if not isinstance(value, list) or len(value) < 2:
            continue
        raw_text = value[1]
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue

        for time_value, title in split_event_text(raw_text):
            event_key = (event_date, time_value, title)
            if event_key in seen:
                continue
            seen.add(event_key)
            events.append(
                FreecalEvent(
                    date=event_date,
                    time=time_value,
                    title=title,
                    user_id=user_id,
                )
            )

    return sorted(
        events,
        key=lambda event: (event.date, event.time or "00:00", event.title),
    )


class FreecalHttpClient:
    """Lightweight reader for public Freecal calendars using `/open/data`."""

    def __init__(
        self,
        *,
        timeout: float = 12.0,
        retries: int = 1,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self._session = session
        self._owns_session = session is None

    def __enter__(self) -> "FreecalHttpClient":
        self._ensure_session()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _ensure_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/151.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
                }
            )
        return self._session

    def _fetch_month_events(
        self,
        user_id: str,
        year: int,
        month: int,
    ) -> tuple[str, list[FreecalEvent]]:
        session = self._ensure_session()
        public_url = build_public_url(user_id, year, month)
        keys_object = build_data_keys(user_id, year, month)
        encoded_keys = urllib.parse.quote(
            json.dumps(keys_object, ensure_ascii=False, separators=(",", ":")),
            safe="",
        )
        last_error: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            try:
                landing = session.get(public_url, timeout=self.timeout)
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
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                events = parse_data_response(
                    payload,
                    user_id=user_id,
                    year=year,
                    month=month,
                )
                return public_url, events
            except (requests.RequestException, ValueError, FreecalHttpError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.25 * (attempt + 1))

        raise FreecalHttpError(
            f"Failed to read Freecal public data endpoint: {public_url}"
        ) from last_error

    def fetch(
        self,
        user_id: str,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> FreecalResult:
        normalized = normalize_user_id(user_id)

        if (year is None) != (month is None):
            raise ValueError("year and month must be specified together")
        if start is not None and end is not None and start >= end:
            raise ValueError("start must be earlier than end")

        source_urls: list[str] = []
        events: list[FreecalEvent] = []

        if year is not None and month is not None:
            url, events = self._fetch_month_events(normalized, year, month)
            source_urls.append(url)
        else:
            if start is None or end is None:
                raise ValueError(
                    "HTTP backend requires --month or both start and end dates"
                )
            for range_year, range_month in months_for_range(start, end):
                url, month_events = self._fetch_month_events(
                    normalized,
                    range_year,
                    range_month,
                )
                source_urls.append(url)
                events.extend(month_events)

        events = filter_events(events, start=start, end=end)
        unique_events = sorted(
            set(events),
            key=lambda event: (event.date, event.time or "00:00", event.title),
        )
        source_url = (
            source_urls[0] if len(source_urls) == 1 else build_public_url(normalized)
        )

        return FreecalResult(
            user_id=normalized,
            source_url=source_url,
            source_urls=tuple(source_urls),
            fetched_at=datetime.now().astimezone(),
            events=tuple(unique_events),
            backend="http",
        )

    def close(self) -> None:
        if self._session is not None and self._owns_session:
            self._session.close()
            self._session = None
