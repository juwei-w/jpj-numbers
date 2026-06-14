"""
Semasa engine — concurrent worker POOL, one state per worker.

Each state is one task with its own resume file (work/numbers_w<n>.md.json, where
n is the state's fixed index); up to K run in parallel. Resumable within a run;
reuses a live session (auto-login) so a captcha is only needed on expiry.

  python run_semasa.py                 # default K workers, runs to completion
  SEMASA_WORKERS=12 python run_semasa.py
"""
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
SCRAPER = os.path.join(HERE, "scrape_numbers.py")
AUTH = config.AUTH
STATES = config.STATES
K = int(os.environ.get("SEMASA_WORKERS", "16"))
MAX_CYCLES = 30


def wout(i):
    return os.path.join(config.WORK, f"numbers_w{i + 1}.md")


def rec(i):
    j = wout(i) + ".json"
    if os.path.exists(j):
        try:
            return json.load(open(j))
        except Exception:
            pass
    return {}


def sdone(i):
    return bool(rec(i).get(STATES[i], {}).get("__done__"))


def count(i):
    st = rec(i).get(STATES[i], {})
    return sum(len(v) for k, v in st.items() if not k.startswith("__"))


def all_done():
    return all(sdone(i) for i in range(len(STATES)))


def total_found():
    return sum(count(i) for i in range(len(STATES)))


def progress_line():
    nd = sum(1 for i in range(len(STATES)) if sdone(i))
    return f"SEMASA [{nd}/{len(STATES)} states | {total_found()} nums | {K} workers]"


def validate():
    """Reuse the istimewa scraper self-test as a shared session check (same cookie)."""
    r = subprocess.run([PY, os.path.join(HERE, "scrape_istimewa.py"), "--auth", AUTH, "--test"],
                       capture_output=True, text=True)
    return "PASS=True" in (r.stdout or "")


def run_pool():
    pool = {}
    stalls = 0
    while True:
        for i, (p, cnt0) in list(pool.items()):
            if p.poll() is not None:
                del pool[i]
                if sdone(i) or count(i) > cnt0:
                    stalls = 0
                else:
                    stalls += 1
        if all_done():
            return True
        if stalls >= K:
            return False
        while len(pool) < K:
            nxt = next((i for i in range(len(STATES)) if not sdone(i) and i not in pool), None)
            if nxt is None:
                break
            p = subprocess.Popen([PY, SCRAPER, "--auth", AUTH, "--states", STATES[nxt], "--out", wout(nxt)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pool[nxt] = (p, count(nxt))
        time.sleep(5)
        print(progress_line(), flush=True)


def run(headless=True):
    config.ensure_dirs()
    for cycle in range(1, MAX_CYCLES + 1):
        if all_done():
            break
        if not (os.path.exists(AUTH) and validate()):
            print(f"== semasa cycle {cycle}: logging in ==", flush=True)
            if not login.run(save_path=AUTH, headless=headless):
                print("!! login failed — aborting semasa."); return False
        else:
            print(f"== semasa cycle {cycle}: session valid ==", flush=True)
        if run_pool():
            break
        print("  session expired mid-run — re-login + resume", flush=True)
    print(f"== semasa complete: {total_found()} numbers ==", flush=True)
    return all_done()


if __name__ == "__main__":
    run()
