from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    fixable: bool = False
    fix_action: Optional[str] = None
    needs_client: bool = False  # True = cannot be auto-fixed, must go back to client


def _normalise_format(fmt: str) -> str:
    fmt = (fmt or "").upper().strip()
    if fmt in ("JPG",):
        return "JPEG"
    return fmt


def check_dimensions(img: Image.Image, spec: dict) -> CheckResult:
    w, h = img.size

    if spec.get("aspect_ratio") == "1:1":
        passed = (w == h)
        return CheckResult(
            name="Aspect Ratio",
            passed=passed,
            message=f"{w}×{h}px — {'1:1 square ✓' if passed else 'not square, must be 1:1 ratio'}",
            fixable=False,
            needs_client=not passed,
        )

    if spec["dimensions"] is None:
        return CheckResult(name="Dimensions", passed=True, message="No fixed dimension required ✓")

    ew, eh = spec["dimensions"]
    passed = (w == ew and h == eh)
    is_animated = getattr(img, "n_frames", 1) > 1

    return CheckResult(
        name="Dimensions",
        passed=passed,
        message=f"{w}×{h}px {'✓' if passed else f'— required {ew}×{eh}px'}",
        fixable=False,
        fix_action=None,
        needs_client=not passed,
    )


def check_file_format(fmt: str, spec: dict) -> CheckResult:
    accepted = spec["accepted_formats"]
    norm = _normalise_format(fmt)
    passed = norm in accepted

    # Can we convert? Yes if it's a known raster format going to JPEG/PNG
    convertible_from = {"JPEG", "PNG", "BMP", "WEBP", "TIFF"}
    fixable = not passed and norm in convertible_from

    accepted_str = " or ".join(accepted)
    return CheckResult(
        name="File Format",
        passed=passed,
        message=f"{norm} ✓" if passed else f"{norm} — must be {accepted_str}",
        fixable=fixable,
        fix_action="convert" if fixable else None,
        needs_client=not passed and not fixable,
    )


def check_file_size(file_bytes: bytes, fmt: str, spec: dict) -> CheckResult:
    size_kb = len(file_bytes) / 1024
    max_kb = spec["max_file_size_kb"]
    if max_kb is None:
        return CheckResult(name="File Size", passed=True, message=f"{size_kb:.1f} KB ✓")
    passed = size_kb <= max_kb
    norm = _normalise_format(fmt)
    # GIFs can't be reliably recompressed without remaking them
    is_animated_gif = norm == "GIF"

    return CheckResult(
        name="File Size",
        passed=passed,
        message=f"{size_kb:.1f} KB {'✓' if passed else f'— exceeds {max_kb} KB limit'}",
        fixable=not passed and not is_animated_gif,
        fix_action="compress" if (not passed and not is_animated_gif) else None,
        needs_client=not passed and is_animated_gif,
    )


def _edge_brightness(img: Image.Image) -> float:
    """Return average brightness of the outermost 2px ring of pixels."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    pixels: list[tuple[int, int, int]] = []
    step_x = max(1, w // 40)
    step_y = max(1, h // 40)
    for x in range(0, w, step_x):
        pixels.append(rgb.getpixel((x, 0)))
        pixels.append(rgb.getpixel((x, h - 1)))
    for y in range(0, h, step_y):
        pixels.append(rgb.getpixel((0, y)))
        pixels.append(rgb.getpixel((w - 1, y)))
    if not pixels:
        return 128.0
    return sum(sum(p) / 3 for p in pixels) / len(pixels)


def _inner_brightness(img: Image.Image) -> float:
    """Return average brightness of the 2nd pixel ring (just inside the edge)."""
    rgb = img.convert("RGB")
    w, h = rgb.size
    if w < 4 or h < 4:
        return 128.0
    pixels: list[tuple[int, int, int]] = []
    step_x = max(1, w // 40)
    step_y = max(1, h // 40)
    for x in range(0, w, step_x):
        pixels.append(rgb.getpixel((x, 1)))
        pixels.append(rgb.getpixel((x, h - 2)))
    for y in range(0, h, step_y):
        pixels.append(rgb.getpixel((1, y)))
        pixels.append(rgb.getpixel((w - 2, y)))
    if not pixels:
        return 128.0
    return sum(sum(p) / 3 for p in pixels) / len(pixels)


def check_border(img: Image.Image, spec: dict) -> CheckResult:
    if not spec.get("border_required_on_light_bg"):
        return CheckResult(name="Border", passed=True, message="Not required for this format ✓")

    edge_bright = _edge_brightness(img)

    # Only required if background is light/white
    if edge_bright < 200:
        return CheckResult(
            name="Border",
            passed=True,
            message=f"Dark background detected — border not required ✓",
        )

    # Background is light — check if a border is already present
    # A border shows as a noticeably darker outermost ring vs the second ring
    inner_bright = _inner_brightness(img)
    has_border = (inner_bright - edge_bright) > 15

    return CheckResult(
        name="Border",
        passed=has_border,
        message="1px border present ✓" if has_border else "Missing 1px border — required on white/light backgrounds",
        fixable=not has_border,
        fix_action="add_border" if not has_border else None,
    )


def check_gif_animation(img: Image.Image, spec: dict) -> list[CheckResult]:
    results: list[CheckResult] = []
    max_sec = spec.get("animation_max_seconds")
    max_fps = spec.get("max_fps")
    max_plays = spec.get("animation_max_plays")

    if not hasattr(img, "n_frames") or img.n_frames <= 1:
        return results

    # Read the loop count BEFORE seeking. Pillow rebuilds img.info per frame, so
    # the NETSCAPE loop extension recorded on frame 0 is gone once we have
    # walked the frames — reading it afterwards fell back to the default and
    # reported every GIF as an infinite loop.
    loop_val = img.info.get("loop")

    # Collect per-frame durations
    durations: list[float] = []
    for i in range(img.n_frames):
        img.seek(i)
        durations.append(float(img.info.get("duration", 100)))
    img.seek(0)

    total_s = sum(durations) / 1000.0

    if max_sec is not None:
        ok = total_s <= max_sec
        results.append(CheckResult(
            name="Animation Duration",
            passed=ok,
            message=f"{total_s:.1f}s {'✓' if ok else f'— exceeds {max_sec}s max (client must fix)'}",
            needs_client=not ok,
        ))

    if max_fps is not None and durations:
        avg_ms = sum(durations) / len(durations)
        fps = 1000.0 / avg_ms if avg_ms else 0.0
        ok = fps <= max_fps
        results.append(CheckResult(
            name="Frame Rate",
            passed=ok,
            message=f"{fps:.1f} fps {'✓' if ok else f'— exceeds {max_fps} fps max (client must fix)'}",
            needs_client=not ok,
        ))

    if max_plays is not None:
        if loop_val is None:
            # No NETSCAPE loop extension at all — the GIF plays once and stops.
            results.append(CheckResult(
                name="Loop / Play Count",
                passed=True,
                message="1 play (no loop) ✓",
            ))
        elif loop_val == 0:
            # 0 in GIF spec = loop forever
            results.append(CheckResult(
                name="Loop / Play Count",
                passed=False,
                message=f"Infinite loop detected — max {max_plays} plays ({max_plays - 1} additional loops) allowed (client must fix)",
                needs_client=True,
            ))
        else:
            total_plays = loop_val + 1
            ok = total_plays <= max_plays
            results.append(CheckResult(
                name="Loop / Play Count",
                passed=ok,
                message=f"{total_plays} play{'s' if total_plays != 1 else ''} {'✓' if ok else f'— max {max_plays} plays allowed (client must fix)'}",
                needs_client=not ok,
            ))

    return results


def check_logo_background(img: Image.Image, spec: dict) -> CheckResult:
    """For card logo: background must be white or transparent."""
    if not spec.get("logo_white_bg_required"):
        return CheckResult(name="Logo Background", passed=True, message="Not applicable ✓")

    # Check for transparency (RGBA/PA mode)
    if img.mode in ("RGBA", "PA", "LA"):
        return CheckResult(
            name="Logo Background",
            passed=True,
            message="Transparent background detected ✓",
        )

    # Check if background is white/near-white
    bright = _edge_brightness(img)
    passed = bright >= 230
    return CheckResult(
        name="Logo Background",
        passed=passed,
        message="White/transparent background ✓" if passed else "Logo background must be white or transparent (client must fix)",
        needs_client=not passed,
    )


def _parse_video_meta(data: bytes) -> dict:
    """Extract width, height, and duration from MP4/MOV bytes via box parsing."""
    import struct
    result: dict = {"width": None, "height": None, "duration_s": None}
    n = len(data)

    def iter_boxes(start: int, end: int):
        pos = start
        while pos + 8 <= end:
            try:
                size = struct.unpack_from(">I", data, pos)[0]
            except struct.error:
                break
            btype = data[pos + 4: pos + 8].decode("latin-1", errors="replace")
            if size == 1:
                if pos + 16 > end:
                    break
                size = int(struct.unpack_from(">Q", data, pos + 8)[0])
                header = 16
            elif size == 0:
                size = end - pos
                header = 8
            else:
                header = 8
            if size < header or pos + size > end or size > 200_000_000:
                break
            yield btype, pos + header, pos + size
            pos += size

    moov_d, moov_e = None, None
    for btype, bd, be in iter_boxes(0, n):
        if btype == "moov":
            moov_d, moov_e = bd, be
            break

    if moov_d is None:
        return result

    for btype, bd, be in iter_boxes(moov_d, moov_e):
        if btype == "mvhd":
            try:
                version = data[bd]
                if version == 0:
                    timescale = struct.unpack_from(">I", data, bd + 12)[0]
                    duration  = struct.unpack_from(">I", data, bd + 16)[0]
                else:
                    timescale = struct.unpack_from(">I", data, bd + 20)[0]
                    duration  = int(struct.unpack_from(">Q", data, bd + 24)[0])
                if timescale:
                    result["duration_s"] = duration / timescale
            except (struct.error, IndexError):
                pass
            break

    for btype, bd, be in iter_boxes(moov_d, moov_e):
        if btype != "trak":
            continue
        for btype2, bd2, be2 in iter_boxes(bd, be):
            if btype2 == "tkhd":
                try:
                    version = data[bd2]
                    if version == 0:
                        w_fp = struct.unpack_from(">I", data, bd2 + 76)[0]
                        h_fp = struct.unpack_from(">I", data, bd2 + 80)[0]
                    else:
                        w_fp = struct.unpack_from(">I", data, bd2 + 88)[0]
                        h_fp = struct.unpack_from(">I", data, bd2 + 92)[0]
                    w = w_fp >> 16
                    h = h_fp >> 16
                    if w > 0 and h > 0:
                        result["width"] = w
                        result["height"] = h
                except (struct.error, IndexError):
                    pass
                break
        if result["width"] is not None:
            break

    return result


def run_video_checks(file_bytes: bytes, filename: str, spec: dict) -> list[CheckResult]:
    """Run checks on a video creative file (MP4/MOV)."""
    results: list[CheckResult] = []

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_fmt = ext.upper()

    # 1. Video format
    accepted_fmts = spec.get("video_formats") or []
    fmt_ok = file_fmt in accepted_fmts
    results.append(CheckResult(
        name="Video Format",
        passed=fmt_ok,
        message=f"{file_fmt} ✓" if fmt_ok else f"{file_fmt} — must be {' or '.join(accepted_fmts)}",
        needs_client=not fmt_ok,
    ))

    # 2. File size
    max_mb = spec.get("video_max_size_mb")
    if max_mb:
        size_mb = len(file_bytes) / (1024 * 1024)
        size_ok = size_mb <= max_mb
        results.append(CheckResult(
            name="File Size",
            passed=size_ok,
            message=f"{size_mb:.1f} MB {'✓' if size_ok else f'— exceeds {max_mb} MB limit (client must reduce)'}",
            needs_client=not size_ok,
        ))

    # 3. Parse metadata
    meta = _parse_video_meta(file_bytes)
    dims_ok = meta["width"] is not None and meta["height"] is not None
    dur_ok  = meta["duration_s"] is not None

    # 4. Aspect ratio + resolution
    if dims_ok:
        w, h = meta["width"], meta["height"]
        accepted_ratios = spec.get("video_aspect_ratios") or []
        if accepted_ratios:
            ratio_ok = False
            for ar in accepted_ratios:
                if ar == "16:9" and w > 0 and h > 0 and abs((w / h) - (16 / 9)) < 0.02:
                    ratio_ok = True; break
                elif ar == "1:1" and w == h:
                    ratio_ok = True; break
            results.append(CheckResult(
                name="Aspect Ratio",
                passed=ratio_ok,
                message=(
                    f"{w}×{h}px ✓" if ratio_ok
                    else f"{w}×{h}px — required {' or '.join(accepted_ratios)}"
                ),
                needs_client=not ratio_ok,
            ))

        min_px = spec.get("video_min_px")
        max_px = spec.get("video_max_px")
        if min_px is not None or max_px is not None:
            short, long_ = min(w, h), max(w, h)
            res_ok = (min_px is None or short >= min_px) and (max_px is None or long_ <= max_px)
            parts = []
            if not res_ok:
                if min_px and short < min_px:
                    parts.append(f"min {min_px}px on shortest side")
                if max_px and long_ > max_px:
                    parts.append(f"max {max_px}px exceeded")
            results.append(CheckResult(
                name="Resolution",
                passed=res_ok,
                message=f"{w}×{h}px {'✓' if res_ok else '— ' + ', '.join(parts)}",
                needs_client=not res_ok,
            ))

        min_res = spec.get("video_min_resolution")
        max_res = spec.get("video_max_resolution")
        if min_res or max_res:
            res_ok = True
            parts = []
            if min_res and (w < min_res[0] or h < min_res[1]):
                res_ok = False
                parts.append(f"min {min_res[0]}×{min_res[1]}px")
            if max_res and (w > max_res[0] or h > max_res[1]):
                res_ok = False
                parts.append(f"max {max_res[0]}×{max_res[1]}px")
            results.append(CheckResult(
                name="Resolution",
                passed=res_ok,
                message=f"{w}×{h}px {'✓' if res_ok else '— ' + ' / '.join(parts) + ' required'}",
                needs_client=not res_ok,
            ))
    else:
        results.append(CheckResult(
            name="Dimensions",
            passed=True,
            message="Could not parse video metadata — verify dimensions manually",
        ))

    # 5. Duration
    if dur_ok:
        d = meta["duration_s"]
        min_d = spec.get("video_min_duration_s")
        max_d = spec.get("video_max_duration_s")
        # Encoders rarely land on a whole second: a "15s" cut usually measures
        # 15.02s once the timescale is divided out. Without this tolerance an
        # in-spec file fails on a rounding artefact.
        tol = 0.25
        d_ok = ((min_d is None or d >= min_d - tol)
                and (max_d is None or d <= max_d + tol))
        range_str = f"{min_d}–{max_d}s" if (min_d and max_d) else ""
        results.append(CheckResult(
            name="Duration",
            passed=d_ok,
            message=f"{d:.1f}s {'✓' if d_ok else f'— required {range_str} (client must fix)'}",
            needs_client=not d_ok,
        ))
    else:
        results.append(CheckResult(
            name="Duration",
            passed=True,
            message="Could not parse duration — verify 6–15s manually",
        ))

    return results


def run_all_checks(img: Image.Image, file_bytes: bytes, fmt: str, spec: dict) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(check_dimensions(img, spec))
    results.append(check_file_format(fmt, spec))
    results.append(check_file_size(file_bytes, fmt, spec))
    results.append(check_border(img, spec))
    results.extend(check_gif_animation(img, spec))
    results.append(check_logo_background(img, spec))
    return results
