import json
import os
import shlex
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


TEXT_KEYS = {"text", "content", "contents", "string", "value"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2", ".bmp"}


def run_ndlocr_lite(image_dir, output_dir, command="ndlocr-lite"):
    """Run NDLOCR-Lite for a directory of cropped page images and return page texts."""
    args = _build_command(command, image_dir, output_dir)
    try:
        completed = subprocess.run(
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


def _collect_ocr_text(output_dir):
    output_path = Path(output_dir)
    text_files = sorted(output_path.rglob("*.txt"))
    if text_files:
        return "\n\n".join(path.read_text(encoding="utf-8", errors="replace") for path in text_files)

    chunks = []
    for path in sorted(output_path.rglob("*")):
        if path.suffix.lower() in IMAGE_SUFFIXES:
            continue
        if path.suffix.lower() == ".json":
            text = _text_from_json(path)
        elif path.suffix.lower() == ".xml":
            text = _text_from_xml(path)
        else:
            continue

        if text:
            chunks.append(f"--- {path.stem} ---\n{text}")

    return "\n\n".join(chunks)


def _collect_ocr_pages(output_dir):
    output_path = Path(output_dir)
    page_paths = sorted(
        path
        for path in output_path.rglob("*")
        if path.suffix.lower() in {".json", ".xml", ".txt"}
    )
    return [_text_from_result_file(path) for path in page_paths]


def _text_from_result_file(path):
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _text_from_json(path)
    if suffix == ".xml":
        return _text_from_xml(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _text_from_json(path):
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    values = []
    _collect_json_strings(data, values)
    if not values:
        _collect_all_json_strings(data, values)
    return "\n".join(values)


def _collect_json_strings(value, values):
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
    root = ET.parse(path).getroot()
    values = []
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.lower() in TEXT_KEYS and value.strip():
                values.append(value.strip())
        if len(element) == 0 and element.text and element.text.strip():
            values.append(element.text.strip())
    return "\n".join(values)
