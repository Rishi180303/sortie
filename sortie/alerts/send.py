import json

from sortie.http import HttpClient

RESEND_URL = "https://api.resend.com/emails"


def send_email(
    http: HttpClient,
    api_key: str,
    to: str,
    subject: str,
    text: str,
    html: str,
    from_addr: str = "sortie <onboarding@resend.dev>",
) -> str:
    r = http.post_json(
        RESEND_URL,
        target="resend-email",
        headers={"Authorization": f"Bearer {api_key}"},
        body={"from": from_addr, "to": [to], "subject": subject, "text": text, "html": html},
    )
    return json.loads(r.text)["id"]
