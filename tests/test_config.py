from pathlib import Path

import pytest

from sortie.config import Config, load_config, load_secrets

TOML = """
[location]
postal_code = "10001"
radius_miles = 30

[letterboxd]
username = "example-user"

[sources]
fandango = true

[alerts]
send_hour = 7

[matching]
min_score = 0.7
"""


def test_load_config_reads_values_and_defaults(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text(TOML)
    cfg = load_config(p)
    assert isinstance(cfg, Config)
    assert cfg.location.postal_code == "10001"
    assert cfg.location.radius_miles == 30
    assert cfg.letterboxd.username == "example-user"
    assert cfg.sources.fandango is True
    assert cfg.sources.amc is True  # default
    assert cfg.alerts.send_hour == 7
    assert cfg.alerts.approaching_days == 5  # default
    assert cfg.matching.min_score == 0.7
    assert cfg.matching.min_margin == 0.2  # default


def test_load_config_missing_required_section_raises(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('[location]\npostal_code = "10001"\n')
    with pytest.raises(ValueError):
        load_config(p)


def test_load_secrets_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("TMDB_API_KEY", "abc")
    monkeypatch.setenv("ALERT_EMAIL_TO", "me@example.com")
    s = load_secrets(env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@h/db"
    assert s.tmdb_api_key == "abc"
    assert s.alert_email_to == "me@example.com"
    assert s.resend_api_key == ""
