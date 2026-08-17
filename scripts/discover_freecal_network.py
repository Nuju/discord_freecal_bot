from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from freecal_core import build_public_url, normalize_user_id


def parse_month(value: str) -> tuple[int, int]:
    try:
        year_text, month_text = value.split("-", 1)
        year, month = int(year_text), int(month_text)
    except (AttributeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("month must be YYYY-MM") from exc
    if not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be YYYY-MM")
    return year, month


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Freecal browser network traffic to find a lighter data endpoint."
    )
    parser.add_argument("user", help="Freecal user id, memXXXXXX, or public URL")
    parser.add_argument("--month", required=True, type=parse_month)
    parser.add_argument("--wait", type=float, default=4.0)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    user_id = normalize_user_id(args.user)
    year, month = args.month
    target_url = build_public_url(user_id, year, month)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1600,1200")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(options=options)
    requests: dict[str, dict[str, Any]] = {}

    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.get(target_url)
        time.sleep(max(1.0, args.wait))

        for entry in driver.get_log("performance"):
            try:
                message = json.loads(entry["message"])["message"]
            except (KeyError, TypeError, json.JSONDecodeError):
                continue

            method = message.get("method")
            params = message.get("params", {})
            request_id = params.get("requestId")
            if not request_id:
                continue

            if method == "Network.requestWillBeSent":
                request = params.get("request", {})
                url = request.get("url", "")
                if "freecalend.com" not in url:
                    continue
                requests.setdefault(request_id, {}).update(
                    {
                        "method": request.get("method"),
                        "url": url,
                        "resource_type": params.get("type"),
                        "post_data": request.get("postData"),
                    }
                )

            elif method == "Network.responseReceived" and request_id in requests:
                response = params.get("response", {})
                requests[request_id].update(
                    {
                        "status": response.get("status"),
                        "mime_type": response.get("mimeType"),
                    }
                )

        interesting: list[dict[str, Any]] = []
        for request_id, record in requests.items():
            resource_type = record.get("resource_type")
            url = record.get("url", "")
            if resource_type not in {"XHR", "Fetch"} and not any(
                marker in url.lower()
                for marker in ("ajax", "api", "calendar", "cal", "json", "event", "schedule")
            ):
                continue

            if resource_type in {"XHR", "Fetch"}:
                try:
                    body = driver.execute_cdp_cmd(
                        "Network.getResponseBody", {"requestId": request_id}
                    ).get("body", "")
                    if body:
                        record["response_preview"] = body[:10000]
                except Exception:
                    pass
            interesting.append(record)

        output = {
            "target_url": target_url,
            "request_count": len(requests),
            "interesting_count": len(interesting),
            "requests": interesting,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
