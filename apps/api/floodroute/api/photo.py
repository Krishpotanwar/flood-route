"""Privacy-safe photo sanitization pipeline for flood evidence (DPDP Act 2023, FR-M4).

Strips all EXIF metadata (GPS, camera serial, device info), resizes large images,
re-encodes pure RGB pixels, and generates immutable content-addressed photo references.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTO_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DIMENSION = 1600  # px max width or height
JPEG_QUALITY = 85
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "MPO"})


class PhotoSanitizationError(ValueError):
    """Raised when an uploaded photo fails boundary validation or sanitization."""


@dataclass(frozen=True)
class ProcessedPhoto:
    """Sanitized, privacy-safe photo evidence."""

    photo_ref: str
    content_type: str
    data: bytes
    width: int
    height: int
    original_bytes: int
    sanitized_bytes: int


def sanitize_photo(
    raw_bytes: bytes,
    max_dimension: int = MAX_DIMENSION,
    jpeg_quality: int = JPEG_QUALITY,
    max_file_size: int = MAX_PHOTO_BYTES,
) -> ProcessedPhoto:
    """Validate, strip EXIF metadata, downscale if needed, and re-encode to JPEG.

    Raises PhotoSanitizationError if the image is empty, exceeds max_file_size,
    corrupt, or in an unapproved format.
    """
    if not raw_bytes:
        raise PhotoSanitizationError("Empty photo payload")

    if len(raw_bytes) > max_file_size:
        raise PhotoSanitizationError(
            f"Photo size ({len(raw_bytes)} bytes) exceeds limit ({max_file_size} bytes)"
        )

    try:
        img_in = Image.open(io.BytesIO(raw_bytes))
        fmt = (img_in.format or "").upper()
        if fmt not in ALLOWED_FORMATS:
            raise PhotoSanitizationError(
                f"Unsupported image format '{fmt}'; allowed: {sorted(ALLOWED_FORMATS)}"
            )

        # Apply EXIF orientation to pixel buffer before stripping metadata
        img_transposed = ImageOps.exif_transpose(img_in)

        # Scale down if exceeds max_dimension
        if img_transposed.width > max_dimension or img_transposed.height > max_dimension:
            img_transposed.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        # Convert to pure RGB, discarding alpha, palette, and metadata
        rgb_img = img_transposed.convert("RGB")
        width, height = rgb_img.size

        # Re-encode to clean JPEG buffer with no EXIF
        out_buf = io.BytesIO()
        rgb_img.save(out_buf, format="JPEG", quality=jpeg_quality, optimize=True)
        sanitized_data = out_buf.getvalue()

        # Deterministic content-addressed reference
        digest = hashlib.sha256(sanitized_data).hexdigest()[:24]
        photo_ref = f"ph_{digest}.jpg"

        return ProcessedPhoto(
            photo_ref=photo_ref,
            content_type="image/jpeg",
            data=sanitized_data,
            width=width,
            height=height,
            original_bytes=len(raw_bytes),
            sanitized_bytes=len(sanitized_data),
        )

    except (UnidentifiedImageError, OSError) as e:
        raise PhotoSanitizationError(f"Corrupt or invalid image: {e}") from e


def store_photo(
    photo: ProcessedPhoto,
    storage_dir: Path | str,
) -> Path:
    """Save sanitized photo to target directory. Returns path."""
    dest_dir = Path(storage_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / photo.photo_ref
    dest_path.write_bytes(photo.data)
    return dest_path
