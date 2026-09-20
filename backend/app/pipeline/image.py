"""Photo intake: validate, read consented GPS, strip metadata, store, and optionally analyse.

Privacy first. A phone photo carries the exact coordinates, the time, the device
model and sometimes the owner's name. NagarNetra reads the GPS **only if the
citizen ticked the box**, and then re-encodes the pixels into a fresh file so
that every other EXIF field is gone before anything touches disk.

The photo is a *signal*, never a requirement. If Pillow cannot read the upload,
if the multimodal model is unavailable, or if the file is simply not an image,
the complaint still goes through and the record says "image not analysed".
"""

from __future__ import annotations

import base64
import io
import logging
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

from app.config.settings import settings

logger = logging.getLogger(__name__)

#: Formats we are willing to decode and re-encode.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}
MAX_DIMENSION = 1600
#: Long edge used when sending to a multimodal model - keeps tokens and latency down.
LLM_MAX_DIMENSION = 1024


@dataclass
class ImageIntake:
    """Result of accepting one uploaded photo."""

    stored_path: str | None = None
    width: int = 0
    height: int = 0
    exif_gps_lat: float | None = None
    exif_gps_lon: float | None = None
    exif_stripped: bool = False
    accepted: bool = False
    note: str = ""
    findings: dict[str, Any] = field(default_factory=dict)


def _rational_to_degrees(value: Any) -> float | None:
    """Convert an EXIF (degrees, minutes, seconds) rational triple to decimal."""
    try:
        degrees, minutes, seconds = (float(part) for part in value)
        return degrees + minutes / 60.0 + seconds / 3600.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _read_gps(image: Image.Image) -> tuple[float | None, float | None]:
    """Extract decimal lat/lon from EXIF, or (None, None)."""
    try:
        exif = image.getexif()
        if not exif:
            return None, None
        gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if not gps:
            return None, None
        lat = _rational_to_degrees(gps.get(2))
        lon = _rational_to_degrees(gps.get(4))
        if lat is None or lon is None:
            return None, None
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lon = -lon
        return lat, lon
    except Exception as exc:  # noqa: BLE001 - malformed EXIF must never fail intake
        logger.debug("Could not read EXIF GPS: %s", exc)
        return None, None


def process_upload(
    raw: bytes,
    *,
    filename: str = "",
    consent_exif_gps: bool = False,
) -> ImageIntake:
    """Validate, optionally read GPS, strip all metadata and store the photo."""
    result = ImageIntake()
    if not raw:
        result.note = "No image data received"
        return result

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(raw) > max_bytes:
        result.note = f"Photo is larger than the {settings.max_upload_mb} MB limit"
        return result

    try:
        probe = Image.open(io.BytesIO(raw))
        probe.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.info("Rejected non-image upload %r: %s", filename[:60], exc)
        result.note = "The attached file could not be read as an image"
        return result

    image_format = (probe.format or "").upper()
    if image_format and image_format not in ALLOWED_FORMATS:
        result.note = f"Unsupported image format: {image_format}"
        return result

    if consent_exif_gps:
        lat, lon = _read_gps(probe)
        result.exif_gps_lat, result.exif_gps_lon = lat, lon
        if lat is not None:
            result.note = "Location read from the photo with your consent"
    else:
        result.note = "Photo metadata removed; location not read from the photo"

    # Re-encode from pixels only. This is what actually strips EXIF - saving the
    # original bytes with a new name would keep every tag.
    working = probe.convert("RGB")
    working.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    clean = Image.new("RGB", working.size)
    clean.putdata(list(working.getdata()))

    target_dir: Path = settings.resolved_upload_dir
    name = f"{secrets.token_hex(12)}.jpg"
    destination = target_dir / name
    try:
        clean.save(destination, format="JPEG", quality=85, optimize=True)
    except OSError as exc:
        logger.warning("Could not store photo: %s", exc)
        result.note = "The photo could not be saved"
        return result

    result.stored_path = name
    result.width, result.height = clean.size
    result.exif_stripped = True
    result.accepted = True
    return result


def encode_for_llm(stored_name: str) -> tuple[str | None, str | None]:
    """Return (base64, media_type) for a stored photo, downscaled for the model."""
    path = settings.resolved_upload_dir / stored_name
    if not path.exists():
        return None, None
    try:
        with Image.open(path) as image:
            working = image.convert("RGB")
            working.thumbnail((LLM_MAX_DIMENSION, LLM_MAX_DIMENSION), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            working.save(buffer, format="JPEG", quality=80)
        return base64.b64encode(buffer.getvalue()).decode("ascii"), "image/jpeg"
    except (OSError, ValueError) as exc:
        logger.warning("Could not encode photo for the model: %s", exc)
        return None, None


def image_url_path(stored_name: str | None) -> str | None:
    """Public URL for a stored photo."""
    return f"/media/{stored_name}" if stored_name else None
