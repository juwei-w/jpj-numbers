"""Build a phone-friendly, self-contained HTML of all available numbers:
Semasa (RM310) + Istimewa. Collapsible per-series sections + live wildcard search.

Writes BOTH a dated archive copy in results/ and index.html at the repo root
(what GitHub Pages serves).

  python make_viewable.py                  # -> results/all_available_numbers_<today>.html + index.html
  python make_viewable.py --date 2026-06-14 --pdf
"""
import argparse
import datetime
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import dataload

PREMIUM = config.PREMIUM


def section(anchor, title, prefix, numbers, extra=""):
    cells = "".join(f"<span>{prefix} {n}</span>" for n in numbers)
    name = re.sub(r"\s+", "", title.lower())
    return (f'<details id="{anchor}" data-n="{html.escape(name)}" data-p="{html.escape(prefix.lower())}">'
            f'<summary>{html.escape(title)} <span class=c>{len(numbers):,}</span></summary>'
            f'{extra}<div class=nums>{cells}</div></details>')


def build(date_str):
    sem = dataload.load_semasa()
    ist = dataload.load_istimewa()
    sem_total = sum(len(v) for st in sem.values() for v in st.values())
    ist_total = sum(len(v) for v in ist.values())
    grand = sem_total + ist_total
    myt = datetime.timezone(datetime.timedelta(hours=8))
    stamp = datetime.datetime.now(myt).strftime("%d %b %Y, %H:%M (MYT)")

    parts = []
    parts.append(f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>JPJ Available Numbers</title><style>
*{{box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
margin:0;padding:0 10px 60px;background:#f5f6f8;color:#1c1c1e;-webkit-text-size-adjust:100%}}
header{{position:sticky;top:0;background:#0a7d3c;color:#fff;margin:0 -10px 12px;padding:12px 14px 14px;z-index:9;box-shadow:0 2px 8px rgba(0,0,0,.18)}}
h1{{font-size:17px;margin:0 0 7px;line-height:1.25}}
.meta{{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 12px;font-size:12.5px;opacity:.96}}
.meta .upd{{background:rgba(255,255,255,.18);border-radius:20px;padding:3px 11px;white-space:nowrap;font-size:12px}}
#q{{width:100%;padding:11px 12px;font-size:16px;border:0;border-radius:10px;margin-top:11px}}
h2{{font-size:15px;margin:18px 4px 6px;color:#0a7d3c}}
.price{{background:#fff7e6;border:1px solid #ffd591;border-radius:9px;padding:9px 11px;font-size:12.5px;margin:8px 0}}
details{{background:#fff;border:1px solid #e4e4e8;border-radius:9px;margin:6px 0;padding:8px 11px}}
summary{{cursor:pointer;font-size:15px;font-weight:600;list-style:none}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:'▸ ';color:#0a7d3c}}details[open] summary::before{{content:'▾ '}}
.c{{color:#0a7d3c;font-weight:700;float:right}}
.nums{{margin-top:9px;display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:4px}}
.nums span{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;text-align:center;
white-space:nowrap;background:#eef3f6;border:1px solid #dde6ec;border-radius:5px;padding:5px 2px;color:#1c1c1e}}
.ph{{color:#888;font-size:13px;margin-top:9px}}
table{{border-collapse:collapse;width:100%;font-size:13px;background:#fff;border-radius:9px;overflow:hidden}}
td,th{{border:1px solid #e4e4e8;padding:6px 9px;text-align:left}}th{{background:#f0f7f2}}
td.r,th.r{{text-align:right}}a{{color:#0a7d3c;text-decoration:none}}.hide{{display:none}}
.muted{{color:#888;font-size:12px;margin:14px 4px 4px}}
body.searching .browse{{display:none}}
#help{{font-size:11.5px;color:#fff;opacity:.9;margin-top:6px}}#help b{{background:rgba(255,255,255,.22);padding:0 4px;border-radius:3px}}
#hint{{display:none;font-size:12.5px;color:#fff;opacity:.97;margin-top:6px;font-weight:600}}
body.searching #hint{{display:block}}
</style></head><body>
<header><h1>JPJ Available Registration Numbers</h1>
<div class=meta><span><b>{grand:,}</b> numbers · Semasa {sem_total:,} · Istimewa {ist_total:,}</span>
<span class=upd>🕒 Updated {stamp}</span></div>
<input id=q placeholder="🔍 Search — e.g. VRB 9014, GM 38, or wildcard SJS _00_">
<div id=help>Tip: <b>_</b> = any digit. Try <b>SJS _00_</b>, <b>VIP 12__</b>, <b>__88</b>. Or a series/state name.</div>
<div id=hint></div>
</header>""")

    parts.append('<h2 class=browse>Semasa — by state (RM 310.00 each)</h2>')
    parts.append('<table class=browse><tr><th>State</th><th>Series</th><th class=r>Available</th></tr>')
    for st in sorted(sem):
        srs = ", ".join(f'<a href="#sem-{st.replace(" ","_")}-{s}">{s}</a>' for s in sem[st])
        cnt = sum(len(sem[st][s]) for s in sem[st])
        parts.append(f'<tr><td>{html.escape(st)}</td><td>{srs}</td><td class=r>{cnt:,}</td></tr>')
    parts.append(f'<tr><td><b>Total</b></td><td></td><td class=r><b>{sem_total:,}</b></td></tr></table>')

    parts.append('<h2 class=browse>Istimewa — premium series</h2>')
    parts.append('<table class=browse><tr><th>Series</th><th class=r>Available</th></tr>')
    for s in PREMIUM:
        if s in ist:
            parts.append(f'<tr><td><a href="#ist-{s}">{s}</a></td><td class=r>{len(ist[s]):,}</td></tr>')
    parts.append(f'<tr><td><b>Total</b></td><td class=r><b>{ist_total:,}</b></td></tr></table>')

    parts.append('<h2 class=browse>Semasa numbers</h2>')
    parts.append('<div class="price browse"><b>Price:</b> fixed <b>RM 310.00</b> per number '
                 '(RM 300 number + RM 10 tender service fee) — same for every Semasa number.</div>')
    for st in sorted(sem):
        parts.append(f'<div class="muted browse">{html.escape(st)}</div>')
        for s in sem[st]:
            anc = f'sem-{st.replace(" ","_")}-{s}'
            parts.append(section(anc, f"{st} · {s}", s, sem[st][s]))

    parts.append('<h2 class=browse>Istimewa numbers</h2>')
    parts.append('<div class="price browse">Premium series, nationwide. Per-number <b>Harga Minimum (RM)</b> '
                 'shows only on selection at checkout — not included here (numbers only).</div>')
    for s in PREMIUM:
        if s in ist:
            parts.append(section(f"ist-{s}", f"{s} (premium)", s, ist[s]))

    parts.append("""<script>
var q=document.getElementById('q'),hint=document.getElementById('hint'),
    ds=document.querySelectorAll('details'),body=document.body,t;
ds.forEach(function(d){d._g=d.querySelector('.nums');d._p=d.dataset.p;
 d._nums=[].map.call(d._g.querySelectorAll('span'),function(s){return s.textContent;});
 d._num=d._nums.map(function(s){return s.replace(/\\D/g,'');});
 d._full=d._nums.map(function(s){return '<span>'+s+'</span>';}).join('');});
function fill(d,arr){d._g.innerHTML=arr===d._nums?d._full:arr.map(function(s){return '<span>'+s+'</span>';}).join('');}
function run(){
 var v=q.value.trim().toLowerCase().replace(/\\s+/g,'');
 body.classList.toggle('searching',!!v);
 if(!v){ds.forEach(function(d){d.classList.remove('hide');d.open=false;fill(d,d._nums);});hint.textContent='';return;}
 var pm=v.match(/^([a-z]*)([0-9_]*)$/),prefix=pm?pm[1]:'',pat=pm?pm[2]:'';
 var wild=pat.indexOf('_')>=0, re=wild?new RegExp('^'+pat.replace(/_/g,'\\\\d')+'$'):null;
 var shown=0,secs=0;
 ds.forEach(function(d){
  var nameHit=!wild&&d.dataset.n.indexOf(v)>=0;
  if(!nameHit&&prefix&&d._p.indexOf(prefix)<0){d.classList.add('hide');return;}
  var m;
  if(nameHit){m=d._nums;}
  else if(wild){m=[];for(var i=0;i<d._num.length;i++){if(re.test(d._num[i]))m.push(d._nums[i]);}}
  else{m=d._nums.filter(function(n){return n.toLowerCase().replace(/\\s+/g,'').indexOf(v)>=0;});}
  if(m.length){d.classList.remove('hide');d.open=true;fill(d,m);shown+=m.length;secs++;}
  else d.classList.add('hide');
 });
 hint.textContent=shown?(shown.toLocaleString()+' plate'+(shown>1?'s':'')+' in '+secs+' series'):'no matches';
}
q.addEventListener('input',function(){clearTimeout(t);t=setTimeout(run,160);});
</script></body></html>""")

    doc = "\n".join(parts)
    dated = os.path.join(config.RESULTS, f"all_available_numbers_{date_str}.html")
    index = os.path.join(config.ROOT, "index.html")   # GitHub Pages entry point
    open(dated, "w", encoding="utf-8").write(doc)
    open(index, "w", encoding="utf-8").write(doc)
    print(f"HTML -> {dated}  +  {index}  ({len(doc)//1024} KB, {grand:,} numbers)")
    return dated, index


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--pdf", action="store_true")
    args, _ = ap.parse_known_args()
    config.ensure_dirs()
    dated, index = build(args.date)
    if args.pdf:
        from playwright.sync_api import sync_playwright
        out_pdf = os.path.join(config.RESULTS, f"all_available_numbers_{args.date}.pdf")
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_context().new_page()
            pg.goto("file://" + os.path.abspath(dated))
            pg.evaluate("()=>document.querySelectorAll('details').forEach(d=>d.open=true)")
            pg.pdf(path=out_pdf, format="A4", margin={"top": "12mm", "bottom": "12mm",
                   "left": "8mm", "right": "8mm"}, print_background=True)
            b.close()
        print(f"PDF -> {out_pdf}  ({os.path.getsize(out_pdf)//1024} KB)")
