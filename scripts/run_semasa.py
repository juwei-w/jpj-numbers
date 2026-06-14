"""
Semasa engine — concurrent worker POOL at (state, series) granularity.

Instead of one worker per state (where a huge state like Selangor hogs a worker and
stalls the finish), it discovers each state's series and pools over (state, series)
tasks, so the heavy states' series spread across the whole pool — no single task can
dominate the tail. Resumable, auto re-login on expiry, scopeable with --states (the
matrix workflow hands each shard a slice).

  python run_semasa.py                         # all 32 states
  python run_semasa.py --states "SELANGOR"     # one state, its series split across workers
  SEMASA_WORKERS=2 python run_semasa.py --states "KEDAH,PERLIS"
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import login_and_save_cookies as login

HERE = config.SCRIPTS
PY = sys.executable
SCRAPER = os.path.join(HERE, "scrape_numbers.py")
ISTIMEWA = os.path.join(HERE, "scrape_istimewa.py")
AUTH = config.AUTH
MAX_CYCLES = 40
TASKS_CACHE = os.path.join(config.WORK, "semasa_tasks.json")


def san(state):
    return re.sub(r"[^A-Za-z0-9]+", "_", state).strip("_")


def wout(state, series):
    # Unique per (state, series) -> matrix artifacts never collide; dataload globs numbers_*.md.json.
    return os.path.join(config.WORK, f"numbers_{san(state)}__{series}.md")


def rec(state, series):
    j = wout(state, series) + ".json"
    if os.path.exists(j):
        try:
            return json.load(open(j))
        except Exception:
            pass
    return {}


def done(state, series):
    return rec(state, series).get(state, {}).get(series) is not None


def count(state, series):
    return len(rec(state, series).get(state, {}).get(series) or [])


def _validate():
    r = subprocess.run([PY, ISTIMEWA, "--auth", AUTH, "--test"], capture_output=True, text=True)
    return "PASS=True" in (r.stdout or "")


def _ensure_session(headless):
    if os.path.exists(AUTH) and _validate():
        return True
    return login.run(save_path=AUTH, headless=headless)


def _discover(states, headless):
    """Return [(state, series)] for the scoped states, caching the series list so a
    resume/re-run doesn't re-query."""
    cache = {}
    if os.path.exists(TASKS_CACHE):
        try:
            cache = json.load(open(TASKS_CACHE))
        except Exception:
            cache = {}
    need = [s for s in states if s not in cache]
    for _ in range(3):
        if not need:
            break
        r = subprocess.run([PY, SCRAPER, "--auth", AUTH, "--states", ",".join(need), "--list-series"],
                           capture_output=True, text=True)
        try:
            m = json.loads((r.stdout or "").strip().splitlines()[-1])
        except Exception:
            m = {}
        if any(m.get(s) for s in need):
            cache.update(m)
            json.dump(cache, open(TASKS_CACHE, "w"))
            need = [s for s in states if s not in cache]
        else:
            login.run(save_path=AUTH, headless=headless)   # session likely dead -> re-login
    return [(s, ser) for s in states for ser in cache.get(s, [])]


def run(states=None, headless=True):
    states = list(states) if states else list(config.STATES)
    config.ensure_dirs()
    if not _ensure_session(headless):
        print("!! login failed — aborting semasa."); return False
    tasks = _discover(states, headless)
    if not tasks:
        print("== semasa: no released series for these states =="); return True
    K = min(int(os.environ.get("SEMASA_WORKERS", "16")), len(tasks))

    def all_done():
        return all(done(s, ser) for s, ser in tasks)

    def total():
        return sum(count(s, ser) for s, ser in tasks)

    def progress(running):
        nd = sum(1 for s, ser in tasks if done(s, ser))
        rs = ", ".join(f"{s.split()[0][:4]}:{ser}" for s, ser in running) or "—"
        return f"SEMASA [{nd}/{len(tasks)} tasks | {total()} nums | {K}w] running: {rs}"

    def run_pool():
        pool = {}
        stalls = 0
        while True:
            for t, (p, c0) in list(pool.items()):
                if p.poll() is not None:
                    del pool[t]
                    if done(*t) or count(*t) > c0:
                        stalls = 0
                    else:
                        stalls += 1
            if all_done():
                return True
            if stalls >= K:                 # K consecutive no-progress exits -> session dead
                return False
            while len(pool) < K:
                nxt = next((t for t in tasks if not done(*t) and t not in pool), None)
                if nxt is None:
                    break
                s, ser = nxt
                p = subprocess.Popen([PY, SCRAPER, "--auth", AUTH, "--states", s,
                                      "--series", ser, "--out", wout(s, ser)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                pool[nxt] = (p, count(*nxt))
            time.sleep(5)
            print(progress(list(pool.keys())), flush=True)

    for cycle in range(1, MAX_CYCLES + 1):
        if all_done():
            break
        if not _ensure_session(headless):
            print("!! login failed mid-run — aborting."); return False
        nd = sum(1 for s, ser in tasks if done(s, ser))
        print(f"== semasa cycle {cycle}: {nd}/{len(tasks)} tasks done ==", flush=True)
        if run_pool():
            break
        print("  session expired mid-run — re-login + resume", flush=True)
    nd = sum(1 for s, ser in tasks if done(s, ser))
    print(f"== semasa complete: {total()} numbers, {nd}/{len(tasks)} tasks ==", flush=True)
    return all_done()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default=None, help="comma-separated subset (default: all 32)")
    args = ap.parse_args()
    st = [s.strip() for s in args.states.split(",")] if args.states else None
    run(st)
