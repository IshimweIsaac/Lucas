"""OCR grounding via pytesseract.

Degrades gracefully when pytesseract or the tesseract binary is missing:
ocr_available() is False and ocr_words() returns []. All OCR text is untrusted
screen data — used for coordinate math only.
"""

from __future__ import annotations

import difflib
import shutil

from core.logger import get_logger

from .models import WordBox

logger = get_logger(__name__)

try:
    import pytesseract

    _TESSERACT = True
except Exception:
    _TESSERACT = False

_TESSERACT_BIN = shutil.which("tesseract") is not None

_FUZZY_THRESHOLD = 0.8


def ocr_available() -> bool:
    """Return True when both pytesseract and the tesseract binary exist."""
    return bool(_TESSERACT and _TESSERACT_BIN)


def ocr_words(image, lang: str = "eng") -> list[WordBox]:
    """Run OCR over *image* and return detected words as WordBox list."""
    if not ocr_available():
        return []
    try:
        data = pytesseract.image_to_data(
            image, lang=lang, output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        logger.debug("ocr_words failed: %s", e)
        return []
    try:
        texts = data.get("text") or []
    except Exception:
        return []
    words: list[WordBox] = []
    for i in range(len(texts)):
        try:
            text = (texts[i] or "").strip()
            if not text:
                continue
            conf_raw = data.get("conf")
            conf = 0.0
            if conf_raw and i < len(conf_raw):
                try:
                    conf = float(conf_raw[i] or 0)
                except (TypeError, ValueError):
                    conf = 0.0
            words.append(
                WordBox(
                    text=text,
                    x=int(data.get("left", [0] * len(texts))[i]),
                    y=int(data.get("top", [0] * len(texts))[i]),
                    w=int(data.get("width", [0] * len(texts))[i]),
                    h=int(data.get("height", [0] * len(texts))[i]),
                    conf=conf,
                )
            )
        except Exception:
            continue
    return words


def _fuzzy_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_words(words: list[WordBox], target: str) -> WordBox | None:
    """Match *target* against OCR words: exact -> substring -> fuzzy (>=0.8)."""
    target = (target or "").strip().lower()
    if not target or not words:
        return None

    best_exact: WordBox | None = None
    best_sub: WordBox | None = None
    best_fuzzy: tuple[float, WordBox] | None = None

    for word in words:
        wtext = word.text.strip().lower()
        if not wtext:
            continue
        if wtext == target:
            if best_exact is None or word.conf > best_exact.conf:
                best_exact = word
            continue
        if target in wtext or wtext in target:
            if best_sub is None or word.conf > best_sub.conf:
                best_sub = word
            continue
        ratio = _fuzzy_ratio(wtext, target)
        if ratio >= _FUZZY_THRESHOLD:
            if best_fuzzy is None or ratio > best_fuzzy[0]:
                best_fuzzy = (ratio, word)

    if best_exact is not None:
        return best_exact
    if best_sub is not None:
        return best_sub
    if best_fuzzy is not None:
        return best_fuzzy[1]
    return None