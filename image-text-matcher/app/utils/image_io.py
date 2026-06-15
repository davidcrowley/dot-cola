from __future__ import annotations

from fastapi import UploadFile


SUPPORTED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


async def read_upload_bytes(upload: UploadFile) -> bytes:
    if upload.content_type and upload.content_type not in SUPPORTED_CONTENT_TYPES:
        raise ValueError(f"Unsupported image content type: {upload.content_type}")

    contents = await upload.read()
    if not contents:
        raise ValueError("Uploaded image is empty")
    return contents

