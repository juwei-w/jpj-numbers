"""
Semasa engine — concurrent worker POOL, one state per worker. Resumable, auto
re-login on session expiry. Scope to a subset of states with --states (the matrix
workflow uses this to run one shard per VM, so each state gets dedicated cores
instead of fighting 15 other browsers for the same 2 CPUs).

  python run_semasa.py                          # all 32 states
  python run_semasa.py --states "SELANGOR"      # one state (a matrix shard)
  SEMASA_WORKERS=2 python run_semasa.py --states "KEDAH,PERLIS,KELANTAN"
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
MAX_CYCLES = 30


def sanitize(state):
    return re.sub(r"[^A-Za-z0-9]+", "_", state).strip("_")


def wout(state):
    # Per-state sidecar name -> unique across shards, so matrix artifacts never collide.
    return os.path.join(config.WORK, f"numbers_{sanitize(state)}.md")


def rec(state):
    j = wout(state) + ".json"
    if os.path.exists(j):
        try:
            return json.load(open(j))
        except Exception:
            pass
    return {}


def sdone(state):
    return bool(rec(state).get(state, {}).get("__done__"))


def count(state):
    st = rec(state).get(state, {})
    return sum(len(v) for k, v in st.items() if not k.startswith("__"))


def _validate():
    """Cheap shared session check (same cookie works for both forms)."""
    r = subprocess.run([PY, ISTIMEWA, "--auth", AUTH, "--test"], capture_output=True, text=True)
    return "PASS=True" in (r.stdout or "")


def run(states=None, headless=True):
    states = list(states) if states else list(config.STATES)
    K = int(os.environ.get("SEMASA_WORKERS", str(min(16, len(states)))))
    config.ensure_dirs()

    def all_done():
        return all(sdone(s) for s in states)

    def total():
        return sum(count(s) for s in states)

    def progress():
        nd = sum(1 for s in states if sdone(s))
        return f"SEMASA [{nd}/{len(states)} states | {total()} nums | {K} workers]"

    def run_pool():
        pool = {}
        stalls = 0
        while True:
            for s, (p, c0) in list(pool.items()):
                if p.poll() is not None:
                    del pool[s]
                    if sdone(s) or count(s) > c0:
                        stalls = 0          # progress or completion
                    else:
                        stalls += 1         # exited with nothing new -> session likely dead
            if all_done():
                return True
            if stalls >= K and not pool:    # a full wave failed with empty pool
                return False
            while len(pool) < K:
                nxt = next((s for s in states if not sdone(s) and s not in pool), None)
                if nxt is None:
                    break
                p = subprocess.Popen([PY, SCRAPER, "--auth", AUTH, "--states", nxt, "--out", wout(nxt)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                pool[nxt] = (p, count(nxt))
            time.sleep(5)
            print(progress(), flush=True)

    for cycle in range(1, MAX_CYCLES + 1):
        if all_done():
            break
        if not (os.path.exists(AUTH) and _validate()):
            print(f"== semasa cycle {cycle}: logging in ==", flush=True)
            if not login.run(save_path=AUTH, headless=headless):
                print("!! login failed — aborting semasa."); return False
        else:
            print(f"== semasa cycle {cycle}: session valid ==", flush=True)
        if run_pool():
            break
        print("  session expired mid-run — re-login + resume", flush=True)
    print(f"== semasa complete: {total()} numbers ==", flush=True)
    return all_done()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default=None, help="comma-separated subset (default: all 32)")
    args = ap.parse_args()
    states = [s.strip() for s in args.states.split(",")] if args.states else None
    run(states)
