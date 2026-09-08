from __future__ import annotations
import io
from PIL import Image, ImageDraw
from checker import CheckResult


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "P", "PA", "LA"):
        return img.convert("RGB")
    return img



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


def has_alpha(img: Image.Image) -> bool:
    """True only if the image actually uses transparency, not merely allows it."""
    if img.mode in ("RGBA", "LA", "PA"):
        try:
            return img.getchannel("A").getextrema()[0] < 255
        except (ValueError, OSError):
            return True
    return "transparency" in img.info


def is_photographic(img: Image.Image, threshold: int = 4096) -> bool:
    """True for continuous-tone imagery, False for flat artwork and logos.

    getcolors returns None once the image exceeds maxcolors, which is the cheap
    way to ask the question. Flat artwork keeps its edges crisp under palette
    reduction; a photograph does not, so the two want different formats.
    """
    try:
        return img.convert("RGB").getcolors(maxcolors=threshold) is None
    except (ValueError, OSError):
        return True


def compress_to_png(img: Image.Image, max_kb: float) -> bytes:
    """Shrink a PNG as far as PNG allows: full compression, then fewer colours.

    PNG is lossless, so compress_level barely moves the needle — the previous
    implementation walked levels 9 down to 1, which cannot help because level 9
    is already the smallest. Reducing the palette is the only real lever, and
    even that will not rescue a photograph. Returns the smallest result found,
    which may still exceed max_kb; callers must check.
    """
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    best = buf.getvalue()
    if len(best) / 1024 <= max_kb:
        return best

    for colours in (256, 128, 64, 32, 16):
        try:
            src = img.convert("RGBA") if has_alpha(img) else img.convert("RGB")
            q   = src.quantize(colors=colours, method=Image.Quantize.FASTOCTREE)
            b2  = io.BytesIO()
            q.save(b2, format="PNG", optimize=True, compress_level=9)
        except (ValueError, OSError):
            break
        if b2.tell() < len(best):
            best = b2.getvalue()
        if b2.tell() / 1024 <= max_kb:
            return best
    return best


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

    # 2. Resize. Only ever reached when checker._resize_verdict cleared it as a
    #    pure downscale at the same aspect ratio, so nothing is cropped.
    if "resize" in fix_map and spec.get("dimensions"):
        ew, eh = spec["dimensions"]
        if img.size != (ew, eh):
            img = img.resize((ew, eh), Image.LANCZOS)
            applied.append(f"Resized to {ew}×{eh}")

    # 3. Border — after the resize, or it would be scaled away
    if "add_border" in fix_map:
        img = add_border(img)
        applied.append("Added 1px grey border")

    # 4. Compress (do last so all prior changes are captured)
    max_kb   = spec.get("max_file_size_kb")
    accepted = [f.upper() for f in (spec.get("accepted_formats") or [])]

    # Serialise to check current size
    buf = io.BytesIO()
    save_fmt = current_fmt if current_fmt in ("JPEG", "PNG") else "JPEG"
    if save_fmt == "JPEG":
        img_out = _to_rgb(img)
        img_out.save(buf, format="JPEG", quality=90, optimize=True)
    else:
        img.save(buf, format="PNG", optimize=True, compress_level=9)
    current_bytes = buf.getvalue()

    if max_kb is not None and len(current_bytes) / 1024 > max_kb:
        # Transparency can only survive in PNG, so it decides the format before
        # anything else does.
        jpeg_ok = "JPEG" in accepted and not has_alpha(img)

        if save_fmt == "PNG" and jpeg_ok and is_photographic(img):
            # A photograph squeezed into a 256-colour palette comes back
            # dithered and speckled. JPEG holds the same size far more cleanly.
            current_bytes = compress_to_jpeg(img, max_kb)
            save_fmt = "JPEG"
            applied.append("Converted to JPEG — better quality than a reduced PNG palette")
        elif save_fmt == "PNG":
            current_bytes = compress_to_png(img, max_kb)
            # PNG is lossless, so on flat artwork it may still not reach a
            # display-sized limit. Falling back to JPEG is then the only option.
            if len(current_bytes) / 1024 > max_kb and jpeg_ok:
                current_bytes = compress_to_jpeg(img, max_kb)
                save_fmt = "JPEG"
                applied.append("Converted to JPEG — PNG could not reach the size limit")
        else:
            current_bytes = compress_to_jpeg(img, max_kb)

        # Report what was actually achieved. Claiming success without checking
        # handed back files that were still over the limit — in the PNG case,
        # occasionally larger than the original.
        final_kb = len(current_bytes) / 1024
        if final_kb <= max_kb:
            applied.append(f"Compressed to {final_kb:.1f} KB (limit {max_kb} KB)")
        else:
            applied.append(
                f"Reduced to {final_kb:.1f} KB — still over the {max_kb} KB limit"
                + (", and PNG transparency prevents converting to JPEG"
                   if save_fmt == "PNG" and has_alpha(img) else "")
            )

    return current_bytes, save_fmt, applied
