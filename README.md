# sortie

sortie emails you when a film on your Letterboxd watchlist gets showtimes at a cinema near you.

I go to the cinema most weekends and add a lot of films to my watchlist from trailers. The annoying part is finding out when those films actually reach a screen near me. They open on different days at different theatres, re-releases of old films only play at a few locations, and checking the AMC app and Fandango theatre by theatre every weekend gets old. sortie does the checking.

## what it does

Every morning it:

1. pulls your public Letterboxd watchlist
2. pulls showtimes for every theatre within a radius of your zip code
3. works out which watchlist films are playing, where, and from what date
4. emails you one digest

A film in the email looks like this:

```
PRIMETIME
  Earliest anywhere   Fri Sep 25  ·  Landmark Midtown         18 mi
  Your theatres       Wed Sep 30  ·  AMC Metro 14
  ↳ 5 days earlier if you drive
```

It also tells you when an older film comes back to a screen near you. It only emails when something changed, and if it breaks it emails you right away, so a quiet day really is a quiet day.

## status

The collector runs end to end and is tested against the real sites: watchlist sync, theatre discovery, the Fandango showtime source, matching against TMDb, and the email digest. `sortie run` does a full daily pass. A web ui now covers the match queue and cinema tracking, see "the web ui" below. Fathom's event feed is used to confirm re-releases. AMC is not implemented yet, so Fandango is the only showtime source.

## how it matches films

Letterboxd and cinema listings share no film IDs, so matching is the hard part. Letterboxd gives a TMDb id for each film. Cinema listings only give a title, so sortie looks the title up on TMDb and scores the candidates on director, runtime, and cast. The year is not a deciding signal on purpose, because listings stamp re-releases with the current year. Anything it can't match with confidence goes into a queue for you to click on instead of guessing.

sortie also flags re-releases. A film whose first US release was two or more years ago is a candidate, and it counts as a re-release when the listing says so (anniversary, restoration, remastered, re-release) or when Fathom lists it. The gap alone is never enough. Re-releases near you get their own section in the email, even when the film is not on your watchlist.

## setup

You need [uv](https://docs.astral.sh/uv/), Docker (or OrbStack), a free [TMDb API key](https://www.themoviedb.org/settings/api), a free [Resend](https://resend.com) API key, and a public Letterboxd watchlist.

```bash
git clone https://github.com/Rishi180303/sortie.git
cd sortie
uv sync
docker compose up -d db
```

Create a file called `.env` in the project folder (git ignores it) with:

```
DATABASE_URL=postgresql+psycopg://sortie:sortie@localhost:5432/sortie
TMDB_API_KEY=your-tmdb-key
RESEND_API_KEY=your-resend-key
ALERT_EMAIL_TO=you@example.com
AMC_VENDOR_KEY=
```

Then copy the config and fill in your zip code and Letterboxd username:

```bash
cp config.example.toml config.toml
uv run alembic upgrade head
```

`alembic upgrade head` reads `DATABASE_URL` from `.env`, the same as the app does, so it needs no extra setup.

Resend can send to your own account email without any domain setup.

## running it

sortie runs itself on github actions. the `daily` workflow wakes at 11:30 UTC,
applies migrations, and runs the collector against a hosted postgres. it emails
you only when something changed, and it emails you whenever a source failed.

to set it up on your own fork you need a postgres database the workflow can
reach. neon's free tier works. then add these repository secrets under
settings, secrets and variables, actions:

| secret | what it holds |
|---|---|
| `DATABASE_URL` | your database url, using the `postgresql+psycopg://` scheme |
| `TMDB_API_KEY` | your tmdb key |
| `RESEND_API_KEY` | your resend key |
| `ALERT_EMAIL_TO` | where the digest is sent |
| `SORTIE_CONFIG` | the contents of your `config.toml` |

`config.toml` holds your location and letterboxd username, so it is never
committed. the workflow writes it from the secret at the start of each run.
copy `config.example.toml` to build yours.

to change when the digest arrives, edit the cron in
`.github/workflows/daily.yml`. the `send_hour` setting in `config.toml` only
applies to `sortie schedule`, which is the old long-running local mode.

you can also run it by hand from the actions tab with "run workflow", or
locally once `.env` and `config.toml` exist:

```bash
docker compose up -d db
uv run alembic upgrade head
uv run sortie run
```

sortie has a few other subcommands, run locally the same way:

```bash
uv run sortie refresh-theatres   # fetch theatres near your zip code
uv run sortie schedule           # run once a day at [alerts].send_hour, the old local mode
uv run sortie serve              # start a small api with a /health endpoint
```

run `refresh-theatres` once before your first `run`. after that, `run` refreshes theatres on its own every 30 days. pick favourites and toggle which cinemas are tracked from the cinemas screen in the web ui. if you are not running the web ui, mark a favourite directly in postgres instead:

```sql
update theatre set is_favourite = true where name = 'AMC Metro 14';
```

## the web ui

the `web` folder is a small next.js app that reads the same database the collector writes to. two screens:

- matches is the queue of cinema listings the collector could not match with confidence on its own. each one shows the candidates side by side so you can pick the right film or reject the listing.
- cinemas lists every cinema the collector found, with a toggle for tracked and favourite, and the distance to each one.

to run it locally: `cd web && npm install && npm run dev`, with `DATABASE_URL` and `SORTIE_PASSWORD` set in `web/.env.local`. any postgres url works, not just neon's.

it deploys to vercel from the `web` directory. vercel needs two environment variables: `DATABASE_URL`, set to the neon **pooled** connection string (its host contains `-pooler`) using the plain `postgresql://` scheme rather than the `postgresql+psycopg://` scheme the python side uses, and `SORTIE_PASSWORD`, set to a password of your choice.

the deployment is public, so the whole site sits behind that one password. every request without it gets a basic auth prompt instead of a page. pick a password that is long, random and plain ascii: there is no rate limit on attempts, and non-ascii characters break the basic auth decode.

## a note on data sources

The AMC catalog API is free for noncommercial use on request and is the preferred source for AMC theatres, but the AMC adapter has not been built yet. Fandango covers every chain but has no public API and its terms prohibit automated access, so it is off by default and you turn it on yourself with `fandango = true` in `config.toml`. Fandango is the only showtime source that exists right now, so with the default `fandango = false` sortie has nothing to check and will never find a showtime. sortie requests politely, one request a second and once a day, and keeps a copy of every response so a broken parser can be fixed offline.

## running the tests

```bash
docker compose up -d db
uv run pytest -q
```

## built with

Python 3.12, SQLAlchemy and Alembic on Postgres, curl_cffi for fetching, FastAPI for a small health API, Resend for email, pytest, ruff, GitHub Actions. The web UI is Next.js.
