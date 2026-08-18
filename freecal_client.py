from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from freecal_core import FreecalResult, FreecalScraper
from freecal_http import FreecalHttpClient, FreecalHttpError


Backend = Literal["auto", "http", "selenium"]


class FreecalClient:
    """Public Freecal reader with a lightweight HTTP backend and Selenium fallback."""

    def __init__(
        self,
        *,
        backend: Backend = "auto",
        timeout: float = 12.0,
        retries: int = 1,
    ) -> None:
        if backend not in {"auto", "http", "selenium"}:
            raise ValueError(f"Unsupported backend: {backend}")
        self.backend = backend
        self.timeout = timeout
        self.retries = retries
        self._http: Optional[FreecalHttpClient] = None
        self._selenium: Optional[FreecalScraper] = None
        self.last_backend: Optional[str] = None
        self.last_http_error: Optional[Exception] = None

    def __enter__(self) -> "FreecalClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _http_client(self) -> FreecalHttpClient:
        if self._http is None:
            self._http = FreecalHttpClient(
                timeout=self.timeout,
                retries=self.retries,
            )
        return self._http

    def _selenium_client(self) -> FreecalScraper:
        if self._selenium is None:
            self._selenium = FreecalScraper(
                timeout=self.timeout,
                retries=self.retries,
            )
        return self._selenium

    def fetch(
        self,
        user_id: str,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> FreecalResult:
        kwargs = {
            "year": year,
            "month": month,
            "start": start,
            "end": end,
        }

        if self.backend == "selenium":
            result = self._selenium_client().fetch(user_id, **kwargs)
            self.last_backend = "selenium"
            return result

        if self.backend == "http":
            result = self._http_client().fetch(user_id, **kwargs)
            self.last_backend = "http"
            return result

        # The direct endpoint needs a concrete month or range. Keep the legacy
        # browser behavior for a bare member URL with no date scope.
        can_use_http = (year is not None and month is not None) or (
            start is not None and end is not None
        )
        if can_use_http:
            try:
                result = self._http_client().fetch(user_id, **kwargs)
                self.last_backend = "http"
                self.last_http_error = None
                return result
            except FreecalHttpError as exc:
                self.last_http_error = exc

        result = self._selenium_client().fetch(user_id, **kwargs)
        self.last_backend = "selenium"
        return result

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None
        if self._selenium is not None:
            self._selenium.close()
            self._selenium = None
