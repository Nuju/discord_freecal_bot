from datetime import date

import pytest

from freecal_core import (
    FreecalScraper,
    build_public_url,
    filter_events,
    months_for_range,
    normalize_user_id,
    parse_events,
    split_event_text,
)


def test_normalize_user_id():
    assert normalize_user_id("230522") == "230522"
    assert normalize_user_id("mem230522") == "230522"
    assert normalize_user_id("https://freecalend.com/open/mem230522") == "230522"


def test_build_month_url():
    assert (
        build_public_url("230522", 2026, 8)
        == "https://freecalend.com/open/mem230522_date202608"
    )


def test_months_for_half_open_range():
    assert months_for_range(date(2026, 8, 17), date(2026, 9, 1)) == [(2026, 8)]
    assert months_for_range(date(2026, 8, 17), date(2026, 9, 2)) == [
        (2026, 8),
        (2026, 9),
    ]
    assert months_for_range(date(2026, 12, 31), date(2027, 2, 1)) == [
        (2026, 12),
        (2027, 1),
    ]


def test_months_for_range_rejects_invalid_range():
    with pytest.raises(ValueError):
        months_for_range(date(2026, 8, 19), date(2026, 8, 19))


def test_parse_known_ccexp_formats_and_deduplicate():
    html = """
    <html><body>
      <div class="ccexp" id="ccexp-230522-2026-8-17">21:00 観戦</div>
      <div class="ccexp" id="ccexp-230522-2026-8-17">21:00 観戦</div>
      <div class="ccexp" id="ccexp-2026-8-18-1">終日イベント</div>
      <div class="ccexp" id="ccexp-999999-2026-8-19">別ユーザー</div>
    </body></html>
    """
    events = parse_events(html, expected_user_id="230522")
    assert len(events) == 2
    assert events[0].date == date(2026, 8, 17)
    assert events[0].time == "21:00"
    assert events[0].title == "観戦"
    assert events[1].date == date(2026, 8, 18)
    assert events[1].time is None
    assert events[1].title == "終日イベント"


def test_split_multiple_timed_events_in_one_day_node():
    assert split_event_text("13:00 しゃべ🐶 21:00 高級鯖缶") == [
        ("13:00", "しゃべ🐶"),
        ("21:00", "高級鯖缶"),
    ]
    assert split_event_text("15:00 鍼灸 20:00 シロクロ") == [
        ("15:00", "鍼灸"),
        ("20:00", "シロクロ"),
    ]


def test_split_all_day_then_timed_event_in_one_day_node():
    assert split_event_text("休 21:00 さよならGM") == [
        (None, "休"),
        ("21:00", "さよならGM"),
    ]


def test_japanese_hour_text_is_not_mistaken_for_clock_token():
    assert split_event_text("20:00 24時 の夢物語") == [
        ("20:00", "24時 の夢物語"),
    ]


def test_parse_multiple_events_creates_separate_rows():
    html = """
    <div id="ccexp-230522-2026-8-9">13:00 しゃべ🐶 21:00 高級鯖缶</div>
    <div id="ccexp-230522-2026-8-14">休 21:00 さよならGM</div>
    <div id="ccexp-230522-2026-8-29">15:00 鍼灸 20:00 シロクロ</div>
    """
    events = parse_events(html, expected_user_id="230522")
    assert [(event.date.day, event.time, event.title) for event in events] == [
        (9, "13:00", "しゃべ🐶"),
        (9, "21:00", "高級鯖缶"),
        (14, None, "休"),
        (14, "21:00", "さよならGM"),
        (29, "15:00", "鍼灸"),
        (29, "20:00", "シロクロ"),
    ]


def test_filter_events_uses_half_open_range():
    html = """
    <div id="ccexp-230522-2026-8-17">A</div>
    <div id="ccexp-230522-2026-8-18">B</div>
    <div id="ccexp-230522-2026-8-19">C</div>
    """
    events = parse_events(html, expected_user_id="230522")
    filtered = filter_events(
        events,
        start=date(2026, 8, 18),
        end=date(2026, 8, 19),
    )
    assert [event.title for event in filtered] == ["B"]


def test_filter_events_rejects_invalid_range():
    with pytest.raises(ValueError):
        filter_events([], start=date(2026, 8, 19), end=date(2026, 8, 19))


class FakeRangeScraper(FreecalScraper):
    def __init__(self):
        super().__init__(driver=object())
        self.loaded = []

    def _load_rendered_html(self, url, *, year, month):
        self.loaded.append((url, year, month))
        if (year, month) == (2026, 8):
            return """
            <div id="ccexp-230522-2026-8-31">23:00 八月末</div>
            <div id="ccexp-230522-2026-9-1">境界重複</div>
            """
        if (year, month) == (2026, 9):
            return """
            <div id="ccexp-230522-2026-9-1">境界重複</div>
            <div id="ccexp-230522-2026-9-2">九月予定</div>
            """
        raise AssertionError((year, month))


def test_fetch_range_loads_each_month_and_deduplicates():
    scraper = FakeRangeScraper()
    result = scraper.fetch(
        "230522",
        start=date(2026, 8, 31),
        end=date(2026, 9, 3),
    )

    assert [(event.date, event.title) for event in result.events] == [
        (date(2026, 8, 31), "八月末"),
        (date(2026, 9, 1), "境界重複"),
        (date(2026, 9, 2), "九月予定"),
    ]
    assert [(year, month) for _, year, month in scraper.loaded] == [
        (2026, 8),
        (2026, 9),
    ]
    assert result.source_urls == (
        "https://freecalend.com/open/mem230522_date202608",
        "https://freecalend.com/open/mem230522_date202609",
    )


def test_fetch_requires_both_range_boundaries_without_month():
    scraper = FakeRangeScraper()
    with pytest.raises(ValueError, match="start and end must be specified together"):
        scraper.fetch("230522", start=date(2026, 8, 31))
