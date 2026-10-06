"""Tests for privacy-safe photo evidence sanitization and upload endpoints (FR-M4, DPDP)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from floodroute.api.main import create_app
from floodroute.api.photo import (
    PhotoSanitizationError,
    sanitize_photo,
    store_photo,
)


def _make_image_bytes(size: tuple[int, int] = (100, 100), fmt: str = "JPEG", add_exif: bool = True) -> bytes:
    img = Image.new("RGB", size, color="blue")
    buf = io.BytesIO()
    if add_exif and fmt == "JPEG":
        exif = img.getexif()
        exif[0x010E] = "User commentary and camera info"  # ImageDescription
        exif[0x0132] = "2026:10:06 05:00:00"  # DateTime
        img.save(buf, format=fmt, exif=exif)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def test_sanitize_photo_validation():
    # Empty
    with pytest.raises(PhotoSanitizationError, match="Empty photo payload"):
        sanitize_photo(b"")

    # Corrupt
    with pytest.raises(PhotoSanitizationError, match="Corrupt or invalid"):
        sanitize_photo(b"not an image at all")

    # Limit exceeded
    with pytest.raises(PhotoSanitizationError, match="exceeds limit"):
        sanitize_photo(_make_image_bytes(), max_file_size=100)


def test_sanitize_photo_strips_exif_and_scales():
    raw = _make_image_bytes(size=(2200, 1400), fmt="JPEG", add_exif=True)
    # Confirm raw has EXIF
    raw_img = Image.open(io.BytesIO(raw))
    assert len(raw_img.getexif()) > 0

    proc = sanitize_photo(raw, max_dimension=1600)
    assert proc.photo_ref.startswith("ph_")
    assert proc.photo_ref.endswith(".jpg")
    assert proc.content_type == "image/jpeg"
    assert proc.width <= 1600
    assert proc.height <= 1600
    assert proc.sanitized_bytes > 0

    # Verify sanitized image has NO EXIF
    san_img = Image.open(io.BytesIO(proc.data))
    assert len(san_img.getexif()) == 0


def test_store_photo(tmp_path):
    raw = _make_image_bytes()
    proc = sanitize_photo(raw)
    p = store_photo(proc, tmp_path)
    assert p.exists()
    assert p.name == proc.photo_ref
    assert p.read_bytes() == proc.data


def test_api_photo_upload_and_retrieve():
    app = create_app()
    client = TestClient(app)

    raw = _make_image_bytes(size=(300, 200))

    # 1. Upload photo
    res = client.post(
        "/v1/reports/photo",
        content=raw,
        headers={"Content-Type": "image/jpeg"},
    )
    assert res.status_code == 201
    data = res.json()
    assert "photo_ref" in data
    photo_ref = data["photo_ref"]
    assert photo_ref.startswith("ph_")
    assert data["content_type"] == "image/jpeg"
    assert data["width"] == 300
    assert data["height"] == 200

    # 2. Retrieve photo
    get_res = client.get(f"/v1/reports/photo/{photo_ref}")
    assert get_res.status_code == 200
    assert get_res.headers["content-type"] == "image/jpeg"
    assert "Cache-Control" in get_res.headers

    # 3. Invalid photo_ref rejection
    bad_res = client.get("/v1/reports/photo/invalid_name.png")
    assert bad_res.status_code == 400

    # 4. Non-existent photo
    not_found = client.get("/v1/reports/photo/ph_000000000000000000000000.jpg")
    assert not_found.status_code == 404
