import argparse
import sys
import time
from datetime import datetime, timedelta

from sortie.config import load_config, load_secrets
from sortie.db import make_engine, make_session_factory
from sortie.run import build_runtime, run_daily
from sortie.sync.theatres import refresh_theatres


def _factory(secrets):
    return make_session_factory(make_engine(secrets.database_url))


def cmd_run(_args) -> int:
    cfg, secrets = load_config(), load_secrets()
    report = run_daily(_factory(secrets), cfg, secrets, build_runtime(cfg, secrets))
    for h in report.health:
        print(h)
    for f in report.failures:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"alerts={report.alerts} emailed={report.emailed}")
    return 1 if report.failures else 0


def cmd_refresh_theatres(_args) -> int:
    cfg, secrets = load_config(), load_secrets()
    rt = build_runtime(cfg, secrets)
    with _factory(secrets)() as db:
        for src in rt.sources:
            n = refresh_theatres(db, src, cfg.location.postal_code, cfg.location.radius_miles)
            print(f"{src.name}: {n} theatres")
        db.commit()
    return 0


def _seconds_until(hour: int) -> float:
    now = datetime.now()
    nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


def cmd_schedule(_args) -> int:
    cfg = load_config()
    while True:
        wait = _seconds_until(cfg.alerts.send_hour)
        print(f"next run in {wait / 3600:.1f}h", flush=True)
        time.sleep(wait)
        try:
            cmd_run(None)
        except Exception as e:  # keep the loop alive even if a run fails
            print(f"run failed: {e}", file=sys.stderr, flush=True)


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("sortie.api:app", host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sortie")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="run the daily pipeline once").set_defaults(fn=cmd_run)
    sub.add_parser("refresh-theatres", help="re-fetch nearby theatres").set_defaults(
        fn=cmd_refresh_theatres
    )
    sub.add_parser("schedule", help="run daily at [alerts].send_hour").set_defaults(fn=cmd_schedule)
    s = sub.add_parser("serve", help="start the API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(fn=cmd_serve)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
