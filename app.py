from __future__ import annotations
import io
import os
import zipfile
import datetime

APP_VERSION = "1.3.0"

import re
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from specs import FORMATS, FORMAT_GROUPS, CARD_TEXT_LIMITS, COPY_LIMITS
from checker import run_all_checks, run_video_checks, CheckResult
from fixer import apply_fixes
from ai_checker import run_ai_checks, AICheckResult
from tag_parser import (
    parse_tag, download_creative, check_url,
    REQUIRED_UTMS, RECOMMENDED_UTMS,
)


# ══════════════════════════════════════════════════════════════════════════════
# Feedback helpers
# ══════════════════════════════════════════════════════════════════════════════

_ACTION_HINTS: dict[str, str] = {
"compress":   "Please reduce the file size to meet the limit.",
    "convert":    "Please convert to the required file format.",
    "add_border": "Please add a 1px solid border around the creative.",
}


def _fmt_issue(c) -> str:
    """Turn any CheckResult or AICheckResult into a plain-English bullet."""
    hint = _ACTION_HINTS.get(getattr(c, "fix_action", None) or "", "")
    return f"{c.message}" + (f" {hint}" if hint else "")


def build_feedback(items: list[dict], campaign: str = "") -> str:
    """
    Build a ready-to-send client feedback email.

    items: list of {
        filename   : str,
        spec_name  : str,
        client_checks  : list[CheckResult | AICheckResult],   # must go back to client
        fixable_checks : list[CheckResult],                   # auto-fixed on our end
    }
    """
    date_str = datetime.date.today().strftime("%d %B %Y")
    heading  = f"Creative Submission Review{' — ' + campaign if campaign else ''}"

    has_client  = any(d["client_checks"]  for d in items)
    has_fixable = any(d["fixable_checks"] for d in items)

    L: list[str] = [
        f"Subject: {heading}",
        f"Date: {date_str}",
        "",
        "Hi [Name],",
        "",
        (
            "Thank you for submitting your ad creatives for the carsales Network. "
            "We have reviewed the files against our specifications and identified the following."
            if has_client else
            "Thank you for submitting your ad creatives for the carsales Network. "
            "We have reviewed the files — all issues have been corrected on your behalf "
            "and no further action is required from you."
        ),
        "",
    ]

    if has_client:
        L += [
            "─" * 48,
            "ITEMS REQUIRING YOUR REVISION",
            "─" * 48,
            "",
        ]
        for d in items:
            if not d["client_checks"]:
                continue
            L.append(f"  {d['filename']}  ({d['spec_name']})")
            for c in d["client_checks"]:
                L.append(f"    • {c.name}: {_fmt_issue(c)}")
            L.append("")

    if has_fixable:
        L += [
            "─" * 48,
            "ITEMS CORRECTED ON YOUR BEHALF",
            "─" * 48,
            "",
        ]
        for d in items:
            if not d["fixable_checks"]:
                continue
            L.append(f"  {d['filename']}  ({d['spec_name']})")
            for c in d["fixable_checks"]:
                L.append(f"    • {c.name}: corrected automatically — no action required.")
            L.append("")

    if has_client:
        L += [
            "Please revise the flagged items and resubmit at your earliest convenience.",
            "If you have any questions, please don't hesitate to reach out.",
        ]

    L += [
        "",
        "Kind regards,",
        "[Your name]",
        "carsales mediahouse",
        "adops@carsalesmediahouse.com.au",
    ]

    return "\n".join(L)


def clipboard_btn(text: str, btn_key: str) -> None:
    """Render a branded copy-to-clipboard button via injected JS."""
    safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    components.html(
        f"""
        <button
            onclick="
                navigator.clipboard.writeText(`{safe}`)
                    .then(()=>{{
                        this.textContent='✓ Copied to clipboard!';
                        this.style.background='#01295F';
                        setTimeout(()=>{{
                            this.textContent='📋 Copy to clipboard';
                            this.style.background='#1E90FF';
                        }}, 2500);
                    }})
                    .catch(()=>{{ this.textContent='Select text above and copy manually'; }})
            "
            style="background:#1E90FF;color:#fff;border:none;padding:10px 24px;
                   border-radius:6px;cursor:pointer;font-weight:600;font-size:0.87rem;
                   font-family:Manrope,sans-serif;transition:background 0.2s;">
            📋 Copy to clipboard
        </button>
        """,
        height=52,
    )


def feedback_ui(items: list[dict], key_prefix: str, default_campaign: str = "") -> None:
    """Render the campaign name input, email preview, and copy button."""
    campaign = st.text_input(
        "Campaign name (optional)",
        value=default_campaign,
        placeholder="e.g. Toyota Corolla — May 2026",
        key=f"{key_prefix}_campaign",
    )

    text = build_feedback(items, campaign)

    # When the auto-generated text changes (e.g. fixes applied, new file, AI checks ran),
    # push the new text into the textarea's session state so it re-renders with updated content.
    # User edits are preserved as long as the underlying check results haven't changed.
    _base_key = f"{key_prefix}_email_base"
    _area_key = f"{key_prefix}_textarea"
    if st.session_state.get(_base_key) != text:
        st.session_state[_base_key] = text
        st.session_state[_area_key] = text

    # Editable preview — user can tweak before sending
    edited = st.text_area(
        "Edit before sending:",
        height=420,
        key=_area_key,
    )

    col_btn, col_tip = st.columns([2, 3])
    with col_btn:
        clipboard_btn(edited, key_prefix)
    with col_tip:
        st.caption("If you edited the email, the button copies your edited version.")


# ══════════════════════════════════════════════════════════════════════════════
# Page config
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="carsales Ad Spec Checker",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ── Dark mode state ───────────────────────────────────────────────────────────
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

# ── API key from secrets only (silent — no UI input) ─────────────────────────
api_key = ""
try:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:
    pass

# ── Brand styles ──────────────────────────────────────────────────────────────
_DARK = st.session_state.dark_mode

_MAIN_BG      = "#0A1628" if _DARK else "#F2F5F7"
_SECONDARY_BG = "#102040" if _DARK else "#E2EAF0"
_TEXT         = "#D8E4F0" if _DARK else "#33373D"
_SIDEBAR_BG   = "#060E1A" if _DARK else "#01295F"
_H_COLOR      = "#66CBE1" if _DARK else "#01295F"
_HR_COLOR     = "#1E3A5F" if _DARK else "#C8D8E8"
_INPUT_BG     = "#0D2540" if _DARK else "#02306B"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {{
        font-family: 'Manrope', sans-serif !important;
    }}

    /* ── Main background ── */
    .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], section.main {{
        background-color: {_MAIN_BG} !important;
    }}

    /* ── Body text ── */
    p, li, span, label, div.stMarkdown, .stText,
    [data-testid="stMarkdownContainer"] p {{
        color: {_TEXT} !important;
    }}

    /* ── Headings ── */
    h1 {{ color: {_H_COLOR} !important; font-weight: 800 !important; }}
    h2, h3 {{ color: {_H_COLOR} !important; font-weight: 700 !important; }}

    /* ── Expanders & metric cards ── */
    [data-testid="stExpander"] {{
        background-color: {_SECONDARY_BG} !important;
        border-color: {_HR_COLOR} !important;
    }}
    [data-testid="metric-container"] {{
        background-color: {_SECONDARY_BG} !important;
        border-radius: 8px;
    }}

    /* ── Input fields in main area ── */
    [data-testid="stMain"] input,
    [data-testid="stMain"] textarea,
    [data-testid="stMain"] select {{
        background-color: {_SECONDARY_BG} !important;
        color: {_TEXT} !important;
        border-color: {_HR_COLOR} !important;
    }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {{ background-color: {_SIDEBAR_BG} !important; }}
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] li,
    [data-testid="stSidebar"] .stMarkdown {{ color: #FFFFFF !important; }}
    [data-testid="stSidebar"] a {{ color: #66CBE1 !important; }}
    [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.15) !important; }}
    [data-testid="stSidebar"] input {{
        background-color: {_INPUT_BG} !important;
        color: #FFFFFF !important;
        border-color: rgba(255,255,255,0.2) !important;
    }}

    /* ── Top accent bar ── */
    [data-testid="stAppViewContainer"]::before {{
        content: "";
        display: block;
        height: 5px;
        background: linear-gradient(90deg, #01295F 0%, #1E90FF 100%);
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 9999;
    }}

    /* ── Metric values ── */
    [data-testid="stMetricValue"] {{ color: #1E90FF !important; font-weight: 700 !important; }}

    /* ── Active tab ── */
    button[role="tab"][aria-selected="true"] {{
        color: #1E90FF !important;
        border-bottom: 3px solid #1E90FF !important;
        font-weight: 700 !important;
    }}

    /* ── Dividers ── */
    hr {{ border-color: {_HR_COLOR} !important; }}

    /* ── Code blocks ── */
    [data-testid="stCode"] {{
        background-color: {_SECONDARY_BG} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo
    try:
        st.image(
            "https://business.carsales.com.au/wp-content/uploads/2024/02/Carsales-Business_reversed-horizontal.svg",
            width=200,
        )
    except Exception:
        st.markdown(
            '<p style="font-size:1.4rem;font-weight:800;color:#FFFFFF;margin:0;">'
            '<span style="color:#1E90FF;">carsales</span> mediahouse</p>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Dark / light mode toggle
    st.toggle("🌙 Dark mode", key="dark_mode")

    st.markdown("---")

    # How to use guide
    st.markdown("### How to use")

    st.markdown("""
**📄 Single file**
Select a format group and size, upload one creative. Issues are flagged instantly with auto-fix where possible.

---

**📂 Multi-file**
Upload several files at once — each is automatically matched to its spec by pixel dimensions. No zipping needed.

---

**📦 ZIP bundle**
Upload a client ZIP to see which formats are present, which have issues, and which are missing from the set.

---

**🏷 Ad Tag**
Paste an HTML or CM360 tag, or upload a client Excel sheet of tags. Checks the creative and validates UTM parameters on the click URL.

---

**🔧 Auto-fix**
Files marked with 🔧 can be corrected automatically — resize, convert format, compress, or add a 1px border. Download the fixed file instantly.

---

**📋 Client email**
After checking, click *Generate client feedback email* to produce a ready-to-send message listing exactly what needs to be fixed.
""")

    st.markdown("---")
    st.caption(
        f"Specs: [carsales.com.au/ad-specs](https://business.carsales.com.au/ad-specs/) · Jan 2026"
        f"  ·  v{APP_VERSION}"
    )

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="display:flex;align-items:center;gap:18px;margin-bottom:4px;">
        <img src="https://resource.csnstatic.com/retail/globals/logo/v3/carsales.svg"
             style="height:38px;" onerror="this.style.display='none'">
        <h1 style="margin:0;padding:0;font-size:1.8rem;color:#01295F;font-weight:800;">
            Ad Spec Checker
        </h1>
    </div>
    <p style="color:#596169;margin-top:2px;margin-bottom:0;font-size:0.95rem;">
        Check and auto-fix ad creatives against carsales Network specifications.
    </p>
    """,
    unsafe_allow_html=True,
)
st.divider()

_VIDEO_EXTS: frozenset[str] = frozenset({".mp4", ".mov"})


# ── Cached check helpers ──────────────────────────────────────────────────────
# Streamlit re-runs the entire script on every widget change.  Without caching,
# every interaction re-opens images and re-runs all checks from scratch.
# @st.cache_data keys on function arguments (bytes → content hash), so the same
# file + spec returns instantly on all subsequent renders.

@st.cache_data(show_spinner=False)
def _cached_image_checks(file_bytes: bytes, fmt: str, spec_key: str) -> list:
    """Open image and run all checks; result cached by content + spec."""
    spec = FORMATS[spec_key]
    img = Image.open(io.BytesIO(file_bytes))
    img.load()
    return run_all_checks(img, file_bytes, fmt, spec)


@st.cache_data(show_spinner=False)
def _cached_video_checks(file_bytes: bytes, filename: str, spec_key: str) -> list:
    """Run video checks; result cached by content + spec."""
    return run_video_checks(file_bytes, filename, FORMATS[spec_key])


# ── Shared dimension → spec lookup (used in Multi-file and Ad Tag tabs) ───────
_DIM_LOOKUP: dict = {}
for _k, _s in FORMATS.items():
    if _s["dimensions"]:
        _DIM_LOOKUP.setdefault(tuple(_s["dimensions"]), []).append(_k)
    elif _s.get("aspect_ratio") == "1:1":
        _DIM_LOOKUP.setdefault("1:1", []).append(_k)

# ── Campaign check helpers ────────────────────────────────────────────────────
import difflib as _difflib

def _camp_name_score(a: str, b: str) -> float:
    a = re.sub(r'[_\-\s\.]+', ' ', os.path.splitext(a)[0]).lower()
    b = re.sub(r'[_\-\s\.]+', ' ', b).lower()
    a_words, b_words = set(a.split()), set(b.split())
    overlap = len(a_words & b_words) / max(len(b_words), 1)
    seq = _difflib.SequenceMatcher(None, a, b).ratio()
    return max(seq, overlap)

def _match_to_placement(filename: str, img_dims, placements: list, threshold: float = 0.35):
    best_idx, best_score = None, threshold
    for i, p in enumerate(placements):
        s = _camp_name_score(filename, p["name"])
        if s > best_score:
            best_score, best_idx = s, i
    if best_idx is not None:
        return best_idx
    if img_dims:
        for i, p in enumerate(placements):
            spec = FORMATS.get(p.get("spec_key") or "", {})
            if spec.get("dimensions") == img_dims:
                return i
    return None

def _expand_creative_uploads(files) -> list[tuple[str, bytes]]:
    out = []
    for f in files:
        raw = f.read()
        if f.name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for zi in zf.infolist():
                        bn = os.path.basename(zi.filename)
                        if zi.filename.startswith("__MACOSX") or bn.startswith("."):
                            continue
                        if any(bn.lower().endswith(x) for x in (".jpg", ".jpeg", ".png", ".gif", ".mp4", ".mov")):
                            out.append((bn, zf.read(zi)))
            except Exception:
                pass
        else:
            out.append((f.name, raw))
    return out

def _parse_camp_mi(file_bytes: bytes) -> list[dict]:
    import pandas as _pdm
    _SHEET_GROUP = {
        "carsales card": "carsales Card", "card": "carsales Card",
        "discover": "carsales Discover", "carousel": "carsales Carousel",
        "brand terms": "Brand Terms", "unmissable": "Unmissable",
        "in feed": "In Feed Video", "infeed": "In Feed Video",
        "stock boost": "Stock Boost", "guaranteed": "Guaranteed Consideration",
        "new car": "New Car Showroom & Research",
    }
    _KW = {
        "Card Text":                         ["card text (b)", "card text"],
        "Headline Text":                     ["headline text (c)", "headline text"],
        "Headline":                          ["headline text (c)", "headline text", "headline"],
        "Sub-headline Text":                 ["sub-headline", "subheadline"],
        "Body Text":                         ["body text"],
        "Body":                              ["body text", "body"],
        "CTA Text":                          ["cta text (e)", "cta text"],
        "CTA":                               ["cta text (e)", "cta text", "cta"],
        "Link Description (off-network only)": ["link description (d", "link description"],
        "Advertiser Name":                   ["advertiser (a)", "advertiser name", "advertiser"],
        "Advertiser":                        ["advertiser (a)", "advertiser"],
        "Title":                             ["title"],
        "Header Text":                       ["header text"],
        "_dims": ["image size", "dimensions", "size"],
        "_url":  ["click through url", "destination url"],
    }
    try:
        xl = _pdm.ExcelFile(io.BytesIO(file_bytes))
    except Exception:
        return []
    for sheet in xl.sheet_names:
        sl = sheet.lower()
        product_group = next((g for kw, g in _SHEET_GROUP.items() if kw in sl), None)
        copy_limits = COPY_LIMITS.get(product_group, {}) if product_group else {}
        try:
            raw = _pdm.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=None)
        except Exception:
            continue
        header_row, col_map = None, {}
        for ri in range(min(25, len(raw))):
            rv = raw.iloc[ri].fillna("").astype(str).str.lower().tolist()
            found, tmp = 0, {}
            for ci, cell in enumerate(rv):
                for label, kws in _KW.items():
                    if label not in tmp and any(kw in cell for kw in kws):
                        tmp[label] = ci; found += 1
            if found >= 3:
                header_row, col_map = ri, tmp; break
        if header_row is None:
            continue
        copy_fields = list(copy_limits.keys()) if copy_limits else [k for k in col_map if not k.startswith("_")]
        primary_col = next((col_map[f] for f in copy_fields if f in col_map), None)
        if primary_col is None:
            continue
        placements = []
        for ri in range(header_row + 2, len(raw)):
            row = raw.iloc[ri]
            pval = str(row.iloc[primary_col]).strip()
            if not pval or pval.lower() in ("nan", "none", ""):
                continue
            pname = next(
                (str(row.iloc[ci]).strip() for ci in range(min(primary_col, len(row)))
                 if str(row.iloc[ci]).strip() and str(row.iloc[ci]).strip().lower() not in ("nan","none","")),
                f"Row {ri+1}"
            )
            copy_vals = {}
            for f in copy_fields:
                if f in col_map:
                    v = str(row.iloc[col_map[f]]).strip()
                    if v and v.lower() not in ("nan", "none", "0"):
                        copy_vals[f] = v
            dims_str = str(row.iloc[col_map["_dims"]]).strip() if "_dims" in col_map else ""
            url_val  = str(row.iloc[col_map["_url"]]).strip()  if "_url"  in col_map else ""
            if url_val.lower() in ("nan","none",""): url_val = ""
            spec_key = None
            if dims_str:
                dm = re.search(r'(\d+)\s*[xX×*]\s*(\d+)', dims_str)
                if dm:
                    dw, dh = int(dm.group(1)), int(dm.group(2))
                    ms = _DIM_LOOKUP.get((dw, dh), [])
                    if not ms and dw == dh: ms = _DIM_LOOKUP.get("1:1", [])
                    if ms:
                        grp_ms = [m for m in ms if FORMATS[m]["group"] == product_group] if product_group else []
                        spec_key = (grp_ms or ms)[0]
            placements.append({
                "name": pname, "product_group": product_group or "",
                "spec_key": spec_key, "dims_str": dims_str,
                "copy": copy_vals, "copy_limits": copy_limits, "url": url_val,
            })
        if placements:
            return placements
    return []

def _parse_camp_tags(file_bytes: bytes) -> dict:
    import pandas as _pdt
    try:
        raw = _pdt.read_excel(io.BytesIO(file_bytes), header=None)
    except Exception:
        return {}
    hri = 0
    for ri in range(min(25, len(raw))):
        rv = raw.iloc[ri].fillna("").astype(str).str.lower().tolist()
        if any("placement id" in v or "click tag" in v or "impression tag" in v for v in rv):
            hri = ri; break
    df = raw.iloc[hri + 1:].reset_index(drop=True)
    n = len(df.columns)
    hrow = raw.iloc[hri].fillna("").astype(str).tolist()
    def _fc(kws, default):
        for kw in kws:
            for ci, h in enumerate(hrow):
                if kw.lower() in h.lower(): return ci
        return min(default, n - 1)
    idx_name = _fc(["placement name"], 8)
    idx_r    = _fc(["impression tag (image)"], 17)
    idx_v    = _fc(["click tag"], 21)
    def _c(row, idx):
        try:
            v = str(row.iloc[idx]).strip()
            return "" if v.lower() in ("nan","none","<na>","nat") else v
        except Exception: return ""
    out = {}
    for i in range(len(df)):
        row = df.iloc[i]
        name = _c(row, idx_name)
        if not name: continue
        imp = _c(row, idx_r); clk = _c(row, idx_v)
        if imp or clk:
            out[name.strip()] = {"impression_tag": imp, "click_tag_raw": clk}
    return out

tab_camp, tab1, tab2, tab3, tab4 = st.tabs(["Campaign Check", "Single file", "Multi-file", "ZIP bundle", "Ad Tag"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Single file
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

    st.subheader("1 · Select ad format")
    col_group, col_size = st.columns(2)
    with col_group:
        group = st.selectbox("Format group", list(FORMAT_GROUPS.keys()), key="t1_group")
    with col_size:
        format_key = st.selectbox(
            "Size / placement",
            FORMAT_GROUPS[group],
            format_func=lambda k: FORMATS[k]["name"],
            key="t1_format",
        )

    spec = FORMATS[format_key]

    with st.expander("View spec requirements"):
        c1, c2, c3 = st.columns(3)
        if spec.get("is_video"):
            c1.metric("Formats", " / ".join(spec.get("video_formats") or []))
            c2.metric("Max File Size", f"{spec.get('video_max_size_mb')} MB")
            _dur_min = spec.get("video_min_duration_s")
            _dur_max = spec.get("video_max_duration_s")
            c3.metric("Duration", f"{_dur_min}–{_dur_max}s")
            if spec.get("video_aspect_ratios"):
                d1, d2, d3 = st.columns(3)
                d1.metric("Aspect Ratios", " or ".join(spec["video_aspect_ratios"]))
                if spec.get("video_min_px") and spec.get("video_max_px"):
                    d2.metric("Min Resolution", f"{spec['video_min_px']}px")
                    d3.metric("Max Resolution", f"{spec['video_max_px']}px")
                elif spec.get("video_min_resolution") and spec.get("video_max_resolution"):
                    d2.metric("Min Resolution", f"{spec['video_min_resolution'][0]}×{spec['video_min_resolution'][1]}")
                    d3.metric("Max Resolution", f"{spec['video_max_resolution'][0]}×{spec['video_max_resolution'][1]}")
            st.info("Also required (manual verification): H.264 codec · Max 25fps · 720p+ recommended")
        else:
            if spec["dimensions"]:
                c1.metric("Dimensions", f"{spec['dimensions'][0]}×{spec['dimensions'][1]}px")
            elif spec.get("aspect_ratio"):
                c1.metric("Aspect Ratio", spec["aspect_ratio"])
            else:
                c1.metric("Dimensions", "Any")
            c2.metric("Max File Size", f"{spec['max_file_size_kb']} KB")
            c3.metric("Formats", " / ".join(spec["accepted_formats"]))
            if spec.get("animation_max_seconds"):
                d1, d2, d3 = st.columns(3)
                d1.metric("Max Animation", f"{spec['animation_max_seconds']}s")
                d2.metric("Max Plays", str(spec["animation_max_plays"]) if spec.get("animation_max_plays") else "Unlimited")
                d3.metric("Max FPS", str(spec["max_fps"]))
            if spec.get("clear_zone_top_px"):
                st.warning(f"⚠️  Clear zone: top **{spec['clear_zone_top_px']}px** must contain no copy or logos.")
            if spec.get("logo_white_bg_required"):
                st.info("Logo must be on a **white or transparent** background.")

    st.divider()

    # Copy / text field character checks (applies to any product group with defined limits)
    card_text_results: list[dict] = []
    _group = FORMATS.get(format_key, {}).get("group", "")
    _copy_limits = COPY_LIMITS.get(_group, {})
    if _copy_limits:
        step_num = "2"
        st.subheader(f"{step_num} · Copy character limits")

        # ── MI sheet drag-and-drop ─────────────────────────────────────────────
        mi_file = st.file_uploader(
            "Drop MI sheet here to auto-fill (optional)",
            type=["xlsx", "xls"],
            key="mi_upload",
            help="Upload the client's MI Excel sheet to automatically populate copy fields below.",
        )
        if mi_file:
            _mi_key = f"_mi_{mi_file.name}"
            if st.session_state.get("_mi_file_id") != mi_file.name:
                # Parse MI sheet
                import pandas as _pd_mi
                _raw = _pd_mi.read_excel(io.BytesIO(mi_file.read()), header=None, sheet_name=0)

                # Find header row by scanning for copy-field keywords
                _header_row = None
                _col_map = {}
                _KEYWORDS = {
                    "Card Text":           ["card text (b)", "card text"],
                    "Headline Text":       ["headline text (c)", "headline text"],
                    "Headline":            ["headline text (c)", "headline text", "headline"],
                    "Sub-headline Text":   ["sub-headline", "subheadline"],
                    "Body Text":           ["body text"],
                    "Body":                ["body text", "body"],
                    "CTA Text":            ["cta text (e)", "cta text"],
                    "CTA":                 ["cta text (e)", "cta text", "cta"],
                    "Link Description (off-network only)": ["link description (d", "link description"],
                    "Link Description":    ["link description (d", "link description"],
                    "Advertiser Name":     ["advertiser (a)", "advertiser name", "advertiser"],
                    "Advertiser":          ["advertiser (a)", "advertiser"],
                    "Title":               ["title"],
                    "Description (Desktop, all ratios)": ["description"],
                    "Description (Mobile 1:1)":          ["description"],
                    "Hero Image Text Link":              ["hero image text link", "text link"],
                    "Native Tile Headline":              ["native tile headline"],
                    "Native Tile Body Copy":             ["native tile body copy", "native tile body"],
                    "Unmissable Bar Text":               ["unmissable bar text", "unmissable text"],
                    "External Text Link":                ["external text link", "external link"],
                    "Header Text":                       ["header text"],
                    "_url": ["click through url", "click-through url", "destination url"],
                }
                for _ri in range(min(25, len(_raw))):
                    _row_vals = _raw.iloc[_ri].fillna("").astype(str).str.lower().tolist()
                    _found, _tmp = 0, {}
                    for _ci, _cell in enumerate(_row_vals):
                        for _label, _kws in _KEYWORDS.items():
                            if _label not in _tmp and any(_kw in _cell for _kw in _kws):
                                _tmp[_label] = _ci
                                _found += 1
                    if _found >= 3:
                        _header_row = _ri
                        _col_map = _tmp
                        break

                _placements = []
                if _header_row is not None:
                    # Primary copy column (first matching copy field in the limits)
                    _primary_col = next(
                        (_col_map[f] for f in _copy_limits if f in _col_map), None
                    )
                    if _primary_col is not None:
                        for _ri in range(_header_row + 2, len(_raw)):
                            _row = _raw.iloc[_ri]
                            _pval = str(_row.iloc[_primary_col]).strip()
                            if not _pval or _pval.lower() in ("nan", "none", ""):
                                continue
                            # Placement label: leftmost non-empty cell in the row
                            _pname = ""
                            for _ci in range(0, min(_primary_col, len(_row))):
                                _v = str(_row.iloc[_ci]).strip()
                                if _v and _v.lower() not in ("nan", "none", ""):
                                    _pname = _v
                                    break
                            _copy_vals = {}
                            for _field in _copy_limits:
                                if _field in _col_map:
                                    _v = str(_row.iloc[_col_map[_field]]).strip()
                                    if _v and _v.lower() not in ("nan", "none", "0"):
                                        _copy_vals[_field] = _v
                            _url_val = ""
                            if "_url" in _col_map:
                                _url_val = str(_row.iloc[_col_map["_url"]]).strip()
                                if _url_val.lower() in ("nan", "none", ""):
                                    _url_val = ""
                            _placements.append({
                                "label":  _pname or f"Row {_ri + 1}",
                                "copy":   _copy_vals,
                                "url":    _url_val,
                            })

                st.session_state["_mi_placements"] = _placements
                st.session_state["_mi_file_id"]    = mi_file.name
                st.session_state["_mi_selection"]  = None

            _placements = st.session_state.get("_mi_placements", [])
            if not _placements:
                st.warning("Could not detect copy fields in this MI sheet. Check that it matches the standard carsales MI template.")
            else:
                _labels = [p["label"] for p in _placements]
                _sel_idx = st.selectbox(
                    f"Select placement ({len(_placements)} found)",
                    range(len(_labels)),
                    format_func=lambda i: _labels[i],
                    key="mi_placement_select",
                )
                # Pre-fill session state for each copy field when selection changes
                if st.session_state.get("_mi_selection") != _sel_idx:
                    st.session_state["_mi_selection"] = _sel_idx
                    _sel = _placements[_sel_idx]
                    for _field in _copy_limits:
                        st.session_state[f"ct_{_field}"] = _sel["copy"].get(_field, "")
                    if _sel["url"]:
                        st.session_state["_mi_prefill_url"] = _sel["url"]
                    st.rerun()
        else:
            # Clear MI state when file removed
            if st.session_state.get("_mi_file_id"):
                for _k in ["_mi_placements", "_mi_file_id", "_mi_selection", "_mi_prefill_url"]:
                    st.session_state.pop(_k, None)

        # ── Copy field inputs (pre-filled from MI if loaded) ──────────────────
        with st.expander("Copy fields", expanded=bool(mi_file)):
            for field_name, limit in _copy_limits.items():
                val = st.text_input(
                    f"{field_name} (max {limit} chars)",
                    key=f"ct_{field_name}",
                )
                if val:
                    ok = len(val) <= limit
                    card_text_results.append({
                        "name": field_name,
                        "passed": ok,
                        "message": (
                            f"{len(val)}/{limit} chars ✓" if ok
                            else f"{len(val)}/{limit} chars — exceeds limit by {len(val) - limit}"
                        ),
                    })
        upload_label = "3 · Upload creative"
        st.divider()
    else:
        upload_label = "2 · Upload creative"

    st.subheader(upload_label)
    uploaded = st.file_uploader(
        "JPEG, PNG, GIF, MP4 or MOV",
        type=["jpg", "jpeg", "png", "gif", "mp4", "mov"],
        key="t1_upload",
    )

    if not uploaded:
        st.info("Upload a file above to run checks.")
    else:
        file_bytes = uploaded.read()
        _t1_ext = os.path.splitext(uploaded.name)[1].lower()
        _t1_is_video = _t1_ext in _VIDEO_EXTS

        if _t1_is_video and not spec.get("is_video"):
            st.error(
                f"**{uploaded.name}** is a video file, but **{spec['name']}** is an image spec.  "
                "Change the format group to **In Feed Video** or **Outstream Video** and select the Video File spec."
            )
        elif not _t1_is_video and spec.get("is_video"):
            st.error(
                f"**{spec['name']}** requires a video file. Please upload an MP4 or MOV."
            )
        elif _t1_is_video:
            # ── Video file + video spec ──────────────────────────────────────
            st.divider()
            _size_mb = len(file_bytes) / (1024 * 1024)
            _info_col1, _info_col2 = st.columns([1, 2])
            with _info_col1:
                st.markdown("### 🎬")
                st.caption("Video — no preview available")
            with _info_col2:
                st.markdown("**File info**")
                st.write(f"**Name:** `{uploaded.name}`")
                st.write(f"**Format:** `{_t1_ext.lstrip('.').upper()}`")
                st.write(f"**Size:** `{_size_mb:.2f} MB`")

            st.divider()
            _vchks = _cached_video_checks(file_bytes, uploaded.name, format_key)
            _vfailed = [c for c in _vchks if not c.passed]
            _vclient = [c for c in _vfailed if c.needs_client]

            st.subheader("Results")
            if not _vfailed:
                st.success("All checks passed ✓  Creative is ready to submit.")
            elif _vclient:
                st.error(f"{len(_vclient)} issue{'s' if len(_vclient)!=1 else ''} — need client revision")
            else:
                st.warning(f"{len(_vfailed)} issue{'s' if len(_vfailed)!=1 else ''} detected")

            for _c in _vchks:
                _icon = "✅" if _c.passed else "❌"
                st.markdown(f"{_icon} &nbsp; **{_c.name}:** {_c.message}")

            _manual_items = "- **Codec:** H.264 required\n- **Frame rate:** Max 25fps\n- **Resolution:** 720p (1280×720) or above recommended"
            if "Outstream" in spec["name"]:
                _manual_items += "\n- **Audio:** Must be user-initiated (muted by default)"
            st.divider()
            st.subheader("Manual verification checklist")
            st.info(_manual_items)

            if _vfailed:
                st.divider()
                with st.expander("📋 Generate client feedback email", expanded=False):
                    _vid_feedback = [{
                        "filename":       uploaded.name,
                        "spec_name":      spec["name"],
                        "client_checks":  _vclient,
                        "fixable_checks": [],
                    }]
                    feedback_ui(_vid_feedback, "t1_vid")

        # ── Image file + image spec ──────────────────────────────────────────
        load_ok = False
        if (not _t1_is_video) and (not spec.get("is_video")):
            try:
                img = Image.open(io.BytesIO(file_bytes))
                img.load()
                load_ok = True
            except Exception as e:
                st.error(f"Could not open image: {e}")

        if load_ok:
            img_format: str = (
                img.format
                or os.path.splitext(uploaded.name)[1].lstrip(".").upper()
                or "JPEG"
            )

            st.divider()
            prev_col, info_col = st.columns([1, 2])
            with prev_col:
                st.image(img, use_container_width=True)
            with info_col:
                st.markdown("**File info**")
                st.write(f"**Name:** `{uploaded.name}`")
                st.write(f"**Format:** `{img_format}`")
                st.write(f"**Dimensions:** `{img.size[0]}×{img.size[1]}px`")
                st.write(f"**Size:** `{len(file_bytes) / 1024:.1f} KB`")
                if getattr(img, "n_frames", 1) > 1:
                    st.write(f"**Frames:** `{img.n_frames}` (animated GIF)")

            st.divider()

            checks      = _cached_image_checks(file_bytes, img_format, format_key)
            failed      = [c for c in checks if not c.passed]
            fixable     = [c for c in failed if c.fixable]
            tech_client = [c for c in failed if c.needs_client]

            ai_results: list[AICheckResult] = []
            if api_key:
                with st.spinner("Running AI visual checks..."):
                    ai_results = run_ai_checks(img, spec, format_key, api_key)
            ai_client = [r for r in ai_results if not r.passed]

            st.subheader("Results")
            total    = len(checks)
            n_pass   = total - len(failed)
            all_client_issues  = tech_client + list(ai_client)
            card_text_failures = [r for r in card_text_results if not r["passed"]]
            all_clear = (not failed) and (not ai_client) and (not card_text_failures)

            if all_clear:
                st.success(
                    f"All {total} technical checks passed"
                    + (" · AI checks passed" if ai_results else "")
                    + " ✓  Creative is ready to submit."
                )
            elif fixable and not all_client_issues and not card_text_failures:
                st.warning(
                    f"{n_pass}/{total} checks passed — "
                    f"{len(fixable)} issue{'s' if len(fixable) != 1 else ''} can be auto-fixed below."
                )
            else:
                parts = []
                if fixable:
                    parts.append(f"{len(fixable)} auto-fixable")
                if all_client_issues:
                    parts.append(f"{len(all_client_issues)} need client revision")
                if card_text_failures:
                    parts.append(f"{len(card_text_failures)} text field issue{'s' if len(card_text_failures) != 1 else ''}")
                st.error(f"{n_pass}/{total} checks passed — {', '.join(parts)}.")

            st.markdown("**Technical checks:**")
            for c in checks:
                icon = "✅" if c.passed else ("🔧" if c.fixable else "❌")
                st.markdown(f"{icon} &nbsp; **{c.name}:** {c.message}")

            if card_text_results:
                st.markdown("**Text field checks:**")
                for r in card_text_results:
                    icon = "✅" if r["passed"] else "❌"
                    st.markdown(f"{icon} &nbsp; **{r['name']}:** {r['message']}")

            if ai_results:
                st.markdown("**AI visual checks:**")
                for r in ai_results:
                    icon = "✅" if r.passed else "❌"
                    conf = f" *(confidence: {r.confidence})*" if r.confidence != "high" else ""
                    st.markdown(f"{icon} &nbsp; **{r.name}:** {r.message}{conf}")

            st.divider()

            # Auto-fix
            if fixable:
                st.subheader("🔧 Auto-fix")
                names = ", ".join(f"**{c.name}**" for c in fixable)
                st.write(f"The following can be fixed automatically: {names}")
                if st.button("Apply fixes & prepare download", type="primary", key="t1_fix"):
                    with st.spinner("Applying fixes..."):
                        fixed_bytes, new_fmt, applied = apply_fixes(img.copy(), file_bytes, img_format, spec, checks)
                    if applied:
                        st.success(f"Applied: {', '.join(applied)}")
                        final_kb = len(fixed_bytes) / 1024
                        if final_kb > spec["max_file_size_kb"]:
                            st.warning(
                                f"File is still {final_kb:.1f} KB after compression "
                                f"(limit: {spec['max_file_size_kb']} KB). "
                                "The client may need to simplify the artwork further."
                            )
                        ext  = new_fmt.lower().replace("jpeg", "jpg")
                        base = os.path.splitext(uploaded.name)[0]
                        st.download_button(
                            label=f"⬇️  Download fixed file  ({final_kb:.1f} KB)",
                            data=fixed_bytes,
                            file_name=f"{base}_fixed.{ext}",
                            mime=f"image/{ext}",
                            key="t1_download",
                        )
                    else:
                        st.info("No changes were needed.")

            # Client revision list
            if all_client_issues or card_text_failures:
                st.subheader("❌ Needs client revision")
                st.error("The following issues **cannot be auto-fixed** and must be corrected by the client:")
                for c in tech_client:
                    st.markdown(f"• **{c.name}:** {c.message}")
                for r in ai_client:
                    st.markdown(f"• **{r.name}:** {r.message}")
                for r in card_text_failures:
                    st.markdown(f"• **{r['name']}:** {r['message']}")

            # Clear zone reminder
            if spec.get("clear_zone_top_px") and not ai_results:
                st.divider()
                st.warning(
                    f"⚠️  **Clear zone reminder:** The top **{spec['clear_zone_top_px']}px** of this "
                    "carsales Card image must contain no copy or logos."
                )

            # ── Client feedback email ─────────────────────────────────────────
            if failed or ai_client or card_text_failures:
                st.divider()
                with st.expander("📋 Generate client feedback email", expanded=False):
                    # Build text-field issues as pseudo-CheckResult dicts
                    text_client = [
                        type("R", (), {"name": r["name"], "message": r["message"], "fix_action": None})()
                        for r in card_text_failures
                    ]
                    feedback_items = [{
                        "filename":      uploaded.name,
                        "spec_name":     spec["name"],
                        "client_checks": all_client_issues + text_client,
                        "fixable_checks": fixable,
                    }]
                    feedback_ui(feedback_items, "t1")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Multi-file
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Multi-file checker")
    st.caption("Upload multiple creatives at once — each file is automatically matched to its spec by dimensions. No ZIP needed.")

    uploaded_files = st.file_uploader(
        "JPEG, PNG, GIF, MP4 or MOV — select as many files as you like",
        type=["jpg", "jpeg", "png", "gif", "mp4", "mov"],
        accept_multiple_files=True,
        key="mf_upload",
    )

    if not uploaded_files:
        st.info("Upload one or more files above to run checks.")
    else:
        # Dimension → spec lookup (shared module-level dict)
        dim_lookup = _DIM_LOOKUP

        # Load all files — separate image and video files
        file_data = []
        video_data = []
        for uf in uploaded_files:
            fb = uf.read()
            if os.path.splitext(uf.name)[1].lower() in _VIDEO_EXTS:
                video_data.append({"uf": uf, "fb": fb})
                continue
            try:
                im = Image.open(io.BytesIO(fb))
                im.load()
                fmt = im.format or os.path.splitext(uf.name)[1].lstrip(".").upper() or "JPEG"
                w, h = im.size
                matches = dim_lookup.get((w, h), [])
                if not matches and w == h:
                    matches = dim_lookup.get("1:1", [])
                file_data.append({"uf": uf, "fb": fb, "img": im, "fmt": fmt,
                                   "w": w, "h": h, "matches": matches, "error": None})
            except Exception as e:
                file_data.append({"uf": uf, "fb": fb, "img": None, "fmt": None,
                                   "w": None, "h": None, "matches": [], "error": str(e)})

        # Summary strip
        n_matched      = sum(1 for f in file_data if f["matches"])
        n_unrecognised = sum(1 for f in file_data if not f["matches"] and not f["error"])
        n_errors       = sum(1 for f in file_data if f["error"])

        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Files uploaded", len(file_data) + len(video_data))
        sm2.metric("Images matched", n_matched)
        sm3.metric("Unrecognised",   n_unrecognised + n_errors)
        if video_data:
            st.info(f"{len(video_data)} video file{'s' if len(video_data)!=1 else ''} detected — see video checks below.")
        st.divider()

        # Per-file results — also collect issues for feedback
        all_issues_mf: list[dict] = []

        for i, fd in enumerate(file_data):
            uf = fd["uf"]

            if fd["error"]:
                label = f"⚠️  {uf.name} — could not open"
            elif not fd["matches"]:
                label = f"❓  {uf.name} — {fd['w']}×{fd['h']}px — no matching spec"
            elif len(fd["matches"]) == 1:
                label = f"{uf.name} — {FORMATS[fd['matches'][0]]['name']}"
            else:
                label = f"{uf.name} — {fd['w']}×{fd['h']}px — {len(fd['matches'])} possible specs"

            with st.expander(label, expanded=(len(file_data) <= 4)):

                if fd["error"]:
                    st.error(f"Could not open file: {fd['error']}")
                    continue

                prev_col, detail_col = st.columns([1, 2])
                with prev_col:
                    st.image(fd["img"], use_container_width=True)
                    st.caption(f"{fd['w']}×{fd['h']}px · {len(fd['fb'])/1024:.1f} KB · {fd['fmt']}")

                with detail_col:
                    if not fd["matches"]:
                        st.error(f"Dimensions {fd['w']}×{fd['h']}px don't match any known carsales ad spec.")
                        st.caption("Check the file is the correct creative, or use the Single file tab to manually select a format.")
                    else:
                        if len(fd["matches"]) == 1:
                            spec_key = fd["matches"][0]
                            st.markdown(f"**Matched:** {FORMATS[spec_key]['name']}")
                        else:
                            spec_key = st.selectbox(
                                "Multiple specs share these dimensions — select the correct one:",
                                fd["matches"],
                                format_func=lambda k: FORMATS[k]["name"],
                                key=f"mf_spec_{i}",
                            )

                        mf_spec   = FORMATS[spec_key]
                        mf_checks = _cached_image_checks(fd["fb"], fd["fmt"], spec_key)
                        mf_failed  = [c for c in mf_checks if not c.passed]
                        mf_fixable = [c for c in mf_failed if c.fixable]
                        mf_client  = [c for c in mf_failed if c.needs_client]

                        if not mf_failed:
                            st.success("All checks passed ✓")
                        elif mf_fixable and not mf_client:
                            st.warning(f"{len(mf_fixable)} issue{'s' if len(mf_fixable)!=1 else ''} — can be auto-fixed below")
                        else:
                            st.error(f"{len(mf_failed)} issue{'s' if len(mf_failed)!=1 else ''} — {len(mf_client)} need client revision")

                        for c in mf_checks:
                            icon = "✅" if c.passed else ("🔧" if c.fixable else "❌")
                            st.markdown(f"{icon} **{c.name}:** {c.message}")

                        if mf_fixable:
                            if st.button("Apply fixes & download", key=f"mf_fix_{i}", type="primary"):
                                with st.spinner("Applying fixes..."):
                                    fixed_bytes, new_fmt, applied = apply_fixes(
                                        fd["img"].copy(), fd["fb"], fd["fmt"], mf_spec, mf_checks
                                    )
                                if applied:
                                    st.success(f"Applied: {', '.join(applied)}")
                                    final_kb = len(fixed_bytes) / 1024
                                    ext  = new_fmt.lower().replace("jpeg", "jpg")
                                    base = os.path.splitext(uf.name)[0]
                                    st.download_button(
                                        label=f"⬇️  Download fixed  ({final_kb:.1f} KB)",
                                        data=fixed_bytes,
                                        file_name=f"{base}_fixed.{ext}",
                                        mime=f"image/{ext}",
                                        key=f"mf_dl_{i}",
                                    )

                        # Collect for bulk feedback
                        if mf_failed:
                            all_issues_mf.append({
                                "filename":      uf.name,
                                "spec_name":     mf_spec["name"],
                                "client_checks":  mf_client,
                                "fixable_checks": mf_fixable,
                            })

        # ── Bulk client feedback ──────────────────────────────────────────────
        if all_issues_mf:
            st.divider()
            with st.expander("📋 Generate client feedback email", expanded=False):
                st.caption(
                    f"Summarises issues across **{len(all_issues_mf)} file{'s' if len(all_issues_mf)!=1 else ''}** "
                    "that need attention."
                )
                feedback_ui(all_issues_mf, "mf")

        # ── Video files ────────────────────────────────────────────────────────
        _VIDEO_SPEC_CHOICES = [k for k in ["in_feed_video_file", "outstream_video_file"] if k in FORMATS]
        if video_data:
            st.divider()
            st.subheader("Video files")
            for _vi, _vd in enumerate(video_data):
                _vuf = _vd["uf"]; _vfb = _vd["fb"]
                _vext = os.path.splitext(_vuf.name)[1].lower()
                _vfmt = _vext.lstrip(".").upper()
                _vmb  = len(_vfb) / (1024 * 1024)
                with st.expander(f"🎬 {_vuf.name} — {_vfmt}, {_vmb:.2f} MB", expanded=(len(video_data) <= 3)):
                    _default_vspec = "outstream_video_file" if _vext == ".mov" else "in_feed_video_file"
                    _vspec_key = st.selectbox(
                        "Video spec",
                        _VIDEO_SPEC_CHOICES,
                        index=_VIDEO_SPEC_CHOICES.index(_default_vspec) if _default_vspec in _VIDEO_SPEC_CHOICES else 0,
                        format_func=lambda k: FORMATS[k]["name"],
                        key=f"mf_vspec_{_vi}",
                    )
                    _vspec = FORMATS[_vspec_key]
                    _vchks = _cached_video_checks(_vfb, _vuf.name, _vspec_key)
                    _vfailed_mf = [c for c in _vchks if not c.passed]
                    if not _vfailed_mf:
                        st.success("All checks passed ✓")
                    else:
                        st.error(f"{len(_vfailed_mf)} issue{'s' if len(_vfailed_mf)!=1 else ''}")
                    for _vc in _vchks:
                        _vi_icon = "✅" if _vc.passed else "❌"
                        st.markdown(f"{_vi_icon} **{_vc.name}:** {_vc.message}")
                    st.info("Also verify manually: H.264 codec · max 25fps · 720p+ recommended" +
                            (" · audio user-initiated" if "Outstream" in _vspec["name"] else ""))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ZIP bundle
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("ZIP bundle checker")
    st.caption(
        "Upload a ZIP containing ad creatives. "
        "The app matches each file to a spec by dimensions and reports what's present, what has issues, and what's missing."
    )

    selected_groups = st.multiselect(
        "Format groups to check",
        list(FORMAT_GROUPS.keys()),
        default=["Network Display"],
        key="t2_groups",
    )

    zip_upload = st.file_uploader("Upload ZIP file", type=["zip"], key="t2_zip")

    if not zip_upload or not selected_groups:
        st.info("Select at least one format group and upload a ZIP file.")
    else:
        zip_bytes = zip_upload.read()
        IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif"}

        images: dict[str, tuple] = {}
        zip_videos: list[tuple[str, bytes]] = []
        bad_files: list[str] = []

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    basename = os.path.basename(name)
                    if not basename or basename.startswith(".") or basename.startswith("__"):
                        continue
                    if ext in _VIDEO_EXTS:
                        try:
                            zip_videos.append((basename, zf.read(name)))
                        except Exception:
                            bad_files.append(basename)
                        continue
                    if ext not in IMAGE_EXTS:
                        continue
                    try:
                        fb = zf.read(name)
                        im = Image.open(io.BytesIO(fb))
                        im.load()
                        fmt = im.format or ext.lstrip(".").upper() or "JPEG"
                        images[name] = (fb, im, fmt, basename)
                    except Exception:
                        bad_files.append(basename)
            zip_ok = True
        except zipfile.BadZipFile:
            st.error("Could not read the ZIP file — make sure it's a valid .zip archive.")
            zip_ok = False

        if zip_ok:
            if not images:
                st.warning("No image files (JPEG, PNG, GIF) found in the ZIP.")
            else:
                expected_keys: list[str] = []
                for g in selected_groups:
                    expected_keys.extend(FORMAT_GROUPS[g])

                matched: set[str] = set()
                results: dict[str, dict | None] = {}

                for spec_key in expected_keys:
                    s = FORMATS[spec_key]
                    found = None
                    for fname, (fb, im, fmt, basename) in images.items():
                        if fname in matched:
                            continue
                        w, h = im.size
                        if s["dimensions"] is not None and (w, h) == tuple(s["dimensions"]):
                            found = (fname, fb, im, fmt, basename)
                            break
                        elif s.get("aspect_ratio") == "1:1" and s["dimensions"] is None and w == h:
                            found = (fname, fb, im, fmt, basename)
                            break
                    if found:
                        fname, fb, im, fmt, basename = found
                        matched.add(fname)
                        chks = _cached_image_checks(fb, fmt, spec_key)
                        results[spec_key] = {
                            "filename": basename,
                            "checks":   chks,
                            "failed":   [c for c in chks if not c.passed],
                        }
                    else:
                        results[spec_key] = None

                unmatched = [
                    (os.path.basename(f), images[f][1], images[f][0])
                    for f in images if f not in matched
                ]

                found_ok     = [k for k, v in results.items() if v is not None and not v["failed"]]
                found_issues = [k for k, v in results.items() if v is not None and v["failed"]]
                missing      = [k for k, v in results.items() if v is None]

                st.divider()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("✅ Found & valid",    len(found_ok))
                m2.metric("⚠️ Found with issues", len(found_issues))
                m3.metric("❌ Missing",           len(missing))
                m4.metric("📁 Unrecognised",      len(unmatched))
                st.divider()

                for group_name in selected_groups:
                    st.markdown(f"### {group_name}")
                    for spec_key in FORMAT_GROUPS[group_name]:
                        s      = FORMATS[spec_key]
                        result = results.get(spec_key)
                        if result is None:
                            st.markdown(f"❌ &nbsp; **{s['name']}** — *not found in ZIP*")
                        elif not result["failed"]:
                            st.markdown(f"✅ &nbsp; **{s['name']}** — `{result['filename']}` — all checks passed")
                        else:
                            issue_names = ", ".join(c.name for c in result["failed"])
                            st.markdown(f"⚠️ &nbsp; **{s['name']}** — `{result['filename']}` — issues: {issue_names}")
                            with st.expander(f"Details — {result['filename']}"):
                                for c in result["checks"]:
                                    icon = "✅" if c.passed else ("🔧" if c.fixable else "❌")
                                    st.markdown(f"{icon} **{c.name}:** {c.message}")
                    st.write("")

                if unmatched:
                    st.divider()
                    st.markdown("### Unrecognised files")
                    st.caption("These files were in the ZIP but didn't match any expected format in the selected groups.")
                    for basename, im, fb in unmatched:
                        w, h = im.size
                        size_kb = len(fb) / 1024
                        st.markdown(f"• `{basename}` — {w}×{h}px, {size_kb:.1f} KB")

                if bad_files:
                    st.warning(f"Could not open: {', '.join(bad_files)}")

                # ── Client feedback for ZIP results ───────────────────────────

                zip_issues = [
                    {
                        "filename":      results[k]["filename"],
                        "spec_name":     FORMATS[k]["name"],
                        "client_checks":  [c for c in results[k]["failed"] if c.needs_client],
                        "fixable_checks": [c for c in results[k]["failed"] if c.fixable],
                    }
                    for k in found_issues
                ]
                if zip_issues:
                    st.divider()
                    with st.expander("📋 Generate client feedback email", expanded=False):
                        st.caption(
                            f"Summarises issues across **{len(zip_issues)} file{'s' if len(zip_issues)!=1 else ''}** "
                            "found in the ZIP."
                        )
                        feedback_ui(zip_issues, "zp")

                # ── Video files in ZIP ────────────────────────────────────────
                _ZIP_VSPEC_CHOICES = [k for k in ["in_feed_video_file", "outstream_video_file"] if k in FORMATS]
                if zip_videos:
                    st.divider()
                    st.markdown("### Video files in ZIP")
                    for _zvi, (_zvname, _zvbytes) in enumerate(zip_videos):
                        _zvext  = os.path.splitext(_zvname)[1].lower()
                        _zvfmt  = _zvext.lstrip(".").upper()
                        _zvmb   = len(_zvbytes) / (1024 * 1024)
                        with st.expander(f"🎬 {_zvname} — {_zvfmt}, {_zvmb:.2f} MB"):
                            _zvdef = "outstream_video_file" if _zvext == ".mov" else "in_feed_video_file"
                            _zvsk = st.selectbox(
                                "Video spec",
                                _ZIP_VSPEC_CHOICES,
                                index=_ZIP_VSPEC_CHOICES.index(_zvdef) if _zvdef in _ZIP_VSPEC_CHOICES else 0,
                                format_func=lambda k: FORMATS[k]["name"],
                                key=f"zp_vspec_{_zvi}",
                            )
                            _zvchks = _cached_video_checks(_zvbytes, _zvname, _zvsk)
                            _zvfail = [c for c in _zvchks if not c.passed]
                            if not _zvfail:
                                st.success("All checks passed ✓")
                            else:
                                st.error(f"{len(_zvfail)} issue{'s' if len(_zvfail)!=1 else ''}")
                            for _zvc in _zvchks:
                                _zv_icon = "✅" if _zvc.passed else "❌"
                                st.markdown(f"{_zv_icon} **{_zvc.name}:** {_zvc.message}")
                            st.info("Also verify manually: H.264 codec · max 25fps · 720p+ recommended" +
                                    (" · audio user-initiated" if "Outstream" in FORMATS[_zvsk]["name"] else ""))


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Ad Tag
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Ad tag checker")

    tag_mode = st.radio(
        "Input method",
        ["Paste a single tag", "Upload Excel file"],
        horizontal=True,
        key="tag_mode",
    )
    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # EXCEL UPLOAD MODE
    # ══════════════════════════════════════════════════════════════════════════
    if tag_mode == "Upload Excel file":
        st.caption(
            "Upload the CM360 trafficking sheet (.xls or .xlsx). "
            "The app auto-detects the header row and reads "
            "**Placement ID**, **Placement Name**, **Dimensions**, "
            "**Impression Tag (image)** and **Click Tag** automatically."
        )

        xl_file = st.file_uploader("Upload Excel file (.xlsx or .xls)", type=["xlsx", "xls"], key="xl_upload")

        if not xl_file:
            st.info("Upload an Excel file above to begin.")
        else:
            import pandas as pd

            file_bytes = xl_file.read()
            xl_ok = False
            header_row_idx = 0
            df = None
            camp_meta = {"advertiser": "", "campaign": ""}

            # ── Clear overrides when a new file is uploaded ───────────────────
            if st.session_state.get("_xl_file_id") != xl_file.name:
                for _k in ["xl_col_f", "xl_col_i", "xl_col_k", "xl_col_r", "xl_col_v",
                           "_xl_results", "_xl_file_id"]:
                    st.session_state.pop(_k, None)

            try:
                # Scan the first 25 rows (no header) to find the real header row.
                # CM360 exports have ~10 rows of metadata before the column headers.
                raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=None, dtype=str)
                for ri in range(min(25, len(raw))):
                    row_vals = raw.iloc[ri].fillna("").astype(str).str.lower().tolist()
                    if any("placement id" in v or "click tag" in v or "impression tag" in v
                           for v in row_vals):
                        header_row_idx = ri
                        break

                # Pull advertiser/campaign name from CM360 metadata rows (label in col B, value in col I)
                for _ri in range(min(header_row_idx, 15)):
                    _row   = raw.iloc[_ri].fillna("").astype(str).tolist()
                    _label = _row[1].lower() if len(_row) > 1 else ""
                    _val   = _row[8].strip() if len(_row) > 8 else ""
                    if "advertiser name" in _label and _val and _val.lower() != "nan":
                        camp_meta["advertiser"] = _val
                    elif "campaign name" in _label and _val and _val.lower() != "nan":
                        camp_meta["campaign"] = _val

                df = pd.read_excel(
                    io.BytesIO(file_bytes),
                    sheet_name=0,
                    skiprows=header_row_idx,
                    header=0,
                    dtype=str,
                )
                df = df.dropna(how="all").reset_index(drop=True)
                xl_ok = True
            except Exception as e:
                st.error(f"Could not read Excel file: {e}")

            if xl_ok and df is not None:
                n_cols = len(df.columns)

                # ── Auto-detect column positions by header name ───────────────
                def _find_col(keywords: list[str], default_pos: int) -> int:
                    for kw in keywords:
                        for ci, col in enumerate(df.columns):
                            if kw.lower() in str(col).lower():
                                return ci
                    return min(default_pos, n_cols - 1)

                auto_f = _find_col(["placement id"],                  5)
                auto_i = _find_col(["placement name"],                8)
                auto_k = _find_col(["dimensions"],                    10)
                auto_r = _find_col(["impression tag (image)"],        17)
                auto_v = _find_col(["click tag"],                     21)

                # ── Campaign info strip ───────────────────────────────────────
                if camp_meta["advertiser"] or camp_meta["campaign"]:
                    _parts = []
                    if camp_meta["advertiser"]:
                        _parts.append(f"**Advertiser:** {camp_meta['advertiser']}")
                    if camp_meta["campaign"]:
                        _parts.append(f"**Campaign:** {camp_meta['campaign']}")
                    st.info("  ·  ".join(_parts))

                st.caption(
                    f"{len(df)} placements · {n_cols} columns · "
                    f"Header auto-detected at row {header_row_idx + 1}"
                )
                det_names = {
                    "F · Placement ID":      str(df.columns[auto_f]),
                    "I · Name":              str(df.columns[auto_i]),
                    "K · Dimensions":        str(df.columns[auto_k]),
                    "R · Impression tag":    str(df.columns[auto_r]),
                    "V · Click tag":         str(df.columns[auto_v]),
                }
                st.markdown(
                    "  ·  ".join(f"**{role}** → *{name}*" for role, name in det_names.items())
                )

                check_urls_toggle = st.checkbox(
                    "Check click URLs & UTMs (makes a network request per row — slower)",
                    value=True,
                    key="xl_check_urls",
                )

                # ── Column override (only needed if auto-detection was wrong) ─
                with st.expander("📐 Override column positions", expanded=False):
                    st.caption("Numbers are 1-based (A=1, B=2 …). Pre-filled with auto-detected values.")
                    ca, cb, cc, cd, ce = st.columns(5)
                    col_f = ca.number_input("F · Placement ID",   min_value=1, max_value=n_cols, value=auto_f + 1, step=1, key="xl_col_f")
                    col_i = cb.number_input("I · Name",           min_value=1, max_value=n_cols, value=auto_i + 1, step=1, key="xl_col_i")
                    col_k = cc.number_input("K · Dimensions",     min_value=1, max_value=n_cols, value=auto_k + 1, step=1, key="xl_col_k")
                    col_r = cd.number_input("R · Impression tag", min_value=1, max_value=n_cols, value=auto_r + 1, step=1, key="xl_col_r")
                    col_v = ce.number_input("V · Click tag",      min_value=1, max_value=n_cols, value=auto_v + 1, step=1, key="xl_col_v")

                idx_f = int(col_f) - 1
                idx_i = int(col_i) - 1
                idx_k = int(col_k) - 1
                idx_r = int(col_r) - 1
                idx_v = int(col_v) - 1

                # ── Preview ───────────────────────────────────────────────────
                with st.expander("Preview first 5 rows", expanded=False):
                    valid_idxs = [ix for ix in [idx_f, idx_i, idx_k, idx_r, idx_v] if ix < n_cols]
                    preview_df = df.iloc[:5, valid_idxs].copy()
                    preview_df.columns = [
                        lbl for lbl, ix in [
                            ("F · Placement ID",   idx_f),
                            ("I · Name",           idx_i),
                            ("K · Dimensions",     idx_k),
                            ("R · Impression tag", idx_r),
                            ("V · Click tag",      idx_v),
                        ] if ix < n_cols
                    ]
                    st.dataframe(preview_df, use_container_width=True)

                max_rows = min(len(df), 50)
                if len(df) > 50:
                    st.warning(f"File has {len(df)} rows — processing the first 50.")

                if st.button("Run checks on all rows", type="primary", key="xl_run"):
                    xl_results = []
                    prog = st.progress(0)
                    status_ph = st.empty()

                    for i in range(max_rows):
                        row = df.iloc[i]

                        def _cell(idx: int) -> str:
                            try:
                                v = str(row.iloc[idx]).strip()
                                return "" if v.lower() in ("nan", "none", "<na>", "nat") else v
                            except Exception:
                                return ""

                        try:
                            placement_id   = _cell(idx_f)
                            name           = _cell(idx_i) or placement_id or f"Row {i+1}"
                            dimensions_str = _cell(idx_k)
                            impression_tag = _cell(idx_r)
                            click_tag_raw  = _cell(idx_v)

                            status_ph.caption(f"Processing {i+1}/{max_rows}: {name} …")

                            # Skip entirely empty rows
                            if not impression_tag and not click_tag_raw:
                                xl_results.append({
                                    "name": name, "placement_id": placement_id, "skipped": True,
                                })
                                continue

                            # ── Spec matching from col K dimensions ───────────────
                            k_spec_key       = None
                            k_spec_name      = None
                            k_dims           = None
                            is_tracking_pixel = False
                            if dimensions_str:
                                dm = re.search(r'(\d+)\s*[xX×*]\s*(\d+)', dimensions_str)
                                if dm:
                                    kw, kh = int(dm.group(1)), int(dm.group(2))
                                    k_dims = (kw, kh)
                                    # 1×1 is a CM360 impression-tracking pixel, not a creative
                                    if kw == 1 and kh == 1:
                                        is_tracking_pixel = True
                                    else:
                                        k_matches = _DIM_LOOKUP.get((kw, kh), [])
                                        if not k_matches and kw == kh:
                                            k_matches = _DIM_LOOKUP.get("1:1", [])
                                        if k_matches:
                                            k_spec_key  = k_matches[0]
                                            k_spec_name = FORMATS[k_spec_key]["name"]

                            # ── Parse impression tag (col R) ──────────────────────
                            parsed = parse_tag(impression_tag) if impression_tag else None

                            # ── Extract click URL from col V ──────────────────────
                            # Col V may be a bare URL, a full HTML click tag, or a CM360 tag
                            if click_tag_raw:
                                if "<" in click_tag_raw:
                                    _cp = parse_tag(click_tag_raw)
                                    click_url = _cp.click_url or click_tag_raw
                                else:
                                    click_url = click_tag_raw
                            else:
                                click_url = parsed.click_url if parsed else None

                            # ── Creative download + spec check ────────────────────
                            creative_summary = None
                            creative_url = parsed.creative_url if parsed else None

                            if is_tracking_pixel:
                                # 1×1 impression pixels are purely for tracking — no creative to check
                                creative_summary = {
                                    "tracking_pixel": True,
                                    "dims":   "1×1px",
                                    "spec":   "Tracking pixel",
                                    "checks": [], "failed": [], "fixable": [], "client": [],
                                }
                            elif creative_url:
                                dl = download_creative(creative_url)
                                if dl:
                                    try:
                                        c_bytes, c_fmt = dl
                                        c_img = Image.open(io.BytesIO(c_bytes))
                                        c_img.load()
                                        c_w, c_h = c_img.size

                                        # Prefer spec from col K, fall back to image dimensions
                                        if k_spec_key:
                                            c_spec_key = k_spec_key
                                        else:
                                            c_matches = _DIM_LOOKUP.get((c_w, c_h), [])
                                            if not c_matches and c_w == c_h:
                                                c_matches = _DIM_LOOKUP.get("1:1", [])
                                            c_spec_key = c_matches[0] if c_matches else None

                                        if c_spec_key:
                                            c_spec = FORMATS[c_spec_key]
                                            c_chks = _cached_image_checks(c_bytes, c_fmt, c_spec_key)
                                            c_fail = [c for c in c_chks if not c.passed]
                                            c_fix  = [c for c in c_fail if c.fixable]
                                            c_cli  = [c for c in c_fail if c.needs_client]
                                            creative_summary = {
                                                "spec":      c_spec["name"],
                                                "dims":      f"{c_w}×{c_h}px",
                                                "checks":    c_chks,
                                                "failed":    c_fail,
                                                "fixable":   c_fix,
                                                "client":    c_cli,
                                                "bytes":     c_bytes,
                                                "fmt":       c_fmt,
                                                "spec_key":  c_spec_key,
                                            }
                                        else:
                                            creative_summary = {"error": f"Dimensions {c_w}×{c_h}px — no matching carsales spec"}
                                    except Exception as e:
                                        creative_summary = {"error": f"Image error: {e}"}
                                else:
                                    creative_summary = {"error": "Creative download failed — URL may require authentication"}
                            elif parsed and parsed.notes:
                                # JS-rendered tag — no static URL, but we have dimensions from col K
                                creative_summary = {
                                    "js_note":     parsed.notes[0],
                                    "spec":        k_spec_name or "",
                                    "dims":        (f"{k_dims[0]}×{k_dims[1]}px" if k_dims else dimensions_str),
                                    "checks":  [], "failed":  [], "fixable": [], "client": [],
                                }
                            elif k_spec_key:
                                # No tag URL at all, but col K tells us the dimensions
                                creative_summary = {
                                    "dims_only": True,
                                    "spec":      k_spec_name,
                                    "dims":      (f"{k_dims[0]}×{k_dims[1]}px" if k_dims else dimensions_str),
                                    "checks":  [], "failed":  [], "fixable": [], "client": [],
                                }

                            # ── Click URL check ───────────────────────────────────
                            url_summary = None
                            if click_url and check_urls_toggle:
                                url_summary = check_url(click_url)

                            xl_results.append({
                                "name":           name,
                                "placement_id":   placement_id,
                                "skipped":        False,
                                "impression_tag": impression_tag,
                                "click_tag_raw":  click_tag_raw,
                                "parsed":         parsed,
                                "creative":       creative_summary,
                                "url":            url_summary,
                                "click_url":      click_url,
                                "dimensions_str": dimensions_str,
                                "k_spec_name":    k_spec_name,
                            })
                        except Exception as _row_err:
                            xl_results.append({
                                "name":         f"Row {i+1}",
                                "placement_id": "",
                                "skipped":      True,
                                "row_error":    str(_row_err),
                            })
                        finally:
                            prog.progress((i + 1) / max_rows)

                    prog.empty()
                    status_ph.empty()
                    st.session_state["_xl_results"] = xl_results
                    st.session_state["_xl_file_id"] = xl_file.name

                # Clear results if file changed
                if st.session_state.get("_xl_file_id") != xl_file.name:
                    st.session_state.pop("_xl_results", None)

                # ── Show results ──────────────────────────────────────────────
                if "_xl_results" in st.session_state:
                    xl_results = st.session_state["_xl_results"]
                    processed  = [r for r in xl_results if not r.get("skipped")]

                    st.divider()

                    def _creative_status(r):
                        c = r.get("creative")
                        if c is None:                    return "no_url"
                        if "error" in c:                 return "error"
                        if c.get("tracking_pixel"):      return "tracking_pixel"
                        if c.get("js_note"):             return "js_tag"
                        if c.get("dims_only"):           return "dims_only"
                        if c.get("client"):              return "client"
                        if c.get("fixable"):             return "fixable"
                        return "pass"

                    def _url_status(r):
                        u = r.get("url")
                        if u is None:          return "no_url"
                        if not u.resolves:     return "error"
                        if u.is_staging:       return "staging"
                        if u.utm_missing:      return "missing_utm"
                        return "pass"

                    sm1, sm2, sm3, sm4, sm5 = st.columns(5)
                    sm1.metric("Placements",           len(processed))
                    sm2.metric("✅ Creative OK",        sum(1 for r in processed if _creative_status(r) == "pass"))
                    sm3.metric("⚠️ Creative issues",    sum(1 for r in processed if _creative_status(r) in ("client", "fixable", "error")))
                    sm4.metric("✅ UTMs OK",            sum(1 for r in processed if _url_status(r) == "pass"))
                    sm5.metric("❌ UTM issues",         sum(1 for r in processed if _url_status(r) in ("error", "missing_utm", "staging")))

                    # ── Summary table ─────────────────────────────────────────
                    _C_ICON = {
                        "pass": "✅", "fixable": "🔧", "client": "❌",
                        "error": "⚠️", "tracking_pixel": "ℹ️",
                        "js_tag": "ℹ️", "dims_only": "ℹ️", "no_url": "—",
                    }
                    _U_ICON = {
                        "pass": "✅", "missing_utm": "⚠️",
                        "staging": "❌", "error": "❌", "no_url": "—",
                    }
                    import pandas as _pd
                    _tbl_rows = []
                    for _r in processed:
                        _c = _r.get("creative") or {}
                        _u = _r.get("url")
                        _c_st = _creative_status(_r)
                        _u_st = _url_status(_r)
                        _tbl_rows.append({
                            "Placement":    _r["name"],
                            "ID":           _r.get("placement_id", ""),
                            "Dimensions":   _r.get("dimensions_str", ""),
                            "Spec":         _c.get("spec") or _r.get("k_spec_name", ""),
                            "Creative":     _C_ICON.get(_c_st, "—"),
                            "Click URL":    _U_ICON.get(_u_st, "—"),
                            "Missing UTMs": ", ".join(_u.utm_missing) if _u and _u.utm_missing else "",
                        })
                    _summary_df = _pd.DataFrame(_tbl_rows)

                    show_issues_only = st.toggle(
                        "Show issues only",
                        value=False,
                        key="xl_issues_only",
                    )
                    if show_issues_only:
                        _mask = _summary_df["Creative"].isin(["🔧", "❌", "⚠️"]) | \
                                _summary_df["Click URL"].isin(["⚠️", "❌"]) | \
                                (_summary_df["Missing UTMs"] != "")
                        st.dataframe(_summary_df[_mask], use_container_width=True, hide_index=True)
                    else:
                        st.dataframe(_summary_df, use_container_width=True, hide_index=True)

                    st.divider()

                    all_xl_issues = []
                    for row_i, r in enumerate(xl_results):
                        if r.get("row_error"):
                            st.warning(f"⚠️ {r['name']} could not be processed: {r['row_error']}")
                            continue
                        if r.get("skipped"):
                            continue

                        c_st = _creative_status(r)
                        u_st = _url_status(r)

                        # Respect issues-only toggle — skip clean rows in expander view
                        _is_clean = (
                            c_st in ("pass", "tracking_pixel", "dims_only", "js_tag", "no_url")
                            and u_st in ("pass", "no_url")
                        )
                        if show_issues_only and _is_clean:
                            continue

                        if c_st in ("pass", "dims_only", "js_tag", "tracking_pixel") and u_st in ("pass", "no_url"):
                            row_icon = "✅"
                        elif c_st == "client" or u_st in ("error", "staging"):
                            row_icon = "❌"
                        else:
                            row_icon = "⚠️"

                        c = r.get("creative") or {}
                        u = r.get("url")

                        pid_str = f"  ·  ID {r['placement_id']}" if r.get("placement_id") else ""

                        c_label = {
                            "pass":           f"Creative ✅ {c.get('dims','')}",
                            "fixable":        f"Creative 🔧 {c.get('dims','')} — fixable",
                            "client":         f"Creative ❌ {c.get('dims','')} — needs revision",
                            "error":          f"Creative ⚠️ — {c.get('error','')}",
                            "js_tag":         f"Creative ℹ️ JS tag ({c.get('dims','')})".rstrip(" ()"),
                            "dims_only":      f"Creative ℹ️ {c.get('dims','')} — no static URL",
                            "tracking_pixel": "1×1 tracking pixel",
                            "no_url":         "Creative — no URL in tag",
                        }.get(c_st, "")

                        u_label = {
                            "pass":        "URL ✅ UTMs OK",
                            "missing_utm": f"URL ⚠️ missing: {', '.join(u.utm_missing) if u else ''}",
                            "staging":     "URL ❌ staging domain",
                            "error":       f"URL ❌ {f'HTTP {u.status_code}' if u and u.status_code else 'failed'}",
                            "no_url":      "URL — not checked",
                        }.get(u_st, "")

                        label = f"{row_icon}  **{r['name']}**{pid_str} — {c_label}  ·  {u_label}"

                        with st.expander(label, expanded=False):
                            # Dimensions / spec strip
                            if r.get("dimensions_str"):
                                spec_note = f" → **{r['k_spec_name']}**" if r.get("k_spec_name") else " → ⚠️ no matching carsales spec"
                                st.caption(f"📐 Col K dimensions: **{r['dimensions_str']}**{spec_note}")

                            ec1, ec2 = st.columns(2)

                            # ── Creative (col R) ──────────────────────────────
                            with ec1:
                                st.markdown("**Impression tag (col R)**")
                                if c_st == "tracking_pixel":
                                    st.info(
                                        "1×1 CM360 impression-tracking pixel — no creative to check. "
                                        "The actual ad creative is served by the platform separately."
                                    )
                                elif c_st == "no_url":
                                    st.info("No image URL found in impression tag.")
                                elif c_st == "js_tag":
                                    st.info(c.get("js_note", "JS-rendered tag — no static image URL to download."))
                                    if c.get("spec"):
                                        st.caption(f"Spec from col K: {c['spec']}")
                                elif c_st == "dims_only":
                                    st.info("No tag or image URL in col R.")
                                    if c.get("spec"):
                                        st.caption(f"Spec from col K: {c['spec']}")
                                elif c_st == "error":
                                    st.error(c.get("error"))
                                else:
                                    st.markdown(f"Spec: **{c.get('spec','')}**")
                                    for chk in c.get("checks", []):
                                        icon = "✅" if chk.passed else ("🔧" if chk.fixable else "❌")
                                        st.markdown(f"{icon} **{chk.name}:** {chk.message}")

                                    if c.get("fixable"):
                                        fix_key = f"xl_fix_{row_i}"
                                        if st.button("Apply fixes & download", key=fix_key, type="primary"):
                                            with st.spinner("Fixing…"):
                                                spec_obj  = FORMATS[c["spec_key"]]
                                                c_img_fix = Image.open(io.BytesIO(c["bytes"]))
                                                fixed_b, new_fmt, applied = apply_fixes(
                                                    c_img_fix, c["bytes"], c["fmt"], spec_obj, c["checks"]
                                                )
                                            if applied:
                                                st.success(f"Applied: {', '.join(applied)}")
                                                ext = new_fmt.lower().replace("jpeg", "jpg")
                                                st.download_button(
                                                    label=f"⬇️ Download fixed ({len(fixed_b)/1024:.1f} KB)",
                                                    data=fixed_b,
                                                    file_name=f"{r['name'][:30]}_fixed.{ext}",
                                                    mime=f"image/{ext}",
                                                    key=fix_key + "_dl",
                                                )

                            # ── Click tag (col V) ─────────────────────────────
                            with ec2:
                                st.markdown("**Click tag (col V)**")
                                if r.get("click_url"):
                                    st.code(r["click_url"], language=None)
                                if u_st == "no_url":
                                    st.info("No click URL found / URL checking disabled.")
                                elif u is None:
                                    st.info("Not checked.")
                                else:
                                    if u.resolves:
                                        st.markdown(f"✅ Resolves (HTTP {u.status_code})")
                                    else:
                                        st.markdown(f"❌ Did not resolve{f' (HTTP {u.status_code})' if u.status_code else ''}")
                                    if u.is_staging:
                                        st.error("⚠️ Staging URL detected")
                                    if u.final_url:
                                        st.caption(f"→ {u.final_url}")
                                    for utm in REQUIRED_UTMS:
                                        if utm in u.utm_present:
                                            st.markdown(f"✅ `{utm}` = `{u.utm_present[utm]}`")
                                        else:
                                            st.markdown(f"❌ `{utm}` — **missing**")
                                    for utm in RECOMMENDED_UTMS:
                                        if utm in u.utm_present:
                                            st.markdown(f"✅ `{utm}` = `{u.utm_present[utm]}`")
                                        else:
                                            st.markdown(f"⚠️ `{utm}` — not present")
                                    for note in u.notes:
                                        st.caption(note)

                            # Collect for bulk feedback
                            if c_st in ("client", "fixable") or u_st in ("missing_utm", "staging", "error"):
                                all_xl_issues.append({
                                    "filename":       r["name"],
                                    "spec_name":      c.get("spec") or r.get("k_spec_name") or "Unknown spec",
                                    "client_checks":  c.get("client", []),
                                    "fixable_checks": c.get("fixable", []),
                                })

                    # ── Export results as Excel ───────────────────────────────
                    st.divider()
                    import pandas as _pd2
                    _export_rows = []
                    for _r in processed:
                        _c  = _r.get("creative") or {}
                        _u  = _r.get("url")
                        _export_rows.append({
                            "Placement ID":    _r.get("placement_id", ""),
                            "Placement Name":  _r["name"],
                            "Dimensions":      _r.get("dimensions_str", ""),
                            "Spec":            _c.get("spec") or _r.get("k_spec_name", ""),
                            "Creative Status": _creative_status(_r).replace("_", " ").title(),
                            "Click URL":       _r.get("click_url", ""),
                            "URL Resolves":    ("Yes" if _u and _u.resolves else ("No" if _u else "Not checked")),
                            "Staging URL":     ("Yes" if _u and _u.is_staging else ""),
                            "utm_source":      (_u.utm_present.get("utm_source",   "") if _u else ""),
                            "utm_medium":      (_u.utm_present.get("utm_medium",   "") if _u else ""),
                            "utm_campaign":    (_u.utm_present.get("utm_campaign", "") if _u else ""),
                            "utm_content":     (_u.utm_present.get("utm_content",  "") if _u else ""),
                            "Missing UTMs":    (", ".join(_u.utm_missing) if _u and _u.utm_missing else ""),
                        })
                    _export_df  = _pd2.DataFrame(_export_rows)
                    _export_buf = io.BytesIO()
                    _export_df.to_excel(_export_buf, index=False, engine="openpyxl")
                    _fname_stem = (
                        camp_meta.get("advertiser") or
                        camp_meta.get("campaign") or
                        xl_file.name.rsplit(".", 1)[0]
                    )
                    st.download_button(
                        label="⬇️  Download results as Excel",
                        data=_export_buf.getvalue(),
                        file_name=f"{_fname_stem}_ad_check_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="xl_export",
                    )

                    # ── Bulk feedback email ───────────────────────────────────
                    if all_xl_issues:
                        st.divider()
                        with st.expander("📋 Generate client feedback email", expanded=False):
                            st.caption(
                                f"Covers **{len(all_xl_issues)} placement{'s' if len(all_xl_issues)!=1 else ''}** with issues."
                            )
                            _default_campaign = " — ".join(
                                filter(None, [camp_meta.get("advertiser"), camp_meta.get("campaign")])
                            )
                            feedback_ui(all_xl_issues, "xl", default_campaign=_default_campaign)

    # ══════════════════════════════════════════════════════════════════════════
    # SINGLE PASTE MODE
    # ══════════════════════════════════════════════════════════════════════════
    else:
        st.caption(
            "Paste any ad tag — HTML, iFrame, or CM360. "
            "The app extracts the creative URL and click URL, downloads and checks the creative "
            "against carsales specs, and validates UTM parameters."
        )

        tag_input = st.text_area(
            "Paste ad tag",
            height=180,
            placeholder=(
                'Paste your tag here, e.g.\n'
                '<a href="https://example.com/?utm_source=carsales&utm_medium=display&utm_campaign=brand">\n'
                '  <img src="https://cdn.example.com/banner_728x90.jpg" width="728" height="90" border="0">\n'
                '</a>'
            ),
            key="tag_input",
        )

        # Clear stale session state when the tag changes
        if st.session_state.get("_tag_prev") != tag_input:
            st.session_state["_tag_prev"] = tag_input
            for _k in ("_tag_creative_bytes", "_tag_creative_fmt", "_tag_url_result"):
                st.session_state.pop(_k, None)

        if not tag_input.strip():
            st.info("Paste an ad tag above to begin.")
        else:
            parsed = parse_tag(tag_input)

            # ── Tag summary ───────────────────────────────────────────────────
            st.divider()
            tc1, tc2 = st.columns(2)
            tc1.markdown(f"**Tag type:** {parsed.tag_type}")

            if parsed.declared_width and parsed.declared_height:
                dims_str = f"{parsed.declared_width}×{parsed.declared_height}px"
                spec_matches = _DIM_LOOKUP.get((parsed.declared_width, parsed.declared_height), [])
                if not spec_matches and parsed.declared_width == parsed.declared_height:
                    spec_matches = _DIM_LOOKUP.get("1:1", [])
                if spec_matches:
                    tc2.markdown(f"**Declared size:** {dims_str} — matches {len(spec_matches)} spec(s)")
                else:
                    tc2.markdown(f"**Declared size:** {dims_str} — ⚠️ no matching carsales spec")
            else:
                tc2.markdown("**Declared size:** not detected")

            for note in parsed.notes:
                st.warning(note)

            st.divider()
            creative_col, url_col = st.columns(2)

            # ── Creative column ───────────────────────────────────────────────
            with creative_col:
                st.markdown("#### 🖼 Creative")
                if parsed.creative_url:
                    st.code(parsed.creative_url, language=None)
                    if st.button("Download & check creative", key="tag_dl_btn", type="primary"):
                        with st.spinner("Downloading…"):
                            dl = download_creative(parsed.creative_url)
                        if dl:
                            st.session_state["_tag_creative_bytes"] = dl[0]
                            st.session_state["_tag_creative_fmt"]   = dl[1]
                        else:
                            st.error(
                                "Could not download the creative. "
                                "The URL may require authentication or is not a direct image link."
                            )
                            st.session_state.pop("_tag_creative_bytes", None)
                else:
                    st.info("No direct image URL found in tag.")

            # ── Click URL column ──────────────────────────────────────────────
            with url_col:
                st.markdown("#### 🔗 Click URL")
                if parsed.click_url:
                    st.code(parsed.click_url, language=None)
                    if st.button("Check URL & UTMs", key="tag_url_btn", type="primary"):
                        with st.spinner("Checking URL…"):
                            url_result = check_url(parsed.click_url)
                        st.session_state["_tag_url_result"] = url_result
                else:
                    st.info("No click URL found in tag.")

            # ── Creative check results ────────────────────────────────────────
            if "_tag_creative_bytes" in st.session_state:
                st.divider()
                st.markdown("### Creative check results")

                tag_bytes = st.session_state["_tag_creative_bytes"]
                tag_fmt   = st.session_state["_tag_creative_fmt"]

                try:
                    tag_img = Image.open(io.BytesIO(tag_bytes))
                    tag_img.load()
                    img_ok = True
                except Exception as e:
                    st.error(f"Could not open downloaded file as an image: {e}")
                    img_ok = False

                if img_ok:
                    actual_w, actual_h = tag_img.size

                    p1, p2 = st.columns([1, 2])
                    with p1:
                        st.image(tag_img, use_container_width=True)
                        st.caption(f"{actual_w}×{actual_h}px · {len(tag_bytes)/1024:.1f} KB · {tag_fmt}")
                    with p2:
                        # Dimension match warning
                        if parsed.declared_width and parsed.declared_height:
                            if (actual_w, actual_h) != (parsed.declared_width, parsed.declared_height):
                                st.warning(
                                    f"⚠️ Tag declares **{parsed.declared_width}×{parsed.declared_height}px** "
                                    f"but downloaded image is **{actual_w}×{actual_h}px**."
                                )

                        # Spec selection
                        tag_matches = _DIM_LOOKUP.get((actual_w, actual_h), [])
                        if not tag_matches and actual_w == actual_h:
                            tag_matches = _DIM_LOOKUP.get("1:1", [])

                        if not tag_matches:
                            st.error(f"Image dimensions {actual_w}×{actual_h}px don't match any carsales spec.")
                            tag_spec_key = None
                        elif len(tag_matches) == 1:
                            tag_spec_key = tag_matches[0]
                            st.markdown(f"**Matched spec:** {FORMATS[tag_spec_key]['name']}")
                        else:
                            tag_spec_key = st.selectbox(
                                "Multiple specs match — select the correct one:",
                                tag_matches,
                                format_func=lambda k: FORMATS[k]["name"],
                                key="tag_spec_sel",
                            )

                        if tag_spec_key:
                            tag_spec   = FORMATS[tag_spec_key]
                            tag_checks = _cached_image_checks(tag_bytes, tag_fmt, tag_spec_key)
                            tag_failed  = [c for c in tag_checks if not c.passed]
                            tag_fixable = [c for c in tag_failed if c.fixable]
                            tag_client  = [c for c in tag_failed if c.needs_client]

                            if not tag_failed:
                                st.success("All checks passed ✓")
                            elif tag_fixable and not tag_client:
                                st.warning(f"{len(tag_fixable)} issue(s) — can be auto-fixed below")
                            else:
                                st.error(f"{len(tag_failed)} issue(s) — {len(tag_client)} need client revision")

                            for c in tag_checks:
                                icon = "✅" if c.passed else ("🔧" if c.fixable else "❌")
                                st.markdown(f"{icon} **{c.name}:** {c.message}")

                            if tag_fixable:
                                if st.button("Apply fixes & download", key="tag_fix_btn", type="primary"):
                                    with st.spinner("Applying fixes…"):
                                        fixed_bytes, new_fmt, applied = apply_fixes(
                                            tag_img.copy(), tag_bytes, tag_fmt, tag_spec, tag_checks
                                        )
                                    if applied:
                                        st.success(f"Applied: {', '.join(applied)}")
                                        final_kb = len(fixed_bytes) / 1024
                                        ext = new_fmt.lower().replace("jpeg", "jpg")
                                        fname = parsed.creative_url.rsplit("/", 1)[-1].split("?")[0] or "creative"
                                        base  = os.path.splitext(fname)[0]
                                        st.download_button(
                                            label=f"⬇️  Download fixed  ({final_kb:.1f} KB)",
                                            data=fixed_bytes,
                                            file_name=f"{base}_fixed.{ext}",
                                            mime=f"image/{ext}",
                                            key="tag_dl_fixed",
                                        )

                            # Feedback email
                            if tag_failed:
                                st.divider()
                                with st.expander("📋 Generate client feedback email", expanded=False):
                                    fname_display = (
                                        parsed.creative_url.rsplit("/", 1)[-1].split("?")[0]
                                        or "creative"
                                    )
                                    feedback_ui([{
                                        "filename":      fname_display,
                                        "spec_name":     tag_spec["name"],
                                        "client_checks":  tag_client,
                                        "fixable_checks": tag_fixable,
                                    }], "tag")

            # ── Click URL / UTM results ───────────────────────────────────────
            if "_tag_url_result" in st.session_state:
                st.divider()
                st.markdown("### Click URL & UTM results")
                ur = st.session_state["_tag_url_result"]

                if ur.resolves:
                    st.success(f"URL resolves ✓  (HTTP {ur.status_code})")
                else:
                    msg = f"HTTP {ur.status_code}" if ur.status_code else "no response"
                    st.error(f"URL did not resolve — {msg}")

                if ur.final_url:
                    st.caption(f"Redirected to: {ur.final_url}")

                if ur.is_staging:
                    st.error("⚠️ Staging/dev URL detected — must point to production before going live.")

                for note in ur.notes:
                    st.warning(note)

                st.markdown("**UTM parameters**")

                for utm in REQUIRED_UTMS:
                    if utm in ur.utm_present:
                        st.markdown(f"✅ `{utm}` = `{ur.utm_present[utm]}`")
                    else:
                        st.markdown(f"❌ `{utm}` — **missing** (required)")

                for utm in RECOMMENDED_UTMS:
                    if utm in ur.utm_present:
                        st.markdown(f"✅ `{utm}` = `{ur.utm_present[utm]}`")
                    else:
                        st.markdown(f"⚠️ `{utm}` — not present (recommended)")

                extra = {k: v for k, v in ur.utm_present.items()
                         if k not in REQUIRED_UTMS and k not in RECOMMENDED_UTMS}
                for k, v in extra.items():
                    st.markdown(f"ℹ️ `{k}` = `{v}`")

                if not ur.utm_missing:
                    st.success("All required UTM parameters present ✓")
                else:
                    missing_str = ", ".join(f"`{u}`" for u in ur.utm_missing)
                    st.error(f"Missing required UTMs: {missing_str} — ask the client to add these to the click URL.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB CAMP — Campaign Check
# ══════════════════════════════════════════════════════════════════════════════
with tab_camp:
    st.caption("Upload your MI sheet, creative files, and CM360 tags to check everything against each placement in one pass.")

    # ── Step 1: MI Sheet ──────────────────────────────────────────────────────
    st.subheader("1 · MI Sheet")
    camp_mi_up = st.file_uploader("Upload MI sheet (Excel)", type=["xlsx", "xls"], key="camp_mi_up")

    camp_placements: list[dict] = []
    if camp_mi_up:
        if st.session_state.get("_camp_mi_id") != camp_mi_up.name:
            with st.spinner("Parsing MI sheet…"):
                _parsed_pl = _parse_camp_mi(camp_mi_up.read())
            st.session_state["_camp_placements"] = _parsed_pl
            st.session_state["_camp_mi_id"]      = camp_mi_up.name
            st.session_state.pop("_camp_results", None)
        camp_placements = st.session_state.get("_camp_placements", [])
        if not camp_placements:
            st.warning("Could not detect placements — check the MI sheet matches the standard carsales template.")
        else:
            st.success(f"{len(camp_placements)} placements detected")
            _prev_df_rows = []
            for p in camp_placements:
                _copy_ok = all(len(v) <= p["copy_limits"].get(f, 999) for f, v in p["copy"].items())
                _prev_df_rows.append({
                    "Placement":  p["name"],
                    "Spec":       FORMATS[p["spec_key"]]["name"] if p.get("spec_key") else p.get("dims_str") or "—",
                    "Copy":       "✅" if _copy_ok else "❌",
                    "URL":        "✅" if p.get("url") else "—",
                })
            import pandas as _pd_prev
            st.dataframe(_pd_prev.DataFrame(_prev_df_rows), hide_index=True, use_container_width=True)
    else:
        if st.session_state.get("_camp_mi_id"):
            for _k in ["_camp_placements", "_camp_mi_id", "_camp_results"]:
                st.session_state.pop(_k, None)

    st.divider()

    # ── Step 2: Creative assets ───────────────────────────────────────────────
    st.subheader("2 · Creative assets")
    camp_creative_ups = st.file_uploader(
        "Upload creatives or ZIP — images and video supported",
        type=["jpg", "jpeg", "png", "gif", "mp4", "mov", "zip"],
        accept_multiple_files=True,
        key="camp_creatives_up",
    )

    _expanded_files: list[tuple[str, bytes]] = []
    if camp_creative_ups:
        _expanded_files = _expand_creative_uploads(camp_creative_ups)
        st.caption(f"{len(_expanded_files)} creative file{'s' if len(_expanded_files) != 1 else ''} ready")

        # Show auto-match preview against MI placements if available
        if camp_placements:
            _match_rows = []
            for fname, fbytes in _expanded_files:
                try:
                    _img = Image.open(io.BytesIO(fbytes)); _img.load()
                    _dims = (_img.size[0], _img.size[1])
                except Exception:
                    _dims = None
                _midx = _match_to_placement(fname, _dims, camp_placements)
                _match_rows.append({
                    "File":       fname,
                    "Matched to": camp_placements[_midx]["name"] if _midx is not None else "— unmatched",
                })
            import pandas as _pd_match
            st.dataframe(_pd_match.DataFrame(_match_rows), hide_index=True, use_container_width=True)

    st.divider()

    # ── Step 3: Tags (optional) ───────────────────────────────────────────────
    st.subheader("3 · Ad tags — optional")
    camp_tags_up = st.file_uploader("Upload CM360 trafficking sheet", type=["xlsx", "xls"], key="camp_tags_up")
    if camp_tags_up:
        st.caption("Tags will be matched to placements by name and click URLs will be checked.")

    st.divider()

    # ── Run button ────────────────────────────────────────────────────────────
    _can_run = bool(camp_placements and _expanded_files)
    if not camp_placements:
        st.info("Upload an MI sheet in Step 1 to get started.")
    elif not _expanded_files:
        st.info("Upload creative files in Step 2 to run checks.")
    else:
        if st.button("Run campaign checks", type="primary", key="camp_run_btn"):
            _camp_results = []
            _all_files = _expanded_files

            # Parse tags if supplied
            _tag_map = {}
            if camp_tags_up:
                with st.spinner("Parsing tags…"):
                    _tag_map = _parse_camp_tags(camp_tags_up.read())

            # Match each file to a placement (first match wins)
            _file_assign: dict[int, tuple[str, bytes]] = {}
            for _fname, _fbytes in _all_files:
                try:
                    _img = Image.open(io.BytesIO(_fbytes)); _img.load()
                    _dims = (_img.size[0], _img.size[1])
                except Exception:
                    _dims = None
                _midx = _match_to_placement(_fname, _dims, camp_placements)
                if _midx is not None and _midx not in _file_assign:
                    _file_assign[_midx] = (_fname, _fbytes)

            prog_c = st.progress(0)
            stat_c = st.empty()
            for _pi, _p in enumerate(camp_placements):
                stat_c.caption(f"Checking {_pi+1}/{len(camp_placements)}: {_p['name']} …")
                _res = {
                    "name":        _p["name"],
                    "spec_key":    _p.get("spec_key"),
                    "copy_checks": [],
                    "creative":    None,
                    "tag":         None,
                    "creative_file": None,
                }

                # Copy validation
                for _field, _limit in _p["copy_limits"].items():
                    _val = _p["copy"].get(_field, "")
                    if _val:
                        _ok = len(_val) <= _limit
                        _res["copy_checks"].append({
                            "field": _field, "value": _val,
                            "limit": _limit, "count": len(_val), "passed": _ok,
                        })

                # Creative check
                if _pi in _file_assign:
                    _fname, _fbytes = _file_assign[_pi]
                    _res["creative_file"] = _fname
                    if _p.get("spec_key"):
                        _spec = FORMATS[_p["spec_key"]]
                        _fext_c = os.path.splitext(_fname)[1].lower()
                        if _fext_c in _VIDEO_EXTS:
                            try:
                                _chks = _cached_video_checks(_fbytes, _fname, _p["spec_key"])
                                _fail = [c for c in _chks if not c.passed]
                                _res["creative"] = {
                                    "dims":    f"{_fext_c.lstrip('.').upper()} video",
                                    "checks":  _chks,
                                    "failed":  _fail,
                                    "fixable": [],
                                    "client":  [c for c in _fail if c.needs_client],
                                    "bytes":   _fbytes,
                                    "fmt":     _fext_c.lstrip(".").upper(),
                                    "is_video": True,
                                }
                            except Exception as _e:
                                _res["creative"] = {"error": str(_e)}
                        else:
                            try:
                                _img = Image.open(io.BytesIO(_fbytes)); _img.load()
                                _fmt = _img.format or "JPEG"
                                _chks = _cached_image_checks(_fbytes, _fmt, _p["spec_key"])
                                _fail = [c for c in _chks if not c.passed]
                                _res["creative"] = {
                                    "dims":    f"{_img.size[0]}×{_img.size[1]}px",
                                    "checks":  _chks,
                                    "failed":  _fail,
                                    "fixable": [c for c in _fail if c.fixable],
                                    "client":  [c for c in _fail if c.needs_client],
                                    "bytes":   _fbytes,
                                    "fmt":     _fmt,
                                }
                            except Exception as _e:
                                _res["creative"] = {"error": str(_e)}
                    else:
                        _res["creative"] = {"no_spec": True}

                # Tag matching (fuzzy by name)
                _best_tag, _best_ts = None, 0.35
                for _tname, _tdata in _tag_map.items():
                    _ts = _camp_name_score(_p["name"], _tname)
                    if _ts > _best_ts:
                        _best_ts, _best_tag = _ts, _tdata
                if _best_tag:
                    _imp = _best_tag["impression_tag"]
                    _clk = _best_tag["click_tag_raw"]
                    _parsed_t = parse_tag(_imp) if _imp else None
                    if _clk and "<" in _clk:
                        _cp2 = parse_tag(_clk)
                        _click_url = _cp2.click_url or _clk
                    elif _clk:
                        _click_url = _clk
                    else:
                        _click_url = _parsed_t.click_url if _parsed_t else None
                    _url_sum = check_url(_click_url) if _click_url else None
                    _res["tag"] = {
                        "impression_tag": _imp,
                        "click_url":      _click_url,
                        "url_summary":    _url_sum,
                    }

                _camp_results.append(_res)
                prog_c.progress((_pi + 1) / len(camp_placements))

            prog_c.empty(); stat_c.empty()
            st.session_state["_camp_results"] = _camp_results
            st.rerun()

    # ── Results ───────────────────────────────────────────────────────────────
    if "_camp_results" in st.session_state:
        _camp_res = st.session_state["_camp_results"]
        st.divider()
        st.subheader("Results")

        # Status helpers
        def _cst(r):
            c = r.get("creative")
            if c is None:           return "no_file"
            if "error" in c:        return "error"
            if c.get("no_spec"):    return "no_spec"
            if c.get("client"):     return "client"
            if c.get("fixable"):    return "fixable"
            return "pass"

        def _cpst(r):
            if not r["copy_checks"]:    return "no_copy"
            if all(x["passed"] for x in r["copy_checks"]): return "pass"
            return "fail"

        def _tst(r):
            t = r.get("tag")
            if t is None:           return "no_tag"
            u = t.get("url_summary")
            if u is None:           return "tag_only"
            if not u.resolves:      return "error"
            if u.is_staging:        return "staging"
            if u.utm_missing:       return "missing_utm"
            return "pass"

        _C_ICON  = {"pass":"✅","fixable":"🔧","client":"❌","error":"⚠️","no_file":"—","no_spec":"—"}
        _CP_ICON = {"pass":"✅","fail":"❌","no_copy":"—"}
        _T_ICON  = {"pass":"✅","tag_only":"ℹ️","missing_utm":"⚠️","staging":"❌","error":"❌","no_tag":"—"}

        # Summary metrics
        _mc1, _mc2, _mc3, _mc4 = st.columns(4)
        _mc1.metric("Placements",        len(_camp_res))
        _mc2.metric("Creative pass",     sum(1 for r in _camp_res if _cst(r) == "pass"))
        _mc3.metric("Copy pass",         sum(1 for r in _camp_res if _cpst(r) == "pass"))
        _mc4.metric("Tags checked",      sum(1 for r in _camp_res if r.get("tag")))

        # Summary table
        import pandas as _pd_cr
        _sum_rows = [{
            "Placement":  r["name"],
            "Creative":   _C_ICON.get(_cst(r), "?"),
            "Copy":       _CP_ICON.get(_cpst(r), "?"),
            "Tag / URL":  _T_ICON.get(_tst(r), "?"),
            "File":       r.get("creative_file") or "—",
        } for r in _camp_res]
        st.dataframe(_pd_cr.DataFrame(_sum_rows), hide_index=True, use_container_width=True)

        # Issues-only toggle
        _issues_only = st.toggle("Show issues only", value=False, key="camp_issues_only")

        # Per-placement expanders
        for _r in _camp_res:
            _cs, _cps, _ts = _cst(_r), _cpst(_r), _tst(_r)
            _is_clean = _cs in ("pass","no_file","no_spec") and _cps in ("pass","no_copy") and _ts in ("pass","no_tag","tag_only")
            if _issues_only and _is_clean:
                continue

            if _cs == "pass" and _cps in ("pass","no_copy") and _ts in ("pass","no_tag","tag_only"):
                _icon = "✅"
            elif _cs == "client" or _ts in ("error","staging"):
                _icon = "❌"
            else:
                _icon = "⚠️"

            with st.expander(f"{_icon} {_r['name']}", expanded=(_icon != "✅")):
                _ec1, _ec2, _ec3 = st.columns(3)

                # Creative column
                with _ec1:
                    st.markdown("**Creative**")
                    _c = _r.get("creative")
                    if _c is None:
                        st.caption("No file matched")
                    elif "error" in _c:
                        st.error(_c["error"])
                    elif _c.get("no_spec"):
                        f_label = _r.get("creative_file","")
                        st.caption(f"{f_label} — spec not detected")
                    else:
                        st.caption(f"{_r.get('creative_file','')}  ·  {_c.get('dims','')}")
                        if not _c["failed"]:
                            st.success("All checks passed")
                        else:
                            for _chk in _c["failed"]:
                                _fix_icon = "🔧" if _chk.fixable else "❌"
                                st.markdown(f"{_fix_icon} {_chk.message}")
                        if _c.get("is_video"):
                            _spec_nm = FORMATS.get(_r.get("spec_key",""), {}).get("name","")
                            st.caption("Manual: H.264 · max 25fps · 720p+"
                                       + (" · audio user-initiated" if "Outstream" in _spec_nm else ""))
                        if _c.get("fixable"):
                            if st.button("Apply fixes & download", key=f"camp_fix_{_r['name']}"):
                                with st.spinner("Fixing…"):
                                    _fb, _nf, _ap = apply_fixes(
                                        Image.open(io.BytesIO(_c["bytes"])).copy(),
                                        _c["bytes"], _c["fmt"],
                                        FORMATS[_r["spec_key"]], _c["checks"],
                                    )
                                if _ap:
                                    _ext = _nf.lower().replace("jpeg","jpg")
                                    st.download_button(
                                        "⬇️ Download fixed",
                                        data=_fb,
                                        file_name=f"{os.path.splitext(_r.get('creative_file','fixed'))[0]}_fixed.{_ext}",
                                        mime=f"image/{_ext}",
                                        key=f"camp_dl_{_r['name']}",
                                    )

                # Copy column
                with _ec2:
                    st.markdown("**Copy**")
                    if not _r["copy_checks"]:
                        st.caption("No copy fields in MI sheet")
                    else:
                        for _cc in _r["copy_checks"]:
                            _ok = _cc["passed"]
                            _ico = "✅" if _ok else "❌"
                            st.markdown(f"{_ico} **{_cc['field']}**")
                            st.caption(f"  {_cc['value'][:60]}{'…' if len(_cc['value'])>60 else ''}")
                            _over = _cc['count'] - _cc['limit']
                            _char_note = f"  {_cc['count']}/{_cc['limit']} chars" + ("  ✓" if _ok else f"  — over by {_over}")
                            st.caption(_char_note)

                # Tag column
                with _ec3:
                    st.markdown("**Tag / URL**")
                    _t = _r.get("tag")
                    if _t is None:
                        st.caption("No tag matched")
                    else:
                        if _t.get("impression_tag"):
                            st.caption("Impression tag: ✅ present")
                        if _t.get("click_url"):
                            st.caption(f"URL: `{_t['click_url'][:50]}…`" if len(_t.get("click_url","")) > 50 else f"URL: `{_t['click_url']}`")
                        _u = _t.get("url_summary")
                        if _u:
                            if not _u.resolves:
                                st.error("URL does not resolve")
                            elif _u.is_staging:
                                st.error("Staging URL — not production")
                            elif _u.utm_missing:
                                st.warning(f"Missing UTMs: {', '.join(_u.utm_missing)}")
                            else:
                                st.success("URL OK")

        # Export
        st.divider()
        _exp_rows = []
        for _r in _camp_res:
            _row = {
                "Placement":       _r["name"],
                "Creative status": _cst(_r),
                "Creative file":   _r.get("creative_file") or "",
                "Creative dims":   (_r.get("creative") or {}).get("dims",""),
                "Copy status":     _cpst(_r),
            }
            for _cc in _r["copy_checks"]:
                _row[f"Copy: {_cc['field']}"] = _cc["value"]
                _row[f"Copy: {_cc['field']} chars"] = _cc["count"]
            _row["Tag status"]  = _tst(_r)
            _row["Click URL"]   = (_r.get("tag") or {}).get("click_url","")
            _exp_rows.append(_row)
        _exp_buf = io.BytesIO()
        import pandas as _pd_exp
        _pd_exp.DataFrame(_exp_rows).to_excel(_exp_buf, index=False, engine="openpyxl")
        st.download_button(
            "⬇️  Download campaign results as Excel",
            data=_exp_buf.getvalue(),
            file_name="campaign_check_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="camp_export",
        )
