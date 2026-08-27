"""OCR receipt scanning.

Pipeline: uploaded image → vision LLM (OpenAI GPT-4o-mini / Gemini) when
configured → pytesseract + regex parser fallback if installed → heuristic text fallback.
Extracts: merchant, date, total_minor, total_amount, currency, items, tax_minor, confidence.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("ocr")

_VISION_PROMPT = """Extract receipt data from this image. Reply with JSON only:
{"merchant": "Store Name", "date": "YYYY-MM-DD", "currency": "USD",
 "total_minor": 1250,  // total in integer minor units (e.g. $12.50 = 1250)
 "total_amount": 12.50,
 "items": [{"label": "Coffee", "amount_minor": 450}],
 "tax_minor": 100,
 "confidence": 0.95}
If the image is not a receipt reply {"error": "not_a_receipt"}."""


def parse_receipt_text(text: str) -> dict:
    """Parse raw OCR text into a structured receipt dictionary."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {
            "merchant": "Unknown Merchant",
            "date": date.today().isoformat(),
            "currency": "USD",
            "total_minor": 0,
            "total_amount": 0.0,
            "items": [],
            "tax_minor": None,
            "confidence": 0.1,
        }

    # 1. Merchant candidate (usually top non-empty line)
    merchant = lines[0]
    for l in lines[:3]:
        if not re.search(r"tax invoice|receipt|welcome|cash sale|store #\d+", l, re.I) and len(l) > 2:
            merchant = l
            break

    # 2. Date candidate
    dt_str = None
    date_match = re.search(r"\b(\d{4}[-/]\d{2}[-/]\d{2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b", text)
    if date_match:
        raw_dt = date_match.group(1)
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"):
            try:
                dt_str = datetime.strptime(raw_dt, fmt).date().isoformat()
                break
            except ValueError:
                continue
    if not dt_str:
        dt_str = date.today().isoformat()

    # 3. Currency detection
    currency = "USD"
    if "€" in text or "EUR" in text:
        currency = "EUR"
    elif "£" in text or "GBP" in text:
        currency = "GBP"
    elif "A$" in text or "AUD" in text:
        currency = "AUD"
    elif "C$" in text or "CAD" in text:
        currency = "CAD"
    elif "¥" in text or "JPY" in text:
        currency = "JPY"

    # 4. Total detection
    total_minor = 0
    total_match = re.findall(
        r"(?:total|amount due|balance due|grand total|subtotal|charge)\s*[:\$€£]?\s*(\d+[.,]\d{2})",
        text,
        re.I,
    )
    if total_match:
        val_str = total_match[-1].replace(",", ".")
        try:
            total_minor = round(float(val_str) * 100)
        except ValueError:
            total_minor = 0
    else:
        # Fallback to largest amount found in text
        all_amounts = re.findall(r"[\$€£]?\s*(\d+[.,]\d{2})", text)
        if all_amounts:
            parsed_floats = []
            for a in all_amounts:
                try:
                    parsed_floats.append(float(a.replace(",", ".")))
                except ValueError:
                    pass
            if parsed_floats:
                total_minor = round(max(parsed_floats) * 100)

    # 5. Items
    items = []
    for line in lines:
        m = re.match(r"^([A-Za-z0-9\s\.\-]{2,30})\s+[\$€£]?\s*(\d+[.,]\d{2})$", line)
        if m and not re.search(r"total|subtotal|tax|balance|cash|change|card", m.group(1), re.I):
            try:
                amt = round(float(m.group(2).replace(",", ".")) * 100)
                items.append({"label": m.group(1).strip(), "amount_minor": amt})
            except ValueError:
                pass

    confidence = 0.5
    if merchant and merchant != "Unknown Merchant":
        confidence += 0.2
    if total_minor > 0:
        confidence += 0.2
    if items:
        confidence += 0.1

    return {
        "merchant": merchant.strip(),
        "date": dt_str,
        "currency": currency,
        "total_minor": total_minor,
        "total_amount": round(total_minor / 100, 2),
        "items": items,
        "tax_minor": None,
        "confidence": min(1.0, round(confidence, 2)),
    }


async def ocr_receipt(image_bytes: bytes, mime: str = "image/jpeg") -> dict:
    # 1. Vision LLM
    result = await _vision_openai(image_bytes, mime) or await _vision_gemini(image_bytes, mime)
    if result and "error" not in result:
        # Format response consistently
        if "total_amount" not in result and "total_minor" in result and result["total_minor"] is not None:
            result["total_amount"] = round(result["total_minor"] / 100, 2)
        elif "total_minor" not in result and "total_amount" in result and result["total_amount"] is not None:
            result["total_minor"] = round(result["total_amount"] * 100)
        if "confidence" not in result:
            result["confidence"] = 0.95
        return result

    # 2. Tesseract fallback
    result = _tesseract_fallback(image_bytes)
    if result is not None:
        return result

    # 3. Deterministic fallback for text-based receipt payloads
    try:
        raw_str = image_bytes.decode("utf-8")
        if any(w in raw_str.lower() for w in ("total", "receipt", "merchant", "$", "tax", "subtotal")):
            return parse_receipt_text(raw_str)
    except Exception:
        pass

    raise RuntimeError(
        "No OCR backend available. Configure OPENAI_API_KEY/GOOGLE_API_KEY "
        "(vision) or install pytesseract + tesseract binary."
    )


async def _vision_openai(image_bytes: bytes, mime: str) -> dict | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        b64 = base64.b64encode(image_bytes).decode()
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or ""
        return json.loads(_extract_json(raw))
    except Exception as exc:
        log.warning("openai_ocr_failed", error=str(exc))
        return None


async def _vision_gemini(image_bytes: bytes, mime: str) -> dict | None:
    if not settings.google_api_key:
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.google_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        result = model.generate_content([
            _VISION_PROMPT,
            {"mime_type": mime, "data": image_bytes},
        ])
        return json.loads(_extract_json(result.text))
    except Exception as exc:
        log.warning("gemini_ocr_failed", error=str(exc))
        return None


def _tesseract_fallback(image_bytes: bytes) -> dict | None:
    try:
        import io
        import pytesseract
        from PIL import Image

        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        if text.strip():
            return parse_receipt_text(text)
        return None
    except Exception as exc:
        log.info("tesseract_unavailable", error=str(exc))
        return None


def _extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON in OCR response: {text[:120]}")
    return text[start : end + 1]
