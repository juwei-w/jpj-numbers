"""
Robust helpers for driving the JPJ mySIKAP ZK reserve-number form.

ZK quirks handled here:
  - widget IDs regenerate every page load -> locate everything by row label text
  - readonly comboboxes open via their '-btn' arrow, items live in '#<id>-pp'
  - the form is progressive (fields appear after earlier selections)
  - server round-trips are flaky -> retry wrappers + explicit waits
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

BASE = "https://public.jpj.gov.my/public/"
TARGET = BASE + "#/vel/04velnummgt/vel04ReserveNumberAdd"


FORM_READY = ("() => [...document.querySelectorAll('td')]"
              ".some(t => /Kategori\\s*Siri/.test(t.innerText))")


def _form_ready(page):
    try:
        return page.evaluate(FORM_READY)
    except Exception:
        return False


def open_form(context, attempts=5):
    """New page on the reserve-number form. SPA deep-links sometimes bounce to
    the landing page, so retry navigation until the Kategori Siri row renders."""
    page = context.new_page()
    for i in range(attempts):
        try:
            page.goto(TARGET, wait_until="domcontentloaded")
        except Exception:
            pass
        # poll up to ~18s for the form to render
        for _ in range(18):
            if _form_ready(page):
                time.sleep(1.5)
                return page
            # detect a bounce to login
            if page.locator("input[type=password]").first.count() and \
               page.locator("input[type=password]").first.is_visible():
                raise RuntimeError("Session expired — re-run login_and_save_cookies.py")
            time.sleep(1.0)
        # nudge: re-assert the route hash, then reload
        try:
            page.evaluate("() => { location.hash = '#/vel/04velnummgt/vel04ReserveNumberAdd'; }")
            time.sleep(1.0)
            page.reload(wait_until="domcontentloaded")
        except Exception:
            pass
    diag = os.path.join(config.WORK, "diag")
    os.makedirs(diag, exist_ok=True)
    shot = os.path.join(diag, "open_form_FAILED.png")
    page.screenshot(path=shot, full_page=True)
    raise RuntimeError(f"Reserve-number form did not render after retries (see {shot})")


def _combo_btn(page, label_substr):
    return page.locator(
        f"xpath=//td[contains(normalize-space(.),'{label_substr}')]"
        f"/following::i[contains(@id,'-btn')][1]"
    ).first


def combo_options(page, label_substr):
    """Return the list of option texts for the combobox in the labelled row."""
    btn = _combo_btn(page, label_substr)
    bid = btn.get_attribute("id")
    pp = "#" + bid[:-4] + "-pp"
    return [t.strip() for t in page.locator(f"{pp} .z-comboitem").all_inner_texts() if t.strip()]


def select_combo(page, label_substr, item_text, settle=1.2, retries=4):
    """Open the labelled combobox and click the matching item. Retries on flake.

    ZK combobox arrows are tiny background-image <i> icons that Playwright often
    reports as 'not visible', so we open via a JS click on the -btn (or the input)
    and select the item with dispatch_event to bypass actionability checks."""
    last = None
    for attempt in range(retries):
        try:
            btn = _combo_btn(page, label_substr)
            btn.wait_for(state="attached", timeout=10000)
            bid = btn.get_attribute("id")
            base = bid[:-4]
            pp = "#" + base + "-pp"
            # open via JS click on the arrow; fall back to the input element
            page.evaluate(
                """(base) => {
                    const b = document.getElementById(base + '-btn');
                    const inp = document.getElementById(base + '-real');
                    (b || inp).click();
                }""", base)
            # wait for the popup to actually populate
            page.locator(f"{pp} .z-comboitem").first.wait_for(state="attached", timeout=8000)
            time.sleep(0.3)
            item = page.locator(f"{pp} .z-comboitem", has_text=item_text).first
            item.wait_for(state="attached", timeout=8000)
            item.dispatch_event("click")
            time.sleep(settle)
            return True
        except Exception as e:
            last = e
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(1.0)
    raise RuntimeError(f"select_combo({label_substr!r}, {item_text!r}) failed: {last}")


def dismiss_dialogs(page):
    """Close any open ZK message dialog (Tutup/OK) and clear leftover modal masks."""
    try:
        page.evaluate(
            """() => {
                // click close/OK buttons of any visible ZK window/messagebox
                document.querySelectorAll('.z-window, .z-messagebox-window, div[role=dialog]')
                  .forEach(w => {
                    if (w.getBoundingClientRect().height > 0) {
                      const btn = [...w.querySelectorAll('button')]
                        .find(b => /Tutup|OK|Close/i.test(b.innerText));
                      if (btn) btn.click();
                    }
                  });
                // remove orphaned modal masks that block pointer events
                document.querySelectorAll('.z-modal-mask, .z-loading, .z-loading-indicator')
                  .forEach(m => { m.style.display = 'none'; });
            }"""
        )
    except Exception:
        pass


def wait_no_mask(page, timeout=8.0):
    """Wait until no modal/loading mask intercepts clicks; dismiss if it lingers."""
    end = time.time() + timeout
    while time.time() < end:
        masked = page.evaluate(
            """() => [...document.querySelectorAll('.z-modal-mask, .z-loading')]
                  .some(m => m.getBoundingClientRect().height > 0
                          && getComputedStyle(m).display !== 'none')"""
        )
        if not masked:
            return
        time.sleep(0.3)
    dismiss_dialogs(page)


def click_button(page, name_regex, settle=2.0):
    import re as _re
    dismiss_dialogs(page)
    wait_no_mask(page)
    page.get_by_role("button", name=_re.compile(name_regex, _re.I)).first.click(timeout=12000)
    time.sleep(settle)


def page_plain_text(page):
    import re as _re
    from html import unescape
    h = page.content()
    t = _re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=_re.S)
    t = _re.sub(r"<[^>]+>", " ", t)
    return _re.sub(r"\s+", " ", unescape(t)).strip()
