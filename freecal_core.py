from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


FREECAL_BASE_URL = "https://freecalend.com/open"
_CCE_ID_RE = re.compile(
    r"^ccexp-(?:(?P<user_id>\d+)-)?(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?:-(?P<seq>\d+))?$"
)
_TIME_TOKEN_RE = re.compile(r"(?<!\d)(?P<time>\d{1,2}:[0-5]\d)(?!\d)")


class FreecalError(RuntimeError):
    """Base exception for Freecal scraping errors."""


class FreecalLoadError(FreecalError):
    """Raised when a public Freecal page cannot be loaded reliably."""


@dataclass(frozen=True, order=True)
class FreecalEvent:
    date: date
    title: str
    time: Optional[str] = None
    user_id: Optional[str] = None

    @property
    def all_day(self) -> bool:
        return self.time is None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["date"] = self.date.isoformat()
        data["all_day"] = self.all_day
        return data


@dataclass(frozen=True)
class FreecalResult:
    user_id: str
    source_url: str
    fetched_at: datetime
    events: tuple[FreecalEvent, ...]

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat(timespec="seconds"),
            "event_count": len(self.events),
            "events": [event.to_dict() for event in self.events],
        }


def normalize_user_id(value: str) -> str:
    """Accept a numeric ID, memXXXXXX, or a public Freecal URL."""
    value = value.strip()
    match = re.search(r"(?:^|/)mem(?P<id>\d+)", value)
    if match:
        return match.group("id")
    if value.startswith("mem") and value[3:].isdigit():
        return value[3:]
    if value.isdigit():
        return value
    raise ValueError(f"Unsupported Freecal user identifier: {value!r}")


def build_public_url(
    user_id: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> str:
    user_id = normalize_user_id(user_id)
    if (year is None) != (month is None):
        raise ValueError("year and month must be specified together")
    if year is None:
        return f"{FREECAL_BASE_URL}/mem{user_id}"
    if not 1 <= int(month) <= 12:
        raise ValueError("month must be between 1 and 12")
    return f"{FREECAL_BASE_URL}/mem{user_id}_date{int(year):04d}{int(month):02d}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _is_supported_time(value: str) -> bool:
    """Allow ordinary clock times plus late-night notation such as 24:00-29:59."""
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (TypeError, ValueError):
        return False
    return 0 <= hour <= 29 and 0 <= minute <= 59


def split_event_text(text: str) -> list[tuple[Optional[str], str]]:
    """Split one Freecal day-cell string into individual events.

    Freecal can render multiple events for the same day inside one ccexp node,
    for example ``13:00 A 21:00 B`` or ``休 21:00 C``.  The old parser treated
    those as one event.  This function keeps an untimed prefix as an all-day
    event and starts a new event at every supported HH:MM token.
    """
    text = _normalize_text(text)
    if not text:
        return []

    matches = [
        match
        for match in _TIME_TOKEN_RE.finditer(text)
        if _is_supported_time(match.group("time"))
    ]
    if not matches:
        return [(None, text)]

    parts: list[tuple[Optional[str], str]] = []
    prefix = text[: matches[0].start()].strip(" -–—")
    if prefix:
        parts.append((None, prefix))

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = text[match.end() : end].strip(" -–—")
        if title:
            parts.append((match.group("time"), title))

    # If a malformed time token consumed the whole text, preserve the source
    # instead of silently dropping the event.
    return parts or [(None, text)]


def parse_events(html: str, *, expected_user_id: Optional[str] = None) -> list[FreecalEvent]:
    """Parse JavaScript-rendered Freecal HTML into structured events."""
    expected = normalize_user_id(expected_user_id) if expected_user_id else None
    soup = BeautifulSoup(html, "lxml")
    events: list[FreecalEvent] = []
    seen: set[tuple[date, Optional[str], str]] = set()

    for node in soup.select('div[id^="ccexp-"]'):
        div_id = node.get("id", "")
        match = _CCE_ID_RE.match(div_id)
        if not match:
            continue

        node_user_id = match.group("user_id")
        if expected and node_user_id and node_user_id != expected:
            continue

        try:
            event_date = date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue

        text = _normalize_text(" ".join(node.stripped_strings))
        if not text:
            continue

        for time_value, title in split_event_text(text):
            key = (event_date, time_value, title)
            if key in seen:
                continue
            seen.add(key)
            events.append(
                FreecalEvent(
                    date=event_date,
                    time=time_value,
                    title=title,
                    user_id=node_user_id or expected,
                )
            )

    return sorted(events, key=lambda event: (event.date, event.time or "00:00", event.title))


def filter_events(
    events: Iterable[FreecalEvent],
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> list[FreecalEvent]:
    """Filter by an inclusive start and exclusive end date."""
    if start is not None and end is not None and start >= end:
        raise ValueError("start must be earlier than end")
    return [
        event
        for event in events
        if (start is None or event.date >= start) and (end is None or event.date < end)
    ]


class FreecalScraper:
    """Reusable browser-backed scraper for public Freecal calendars.

    One Chrome session is reused across calls. Selenium Manager handles the
    ChromeDriver automatically.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        timeout: float = 12.0,
        retries: int = 1,
        driver: Optional[webdriver.Chrome] = None,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self._driver = driver
        self._owns_driver = driver is None
        self._headless = headless

    def __enter__(self) -> "FreecalScraper":
        self._ensure_driver()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _create_driver(self) -> webdriver.Chrome:
        options = Options()
        if self._headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1600,1200")
        options.add_argument("--lang=ja-JP")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
        )
        return webdriver.Chrome(options=options)

    def _ensure_driver(self) -> webdriver.Chrome:
        if self._driver is None:
            self._driver = self._create_driver()
        return self._driver

    @staticmethod
    def _page_ready(driver, year: Optional[int], month: Optional[int]) -> bool:
        if driver.execute_script("return document.readyState") != "complete":
            return False
        if year is None or month is None:
            return True
        body = driver.find_element("tag name", "body").text
        return f"{year}年" in body and f"{month}月" in body

    def _load_rendered_html(
        self,
        url: str,
        *,
        year: Optional[int],
        month: Optional[int],
    ) -> str:
        driver = self._ensure_driver()
        last_error: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            try:
                driver.get(url)
                WebDriverWait(driver, self.timeout, poll_frequency=0.2).until(
                    lambda current_driver: self._page_ready(current_driver, year, month)
                )

                observation_started = time.monotonic()
                minimum_observation = min(0.8, max(0.3, self.timeout / 10))
                deadline = observation_started + min(2.5, max(1.0, self.timeout / 3))
                previous = None
                stable_rounds = 0

                while time.monotonic() < deadline:
                    current = driver.page_source
                    if current == previous:
                        stable_rounds += 1
                    else:
                        stable_rounds = 0
                        previous = current

                    elapsed = time.monotonic() - observation_started
                    if elapsed >= minimum_observation and stable_rounds >= 2:
                        return current
                    time.sleep(0.15)

                return driver.page_source
            except (TimeoutException, WebDriverException) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))

        raise FreecalLoadError(f"Failed to load Freecal page: {url}") from last_error

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
        url = build_public_url(normalized, year=year, month=month)
        html = self._load_rendered_html(url, year=year, month=month)
        events = parse_events(html, expected_user_id=normalized)

        if year is not None and month is not None:
            events = [
                event
                for event in events
                if event.date.year == year and event.date.month == month
            ]
        events = filter_events(events, start=start, end=end)

        return FreecalResult(
            user_id=normalized,
            source_url=url,
            fetched_at=datetime.now().astimezone(),
            events=tuple(events),
        )

    def close(self) -> None:
        if self._driver is not None and self._owns_driver:
            try:
                self._driver.quit()
            finally:
                self._driver = None
