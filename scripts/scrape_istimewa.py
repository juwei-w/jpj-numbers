"""
Full-auto Istimewa (premium) number scraper via RAW ZK-AU POST.  PROVEN WORKING.

The Kategori->Istimewa switch cannot be triggered through DOM events (ZK 5.0.7
won't emit the server event from synthetic clicks; wgt.fire(...,{toServer}) sends
nothing; widgets report zero geometry so real clicks are impossible). So we drive
the zkau protocol directly.

KEY DETAILS (all hard-won, verified live against GM 3050-3100):
  * POST /public/zkau, header `ZK-SID: <last observed + 1>`.
  * A combobox selection needs BOTH onChange AND onSelect in ONE request; the
    `value` must equal the comboitem label EXACTLY (full Julat label).
  * Intbox value MUST be a JSON NUMBER: {"value":3050,"start":4} — NOT "3050".
    A string makes the server throw String-incompatible-with-Integer (Error 500).
  * The two range intboxes (from setAttr visible) are ordered [END, START]:
    fill boxes[1]=lo, boxes[0]=hi, else "permulaan mestilah kecil dari akhir".
  * Batch both intbox onChanges + the Cari onClick in ONE request.
  * Results arrive in a zul.sel.Listbox as Label{value:'NNNN'} -> parse those.
  * No price in the search result (Harga Minimum needs per-number selection).
  * Desktop reuse: after one switch, loop series (onChange+onSelect on siri combo,
    re-select Julat each series) and loop 50-windows by re-sending fill+Cari — no
    page reload until the session expires.

Premium series: A, FC, FD, FE, FH, GM, GOLD, M, MADANI, MYSI, PETRA, VIPS, VIP
(nationwide; no Negeri). Each Julat search spans <=50 numbers, so a full series
sweep is 200 windows (0..10000 step 50).

Usage:
  python scrape_istimewa.py --auth ./auth.json --out istimewa_numbers.md
  python scrape_istimewa.py --auth ./auth.json --test          # GM 3050-3100 self-check
  python scrape_istimewa.py --auth ./auth.json --series GM      # one series only
"""
from playwright.sync_api import sync_playwright
import argparse, time, re, json, os, urllib.parse

TARGET = "https://public.jpj.gov.my/public/#/vel/04velnummgt/vel04ReserveNumberAdd"
JULAT = "Julat (Pilihan Dalam Lingkungan 50 Nombor)"
PREMIUM = ["A", "FC", "FD", "FE", "FH", "GM", "GOLD", "M", "MADANI", "MYSI", "PETRA", "VIPS", "VIP"]
RATE = 0.1   # seconds between searches (inline recovery is the natural pacer)


class SessionExpired(Exception):
    pass


class Au:
    """Raw ZK-AU POST driver: tracks ZK-SID, sends commands, returns response text."""
    def __init__(self, page):
        self.page = page
        self.maxsid = 0
        page.on("request", self._track)

    def _track(self, r):
        if "/zkau" in r.url and r.method == "POST":
            s = r.headers.get("zk-sid")
            if s:
                try:
                    self.maxsid = max(self.maxsid, int(s))
                except ValueError:
                    pass

    def send(self, dtid, cmds):
        self.maxsid += 1
        sid = self.maxsid
        parts = [f"dtid={dtid}"]
        for i, (cmd, uuid, data) in enumerate(cmds):
            parts.append(f"cmd_{i}={cmd}")
            if uuid:
                parts.append(f"uuid_{i}={uuid}")
            parts.append(f"data_{i}=" + urllib.parse.quote(json.dumps(data)))
        body = "&".join(parts)
        return self.page.evaluate(
            """async (a) => { const [body, sid] = a;
                const r = await fetch('/public/zkau', {method:'POST',
                    headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8','ZK-SID':String(sid)},
                    body});
                return await r.text(); }""", [body, sid])


def parse_blocks(resp):
    """addChd target uuid -> [(itemUuid, label)], segmented by command markers."""
    mk = [(m.start(), m.group(1), m.group(2))
          for m in re.finditer(r'\["(addChd|setAttr|rm|addAft|removeChd)",\["?([^"\],]*)', resp)]
    out = {}
    for i, (pos, cmd, uuid) in enumerate(mk):
        if cmd != "addChd":
            continue
        end = mk[i + 1][0] if i + 1 < len(mk) else len(resp)
        out[uuid] = re.findall(r"Comboitem','([^']+)',\{label:'([^']*)'\}", resp[pos:end])
    return out


def find_item(items, label):
    return next((u for u, l in items if l == label), None)


def parse_numbers(resp):
    """Available numbers come back as Label{value:'NNNN'} inside the result Listbox."""
    return sorted(set(int(x) for x in re.findall(r"Label','[^']+',\{value:'(\d{1,4})'\}", resp)))


def load_form(page):
    # Force a REAL reload each time (a fresh ZK desktop). Navigating straight to the
    # same hash URL is a no-op for the SPA, so bounce through about:blank first.
    for _ in range(8):
        try:
            page.goto("about:blank")
            page.goto(TARGET, wait_until="domcontentloaded", timeout=30000)
            for _ in range(12):
                if page.evaluate("()=>[...document.querySelectorAll('td')].some(t=>/Kategori\\s*Siri/.test(t.innerText))"):
                    time.sleep(1.2)
                    return True
                if page.locator("input[type=password]").first.count() and \
                   page.locator("input[type=password]").first.is_visible():
                    return False     # bounced to login = session dead
                time.sleep(0.8)
        except Exception:
            pass
        time.sleep(1.2)
    return False


def base_info(page):
    """Locate the Kategori combo (+ its Istimewa item) and the Cari button."""
    return page.evaluate("""()=>{
        const dt=zk.Desktop.$().id; let res={dtid:dt,cari:[]};
        document.querySelectorAll("i[id$='-btn']").forEach(btn=>{
            const base=btn.id.slice(0,-4); const w=zk.Widget.$('#'+base);
            if(w&&w.className==='zul.inp.Combobox'){let it=w.firstChild;
                while(it){ if((it.getLabel&&it.getLabel())==='Nombor Pendaftaran Istimewa'){res.kuuid=base;res.istUuid=it.uuid;} it=it.nextSibling; }}
        });
        document.querySelectorAll('button').forEach(bt=>{const w=zk.Widget.$(bt);
            if(w&&/^Cari$/.test(bt.innerText.trim()))res.cari.push(w.uuid);});
        return res;}""")


def pick_type_combo_for_siri(page, siri_uuid, type_uuids):
    """The type (Nombor/Julat) combo in the same panel as the premium siri combo."""
    return page.evaluate("""(a)=>{
        const [siri, types] = a;
        const sEl = document.getElementById(siri); if(!sEl) return types[types.length-1];
        function ancestors(el){const o=[];while(el){o.push(el);el=el.parentElement;}return o;}
        const sAnc = ancestors(sEl);
        let best=types[types.length-1], bestScore=-1;
        for(const t of types){const tEl=document.getElementById(t); if(!tEl) continue;
            const tAnc=ancestors(tEl); let score=1e9;
            for(let i=0;i<sAnc.length;i++){const j=tAnc.indexOf(sAnc[i]); if(j>=0){score=i+j; break;}}
            if(score<bestScore||bestScore<0){bestScore=score;best=t;}
        }
        return best;
    }""", [siri_uuid, type_uuids])


def switch_istimewa(au, info):
    """Switch Kategori->Istimewa. Returns (siri_combo, {series:itemUuid}, [(typeUuid,items)])."""
    r1 = au.send(info["dtid"], [
        ("onChange", info["kuuid"], {"value": "Nombor Pendaftaran Istimewa", "start": 0}),
        ("onSelect", info["kuuid"], {"items": [info["istUuid"]], "reference": info["istUuid"]}),
    ])
    bl = parse_blocks(r1)
    siri = next((u for u, its in bl.items() if [l for _, l in its][:2] == ["A", "FC"]), None)
    series_items = {l: u for u, l in (bl.get(siri) or [])}
    types = [(u, its) for u, its in bl.items() if [l for _, l in its] == ["Nombor", JULAT]]
    return siri, series_items, types


def refresh_items(ctx, resp):
    """Combo *item* uuids (series items + the Julat item) are re-minted on each
    search response; refresh them so the next onSelect references live uuids. The
    combo/intbox *widget* uuids are stable for the desktop and never change, so we
    only ever update items here (and keep the last good value if absent)."""
    bl = parse_blocks(resp)
    for u, its in bl.items():
        labels = [l for _, l in its]
        if labels[:2] == ["A", "FC"]:
            ctx["series_items"] = {l: iu for iu, l in its}
        if labels == ["Nombor", JULAT]:
            ji = find_item(its, JULAT)
            if ji:
                ctx["julat_item"] = ji


def select_series_julat(ctx, page, series):
    """Select a premium series on the LIVE desktop (no reload). The Julat range mode
    + its intboxes are revealed once on the first series and STAY visible across
    series changes (the type combo keeps Julat, so re-selecting it is a no-op), so
    we cache the box uuids (stable for the desktop) and reuse them every series."""
    au, info = ctx["au"], ctx["info"]
    item = ctx["series_items"].get(series)
    if not item:
        return None
    au.send(info["dtid"], [("onChange", ctx["siri"], {"value": series, "start": 0}),
                           ("onSelect", ctx["siri"], {"items": [item], "reference": item})])
    # ensure Julat mode; on the first series this reveals the intboxes, on later
    # series it returns an empty {"rs":[]} (already Julat) — that's expected.
    jl = ctx["julat_item"]
    r3 = au.send(info["dtid"], [("onChange", ctx["tc"], {"value": JULAT, "start": 0}),
                                ("onSelect", ctx["tc"], {"items": [jl], "reference": jl})])
    refresh_items(ctx, r3)
    vis = re.findall(r'\["setAttr",\["([^"]+)","visible",true', r3)
    if len(vis) >= 2 and not ctx.get("boxes"):
        boxes = page.evaluate(
            """(u)=>u.filter(id=>{const w=zk.Widget.$('#'+id);return w&&w.className==='zul.inp.Intbox'})""", vis)
        ctx["boxes"] = boxes if len(boxes) >= 2 else vis[:2]
    return ctx.get("boxes")


def _dismiss(au, info, resp):
    """Close a ZK messagebox (its OK/Tutup button) so it stops blocking the form.
    An empty search pops a 'no records' wndMessageBox that otherwise freezes every
    later search on this desktop."""
    m = (re.search(r"'zul\.wgt\.Button','([^']+)',\{id:'btnOK'", resp)
         or re.search(r"'zul\.wgt\.Button','([^']+)',\{[^}]*label:'(?:Tutup|OK|Ya)'", resp))
    if m:
        au.send(info["dtid"], [("onClick", m.group(1),
                                {"pageX": 190, "pageY": 110, "which": 1, "x": 10, "y": 10})])
        return True
    return False


def do_window(ctx, boxes, lo, hi):
    """One 50-window search. Returns (numbers, broke, rb). broke=True means the
    search was empty: the 'no records' popup REBUILDS the form (back to a Semasa
    view) with new uuids, so the caller must recover before the next search. A
    search that returns numbers leaves the form intact. Raises SessionExpired if dead."""
    au, info = ctx["au"], ctx["info"]
    rb = au.send(info["dtid"], [
        ("onChange", boxes[1], {"value": lo, "start": len(str(lo))}),
        ("onChange", boxes[0], {"value": hi, "start": len(str(hi))}),
        ("onClick", info["cari"][0], {"pageX": 793, "pageY": 530, "which": 1, "x": 24, "y": 13}),
    ])
    if '"rs":' not in rb or "login" in rb[:200].lower():
        raise SessionExpired()
    if "wndMessageBox" in rb or "wrongValue" in rb:    # empty/validation -> form rebuilt
        _dismiss(au, info, rb)
        return [], True, rb
    return parse_numbers(rb), False, rb


def recover_istimewa(ctx, page, rb, series):
    """After an empty search rebuilt the form to a Semasa view, switch back to
    Istimewa INLINE (raw POST, NO page reload — ~4x faster) and re-select the
    series + Julat. Returns fresh [end,start] boxes, or None if recovery failed
    (caller then falls back to a full page reload)."""
    au, info = ctx["au"], ctx["info"]
    mi = re.search(r"Comboitem','([^']+)',\{label:'Nombor Pendaftaran Istimewa'\}", rb)
    if not mi:
        return None
    ist = mi.group(1)
    kb = list(re.finditer(r"Combobox','([^']+)'", rb[:mi.start()]))   # nearest preceding = Kategori
    if not kb:
        return None
    ncari = re.findall(r"'([A-Za-z0-9_]+)',\{[^}]*label:'Cari'", rb)
    if ncari:
        info["cari"] = [ncari[0]]
    r = au.send(info["dtid"], [("onChange", kb[-1].group(1), {"value": "Nombor Pendaftaran Istimewa", "start": 0}),
                               ("onSelect", kb[-1].group(1), {"items": [ist], "reference": ist})])
    bl = parse_blocks(r)
    siri = next((u for u, its in bl.items() if [l for _, l in its][:2] == ["A", "FC"]), None)
    if not siri:
        return None
    types = [(u, its) for u, its in bl.items() if [l for _, l in its] == ["Nombor", JULAT]]
    if not types:
        return None
    ctx["siri"] = siri
    ctx["series_items"] = {l: u for u, l in bl[siri]}
    ctx["tc"] = types[-1][0]
    ctx["julat_item"] = find_item(types[-1][1], JULAT)
    ctx["boxes"] = None
    return select_series_julat(ctx, page, series)


# ----- orchestration ---------------------------------------------------------

def establish(page):
    """Load the form + switch to Istimewa ONCE per login. Returns a mutable ctx
    dict with cached (stable) combo widget uuids; item uuids are refreshed from
    each search response. NO per-series reload — reloading bounced the SPA and was
    misread as session expiry (the real cause of one-series-per-login)."""
    if not load_form(page):
        raise SessionExpired()
    au = Au(page)
    info = base_info(page)
    if not info.get("kuuid"):
        raise SessionExpired()
    siri, series_items, types = switch_istimewa(au, info)
    if not series_items:
        raise SessionExpired()
    tc = pick_type_combo_for_siri(page, siri, [u for u, _ in types])
    tcits = next((its for u, its in types if u == tc), [])
    return {"au": au, "info": info, "siri": siri, "tc": tc,
            "series_items": dict(series_items), "julat_item": find_item(tcits, JULAT)}


def scan_series(page, state, series, log):
    """Scan all 50-windows for one series. Reuses the desktop while searches return
    numbers; re-establishes a fresh desktop after an empty search (which rebuilds the
    form). Resumable via state[series]={'numbers':[...], 'next_lo':int, 'done':bool}.
    Raises SessionExpired (caller re-logins) when the session dies."""
    rec = state.setdefault(series, {"numbers": [], "next_lo": 0, "done": False})
    if rec["done"]:
        return
    ctx = establish(page)
    if series not in ctx["series_items"]:
        log(f"  {series}: not in available list"); rec["done"] = True; save(state); return
    boxes = select_series_julat(ctx, page, series)
    if not boxes:
        log(f"  {series}: could not reveal range boxes"); raise SessionExpired()
    found = set(rec["numbers"])
    lo = rec["next_lo"]
    while lo < 10000:
        nums, broke, rb = do_window(ctx, boxes, lo, lo + 50)
        if nums:
            new = set(nums) - found
            if new:
                found |= new
                rec["numbers"] = sorted(found)
                log(f"  {series} {lo}-{lo+50}: +{len(new)} (total {len(found)})")
        rec["next_lo"] = lo + 50
        save(state)
        lo += 50
        if broke and lo < 10000:        # empty search rebuilt the form
            boxes = recover_istimewa(ctx, page, rb, series)   # fast inline re-switch
            if not boxes:                                     # fall back to full reload
                ctx = establish(page)
                boxes = select_series_julat(ctx, page, series)
                if not boxes:
                    raise SessionExpired()
        time.sleep(RATE)
    rec["done"] = True
    save(state)
    log(f"=== {series}: DONE — {len(found)} available numbers ===")


def save(state):
    out = state["_out"]
    data = {k: v for k, v in state.items() if not k.startswith("_")}
    json.dump(data, open(out + ".json", "w"))
    with open(out, "w", encoding="utf-8") as f:
        f.write("# JPJ Istimewa (Premium) Available Numbers\n\n")
        total = sum(len(v["numbers"]) for v in data.values())
        done = sum(1 for v in data.values() if v.get("done"))
        f.write(f"_Total available premium numbers: **{total}** across {len(data)} series "
                f"({done} fully scanned). Nationwide. Price (Harga Minimum) is per-number "
                f"and shown on selection — not included here._\n\n")
        for s in [x for x in PREMIUM if x in data] + [x for x in data if x not in PREMIUM]:
            v = data[s]
            status = "complete" if v.get("done") else f"partial, scanned through {v.get('next_lo',0)}"
            f.write(f"## {s}  ({len(v['numbers'])} available — {status})\n\n")
            if v["numbers"]:
                f.write(", ".join(f"`{s} {n}`" for n in v["numbers"]) + "\n\n")


def all_complete(out, series_list=None):
    """True if every target series is fully scanned (for the auto-loop wrapper)."""
    if not os.path.exists(out + ".json"):
        return False
    data = json.load(open(out + ".json"))
    for s in (series_list or PREMIUM):
        if not data.get(s, {}).get("done"):
            return False
    return True


def run(auth, out, only_series=None, do_test=False):
    def log(m): print(m, flush=True)
    data = json.load(open(out + ".json")) if os.path.exists(out + ".json") else {}
    series_list = [s.strip() for s in only_series.split(",")] if only_series else PREMIUM
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        bctx = b.new_context(storage_state=auth, viewport={"width": 1600, "height": 2400})
        page = bctx.new_page()

        if do_test:
            # Validate reload-on-break: search a result window, then an empty window
            # (which rebuilds the form), re-establish, and confirm the result window
            # still returns the known GM numbers.
            expect = [3052, 3054, 3056, 3058, 3064, 3067, 3071, 3074, 3079, 3084, 3091, 3095]
            ctx = establish(page)
            boxes = select_series_julat(ctx, page, "GM")
            a, ba, _ = do_window(ctx, boxes, 3050, 3100)
            e, be, rb = do_window(ctx, boxes, 3100, 3150)
            log(f"  GM 3050-3100: {a}  (broke={ba})")
            log(f"  GM 3100-3150: {e}  (empty, broke={be})")
            boxes = recover_istimewa(ctx, page, rb, "GM")        # fast inline recovery
            d, bd, _ = do_window(ctx, boxes, 3050, 3100)
            log(f"  GM 3050-3100 after inline recover: {d}  (broke={bd})")
            ok = a == expect and e == [] and d == expect
            log(f"  INLINE-RECOVERY PASS={ok}")
            b.close(); return ok

        try:
            ctx = establish(page)
            log(f"Switched to Istimewa. Series available: {list(ctx['series_items'])}")
        except SessionExpired:
            log("!! Session expired — re-run login_and_save_cookies.py, then re-run this.")
            b.close(); return False

        state = dict(data)
        state["_out"] = out
        for series in series_list:
            if state.get(series, {}).get("done"):
                log(f"  {series}: already complete — skipping"); continue
            try:
                scan_series(page, state, series, log)
            except SessionExpired:
                log(f"!! Session expired during {series} (scanned through "
                    f"{state.get(series,{}).get('next_lo',0)}). Progress saved. "
                    f"Re-login and re-run to resume.")
                save(state); b.close(); return False
        save(state)
        b.close()
    log(f"\nDone -> {out}")
    return True


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth", default=config.AUTH)
    ap.add_argument("--out", default=os.path.join(config.WORK, "istimewa_numbers.md"))
    ap.add_argument("--series", default=None, help="comma-separated premium series, e.g. GM,GOLD")
    ap.add_argument("--test", action="store_true", help="reload-on-break self-check")
    args = ap.parse_args()
    run(args.auth, args.out, args.series, args.test)
