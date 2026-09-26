"""Server-side compression of uploaded images (ID documents, expense receipts) to ≤ 300 KB JPEG (spec §5)."""

import hashlib
import io
import uuid
from dataclasses import dataclass

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_STORED_BYTES = 300 * 1024  # after compression (spec §5)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # before compression
_START_EDGE = 1600
_QUALITIES = (85, 75, 65, 55, 45)


class InvalidImage(ValueError):
    pass


def compress_to_jpeg(raw: bytes, max_bytes: int = MAX_STORED_BYTES) -> bytes:
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


@dataclass(frozen=True)
class StoredImage:
    relative_path: str  # relative to the attachments directory
    size: int
    sha256: str

    @property
    def absolute_path(self):
        return settings.RUNTIME.attachments_dir / self.relative_path


def store_image(raw: bytes, folder: str) -> StoredImage:
    """Compress and write under ``attachments/<folder>/``. Raises InvalidImage for non-images or > 10 MB.

    The caller deletes ``absolute_path`` if its transaction fails, so no orphan file stays behind.
    """
    if len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidImage("upload too large")
    data = compress_to_jpeg(raw)
    stored = StoredImage(f"{folder}/{uuid.uuid4().hex}.jpg", len(data), hashlib.sha256(data).hexdigest())
    stored.absolute_path.parent.mkdir(parents=True, exist_ok=True)
    stored.absolute_path.write_bytes(data)
    return stored
