import json
from datetime import date, datetime

from freecal_client import FreecalClient
from freecal_core import FreecalEvent, FreecalResult
from freecal_http import (
    FreecalHttpClient,
    FreecalHttpError,
    build_data_keys,
    parse_data_response,
)


def make_operation(key: str, text: str) -> list:
    value = [[], text, "color", ""]
    record = ["hda", "on", key, value, "version", None, "e"]
    return ["set", json.dumps(record, ensure_ascii=False)]


def test_build_data_keys_for_august():
    payload = build_data_keys("230522", 2026, 8)
    values = payload["data"]

    assert len(values) == 34
    assert values[0][0] == "message-0-oto"
    assert values[2][0] == "cald-230522-2026-8"
    assert values[-1][0] == "cald-230522-2026-8-31"
    assert values[2][3] == [["ok-230522-all-r-cald", True]]


def test_parse_data_response_splits_multiple_events():
    payload = [
        make_operation("cald-230522-2026-8-9", "13:00\nしゃべ🐶\n21:00\n高級鯖缶"),
        make_operation("cald-230522-2026-8-14", "休\n21:00\nさよならGM"),
        make_operation("cald-230522-2026-8-29", "15:00\n鍼灸\n20:00\nシロクロ"),
    ]

    events = parse_data_response(
        payload,
        user_id="230522",
        year=2026,
        month=8,
    )

    assert [(event.date.day, event.time, event.title) for event in events] == [
        (9, "13:00", "しゃべ🐶"),
        (9, "21:00", "高級鯖缶"),
        (14, None, "休"),
        (14, "21:00", "さよならGM"),
        (29, "15:00", "鍼灸"),
        (29, "20:00", "シロクロ"),
    ]


def test_parse_data_response_keeps_raw_title_semantics():
    payload = [
        make_operation("cald-230522-2026-8-7", "20:00\n24時の夢物語"),
    ]
    events = parse_data_response(
        payload,
        user_id="230522",
        year=2026,
        month=8,
    )
    assert [(event.time, event.title) for event in events] == [
        ("20:00", "24時の夢物語")
    ]


class FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
        self.get_calls = []
        self.post_calls = []

    def get(self, url, timeout):
        self.get_calls.append((url, timeout))
        return FakeResponse()

    def post(self, url, data, headers, timeout):
        self.post_calls.append((url, data, headers, timeout))
        return FakeResponse(self.payload)


def test_http_client_fetches_month_without_browser():
    payload = [
        make_operation("cald-230522-2026-8-17", "21:00\n観戦"),
    ]
    session = FakeSession(payload)
    client = FreecalHttpClient(session=session)

    result = client.fetch("230522", year=2026, month=8)

    assert [(event.date, event.time, event.title) for event in result.events] == [
        (date(2026, 8, 17), "21:00", "観戦")
    ]
    assert session.get_calls[0][0].endswith("mem230522_date202608")
    assert session.post_calls[0][0] == "https://freecalend.com/open/data"
    assert session.post_calls[0][1]["target_mem_no"] == "230522"


class FailingHttpClient:
    def fetch(self, *args, **kwargs):
        raise FreecalHttpError("test failure")

    def close(self):
        return None


class FakeSeleniumClient:
    def fetch(self, *args, **kwargs):
        return FreecalResult(
            user_id="230522",
            source_url="https://freecalend.com/open/mem230522_date202608",
            fetched_at=datetime.now().astimezone(),
            events=(
                FreecalEvent(
                    date=date(2026, 8, 17),
                    time="21:00",
                    title="fallback",
                    user_id="230522",
                ),
            ),
        )

    def close(self):
        return None


def test_auto_client_falls_back_to_selenium_on_http_failure():
    client = FreecalClient(backend="auto")
    client._http = FailingHttpClient()
    client._selenium = FakeSeleniumClient()

    result = client.fetch("230522", year=2026, month=8)

    assert client.last_backend == "selenium"
    assert client.last_http_error is not None
    assert result.events[0].title == "fallback"
