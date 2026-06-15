from __future__ import annotations

import cv2
import numpy as np


MAX_IMAGE_DIMENSION = 2400


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Decode uploaded bytes into an OpenCV BGR image."""
    data = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Uploaded file is not a supported image")
    return image


def resize_if_large(image: np.ndarray, max_dimension: int = MAX_IMAGE_DIMENSION) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_dimension:
        return image

    scale = max_dimension / float(longest)
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def improve_contrast(image: np.ndarray) -> np.ndarray:
    """Apply light CLAHE on luminance; conservative enough for general OCR."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)
    enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """Decode and lightly normalize an image for OCR.

    This intentionally avoids aggressive thresholding or deskewing because those
    can damage photos and low-quality scans. Future versions can add optional
    deskew, perspective correction, or ROI-specific processing here.
    """
    image = decode_image(image_bytes)
    image = resize_if_large(image)
    image = cv2.fastNlMeansDenoisingColored(image, None, 3, 3, 7, 21)
    image = improve_contrast(image)
    return image

