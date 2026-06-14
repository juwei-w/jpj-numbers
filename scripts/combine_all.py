"""Combine everything into one dated markdown with a clickable Table of Contents:
Semasa (all states, fixed RM310) + Istimewa (all premium series).

  python combine_all.py                 # -> results/all_available_numbers_<today>.md
  python combine_all.py --date 2026-06-14
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import dataload

PREMIUM = config.PREMIUM


def aid(*parts):
    return "-".join(str(p).replace(" ", "_").replace(" ", "_") for p in parts)


def build(date_str):
    sem = dataload.load_semasa()
    ist = dataload.load_istimewa()
    sem_total = sum(len(v) for st in sem.values() for v in st.values())
    ist_total = sum(len(v) for v in ist.values())
    sem_active = {st: [s for s in sem[st] if sem[st][s]] for st in sem}
    sem_active = {st: v for st, v in sem_active.items() if v}
    ist_active = [s for s in PREMIUM if ist.get(s)]
    n_sem_series = sum(len(v) for v in sem_active.values())

    out = os.path.join(config.RESULTS, f"all_available_numbers_{date_str}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# JPJ Available Registration Numbers — Combined (Semasa + Istimewa)\n\n")
        f.write(f"_Updated {date_str}. Grand total: **{sem_total + ist_total:,}** available "
                f"numbers — **{sem_total:,}** Semasa across {len(sem_active)} states + "
                f"**{ist_total:,}** Istimewa across {len(ist_active)} premium series._\n\n")

        f.write(f"## Table of Contents — Available Series "
                f"({n_sem_series} Semasa + {len(ist_active)} Istimewa)\n\n")
        f.write("### Semasa (current/running — RM 310.00 each)\n\n")
        f.write("| State | Series | Available |\n|---|---|---:|\n")
        for st in sorted(sem_active):
            links = ", ".join(f"[{s}](#{aid('sem', st, s)})" for s in sem_active[st])
            cnt = sum(len(sem[st][s]) for s in sem_active[st])
            f.write(f"| {st.replace(chr(160), ' ')} | {links} | {cnt:,} |\n")
        f.write(f"| **Total** | | **{sem_total:,}** |\n\n")
        f.write("### Istimewa (premium, nationwide)\n\n")
        f.write("| Series | Available |\n|---|---:|\n")
        for s in ist_active:
            f.write(f"| [{s}](#{aid('ist', s)}) | {len(ist[s]):,} |\n")
        f.write(f"| **Total** | **{ist_total:,}** |\n\n---\n\n")

        f.write("# Part 1 — Semasa (Current / Running Numbers)\n\n")
        f.write("**Price: fixed Harga Tetap, RM 310.00 per number** "
                "(RM 300 number + RM 10 tender service fee) — identical for every number "
                "below, verified live at checkout.\n\n")
        for state in sorted(sem):
            f.write(f"## {state.replace(chr(160), ' ')}\n\n")
            for series, nums in sem[state].items():
                f.write(f'<a id="{aid("sem", state, series)}"></a>\n')
                f.write(f"### {series}  ({len(nums)} available — RM 310.00 each)\n\n")
                if nums:
                    f.write(", ".join(f"`{series}{n}`" for n in nums) + "\n\n")

        f.write("---\n\n# Part 2 — Istimewa (Premium / Special Numbers)\n\n")
        f.write("_Nationwide premium series. Price is a per-number **Harga Minimum (RM)** "
                "shown only when an individual number is selected at checkout — not captured "
                "in this run (numbers only)._\n\n")
        for s in PREMIUM:
            nums = ist.get(s, [])
            if not nums:
                continue
            f.write(f'<a id="{aid("ist", s)}"></a>\n')
            f.write(f"## {s}  ({len(nums)} available)\n\n")
            f.write(", ".join(f"`{s} {n}`" for n in nums) + "\n\n")

    print(f"Semasa: {sem_total} / Istimewa: {ist_total} / GRAND: {sem_total + ist_total} -> {out}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args()
    config.ensure_dirs()
    build(args.date)
