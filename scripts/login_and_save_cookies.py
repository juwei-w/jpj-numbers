"""
Log in to the JPJ mySIKAP portal and save the authenticated session (auth.json).

The login uses a 5-letter visual security code (captcha). This is solved
automatically with an offline OCR model (ddddocr) and a retry loop, so the whole
process is hands-off: a wrong guess simply refreshes the captcha and tries again.
If automatic solving fails repeatedly it falls back to a real browser window for
you to type the code once.

This automates the account holder's OWN login for personal data collection.

Usage:
  python login_and_save_cookies.py                 # auto, credentials from config
  python login_and_save_cookies.py --manual        # type the captcha yourself
  python login_and_save_cookies.py --attempts 15
"""
from playwright.sync_api import sync_playwright
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import captcha_solver

LOGIN_URL = "https://public.jpj.gov.my/public/"


def _select_individu(page):
    for sel in ["input[type=radio][value*='I' i]",
                "label:has-text('Individu') input[type=radio]", "input#individu"]:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                loc.check()
                return True
        except Exception:
            continue
    try:
        page.get_by_text("Individu", exact=True).first.click()
        return True
    except Exception:
        return False


def _fields(page):
    """Locate the id / password / captcha-input / captcha-image element ids.
    IDs regenerate each load, so find them structurally (text-before-password =
    user id, text-after-password = captcha)."""
    return page.evaluate(r"""()=>{
        const inputs=[...document.querySelectorAll('input')];
        const vis=i=>i&&i.offsetParent!==null;
        const pwI=inputs.findIndex(i=>i.type==='password'&&vis(i));
        let id=null,cap=null;
        inputs.forEach((i,idx)=>{ if(i.type!=='text'||!vis(i))return;
            if(pwI>=0&&idx<pwI){ if(!id)id=i.id; } else if(cap===null){ cap=i.id; } });
        const texts=inputs.filter(i=>i.type==='text'&&vis(i));
        if(!id&&texts[0]) id=texts[0].id;
        if(!cap&&texts.length>1) cap=texts[texts.length-1].id;
        const img=[...document.querySelectorAll('img')].find(x=>/captcha/i.test(x.src||''));
        const pw=inputs[pwI];
        return {id, cap, pw: pw?pw.id:null, img: img?img.id:null};
    }""")


def _click_login(page):
    for how in (lambda: page.get_by_role("button", name="Log Masuk").first.click(timeout=4000),
                lambda: page.get_by_text("Log Masuk", exact=False).first.click(timeout=4000),
                lambda: page.keyboard.press("Enter")):
        try:
            how()
            return True
        except Exception:
            continue
    return False


def _logged_in(page, secs=12):
    """True if the password field stays gone for a few consecutive checks."""
    end = time.time() + secs
    streak = 0
    while time.time() < end:
        try:
            pw = page.locator("input[type=password]").first
            gone = pw.count() == 0 or not pw.is_visible()
        except Exception:
            gone = True
        streak = streak + 1 if gone else 0
        if streak >= 3:
            return True
        time.sleep(1.0)
    return False


def _attempt(page, username, password):
    """One full login attempt on a freshly-loaded page. Returns True on success."""
    page.wait_for_selector("input", timeout=25000)
    time.sleep(1.5)
    _select_individu(page)
    f = _fields(page)
    if not (f["id"] and f["pw"] and f["cap"] and f["img"]):
        return False
    page.locator(f"#{f['id']}").fill(username)
    page.locator(f"#{f['pw']}").fill(password)
    img_bytes = page.locator(f"#{f['img']}").screenshot()
    code = captcha_solver.solve(img_bytes)
    if len(code) < 4:
        return False  # unreadable -> reload for a fresh captcha
    page.locator(f"#{f['cap']}").fill(code)
    print(f"  captcha guess: {code}", flush=True)
    _click_login(page)
    return _logged_in(page)


def run(username=None, password=None, save_path=None, attempts=10, manual=False, headless=True):
    if save_path is None:
        save_path = config.AUTH
    if not manual and (not username or not password):
        username, password = config.load_credentials()
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False if manual else headless)
        context = browser.new_context()
        page = context.new_page()

        if manual:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.wait_for_selector("input", timeout=25000)
            _select_individu(page)
            f = _fields(page)
            if f["id"]:
                page.locator(f"#{f['id']}").fill(username or "")
            if f["pw"] and password:
                page.locator(f"#{f['pw']}").fill(password)
            print("\n" + "=" * 64 + "\nType the Kod Sekuriti in the browser and click Log Masuk.\n"
                  + "=" * 64, flush=True)
            ok = _logged_in(page, secs=300)
        else:
            ok = False
            for i in range(1, attempts + 1):
                print(f"login attempt {i}/{attempts}...", flush=True)
                try:
                    page.goto(LOGIN_URL, wait_until="domcontentloaded")
                    if _attempt(page, username, password):
                        ok = True
                        break
                except Exception as e:
                    print(f"  attempt error: {type(e).__name__}: {e}", flush=True)
                time.sleep(1.0)
            if not ok:
                browser.close()
                if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
                    # Headless cloud runner: no human, no display, and re-entering the
                    # sync Playwright API here crashes ("sync API inside asyncio loop").
                    # Fail cleanly so the shard reports a login failure, not a traceback.
                    print("auto-login failed after retries (headless CI — no manual fallback).",
                          flush=True)
                    return False
                print("auto-login failed after retries — opening a browser for manual captcha.",
                      flush=True)
                return run(username, password, save_path, manual=True)

        if not ok:
            print("Login not detected — not saving.", flush=True)
            browser.close()
            return False
        time.sleep(1.5)
        context.storage_state(path=save_path)
        print(f"Session saved to: {save_path}", flush=True)
        browser.close()
        return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--save", default=None, help="session path (default work/auth.json)")
    ap.add_argument("--attempts", type=int, default=10)
    ap.add_argument("--manual", action="store_true", help="type the captcha yourself")
    args = ap.parse_args()
    ok = run(args.username, args.password, args.save, attempts=args.attempts, manual=args.manual)
    sys.exit(0 if ok else 1)
