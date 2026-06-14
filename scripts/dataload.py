"""Load scraped numbers from the work/ sidecars (single source of truth for the
merge + render steps, so they never drift)."""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def load_semasa(work=None):
    """state -> {series -> sorted[int]} unioned across all numbers_w*.md.json."""
    work = work or config.WORK
    sem = {}
    for jf in sorted(glob.glob(os.path.join(work, "numbers_w*.md.json"))):
        try:
            data = json.load(open(jf))
        except Exception:
            continue
        for state, series in data.items():
            for k, v in series.items():
                if k.startswith("__"):
                    continue
                sem.setdefault(state, {}).setdefault(k, set()).update(v)
    return {st: {s: sorted(ns) for s, ns in sd.items() if ns}
            for st, sd in sem.items() if any(sd.values())}


def load_istimewa(work=None):
    """series -> sorted[int] from ist_<S>.md.json (only series with numbers)."""
    work = work or config.WORK
    ist = {}
    for s in config.PREMIUM:
        p = os.path.join(work, f"ist_{s}.md.json")
        if os.path.exists(p):
            try:
                ns = sorted(json.load(open(p)).get(s, {}).get("numbers", []))
            except Exception:
                ns = []
            if ns:
                ist[s] = ns
    return ist
