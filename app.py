from __future__ import annotations
import io
import os
import zipfile
import datetime

APP_VERSION = "1.5.0"

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from specs import FORMATS, FORMAT_GROUPS
from checker import run_all_checks, run_video_checks, CheckResult
from fixer import apply_fixes


# ══════════════════════════════════════════════════════════════════════════════
# Feedback helpers
# ══════════════════════════════════════════════════════════════════════════════

_ACTION_HINTS: dict[str, str] = {
    "compress":   "Please reduce the file size to meet the limit.",
    "convert":    "Please convert to the required file format.",
    "add_border": "Please add a 1px solid border around the creative.",
}


def _fmt_issue(c) -> str:
    hint = _ACTION_HINTS.get(getattr(c, "fix_action", None) or "", "")
    return f"{c.message}" + (f" {hint}" if hint else "")


def build_feedback(items: list[dict], campaign: str = "") -> str:
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
    campaign = st.text_input(
        "Campaign name (optional)",
        value=default_campaign,
        placeholder="e.g. Toyota Corolla — May 2026",
        key=f"{key_prefix}_campaign",
    )

    text = build_feedback(items, campaign)

    _base_key = f"{key_prefix}_email_base"
    _area_key = f"{key_prefix}_textarea"
    if st.session_state.get(_base_key) != text:
        st.session_state[_base_key] = text
        st.session_state[_area_key] = text

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
# Page config & styles
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="carsales Ad Spec Checker",
    page_icon="🚗",
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {
        font-family: 'Manrope', sans-serif !important;
    }

    .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stMain"], section.main {
        background-color: #F2F5F7 !important;
    }

    p, li, span, label, div.stMarkdown, .stText,
    [data-testid="stMarkdownContainer"] p {
        color: #33373D !important;
    }

    h1 { color: #01295F !important; font-weight: 800 !important; }
    h2, h3 { color: #01295F !important; font-weight: 700 !important; }

    [data-testid="stExpander"] {
        background-color: #E2EAF0 !important;
        border-color: #C8D8E8 !important;
    }
    [data-testid="metric-container"] {
        background-color: #E2EAF0 !important;
        border-radius: 8px;
    }

    [data-testid="stMain"] input,
    [data-testid="stMain"] textarea,
    [data-testid="stMain"] select {
        background-color: #E2EAF0 !important;
        color: #33373D !important;
        border-color: #C8D8E8 !important;
    }

    [data-testid="stSidebar"] { background-color: #01295F !important; }
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] li,
    [data-testid="stSidebar"] .stMarkdown { color: #FFFFFF !important; }
    [data-testid="stSidebar"] a { color: #66CBE1 !important; }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15) !important; }

    [data-testid="stAppViewContainer"]::before {
        content: "";
        display: block;
        height: 5px;
        background: linear-gradient(90deg, #01295F 0%, #1E90FF 100%);
        position: fixed;
        top: 0; left: 0; right: 0;
        z-index: 9999;
    }

    [data-testid="stMetricValue"] { color: #1E90FF !important; font-weight: 700 !important; }

    button[role="tab"][aria-selected="true"] {
        color: #1E90FF !important;
        border-bottom: 3px solid #1E90FF !important;
        font-weight: 700 !important;
    }

    hr { border-color: #C8D8E8 !important; }

    [data-testid="stCode"] { background-color: #E2EAF0 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
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
    st.markdown("### How to use")
    st.markdown("""
**📂 Multi-file**
Upload several files at once — each is automatically matched to its spec by pixel dimensions.

---

**📦 ZIP bundle**
Upload a client ZIP to see which formats are present, which have issues, and what's missing.

---

**🔧 Auto-fix**
Files marked 🔧 can be corrected automatically — resize, convert, compress, or add a border.
Download the fixed file instantly.

---

**📋 Client email**
After checking, generate a ready-to-send feedback email listing exactly what needs fixing.
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

_VIDEO_EXTS: frozenset[str] = frozenset({".mp4", ".mov", ".flv", ".webm"})


# ── Cached check helpers ──────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _cached_image_checks(file_bytes: bytes, fmt: str, spec_key: str) -> list:
    spec = FORMATS[spec_key]
    img = Image.open(io.BytesIO(file_bytes))
    img.load()
    return run_all_checks(img, file_bytes, fmt, spec)


@st.cache_data(show_spinner=False)
def _cached_video_checks(file_bytes: bytes, filename: str, spec_key: str) -> list:
    return run_video_checks(file_bytes, filename, FORMATS[spec_key])


# ── Dimension → spec lookup ───────────────────────────────────────────────────
_DIM_LOOKUP: dict = {}
for _k, _s in FORMATS.items():
    if _s["dimensions"]:
        _DIM_LOOKUP.setdefault(tuple(_s["dimensions"]), []).append(_k)
    elif _s.get("aspect_ratio") == "1:1":
        _DIM_LOOKUP.setdefault("1:1", []).append(_k)


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


tab_mf, tab_zip = st.tabs(["📂 Multi-file", "📦 ZIP bundle"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB — Multi-file
# ══════════════════════════════════════════════════════════════════════════════
with tab_mf:
    st.subheader("Multi-file checker")
    st.caption("Upload multiple creatives — each file is automatically matched to its spec by dimensions.")

    uploaded_files = st.file_uploader(
        "JPEG, PNG, GIF, MP4, MOV, FLV or WebM — select as many files as you like",
        type=["jpg", "jpeg", "png", "gif", "mp4", "mov", "flv", "webm"],
        accept_multiple_files=True,
        key="mf_upload",
    )

    if not uploaded_files:
        st.info("Upload one or more files above to run checks.")
    else:
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
                matches = _DIM_LOOKUP.get((w, h), [])
                if not matches and w == h:
                    matches = _DIM_LOOKUP.get("1:1", [])
                file_data.append({"uf": uf, "fb": fb, "img": im, "fmt": fmt,
                                   "w": w, "h": h, "matches": matches, "error": None})
            except Exception as e:
                file_data.append({"uf": uf, "fb": fb, "img": None, "fmt": None,
                                   "w": None, "h": None, "matches": [], "error": str(e)})

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
                        st.caption("Verify the file dimensions are correct for the intended placement.")
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

                        if mf_failed:
                            all_issues_mf.append({
                                "filename":       uf.name,
                                "spec_name":      mf_spec["name"],
                                "client_checks":  mf_client,
                                "fixable_checks": mf_fixable,
                            })

        if all_issues_mf:
            st.divider()
            with st.expander("📋 Generate client feedback email", expanded=False):
                st.caption(
                    f"Summarises issues across **{len(all_issues_mf)} file{'s' if len(all_issues_mf)!=1 else ''}** "
                    "that need attention."
                )
                feedback_ui(all_issues_mf, "mf")

        # ── Video files ────────────────────────────────────────────────────────
        _VIDEO_SPEC_CHOICES = [k for k, v in FORMATS.items() if v.get("is_video")]
        if video_data:
            st.divider()
            st.subheader("Video files")
            for _vi, _vd in enumerate(video_data):
                _vuf = _vd["uf"]
                _vfb = _vd["fb"]
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
                    st.info(
                        "Also verify manually: H.264 codec · max 25fps · 720p+ recommended"
                        + (" · audio user-initiated" if "Outstream" in _vspec["name"] else "")
                    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB — ZIP bundle
# ══════════════════════════════════════════════════════════════════════════════
with tab_zip:
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
                    if ext in _VIDEO_EXTS:  # .mp4 .mov .flv .webm
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
            if not images and not zip_videos:
                st.warning("No supported files (JPEG, PNG, GIF, MP4, MOV) found in the ZIP.")
            elif images:
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

                zip_issues = [
                    {
                        "filename":       results[k]["filename"],
                        "spec_name":      FORMATS[k]["name"],
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

            # ── Video files in ZIP ────────────────────────────────────────────
            _ZIP_VSPEC_CHOICES = [k for k, v in FORMATS.items() if v.get("is_video")]
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
                        st.info(
                            "Also verify manually: H.264 codec · max 25fps · 720p+ recommended"
                            + (" · audio user-initiated" if "Outstream" in FORMATS[_zvsk]["name"] else "")
                        )
