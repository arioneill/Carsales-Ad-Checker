# carsales Ad Spec Checker

Checks ad creatives against carsales Network specifications and auto-fixes common issues.

## Supported formats

| Group | Sizes |
|---|---|
| Network Display | Desktop 728×90, 300×250, 300×600 · Mobile 300×250, 300×100 |
| Roadblock | Desktop 728×90, 300×600 · Mobile 300×250 |
| carsales Card | Card image 720×720 · Logo (1:1) |

## What it checks

**Technical (always):**
- Dimensions / aspect ratio
- File format (JPEG, GIF, PNG per spec)
- File size (80 KB or 100 KB limit)
- 1px border on light/white backgrounds
- GIF animation duration, frame rate, and loop count

**AI-powered (optional, requires Anthropic API key):**
- Brand logo or name visible
- No competitor publisher references
- No prohibited all-caps text
- Clear zone free of copy/logos (carsales Card)

**carsales Card text fields:**
- Headline (30 chars), Card Text (90 chars), CTA (18 chars), Link Description (35 chars)

## What it auto-fixes

- Wrong dimensions → resize
- Wrong format → convert to JPEG/PNG
- Missing 1px border → add border
- File too large → compress

Issues that require client revision (wrong content, missing branding, competitor logos, animation violations) are flagged clearly.

---

## Run locally

**Requirements:** Python 3.10+

```bash
cd carsales-ad-checker
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Share with colleagues — deploy to Streamlit Cloud (free)

1. Push this folder to a GitHub repository (public or private).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → select your repo → set **Main file path** to `app.py`.
4. Click **Deploy**. You'll get a public URL to share with your team.

> **API key for AI checks:** In Streamlit Cloud, go to **Settings → Secrets** and add:
> ```
> ANTHROPIC_API_KEY = "sk-ant-..."
> ```
> Then update `app.py` to read it with `st.secrets["ANTHROPIC_API_KEY"]` as a fallback
> if the sidebar field is empty.

---

## File structure

```
carsales-ad-checker/
├── app.py          # Streamlit UI
├── specs.py        # All format specifications
├── checker.py      # Technical check functions
├── fixer.py        # Auto-fix functions
├── ai_checker.py   # Claude vision API checks
└── requirements.txt
```
