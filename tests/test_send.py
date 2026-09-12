import json

import pytest

from sortie.alerts.send import send_email
from sortie.http import FetchError


def test_send_email_posts_to_resend(routed, http):
    routed.add("api.resend.com/emails", 200, '{"id": "msg_123"}')
    mid = send_email(http, "re_key", "me@example.com", "subj", "text body", "<p>html</p>")
    assert mid == "msg_123"
    method, url, body = routed.calls[0]
    assert method == "POST" and url == "https://api.resend.com/emails"
    payload = json.loads(body)
    assert payload == {
        "from": "sortie <onboarding@resend.dev>",
        "to": ["me@example.com"],
        "subject": "subj",
        "text": "text body",
        "html": "<p>html</p>",
    }


def test_send_email_raises_on_failure(routed, http):
    routed.add("api.resend.com/emails", 422, '{"message":"bad"}')
    with pytest.raises(FetchError):
        send_email(http, "re_key", "me@example.com", "s", "t", "h")
