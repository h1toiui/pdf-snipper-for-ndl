from dataclasses import dataclass

from PySide6.QtCore import QRect

OUTPUT_PDF = "pdf"
OUTPUT_EPUB = "epub"

EPUB_LTR = "ltr"
EPUB_RTL = "rtl"

IMAGE_PROCESS_NONE = "none"
IMAGE_PROCESS_ENHANCE = "enhance"


class ProcessingCancelled(Exception):
    """ユーザー操作によって処理が中止されたことを表す。"""


@dataclass(frozen=True)
class ProcessingOptions:
    file_paths: list[str]
    output_path: str
    output_title: str
    output_author: str
    crop_rects: list[QRect]
    viewport_width: int
    viewport_height: int
    dpi: int
    grayscale: bool
    output_format: str
    epub_direction: str
    image_processing: str = IMAGE_PROCESS_NONE
    ocr_text_output: bool = False
    ocr_command: str = "ndlocr-lite"
    cover_image_path: str = ""


@dataclass(frozen=True)
class ProcessingResult:
    output_path: str
    page_count: int
    file_size_mb: float
    ocr_embedded: bool = False
