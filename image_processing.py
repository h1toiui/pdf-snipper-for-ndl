import fitz
import cv2
import numpy as np

from models import IMAGE_PROCESS_ENHANCE, IMAGE_PROCESS_NONE


def apply_image_processing(pixmap: fitz.Pixmap, mode: str) -> fitz.Pixmap:
    """UIで選ばれた画像処理モードをPixmapへ適用する入口。"""
    if mode == IMAGE_PROCESS_NONE:
        return pixmap
    if mode == IMAGE_PROCESS_ENHANCE:
        return enhance_for_ereader(pixmap)

    raise ValueError(f"Unsupported image processing mode: {mode}")


def enhance_for_ereader(pixmap: fitz.Pixmap) -> fitz.Pixmap:
    """電子リーダーで読みやすい白背景・黒文字の2値画像に寄せる。"""
    # 以降の処理は濃淡だけを見ればよいので、最初にグレースケールへ揃える。
    gray = _pixmap_to_gray_array(pixmap)

    # 中央付近の明るい紙面を背景白として推定し、ページ全体の明るさを揃える。
    normalized = _flatten_background(gray)

    # 白黒へ二極化する。出力サイズも小さくなりやすい。
    binary = _binarize(normalized)
    return _gray_array_to_pixmap(binary)


def _pixmap_to_gray_array(pixmap: fitz.Pixmap):
    """PyMuPDFのPixmapをOpenCVで扱えるグレースケール配列へ変換する。"""
    data = np.frombuffer(pixmap.samples, dtype=np.uint8)

    if pixmap.n == 1:
        return data.reshape(pixmap.height, pixmap.width).copy()

    image = data.reshape(pixmap.height, pixmap.width, pixmap.n)

    # OpenCVのRGB変換前にアルファチャンネルは落とす。
    if pixmap.alpha:
        image = image[:, :, :-1]

    if image.shape[2] == 1:
        return image[:, :, 0].copy()
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def _flatten_background(gray):
    """中央付近の明るい画素を背景白として推定し、紙色を白へ寄せる。"""
    height, width = gray.shape[:2]
    y_margin = height // 5
    x_margin = width // 5
    center = gray[y_margin : height - y_margin, x_margin : width - x_margin]
    if center.size == 0:
        center = gray

    background_level = max(1.0, float(np.percentile(center, 95)))
    normalized = gray.astype(np.float32) * (255.0 / background_level)
    return np.clip(normalized, 0, 255).astype(np.uint8)


def _binarize(gray):
    """ページ全体ではなく近傍の明るさを基準に白黒へ分ける。"""
    block_size = _odd_kernel_size(gray.shape, ratio=0.02, minimum=35)
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        11,
    )


def _gray_array_to_pixmap(gray):
    """OpenCVの配列をPNG経由でPyMuPDFのPixmapへ戻す。"""
    ok, buffer = cv2.imencode(".png", gray)
    if not ok:
        raise ValueError("Failed to encode enhanced image")
    return fitz.Pixmap(buffer.tobytes())


def _odd_kernel_size(shape, ratio, minimum):
    """OpenCVのぼかし・二値化で必要な奇数サイズを画像寸法から決める。"""
    shortest_side = max(1, min(shape[:2]))
    size = max(minimum, int(shortest_side * ratio))
    if size % 2 == 0:
        size += 1
    return size
