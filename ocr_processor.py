import json
import os
import shlex
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


TEXT_KEYS = {"text", "content", "contents", "string", "value"}


@dataclass(frozen=True)
class OCRLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    is_vertical: bool
    confidence: float | None = None


@dataclass(frozen=True)
class OCRPage:
    lines: list[OCRLine]
    image_width: float
    image_height: float
    text: str


def run_ndlocr_lite(image_dir, output_dir, command="ndlocr-lite"):
    """Run NDLOCR-Lite for a directory of cropped page images and return pages."""
    args = _build_command(command, image_dir, output_dir)
    try:
        subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "NDLOCR-Lite command was not found. Install ndlocr-lite or set "
            "NDLOCR_LITE_COMMAND to the executable command."
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = "\n".join(part for part in (exc.stdout, exc.stderr) if part)
        raise RuntimeError(f"NDLOCR-Lite failed:\n{details}") from exc

    return _collect_ocr_pages(output_dir)


def _build_command(command, image_dir, output_dir):
    """NDLOCR-Liteを呼び出すためのコマンド引数を組み立てる。"""
    args = shlex.split(os.environ.get("NDLOCR_LITE_COMMAND", command))
    if not args:
        raise RuntimeError("NDLOCR-Lite command is empty.")

    return [
        *args,
        "--sourcedir",
        str(image_dir),
        "--output",
        str(output_dir),
        "--json-only",
    ]


def _collect_ocr_pages(output_dir):
    """NDLOCR-Liteの出力ディレクトリからページ順にOCR結果を集める。"""
    output_path = Path(output_dir)
    page_paths = sorted(
        path
        for path in output_path.rglob("*")
        if path.suffix.lower() in {".json", ".xml", ".txt"}
    )
    return [_page_from_result_file(path) for path in page_paths]


def _page_from_result_file(path):
    """JSON/XML/TXTのOCR結果ファイルをOCRPageへ変換する。"""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _page_from_json(path)
    if suffix == ".xml":
        text = _text_from_xml(path)
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    else:
        text = ""
    return OCRPage(lines=[], image_width=0, image_height=0, text=text)


def _fallback_text_from_json_data(data):
    """標準構造で読めないJSONから本文らしい文字列を集める。"""
    values = []
    _collect_json_strings(data, values)
    if not values:
        _collect_all_json_strings(data, values)
    return "\n".join(values)


def _page_from_json(path):
    """NDLOCR-Lite JSONを読み込み、ページ単位のOCR結果へ変換する。"""
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    page = _page_from_ndlocr_json(data)
    if page.text or page.lines:
        return page
    return OCRPage(lines=[], image_width=0, image_height=0, text=_fallback_text_from_json_data(data))


def _page_from_ndlocr_json(data):
    """NDLOCR-Liteのcontents構造から行情報と段落テキストを作る。"""
    contents = data.get("contents") if isinstance(data, dict) else None
    if not isinstance(contents, list):
        return OCRPage(lines=[], image_width=0, image_height=0, text="")

    imginfo = data.get("imginfo") if isinstance(data.get("imginfo"), dict) else {}
    image_width = float(imginfo.get("img_width") or 0)
    image_height = float(imginfo.get("img_height") or 0)

    paragraphs = []
    ocr_lines = []
    for block in contents:
        block_lines = _ocr_lines_from_block(block)
        ocr_lines.extend(block_lines)
        paragraph = _join_ocr_lines([line.text for line in block_lines])
        if paragraph:
            paragraphs.append(paragraph)

    return OCRPage(
        lines=ocr_lines,
        image_width=image_width,
        image_height=image_height,
        text="\n\n".join(paragraphs),
    )


def _ocr_lines_from_block(block):
    """contentsブロックを再帰的にたどり、OCR行を抽出する。"""
    lines = []
    if isinstance(block, dict):
        line = _ocr_line_from_dict(block)
        if line is not None:
            lines.append(line)
        for value in block.values():
            lines.extend(_ocr_lines_from_block(value))
    elif isinstance(block, list):
        for item in block:
            lines.extend(_ocr_lines_from_block(item))
    return lines


def _ocr_line_from_dict(data):
    """boundingBox付きの辞書から1行分のOCRLineを作る。"""
    text = data.get("text")
    bbox = data.get("boundingBox")
    if not isinstance(text, str) or not text.strip() or not _is_bbox(bbox):
        return None

    xs = [float(point[0]) for point in bbox]
    ys = [float(point[1]) for point in bbox]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    is_vertical = (y1 - y0) > (x1 - x0)
    confidence = data.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = None

    return OCRLine(
        text=text.strip(),
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        is_vertical=is_vertical,
        confidence=confidence,
    )


def _is_bbox(value):
    """NDLOCR-LiteのboundingBoxとして扱える形か判定する。"""
    return (
        isinstance(value, list)
        and len(value) >= 4
        and all(isinstance(point, list) and len(point) >= 2 for point in value[:4])
    )


def _join_ocr_lines(lines):
    """同一contentsブロック内のOCR行を段落テキストとして詰める。"""
    joined = ""
    for line in lines:
        # line = _normalize_ocr_line(line)
        if not line:
            continue
        if joined and _needs_space_between(joined[-1], line[0]):
            joined += " "
        joined += line
    return joined


def _normalize_ocr_line(line):
    """OCR行内の余分な空白と改行を単一空白へ正規化する。"""
    return " ".join(line.strip().split())


def _needs_space_between(left, right):
    """英数字同士を連結するときに空白が必要か判定する。"""
    return left.isascii() and right.isascii() and left.isalnum() and right.isalnum()


def _collect_json_strings(value, values):
    """JSON内の本文キーに紐づく文字列を再帰的に集める。"""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.lower()
            is_text_key = normalized_key in TEXT_KEYS or normalized_key.endswith("_text")
            if isinstance(item, str) and is_text_key:
                text = item.strip()
                if text:
                    values.append(text)
            else:
                _collect_json_strings(item, values)
    elif isinstance(value, list):
        for item in value:
            _collect_json_strings(item, values)


def _collect_all_json_strings(value, values):
    """本文キーで見つからない場合にJSON内の全文字列を集める。"""
    if isinstance(value, dict):
        for item in value.values():
            _collect_all_json_strings(item, values)
    elif isinstance(value, list):
        for item in value:
            _collect_all_json_strings(item, values)
    elif isinstance(value, str):
        text = value.strip()
        if text:
            values.append(text)


def _text_from_xml(path):
    """XML形式のOCR結果から本文テキストを抽出する。"""
    root = ET.parse(path).getroot()
    values = []
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.lower() in TEXT_KEYS and value.strip():
                values.append(value.strip())
        if len(element) == 0 and element.text and element.text.strip():
            values.append(element.text.strip())
    return "\n".join(values)
