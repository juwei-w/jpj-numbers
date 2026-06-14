"""
Istimewa engine — concurrent worker POOL over the premium series.

Each premium series is one task with its own resume file (work/ist_<SERIES>.md.json);
up to K run in parallel. Changing K never loses progress. Reuses a live session
(auto-login, captcha solved automatically) so a captcha is only ever needed when a
session actually expires.

  python run_istimewa_fast.py                  # default K workers, runs to completion
  ISTIMEWA_WORKERS=10 python run_istimewa_fast.py
"""
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import login_and_save_cookies as login

HERE = config.SCRIPTS
PY = sys.executable
SCRAPER = os.path.join(HERE, "scrape_istimewa.py")
AUTH = config.AUTH
PREMIUM = config.PREMIUM
K = int(os.environ.get("ISTIMEWA_WORKERS", str(len(PREMIUM))))   # one worker per series
MAX_CYCLES = 30


def sout(s):
    return os.path.join(config.WORK, f"ist_{s}.md")


def rec(s):
    j = sout(s) + ".json"
    if os.path.exists(j):
        try:
            return json.load(open(j)).get(s, {})
        except Exception:
            pass
    return {}


def done(s):
    return bool(rec(s).get("done"))


def lo_of(s):
    return rec(s).get("next_lo", 0)


def all_done():
    return all(done(s) for s in PREMIUM)


def total_found():
    return sum(len(rec(s).get("numbers", [])) for s in PREMIUM)


def progress_line():
    parts = []
    for s in PREMIUM:
        v = rec(s)
        if not v:
            parts.append(f"{s}:·")
        elif v.get("done"):
            parts.append(f"{s}:✓{len(v.get('numbers', []))}")
        else:
            parts.append(f"{s}:{int(v.get('next_lo', 0) / 100)}%·{len(v.get('numbers', []))}")
    nd = sum(1 for s in PREMIUM if done(s))
    return f"ISTIMEWA [{nd}/{len(PREMIUM)} done | {total_found()} nums | {K} workers] " + " ".join(parts)


def validate():
    """Cheap session check via the scraper self-test. True if the session is alive."""
    r = subprocess.run([PY, SCRAPER, "--auth", AUTH, "--test"], capture_output=True, text=True)
    return "PASS=True" in (r.stdout or "")


def run_pool():
    """Run the worker pool over not-done series until all done OR the session dies.
    Returns True if all done."""
    pool = {}
    stalls = 0
    while True:
        for s, (p, slo) in list(pool.items()):
            if p.poll() is not None:
                del pool[s]
                if done(s) or lo_of(s) > slo:
                    stalls = 0
                else:
                    stalls += 1
        if all_done():
            return True
        if stalls >= K:
            return False
        while len(pool) < K:
            nxt = next((s for s in PREMIUM if not done(s) and s not in pool), None)
            if nxt is None:
                break
            p = subprocess.Popen([PY, SCRAPER, "--auth", AUTH, "--out", sout(nxt), "--series", nxt],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pool[nxt] = (p, lo_of(nxt))
        time.sleep(5)
        print(progress_line(), flush=True)


def run(headless=True):
    """Ensure a session, then scan all premium series to completion. Returns True."""
    config.ensure_dirs()
    for cycle in range(1, MAX_CYCLES + 1):
        if all_done():
            break
        if not (os.path.exists(AUTH) and validate()):
            print(f"== istimewa cycle {cycle}: logging in ==", flush=True)
            if not login.run(save_path=AUTH, headless=headless):
                print("!! login failed — aborting istimewa."); return False
        else:
            print(f"== istimewa cycle {cycle}: session valid ==", flush=True)
        if run_pool():
            break
        print("  session expired mid-run — re-login + resume", flush=True)
    print(f"== istimewa complete: {total_found()} numbers ==", flush=True)
    return all_done()


if __name__ == "__main__":
    run()
