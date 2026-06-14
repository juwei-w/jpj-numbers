"""Polite pacing for the JPJ scrapers: jittered inter-request delays + adaptive
backoff that responds to server-stress signals (so we slow down when the portal
pushes back instead of hammering it).

Tunable via env:
  JPJ_DELAY_MIN / JPJ_DELAY_MAX   seconds, the jittered gap between requests
"""
import os
import random
import time

DELAY_MIN = float(os.environ.get("JPJ_DELAY_MIN", "0.3"))
DELAY_MAX = float(os.environ.get("JPJ_DELAY_MAX", "0.8"))


def nap(lo=None, hi=None):
    """Randomized pause between requests — spreads load and avoids a robotic,
    fixed-interval signature."""
    lo = DELAY_MIN if lo is None else lo
    hi = DELAY_MAX if hi is None else hi
    time.sleep(random.uniform(lo, max(lo, hi)))


class Backoff:
    """Exponential backoff that responds to genuine stress. Call ok() after a clean
    request; call stress() when the server pushes back (form/render failure, error,
    session expiry). Each consecutive stress() sleeps ~2x longer (jittered, capped);
    ok() resets it. This makes the scraper a polite citizen under load."""

    def __init__(self, base=1.0, cap=30.0):
        self.base, self.cap, self.n = base, cap, 0

    def ok(self):
        self.n = 0

    def stress(self):
        self.n += 1
        d = min(self.cap, self.base * (2 ** (self.n - 1))) * random.uniform(0.8, 1.2)
        time.sleep(d)
        return d
