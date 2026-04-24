import os
from typing import Callable

import fitz

from image_processing import apply_image_processing
from models import OUTPUT_PDF, ProcessingOptions, ProcessingResult
from epub_writer import save_as_epub


def normalize_output_path(save_dir, filename, output_format):
    filename = filename.strip() or "output"
    ext = ".pdf" if output_format == OUTPUT_PDF else ".epub"
    if not filename.endswith(ext):
        filename += ext
    return os.path.join(save_dir, filename), filename


def process_documents(
    options: ProcessingOptions,
    on_file_done: Callable[[int], None] | None = None,
) -> ProcessingResult:
    is_pdf = options.output_format == OUTPUT_PDF
    zoom = options.dpi / 72
    new_doc = fitz.open()
    image_list = []
    page_count = 0

    try:
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

            if on_file_done is not None:
                on_file_done(file_index + 1)

        if is_pdf:
            new_doc.save(options.output_path, garbage=3, deflate=True)
        else:
            save_as_epub(
                options.output_path,
                image_list,
                options.output_title,
                options.epub_direction,
            )

        return ProcessingResult(
            output_path=options.output_path,
            page_count=page_count,
            file_size_mb=os.path.getsize(options.output_path) / (1024 * 1024),
        )
    finally:
        new_doc.close()


def _qt_rect_to_pdf_rect(q_rect, page_width, page_height, viewport_width, viewport_height):
    scale_x = page_width / viewport_width
    scale_y = page_height / viewport_height
    return fitz.Rect(
        q_rect.left() * scale_x,
        q_rect.top() * scale_y,
        q_rect.right() * scale_x,
        q_rect.bottom() * scale_y,
    )
