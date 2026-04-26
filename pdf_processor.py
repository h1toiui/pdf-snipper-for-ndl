import os
import tempfile
from typing import Callable

import fitz

from image_processing import apply_image_processing
from models import OUTPUT_PDF, ProcessingOptions, ProcessingResult
from ocr_processor import run_ndlocr_lite
from epub_writer import save_as_epub

OCR_DPI = 200


def normalize_output_path(save_dir, filename, output_format):
    filename = filename.strip() or "output"
    ext = ".pdf" if output_format == OUTPUT_PDF else ".epub"
    if not filename.endswith(ext):
        filename += ext
    return os.path.join(save_dir, filename), filename


def process_documents(
    options: ProcessingOptions,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> ProcessingResult:
    is_pdf = options.output_format == OUTPUT_PDF
    zoom = options.dpi / 72
    image_list = []
    page_count = 0
    ocr_output_path = None
    ocr_texts = []
    should_embed_ocr = options.ocr_text_output and not is_pdf

    with fitz.open() as new_doc, tempfile.TemporaryDirectory() as temp_dir:
        ocr_image_dir = os.path.join(temp_dir, "ocr-images")
        ocr_result_dir = os.path.join(temp_dir, "ocr-results")
        if should_embed_ocr:
            os.makedirs(ocr_image_dir, exist_ok=True)
            os.makedirs(ocr_result_dir, exist_ok=True)

        for file_index, file_path in enumerate(options.file_paths):
            with fitz.open(file_path) as doc:
                for page in doc:
                    for q_rect in options.crop_rects:
                        if q_rect.isNull():
                            continue

                        pdf_rect = _qt_rect_to_pdf_rect(
                            q_rect,
                            page.rect.width,
                            page.rect.height,
                            options.viewport_width,
                            options.viewport_height,
                        )
                        if should_embed_ocr:
                            ocr_pix = page.get_pixmap(
                                matrix=fitz.Matrix(OCR_DPI / 72, OCR_DPI / 72),
                                clip=pdf_rect,
                                colorspace=fitz.csRGB,
                            )
                            ocr_pix.save(
                                os.path.join(
                                    ocr_image_dir,
                                    f"page_{page_count + 1:05d}.png",
                                )
                            )

                        colorspace = fitz.csGRAY if options.grayscale else fitz.csRGB
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(zoom, zoom),
                            clip=pdf_rect,
                            colorspace=colorspace,
                        )
                        pix = apply_image_processing(pix, options.image_processing)

                        if is_pdf:
                            img_page = new_doc.new_page(
                                width=pdf_rect.width,
                                height=pdf_rect.height,
                            )
                            img_page.insert_image(img_page.rect, pixmap=pix)
                        else:
                            image_list.append(pix.tobytes("png"))

                        page_count += 1

            if on_progress is not None:
                on_progress("render", file_index + 1, len(options.file_paths))

        if should_embed_ocr:
            if on_progress is not None:
                on_progress("ocr", 0, 1)
            ocr_texts = run_ndlocr_lite(
                ocr_image_dir,
                ocr_result_dir,
                options.ocr_command,
            )
            if on_progress is not None:
                on_progress("ocr", 1, 1)

        if is_pdf:
            new_doc.save(options.output_path, garbage=3, deflate=True)
        else:
            save_as_epub(
                options.output_path,
                image_list,
                options.output_title,
                options.epub_direction,
                ocr_texts=ocr_texts,
            )

        return ProcessingResult(
            output_path=options.output_path,
            page_count=page_count,
            file_size_mb=os.path.getsize(options.output_path) / (1024 * 1024),
            ocr_output_path=ocr_output_path,
            ocr_embedded=should_embed_ocr,
        )


def _qt_rect_to_pdf_rect(q_rect, page_width, page_height, viewport_width, viewport_height):
    scale_x = page_width / viewport_width
    scale_y = page_height / viewport_height
    return fitz.Rect(
        q_rect.left() * scale_x,
        q_rect.top() * scale_y,
        q_rect.right() * scale_x,
        q_rect.bottom() * scale_y,
    )
