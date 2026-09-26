"""Server-side compression of ID images to ≤ 300 KB JPEG (spec §5)."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from . import rules

_START_EDGE = 1600
_QUALITIES = (85, 75, 65, 55, 45)


class InvalidImage(ValueError):
    pass


def compress_to_jpeg(raw: bytes, max_bytes: int = rules.MAX_DOCUMENT_BYTES) -> bytes:
    """Decode any Pillow-readable image, fix orientation, drop metadata, shrink until it fits."""
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage(str(exc)) from exc

    edge = _START_EDGE
    while edge >= 200:
        candidate = img.copy()
        candidate.thumbnail((edge, edge))
        for quality in _QUALITIES:
            buf = io.BytesIO()
            candidate.save(buf, "JPEG", quality=quality, optimize=True)  # no EXIF: location/device data dropped
            if buf.tell() <= max_bytes:
                return buf.getvalue()
        edge = int(edge * 0.75)
    raise InvalidImage("image cannot be compressed under the size limit")
