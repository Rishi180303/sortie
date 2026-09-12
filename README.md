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

The collector runs end to end and is tested against the real sites: watchlist sync, theatre discovery, the Fandango showtime source, matching against TMDb, and the email digest. `sortie run` does a full daily pass. A web page for picking favourite theatres has not been built yet. For now you mark a theatre as a favourite with a direct sql update, see "running it" below. AMC and Fathom are not implemented yet either, so Fandango is the only showtime source that exists.

## how it matches films

Letterboxd and cinema listings share no film IDs, so matching is the hard part. Letterboxd gives a TMDb id for each film. Cinema listings only give a title, so sortie looks the title up on TMDb and scores the candidates on director, runtime, and cast. The year is not a deciding signal on purpose, because listings stamp re-releases with the current year. Anything it can't match with confidence goes into a queue for you to click on instead of guessing.

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

```bash
uv run sortie refresh-theatres   # fetch theatres near your zip code
uv run sortie run                # one full pass: sync watchlist, sweep showtimes, match, email
uv run sortie schedule           # run once a day at [alerts].send_hour, forever
uv run sortie serve              # start a small health-check API
```

Run `refresh-theatres` once before your first `run`. After that, `run` refreshes theatres on its own every 30 days.

There is no command yet for picking favourite theatres. That is plan 3. Until then, mark one directly in postgres:

```sql
update theatre set is_favourite = true where name = 'AMC Metro 14';
```

## a note on data sources

The AMC catalog API is free for noncommercial use on request and is the preferred source for AMC theatres, but the AMC adapter has not been built yet. Fandango covers every chain but has no public API and its terms prohibit automated access, so it is off by default and you turn it on yourself with `fandango = true` in `config.toml`. Fandango is the only showtime source that exists right now, so with the default `fandango = false` sortie has nothing to check and will never find a showtime. sortie requests politely, one request a second and once a day, and keeps a copy of every response so a broken parser can be fixed offline.

## running the tests

```bash
docker compose up -d db
uv run pytest -q
```

## built with

Python 3.12, SQLAlchemy and Alembic on Postgres, curl_cffi for fetching, FastAPI for a small health API, Resend for email, pytest, ruff, GitHub Actions. The web UI will be Next.js.
