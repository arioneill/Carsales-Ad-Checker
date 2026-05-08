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
        fixable=not passed and not is_animated,
        fix_action="resize" if (not passed and not is_animated) else None,
        needs_client=not passed and is_animated,
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
        img.seek(0)
        loop_val = img.info.get("loop", 0)
        if loop_val == 0:
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


def run_all_checks(img: Image.Image, file_bytes: bytes, fmt: str, spec: dict) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(check_dimensions(img, spec))
    results.append(check_file_format(fmt, spec))
    results.append(check_file_size(file_bytes, fmt, spec))
    results.append(check_border(img, spec))
    results.extend(check_gif_animation(img, spec))
    results.append(check_logo_background(img, spec))
    return results
