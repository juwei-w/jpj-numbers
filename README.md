# JPJ Available Plate-Number Scraper

Collects **every available car registration number** from the JPJ **mySIKAP**
reserve-number portal — both categories, nationwide — merges them into a dated
snapshot, and publishes a searchable web page.

- **Semasa** (current/running numbers) — all 32 states, fixed **RM 310.00** each.
- **Istimewa** (premium/special series) — nationwide, per-number *Harga Minimum*.

Latest published page: **https://juwei-w.github.io/jpj-numbers/**

## One command

```bash
python scripts/run_all.py
```

That single command is fully hands-off — it logs in (solving the login captcha
automatically, offline), scrapes Istimewa + Semasa, merges everything into
`results/all_available_numbers_<date>.md` + `.html`, regenerates `index.html`,
and pushes it live to GitHub Pages.

Useful flags:

| flag | effect |
|---|---|
| `--resume` | continue an interrupted run instead of starting fresh |
| `--no-publish` | build the files locally, don't push |
| `--skip-semasa` / `--skip-istimewa` | run only one category |
| `--date YYYY-MM-DD` | override the snapshot date |

## Setup

```bash
cd jpj_plate_scraper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

cp config.example.json config.local.json     # then fill in your JPJ credentials
```

Credentials are read from `config.local.json` (gitignored) or the env vars
`JPJ_USER` / `JPJ_PASS`. **They are never committed.**

## How it works

- **Login (`login_and_save_cookies.py`)** — the 5-letter *Kod Sekuriti* captcha is
  read automatically by an offline OCR model (`ddddocr`). A wrong guess just
  refreshes the captcha and retries, so login is hands-off. Falls back to a manual
  browser prompt only if auto-solving fails repeatedly. The session is saved to
  `work/auth.json` and reused until it expires.
- **The ZK form** (`#/vel/04velnummgt/vel04ReserveNumberAdd`) is a ZK 5.0.7
  server-side app — no JSON API, widget IDs regenerate each load. Istimewa is
  driven via the raw `zkau` POST protocol (`scrape_istimewa.py`); Semasa via DOM
  automation (`scrape_numbers.py`). See `scrape_istimewa.py`'s header for the
  hard-won protocol details.
- **Engines** — `run_istimewa_fast.py` (worker pool, one task per premium series)
  and `run_semasa.py` (worker pool, one task per state) scan 50-number windows,
  resume from per-task sidecars in `work/`, and re-login automatically on expiry.
- **Merge + render** — `combine_all.py` (markdown) and `make_viewable.py`
  (searchable HTML + `index.html`) read the `work/` sidecars via `dataload.py`.

## Layout

```
scripts/         all code (run_all.py is the entry point)
results/         deliverables — committed: all_available_numbers_<date>.{md,html}
index.html       the live page GitHub Pages serves (latest snapshot)
work/            intermediate sidecars, logs, session — gitignored
config.local.json   your credentials — gitignored
config.example.json template to copy
```

## Notes

- This automates the **account holder's own** mySIKAP login for personal data
  collection. Use only on an account you own and within JPJ's terms; the scrapers
  rate-limit politely.
- Availability changes over time, so each run captures a fresh current snapshot.
