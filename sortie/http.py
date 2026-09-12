import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

Transport = Callable[
    [str, str, dict[str, str] | None, dict[str, str] | None, str | None], tuple[int, str]
]


class FetchError(Exception):
    def __init__(self, url: str, status: int | None, message: str):
        super().__init__(f"{message}: {url} (status={status})")
        self.url = url
        self.status = status


@dataclass
class FetchResult:
    status: int
    text: str
    url: str


@dataclass
class FetchRecord:
    source: str
    target: str
    url: str
    status: int | None
    ok: bool
    error: str | None = None


_RETRY_STATUSES = {403, 429}


def _retryable(status: int) -> bool:
    return status in _RETRY_STATUSES or 500 <= status < 600


def curl_cffi_transport(impersonate: str = "chrome") -> Transport:
    from curl_cffi import requests

    session = requests.Session(impersonate=impersonate)

    def transport(method, url, headers, params, json_body):
        if method == "POST":
            r = session.post(url, headers=headers, params=params, data=json_body, timeout=30)
        else:
            r = session.get(url, headers=headers, params=params, timeout=30)
        return r.status_code, r.text

    return transport


@dataclass(kw_only=True)
class HttpClient:
    source: str
    min_interval_s: float = 1.0
    archive_dir: Path | None = None
    warm_url: str | None = None
    retries: int = 3
    backoff_s: tuple[float, ...] = (5, 30, 120)
    transport: Transport | None = None
    sleeper: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    today: Callable[[], date] = date.today
    records: list[FetchRecord] = field(default_factory=list)
    _last_at: float | None = field(default=None, init=False)

    def __post_init__(self):
        if self.transport is None:
            self.transport = curl_cffi_transport()

    def _throttle(self) -> None:
        if self._last_at is not None:
            wait = self.min_interval_s - (self.clock() - self._last_at)
            if wait > 0:
                self.sleeper(wait)
        self._last_at = self.clock()

    def _raw(self, method, url, headers, params, body) -> tuple[int, str]:
        self._throttle()
        return self.transport(method, url, headers, params, body)

    def _archive(self, target: str, text: str) -> None:
        if self.archive_dir is None:
            return
        d = self.archive_dir / self.today().isoformat()
        d.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", target)[:120]
        ext = "json" if text.lstrip().startswith(("{", "[")) else "txt"
        # if we already saved this one today, number the new copy
        path = d / f"{self.source}-{safe}.{ext}"
        n = 1
        while path.exists():
            path = d / f"{self.source}-{safe}-{n}.{ext}"
            n += 1
        path.write_text(text)

    def _request(self, method, url, *, target, headers, params, body) -> FetchResult:
        last_status: int | None = None
        last_error: str | None = None
        text = ""
        for attempt in range(self.retries + 1):
            try:
                status, text = self._raw(method, url, headers, params, body)
            except OSError as e:
                # a transport error (timeout, dns, connection reset) is a retryable attempt too
                status, text, last_error = None, "", str(e)
            last_status = status
            if status is not None and 200 <= status < 300:
                self._archive(target, text)
                self.records.append(FetchRecord(self.source, target, url, status, True))
                return FetchResult(status, text, url)
            if attempt == self.retries or (status is not None and not _retryable(status)):
                break
            delay = self.backoff_s[min(attempt, len(self.backoff_s) - 1)]
            self.sleeper(delay)
            if self.warm_url:
                try:
                    self._raw("GET", self.warm_url, None, None, None)
                except OSError:
                    pass  # a failed warm-up only means the next attempt is not warmed
        if last_status is None:
            err = f"transport error after {self.retries + 1} attempt(s): {last_error}"
        else:
            err = f"HTTP {last_status} after {self.retries + 1} attempt(s)"
        # keep the failed body so we can see why the site blocked us
        if text:
            self._archive(f"{target}-{last_status}", text)
        self.records.append(FetchRecord(self.source, target, url, last_status, False, err))
        raise FetchError(url, last_status, err)

    def get(self, url: str, *, target: str, headers=None, params=None) -> FetchResult:
        return self._request("GET", url, target=target, headers=headers, params=params, body=None)

    def post_json(self, url: str, *, target: str, headers=None, body: dict) -> FetchResult:
        h = {"Content-Type": "application/json", **(headers or {})}
        return self._request(
            "POST", url, target=target, headers=h, params=None, body=json.dumps(body)
        )
