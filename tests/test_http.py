from datetime import date
from pathlib import Path

import pytest

from sortie.http import FetchError, HttpClient


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)  # list of (status, text)
        self.calls = []

    def __call__(self, method, url, headers, params, json_body):
        self.calls.append((method, url, headers, params, json_body))
        return self.responses.pop(0)


def make(responses, **kw):
    sleeps = []
    clock = {"t": 0.0}
    ft = FakeTransport(responses)
    c = HttpClient(
        source="test",
        transport=ft,
        sleeper=lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)),
        clock=lambda: clock["t"],
        today=lambda: date(2026, 9, 8),
        **kw,
    )
    return c, ft, sleeps, clock


def test_get_success_records_and_returns():
    c, ft, sleeps, _ = make([(200, "hello")])
    r = c.get("https://x.test/a", target="a")
    assert r.status == 200 and r.text == "hello"
    assert ft.calls[0][0] == "GET"
    assert c.records[-1].ok is True and c.records[-1].status == 200


def test_throttle_enforces_min_interval():
    c, ft, sleeps, clock = make([(200, "1"), (200, "2")], min_interval_s=1.0)
    c.get("https://x.test/1", target="1")
    c.get("https://x.test/2", target="2")
    assert sum(sleeps) >= 1.0


def test_retries_on_403_then_succeeds_and_rewarms():
    c, ft, sleeps, _ = make(
        [(403, ""), (200, "warm"), (200, "ok")],
        min_interval_s=0,
        warm_url="https://x.test/",
        backoff_s=(5, 30, 120),
    )
    r = c.get("https://x.test/a", target="a")
    assert r.text == "ok"
    assert [u for _, u, *_ in ft.calls] == [
        "https://x.test/a",
        "https://x.test/",
        "https://x.test/a",
    ]
    assert 5 in sleeps


def test_gives_up_after_retries():
    c, ft, sleeps, _ = make([(403, "")] * 4, min_interval_s=0, retries=3, backoff_s=(0, 0, 0))
    with pytest.raises(FetchError):
        c.get("https://x.test/a", target="a")
    assert c.records[-1].ok is False and c.records[-1].status == 403


def test_404_is_not_retried():
    c, ft, sleeps, _ = make([(404, "")], min_interval_s=0)
    with pytest.raises(FetchError):
        c.get("https://x.test/a", target="a")
    assert len(ft.calls) == 1


class RaisingTransport:
    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def __call__(self, method, url, headers, params, json_body):
        self.calls += 1
        raise self.exc


def test_transport_error_is_retried_then_raises_fetch_error():
    ft = RaisingTransport(OSError("connection reset"))
    c = HttpClient(source="test", transport=ft, min_interval_s=0, sleeper=lambda s: None, retries=2)
    with pytest.raises(FetchError):
        c.get("https://x.test/a", target="a")
    assert ft.calls == 3  # initial attempt + 2 retries
    assert c.records[-1].ok is False and c.records[-1].status is None


def test_archives_response(tmp_path: Path):
    c, ft, _, _ = make([(200, '{"a":1}')], min_interval_s=0, archive_dir=tmp_path)
    c.get("https://x.test/napi/thing?x=1", target="thing-x1")
    files = list((tmp_path / "2026-09-08").iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("test-thing-x1")
    assert files[0].read_text() == '{"a":1}'


def test_archives_failed_response(tmp_path: Path):
    c, ft, _, _ = make([(403, "blocked")], min_interval_s=0, retries=0, archive_dir=tmp_path)
    with pytest.raises(FetchError):
        c.get("https://x.test/napi/thing", target="thing")
    files = list((tmp_path / "2026-09-08").iterdir())
    assert len(files) == 1
    assert files[0].name == "test-thing-403.txt"
    assert files[0].read_text() == "blocked"


def test_post_json_sends_body():
    c, ft, _, _ = make([(200, '{"id":"m1"}')], min_interval_s=0)
    r = c.post_json("https://x.test/emails", target="emails", body={"to": ["a@b.c"]})
    assert r.status == 200
    assert ft.calls[0][0] == "POST" and ft.calls[0][4] == '{"to": ["a@b.c"]}'


class FlakyWarmTransport:
    # the real request keeps failing with 403 and the warm-up ping raises
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, params, json_body):
        self.calls.append(url)
        if url == "https://x.test/":
            raise OSError("warm-up reset")
        return 403, "blocked"


def test_warm_up_transport_error_does_not_escape():
    ft = FlakyWarmTransport()
    c = HttpClient(
        source="test",
        transport=ft,
        min_interval_s=0,
        sleeper=lambda s: None,
        retries=1,
        warm_url="https://x.test/",
    )
    with pytest.raises(FetchError):
        c.get("https://x.test/a", target="a")
    assert ft.calls == ["https://x.test/a", "https://x.test/", "https://x.test/a"]


class ThenRaisingTransport:
    # first a 500 with a body, then the connection drops
    def __init__(self):
        self.calls = 0

    def __call__(self, method, url, headers, params, json_body):
        self.calls += 1
        if self.calls == 1:
            return 500, "server error page"
        raise OSError("connection reset")


def test_transport_error_after_http_error_archives_nothing(tmp_path: Path):
    c = HttpClient(
        source="test",
        transport=ThenRaisingTransport(),
        min_interval_s=0,
        sleeper=lambda s: None,
        retries=1,
        archive_dir=tmp_path,
        today=lambda: date(2026, 9, 8),
    )
    with pytest.raises(FetchError):
        c.get("https://x.test/a", target="a")
    assert not (tmp_path / "2026-09-08").exists()
    assert c.records[-1].status is None
