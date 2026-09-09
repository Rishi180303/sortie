from urllib.parse import urlencode

import pytest

from sortie.http import HttpClient


class RoutedTransport:
    """Routes requests to canned responses by URL substring, in registration order."""

    def __init__(self):
        self.routes: list[tuple[str, int, str]] = []
        self.calls: list[tuple[str, str, str | None]] = []

    def add(self, substring: str, status: int, text: str) -> None:
        self.routes.append((substring, status, text))

    def __call__(self, method, url, headers, params, body):
        full = url + ("?" + urlencode(params) if params else "")
        self.calls.append((method, full, body))
        for sub, status, text in self.routes:
            if sub in full:
                return status, text
        raise AssertionError(f"unrouted request: {method} {full}")


@pytest.fixture
def routed():
    return RoutedTransport()


@pytest.fixture
def http(routed):
    return HttpClient(source="test", transport=routed, min_interval_s=0, sleeper=lambda s: None)
