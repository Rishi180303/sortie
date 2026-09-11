# sortie

sortie emails you when a film on your Letterboxd watchlist gets showtimes at a cinema near you.

I go to the cinema most weekends and add a lot of films to my watchlist from trailers. The annoying part is finding out *when* those films actually reach a screen near me. They open on different days at different theatres, re-releases of old films only play at a few locations, and checking the AMC app and Fandango theatre by theatre every weekend gets old. sortie does the checking.

*sortie* is French for a film's theatrical release.

## what it does

Every morning it:

1. pulls your public Letterboxd watchlist
2. pulls showtimes for every theatre within a radius of your zip code
3. works out which watchlist films are playing, where, and from what date
4. emails you one digest

The email is built around the thing you actually want to know — the earliest date a film plays anywhere near you, and the earliest date at *your* theatres, because those are often not the same:

```
PRIMETIME
  Earliest anywhere   Fri Sep 25  ·  Landmark Midtown         18 mi
  Your theatres       Wed Sep 30  ·  AMC Metro 14
  ↳ 5 days earlier if you drive
```

It also tells you when an older film comes back to a screen near you, and it only emails when something changed. Silence means nothing new, not that it broke — any failure emails you immediately.

## status

Early. The collector is being built in stages and the pieces that exist are tested and working against the real sites: watchlist sync, film metadata, the database, and theatre discovery. The showtime source, the matching engine, and the email digest are next. The web UI for picking theatres comes after that. Until the daily runner lands, there is nothing to run yet.

## how it matches films

Letterboxd and cinema listings share no film IDs, so matching is the hard part. Letterboxd gives a TMDb id for each film, which is exact. Cinema listings only give a title, so sortie looks the title up on TMDb and scores the candidates on director, runtime, and cast. The year is deliberately *not* a deciding signal, because listings stamp re-releases with the current year. Anything it can't match with confidence goes into a queue for you to click on, rather than guessing and emailing you about the wrong film.

## setup

You need [uv](https://docs.astral.sh/uv/), Docker (or OrbStack), a free [TMDb API key](https://www.themoviedb.org/settings/api), a free [Resend](https://resend.com) API key, and a public Letterboxd watchlist.

```bash
git clone https://github.com/Rishi180303/sortie.git
cd sortie
uv sync
docker compose up -d db
```

Create a file called `.env` in the project folder (it is git-ignored) with:

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

Resend can deliver to your own account email without any domain setup, which is all a single-user tool needs.

## a note on data sources

The AMC catalog API is free for non-commercial use on request and is the preferred source for AMC theatres. Fandango covers every chain but has no public API, and its terms prohibit automated access, so it is **off by default** — you turn it on knowingly in `config.toml`. sortie requests politely (one request a second, once a day) and keeps a copy of every response so a broken parser can be fixed offline.

## running the tests

```bash
docker compose up -d db
uv run pytest -q
```

## built with

Python 3.12, SQLAlchemy and Alembic on Postgres, curl_cffi for fetching, FastAPI for a small health API, Resend for email, pytest, ruff, GitHub Actions. The web UI will be Next.js.
