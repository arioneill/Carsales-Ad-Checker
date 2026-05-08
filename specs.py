# All carsales Network ad format specifications
# Sources: carsales Network Creative Guidelines (Jan 2026), format spec PDFs

def _spec(name, group, dimensions, accepted_formats, max_file_size_kb,
          animation_max_seconds=None, animation_max_plays=None, max_fps=None,
          border=False, aspect_ratio=None, clear_zone_top_px=None,
          logo_white_bg_required=False):
    return {
        "name": name,
        "group": group,
        "dimensions": dimensions,
        "accepted_formats": accepted_formats,
        "max_file_size_kb": max_file_size_kb,
        "animation_max_seconds": animation_max_seconds,
        "animation_max_plays": animation_max_plays,
        "max_fps": max_fps,
        "border_required_on_light_bg": border,
        "aspect_ratio": aspect_ratio,
        "clear_zone_top_px": clear_zone_top_px,
        "logo_white_bg_required": logo_white_bg_required,
    }


FORMATS = {

    # ── NETWORK DISPLAY ──────────────────────────────────────────────────────
    "display_desktop_728x90": _spec(
        "Network Display — Desktop Leaderboard (728×90)", "Network Display",
        (728, 90), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "display_desktop_300x250": _spec(
        "Network Display — Desktop MREC (300×250)", "Network Display",
        (300, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "display_desktop_300x600": _spec(
        "Network Display — Desktop Half Page (300×600)", "Network Display",
        (300, 600), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "display_mobile_300x250": _spec(
        "Network Display — Mobile MREC (300×250)", "Network Display",
        (300, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "display_mobile_300x100": _spec(
        "Network Display — Mobile Banner (300×100)", "Network Display",
        (300, 100), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),

    # ── ROADBLOCK ─────────────────────────────────────────────────────────────
    "roadblock_desktop_728x90": _spec(
        "Roadblock — Desktop Leaderboard (728×90)", "Roadblock",
        (728, 90), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "roadblock_desktop_300x600": _spec(
        "Roadblock — Desktop Half Page (300×600)", "Roadblock",
        (300, 600), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "roadblock_mobile_300x250": _spec(
        "Roadblock — Mobile MREC (300×250)", "Roadblock",
        (300, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),

    # ── CARSALES CARD ─────────────────────────────────────────────────────────
    "card_image": _spec(
        "carsales Card — Card Image (720×720)", "carsales Card",
        (720, 720), ["JPEG", "PNG"], 100,
        clear_zone_top_px=280,
    ),
    "card_logo": _spec(
        "carsales Card — Logo (1:1 square)", "carsales Card",
        None, ["JPEG", "PNG"], 100,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── BRAND TERMS — STANDARD BANNERS ───────────────────────────────────────
    # Same animation/border rules as Network Display; includes 970×250 billboard
    "brand_terms_728x90": _spec(
        "Brand Terms — Desktop Leaderboard (728×90)", "Brand Terms",
        (728, 90), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "brand_terms_300x250": _spec(
        "Brand Terms — Desktop MREC (300×250)", "Brand Terms",
        (300, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "brand_terms_300x600": _spec(
        "Brand Terms — Desktop Half Page (300×600)", "Brand Terms",
        (300, 600), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "brand_terms_970x250": _spec(
        "Brand Terms — Desktop Billboard (970×250)", "Brand Terms",
        (970, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "brand_terms_mobile_300x250": _spec(
        "Brand Terms — Mobile MREC (300×250)", "Brand Terms",
        (300, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "brand_terms_mobile_300x100": _spec(
        "Brand Terms — Mobile Banner (300×100)", "Brand Terms",
        (300, 100), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    # Brand Terms — Native High Impact unique assets
    "brand_terms_skin_mobile": _spec(
        "Brand Terms — Native High Impact Mobile Skin (1940×500)", "Brand Terms",
        (1940, 500), ["JPEG", "PNG"], 100,
    ),
    "brand_terms_skin_desktop": _spec(
        "Brand Terms — Native High Impact Desktop Skin (3840×500)", "Brand Terms",
        (3840, 500), ["JPEG", "PNG"], 300,
    ),
    "brand_terms_floating_footer": _spec(
        "Brand Terms — Floating Footer Mobile (1065×210)", "Brand Terms",
        (1065, 210), ["JPEG", "PNG"], 300,
    ),
    "brand_terms_logo": _spec(
        "Brand Terms — Logo (250×250)", "Brand Terms",
        (250, 250), ["PNG"], 50,
        logo_white_bg_required=True,
    ),

    # ── NEW CAR SHOWROOM & RESEARCH ──────────────────────────────────────────
    "new_car_showroom_hero": _spec(
        "New Car Showroom & Research — Hero Image (1920×686)", "New Car Showroom & Research",
        (1920, 686), ["JPEG", "PNG"], 300,
    ),
    "new_car_showroom_native_tile": _spec(
        "New Car Showroom & Research — Native Tile (800×400)", "New Car Showroom & Research",
        (800, 400), ["JPEG", "PNG"], 300,
    ),
    "new_car_showroom_logo": _spec(
        "New Car Showroom & Research — Logo (250×250)", "New Car Showroom & Research",
        (250, 250), ["PNG"], 50,
        logo_white_bg_required=True,
    ),

    # ── AUTO UNMISSABLE HIGH-IMPACT ──────────────────────────────────────────
    "auto_unmissable_hero_desktop": _spec(
        "Auto Unmissable High-Impact — Hero Image Desktop (1920×600)", "Auto Unmissable High-Impact",
        (1920, 600), ["JPEG", "PNG"], 300,
    ),
    "auto_unmissable_hero_mobile": _spec(
        "Auto Unmissable High-Impact — Hero Image Mobile (800×450)", "Auto Unmissable High-Impact",
        (800, 450), ["JPEG", "PNG"], 300,
    ),
    "auto_unmissable_logo": _spec(
        "Auto Unmissable High-Impact — Logo (250×250)", "Auto Unmissable High-Impact",
        (250, 250), ["PNG"], 80,
        logo_white_bg_required=True,
    ),
    # Billboard and standard banners share same rules as display but max 30s animation, looping OK
    "auto_unmissable_billboard": _spec(
        "Auto Unmissable High-Impact — Billboard (970×250)", "Auto Unmissable High-Impact",
        (970, 250), ["JPEG", "PNG"], 80,
        animation_max_seconds=30, max_fps=24, border=True,
    ),
    "auto_unmissable_728x90": _spec(
        "Auto Unmissable High-Impact — Standard Banner Desktop (728×90)", "Auto Unmissable High-Impact",
        (728, 90), ["JPEG", "PNG"], 80,
        animation_max_seconds=30, max_fps=24, border=True,
    ),
    "auto_unmissable_300x250": _spec(
        "Auto Unmissable High-Impact — Standard Banner Desktop MREC (300×250)", "Auto Unmissable High-Impact",
        (300, 250), ["JPEG", "PNG"], 80,
        animation_max_seconds=30, max_fps=24, border=True,
    ),
    "auto_unmissable_300x600": _spec(
        "Auto Unmissable High-Impact — Standard Banner Desktop Half Page (300×600)", "Auto Unmissable High-Impact",
        (300, 600), ["JPEG", "PNG"], 80,
        animation_max_seconds=30, max_fps=24, border=True,
    ),
    "auto_unmissable_mobile_300x100": _spec(
        "Auto Unmissable High-Impact — Standard Banner Mobile (300×100)", "Auto Unmissable High-Impact",
        (300, 100), ["JPEG", "PNG"], 80,
        animation_max_seconds=30, max_fps=24, border=True,
    ),

    # ── UNMISSABLE (SPONSORED BAR) ────────────────────────────────────────────
    "unmissable_logo": _spec(
        "Unmissable — Logo (1:1)", "Unmissable",
        None, ["PNG"], 200,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── CARSALES CAROUSEL ─────────────────────────────────────────────────────
    "carousel_logo": _spec(
        "carsales Carousel — Logo (100×100)", "carsales Carousel",
        (100, 100), ["JPEG", "PNG"], 100,
        logo_white_bg_required=True,
    ),
    "carousel_card_image": _spec(
        "carsales Carousel — Card Image (627×627)", "carsales Carousel",
        (627, 627), ["JPEG", "PNG"], 100,
    ),

    # ── CARSALES DISCOVER ─────────────────────────────────────────────────────
    "discover_image": _spec(
        "carsales Discover — Image (600×600)", "carsales Discover",
        (600, 600), ["JPEG", "PNG"], 100,
        clear_zone_top_px=200,
    ),
    "discover_logo": _spec(
        "carsales Discover — Logo (1:1)", "carsales Discover",
        None, ["JPEG", "PNG"], 100,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── IN FEED VIDEO ─────────────────────────────────────────────────────────
    "in_feed_video_logo": _spec(
        "In Feed Video — Logo (200×200)", "In Feed Video",
        (200, 200), ["JPEG", "PNG"], 100,
        logo_white_bg_required=True,
    ),

    # ── OUTSTREAM VIDEO ──────────────────────────────────────────────────────
    # End frame is the only image asset; video itself is not checked here
    "outstream_end_frame": _spec(
        "Outstream Video — End Frame (16:9, up to 100KB)", "Outstream Video",
        None, ["JPEG", "PNG"], 100,
    ),

    # ── GUARANTEED CONSIDERATION ─────────────────────────────────────────────
    "guaranteed_consideration_logo": _spec(
        "Guaranteed Consideration — Logo (150×150)", "Guaranteed Consideration",
        (150, 150), ["JPEG", "PNG"], 200,
        logo_white_bg_required=True,
    ),

    # ── STOCK BOOST ──────────────────────────────────────────────────────────
    "stock_boost_logo": _spec(
        "Stock Boost — Logo (100×100)", "Stock Boost",
        (100, 100), ["JPEG", "PNG"], 100,
        logo_white_bg_required=True,
    ),
}


# Group order controls dropdown display order
_GROUP_ORDER = [
    "Network Display",
    "Roadblock",
    "carsales Card",
    "Brand Terms",
    "New Car Showroom & Research",
    "Auto Unmissable High-Impact",
    "Unmissable",
    "carsales Carousel",
    "carsales Discover",
    "In Feed Video",
    "Outstream Video",
    "Guaranteed Consideration",
    "Stock Boost",
]

FORMAT_GROUPS = {
    group: [k for k, v in FORMATS.items() if v["group"] == group]
    for group in _GROUP_ORDER
}

CARD_TEXT_LIMITS = {
    "Headline Text": 30,
    "Card Text": 90,
    "CTA Text": 18,
    "Link Description (off-network only)": 35,
}
