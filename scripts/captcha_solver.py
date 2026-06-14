"""Offline captcha reader for the JPJ login 'Kod Sekuriti' (5 distorted letters).

Uses ddddocr (a bundled ONNX model, no API key, fully offline). Accuracy on this
captcha style is high but not perfect, which is fine: the login flow simply
refreshes the captcha and retries on a miss, so a few cheap attempts -> success.
"""
import re

_ocr = None


def _engine():
    global _ocr
    if _ocr is None:
        import ddddocr  # lazy: model load is ~1s
        _ocr = ddddocr.DdddOcr(show_ad=False)
    return _ocr


def solve(image_bytes):
    """Return the best-guess captcha code (UPPERCASE letters only).

    The portal shows 5 uppercase A-Z glyphs, so we strip anything else and
    uppercase the result to match what's displayed."""
    raw = _engine().classification(image_bytes)
    code = re.sub(r"[^A-Za-z]", "", raw or "").upper()
    return code
