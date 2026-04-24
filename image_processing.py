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

    # スキャン由来の紙色・影・周辺減光をならして、背景を白に近づける。
    normalized = _flatten_background(gray)

    # 薄い文字やインクのかすれを拾いやすくするため、局所コントラストを上げる。
    contrasted = _boost_local_contrast(normalized)

    # 最後に白黒へ二極化する。出力サイズも小さくなりやすい。
    binary = _binarize(contrasted)

    # 薄い複製防止透かしは局所コントラスト補正で黒く拾われやすい。
    # 濃い本文と、それに接する薄い縁だけを残し、独立した灰色の点描は白へ戻す。
    binary = _remove_pale_marks(binary, gray)
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
    """ぼかした画像を背景推定として使い、紙色や影を均一化する。"""
    kernel_size = _odd_kernel_size(gray.shape, ratio=0.03, minimum=31)
    background = cv2.GaussianBlur(gray, (kernel_size, kernel_size), 0)
    return cv2.divide(gray, background, scale=255)


def _boost_local_contrast(gray):
    """CLAHEでページ内の場所ごとの薄さの差を補正する。"""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


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


def _remove_pale_marks(binary, original_gray):
    """薄い透かしを落としつつ、本文の淡い縁は残す。"""
    strong_ink = original_gray < 172
    weak_ink = original_gray < 220
    black_candidate = (binary == 0) & weak_ink

    # 文字は薄い画素だけで構成される部分があっても、同じ連結成分のどこかに
    # 濃い芯が出やすい。透かしの点描は濃い芯を含まない小片になりやすい。
    component_count, labels = cv2.connectedComponents(black_candidate.astype(np.uint8), connectivity=8)
    keep_labels = np.zeros(component_count, dtype=bool)
    keep_labels[np.unique(labels[strong_ink & black_candidate])] = True
    keep_mask = keep_labels[labels] & black_candidate

    result = np.full(binary.shape, 255, dtype=np.uint8)
    result[keep_mask] = 0
    return result


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
