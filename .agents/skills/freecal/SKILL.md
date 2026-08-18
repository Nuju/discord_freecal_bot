---
name: freecal
description: Read public Freecal calendars from freecalend.com, retrieve a requested month or date range, and summarize schedules as tables, free-time candidates, or cross-person comparisons. Use only for public Freecal URLs or public member IDs.
---

# Freecal Schedule Reader

Use this skill when the user asks to inspect a public calendar on `freecalend.com`, such as:

- "この人の今月の予定を表にして"
- "8月後半の予定を教えて"
- "AさんとBさんが両方空いている日を探して"
- "この予定に変更があるか確認して"

## Data access

Freecal's public page loads calendar data after the initial HTML. Do not rely on the initial HTML alone.
Use the repository CLI:

```bash
python freecal_cli.py <USER_OR_PUBLIC_URL> --month YYYY-MM --pretty
```

The default `auto` backend first reads Freecal's public `/open/data` endpoint over HTTP. If that route fails, it automatically falls back to the browser-backed Selenium reader.

For diagnostics, a backend can be forced explicitly:

```bash
python freecal_cli.py 230522 --month 2026-08 --backend http --pretty
python freecal_cli.py 230522 --month 2026-08 --backend selenium --pretty
```

Examples:

```bash
python freecal_cli.py 230522 --month 2026-08 --pretty
python freecal_cli.py https://freecalend.com/open/mem230522 --start 2026-08-17 --end 2026-09-01 --pretty
```

The `--start` date is inclusive and `--end` is exclusive.

## Retrieval workflow

1. Resolve the target member ID from a numeric ID, `memXXXXXX`, or a public Freecal URL.
2. Prefer `--month YYYY-MM` when the user asks about one calendar month.
3. Use `--start` and `--end` for a specific date range. Multi-month ranges are fetched month by month and merged.
4. Use the default `auto` backend unless diagnosing a retrieval problem.
5. Parse the JSON result. Treat `events` as the source of truth and note the returned `backend` value when troubleshooting.
6. If `event_count` is zero, distinguish between "no public events were returned" and a fetch error. Do not invent events.
7. Present dates in the user's locale. For Japanese responses, include weekday names when useful.

## Output rules

For a single person's monthly schedule, default to a compact table:

| 日付 | 曜日 | 時刻 | 予定 |
|---|---|---|---|

- Use `終日` when `all_day` is true.
- Keep event titles as returned by Freecal. Do not silently rewrite proper nouns.
- Sort chronologically.
- If multiple events occur on the same date, show separate rows unless the user asks for grouping.
- Whitespace-only differences between the raw data endpoint and browser-rendered text are not different events.

For availability questions, clearly state the assumed available hours. A day with no published event is only "予定が公開されていない日" unless the user explicitly wants it treated as free time.

For comparisons across multiple people, fetch each calendar independently and compare normalized ISO dates/times. Never infer a private schedule from missing public data.

## Failure handling

The normal fallback order is HTTP -> Selenium.

If both routes fail:

1. Report that the public calendar could not be fetched in the current runtime.
2. Do not replace the missing schedule with search-engine snippets unless the user explicitly accepts a best-effort fallback.
3. If a fallback is needed, web search may confirm the public page and month-specific URL, but search snippets are not authoritative for a complete event list.

## Implementation notes

- `freecal_http.py`: lightweight public `/open/data` reader.
- `freecal_core.py`: Selenium-backed reader and shared event parsing/model code.
- `freecal_client.py`: `auto`, `http`, and `selenium` backend selection.
- `freecal_cli.py`: JSON command-line interface used by this skill.

The Selenium parser reads JavaScript-rendered nodes whose IDs begin with `ccexp-`. Known formats include:

- `ccexp-<user_id>-<year>-<month>-<day>`
- `ccexp-<year>-<month>-<day>-<sequence>`
