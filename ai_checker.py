from __future__ import annotations
import base64
import io
import json
from dataclasses import dataclass
from typing import Optional
from PIL import Image


@dataclass
class AICheckResult:
    name: str
    passed: bool
    confidence: str  # "high" | "medium" | "low"
    message: str
    needs_client: bool = False


def _encode_image(img: Image.Image) -> str:
    """Base64-encode image as JPEG for the API."""
    buf = io.BytesIO()
    out = img.convert("RGB") if img.mode not in ("RGB",) else img
    # Downscale very large images to keep tokens manageable
    max_side = 1200
    w, h = out.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        out = out.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    out.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()


def run_ai_checks(
    img: Image.Image,
    spec: dict,
    format_key: str,
    api_key: str,
) -> list[AICheckResult]:
    try:
        import anthropic
    except ImportError:
        return [AICheckResult(
            name="AI Checks",
            passed=False,
            confidence="high",
            message="anthropic package not installed — run: pip install anthropic",
        )]

    client = anthropic.Anthropic(api_key=api_key)
    img_b64 = _encode_image(img)

    is_card_image = format_key == "card_image"
    clear_zone_px = spec.get("clear_zone_top_px")

    questions = """Answer only in valid JSON. Analyse the ad creative image and respond to each of these checks:

1. "branding": Is a brand logo, brand name, or vehicle model name clearly visible anywhere in the image?
   PASS = branding is present. FAIL = no branding found.

2. "competitor": Does the image contain any logo or text referencing competitor car classified publishers such as Drive.com.au, CarGuide, Autotrader, CarsGuide, RedBook, or similar car listing/review sites?
   PASS = no competitor references. FAIL = competitor reference found.

3. "text_case": Does any text in the image use ALL CAPS styling across a whole word or phrase (other than an acronym or logo)?
   PASS = no prohibited all-caps text found. FAIL = all-caps text found that is not an acronym."""

    if is_card_image and clear_zone_px:
        questions += f"""

4. "clear_zone": In this 720×720px image, is the top {clear_zone_px}px (roughly the top 39%) free from any text, logos, prices, or key foreground content?
   PASS = top area is clear. FAIL = copy/logos found in the clear zone."""

    questions += """

Respond with ONLY this JSON structure (no markdown, no explanation):
{
  "branding": {"result": "PASS or FAIL", "confidence": "HIGH or MEDIUM or LOW", "explanation": "one sentence"},
  "competitor": {"result": "PASS or FAIL", "confidence": "HIGH or MEDIUM or LOW", "explanation": "one sentence"},
  "text_case": {"result": "PASS or FAIL", "confidence": "HIGH or MEDIUM or LOW", "explanation": "one sentence"}"""

    if is_card_image and clear_zone_px:
        questions += """,
  "clear_zone": {"result": "PASS or FAIL", "confidence": "HIGH or MEDIUM or LOW", "explanation": "one sentence"}"""

    questions += "\n}"

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": img_b64,
                        },
                    },
                    {"type": "text", "text": questions},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        # Strip any markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data: dict = json.loads(raw)

    except json.JSONDecodeError as e:
        return [AICheckResult(
            name="AI Checks",
            passed=False,
            confidence="low",
            message=f"Could not parse AI response: {e}",
        )]
    except Exception as e:
        return [AICheckResult(
            name="AI Checks",
            passed=False,
            confidence="low",
            message=f"AI check error: {e}",
        )]

    label_map = {
        "branding": "Branding Visible",
        "competitor": "Competitor References",
        "text_case": "Text Casing (no all-caps)",
        "clear_zone": f"Clear Zone (top {clear_zone_px}px)",
    }

    results: list[AICheckResult] = []
    for key, label in label_map.items():
        if key not in data:
            continue
        val = data[key]
        passed = val.get("result", "FAIL").upper() == "PASS"
        conf = val.get("confidence", "MEDIUM").lower()
        explanation = val.get("explanation", "")
        results.append(AICheckResult(
            name=label,
            passed=passed,
            confidence=conf,
            message=explanation,
            needs_client=not passed,
        ))

    return results
