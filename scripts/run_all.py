"""
ONE COMMAND — scrape the latest available JPJ numbers (Istimewa + Semasa),
merge them, write a dated snapshot + index.html, and publish to GitHub Pages.

Fully hands-off: the login captcha is solved automatically (offline OCR), and a
fresh run captures a current snapshot (availability changes over time).

  python run_all.py                # fresh full run -> dated snapshot -> publish
  python run_all.py --resume       # continue an interrupted run (don't reset)
  python run_all.py --no-publish   # generate files locally, don't push
  python run_all.py --skip-semasa  # istimewa only (or --skip-istimewa)
"""
import argparse
import datetime
import glob
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import dataload
import combine_all
import make_viewable
import run_istimewa_fast as istimewa
import run_semasa as semasa


def reset_work(skip_istimewa=False, skip_semasa=False):
    """Move last run's sidecars aside so a fresh run reflects only current
    availability (kept under work/prev for one-run recovery). Only resets the
    categories actually being scraped, so a scoped run never drops the other's data."""
    pats = []
    if not skip_istimewa:
        pats.append("ist_*.md*")
    if not skip_semasa:
        pats.append("numbers_*.md*")
    if not pats:
        return
    prev = os.path.join(config.WORK, "prev")
    os.makedirs(prev, exist_ok=True)
    moved = 0
    for pat in pats:
        for f in glob.glob(os.path.join(config.WORK, pat)):
            dest = os.path.join(prev, os.path.basename(f))
            if os.path.exists(dest):
                os.remove(dest)
            shutil.move(f, dest)
            moved += 1
    print(f"reset: moved {moved} prior sidecars -> work/prev", flush=True)


def publish(date_str, grand):
    """Commit + push index.html and the dated snapshot to GitHub Pages."""
    root = config.ROOT
    if subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                      capture_output=True).returncode != 0:
        print("publish: not a git repo yet — skipping (run git init + add remote first).")
        return
    if not subprocess.run(["git", "-C", root, "remote"], capture_output=True, text=True).stdout.strip():
        print("publish: no git remote 'origin' — skipping.")
        return
    subprocess.run(["git", "-C", root, "add", "-A"], check=False)
    msg = f"update numbers {date_str} ({grand:,} available)"
    c = subprocess.run(["git", "-C", root, "commit", "-m", msg], capture_output=True, text=True)
    if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
        print("publish: nothing changed.")
        return
    pu = subprocess.run(["git", "-C", root, "push", "origin", "HEAD"], capture_output=True, text=True)
    if pu.returncode == 0:
        print("publish: pushed — live shortly at https://juwei-w.github.io/jpj-numbers/")
    else:
        print("publish: push failed:\n", pu.stderr.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true", help="continue an interrupted run")
    ap.add_argument("--no-publish", action="store_true")
    ap.add_argument("--skip-istimewa", action="store_true")
    ap.add_argument("--skip-semasa", action="store_true")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args()

    config.ensure_dirs()
    print(f"==== JPJ full run {args.date} ({'resume' if args.resume else 'fresh'}) ====", flush=True)
    if not args.resume:
        reset_work(args.skip_istimewa, args.skip_semasa)

    if not args.skip_istimewa:
        print("\n----- ISTIMEWA -----", flush=True)
        istimewa.run()
    if not args.skip_semasa:
        print("\n----- SEMASA -----", flush=True)
        semasa.run()

    print("\n----- MERGE + RENDER -----", flush=True)
    combine_all.build(args.date)
    make_viewable.build(args.date)
    grand = (sum(len(v) for st in dataload.load_semasa().values() for v in st.values())
             + sum(len(v) for v in dataload.load_istimewa().values()))
    print(f"GRAND TOTAL: {grand:,} available numbers", flush=True)

    if not args.no_publish:
        print("\n----- PUBLISH -----", flush=True)
        publish(args.date, grand)
    print("\n==== done ====", flush=True)


if __name__ == "__main__":
    main()
