import fitz

from models import IMAGE_PROCESS_NONE


def apply_image_processing(pixmap: fitz.Pixmap, mode: str) -> fitz.Pixmap:
    if mode == IMAGE_PROCESS_NONE:
        return pixmap

    raise ValueError(f"Unsupported image processing mode: {mode}")
