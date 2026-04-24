from dataclasses import dataclass

from PySide6.QtCore import QRect


OUTPUT_PDF = "pdf"
OUTPUT_EPUB = "epub"

EPUB_LTR = "ltr"
EPUB_RTL = "rtl"

IMAGE_PROCESS_NONE = "none"


@dataclass(frozen=True)
class ProcessingOptions:
    file_paths: list[str]
    output_path: str
    output_title: str
    crop_rects: list[QRect]
    viewport_width: int
    viewport_height: int
    dpi: int
    grayscale: bool
    output_format: str
    epub_direction: str
    image_processing: str = IMAGE_PROCESS_NONE


@dataclass(frozen=True)
class ProcessingResult:
    output_path: str
    page_count: int
    file_size_mb: float
