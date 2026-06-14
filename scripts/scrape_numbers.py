"""
Scrape the actual available NUMBER combinations for Nombor Pendaftaran Semasa
(current, fixed-price) per state, by searching 50-number windows and reading the
"Senarai Nombor" result grid.

The ZK form cannot be reused after a search (it drops into the result view and
won't restore the search inputs), so each window uses a fresh page + setup. The
available numbers for a running series sit from its current counter up to 9999,
so we scan high->low and stop a few empty windows past the populated block.

Price note: this is "Harga Tetap" (fixed price) — the per-number price is a flat
JPJ rate, not a per-number value (the "Harga Minimum (RM)" column is for the
Istimewa premium series, not these).

Usage:
  python scrape_numbers.py --auth ./auth.json --states "WILAYAH PERSEKUTUAN KUALA LUMPUR" --out numbers.md
  python scrape_numbers.py --auth ./auth.json --all --out numbers.md
"""
from playwright.sync_api import sync_playwright
import argparse, time, re, json, os, sys
import zk_lib as zk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import pace

TARGET = zk.TARGET


def _boxes(pg):
    return pg.evaluate("""()=>[...document.querySelectorAll('input.z-intbox')]
        .filter(x=>x.getBoundingClientRect().height>0&&x.maxLength===4).map(x=>x.id)""")


def _pick_type_julat(pg):
    info = pg.evaluate("""()=>{const res=[];document.querySelectorAll("i[id$='-btn']").forEach(b=>{
        const base=b.id.slice(0,-4);const pp=document.getElementById(base+'-pp');if(!pp)return;
        const items=[...pp.querySelectorAll('.z-comboitem')].map(x=>x.innerText.trim());
        const inp=document.getElementById(base+'-real');const vis=inp&&inp.getBoundingClientRect().height>0;
        if(vis&&items.some(t=>t.startsWith('Julat')))res.push(base);});return res;}""")
    if not info:
        return False
    base = info[0]
    pg.evaluate("(b)=>document.getElementById(b+'-btn').click()", base)
    time.sleep(0.25)
    pg.locator(f"#{base}-pp .z-comboitem", has_text="Julat").first.dispatch_event("click")
    time.sleep(0.5)
    return True


def _read_numbers(pg):
    rows = pg.evaluate("""()=>{const o=[];document.querySelectorAll('.z-grid,.z-listbox').forEach(g=>{
        g.querySelectorAll('td').forEach(td=>{const t=td.innerText.trim();if(/^\\d{1,4}$/.test(t))o.push(t)})});return o}""")
    return sorted(set(int(x) for x in rows if x.isdigit() and int(x) > 0))


def setup(ctx, state, series):
    """Fresh page set to Semasa/state/series with Julat mode, ready to Cari.

    Returns (status, page):
      ("OK", pg)        -> ready to Cari
      ("NOJULAT", None) -> form loaded but this series has no search UI
                           (series not yet released for purchase -> no numbers)
      ("NOFORM", None)  -> page/form didn't render (transient -> retry worthwhile)
    """
    pg = ctx.new_page()
    loaded = False
    for _ in range(6):
        pg.goto(TARGET, wait_until="domcontentloaded")
        if pg.evaluate("()=>[...document.querySelectorAll('td')].some(t=>/Kategori\\s*Siri/.test(t.innerText))"):
            loaded = True
            break
        time.sleep(1.2)
    if not loaded:
        pg.close()
        return ("NOFORM", None)
    time.sleep(0.7)
    try:
        zk.select_combo(pg, "Kategori Siri", "Nombor Pendaftaran Semasa", settle=0.6)
        zk.select_combo(pg, "Negeri", state, settle=0.6)
        zk.click_button(pg, "Papar No", settle=1.1)
        zk.select_combo(pg, "Siri Awalan", series, settle=0.6)
    except Exception:
        pg.close()
        return ("NOFORM", None)
    if not _pick_type_julat(pg):
        pg.close()
        return ("NOJULAT", None)
    return ("OK", pg)


def cari_window(ctx, state, series, a, c):
    """One 50-number window. Returns a list of available numbers, or the string
    status marker ("NOJULAT"/"NOFORM") on a non-search outcome."""
    status, pg = setup(ctx, state, series)
    if status != "OK":
        return status
    try:
        bx = _boxes(pg)
        if len(bx) < 2:
            return "NOFORM"
        pg.locator(f"#{bx[0]}").fill(str(a))
        pg.locator(f"#{bx[1]}").fill(str(c))
        zk.click_button(pg, r"^Cari$", settle=1.5)
        return _read_numbers(pg)
    finally:
        pg.close()


def scan_series(ctx, state, series, log, step=50, max_empty=4, max_windows=200,
                no_found_limit=6, start=None, floor=0):
    """High->low scan; collect available numbers, stop a few empties past the block.
    Stops early if nothing is found in the first `no_found_limit` windows (series
    not yet released), and caps total windows so a fully-open series can't run away.

    `start`/`floor` bound the window range so a single series can be split into
    parallel bands (band mode)."""
    available = set()
    empty_streak = 0
    found = False
    windows = 0
    if start is None:
        start = 9999 - (9999 % step)  # 9950
    a = start
    bo = pace.Backoff()
    while a >= floor and windows < max_windows:
        windows += 1
        if not found and windows > no_found_limit:
            log(f"      {series}: no numbers in top {no_found_limit} windows — skipping")
            break
        nums = cari_window(ctx, state, series, a, min(a + step - 1, 9999))
        if nums == "NOJULAT":
            log(f"      {series}: no search UI — series not released, skipping")
            break
        if nums == "NOFORM":
            bo.stress()        # form/render failure — back off before retrying
            log(f"      {series} {a}: (retry)"); nums = cari_window(ctx, state, series, a, a + step - 1)
            if nums == "NOJULAT":
                log(f"      {series}: no search UI — series not released, skipping")
                break
        else:
            bo.ok()
        nums = nums if isinstance(nums, list) else []
        available.update(nums)
        if nums:
            found = True; empty_streak = 0
            log(f"      {series} {a}-{a+step-1}: +{len(nums)} (total {len(available)})")
        else:
            if found:
                empty_streak += 1
                if empty_streak >= max_empty:
                    log(f"      {series}: stopping (boundary passed at {a})")
                    break
        a -= step
        pace.nap()       # jittered polite delay between windows
    return sorted(available)


def run(auth, states, out, series_filter=None):
    def log(m): print(m, flush=True)
    jpath = out + ".json"
    data = json.load(open(jpath)) if os.path.exists(jpath) else {}
    if data:
        log(f"Resuming — {len([s for s in data if data[s]])} states already done.")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=auth, viewport={"width": 1600, "height": 2400})
        # discover series per state
        for state in states:
            if data.get(state, {}).get("__done__"):
                continue  # resume: skip states already fully scanned
            log(f"\n=== {state} ===")
            # transient form/combo failures shouldn't kill the worker — retry the
            # state a few times before giving up.
            series_list = None
            for attempt in range(4):
                try:
                    series_list = setup_state_series(ctx, state, log)
                    break
                except Exception as e:
                    log(f"  (state setup retry {attempt+1}/4: {type(e).__name__})")
                    time.sleep(3)
            if series_list is None:
                log(f"  !! {state} failed after retries — skipping for now (re-run to fill).")
                continue
            if not series_list:
                log("  !! no series returned — session likely EXPIRED. Stopping; "
                    "re-login and re-run to resume.")
                break
            data.setdefault(state, {})
            if series_filter:
                series_list = [s for s in series_list if s in series_filter]
            for series in series_list:
                if series in data[state]:
                    continue  # resume: skip series already scanned for this state
                log(f"  series {series}")
                nums = scan_series(ctx, state, series, log)
                data[state][series] = nums
                write_out(out, data)
            data[state]["__done__"] = True
            write_out(out, data)
        b.close()
    write_out(out, data)
    log(f"\nDone -> {out}")


def setup_state_series(ctx, state, log):
    """Return the available series list for a state."""
    pg = ctx.new_page()
    for _ in range(6):
        pg.goto(TARGET, wait_until="domcontentloaded")
        if pg.evaluate("()=>[...document.querySelectorAll('td')].some(t=>/Kategori\\s*Siri/.test(t.innerText))"):
            break
        time.sleep(1.2)
    time.sleep(1.3)
    zk.select_combo(pg, "Kategori Siri", "Nombor Pendaftaran Semasa")
    zk.select_combo(pg, "Negeri", state)
    zk.click_button(pg, "Papar No")
    series = [s for s in zk.combo_options(pg, "Siri Awalan") if s.strip()]
    pg.close()
    log(f"  available series: {series}")
    return series


def write_out(out, data):
    json.dump(data, open(out + ".json", "w"))
    with open(out, "w", encoding="utf-8") as f:
        f.write("# JPJ Available Number Combinations (Semasa / fixed price)\n\n")
        total = sum(len(v) for st in data.values() for k, v in st.items() if not k.startswith("__"))
        f.write(f"_Total available numbers: **{total}**. Price: fixed JPJ rate "
                f"(Harga Tetap) per number._\n\n")
        for state in data:
            f.write(f"## {state.replace(chr(160),' ')}\n\n")
            for series, nums in data[state].items():
                if series.startswith("__"):
                    continue
                f.write(f"### {series}  ({len(nums)} available)\n\n")
                f.write(", ".join(f"`{series}{n}`" for n in nums) + "\n\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", default=config.AUTH)
    ap.add_argument("--states", default="WILAYAH PERSEKUTUAN KUALA LUMPUR",
                    help="comma-separated state names")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--series", default=None, help="comma-separated series filter, e.g. VRB")
    ap.add_argument("--out", default=os.path.join(config.WORK, "numbers.md"))
    # band mode: scan ONE state+series over a window range [band_lo, band_hi] so a
    # single deep series can be split across parallel processes.
    ap.add_argument("--band-state", default=None)
    ap.add_argument("--band-series", default=None)
    ap.add_argument("--band-lo", type=int, default=0)
    ap.add_argument("--band-hi", type=int, default=9999)
    ap.add_argument("--list-series", action="store_true",
                    help="print JSON {state: [series,...]} for --states and exit")
    args = ap.parse_args()

    if args.band_series:
        def log(m): print(m, flush=True)
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(storage_state=args.auth, viewport={"width": 1600, "height": 2400})
            log(f"BAND {args.band_state}/{args.band_series} [{args.band_lo}-{args.band_hi}]")
            nums = scan_series(ctx, args.band_state, args.band_series, log,
                               start=args.band_hi - (args.band_hi % 50), floor=args.band_lo)
            data = {args.band_state: {args.band_series: nums}}
            write_out(args.out, data)
            b.close()
        log(f"band done -> {len(nums)} numbers")
        log(f"Done -> {args.out}")
        raise SystemExit(0)
    ALL = ["BEAUFORT","BETONG","BINTULU","JOHOR","KAPIT","KEDAH","KELANTAN","KENINGAU",
           "KOTA KINABALU","KOTA SAMARAHAN","KUCHING","KUDAT","LAHAD DATU","LAWAS","LIMBANG",
           "MELAKA","MIRI","MUKAH","NEGERI SEMBILAN","PAHANG","PERAK","PERLIS","PULAU PINANG",
           "SANDAKAN","SARIKEI","SELANGOR","SIBU","SRI AMAN","TAWAU","TERENGGANU",
           "WILAYAH PERSEKUTUAN KUALA LUMPUR","WILAYAH PERSEKUTUAN PUTRAJAYA"]
    states = ALL if args.all else [s.strip() for s in args.states.split(",")]

    if args.list_series:
        # Enumerate the available series per state (used to build (state,series) tasks).
        def log(m): pass
        out = {}
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            ctx = b.new_context(storage_state=args.auth, viewport={"width": 1600, "height": 2400})
            for st in states:
                try:
                    out[st] = setup_state_series(ctx, st, log)
                except Exception:
                    out[st] = []
            b.close()
        print(json.dumps(out))
        raise SystemExit(0)

    sf = [x.strip() for x in args.series.split(",")] if args.series else None
    run(args.auth, states, args.out, sf)
