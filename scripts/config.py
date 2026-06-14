"""Shared paths + credential loading.

Credentials are NEVER hardcoded or committed. They are read, in order, from:
  1. environment variables  JPJ_USER / JPJ_PASS
  2. config.local.json at the project root  (gitignored)

Copy config.example.json -> config.local.json and fill it in, or export the
env vars, before running anything that logs in.
"""
import json
import os

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPTS)
WORK = os.path.join(ROOT, "work")          # intermediate sidecars + logs (gitignored)
RESULTS = os.path.join(ROOT, "results")    # final deliverables (committed)
AUTH = os.path.join(WORK, "auth.json")     # saved session (gitignored)
CONFIG_LOCAL = os.path.join(ROOT, "config.local.json")

PREMIUM = ["A", "FC", "FD", "FE", "FH", "GM", "GOLD", "M", "MADANI", "MYSI",
           "PETRA", "VIPS", "VIP"]

STATES = ["BEAUFORT", "BETONG", "BINTULU", "JOHOR", "KAPIT", "KEDAH", "KELANTAN",
          "KENINGAU", "KOTA KINABALU", "KOTA SAMARAHAN", "KUCHING", "KUDAT",
          "LAHAD DATU", "LAWAS", "LIMBANG", "MELAKA", "MIRI", "MUKAH",
          "NEGERI SEMBILAN", "PAHANG", "PERAK", "PERLIS", "PULAU PINANG",
          "SANDAKAN", "SARIKEI", "SELANGOR", "SIBU", "SRI AMAN", "TAWAU",
          "TERENGGANU", "WILAYAH PERSEKUTUAN KUALA LUMPUR",
          "WILAYAH PERSEKUTUAN PUTRAJAYA"]


def load_credentials():
    """Return (username, password). Raises a clear error if neither source is set."""
    u = os.environ.get("JPJ_USER")
    p = os.environ.get("JPJ_PASS")
    if u and p:
        return u, p
    if os.path.exists(CONFIG_LOCAL):
        try:
            c = json.load(open(CONFIG_LOCAL))
            u = u or c.get("username")
            p = p or c.get("password")
        except Exception as e:
            raise RuntimeError(f"Could not read {CONFIG_LOCAL}: {e}")
    if not u or not p:
        raise RuntimeError(
            "JPJ credentials not found. Set env JPJ_USER / JPJ_PASS, or copy "
            "config.example.json -> config.local.json and fill it in.")
    return u, p


def ensure_dirs():
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
