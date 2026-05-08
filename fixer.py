from __future__ import annotations
import io
from PIL import Image, ImageDraw
from checker import CheckResult


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "P", "PA", "LA"):
        return img.convert("RGB")
    return img


def resize_image(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    return img.resize((target_w, target_h), Image.LANCZOS)


def add_border(img: Image.Image, colour: tuple[int, int, int] = (160, 160, 160)) -> Image.Image:
    out = _to_rgb(img).copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    draw.rectangle([0, 0, w - 1, h - 1], outline=colour)
    return out


def compress_to_jpeg(img: Image.Image, max_kb: float) -> bytes:
    img = _to_rgb(img)
    for quality in range(92, 5, -5):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() / 1024 <= max_kb:
            return buf.getvalue()
    # Last resort — minimum quality
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=5, optimize=True)
    return buf.getvalue()


def compress_to_png(img: Image.Image, max_kb: float) -> bytes:
    for compress in range(9, 0, -1):
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True, compress_level=compress)
        if buf.tell() / 1024 <= max_kb:
            return buf.getvalue()
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def apply_fixes(
    img: Image.Image,
    file_bytes: bytes,
    fmt: str,
    spec: dict,
    checks: list[CheckResult],
) -> tuple[bytes, str, list[str]]:
    """
    Apply all auto-fixable issues in order: format → dimensions → border → size.
    Returns (fixed_bytes, output_format, list_of_descriptions).
    """
    applied: list[str] = []
    current_fmt = (fmt or "JPEG").upper()
    if current_fmt == "JPG":
        current_fmt = "JPEG"

    fix_map = {c.fix_action: c for c in checks if c.fixable and c.fix_action}

    # 1. Format conversion (must happen first so subsequent ops work on correct type)
    if "convert" in fix_map:
        target = spec["accepted_formats"][0]
        if target == "JPEG":
            img = _to_rgb(img)
        current_fmt = target
        applied.append(f"Converted format to {target}")

    # 2. Resize
    if "resize" in fix_map and spec.get("dimensions"):
        tw, th = spec["dimensions"]
        img = resize_image(img, tw, th)
        applied.append(f"Resized to {tw}×{th}px")

    # 3. Border
    if "add_border" in fix_map:
        img = add_border(img)
        applied.append("Added 1px grey border")

    # 4. Compress (do last so all prior changes are captured)
    max_kb = spec["max_file_size_kb"]

    # Serialise to check current size
    buf = io.BytesIO()
    save_fmt = current_fmt if current_fmt in ("JPEG", "PNG") else "JPEG"
    if save_fmt == "JPEG":
        img_out = _to_rgb(img)
        img_out.save(buf, format="JPEG", quality=90, optimize=True)
    else:
        img.save(buf, format="PNG", optimize=True)
    current_bytes = buf.getvalue()

    if len(current_bytes) / 1024 > max_kb:
        if save_fmt == "JPEG":
            current_bytes = compress_to_jpeg(img, max_kb)
        else:
            current_bytes = compress_to_png(img, max_kb)
        applied.append(f"Compressed to under {max_kb} KB")
    elif "compress" in fix_map:
        # Was flagged as too large but after other fixes it's now fine
        if save_fmt == "JPEG":
            current_bytes = compress_to_jpeg(img, max_kb)
        else:
            current_bytes = compress_to_png(img, max_kb)
        applied.append(f"Compressed to under {max_kb} KB")

    return current_bytes, save_fmt, applied
