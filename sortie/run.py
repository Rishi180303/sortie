from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from sortie.alerts.diff import Alert, mark_alerted, transitions
from sortie.alerts.digest import build_digest, is_empty, render_html, render_text, subject
from sortie.alerts.send import send_email
from sortie.alerts.state import compute_film_states
from sortie.clients.letterboxd import LetterboxdClient
from sortie.clients.tmdb import TmdbClient
from sortie.config import Config, Secrets
from sortie.http import HttpClient
from sortie.matching.resolve import ResolveResult, resolve_pending
from sortie.models import FetchLog, FilmState, MatchQueue
from sortie.sources.base import ShowtimeSource
from sortie.sync.films import hydrate_film
from sortie.sync.showtimes import SweepResult, sweep_showtimes
from sortie.sync.theatres import refresh_theatres
from sortie.sync.watchlist import WatchlistSyncResult, sync_watchlist


@dataclass
class Runtime:
    sources: list[ShowtimeSource]
    tmdb: TmdbClient
    lb: LetterboxdClient
    http_clients: list[HttpClient] = field(default_factory=list)
    mailer: Callable[[str, str, str], str] | None = None


@dataclass
class RunReport:
    today: date
    watchlist: WatchlistSyncResult | None = None
    theatres_refreshed: int = 0
    sweeps: list[SweepResult] = field(default_factory=list)
    resolves: list[ResolveResult] = field(default_factory=list)
    states: int = 0
    alerts: int = 0
    emailed: bool = False
    failures: list[str] = field(default_factory=list)
    health: list[str] = field(default_factory=list)


def build_runtime(cfg: Config, secrets: Secrets, archive_dir: Path = Path("raw")) -> Runtime:
    tmdb_http = HttpClient(source="tmdb", min_interval_s=0.05)
    lb_http = HttpClient(source="letterboxd", min_interval_s=1.0, archive_dir=archive_dir)
    mail_http = HttpClient(source="resend", min_interval_s=0)
    sources: list[ShowtimeSource] = []
    clients = [tmdb_http, lb_http, mail_http]
    if cfg.sources.fandango:
        from sortie.sources.fandango import FandangoSource, make_fandango_http

        fh = make_fandango_http(archive_dir)
        clients.append(fh)
        sources.append(FandangoSource(fh))

    mailer = None
    if secrets.resend_api_key and secrets.alert_email_to:

        def mailer(s: str, t: str, h: str) -> str:
            return send_email(mail_http, secrets.resend_api_key, secrets.alert_email_to, s, t, h)

    return Runtime(
        sources=sources,
        tmdb=TmdbClient(secrets.tmdb_api_key, tmdb_http),
        lb=LetterboxdClient(lb_http),
        http_clients=clients,
        mailer=mailer,
    )


def _theatres_stale(db: Session, source_name: str, now: datetime, days: int) -> bool:
    last = db.execute(
        select(func.max(FetchLog.run_at)).where(
            FetchLog.source == source_name, FetchLog.target == "theatres", FetchLog.ok.is_(True)
        )
    ).scalar()
    return last is None or now - last > timedelta(days=days)


def _flush_fetch_logs(db: Session, rt: Runtime, now: datetime) -> None:
    for c in rt.http_clients:
        for rec in c.records:
            db.add(
                FetchLog(
                    run_at=now,
                    source=rec.source,
                    target=rec.target[:300],
                    http_status=rec.status,
                    ok=rec.ok,
                    error=(rec.error or "")[:1000] or None,
                )
            )
        c.records.clear()


def run_daily(
    session_factory: sessionmaker[Session],
    cfg: Config,
    secrets: Secrets,
    rt: Runtime,
    *,
    today: date | None = None,
    now: datetime | None = None,
    theatre_refresh_days: int = 30,
) -> RunReport:
    now = now or datetime.now(UTC)
    today = today or now.astimezone().date()
    report = RunReport(today=today)

    with session_factory() as db:

        def ensure_film(tid: int) -> None:
            hydrate_film(db, rt.tmdb, tid, now)

        # 1-2. watchlist sync + film hydration
        try:
            report.watchlist = sync_watchlist(
                db, rt.lb, cfg.letterboxd.username, now, ensure_film=ensure_film
            )
            w = report.watchlist
            report.health.append(
                f"watchlist: {w.total_active} active, +{w.added} -{w.removed}, "
                f"{w.unresolved} unresolved"
            )
            for err in w.errors:
                report.health.append(f"watchlist: {err}")
        except Exception as e:  # one source failing must not stop the run
            report.failures.append(f"watchlist sync: {e}")
        db.commit()

        # 3. theatres, refreshed every theatre_refresh_days
        for src in rt.sources:
            if _theatres_stale(db, src.name, now, theatre_refresh_days):
                try:
                    n = refresh_theatres(
                        db, src, cfg.location.postal_code, cfg.location.radius_miles
                    )
                    report.theatres_refreshed += n
                    db.add(
                        FetchLog(run_at=now, source=src.name, target="theatres", rows=n, ok=True)
                    )
                except Exception as e:  # one source failing must not stop the run
                    report.failures.append(f"{src.name} theatres: {e}")
                    db.add(
                        FetchLog(
                            run_at=now,
                            source=src.name,
                            target="theatres",
                            ok=False,
                            error=str(e)[:1000],
                        )
                    )
        db.commit()

        # 4. showtime sweep
        for src in rt.sources:
            sw = sweep_showtimes(db, src, now, today)
            report.sweeps.append(sw)
            report.failures.extend(sw.failures)
            report.health.append(
                f"{src.name}: {sw.theatres} theatres, {sw.source_films_new} new films, "
                f"{sw.showings_upserted} showings"
            )
        db.commit()

        # 5. resolve source films against tmdb
        for src in rt.sources:
            try:
                rr = resolve_pending(db, src, rt.tmdb, cfg.matching, now)
            except Exception as e:  # one source failing must not stop the run
                report.failures.append(f"{src.name} resolve: {e}")
                continue
            report.resolves.append(rr)
            report.health.extend(f"{src.name} resolve: {e}" for e in rr.errors)
            if rr.resolved or rr.queued:
                report.health.append(
                    f"{src.name} resolve: {rr.resolved} matched, {rr.queued} queued"
                )
        db.commit()

        # 7-8. per-film state + alert transitions
        report.states = compute_film_states(db, today, now)
        alerts: dict[int, list[Alert]] = {}
        for state in db.execute(select(FilmState).where(FilmState.last_computed == now)).scalars():
            ts = transitions(state, today, cfg.alerts.approaching_days)
            if ts:
                alerts[state.tmdb_id] = ts
                if rt.mailer is not None:
                    mark_alerted(state, ts, now)
        report.alerts = len(alerts)
        needs_input = (
            db.execute(
                select(func.count()).select_from(MatchQueue).where(MatchQueue.resolved_at.is_(None))
            ).scalar()
            or 0
        )

        # 9. build digest and send if there is something to say
        digest = build_digest(db, alerts, today, needs_input, report.health, report.failures)
        heartbeat = today.weekday() == 6
        if rt.mailer is not None and (not is_empty(digest) or heartbeat):
            rt.mailer(subject(digest), render_text(digest), render_html(digest))
            report.emailed = True

        # 10. flush fetch logs
        _flush_fetch_logs(db, rt, now)
        db.commit()
    return report
