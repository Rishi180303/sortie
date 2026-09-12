from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import func, select

from sortie.config import load_config, load_secrets
from sortie.db import make_engine, make_session_factory
from sortie.models import FetchLog
from sortie.run import build_runtime, run_daily

app = FastAPI(title="sortie collector")
SessionFactory = None  # set on first use; tests monkeypatch this


def _factory():
    global SessionFactory
    if SessionFactory is None:
        SessionFactory = make_session_factory(make_engine(load_secrets().database_url))
    return SessionFactory


@app.get("/health")
def health():
    with _factory()() as db:
        last = db.execute(select(func.max(FetchLog.run_at))).scalar()
    return {
        "ok": True,
        "last_fetch_at": last.isoformat() if last else None,
        "now": datetime.now(UTC).isoformat(),
    }


@app.post("/run")
def run_now():
    cfg, secrets = load_config(), load_secrets()
    report = run_daily(_factory(), cfg, secrets, build_runtime(cfg, secrets))
    return {
        "today": report.today.isoformat(),
        "alerts": report.alerts,
        "emailed": report.emailed,
        "failures": report.failures,
        "health": report.health,
    }
