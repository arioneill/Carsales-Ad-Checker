from __future__ import annotations
import io, os, re, zipfile, datetime

# Bump on every release so a deploy can be confirmed at a glance. The build
# stamp below is derived from the file's own mtime, which on Streamlit Cloud is
# the checkout time — so it moves on every deploy without being maintained.
APP_VERSION = "1.9.0"

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from specs import (FORMATS, FORMAT_GROUPS, group_slots, slot_base, slot_label,
                   is_unlimited)
from checker import run_all_checks, run_video_checks, CheckResult, _resize_verdict
from fixer import apply_fixes, compress_to_jpeg, compress_to_png

# ── Constants ──────────────────────────────────────────────────────────────────
_VIDEO_EXTS = frozenset({".mp4", ".mov", ".flv", ".webm"})
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif"})

# Products shown in selector (order matters).
# Unmissable, Sponsored Search, Guaranteed Consideration and Stock Boost are
# absent on purpose — they take no creative file. See _GROUP_ORDER in specs.py.
_SELECTOR_PRODUCTS = [
    "Network Display",
    "Roadblock",
    "carsales Card",
    "Brand Terms",
    "Auto Unmissable High-Impact",
    "carsales Carousel",
    "carsales Discover",
    "In Feed Video",
    "Outstream Video",
    "New Car Showroom & Research",
    "Newsletter",
    "Tile",
    "Push Notifications",
    "XT Social Newsfeed",
    "XT Premium Display",
    "XT Display",
    "XT Pre-Roll Video",
    "XT Connected TV",
]

# Design tokens
_ROYAL  = "#01295F"
_DODGER = "#1E90FF"
_DK_DG  = "#0073E3"
_MINT   = "#00BD9D"
_MINT_T = "#00755F"
_SMOKE  = "#F5F5F5"
_GRAY   = "#757575"
_JET    = "#3A3A3A"
_RED    = "#D93025"
_AMBER  = "#E07B00"
_BORDER = "#DBE3EA"
_HAIR   = "#EEF1F4"

_ACTION_HINTS = {
    "compress":   "Please reduce the file size to meet the limit.",
    "convert":    "Please convert to the required file format.",
    "add_border": "Please add a 1px solid border around the creative.",
    "resize":     "Please supply the creative at the required dimensions.",
}

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Ad Spec Checker — carsales mediahouse",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* Hide Streamlit chrome */
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stHeader"],
footer, #MainMenu { display: none !important; }
[data-testid="stSidebar"] { display: none !important; }

/* Global — target all Streamlit app containers for background */
html, body,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"],
section[data-testid="stSidebar"] ~ div {
    background: #F5F5F5 !important;
}
*, *::before, *::after { font-family: 'Manrope', sans-serif !important; box-sizing: border-box; }
.mono, .mono * { font-family: 'IBM Plex Mono', monospace !important; }

/* Layout */
.block-container {
    padding-top: 0 !important;
    padding-bottom: 48px !important;
    max-width: 100% !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
[data-testid="stAppViewBlockContainer"] {
    padding-top: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}

/* Column layout */
[data-testid="stHorizontalBlock"] {
    gap: 0 !important;
    align-items: flex-start !important;
    padding: 0 32px !important;
}
[data-testid="column"] { padding: 0 10px !important; }
[data-testid="column"]:first-child { padding-left: 0 !important; }
[data-testid="column"]:last-child  { padding-right: 0 !important; }

/* Sticky left column */
[data-testid="stHorizontalBlock"] > div:first-child {
    position: sticky;
    top: 80px;
    align-self: flex-start;
    max-height: calc(100vh - 96px);
    overflow-y: auto;
    scrollbar-width: thin;
}

/* Typography */
h1,h2,h3,h4,h5 { color: #01295F !important; font-weight: 700 !important; }
p, span, label, div { color: #3A3A3A; }

/* Checkboxes */
.stCheckbox { margin-bottom: 2px !important; }
.stCheckbox > label { font-size: 13px !important; font-weight: 500 !important; }

/* ── Drop zone ────────────────────────────────────────────────────────────────
   Streamlit's dropzone is a bare row of [button][hint]. Restack it as a centred
   column: mint glyph, headline, hint, button. Orders are explicit because the
   ::before pseudo-element is always the first flex child.                     */
[data-testid="stFileUploaderDropzone"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0 !important;
    border: 2px dashed #9CC7F5 !important;
    border-radius: 10px !important;
    background: repeating-linear-gradient(
        135deg, #F4FAFF 0px, #F4FAFF 8px, #EAF4FF 8px, #EAF4FF 16px
    ) !important;
    padding: 56px 32px !important;
}

/* Mint→blue rounded-square upload glyph. Inline SVG keeps it independent of
   the Material icon font, which does not always load on Streamlit Cloud. */
[data-testid="stFileUploaderDropzone"]::before {
    content: "";
    order: 1;
    width: 56px;
    height: 56px;
    border-radius: 14px;
    background:
        url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/%3E%3Cpolyline points='17 8 12 3 7 8'/%3E%3Cline x1='12' y1='3' x2='12' y2='15'/%3E%3C/svg%3E")
        center / 26px 26px no-repeat,
        linear-gradient(135deg, #00BD9D 0%, #1E90FF 100%);
    box-shadow: 0 4px 12px rgba(0, 189, 157, 0.28);
}

[data-testid="stFileUploaderDropzoneInstructions"] {
    order: 2;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    margin: 0 !important;
    padding: 0 !important;
}
/* Headline above Streamlit's own size/format hint */
[data-testid="stFileUploaderDropzoneInstructions"]::before {
    content: "Drop your creative files here";
    margin: 20px 0 8px;
    color: #01295F;
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
    color: #757575 !important;
    font-weight: 400 !important;
    font-size: 0.82rem !important;
}

/* Once files are attached Streamlit swaps the instructions out for a chip list
   inside the same section, so drop the big glyph and tighten the padding. */
[data-testid="stFileUploaderDropzone"]:has([data-testid="stFileChips"]) {
    padding: 20px !important;
}
[data-testid="stFileUploaderDropzone"]:has([data-testid="stFileChips"])::before {
    display: none;
}

/* Browse button: relabel and paint it dodger blue.
   Scope by position, not by button kind. Once files are attached the chip row
   adds "Remove <file>" and "Add files" buttons inside the same section, and
   Streamlit reuses the same kind names for them — a kind-based selector paints
   the remove button blue and labels it "Browse files", turning a destructive
   control into a decoy. Only the empty state puts a button in section > span. */
[data-testid="stFileUploaderDropzone"] > span {
    order: 3;
    margin-top: 22px;
}
[data-testid="stFileUploaderDropzone"] > span > button {
    background: #1E90FF !important;
    border: 1px solid #1E90FF !important;
    border-radius: 8px !important;
    padding: 10px 22px !important;
}
[data-testid="stFileUploaderDropzone"] > span > button [data-testid="stMarkdownContainer"],
[data-testid="stFileUploaderDropzone"] > span > button [data-testid="stIconMaterial"] {
    display: none !important;
}
[data-testid="stFileUploaderDropzone"] > span > button::after {
    content: "Browse files";
    color: #ffffff;
    font-size: 0.9rem;
    font-weight: 600;
    white-space: nowrap;
}
[data-testid="stFileUploaderDropzone"] > span > button:hover {
    background: #0073E3 !important;
    border-color: #0073E3 !important;
}

/* Buttons */
.stButton button {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
}
.stButton button[kind="primary"] {
    background: #1E90FF !important;
    border-color: #1E90FF !important;
    color: #fff !important;
}
.stButton button[kind="primary"]:hover {
    background: #0073E3 !important;
    border-color: #0073E3 !important;
}

/* Expanders */
[data-testid="stExpander"] {
    background: #fff !important;
    border: 1px solid #DBE3EA !important;
    border-radius: 8px !important;
    margin-top: 8px !important;
}

/* Inputs */
.stTextInput input, .stTextArea textarea {
    border-radius: 6px !important;
    border-color: #DBE3EA !important;
    font-family: 'Manrope', sans-serif !important;
}

/* Material icons are ligature glyphs: forcing Manrope onto them makes each one
   print its own name ("upload", "keyboard_arrow_down") over the adjacent label.
   Restore the icon font so expander arrows and chip delete buttons draw. */
[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded' !important;
    font-weight: normal !important;
    letter-spacing: normal !important;
    text-transform: none !important;
}

[data-testid="stFileUploader"] .stWidgetLabel,
[data-testid="stFileUploader"] [data-testid="stWidgetLabel"] {
    display: none !important;
}

/* ── Left panel ───────────────────────────────────────────────────────────────
   The Ad-products card is three stacked Streamlit elements (header HTML, the
   checkbox widgets, footer HTML). Collapse the gaps between them and give each
   piece only the borders it needs so they read as one continuous card.       */
/* The whole Ad-products card is one keyed container, so the white background
   and border live on a single element rather than being stitched across the
   header, the rows and the footer. */
.st-key-adproducts_card {
    background: #ffffff !important;
    border: 1px solid #DBE3EA !important;
    border-radius: 10px !important;
    padding: 16px 12px 14px !important;
    /* Streamlit gives a keyed container align-items:start, which shrink-wraps
       every row to its text. The rows must span the card for the asset count
       to sit in its own right-hand column instead of against the name. */
    align-items: stretch !important;
}
/* The key class lands on the vertical block itself, so match it directly as
   well as any nested block. */
.st-key-adproducts_card,
.st-key-adproducts_card [data-testid="stVerticalBlock"] {
    gap: 1px !important;
}
/* Streamlit ships these containers as width:fit-content, so each row would
   shrink to its own text and strand the asset count against the product name
   instead of in a right-hand column. */
[class*="st-key-chk_"] {
    margin: 0 !important;
    width: 100% !important;
}

[class*="st-key-chk_"] [data-testid="stCheckbox"] {
    background: transparent;
    padding: 0;
    margin: 0 !important;
}
[class*="st-key-chk_"] [data-testid="stCheckbox"] > label {
    display: flex !important;
    width: 100%;
    padding: 7px 8px;
    border-radius: 6px;
    align-items: center !important;
}
/* Selected row gets the blue pill treatment */
[class*="st-key-chk_"] [data-testid="stCheckbox"]:has(input:checked) > label {
    background: #EBF3FF;
}
/* Right-aligned per-product asset count (text supplied per row, see app.py) */
[class*="st-key-chk_"] [data-testid="stCheckbox"] > label::after {
    margin-left: auto;
    font-size: 11px;
    font-weight: 700;
    color: #757575;
}
/* Let the label text claim the space between the box and the count, otherwise
   the bolded selected row shrink-wraps and spills onto a second line. */
[class*="st-key-chk_"] [data-testid="stCheckbox"] label > div {
    flex: 1 1 auto;
    min-width: 0;
}
[class*="st-key-chk_"] [data-testid="stCheckbox"] label p {
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #3A3A3A !important;
    line-height: 1.35 !important;
}
[class*="st-key-chk_"] [data-testid="stCheckbox"]:has(input:checked) label p {
    color: #01295F !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="position:sticky;top:0;z-index:9000;height:64px;
            background:{_ROYAL};
            display:flex;align-items:center;justify-content:space-between;
            padding:0 32px;margin-bottom:28px;
            border-bottom:3px solid {_DODGER};">
  <div style="display:flex;align-items:center;gap:14px;">
    <img src="https://business.carsales.com.au/wp-content/uploads/2024/02/Carsales-Business_reversed-horizontal.svg"
         style="height:26px;" onerror="this.style.display='none'">
    <div style="width:1px;height:26px;background:rgba(255,255,255,0.25)"></div>
    <span style="color:#fff;font-weight:700;font-size:1rem;letter-spacing:-0.01em;">
      Ad Spec Checker
    </span>
  </div>
  <div style="display:flex;align-items:center;gap:20px;">
    <a href="https://business.carsales.com.au/ad-specs/" target="_blank"
       style="color:rgba(255,255,255,0.65);font-size:0.78rem;text-decoration:none;font-weight:500;">
      Creative Guidelines · Jan 2026
    </a>
    <div style="width:32px;height:32px;border-radius:50%;background:{_DODGER};
                display:flex;align-items:center;justify-content:center;
                color:#fff;font-weight:700;font-size:0.72rem;">ER</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Inject card styling via JS with MutationObserver ──────────────────────────
components.html("""
<script>
(function() {
  function styleCards() {
    // Match by data-testid OR class (version-safe)
    var sel = [
      '[data-testid="stVerticalBlockBorderWrapper"]',
      '.stVerticalBlockBorderWrapper'
    ].join(',');
    var els = parent.document.querySelectorAll(sel);
    els.forEach(function(el) {
      el.style.backgroundColor = '#ffffff';
      el.style.borderColor     = '#DBE3EA';
      el.style.borderRadius    = '10px';
      el.style.marginBottom    = '12px';
    });
  }
  styleCards();
  var obs = new MutationObserver(styleCards);
  obs.observe(parent.document.body, {childList: true, subtree: true});
})();
</script>
""", height=0)

# ── Session state ──────────────────────────────────────────────────────────────
if "sel_products" not in st.session_state:
    st.session_state.sel_products = ["Network Display"]
if "only_issues" not in st.session_state:
    st.session_state.only_issues = False
# Bumping this changes the uploader's widget key, which is the only way to drop
# every staged file at once — Streamlit has no API to clear a file_uploader.
if "upload_nonce" not in st.session_state:
    st.session_state.upload_nonce = 0

# ── Cached helpers ─────────────────────────────────────────────────────────────
def _find_slot(w: int, h: int, expected_img: list[str], matched: dict,
               exact: bool) -> str | None:
    """First free slot this file fits.

    exact=True matches a declared pixel size; exact=False matches a spec that
    takes any square (logos). Callers run the exact pass first so a sized asset
    is never consumed by a slot that would have accepted anything square.
    """
    for sk in expected_img:
        if sk in matched:
            continue
        s = FORMATS[slot_base(sk)]
        if exact:
            if s["dimensions"] and tuple(s["dimensions"]) == (w, h):
                return sk
        elif (s.get("aspect_ratio") == "1:1" and s["dimensions"] is None
                and w == h):
            return sk
    return None


def _grow_slot(expected: list[str], expected_img: list[str], base: str) -> str:
    """Append another slot to a spec, next to its siblings so results group."""
    siblings = [s for s in expected if slot_base(s) == base]
    new_slot = f"{base}#{len(siblings) + 1}"
    expected.insert(expected.index(siblings[-1]) + 1, new_slot)
    expected_img.append(new_slot)
    return new_slot


def _open_extra_slot(w: int, h: int, expected: list[str],
                     expected_img: list[str], exact: bool = True) -> str | None:
    """Fit another file of a size some selected spec already accepts.

    Slot counts are a minimum, not a quota: a campaign routinely carries
    several creatives per placement — three Cards, two Roadblock sets — and
    every one of them needs checking. Previously the second file of a given
    size found its slot taken and fell through to "skipped", which read as
    though it were the wrong size.
    """
    for base in dict.fromkeys(slot_base(s) for s in expected):
        spec = FORMATS[base]
        if spec.get("is_video"):
            continue
        if exact:
            fits = bool(spec["dimensions"]) and tuple(spec["dimensions"]) == (w, h)
        else:
            fits = (spec.get("aspect_ratio") == "1:1"
                    and spec["dimensions"] is None and w == h)
        if fits:
            return _grow_slot(expected, expected_img, base)
    return None


@st.cache_data(show_spinner=False)
def _img_checks(fb: bytes, fmt: str, spec_key: str) -> list:
    spec = FORMATS[slot_base(spec_key)]
    img  = Image.open(io.BytesIO(fb)); img.load()
    return run_all_checks(img, fb, fmt, spec)

@st.cache_data(show_spinner=False)
def _vid_checks(fb: bytes, fname: str, spec_key: str) -> list:
    return run_video_checks(fb, fname, FORMATS[slot_base(spec_key)])

# ── Dimension → spec lookup ────────────────────────────────────────────────────
_DIM_LOOKUP: dict = {}
for _k, _s in FORMATS.items():
    if _s["dimensions"]:
        _DIM_LOOKUP.setdefault(tuple(_s["dimensions"]), []).append(_k)
    elif _s.get("aspect_ratio") == "1:1":
        _DIM_LOOKUP.setdefault("1:1", []).append(_k)

# ── HTML helpers ───────────────────────────────────────────────────────────────
def _chip(label: str, kind: str) -> str:
    colors = {
        "pass": ("#E3F7F3", _MINT_T),
        "fix":  ("#EBF3FF", _DK_DG),
        "fail": ("#FDECEA", _RED),
        "note": ("#FFF5E6", _AMBER),
        "mute": ("#F5F5F5", _GRAY),
    }
    bg, fg = colors.get(kind, colors["mute"])
    return (f'<span style="display:inline-flex;align-items:center;gap:3px;font-size:11px;'
            f'font-weight:600;padding:3px 9px;border-radius:100px;background:{bg};color:{fg};'
            f'font-family:Manrope,sans-serif;margin:2px 2px 2px 0;">{label}</span>')

def _badge(status: str) -> str:
    cfg = {
        "pass": ("Passed",            _MINT_T, "#E3F7F3"),
        "fix":  ("Auto-fixable",      _DK_DG,  "#EBF3FF"),
        "fail": ("Client fix needed", _RED,    "#FDECEA"),
        "miss": ("Missing",           _AMBER,  "#FFF5E6"),
        "skip": ("Skipped",           _GRAY,   "#F5F5F5"),
    }
    label, fg, bg = cfg.get(status, cfg["skip"])
    return (f'<span style="font-size:11px;font-weight:700;padding:3px 10px;border-radius:4px;'
            f'background:{bg};color:{fg};white-space:nowrap;">{label}</span>')

def _stat_card(n: int, label: str, kind: str) -> str:
    colors = {
        "pass": (_MINT_T, "#E8F9F5", _MINT),
        "fix":  (_DK_DG,  "#EBF3FF", _DODGER),
        "fail": (_RED,    "#FDECEA", _RED),
        "miss": (_AMBER,  "#FFF5E6", _AMBER),
        "skip": (_GRAY,   "#F5F5F5", _GRAY),
    }
    fg, bg, top = colors[kind]
    return (f'<div style="background:{bg};border:1px solid {_BORDER};border-top:3px solid {top};'
            f'border-radius:8px;padding:16px 12px;text-align:center;">'
            f'<div style="font-size:1.6rem;font-weight:800;color:{fg};font-family:Manrope,sans-serif;">{n}</div>'
            f'<div style="font-size:11px;font-weight:600;color:{_GRAY};margin-top:2px;">{label}</div>'
            f'</div>')

def _row_status(checks: list) -> str:
    failed = [c for c in checks if not c.passed]
    if not failed:
        return "pass"
    if any(c.needs_client for c in failed):
        return "fail"
    if any(c.fixable for c in failed):
        return "fix"
    return "fail"

def _build_stamp() -> str:
    """Deploy time, taken from this file's mtime — the checkout time on Cloud."""
    try:
        ts = os.path.getmtime(os.path.abspath(__file__))
        return datetime.datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")
    except OSError:
        return ""

def _ratio_str(w: int, h: int) -> str:
    """Aspect ratio in lowest terms, e.g. 728×90 -> '36:5'."""
    from math import gcd
    g = gcd(w, h) or 1
    return f"{w // g}:{h // g}"

def _dim_str(spec: dict) -> str:
    if spec["dimensions"]:
        return f"{spec['dimensions'][0]}×{spec['dimensions'][1]}"
    return spec.get("aspect_ratio") or "—"

def _checks_chips(checks: list) -> str:
    html = ""
    for c in checks:
        if getattr(c, "advisory", False):
            html += _chip(f"ⓘ {c.name}", "note")
        elif c.passed:
            html += _chip(f"✓ {c.name}", "pass")
        elif c.fixable:
            html += _chip(f"🔧 {c.name}", "fix")
        else:
            html += _chip(f"✗ {c.name}", "fail")
    return html

def _section_label(text: str) -> str:
    return (f'<p style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{_ROYAL};margin:0 0 10px;">{text}</p>')

def _hairline() -> str:
    return f'<div style="height:1px;background:{_HAIR};margin:14px 0;"></div>'

# ── Feedback helpers ───────────────────────────────────────────────────────────
def _build_feedback(items: list[dict], campaign: str = "",
                    skipped: list[dict] | None = None,
                    missing: list[str] | None = None) -> str:
    date_str = datetime.date.today().strftime("%d %B %Y")
    heading  = f"Creative Submission Review{' — ' + campaign if campaign else ''}"
    skipped  = skipped or []
    missing  = missing or []
    has_client  = any(d["client_checks"]  for d in items) or bool(skipped) or bool(missing)
    has_fixable = any(d["fixable_checks"] for d in items)
    L: list[str] = [
        f"Subject: {heading}", f"Date: {date_str}", "",
        "Hi [Name],", "",
        ("Thank you for submitting your ad creatives for the carsales Network. "
         "We have reviewed the files against our specifications and identified the following."
         if has_client else
         "Thank you for submitting your ad creatives for the carsales Network. "
         "We have reviewed the files — all issues have been corrected on your behalf "
         "and no further action is required from you."),
        "",
    ]
    if has_client:
        L += ["─" * 48, "ITEMS REQUIRING YOUR REVISION", "─" * 48, ""]
        for d in items:
            if not d["client_checks"]: continue
            L.append(f"  {d['filename']}  ({d['spec_name']})")
            for c in d["client_checks"]:
                hint = _ACTION_HINTS.get(getattr(c, "fix_action", None) or "", "")
                L.append(f"    • {c.name}: {c.message}" + (f" {hint}" if hint else ""))
            L.append("")
    # Skipped files are the ones most worth spelling out: they are usually a
    # correctly named asset built to the wrong size, so quote the dimensions we
    # actually measured rather than just saying the file was ignored.
    if skipped:
        L += ["─" * 48, "FILES WE COULD NOT MATCH TO A SPEC", "─" * 48, ""]
        for s in skipped:
            dims = f"{s['w']}×{s['h']}px" if s.get("w") else "dimensions unreadable"
            L.append(f"  {s['fname']}  —  supplied at {dims}")
        L += ["",
              "These did not match the dimensions of any placement on this booking.",
              "Please check them against the required sizes listed below and resupply.",
              ""]

    if missing:
        L += ["─" * 48, "ASSETS STILL OUTSTANDING", "─" * 48, ""]
        for name in missing:
            L.append(f"  {name}")
        L.append("")

    if has_fixable:
        L += ["─" * 48, "ITEMS CORRECTED ON YOUR BEHALF", "─" * 48, ""]
        for d in items:
            if not d["fixable_checks"]: continue
            L.append(f"  {d['filename']}  ({d['spec_name']})")
            for c in d["fixable_checks"]:
                L.append(f"    • {c.name}: corrected automatically — no action required.")
            L.append("")
    if has_client:
        L += [
            "Please revise the flagged items and resubmit at your earliest convenience.",
            "If you have any questions, please don't hesitate to reach out.",
        ]
    L += ["", "Kind regards,", "[Your name]",
          "carsales mediahouse", "adops@carsalesmediahouse.com.au"]
    return "\n".join(L)


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
left_col, right_col = st.columns([1, 3], gap="large")

# ── LEFT PANEL ─────────────────────────────────────────────────────────────────
with left_col:
    sel: list[str] = st.session_state.sel_products

    # ── Ad products card ───────────────────────────────────────────────────────
    # One keyed container carries the whole card (white bg, border, radius) via
    # its .st-key-adproducts_card class, so the header, the checkbox rows and
    # the footer do not have to stitch borders together across sibling elements.
    with st.container(key="adproducts_card"):
        st.markdown(
            f'<p style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{_ROYAL};margin:0 0 6px;">Ad products</p>',
            unsafe_allow_html=True,
        )

        # Per-row asset counts, right-aligned via the container class Streamlit
        # derives from each widget key (.st-key-<key>).
        count_css = ""
        for prod in _SELECTOR_PRODUCTS:
            if prod not in FORMAT_GROUPS:
                continue
            key   = "chk_" + re.sub(r"[^a-z0-9]+", "_", prod.lower()).strip("_")
            # Every count is a minimum now, so no product carries a "+" badge —
            # the note under Required assets says so once for all of them.
            count = str(len(group_slots(prod)))
            count_css += (
                f'.st-key-{key} [data-testid="stCheckbox"] > label::after'
                f'{{content:"{count}";}}'
            )
            new_val = st.checkbox(prod, value=prod in sel, key=key)
            if new_val and prod not in sel:
                sel.append(prod)
            elif not new_val and prod in sel:
                sel.remove(prod)

        st.markdown(f"<style>{count_css}</style>", unsafe_allow_html=True)

        total_assets = sum(len(group_slots(p)) for p in sel if p in FORMAT_GROUPS)
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;'
            f'border-top:1px solid {_HAIR};padding-top:12px;margin-top:10px;">'
            f'<span style="font-size:11px;color:{_GRAY};">'
            f'{len(sel)} product{"s" if len(sel)!=1 else ""} selected</span>'
            f'<span style="font-size:11px;font-weight:700;color:{_ROYAL};">'
            f'{total_assets} assets</span></div>',
            unsafe_allow_html=True,
        )

    # ── Required assets card (pure HTML — inline bg always works) ──────────────
    assets_html = ""
    all_fmts: set[str] = set()
    all_max_kb: list[int] = []
    all_anim_s: list[int] = []
    all_fps:    list[int] = []

    for prod in sel:
        if prod not in FORMAT_GROUPS:
            continue
        assets_html += (
            f'<p style="font-size:11px;font-weight:700;color:{_ROYAL};margin:10px 0 4px;">'
            f'{prod}</p>'
        )
        for i, slot in enumerate(group_slots(prod)):
            s     = FORMATS[slot_base(slot)]
            dim   = _dim_str(s)
            full  = slot_label(slot)
            short = full.split("—", 1)[-1].strip() if "—" in full else full
            dot   = _MINT if i == 0 else _RED
            all_fmts.update(f.upper() for f in (s.get("accepted_formats") or []))
            all_fmts.update(f.upper() for f in (s.get("video_formats") or []))
            if s.get("max_file_size_kb"):      all_max_kb.append(s["max_file_size_kb"])
            if s.get("animation_max_seconds"): all_anim_s.append(s["animation_max_seconds"])
            if s.get("max_fps"):               all_fps.append(s["max_fps"])
            assets_html += (
                f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0;">'
                f'<div style="width:8px;height:8px;border-radius:50%;background:{dot};'
                f'flex-shrink:0;"></div>'
                f'<span style="font-family:IBM Plex Mono,monospace;font-size:11px;'
                f'color:{_GRAY};flex-shrink:0;min-width:52px;">{dim}</span>'
                f'<span style="font-size:11px;color:{_JET};">{short}</span>'
                f'</div>'
            )
    if assets_html:
        assets_html += (
            f'<div style="font-size:10px;color:{_GRAY};font-style:italic;'
            f'margin:10px 0 0;line-height:1.5;">'
            f'Minimum set per product. Extra creatives at any size listed above '
            f'are checked too — upload the whole campaign.</div>'
        )

    fmt_str  = ", ".join(sorted(all_fmts)) if all_fmts else "—"
    size_str = f"{max(all_max_kb)} KB" if all_max_kb else "No limit"
    anim_parts = []
    if all_anim_s: anim_parts.append(f"{max(all_anim_s)}s")
    if all_fps:    anim_parts.append(f"{max(all_fps)}fps")
    anim_str   = " · ".join(anim_parts) if anim_parts else "Static only"

    footer = (
        f'<div style="border-top:1px solid {_HAIR};margin-top:12px;padding-top:10px;">'
        f'<div style="display:flex;justify-content:space-between;margin:4px 0;">'
        f'<span style="font-size:11px;color:{_GRAY};">Formats</span>'
        f'<span style="font-size:11px;font-weight:600;color:{_JET};">{fmt_str}</span></div>'
        f'<div style="display:flex;justify-content:space-between;margin:4px 0;">'
        f'<span style="font-size:11px;color:{_GRAY};">Max file size</span>'
        f'<span style="font-size:11px;font-weight:600;color:{_JET};">{size_str}</span></div>'
        f'<div style="display:flex;justify-content:space-between;margin:4px 0;">'
        f'<span style="font-size:11px;color:{_GRAY};">Animation</span>'
        f'<span style="font-size:11px;font-weight:600;color:{_JET};">{anim_str}</span></div>'
        f'</div>'
    ) if sel else ""

    st.markdown(
        f'<div style="background:#fff;border:1px solid {_BORDER};border-radius:10px;'
        f'padding:16px 20px;margin-top:12px;">'
        f'<p style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
        f'text-transform:uppercase;color:{_ROYAL};margin:0 0 8px;">Required assets</p>'
        + (assets_html + footer if sel else
           '<p style="font-size:12px;color:#757575;margin:0;">Select a product above.</p>')
        + f'</div>'
        + f'<p style="font-size:10px;color:{_GRAY};margin-top:8px;">'
          f'v{APP_VERSION}'
          + (f' &nbsp;·&nbsp; build {_build_stamp()}' if _build_stamp() else '')
          + f'</p>',
        unsafe_allow_html=True,
    )


# ── RIGHT PANEL ────────────────────────────────────────────────────────────────
with right_col:
    # Context heading
    if len(sel) == 0:
        heading = "Select products to begin"
        subtext  = "Choose one or more ad products from the left panel, then upload your files."
    elif len(sel) == 1:
        heading = f"Check a {sel[0].lower()} campaign"
        subtext  = (f"Drop the full set of creative for a {sel[0]} booking. "
                    "Every file is matched to a spec and checked against carsales Network specs.")
    else:
        heading = f"Check {len(sel)} products"
        subtext  = ("Drop creative files for all selected products. "
                    "Each file is matched to its spec by dimensions automatically.")

    st.markdown(
        f'<h2 style="margin:0 0 4px;font-size:1.4rem;">{heading}</h2>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="color:{_GRAY};margin:0 0 20px;font-size:0.875rem;">{subtext}</p>',
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "",
        type=["jpg", "jpeg", "png", "gif", "mp4", "mov", "flv", "webm", "zip"],
        accept_multiple_files=True,
        key=f"main_upload_{st.session_state.upload_nonce}",
        label_visibility="collapsed",
    )

    if uploaded:
        n = len(uploaded)
        if st.button(f"✕  Clear all {n} file{'s' if n != 1 else ''}", key="clear_all"):
            st.session_state.upload_nonce += 1
            st.rerun()

    st.markdown(
        f'<p style="text-align:center;font-size:12px;color:{_GRAY};margin:8px 0 0;">'
        f'Dimensions &nbsp;·&nbsp; File format &nbsp;·&nbsp; File size '
        f'&nbsp;·&nbsp; Animation &amp; loops &nbsp;·&nbsp; 1px border</p>',
        unsafe_allow_html=True,
    )

    # ── Empty state ────────────────────────────────────────────────────────────
    if not uploaded or not sel:
        if not sel:
            st.info("← Select at least one product from the left panel.")
        else:
            st.markdown(f"""
            <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:16px;">
                {''.join(
                    f'<div style="text-align:center;padding:14px 8px;background:#fff;'
                    f'border:1px solid {_BORDER};border-radius:8px;">'
                    f'<div style="font-size:11px;font-weight:600;color:{_ROYAL};">{name}</div>'
                    f'</div>'
                    for name in ["Dimensions","File format","File size","Animation & loops","1px border"]
                )}
            </div>
            """, unsafe_allow_html=True)

    # ── Results state ──────────────────────────────────────────────────────────
    else:
        # Build the expected slot list — one entry per file the client owes us,
        # so a spec wanting three files (carousel cards) contributes three.
        expected: list[str] = []
        for p in sel:
            if p in FORMAT_GROUPS:
                expected.extend(group_slots(p))

        expected_img = [k for k in expected if not FORMATS[slot_base(k)].get("is_video")]
        expected_vid = [k for k in expected if FORMATS[slot_base(k)].get("is_video")]

        # Read all files (expand ZIPs)
        all_files: list[tuple[str, bytes]] = []
        for uf in uploaded:
            raw = uf.read()
            if uf.name.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                        for zi in zf.infolist():
                            bn = os.path.basename(zi.filename)
                            if not bn or bn.startswith(".") or zi.filename.startswith("__MACOSX"):
                                continue
                            if any(bn.lower().endswith(x) for x in _IMAGE_EXTS | _VIDEO_EXTS):
                                all_files.append((bn, zf.read(zi)))
                except Exception:
                    pass
            else:
                all_files.append((uf.name, raw))

        # Match files to expected specs
        matched: dict[str, dict] = {}    # spec_key -> result dict
        matched_fnames: set[str] = set()
        unmatched_imgs: list[dict] = []

        for fname, fb in all_files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _IMAGE_EXTS:
                continue
            try:
                img = Image.open(io.BytesIO(fb)); img.load()
                fmt = img.format or ext.lstrip(".").upper() or "JPEG"
                w, h = img.size
                # Exact dimensions win over "any square" at every stage, or a
                # 627×627 carousel card would be swallowed by the logo slot
                # above it. Growing an exactly sized spec also beats handing the
                # file to a free logo slot.
                best = (_find_slot(w, h, expected_img, matched, exact=True)
                        or _open_extra_slot(w, h, expected, expected_img, exact=True)
                        or _find_slot(w, h, expected_img, matched, exact=False)
                        or _open_extra_slot(w, h, expected, expected_img, exact=False))
                if best:
                    checks = _img_checks(fb, fmt, best)
                    matched[best] = {
                        "filename": fname, "fb": fb, "img": img, "fmt": fmt,
                        "checks": checks, "status": _row_status(checks), "is_video": False,
                    }
                    matched_fnames.add(fname)
                else:
                    unmatched_imgs.append({"fname": fname, "w": w, "h": h})
            except Exception:
                unmatched_imgs.append({"fname": fname, "w": None, "h": None})

        unmatched_vids: list[dict] = []
        vid_pool = list(expected_vid)
        for fname, fb in all_files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _VIDEO_EXTS or fname in matched_fnames:
                continue
            mb = len(fb) / (1024 * 1024)
            best_vsk = next((k for k in vid_pool if k not in matched), None)
            if best_vsk is None and vid_pool:
                # Extra cuts go to the first video spec on the booking. With two
                # video products selected that is a guess, but checking against
                # a plausible spec beats discarding the file as unmatched.
                best_vsk = _grow_slot(expected, vid_pool, slot_base(vid_pool[0]))
            if best_vsk:
                checks = _vid_checks(fb, fname, best_vsk)
                matched[best_vsk] = {
                    "filename": fname, "fb": fb, "img": None,
                    "fmt": ext.lstrip(".").upper(), "mb": mb,
                    "checks": checks, "status": _row_status(checks), "is_video": True,
                }
                matched_fnames.add(fname)
            else:
                unmatched_vids.append({"fname": fname, "mb": mb, "ext": ext})

        # Counts
        passed_keys  = [k for k, v in matched.items() if v["status"] == "pass"]
        fix_keys     = [k for k, v in matched.items() if v["status"] == "fix"]
        fail_keys    = [k for k, v in matched.items() if v["status"] == "fail"]
        missing_keys = [k for k in expected if k not in matched]
        skip_count   = len(unmatched_imgs) + len(unmatched_vids)

        # Stat cards
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:20px 0 16px;">
            {_stat_card(len(passed_keys),  "Passed",            "pass")}
            {_stat_card(len(fix_keys),     "Auto-fixable",      "fix")}
            {_stat_card(len(fail_keys),    "Client fix needed", "fail")}
            {_stat_card(len(missing_keys), "Missing",           "miss")}
            {_stat_card(skip_count,        "Skipped",           "skip")}
        </div>
        """, unsafe_allow_html=True)

        only_issues = st.checkbox(
            "Show issues only",
            value=st.session_state.only_issues,
            key="only_issues_chk",
        )
        st.session_state.only_issues = only_issues

        st.markdown(_hairline(), unsafe_allow_html=True)
        st.markdown(_section_label("Results"), unsafe_allow_html=True)

        # Bar colour map
        _bc = {"pass": _MINT, "fix": _DODGER, "fail": _RED, "miss": _AMBER, "skip": _GRAY}

        # ── Matched file rows ──────────────────────────────────────────────────
        for sk in expected:
            if sk not in matched:
                continue
            r      = matched[sk]
            status = r["status"]
            if only_issues and status == "pass":
                continue
            spec   = FORMATS[slot_base(sk)]
            fname  = r["filename"]
            checks = r["checks"]
            bc     = _bc[status]
            chips  = _checks_chips(checks)
            dim    = _dim_str(spec)
            failed_msgs = " · ".join(c.message for c in checks
                                     if not c.passed and not getattr(c, "advisory", False))
            note_msgs   = " · ".join(c.message for c in checks
                                     if getattr(c, "advisory", False))

            st.markdown(f"""
            <div style="display:flex;gap:14px;background:#fff;border:1px solid {_BORDER};
                        border-left:3px solid {bc};border-radius:8px;padding:14px 16px;
                        margin-bottom:8px;align-items:flex-start;">
              <div style="flex-shrink:0;width:64px;min-height:48px;background:{_HAIR};
                          border:1px dashed {_BORDER};border-radius:6px;
                          display:flex;align-items:center;justify-content:center;
                          font-family:'IBM Plex Mono',monospace;font-size:9px;
                          color:{_GRAY};text-align:center;line-height:1.4;padding:4px;">{dim}</div>
              <div style="flex:1;min-width:0;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap;">
                  <span style="font-family:'IBM Plex Mono',monospace;font-size:13px;
                               font-weight:500;color:{_JET};">{fname}</span>
                  {_badge(status)}
                </div>
                <div style="font-size:11px;color:{_GRAY};margin-bottom:8px;">{slot_label(sk)}</div>
                <div style="display:flex;flex-wrap:wrap;gap:0;">{chips}</div>
                {f'<div style="font-size:11px;color:{_RED};margin-top:6px;">{failed_msgs}</div>' if failed_msgs else ''}
                {f'<div style="font-size:11px;color:{_GRAY};margin-top:6px;">ⓘ {note_msgs}</div>' if note_msgs else ''}
              </div>
            </div>
            """, unsafe_allow_html=True)

            # Auto-fix button
            fixable = [c for c in checks if c.fixable]
            if fixable and not r.get("is_video"):
                if st.button("Apply fixes & download", key=f"fix_{sk}", type="primary"):
                    with st.spinner("Applying fixes..."):
                        fixed_bytes, new_fmt, applied = apply_fixes(
                            r["img"].copy(), r["fb"], r["fmt"], spec, checks
                        )
                    if applied:
                        # Only call it fixed if it actually came in under the
                        # limit — a file still over spec must not look resolved.
                        _lim = spec.get("max_file_size_kb")
                        _kb  = len(fixed_bytes) / 1024
                        if _lim is not None and _kb > _lim:
                            st.warning(
                                f"Partly fixed: {', '.join(applied)}. "
                                f"This still needs to go back to the client."
                            )
                        else:
                            st.success(f"Fixed: {', '.join(applied)}")
                        ext_ = new_fmt.lower().replace("jpeg", "jpg")
                        base = os.path.splitext(fname)[0]
                        st.download_button(
                            f"⬇ Download fixed  ({_kb:.1f} KB)",
                            fixed_bytes, f"{base}_fixed.{ext_}",
                            f"image/{ext_}", key=f"dl_{sk}",
                        )

        # ── Missing rows ───────────────────────────────────────────────────────
        for sk in missing_keys:
            spec = FORMATS[slot_base(sk)]
            dim  = _dim_str(spec)
            st.markdown(f"""
            <div style="display:flex;gap:14px;background:#FFFDF5;border:1px solid {_BORDER};
                        border-left:3px solid {_AMBER};border-radius:8px;padding:14px 16px;
                        margin-bottom:8px;align-items:flex-start;opacity:0.85;">
              <div style="flex-shrink:0;width:64px;min-height:48px;background:{_HAIR};
                          border:1px dashed {_BORDER};border-radius:6px;
                          display:flex;align-items:center;justify-content:center;
                          font-family:'IBM Plex Mono',monospace;font-size:9px;
                          color:{_GRAY};text-align:center;line-height:1.4;padding:4px;">{dim}</div>
              <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                  <span style="font-size:13px;color:{_GRAY};font-style:italic;">No file uploaded</span>
                  {_badge("miss")}
                </div>
                <div style="font-size:11px;color:{_GRAY};">{slot_label(sk)}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        # ── Skipped rows ───────────────────────────────────────────────────────
        if not only_issues:
            for item in unmatched_imgs:
                fname = item["fname"]
                w, h  = item.get("w"), item.get("h")
                dim   = f"{w}×{h}" if w else "?"
                st.markdown(f"""
                <div style="display:flex;gap:14px;background:#FAFAFA;border:1px solid {_HAIR};
                            border-left:3px solid {_GRAY};border-radius:8px;padding:14px 16px;
                            margin-bottom:8px;align-items:flex-start;opacity:0.7;">
                  <div style="flex-shrink:0;width:64px;min-height:48px;background:{_HAIR};
                              border:1px dashed {_BORDER};border-radius:6px;
                              display:flex;align-items:center;justify-content:center;
                              font-family:'IBM Plex Mono',monospace;font-size:9px;
                              color:{_GRAY};text-align:center;padding:4px;">{dim}</div>
                  <div style="flex:1;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                      <span style="font-family:'IBM Plex Mono',monospace;font-size:13px;
                                   color:{_GRAY};">{fname}</span>
                      {_badge("skip")}
                    </div>
                    <div style="font-size:11px;color:{_GRAY};">
                      Dimensions don't match any spec in selected products
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

            for item in unmatched_vids:
                st.markdown(f"""
                <div style="display:flex;gap:14px;background:#FAFAFA;border:1px solid {_HAIR};
                            border-left:3px solid {_GRAY};border-radius:8px;padding:14px 16px;
                            margin-bottom:8px;align-items:flex-start;opacity:0.7;">
                  <div style="flex-shrink:0;width:64px;min-height:48px;background:{_HAIR};
                              border:1px dashed {_BORDER};border-radius:6px;
                              display:flex;align-items:center;justify-content:center;
                              font-size:9px;color:{_GRAY};text-align:center;padding:4px;">
                              {item['ext'].lstrip('.').upper()}</div>
                  <div style="flex:1;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                      <span style="font-family:'IBM Plex Mono',monospace;font-size:13px;
                                   color:{_GRAY};">{item['fname']}</span>
                      {_badge("skip")}
                    </div>
                    <div style="font-size:11px;color:{_GRAY};">
                      No video spec selected — add In Feed Video or Outstream Video
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

        # ── Footer banner + feedback email ────────────────────────────────────
        has_issues = fail_keys or fix_keys or missing_keys or unmatched_imgs
        if has_issues:
            parts = []
            if fail_keys:
                parts.append(f"{len(fail_keys)} file{'s' if len(fail_keys)!=1 else ''} need client revision")
            if fix_keys:
                parts.append(f"{len(fix_keys)} auto-fixable")
            if missing_keys:
                parts.append(f"{len(missing_keys)} missing")
            if unmatched_imgs:
                parts.append(f"{len(unmatched_imgs)} unmatched")

            st.markdown(f"""
            <div style="background:{_ROYAL};border-radius:10px;padding:20px 24px;
                        margin-top:20px;display:flex;align-items:center;
                        justify-content:space-between;gap:20px;flex-wrap:wrap;">
              <div>
                <div style="color:#fff;font-weight:700;font-size:0.95rem;margin-bottom:3px;">
                  {" · ".join(parts)}
                </div>
                <div style="color:rgba(255,255,255,0.6);font-size:0.8rem;">
                  Generate a feedback email to send to the client.
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            issues_for_client = [
                {
                    "filename":       matched[k]["filename"],
                    "spec_name":      slot_label(k),
                    "client_checks":  [c for c in matched[k]["checks"] if c.needs_client],
                    "fixable_checks": [c for c in matched[k]["checks"] if c.fixable],
                }
                for k in (fail_keys + fix_keys)
            ]

            with st.expander("📋 Generate client feedback email", expanded=False):
                campaign = st.text_input(
                    "Campaign name (optional)",
                    placeholder="e.g. Toyota Corolla — Aug 2026",
                    key="campaign_name",
                )
                email_text = _build_feedback(
                    issues_for_client,
                    campaign,
                    skipped=unmatched_imgs,
                    missing=[
                        f"{slot_label(k)}  —  {_dim_str(FORMATS[slot_base(k)])}"
                        for k in missing_keys
                    ],
                )
                _bk = "email_base_v2"
                _ak = "email_textarea_v2"
                if st.session_state.get(_bk) != email_text:
                    st.session_state[_bk] = email_text
                    st.session_state[_ak] = email_text
                edited = st.text_area("Edit before sending:", height=380, key=_ak)
                safe = edited.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
                components.html(
                    f"""<button onclick="navigator.clipboard.writeText(`{safe}`).then(()=>{{
                            this.textContent='✓ Copied!';this.style.background='#01295F';
                            setTimeout(()=>{{this.textContent='📋 Copy to clipboard';
                                this.style.background='#1E90FF';}},2500);
                        }})" style="background:#1E90FF;color:#fff;border:none;padding:10px 24px;
                                    border-radius:6px;cursor:pointer;font-weight:600;font-size:0.87rem;
                                    font-family:Manrope,sans-serif;">📋 Copy to clipboard</button>""",
                    height=52,
                )

    # ── Quick resize ───────────────────────────────────────────────────────────
    # Standalone scaler. Same rule as the auto-fix: pure scaling only, so a file
    # is never cropped or stretched to fit. Upscaling is refused by default but
    # can be overridden, since it only costs sharpness.
    st.markdown(_hairline(), unsafe_allow_html=True)

    with st.expander("📐  Quick resize — scale a file to a target size"):
        _known = sorted({tuple(s["dimensions"]) for s in FORMATS.values()
                         if s["dimensions"]})
        _opts  = [f"{w}×{h}" for w, h in _known] + ["Custom…"]
        choice = st.selectbox("Target size", _opts, key="qr_target")

        if choice == "Custom…":
            k1, k2 = st.columns(2)
            tw = k1.number_input("Width (px)",  1, 10_000, 300, key="qr_w")
            th = k2.number_input("Height (px)", 1, 10_000, 250, key="qr_h")
        else:
            tw, th = (int(v) for v in choice.split("×"))

        allow_up = st.checkbox(
            "Allow upscaling", value=False, key="qr_up",
            help="Off by default — enlarging a file cannot add detail, so the "
                 "result is softer than a correctly sized original.",
        )

        st.caption(
            f"Scaling only. A file whose shape differs from {tw}×{th} is "
            "rejected rather than cropped or stretched."
        )

        zfiles = st.file_uploader(
            "Files to resize",
            type=["jpg", "jpeg", "png", "gif"],
            accept_multiple_files=True,
            key="quick_resize",
        )

        for uf in zfiles or []:
            raw = uf.read()
            try:
                zimg = Image.open(io.BytesIO(raw)); zimg.load()
            except Exception:
                st.warning(f"{uf.name} — could not be read as an image.")
                continue

            w, h = zimg.size
            ok, code, why = _resize_verdict(
                w, h, tw, th, getattr(zimg, "n_frames", 1) > 1
            )
            if not ok and code == "upscale" and allow_up:
                ok, why = True, ""

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
                f'margin:12px 0 4px;">'
                f'<span style="font-family:IBM Plex Mono,monospace;font-size:13px;'
                f'color:{_JET};">{uf.name}</span>'
                f'<span style="font-size:12px;color:{_GRAY};">{w}×{h} → </span>'
                f'<span style="font-size:12px;font-weight:700;'
                f'color:{_MINT_T if ok else _RED};">'
                f'{f"{tw}×{th}" if ok else "not resized"}</span></div>',
                unsafe_allow_html=True,
            )

            if not ok:
                st.caption(
                    why + ("  Tick “Allow upscaling” to override."
                           if code == "upscale" else
                           f"  {uf.name} is {_ratio_str(w, h)}; "
                           f"{tw}×{th} is {_ratio_str(tw, th)}.")
                )
                continue

            out_png = zimg.mode in ("RGBA", "LA", "PA") or (zimg.format == "PNG")
            scaled  = zimg.convert("RGBA" if out_png else "RGB")
            scaled  = scaled.resize((tw, th), Image.LANCZOS)

            buf = io.BytesIO()
            if out_png:
                scaled.save(buf, format="PNG", optimize=True)
                out_ext, mime = "png", "image/png"
            else:
                scaled.save(buf, format="JPEG", quality=92, optimize=True)
                out_ext, mime = "jpg", "image/jpeg"
            out_bytes = buf.getvalue()

            base = os.path.splitext(uf.name)[0]
            st.download_button(
                f"⬇  Download  {base}_{tw}x{th}.{out_ext}  "
                f"({len(out_bytes)/1024:.1f} KB)",
                out_bytes, f"{base}_{tw}x{th}.{out_ext}", mime,
                key=f"qr_dl_{uf.name}",
            )

    # ── Quick compress ─────────────────────────────────────────────────────────
    # Standalone shrink tool: no product selection, no spec matching, no report.
    # For when you already know a file is just over the limit.
    st.markdown(_hairline(), unsafe_allow_html=True)

    with st.expander("🗜  Quick compress — shrink a file without running a check"):
        c1, c2 = st.columns([1, 1])
        with c1:
            target_kb = st.number_input(
                "Target size (KB)", min_value=5, max_value=10_000,
                value=80, step=5, key="qc_target",
                help="80 KB is the carsales Network display limit.",
            )
        with c2:
            keep_png = st.checkbox(
                "Keep PNG (preserves transparency)", value=False, key="qc_png",
                help="Leave off to output JPEG, which compresses far harder. "
                     "Turn on only if the creative needs a transparent background.",
            )

        qfiles = st.file_uploader(
            "Files to compress",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="quick_compress",
        )

        for uf in qfiles or []:
            raw = uf.read()
            before_kb = len(raw) / 1024
            try:
                qimg = Image.open(io.BytesIO(raw)); qimg.load()
            except Exception:
                st.warning(f"{uf.name} — could not be read as an image.")
                continue

            if keep_png:
                out_bytes, out_ext = compress_to_png(qimg, target_kb), "png"
            else:
                out_bytes, out_ext = compress_to_jpeg(qimg, target_kb), "jpg"

            after_kb = len(out_bytes) / 1024
            hit      = after_kb <= target_kb
            saved    = (1 - after_kb / before_kb) * 100 if before_kb else 0

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
                f'margin:10px 0 4px;">'
                f'<span style="font-family:IBM Plex Mono,monospace;font-size:13px;'
                f'color:{_JET};">{uf.name}</span>'
                f'<span style="font-size:12px;color:{_GRAY};">'
                f'{before_kb:.1f} KB → </span>'
                f'<span style="font-size:12px;font-weight:700;'
                f'color:{_MINT_T if hit else _AMBER};">{after_kb:.1f} KB</span>'
                f'<span style="font-size:11px;color:{_GRAY};">({saved:.0f}% smaller)</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if not hit:
                st.caption(
                    f"Could not reach {target_kb} KB without dropping below usable "
                    f"quality — this is as small as it goes"
                    + (" in PNG. Untick “Keep PNG” to compress harder." if keep_png else ".")
                )

            base = os.path.splitext(uf.name)[0]
            st.download_button(
                f"⬇  Download  {base}_compressed.{out_ext}",
                out_bytes, f"{base}_compressed.{out_ext}",
                f"image/{'png' if out_ext == 'png' else 'jpeg'}",
                key=f"qc_dl_{uf.name}",
            )
