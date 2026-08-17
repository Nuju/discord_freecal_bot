from datetime import date

from freecal_core import build_public_url, filter_events, normalize_user_id, parse_events


def test_normalize_user_id():
    assert normalize_user_id("230522") == "230522"
    assert normalize_user_id("mem230522") == "230522"
    assert normalize_user_id("https://freecalend.com/open/mem230522") == "230522"


def test_build_month_url():
    assert (
        build_public_url("230522", 2026, 8)
        == "https://freecalend.com/open/mem230522_date202608"
    )


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
