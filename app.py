from __future__ import annotations
import io, os, zipfile, datetime

APP_VERSION = "1.6.0"

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from specs import FORMATS, FORMAT_GROUPS
from checker import run_all_checks, run_video_checks, CheckResult
from fixer import apply_fixes

# ── Constants ──────────────────────────────────────────────────────────────────
_VIDEO_EXTS = frozenset({".mp4", ".mov", ".flv", ".webm"})
_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif"})

# Products shown in selector (order matters)
_SELECTOR_PRODUCTS = [
    "Network Display",
    "Roadblock",
    "carsales Card",
    "Brand Terms",
    "Auto Unmissable High-Impact",
    "Unmissable",
    "carsales Carousel",
    "carsales Discover",
    "In Feed Video",
    "Outstream Video",
    "New Car Showroom & Research",
    "Sponsored Search",
    "Newsletter",
    "Tile",
    "Push Notifications",
    "Guaranteed Consideration",
    "Stock Boost",
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

/* File uploader */
[data-testid="stFileUploaderDropzone"] {
    border: 2px dashed #9CC7F5 !important;
    border-radius: 10px !important;
    background: repeating-linear-gradient(
        135deg, #F4FAFF 0px, #F4FAFF 8px, #EAF4FF 8px, #EAF4FF 16px
    ) !important;
    padding: 40px 32px !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
    color: #01295F !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
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

/* File uploader: hide label above dropzone — cover all Streamlit label selectors */
[data-testid="stFileUploader"] .stWidgetLabel,
[data-testid="stFileUploader"] [data-testid="stWidgetLabel"],
[data-testid="stFileUploader"] label,
[data-testid="stFileUploader"] > div > label,
[data-testid="stFileUploader"] > div:first-child p {
    display: none !important;
    height: 0 !important;
    overflow: hidden !important;
}

/* Left panel white cards */
[data-testid="stVerticalBlockBorderWrapper"],
.stVerticalBlockBorderWrapper,
div[style*="border: 1px solid rgba(49, 51, 63"] {
    background: #ffffff !important;
    border-color: #DBE3EA !important;
    border-radius: 10px !important;
    margin-bottom: 12px !important;
}

/* Left column itself — fallback white card if above selectors miss */
[data-testid="column"]:first-child > div {
    background: #ffffff;
    border: 1px solid #DBE3EA;
    border-radius: 10px;
    overflow: hidden;
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

# ── Cached helpers ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _img_checks(fb: bytes, fmt: str, spec_key: str) -> list:
    spec = FORMATS[spec_key]
    img  = Image.open(io.BytesIO(fb)); img.load()
    return run_all_checks(img, fb, fmt, spec)

@st.cache_data(show_spinner=False)
def _vid_checks(fb: bytes, fname: str, spec_key: str) -> list:
    return run_video_checks(fb, fname, FORMATS[spec_key])

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

def _dim_str(spec: dict) -> str:
    if spec["dimensions"]:
        return f"{spec['dimensions'][0]}×{spec['dimensions'][1]}"
    return spec.get("aspect_ratio") or "—"

def _checks_chips(checks: list) -> str:
    html = ""
    for c in checks:
        if c.passed:
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
def _build_feedback(items: list[dict], campaign: str = "") -> str:
    date_str = datetime.date.today().strftime("%d %B %Y")
    heading  = f"Creative Submission Review{' — ' + campaign if campaign else ''}"
    has_client  = any(d["client_checks"]  for d in items)
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
    total_assets = sum(len(FORMAT_GROUPS[p]) for p in sel if p in FORMAT_GROUPS)

    # ── Card 1: Ad products ────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'margin-bottom:12px;">'
            f'<p style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{_ROYAL};margin:0;">Ad products</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for prod in _SELECTOR_PRODUCTS:
            if prod not in FORMAT_GROUPS:
                continue
            count = len(FORMAT_GROUPS[prod])
            new_val = st.checkbox(
                f"{prod}",
                value=prod in sel,
                key=f"chk_{prod}",
            )
            if new_val and prod not in sel:
                sel.append(prod)
            elif not new_val and prod in sel:
                sel.remove(prod)

        st.markdown(
            f'<div style="display:flex;justify-content:space-between;'
            f'border-top:1px solid {_HAIR};margin-top:10px;padding-top:10px;">'
            f'<span style="font-size:11px;color:{_GRAY};">'
            f'{len(sel)} product{"s" if len(sel)!=1 else ""} selected</span>'
            f'<span style="font-size:11px;font-weight:700;color:{_ROYAL};">'
            f'{total_assets} assets</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Card 2: Required assets ────────────────────────────────────────────────
    if sel:
        with st.container(border=True):
            st.markdown(
                f'<p style="font-size:10px;font-weight:700;letter-spacing:0.1em;'
                f'text-transform:uppercase;color:{_ROYAL};margin:0 0 12px;">Required assets</p>',
                unsafe_allow_html=True,
            )

            # Collect union of formats + specs for the summary footer
            all_fmts: set[str] = set()
            all_max_kb: list[int] = []
            all_anim_s: list[int] = []
            all_fps: list[int] = []

            for prod in sel:
                if prod not in FORMAT_GROUPS:
                    continue
                st.markdown(
                    f'<p style="font-size:11px;font-weight:700;color:{_ROYAL};'
                    f'margin:8px 0 4px;">{prod}</p>',
                    unsafe_allow_html=True,
                )
                for sk in FORMAT_GROUPS[prod]:
                    s = FORMATS[sk]
                    dim = _dim_str(s)
                    short = s["name"].split("—")[-1].strip() if "—" in s["name"] else s["name"]
                    # Collect for summary
                    all_fmts.update(s.get("allowed_formats", []))
                    if s.get("max_file_size_kb"):
                        all_max_kb.append(s["max_file_size_kb"])
                    if s.get("max_animation_s"):
                        all_anim_s.append(s["max_animation_s"])
                    if s.get("max_frame_rate"):
                        all_fps.append(s["max_frame_rate"])
                    # Dot colour: green if first of a product, red otherwise
                    dot_color = _MINT if sk == FORMAT_GROUPS[prod][0] else _RED
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0;">'
                        f'<div style="width:8px;height:8px;border-radius:50%;'
                        f'background:{dot_color};flex-shrink:0;"></div>'
                        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;'
                        f'color:{_GRAY};flex-shrink:0;min-width:52px;">{dim}</span>'
                        f'<span style="font-size:11px;color:{_JET};">{short}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Spec summary footer
            fmt_str  = ", ".join(sorted(all_fmts)) if all_fmts else "—"
            size_str = f"{max(all_max_kb)} KB" if all_max_kb else "No limit"
            anim_parts = []
            if all_anim_s:
                anim_parts.append(f"{max(all_anim_s)}s")
            if all_fps:
                anim_parts.append(f"{max(all_fps)}fps")
            anim_str = " · ".join(anim_parts) if anim_parts else "Static only"

            st.markdown(
                f'<div style="border-top:1px solid {_HAIR};margin-top:12px;padding-top:10px;">'
                f'<div style="display:flex;justify-content:space-between;margin:4px 0;">'
                f'<span style="font-size:11px;color:{_GRAY};">Formats</span>'
                f'<span style="font-size:11px;font-weight:600;color:{_JET};">{fmt_str}</span>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;margin:4px 0;">'
                f'<span style="font-size:11px;color:{_GRAY};">Max file size</span>'
                f'<span style="font-size:11px;font-weight:600;color:{_JET};">{size_str}</span>'
                f'</div>'
                f'<div style="display:flex;justify-content:space-between;margin:4px 0;">'
                f'<span style="font-size:11px;color:{_GRAY};">Animation</span>'
                f'<span style="font-size:11px;font-weight:600;color:{_JET};">{anim_str}</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        f'<p style="font-size:10px;color:{_GRAY};margin-top:8px;">v{APP_VERSION}</p>',
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
        key="main_upload",
        label_visibility="collapsed",
    )

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
        # Build expected spec set
        expected: list[str] = []
        for p in sel:
            if p in FORMAT_GROUPS:
                expected.extend(FORMAT_GROUPS[p])

        expected_img = [k for k in expected if not FORMATS[k].get("is_video")]
        expected_vid = [k for k in expected if FORMATS[k].get("is_video")]

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
                best = None
                for sk in expected_img:
                    if sk in matched:
                        continue
                    s = FORMATS[sk]
                    if s["dimensions"] and tuple(s["dimensions"]) == (w, h):
                        best = sk; break
                    if s.get("aspect_ratio") == "1:1" and s["dimensions"] is None and w == h:
                        best = sk; break
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
            spec   = FORMATS[sk]
            fname  = r["filename"]
            checks = r["checks"]
            bc     = _bc[status]
            chips  = _checks_chips(checks)
            dim    = _dim_str(spec)
            failed_msgs = " · ".join(c.message for c in checks if not c.passed)

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
                <div style="font-size:11px;color:{_GRAY};margin-bottom:8px;">{spec['name']}</div>
                <div style="display:flex;flex-wrap:wrap;gap:0;">{chips}</div>
                {f'<div style="font-size:11px;color:{_RED};margin-top:6px;">{failed_msgs}</div>' if failed_msgs else ''}
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
                        st.success(f"Fixed: {', '.join(applied)}")
                        ext_ = new_fmt.lower().replace("jpeg", "jpg")
                        base = os.path.splitext(fname)[0]
                        st.download_button(
                            f"⬇ Download fixed  ({len(fixed_bytes)/1024:.1f} KB)",
                            fixed_bytes, f"{base}_fixed.{ext_}",
                            f"image/{ext_}", key=f"dl_{sk}",
                        )

        # ── Missing rows ───────────────────────────────────────────────────────
        for sk in missing_keys:
            spec = FORMATS[sk]
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
                <div style="font-size:11px;color:{_GRAY};">{spec['name']}</div>
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
        has_issues = fail_keys or fix_keys or missing_keys
        if has_issues:
            parts = []
            if fail_keys:
                parts.append(f"{len(fail_keys)} file{'s' if len(fail_keys)!=1 else ''} need client revision")
            if fix_keys:
                parts.append(f"{len(fix_keys)} auto-fixable")
            if missing_keys:
                parts.append(f"{len(missing_keys)} missing")

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
                    "spec_name":      FORMATS[k]["name"],
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
                email_text = _build_feedback(issues_for_client, campaign)
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
