from __future__ import annotations
import io
import os
import zipfile
import datetime

APP_VERSION = "1.2.0"

import re
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from specs import FORMATS, FORMAT_GROUPS, CARD_TEXT_LIMITS, COPY_LIMITS
from checker import run_all_checks, CheckResult
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
    "resize":     "Please resize to the correct dimensions.",
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

    # Editable preview — user can tweak before sending
    edited = st.text_area(
        "Edit before sending:",
        value=text,
        height=420,
        key=f"{key_prefix}_textarea",
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

# ── Shared dimension → spec lookup (used in Multi-file and Ad Tag tabs) ───────
_DIM_LOOKUP: dict = {}
for _k, _s in FORMATS.items():
    if _s["dimensions"]:
        _DIM_LOOKUP.setdefault(tuple(_s["dimensions"]), []).append(_k)
    elif _s.get("aspect_ratio") == "1:1":
        _DIM_LOOKUP.setdefault("1:1", []).append(_k)

tab1, tab2, tab3, tab4 = st.tabs(["Single file", "Multi-file", "ZIP bundle", "Ad Tag"])


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
        with st.expander("Check copy fields", expanded=False):
            for field_name, limit in _copy_limits.items():
                val = st.text_input(f"{field_name} (max {limit} chars)", key=f"ct_{field_name}")
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
    uploaded = st.file_uploader("JPEG, PNG or GIF", type=["jpg", "jpeg", "png", "gif"], key="t1_upload")

    if not uploaded:
        st.info("Upload a file above to run checks.")
    else:
        file_bytes = uploaded.read()
        try:
            img = Image.open(io.BytesIO(file_bytes))
            img.load()
            load_ok = True
        except Exception as e:
            st.error(f"Could not open image: {e}")
            load_ok = False

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

            checks      = run_all_checks(img, file_bytes, img_format, spec)
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
        "JPEG, PNG or GIF — select as many files as you like",
        type=["jpg", "jpeg", "png", "gif"],
        accept_multiple_files=True,
        key="mf_upload",
    )

    if not uploaded_files:
        st.info("Upload one or more files above to run checks.")
    else:
        # Dimension → spec lookup (shared module-level dict)
        dim_lookup = _DIM_LOOKUP

        # Load all files
        file_data = []
        for uf in uploaded_files:
            fb = uf.read()
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
        sm1.metric("Files uploaded", len(file_data))
        sm2.metric("Format matched", n_matched)
        sm3.metric("Unrecognised",   n_unrecognised + n_errors)
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
                        mf_checks = run_all_checks(fd["img"], fd["fb"], fd["fmt"], mf_spec)
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
        bad_files: list[str] = []

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in IMAGE_EXTS:
                        continue
                    basename = os.path.basename(name)
                    if not basename or basename.startswith(".") or basename.startswith("__"):
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
                        chks = run_all_checks(im, fb, fmt, s)
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
                                            c_chks = run_all_checks(c_img, c_bytes, c_fmt, c_spec)
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
                            tag_checks = run_all_checks(tag_img, tag_bytes, tag_fmt, tag_spec)
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
