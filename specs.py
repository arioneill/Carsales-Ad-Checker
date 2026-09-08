# All carsales Network ad format specifications
# Sources: carsales Network Creative Guidelines (Jan 2026), On & Off Specs reference doc

def _spec(name, group, dimensions, accepted_formats, max_file_size_kb,
          animation_max_seconds=None, animation_max_plays=None, max_fps=None,
          border=False, aspect_ratio=None, clear_zone_top_px=None,
          logo_white_bg_required=False, min_count=1, unlimited=False,
          is_video=False, video_formats=None, video_max_size_mb=None,
          video_min_duration_s=None, video_max_duration_s=None,
          video_aspect_ratios=None, video_min_px=None, video_max_px=None,
          video_min_resolution=None, video_max_resolution=None):
    return {
        "name": name,
        "group": group,
        "dimensions": dimensions,
        "min_count": min_count,
        "unlimited": unlimited,   # min_count is a floor, extra files welcome
        "accepted_formats": accepted_formats,
        "max_file_size_kb": max_file_size_kb,
        "animation_max_seconds": animation_max_seconds,
        "animation_max_plays": animation_max_plays,
        "max_fps": max_fps,
        "border_required_on_light_bg": border,
        "aspect_ratio": aspect_ratio,
        "clear_zone_top_px": clear_zone_top_px,
        "logo_white_bg_required": logo_white_bg_required,
        "is_video": is_video,
        "video_formats": video_formats,
        "video_max_size_mb": video_max_size_mb,
        "video_min_duration_s": video_min_duration_s,
        "video_max_duration_s": video_max_duration_s,
        "video_aspect_ratios": video_aspect_ratios,
        "video_min_px": video_min_px,
        "video_max_px": video_max_px,
        "video_min_resolution": video_min_resolution,
        "video_max_resolution": video_max_resolution,
    }


FORMATS = {

    # ── NETWORK DISPLAY ──────────────────────────────────────────────────────
    "display_desktop_728x90": _spec(
        "Network Display — Desktop Leaderboard (728×90)", "Network Display",
        (728, 90), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    # One 300×250 serves both desktop and mobile MREC placements — listing them
    # as separate assets made the checker ask for the same file twice.
    "display_desktop_300x250": _spec(
        "Network Display — MREC (300×250)", "Network Display",
        (300, 250), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "display_desktop_300x600": _spec(
        "Network Display — Desktop Half Page (300×600)", "Network Display",
        (300, 600), ["JPEG", "GIF"], 80,
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
        "carsales Card — Logo (1:1, 100×100 recommended)", "carsales Card",
        None, ["JPEG", "PNG"], 100,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── BRAND TERMS — STANDARD BANNERS ───────────────────────────────────────
    "brand_terms_728x90": _spec(
        "Brand Terms — Desktop Leaderboard (728×90)", "Brand Terms",
        (728, 90), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
    "brand_terms_300x250": _spec(
        "Brand Terms — MREC (300×250)", "Brand Terms",
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
    "brand_terms_mobile_300x100": _spec(
        "Brand Terms — Mobile Banner (300×100)", "Brand Terms",
        (300, 100), ["JPEG", "GIF"], 80,
        animation_max_seconds=15, animation_max_plays=3, max_fps=24, border=True,
    ),
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
        "Brand Terms — Logo (1:1, 250×250 recommended)", "Brand Terms",
        None, ["PNG"], 50,
        aspect_ratio="1:1", logo_white_bg_required=True,
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
        "New Car Showroom & Research — Logo (1:1, 250×250 recommended)", "New Car Showroom & Research",
        None, ["PNG"], 50,
        aspect_ratio="1:1", logo_white_bg_required=True,
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
        "Auto Unmissable High-Impact — Logo (1:1, 250×250 recommended)", "Auto Unmissable High-Impact",
        None, ["PNG"], 80,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),
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
        "carsales Carousel — Logo (1:1, 100×100 recommended)", "carsales Carousel",
        None, ["JPEG", "PNG"], 100,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),
    "carousel_card_image": _spec(
        "carsales Carousel — Card Image (627×627)", "carsales Carousel",
        (627, 627), ["JPEG", "PNG"], 100,
        min_count=3, unlimited=True,   # at least three cards, no upper limit
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

    # ── SPONSORED SEARCH ─────────────────────────────────────────────────────
    "sponsored_search_logo": _spec(
        "Sponsored Search — Logo (1:1 PNG)", "Sponsored Search",
        None, ["PNG"], 200,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── NEWSLETTER ───────────────────────────────────────────────────────────
    "newsletter_300x250": _spec(
        "Newsletter — Static Image (300×250)", "Newsletter",
        (300, 250), ["JPEG", "GIF"], 80,
    ),

    # ── TILE ─────────────────────────────────────────────────────────────────
    "tile_211x70": _spec(
        "Tile — Static Image (211×70)", "Tile",
        (211, 70), ["JPEG", "GIF"], 80,
    ),

    # ── PUSH NOTIFICATIONS ───────────────────────────────────────────────────
    "push_notification_ios": _spec(
        "Push Notification — iOS (1038×1038)", "Push Notifications",
        (1038, 1038), ["JPEG", "PNG"], 5120,
    ),
    "push_notification_android": _spec(
        "Push Notification — Android (1024×512)", "Push Notifications",
        (1024, 512), ["JPEG", "PNG"], 5120,
    ),

    # ── IN FEED VIDEO ─────────────────────────────────────────────────────────
    "in_feed_video_file": _spec(
        "In Feed Video — Video File (MP4)", "In Feed Video",
        None, ["MP4"], 25 * 1024,
        is_video=True, video_formats=["MP4"],
        video_max_size_mb=25,
        video_min_duration_s=6, video_max_duration_s=15,
        video_aspect_ratios=["1:1", "16:9"],
        video_min_px=500, video_max_px=1920,
    ),
    "in_feed_video_logo": _spec(
        "In Feed Video — Logo (1:1, 200×200 recommended)", "In Feed Video",
        None, ["JPEG", "PNG"], 100,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── OUTSTREAM VIDEO ──────────────────────────────────────────────────────
    "outstream_video_file": _spec(
        "Outstream Video — Video File (MP4 or MOV)", "Outstream Video",
        None, ["MP4", "MOV"], 5 * 1024,
        is_video=True, video_formats=["MP4", "MOV"],
        video_max_size_mb=5,
        video_min_duration_s=6, video_max_duration_s=15,
        video_aspect_ratios=["16:9"],
        video_min_resolution=(640, 360), video_max_resolution=(1920, 1080),
    ),
    "outstream_end_frame": _spec(
        "Outstream Video — End Frame (16:9, up to 100KB)", "Outstream Video",
        None, ["JPEG", "GIF"], 100,
        aspect_ratio="16:9",
    ),

    # ── GUARANTEED CONSIDERATION ─────────────────────────────────────────────
    "guaranteed_consideration_logo": _spec(
        "Guaranteed Consideration — Logo (1:1, 150×150 recommended)", "Guaranteed Consideration",
        None, ["JPEG", "PNG"], 200,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── STOCK BOOST ──────────────────────────────────────────────────────────
    "stock_boost_logo": _spec(
        "Stock Boost — Logo (1:1, 100×100 recommended)", "Stock Boost",
        None, ["JPEG", "PNG"], 100,
        aspect_ratio="1:1", logo_white_bg_required=True,
    ),

    # ── XT SOCIAL NEWSFEED ───────────────────────────────────────────────────
    "xt_social_newsfeed_image": _spec(
        "XT Social Newsfeed — Image (1080×1080)", "XT Social Newsfeed",
        (1080, 1080), ["JPEG", "PNG"], None,
    ),

    # ── XT PREMIUM DISPLAY ───────────────────────────────────────────────────
    "xt_premium_display_970x250": _spec(
        "XT Premium Display — Billboard (970×250)", "XT Premium Display",
        (970, 250), ["JPEG", "GIF"], 100,
    ),
    "xt_premium_display_300x600": _spec(
        "XT Premium Display — Half Page (300×600)", "XT Premium Display",
        (300, 600), ["JPEG", "GIF"], 100,
    ),

    # ── XT DISPLAY ───────────────────────────────────────────────────────────
    "xt_display_300x250": _spec(
        "XT Display — MREC (300×250)", "XT Display",
        (300, 250), ["JPEG", "GIF"], 100,
    ),
    "xt_display_300x600": _spec(
        "XT Display — Half Page (300×600)", "XT Display",
        (300, 600), ["JPEG", "GIF"], 100,
    ),
    "xt_display_300x100": _spec(
        "XT Display — Mobile Banner (300×100)", "XT Display",
        (300, 100), ["JPEG", "GIF"], 100,
    ),
    "xt_display_300x50": _spec(
        "XT Display — Mobile Strip (300×50)", "XT Display",
        (300, 50), ["JPEG", "GIF"], 100,
    ),
    "xt_display_728x90": _spec(
        "XT Display — Leaderboard (728×90)", "XT Display",
        (728, 90), ["JPEG", "GIF"], 100,
    ),
    "xt_display_160x600": _spec(
        "XT Display — Wide Skyscraper (160×600)", "XT Display",
        (160, 600), ["JPEG", "GIF"], 100,
    ),
    "xt_display_320x50": _spec(
        "XT Display — Mobile Leaderboard (320×50)", "XT Display",
        (320, 50), ["JPEG", "GIF"], 100,
    ),

    # ── XT PRE-ROLL VIDEO ────────────────────────────────────────────────────
    # 960×540 is the recommended size, not a hard lock — pinning min and max to
    # it rejected in-spec HD masters. Accept anything 16:9 from 640×360 to HD.
    "xt_preroll_video": _spec(
        "XT Pre-Roll Video — 16:9 (960×540 recommended)", "XT Pre-Roll Video",
        None, ["MP4", "FLV", "WEBM"], None,
        is_video=True, video_formats=["MP4", "FLV", "WEBM"],
        video_max_size_mb=None,
        video_min_duration_s=6, video_max_duration_s=30,
        video_aspect_ratios=["16:9"],
        video_min_resolution=(640, 360), video_max_resolution=(1920, 1080),
    ),

    # ── XT CONNECTED TV ──────────────────────────────────────────────────────
    "xt_ctv_video": _spec(
        "XT Connected TV — 1920×1080 (16:9)", "XT Connected TV",
        None, ["MP4"], None,
        is_video=True, video_formats=["MP4"],
        video_max_size_mb=None,
        video_min_duration_s=15, video_max_duration_s=30,
        video_aspect_ratios=["16:9"],
        video_min_resolution=(1920, 1080), video_max_resolution=(1920, 1080),
    ),
}


# Group order controls display order in the product selector.
#
# Deliberately excluded — these run on logo and text supplied in Ignition and
# take no creative file, so there is nothing for the checker to check:
#   Unmissable, Sponsored Search, Guaranteed Consideration, Stock Boost
# Their FORMATS entries are kept so they can be restored by re-adding the group
# name below if that ever changes.
_GROUP_ORDER = [
    # On Network
    "Network Display",
    "Roadblock",
    "carsales Card",
    "Brand Terms",
    "New Car Showroom & Research",
    "Auto Unmissable High-Impact",
    "carsales Carousel",
    "carsales Discover",
    "Newsletter",
    "Tile",
    "Push Notifications",
    "In Feed Video",
    "Outstream Video",
    # Off Network (XT)
    "XT Social Newsfeed",
    "XT Premium Display",
    "XT Display",
    "XT Pre-Roll Video",
    "XT Connected TV",
]

FORMAT_GROUPS = {
    group: [k for k, v in FORMATS.items() if v["group"] == group]
    for group in _GROUP_ORDER
}


# ── Asset slots ───────────────────────────────────────────────────────────────
# Most specs want one file, but some (carousel cards) want several. A "slot" is
# one file the client owes us: "carousel_card_image#2" is the second card. Slot
# ids stay plain spec keys wherever min_count is 1, so single-file specs are
# unaffected.

def slot_base(slot: str) -> str:
    """The spec key behind a slot id."""
    return slot.split("#", 1)[0]


def spec_slots(spec_key: str) -> list[str]:
    n = FORMATS[spec_key].get("min_count") or 1
    if n == 1:
        return [spec_key]
    return [f"{spec_key}#{i + 1}" for i in range(n)]


def group_slots(group: str) -> list[str]:
    """Every file a product needs, one entry per file."""
    slots: list[str] = []
    for key in FORMAT_GROUPS.get(group, []):
        slots.extend(spec_slots(key))
    return slots


def slot_label(slot: str) -> str:
    base = slot_base(slot)
    name = FORMATS[base]["name"]
    if "#" not in slot:
        return name
    n = int(slot.split("#", 1)[1])
    spec = FORMATS[base]
    if spec.get("unlimited"):
        return f"{name} — card {n}"
    # Spec normally wants one file; this is an additional creative for the same
    # placement, which a campaign can carry any number of.
    return f"{name} — creative {n}"


def is_unlimited(slot: str) -> bool:
    """True when a spec takes any number of files above its min_count."""
    return bool(FORMATS[slot_base(slot)].get("unlimited"))

CARD_TEXT_LIMITS = {
    "Headline Text": 30,
    "Card Text": 90,
    "CTA Text": 18,
    "Link Description (off-network only)": 35,
}

COPY_LIMITS: dict[str, dict[str, int]] = {
    "carsales Card": {
        "Headline Text": 30,
        "Card Text": 90,
        "CTA Text": 18,
        "Link Description (off-network only)": 35,
    },
    "carsales Discover": {
        "Headline": 30,
        "Advertiser Name": 18,
        "CTA": 18,
    },
    "carsales Carousel": {
        "Headline Text": 30,
        "Sub-headline Text": 30,
        "Body Text": 110,
        "CTA Text": 18,
    },
    "Brand Terms": {
        "Headline": 30,
        "Body": 70,
        "CTA": 10,
    },
    "New Car Showroom & Research": {
        "Hero Image Text Link": 35,
        "Native Tile Headline": 25,
        "Native Tile Body Copy": 85,
    },
    "Auto Unmissable High-Impact": {
        "Unmissable Bar Text": 40,
        "External Text Link": 35,
    },
    "In Feed Video": {
        "Title": 35,
        "CTA": 18,
        "Description (Desktop, all ratios)": 108,
        "Description (Mobile 1:1)": 48,
    },
    "Stock Boost": {
        "Header Text": 30,
    },
}
