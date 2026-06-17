"""
Ad tag parser — extracts creative URLs, click URLs, and dimensions from
common ad tag formats: HTML img/anchor, iFrame, CM360 ins, CM360 script,
and generic JavaScript tags.
"""
from __future__ import annotations
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional


# ── Parse result ──────────────────────────────────────────────────────────────

@dataclass
class TagParseResult:
    tag_type: str                           # human-readable tag format
    creative_url: Optional[str] = None     # direct image/iframe URL (if extractable)
    click_url: Optional[str] = None        # final destination URL
    declared_width: Optional[int] = None
    declared_height: Optional[int] = None
    notes: list[str] = field(default_factory=list)


def parse_tag(html: str) -> TagParseResult:
    """Parse an ad tag string and return all extractable information."""
    r = TagParseResult(tag_type="Unknown")

    # ── Tag type detection ────────────────────────────────────────────────────
    if re.search(r'class=["\']dcmads["\']|data-dcm-placement', html, re.I):
        r.tag_type = "CM360 ins (JavaScript)"
    elif re.search(r"doubleclick\.net|ad\.doubleclick", html, re.I):
        r.tag_type = "CM360 iFrame" if re.search(r"<iframe", html, re.I) else "CM360 script"
    elif re.search(r"<iframe", html, re.I):
        r.tag_type = "iFrame"
    elif re.search(r"<img", html, re.I) and re.search(r"<a\b", html, re.I):
        r.tag_type = "HTML (img + anchor)"
    elif re.search(r"<img", html, re.I):
        r.tag_type = "HTML (img only)"
    elif re.search(r"<script", html, re.I):
        r.tag_type = "JavaScript"

    # ── Dimensions ────────────────────────────────────────────────────────────
    # style="width:728px; height:90px"
    m = re.search(r"width\s*:\s*(\d+)px.*?height\s*:\s*(\d+)px", html, re.I | re.S)
    if m:
        r.declared_width, r.declared_height = int(m.group(1)), int(m.group(2))

    # width="728" height="90"  or  width=728 height=90
    if not r.declared_width:
        wm = re.search(r'\bwidth=["\']?(\d+)["\']?', html, re.I)
        hm = re.search(r'\bheight=["\']?(\d+)["\']?', html, re.I)
        if wm and hm:
            r.declared_width, r.declared_height = int(wm.group(1)), int(hm.group(1))

    # sz=728x90  (CM360 script tags)
    if not r.declared_width:
        sm = re.search(r'\bsz=(\d+)x(\d+)', html, re.I)
        if sm:
            r.declared_width, r.declared_height = int(sm.group(1)), int(sm.group(2))

    # ── Creative URL ──────────────────────────────────────────────────────────
    # <img src="...">
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if m:
        r.creative_url = m.group(1).strip()

    # <iframe src="...">
    if not r.creative_url:
        m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
        if m:
            r.creative_url = m.group(1).strip()

    # CM360 Standard Tag: the <img src> is a tracking pixel (ddm/trackimp), not the creative.
    # Clear it so callers don't try to download a 1×1 pixel and run spec checks on it.
    if r.creative_url and re.search(r'doubleclick\.net/ddm/track', r.creative_url, re.I):
        r.creative_url = None

    # ── Click URL ─────────────────────────────────────────────────────────────
    # <a href="...">
    m = re.search(r'<a\b[^>]+href=["\']([^"\']+)["\']', html, re.I)
    if m:
        r.click_url = _extract_destination(m.group(1).strip())

    # data-dcm-click-tracker="..."
    if not r.click_url:
        m = re.search(r'data-dcm-click-tracker=["\']([^"\']+)["\']', html, re.I)
        if m:
            r.click_url = m.group(1).strip()

    # Destination embedded in CM360 script src after final semicolon
    if not r.click_url:
        m = re.search(
            r'src=["\']https://ad\.doubleclick\.net[^"\']*;(https?://[^"\']+)["\']',
            html, re.I,
        )
        if m:
            r.click_url = m.group(1).strip()

    # ── Notes ─────────────────────────────────────────────────────────────────
    # JS-rendered tags have no static creative URL
    if r.tag_type in ("CM360 ins (JavaScript)", "CM360 script", "JavaScript") and not r.creative_url:
        r.notes.append(
            "This tag renders the creative dynamically via JavaScript — "
            "there is no static image URL to download. "
            "Ask the client for a static backup image (JPEG/GIF) for spec checking."
        )

    # CM360 standard display tag — creative is served by CM360, not a static file
    if r.tag_type in ("CM360 iFrame", "CM360 script") and not r.creative_url and not r.notes:
        r.notes.append(
            "CM360 standard display tag — the creative is served dynamically by CM360 "
            "and cannot be downloaded for spec checking. "
            "Upload the actual banner files to the Single file or Multi-file tab instead."
        )

    return r


def _extract_destination(url: str) -> str:
    """Pull the real landing page out of ad-server redirect URLs."""
    # CM360: https://ad.doubleclick.net/.../clk/...;https://destination.com
    parts = url.split(";")
    for p in reversed(parts):
        p = p.strip()
        if p.startswith("http") and "doubleclick.net" not in p:
            return p

    # Destination in a query param
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        for k in ("url", "dest", "redirect", "r", "u", "goto", "click", "adurl"):
            if k in qs:
                return urllib.parse.unquote(qs[k][0])
    except Exception:
        pass

    return url


# ── Creative download ─────────────────────────────────────────────────────────

def download_creative(url: str, timeout: int = 15) -> tuple[bytes, str] | None:
    """
    Download a creative image from a URL.
    Returns (file_bytes, fmt) where fmt is "JPEG", "PNG", or "GIF", or None on failure.
    """
    import requests as _req
    try:
        resp = _req.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; carsales-ad-checker/1.0)"},
        )
        if resp.status_code != 200:
            return None

        ct  = resp.headers.get("Content-Type", "").lower()
        ext = urllib.parse.urlparse(url).path.rsplit(".", 1)[-1].upper()

        if "png"  in ct:            fmt = "PNG"
        elif "gif" in ct:           fmt = "GIF"
        elif "jpeg" in ct or "jpg" in ct: fmt = "JPEG"
        elif ext in ("PNG", "GIF"): fmt = ext
        elif ext in ("JPG", "JPEG"): fmt = "JPEG"
        else:                       fmt = "JPEG"

        return resp.content, fmt
    except Exception:
        return None


# ── Click URL / UTM checker ───────────────────────────────────────────────────

REQUIRED_UTMS     = ["utm_source", "utm_medium", "utm_campaign"]
RECOMMENDED_UTMS  = ["utm_content", "utm_term"]
_STAGING_RE       = re.compile(
    r"localhost|127\.0\.0\.1|staging\.|\.staging|dev\.|\.dev\.|test\.|uat\.|preprod\.",
    re.I,
)


@dataclass
class UrlCheckResult:
    url: str
    resolves: bool
    status_code: Optional[int]
    final_url: Optional[str]
    is_staging: bool
    utm_present: dict[str, str]
    utm_missing: list[str]
    utm_recommended_missing: list[str]
    notes: list[str] = field(default_factory=list)


def check_url(url: str, timeout: int = 10) -> UrlCheckResult:
    """Resolve the click URL and validate UTM parameters."""
    import requests as _req

    is_staging = bool(_STAGING_RE.search(url))
    notes: list[str] = []

    def _utms(u: str) -> dict[str, str]:
        try:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
            return {k: v[0] for k, v in qs.items() if k.startswith("utm_")}
        except Exception:
            return {}

    utm_present = _utms(url)

    try:
        resp = _req.get(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; carsales-ad-checker/1.0)"},
        )
        resolves    = resp.status_code < 400
        status_code = resp.status_code
        final_url   = resp.url if resp.url != url else None

        if final_url:
            final_utms = _utms(final_url)
            if final_utms:
                utm_present = final_utms          # prefer UTMs from final destination
            if _STAGING_RE.search(final_url):
                is_staging = True

    except _req.exceptions.Timeout:
        resolves, status_code, final_url = False, None, None
        notes.append("Request timed out after 10 seconds.")
    except _req.exceptions.ConnectionError:
        resolves, status_code, final_url = False, None, None
        notes.append("Connection failed — check the URL is accessible.")
    except Exception as e:
        resolves, status_code, final_url = False, None, None
        notes.append(f"Unexpected error: {e}")

    return UrlCheckResult(
        url=url,
        resolves=resolves,
        status_code=status_code,
        final_url=final_url,
        is_staging=is_staging,
        utm_present=utm_present,
        utm_missing=[u for u in REQUIRED_UTMS    if u not in utm_present],
        utm_recommended_missing=[u for u in RECOMMENDED_UTMS if u not in utm_present],
        notes=notes,
    )
