import tomllib
from pathlib import Path

from pydantic import BaseModel, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    tmdb_api_key: str
    resend_api_key: str = ""
    alert_email_to: str = ""
    amc_vendor_key: str = ""

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, v: str) -> str:
        # hosted providers hand out postgresql://, which makes sqlalchemy reach for psycopg2
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v


class LocationCfg(BaseModel):
    postal_code: str
    radius_miles: int = 25


class LetterboxdCfg(BaseModel):
    username: str


class SourcesCfg(BaseModel):
    amc: bool = True
    fandango: bool = False
    fathom: bool = True


class AlertsCfg(BaseModel):
    send_hour: int = 9
    approaching_days: int = 5
    rerelease_gap_years: int = 2


class MatchingCfg(BaseModel):
    min_score: float = 0.6
    min_margin: float = 0.2


class Config(BaseModel):
    location: LocationCfg
    letterboxd: LetterboxdCfg
    sources: SourcesCfg = SourcesCfg()
    alerts: AlertsCfg = AlertsCfg()
    matching: MatchingCfg = MatchingCfg()


def load_config(path: Path = Path("config.toml")) -> Config:
    with path.open("rb") as f:
        data = tomllib.load(f)
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"invalid {path}: {e}") from e


def load_secrets(env_file: str | None = ".env") -> Secrets:
    return Secrets(_env_file=env_file)  # type: ignore[call-arg]
