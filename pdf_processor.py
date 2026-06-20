import os
import tempfile
from typing import Callable

import fitz

from image_processing import apply_image_processing
from models import OUTPUT_PDF, ProcessingOptions, ProcessingResult
from ocr_processor import run_ndlocr_lite
from epub_writer import save_as_epub

OCR_DPI = 200
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def normalize_output_path(save_dir, filename, output_format):
    """保存先、入力名、出力形式から最終的な出力パスとタイトルを作る。"""
    title = filename.strip() or "output"
    ext = ".pdf" if output_format == OUTPUT_PDF else ".epub"
    if title.lower().endswith(ext):
        title = title[: -len(ext)]
    safe_filename = _safe_filename(title) + ext
    return os.path.join(save_dir, safe_filename), title


def process_documents(
    options: ProcessingOptions,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> ProcessingResult:
    """指定されたPDF群を切り抜き、PDFまたはEPUBとして保存する。"""
    is_pdf = options.output_format == OUTPUT_PDF
    zoom = options.dpi / 72
    image_list = []
    page_count = 0
    ocr_pages = []
    should_run_ocr = options.ocr_text_output
    crop_rects = [rect for rect in options.crop_rects if not rect.isNull()]
    total_pages = _count_output_pages(options.file_paths, len(crop_rects))

    if on_progress is not None:
        on_progress("prepare", 0, total_pages)

    with fitz.open() as new_doc, tempfile.TemporaryDirectory() as temp_dir:
        ocr_image_dir = os.path.join(temp_dir, "ocr-images")
        ocr_result_dir = os.path.join(temp_dir, "ocr-results")
        if should_run_ocr:
            os.makedirs(ocr_image_dir, exist_ok=True)
            os.makedirs(ocr_result_dir, exist_ok=True)

        for file_path in options.file_paths:
            with fitz.open(file_path) as doc:
                for page in doc:
                    for q_rect in crop_rects:
                        pdf_rect = _qt_rect_to_pdf_rect(
                            q_rect,
                            page.rect.width,
                            page.rect.height,
                            options.viewport_width,
                            options.viewport_height,
                        )
                        if should_run_ocr:
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
                            on_progress("render", page_count, total_pages)

        if should_run_ocr:
            if on_progress is not None:
                on_progress("ocr", 0, 0)
            ocr_pages = run_ndlocr_lite(
                ocr_image_dir,
                ocr_result_dir,
                options.ocr_command,
            )
            if on_progress is not None:
                on_progress("ocr_done", total_pages, total_pages)

        if is_pdf:
            if should_run_ocr:
                if on_progress is not None:
                    on_progress("embed", total_pages, total_pages)
                _embed_ocr_in_pdf(new_doc, ocr_pages)
            _set_pdf_metadata(new_doc, options.output_title, options.output_author)
            if on_progress is not None:
                on_progress("save", total_pages, total_pages)
            new_doc.save(options.output_path, garbage=3, deflate=True)
        else:
            if on_progress is not None:
                on_progress("save", total_pages, total_pages)
            save_as_epub(
                options.output_path,
                image_list,
                options.output_title,
                options.epub_direction,
                ocr_pages=ocr_pages,
                author=options.output_author,
            )

        return ProcessingResult(
            output_path=options.output_path,
            page_count=page_count,
            file_size_mb=os.path.getsize(options.output_path) / (1024 * 1024),
            ocr_embedded=should_run_ocr,
        )


def _safe_filename(value):
    """ファイル名として使えない文字を取り除く。"""
    cleaned = "".join("_" if char in INVALID_FILENAME_CHARS else char for char in value)
    cleaned = cleaned.strip().strip(".")
    return cleaned or "output"


def _count_output_pages(file_paths, crop_count):
    """入力PDFのページ数と切り抜き矩形数から出力ページ数を見積もる。"""
    if crop_count <= 0:
        return 0

    page_count = 0
    for file_path in file_paths:
        with fitz.open(file_path) as doc:
            page_count += doc.page_count * crop_count
    return page_count


def _qt_rect_to_pdf_rect(
    q_rect, page_width, page_height, viewport_width, viewport_height
):
    """プレビュー上のQt矩形をPDFページ座標の矩形へ変換する。"""
    scale_x = page_width / viewport_width
    scale_y = page_height / viewport_height
    return fitz.Rect(
        q_rect.x() * scale_x,
        q_rect.y() * scale_y,
        (q_rect.x() + q_rect.width()) * scale_x,
        (q_rect.y() + q_rect.height()) * scale_y,
    )


def _embed_ocr_in_pdf(doc, ocr_pages):
    """OCR結果をPDF各ページの透明テキストレイヤーとして埋め込む。"""
    for page_index, ocr_page in enumerate(ocr_pages[: doc.page_count]):
        page = doc[page_index]
        if not ocr_page.lines:
            continue

        scale_x = page.rect.width / max(1, ocr_page.image_width)
        scale_y = page.rect.height / max(1, ocr_page.image_height)
        for line in ocr_page.lines:
            rect = fitz.Rect(
                line.x0 * scale_x,
                line.y0 * scale_y,
                line.x1 * scale_x,
                line.y1 * scale_y,
            )
            _insert_invisible_textbox(page, rect, line.text, line.is_vertical)


def _set_pdf_metadata(doc, title, author):
    """生成PDFへタイトルと著者のメタデータを設定する。"""
    metadata = dict(doc.metadata or {})
    metadata["title"] = title.strip()
    metadata["author"] = author.strip()
    doc.set_metadata(metadata)


def _insert_invisible_textbox(page, rect, text, is_vertical):
    """指定範囲へ検索可能だが見えないテキストを挿入する。"""
    if rect.is_empty or not text.strip():
        return

    base_size = rect.width if is_vertical else rect.height
    rotate = 90 if is_vertical else 0
    for ratio in (0.85, 0.7, 0.55, 0.4):
        fontsize = max(3, base_size * ratio)
        remaining = page.insert_textbox(
            rect,
            text,
            fontname="japan",
            fontsize=fontsize,
            render_mode=3,
            rotate=rotate,
            overlay=True,
        )
        if remaining >= 0:
            return
